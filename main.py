# ============================================
# SKINGLOW AI - PRODUCTION BACKEND
# Professional Skin Analysis API
# ============================================

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
import uvicorn
from PIL import Image
import io
import os
from typing import Dict, Optional, List
import requests
from dotenv import load_dotenv
import jwt
from pydantic import BaseModel
import uuid
import sqlite3
import hashlib
import asyncio
import cv2
import numpy as np

# Load environment variables
load_dotenv()

# ============================================
# DATABASE SETUP (SQLite)
# ============================================

DATABASE_FILE = "skinglow.db"

def get_db():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    with get_db() as conn:
        # USERS TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                role TEXT DEFAULT 'customer',
                is_approved INTEGER DEFAULT 0,
                phone TEXT,
                address TEXT,
                latitude REAL,
                longitude REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        # Add missing columns
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'role' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'customer'")
        if 'is_approved' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN is_approved INTEGER DEFAULT 0")
        if 'phone' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        if 'address' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN address TEXT")
        if 'last_login' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN last_login TIMESTAMP")
        
        # ANALYSES TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                skin_type TEXT NOT NULL,
                skin_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                characteristics TEXT,
                recommendations TEXT,
                recommended_oils TEXT,
                products TEXT,
                method TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # STORES TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS stores (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                address TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                phone TEXT,
                logo_url TEXT,
                rating REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            )
        ''')
        
        # PRODUCTS TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                category TEXT,
                skin_type TEXT,
                image_url TEXT,
                stock INTEGER DEFAULT 0,
                rating REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                is_approved INTEGER DEFAULT 0,
                is_sponsored INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        ''')
        
        # SPONSORED PRODUCTS TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sponsored_products (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                vendor_id TEXT NOT NULL,
                amount_paid REAL NOT NULL,
                start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_date TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                views INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (vendor_id) REFERENCES users(id)
            )
        ''')
        
        # VENDOR_SUBSCRIPTIONS TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS vendor_subscriptions (
                id TEXT PRIMARY KEY,
                vendor_id TEXT NOT NULL,
                plan TEXT DEFAULT 'basic',
                amount_paid REAL,
                start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_date TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (vendor_id) REFERENCES users(id)
            )
        ''')
        
        # ORDERS TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                total_amount REAL NOT NULL,
                delivery_address TEXT,
                delivery_latitude REAL,
                delivery_longitude REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        ''')
        
        # ORDER ITEMS TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        ''')
        
        # Create indexes
        conn.execute('CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_products_store_id ON products(store_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_users_is_approved ON users(is_approved)')
        
        # CREATE DEFAULT ADMIN USER
        admin_email = "admin@skinglow.com"
        admin_password = "Admin@123"
        
        existing_admin = conn.execute("SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
        
        if not existing_admin:
            admin_id = str(uuid.uuid4())
            password_hash = hash_password(admin_password)
            conn.execute(
                """INSERT INTO users (id, email, password_hash, name, role, is_approved, created_at) 
                   VALUES (?, ?, ?, ?, 'admin', 1, CURRENT_TIMESTAMP)""",
                (admin_id, admin_email, password_hash, "Super Admin")
            )
            conn.commit()
            print("✅ Default admin user created!")
            print("   Email: admin@skinglow.com")
            print("   Password: Admin@123")
        else:
            print("✅ Admin user already exists")
        
        conn.commit()
        print("✅ Database initialized successfully!")

# Initialize database
init_db()

# ============================================
# INITIALIZE FASTAPI
# ============================================
app = FastAPI(title="SkinGlow AI API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ============================================
# SECURITY CONFIGURATION
# ============================================
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
security = HTTPBearer()

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id") or payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============================================
# REQUEST MODELS
# ============================================
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    role: Optional[str] = "customer"

class LoginRequest(BaseModel):
    email: str
    password: str

# ============================================
# IMAGE PREPROCESSING (Fix Bias & Inconsistency)
# ============================================

def standardize_image(image_bytes: bytes) -> np.ndarray:
    """Standardize image to reduce lighting and angle bias"""
    
    # Load image
    image = Image.open(io.BytesIO(image_bytes))
    
    # Convert to RGB if needed
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Resize to standard size
    image = image.resize((500, 500), Image.LANCZOS)
    
    # Convert to numpy array
    img_array = np.array(image)
    
    # Apply CLAHE for lighting normalization
    lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge([l, a, b])
    img_array = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    
    # Normalize brightness
    img_array = cv2.normalize(img_array, None, 0, 255, cv2.NORM_MINMAX)
    
    # Apply slight Gaussian blur to reduce noise
    img_array = cv2.GaussianBlur(img_array, (3, 3), 0)
    
    return img_array

def extract_skin_region(image_array: np.ndarray) -> tuple:
    """Extract only skin region from image"""
    
    # Convert to HSV for better skin detection
    hsv = cv2.cvtColor(image_array, cv2.COLOR_RGB2HSV)
    
    # Skin color range in HSV (expanded for African skin tones)
    lower_skin = np.array([0, 20, 70], dtype=np.uint8)
    upper_skin = np.array([20, 255, 255], dtype=np.uint8)
    
    # Create mask
    mask = cv2.inRange(hsv, lower_skin, upper_skin)
    
    # Clean mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    
    # Apply mask
    skin_region = cv2.bitwise_and(image_array, image_array, mask=mask)
    
    return skin_region, mask

# ============================================
# MEDIAPIPE (Optional)
# ============================================
MEDIAPIPE_AVAILABLE = False
try:
    import mediapipe as mp
    os.environ['GLOG_minloglevel'] = '2'
    mp_face_detection = mp.solutions.face_detection
    face_detection = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
    MEDIAPIPE_AVAILABLE = True
    print("✅ MediaPipe loaded!")
except:
    print("⚠️ MediaPipe not available")

# ============================================
# IMPROVED SKIN ANALYSIS FUNCTIONS
# ============================================

def analyze_with_mediapipe(image_bytes: bytes) -> Optional[Dict]:
    """Analyze skin using MediaPipe with standardized preprocessing"""
    if not MEDIAPIPE_AVAILABLE:
        return None
    
    try:
        # Step 1: Standardize image first
        standardized_img = standardize_image(image_bytes)
        
        # Convert to RGB for MediaPipe
        image_rgb = cv2.cvtColor(standardized_img, cv2.COLOR_RGB2BGR)
        image_rgb = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2RGB)
        
        # Step 2: Detect face
        results = face_detection.process(image_rgb)
        
        if results.detections:
            h, w, _ = standardized_img.shape
            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            x = max(0, int(bbox.xmin * w))
            y = max(0, int(bbox.ymin * h))
            width = min(w - x, int(bbox.width * w))
            height = min(h - y, int(bbox.height * h))
            
            # Extract face region
            face_region = standardized_img[y:y+height, x:x+width]
            
            if face_region.size > 0:
                # Step 3: Extract only skin region
                skin_region, mask = extract_skin_region(face_region)
                
                # Get skin pixels only
                skin_pixels = skin_region[mask > 0]
                
                if len(skin_pixels) > 100:
                    # Convert to grayscale
                    gray_face = cv2.cvtColor(face_region, cv2.COLOR_RGB2GRAY)
                    gray_skin = cv2.cvtColor(skin_region, cv2.COLOR_RGB2GRAY)
                    gray_skin_masked = gray_skin[mask > 0]
                    
                    # Calculate multiple metrics
                    texture_var = np.var(gray_skin_masked) if len(gray_skin_masked) > 0 else np.var(gray_face)
                    avg_brightness = np.mean(gray_skin_masked) if len(gray_skin_masked) > 0 else np.mean(gray_face)
                    
                    # Color analysis from skin pixels
                    if len(skin_pixels) > 0:
                        avg_r = np.mean(skin_pixels[:, 0])
                        avg_g = np.mean(skin_pixels[:, 1])
                        avg_b = np.mean(skin_pixels[:, 2])
                    else:
                        avg_r = avg_g = avg_b = 128
                    
                    # Texture analysis using Laplacian
                    laplacian = cv2.Laplacian(gray_face, cv2.CV_64F)
                    texture_score = np.var(laplacian)
                    
                    # Scoring system
                    scores = {"dry": 0, "oily": 0, "combination": 0, "sensitive": 0, "normal": 0}
                    
                    # Rule 1: Texture variance
                    if texture_var > 3000:
                        scores["oily"] += 3
                        scores["combination"] += 2
                    elif texture_var < 1500:
                        scores["dry"] += 3
                        scores["normal"] += 1
                    else:
                        scores["normal"] += 2
                        scores["combination"] += 2
                    
                    # Rule 2: Brightness
                    if avg_brightness > 180:
                        scores["dry"] += 2
                        scores["sensitive"] += 2
                    elif avg_brightness < 100:
                        scores["oily"] += 2
                    else:
                        scores["normal"] += 2
                    
                    # Rule 3: Color balance (redness = sensitivity)
                    if avg_r > avg_g + 10 and avg_r > avg_b + 10:
                        scores["sensitive"] += 3
                    elif avg_g > avg_r + 10 and avg_g > avg_b + 10:
                        scores["oily"] += 2
                    
                    # Rule 4: Texture score
                    if texture_score > 500:
                        scores["sensitive"] += 2
                        scores["dry"] += 1
                    elif texture_score < 200:
                        scores["normal"] += 2
                        scores["oily"] += 1
                    
                    # Get highest scoring type
                    max_score = max(scores.values())
                    candidates = [k for k, v in scores.items() if v == max_score]
                    
                    if len(candidates) > 1:
                        if "normal" in candidates:
                            skin_type = "normal"
                        elif "combination" in candidates:
                            skin_type = "combination"
                        else:
                            skin_type = candidates[0]
                    else:
                        skin_type = candidates[0]
                    
                    # Calculate confidence
                    confidence = 0.75
                    if max_score >= 5:
                        confidence = 0.85
                    elif max_score >= 3:
                        confidence = 0.75
                    else:
                        confidence = 0.65
                    
                    return {
                        "skin_type": skin_type,
                        "confidence": confidence,
                        "method": "MediaPipe AI"
                    }
        
        return None
    except Exception as e:
        print(f"MediaPipe analysis error: {e}")
        return None

def analyze_with_fallback(image_bytes: bytes) -> Dict:
    """Deterministic fallback analysis (no randomness)"""
    try:
        # Standardize image first
        standardized_img = standardize_image(image_bytes)
        
        # Extract skin region
        skin_region, mask = extract_skin_region(standardized_img)
        
        # Calculate metrics from skin region
        gray = cv2.cvtColor(skin_region, cv2.COLOR_RGB2GRAY)
        skin_pixels = gray[mask > 0]
        
        if len(skin_pixels) > 100:
            texture_var = np.var(skin_pixels)
            avg_brightness = np.mean(skin_pixels)
            
            # Color analysis
            skin_rgb = skin_region[mask > 0]
            if len(skin_rgb) > 0 and len(skin_rgb.shape) > 1:
                avg_r = np.mean(skin_rgb[:, 0])
                avg_g = np.mean(skin_rgb[:, 1])
                avg_b = np.mean(skin_rgb[:, 2])
                is_reddish = avg_r > avg_g + 10 and avg_r > avg_b + 10
            else:
                is_reddish = False
            
            # Deterministic logic (no random)
            if texture_var > 3000:
                skin_type = "oily"
                confidence = 0.80
            elif texture_var < 1500:
                skin_type = "dry"
                confidence = 0.80
            elif is_reddish:
                skin_type = "sensitive"
                confidence = 0.75
            elif 1500 <= texture_var <= 2500:
                skin_type = "normal"
                confidence = 0.75
            else:
                skin_type = "combination"
                confidence = 0.70
            
            return {
                "skin_type": skin_type,
                "confidence": confidence,
                "method": "Color Analysis"
            }
        else:
            return {
                "skin_type": "normal",
                "confidence": 0.60,
                "method": "Default"
            }
            
    except Exception as e:
        print(f"Fallback analysis error: {e}")
        return {
            "skin_type": "normal",
            "confidence": 0.50,
            "method": "Default"
        }

def analyze_with_consistency(image_bytes: bytes) -> Dict:
    """Run analysis with consistency check"""
    
    # First try MediaPipe
    result = analyze_with_mediapipe(image_bytes)
    if result:
        return result
    
    # Fallback to improved color analysis
    return analyze_with_fallback(image_bytes)

# ============================================
# WEATHER API
# ============================================
WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')
WEATHER_API_URL = "https://api.openweathermap.org/data/2.5"

async def get_city_from_coordinates(lat: float, lon: float) -> str:
    try:
        response = requests.get(f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json", 
                                headers={'User-Agent': 'SkinGlowApp/1.0'}, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('address', {}).get('city') or data.get('address', {}).get('town') or 'Unknown'
    except:
        pass
    return 'Unknown'

def get_weather_data(lat: float, lon: float) -> Dict:
    if not WEATHER_API_KEY:
        return {"success": False, "uv_index": 5, "temperature": 25, "city": "Unknown"}
    try:
        response = requests.get(f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric", timeout=10)
        if response.status_code != 200:
            return get_weather_data_fallback(lat, lon)
        current = response.json().get('current', {})
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        city_name = loop.run_until_complete(get_city_from_coordinates(lat, lon))
        return {"success": True, "temperature": current.get('temp', 25), "humidity": current.get('humidity', 60), 
                "condition": current.get('weather', [{}])[0].get('description', 'clear'), "uv_index": current.get('uvi', 5), "city": city_name}
    except:
        return get_weather_data_fallback(lat, lon)

def get_weather_data_fallback(lat: float, lon: float) -> Dict:
    try:
        response = requests.get(f"{WEATHER_API_URL}/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric", timeout=10)
        data = response.json()
        current_hour = datetime.now().hour
        uv_index = 5 if 6 <= current_hour <= 18 else 0
        return {"success": True, "temperature": data.get('main', {}).get('temp', 25), "humidity": data.get('main', {}).get('humidity', 60),
                "condition": data.get('weather', [{}])[0].get('description', 'clear'), "uv_index": uv_index, "city": data.get('name', 'Unknown')}
    except:
        return {"success": False, "uv_index": 5, "temperature": 25, "city": "Unknown"}

def get_sunscreen_recommendation(uv_index: float, skin_type: str) -> Dict:
    if uv_index <= 2:
        uv_level, base_spf, advice = "Low", 15, "Minimal UV risk."
    elif uv_index <= 5:
        uv_level, base_spf, advice = "Moderate", 30, "Sunscreen required."
    elif uv_index <= 7:
        uv_level, base_spf, advice = "High", 50, "Strong protection needed."
    elif uv_index <= 10:
        uv_level, base_spf, advice = "Very High", 50, "Maximum protection required."
    else:
        uv_level, base_spf, advice = "Extreme", 50, "Avoid sun exposure."
    skin_advice = {'dry': "Hydrating sunscreen", 'oily': "Oil-free sunscreen", 'combination': "Lightweight sunscreen", 'sensitive': "Mineral sunscreen", 'normal': "Broad-spectrum sunscreen"}
    return {"uv_index": uv_index, "uv_level": uv_level, "advice": advice, "recommended_spf": base_spf, 
            "reapplication_hours": 2 if uv_index > 5 else 4, "skin_advice": skin_advice.get(skin_type, skin_advice['normal']),
            "tips": ["Apply 15-20 min before sun exposure", f"Reapply every {2 if uv_index > 5 else 4} hours", "Use 1/2 tsp for face and neck"]}

# ============================================
# SKIN CARE DATABASE
# ============================================
SKIN_CARE_DATA = {
    "dry": {"name": "Dry Skin", "characteristics": ["Lacks moisture", "May feel tight or flaky"], 
            "recommendations": ["Use hydrating cleanser", "Apply hyaluronic acid", "Use rich moisturizer", "Add facial oil"],
            "oils": ["Argan Oil", "Rosehip Oil", "Jojoba Oil"]},
    "oily": {"name": "Oily Skin", "characteristics": ["Excess sebum", "Shiny appearance"], 
             "recommendations": ["Use foaming cleanser", "Apply niacinamide", "Use gel moisturizer", "Exfoliate weekly"],
             "oils": ["Grapeseed Oil", "Tea Tree Oil", "Hemp Seed Oil"]},
    "combination": {"name": "Combination Skin", "characteristics": ["Oily in T-zone", "Normal or dry on cheeks"],
                    "recommendations": ["Use balancing cleanser", "Lightweight moisturizer", "Exfoliate T-zone"],
                    "oils": ["Jojoba Oil", "Squalane Oil", "Marula Oil"]},
    "sensitive": {"name": "Sensitive Skin", "characteristics": ["Easily irritated", "Prone to redness"],
                  "recommendations": ["Use gentle cleanser", "Calming ingredients", "Minimal products"],
                  "oils": ["Chamomile Oil", "Calendula Oil", "Rose Oil"]},
    "normal": {"name": "Normal Skin", "characteristics": ["Balanced moisture", "Neither too oily nor too dry"],
               "recommendations": ["Regular cleansing", "Antioxidant serum", "SPF daily", "Weekly exfoliation"],
               "oils": ["Argan Oil", "Jojoba Oil", "Rosehip Oil"]}
}

# ============================================
# BASIC API ENDPOINTS
# ============================================

@app.get("/")
async def root():
    return {"status": "healthy", "app": "SkinGlow AI", "version": "3.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "operational", "mediapipe": MEDIAPIPE_AVAILABLE, "weather_api": bool(WEATHER_API_KEY), "skin_types": list(SKIN_CARE_DATA.keys())}

@app.get("/location/{lat}/{lon}")
async def get_location_name(lat: float, lon: float):
    return {"success": True, "city": await get_city_from_coordinates(lat, lon), "latitude": lat, "longitude": lon}

@app.get("/sunscreen/{uv_index}")
async def get_sunscreen(uv_index: float, skin_type: str = "normal"):
    return {"success": True, **get_sunscreen_recommendation(uv_index, skin_type)}

@app.get("/weather/{lat}/{lon}")
async def get_weather(lat: float, lon: float, skin_type: str = "normal", user_id: str = Depends(verify_token)):
    weather = get_weather_data(lat, lon)
    if not weather.get("success"):
        return {"success": False, "error": weather.get("error", "Weather service unavailable")}
    sunscreen = get_sunscreen_recommendation(weather.get("uv_index", 5), skin_type)
    return {"success": True, "weather": weather, "sunscreen": sunscreen}

# ============================================
# AUTH ENDPOINTS
# ============================================

@app.post("/auth/register")
async def register(request: RegisterRequest):
    try:
        email, password, name = request.email, request.password, request.name
        phone, address, role = request.phone, request.address, request.role
        
        with get_db() as conn:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                return JSONResponse(status_code=400, content={"success": False, "message": "Email already registered"})
            
            user_id = str(uuid.uuid4())
            password_hash = hash_password(password)
            is_approved = 1 if role == 'customer' else 0
            
            conn.execute("""INSERT INTO users (id, email, password_hash, name, role, is_approved, phone, address, created_at) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                        (user_id, email, password_hash, name, role, is_approved, phone, address))
            conn.commit()
        
        token_data = {"sub": email, "user_id": user_id, "role": role, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        
        return {"success": True, "message": "User registered successfully", "token": token, "token_type": "bearer",
                "user": {"id": user_id, "email": email, "name": name, "role": role, "is_approved": is_approved}}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.post("/auth/login")
async def login(request: LoginRequest):
    try:
        email, password = request.email, request.password
        with get_db() as conn:
            user = conn.execute("SELECT id, email, password_hash, name, role, is_approved, created_at, phone, address FROM users WHERE email = ?", (email,)).fetchone()
            if not user or user["password_hash"] != hash_password(password):
                return JSONResponse(status_code=401, content={"success": False, "message": "Invalid email or password"})
            
            if user["role"] == "vendor" and user["is_approved"] == 0:
                return JSONResponse(status_code=403, content={"success": False, "message": "Your vendor account is pending admin approval"})
            
            user_id, user_email, user_name, user_role, is_approved, member_since, phone, address = user["id"], user["email"], user["name"], user["role"], user["is_approved"], user["created_at"], user["phone"], user["address"]
            conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
            conn.commit()
        
        token_data = {"sub": user_email, "user_id": user_id, "role": user_role, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        
        return {"success": True, "message": "Login successful", "token": token, "token_type": "bearer",
                "user": {"id": user_id, "email": user_email, "name": user_name, "role": user_role, "is_approved": is_approved, "phone": phone, "address": address, "member_since": member_since}}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.get("/users/me")
async def get_current_user(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT id, email, name, role, is_approved, created_at, last_login, phone, address FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return JSONResponse(status_code=404, content={"success": False, "message": "User not found"})
        return {"success": True, "user": dict(user)}

# ============================================
# SKIN ANALYSIS ENDPOINT (UPDATED)
# ============================================

@app.post("/analyze")
async def analyze_skin(file: UploadFile = File(...), user_id: str = Depends(verify_token)):
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    try:
        contents = await file.read()
        
        # Use improved consistency check
        analysis = analyze_with_consistency(contents)
        
        skin_type = analysis.get("skin_type", "normal")
        confidence = analysis.get("confidence", 0.75)
        method = analysis.get("method", "AI Analysis")
        
        skin_data = SKIN_CARE_DATA.get(skin_type, SKIN_CARE_DATA["normal"])
        
        # Save to database
        analysis_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                """INSERT INTO analyses (id, user_id, skin_type, skin_name, confidence, characteristics, recommendations, recommended_oils, method) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id, user_id, skin_type, skin_data["name"], confidence,
                    "|".join(skin_data["characteristics"]),
                    "|".join(skin_data["recommendations"]),
                    "|".join(skin_data["oils"]),
                    method
                )
            )
            conn.commit()
        
        return {
            "success": True,
            "skin_type": skin_type,
            "skin_name": skin_data["name"],
            "confidence": confidence,
            "characteristics": skin_data["characteristics"],
            "recommendations": skin_data["recommendations"],
            "recommended_oils": skin_data["oils"],
            "products": skin_data["products"],
            "method": method,
            "analysis_id": analysis_id,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/analyses/history")
async def get_analysis_history(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        analyses = conn.execute("SELECT id, skin_type, skin_name, confidence, recommendations, recommended_oils, method, created_at FROM analyses WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (user_id,)).fetchall()
        return {"success": True, "analyses": [dict(a) for a in analyses]}

@app.get("/users/stats")
async def get_user_stats(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        analyses = conn.execute("SELECT skin_type, confidence, created_at FROM analyses WHERE user_id = ?", (user_id,)).fetchall()
        if not analyses:
            return {"success": True, "total_analyses": 0, "active_days": 0, "skin_health_score": 85, "skin_type_trends": {}}
        skin_type_counts, active_days = {}, set()
        for a in analyses:
            skin_type_counts[a["skin_type"]] = skin_type_counts.get(a["skin_type"], 0) + 1
            active_days.add(a["created_at"][:10])
        latest = analyses[0]
        scores = {"normal": 92, "combination": 82, "dry": 78, "oily": 75, "sensitive": 70}
        base_score = scores.get(latest["skin_type"], 85)
        skin_health_score = int(base_score * (latest["confidence"] * 0.3 + 0.7))
        return {"success": True, "total_analyses": len(analyses), "active_days": len(active_days), 
                "skin_health_score": skin_health_score, "skin_type_trends": skin_type_counts}

# ============================================
# VENDOR ENDPOINTS
# ============================================

@app.post("/vendor/products/add")
async def vendor_add_product(request: dict, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role, is_approved FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "vendor" or user["is_approved"] != 1:
            return JSONResponse(status_code=403, content={"success": False, "message": "Only approved vendors can add products"})
    
    name, description, price, category, skin_type, stock, image_url = request.get('name'), request.get('description'), request.get('price'), request.get('category'), request.get('skin_type'), request.get('stock', 0), request.get('image_url', '')
    product_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute("INSERT INTO products (id, store_id, name, description, price, category, skin_type, stock, image_url, is_approved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)", (product_id, user_id, name, description, price, category, skin_type, stock, image_url))
        conn.commit()
    return {"success": True, "message": "Product submitted for approval", "product_id": product_id}

@app.get("/vendor/products")
async def vendor_get_products(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        products = conn.execute("SELECT * FROM products WHERE store_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        return {"success": True, "products": [dict(p) for p in products]}

@app.post("/vendor/sponsor")
async def sponsor_product(request: dict, user_id: str = Depends(verify_token)):
    product_id, amount, days = request.get('product_id'), request.get('amount', 0), request.get('days', 7)
    with get_db() as conn:
        product = conn.execute("SELECT id, is_approved FROM products WHERE id = ? AND store_id = ?", (product_id, user_id)).fetchone()
        if not product or product["is_approved"] == 0:
            return JSONResponse(status_code=400, content={"success": False, "message": "Product not found or not approved"})
        sponsored_id, end_date = str(uuid.uuid4()), datetime.now() + timedelta(days=days)
        conn.execute("INSERT INTO sponsored_products (id, product_id, vendor_id, amount_paid, end_date) VALUES (?, ?, ?, ?, ?)", (sponsored_id, product_id, user_id, amount, end_date))
        conn.execute("UPDATE products SET is_sponsored = 1 WHERE id = ?", (product_id,))
        conn.commit()
    return {"success": True, "message": f"Product sponsored for {days} days", "end_date": end_date.isoformat()}

@app.get("/vendor/stats")
async def vendor_stats(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        products = conn.execute("SELECT COUNT(*) as total FROM products WHERE store_id = ?", (user_id,)).fetchone()
        sales = conn.execute("""SELECT SUM(oi.quantity * oi.price) as revenue, COUNT(DISTINCT o.id) as orders 
                               FROM orders o JOIN order_items oi ON o.id = oi.order_id 
                               JOIN products p ON oi.product_id = p.id 
                               WHERE p.store_id = ? AND o.status = 'delivered'""", (user_id,)).fetchone()
        views = conn.execute("SELECT SUM(views) as total_views FROM products WHERE store_id = ?", (user_id,)).fetchone()
        return {"success": True, "total_products": products["total"] or 0, "total_revenue": sales["revenue"] or 0, 
                "total_orders": sales["orders"] or 0, "total_views": views["total_views"] or 0}

# ============================================
# SUPER ADMIN ENDPOINTS
# ============================================

@app.get("/admin/stats")
async def admin_stats(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        
        total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
        total_customers = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'customer'").fetchone()["count"]
        total_vendors = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'vendor'").fetchone()["count"]
        pending_vendors = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'vendor' AND is_approved = 0").fetchone()["count"]
        total_products = conn.execute("SELECT COUNT(*) as count FROM products").fetchone()["count"]
        pending_products = conn.execute("SELECT COUNT(*) as count FROM products WHERE is_approved = 0").fetchone()["count"]
        total_orders = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()["count"]
        total_revenue = conn.execute("SELECT SUM(total_amount) as total FROM orders WHERE status = 'delivered'").fetchone()["total"] or 0
        
        all_users = conn.execute("SELECT id, email, name, role, is_approved, phone, address, created_at, last_login FROM users ORDER BY created_at DESC").fetchall()
        all_vendors = conn.execute("SELECT id, email, name, is_approved, phone, address, created_at FROM users WHERE role = 'vendor' ORDER BY created_at DESC").fetchall()
        pending_vendors_list = conn.execute("SELECT id, email, name, phone, address, created_at FROM users WHERE role = 'vendor' AND is_approved = 0 ORDER BY created_at DESC").fetchall()
        pending_products_list = conn.execute("""SELECT p.*, u.name as vendor_name, u.email as vendor_email 
                                               FROM products p JOIN users u ON p.store_id = u.id 
                                               WHERE p.is_approved = 0 ORDER BY p.created_at DESC""").fetchall()
        
        return {
            "success": True,
            "stats": {
                "users": {"total": total_users, "customers": total_customers, "vendors": total_vendors, "pending_vendors": pending_vendors},
                "products": {"total": total_products, "pending": pending_products},
                "orders": {"total": total_orders, "revenue": total_revenue}
            },
            "all_users": [dict(u) for u in all_users],
            "all_vendors": [dict(v) for v in all_vendors],
            "pending_vendors": [dict(v) for v in pending_vendors_list],
            "pending_products": [dict(p) for p in pending_products_list]
        }

@app.get("/admin/users")
async def admin_get_users(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        users = conn.execute("SELECT id, email, name, role, is_approved, phone, address, created_at, last_login FROM users ORDER BY created_at DESC").fetchall()
        return {"success": True, "users": [dict(u) for u in users]}

@app.get("/admin/user/{target_user_id}")
async def admin_get_user(target_user_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        admin = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not admin or admin["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        
        user = conn.execute("SELECT id, email, name, role, is_approved, phone, address, created_at, last_login FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if not user:
            return JSONResponse(status_code=404, content={"success": False, "message": "User not found"})
        
        analyses = conn.execute("SELECT id, skin_type, skin_name, confidence, created_at FROM analyses WHERE user_id = ? ORDER BY created_at DESC", (target_user_id,)).fetchall()
        orders = conn.execute("SELECT id, status, total_amount, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC", (target_user_id,)).fetchall()
        
        return {"success": True, "user": dict(user), "analyses": [dict(a) for a in analyses], "orders": [dict(o) for o in orders]}

@app.get("/admin/vendors")
async def admin_get_vendors(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        
        vendors = conn.execute("SELECT id, email, name, is_approved, phone, address, created_at FROM users WHERE role = 'vendor' ORDER BY created_at DESC").fetchall()
        result = []
        for vendor in vendors:
            product_count = conn.execute("SELECT COUNT(*) as count FROM products WHERE store_id = ?", (vendor["id"],)).fetchone()["count"]
            vendor_dict = dict(vendor)
            vendor_dict["product_count"] = product_count
            result.append(vendor_dict)
        return {"success": True, "vendors": result}

@app.get("/admin/vendor/{vendor_id}")
async def admin_get_vendor(vendor_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        admin = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not admin or admin["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        
        vendor = conn.execute("SELECT id, email, name, is_approved, phone, address, created_at FROM users WHERE id = ? AND role = 'vendor'", (vendor_id,)).fetchone()
        if not vendor:
            return JSONResponse(status_code=404, content={"success": False, "message": "Vendor not found"})
        
        products = conn.execute("SELECT id, name, price, category, skin_type, stock, is_approved, is_sponsored, views, created_at FROM products WHERE store_id = ? ORDER BY created_at DESC", (vendor_id,)).fetchall()
        orders = conn.execute("""SELECT o.id, o.status, o.total_amount, o.created_at, COUNT(oi.id) as items 
                                FROM orders o JOIN order_items oi ON o.id = oi.order_id 
                                WHERE o.store_id = ? GROUP BY o.id ORDER BY o.created_at DESC""", (vendor_id,)).fetchall()
        return {"success": True, "vendor": dict(vendor), "products": [dict(p) for p in products], "orders": [dict(o) for o in orders]}

@app.post("/admin/approve-vendor/{vendor_id}")
async def approve_vendor(vendor_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        admin = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not admin or admin["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("UPDATE users SET is_approved = 1 WHERE id = ? AND role = 'vendor'", (vendor_id,))
        conn.commit()
    return {"success": True, "message": "Vendor approved successfully"}

@app.post("/admin/reject-vendor/{vendor_id}")
async def reject_vendor(vendor_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        admin = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not admin or admin["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("DELETE FROM users WHERE id = ? AND role = 'vendor'", (vendor_id,))
        conn.commit()
    return {"success": True, "message": "Vendor application rejected"}

@app.post("/admin/approve-product/{product_id}")
async def approve_product(product_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        admin = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not admin or admin["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("UPDATE products SET is_approved = 1 WHERE id = ?", (product_id,))
        conn.commit()
    return {"success": True, "message": "Product approved successfully"}

@app.post("/admin/reject-product/{product_id}")
async def reject_product(product_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        admin = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not admin or admin["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
    return {"success": True, "message": "Product rejected and deleted"}

@app.post("/admin/delete-user/{target_user_id}")
async def admin_delete_user(target_user_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        admin = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not admin or admin["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("DELETE FROM users WHERE id = ?", (target_user_id,))
        conn.commit()
    return {"success": True, "message": "User deleted successfully"}

@app.post("/admin/set-vendor-role/{target_user_id}")
async def set_vendor_role(target_user_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        admin = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not admin or admin["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("UPDATE users SET role = 'vendor', is_approved = 0 WHERE id = ?", (target_user_id,))
        conn.commit()
    return {"success": True, "message": "User role updated to vendor (pending approval)"}

# ============================================
# CUSTOMER PRODUCTS ENDPOINT
# ============================================

@app.get("/products/customer")
async def get_customer_products(skin_type: str = None, category: str = None, sort_by: str = "sponsored", user_id: str = Depends(verify_token)):
    with get_db() as conn:
        query = "SELECT p.*, u.name as vendor_name FROM products p JOIN users u ON p.store_id = u.id WHERE p.is_approved = 1"
        params = []
        if skin_type and skin_type != "all":
            query += " AND p.skin_type = ?"
            params.append(skin_type)
        if category and category != "all":
            query += " AND p.category = ?"
            params.append(category)
        
        sort_map = {"sponsored": "p.is_sponsored DESC, p.views DESC, p.created_at DESC", "popular": "p.views DESC, p.created_at DESC",
                    "newest": "p.created_at DESC", "price_low": "p.price ASC", "price_high": "p.price DESC"}
        query += f" ORDER BY {sort_map.get(sort_by, sort_map['sponsored'])}"
        
        products = conn.execute(query, params).fetchall()
        for product in products:
            conn.execute("UPDATE products SET views = views + 1 WHERE id = ?", (product["id"],))
        conn.commit()
        return {"success": True, "products": [dict(p) for p in products]}

@app.get("/products/categories")
async def get_product_categories():
    return {"success": True, "categories": [
        {"id": "cleanser", "name": "Cleanser", "icon": "🧼"}, {"id": "moisturizer", "name": "Moisturizer", "icon": "💧"},
        {"id": "sunscreen", "name": "Sunscreen / SPF", "icon": "☀️"}, {"id": "serum", "name": "Serum", "icon": "✨"},
        {"id": "oil", "name": "Face Oil", "icon": "🌿"}, {"id": "mask", "name": "Face Mask", "icon": "🎭"}, {"id": "toner", "name": "Toner", "icon": "💦"}
    ]}

# ============================================
# CHAT ENDPOINT
# ============================================

import openai

@app.post("/chat")
async def chat(request: dict, user_id: str = Depends(verify_token)):
    user_message = request.get('message', '')
    if not user_message:
        return {"success": False, "response": "Tafadhali uliza swali."}
    openai.api_key = os.getenv('OPENAI_API_KEY', '')
    if not openai.api_key:
        return {"success": False, "response": "AI chat is not configured yet."}
    try:
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[
            {"role": "system", "content": "You are a professional African skincare advisor. Give short, practical advice."},
            {"role": "user", "content": user_message}
        ], max_tokens=300, temperature=0.7)
        return {"success": True, "response": response.choices[0].message.content}
    except Exception as e:
        return {"success": False, "response": "Samahani, nahitaji muda kidogo. Jaribu tena."}

# ============================================
# RUN SERVER
# ============================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print("=" * 60)
    print("🌟 SKINGLOW AI PRODUCTION BACKEND")
    print("=" * 60)
    print(f"✅ MediaPipe: {'Available' if MEDIAPIPE_AVAILABLE else 'Not available'}")
    print(f"✅ Weather API: {'Configured' if WEATHER_API_KEY else 'Not configured'}")
    print(f"✅ Database: SQLite with full vendor/admin tables")
    print("=" * 60)
    print(f"🚀 Server starting on port {port}...")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
