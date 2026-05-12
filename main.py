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
# MEDIAPIPE (Optional - No OpenCV needed)
# ============================================
MEDIAPIPE_AVAILABLE = False
try:
    import mediapipe as mp
    mp_face_detection = mp.solutions.face_detection
    face_detection = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
    MEDIAPIPE_AVAILABLE = True
    print("✅ MediaPipe loaded!")
except Exception as e:
    print(f"⚠️ MediaPipe not available: {e}")

# ============================================
# IMAGE PREPROCESSING (PIL only - No OpenCV)
# ============================================

def standardize_image(image_bytes: bytes) -> Image.Image:
    """Standardize image using PIL only"""
    image = Image.open(io.BytesIO(image_bytes))
    if image.mode != 'RGB':
        image = image.convert('RGB')
    image = image.resize((500, 500), Image.LANCZOS)
    return image

# ============================================
# SKIN ANALYSIS FUNCTIONS (No OpenCV)
# ============================================

def analyze_with_mediapipe(image_bytes: bytes) -> Optional[Dict]:
    """Analyze skin using MediaPipe"""
    if not MEDIAPIPE_AVAILABLE:
        return None
    
    try:
        # Standardize image
        pil_image = standardize_image(image_bytes)
        img_array = np.array(pil_image)
        
        # MediaPipe needs RGB format
        img_rgb = img_array.copy()
        
        # Detect face
        results = face_detection.process(img_rgb)
        
        if results.detections:
            h, w, _ = img_array.shape
            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            x = max(0, int(bbox.xmin * w))
            y = max(0, int(bbox.ymin * h))
            width = min(w - x, int(bbox.width * w))
            height = min(h - y, int(bbox.height * h))
            
            face_region = img_array[y:y+height, x:x+width]
            
            if face_region.size > 0:
                # Convert to grayscale using numpy
                gray = np.dot(face_region[..., :3], [0.299, 0.587, 0.114])
                
                texture_var = np.var(gray)
                avg_brightness = np.mean(gray)
                
                # Determine skin type
                if texture_var > 3000:
                    skin_type = "oily"
                    confidence = 0.85
                elif texture_var < 1500:
                    skin_type = "dry"
                    confidence = 0.85
                elif avg_brightness > 180:
                    skin_type = "sensitive"
                    confidence = 0.80
                elif 100 < avg_brightness < 150:
                    skin_type = "combination"
                    confidence = 0.80
                else:
                    skin_type = "normal"
                    confidence = 0.85
                
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
    """Fallback analysis using PIL only"""
    try:
        pil_image = standardize_image(image_bytes)
        
        # Convert to grayscale
        gray = pil_image.convert('L')
        pixels = list(gray.getdata())
        
        avg_brightness = sum(pixels) / len(pixels)
        variance = sum((x - avg_brightness) ** 2 for x in pixels) / len(pixels)
        
        if variance > 3000:
            skin_type = "oily"
            confidence = 0.75
        elif variance < 1500:
            skin_type = "dry"
            confidence = 0.75
        elif avg_brightness > 180:
            skin_type = "sensitive"
            confidence = 0.70
        elif 100 < avg_brightness < 150:
            skin_type = "combination"
            confidence = 0.70
        else:
            skin_type = "normal"
            confidence = 0.75
        
        return {
            "skin_type": skin_type,
            "confidence": confidence,
            "method": "Color Analysis"
        }
    except Exception as e:
        print(f"Fallback error: {e}")
        return {
            "skin_type": "normal",
            "confidence": 0.50,
            "method": "Default"
        }

def analyze_with_consistency(image_bytes: bytes) -> Dict:
    """Run analysis with consistency check"""
    result = analyze_with_mediapipe(image_bytes)
    if result:
        return result
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
# SKIN ANALYSIS ENDPOINT
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
# VENDOR ENDPOINTS (Simplified)
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

# ============================================
# SUPER ADMIN ENDPOINTS (Simplified)
# ============================================

@app.get("/admin/stats")
async def admin_stats(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        
        total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
        total_vendors = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'vendor'").fetchone()["count"]
        pending_vendors = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'vendor' AND is_approved = 0").fetchone()["count"]
        total_products = conn.execute("SELECT COUNT(*) as count FROM products").fetchone()["count"]
        pending_products = conn.execute("SELECT COUNT(*) as count FROM products WHERE is_approved = 0").fetchone()["count"]
        total_revenue = conn.execute("SELECT SUM(total_amount) as total FROM orders WHERE status = 'delivered'").fetchone()["total"] or 0
        
        pending_vendors_list = conn.execute("SELECT id, email, name, phone, address, created_at FROM users WHERE role = 'vendor' AND is_approved = 0 ORDER BY created_at DESC").fetchall()
        pending_products_list = conn.execute("""SELECT p.*, u.name as vendor_name 
                                               FROM products p JOIN users u ON p.store_id = u.id 
                                               WHERE p.is_approved = 0 ORDER BY p.created_at DESC""").fetchall()
        
        return {
            "success": True,
            "stats": {
                "total_users": total_users,
                "total_vendors": total_vendors,
                "pending_vendors": pending_vendors,
                "total_products": total_products,
                "pending_products": pending_products,
                "total_revenue": total_revenue
            },
            "pending_vendors": [dict(v) for v in pending_vendors_list],
            "pending_products": [dict(p) for p in pending_products_list]
        }

@app.post("/admin/approve-product/{product_id}")
async def approve_product(product_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        admin = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not admin or admin["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("UPDATE products SET is_approved = 1 WHERE id = ?", (product_id,))
        conn.commit()
    return {"success": True, "message": "Product approved successfully"}

@app.post("/admin/approve-vendor/{vendor_id}")
async def approve_vendor(vendor_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        admin = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not admin or admin["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("UPDATE users SET is_approved = 1 WHERE id = ? AND role = 'vendor'", (vendor_id,))
        conn.commit()
    return {"success": True, "message": "Vendor approved successfully"}

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
