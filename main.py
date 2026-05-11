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
# MEDIAPIPE (Optional)
# ============================================
MEDIAPIPE_AVAILABLE = False
try:
    import mediapipe as mp
    import cv2
    import numpy as np
    os.environ['GLOG_minloglevel'] = '2'
    mp_face_detection = mp.solutions.face_detection
    face_detection = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
    MEDIAPIPE_AVAILABLE = True
    print("✅ MediaPipe loaded!")
except:
    print("⚠️ MediaPipe not available")

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

def analyze_with_mediapipe(image_bytes: bytes) -> Optional[Dict]:
    if not MEDIAPIPE_AVAILABLE:
        return None
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = np.array(image)
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = face_detection.process(image_rgb)
        if results.detections:
            h, w, _ = image.shape
            bbox = results.detections[0].location_data.relative_bounding_box
            x, y = int(bbox.xmin * w), int(bbox.ymin * h)
            width, height = int(bbox.width * w), int(bbox.height * h)
            face_region = image_rgb[y:y+height, x:x+width]
            if face_region.size > 0:
                gray_face = cv2.cvtColor(face_region, cv2.COLOR_RGB2GRAY)
                texture_var = np.var(gray_face)
                if texture_var > 3000:
                    return {"skin_type": "oily", "confidence": 0.85, "method": "MediaPipe AI"}
                elif texture_var < 1500:
                    return {"skin_type": "dry", "confidence": 0.85, "method": "MediaPipe AI"}
                else:
                    return {"skin_type": "normal", "confidence": 0.85, "method": "MediaPipe AI"}
        return None
    except:
        return None

def analyze_with_fallback(image_bytes: bytes) -> Dict:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        pixels = list(image.getdata())
        sample = pixels[:min(1000, len(pixels))]
        brightness = sum(sum(p[:3])/3 for p in sample) / len(sample) if sample else 128
        if brightness > 200:
            return {"skin_type": "dry", "confidence": 0.70, "method": "Color Analysis"}
        elif brightness < 80:
            return {"skin_type": "oily", "confidence": 0.70, "method": "Color Analysis"}
        else:
            return {"skin_type": "normal", "confidence": 0.70, "method": "Color Analysis"}
    except:
        return {"skin_type": "normal", "confidence": 0.50, "method": "Default"}

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
# AUTH ENDPOINTS (WITH ROLE SUPPORT)
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
            # Set is_approved: 1 for customer, 0 for vendor (needs admin approval)
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
# SKIN ANALYSIS
# ============================================

@app.post("/analyze")
async def analyze_skin(file: UploadFile = File(...), user_id: str = Depends(verify_token)):
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    try:
        contents = await file.read()
        analysis = analyze_with_mediapipe(contents) or analyze_with_fallback(contents)
        skin_type, confidence, method = analysis["skin_type"], analysis["confidence"], analysis["method"]
        skin_data = SKIN_CARE_DATA.get(skin_type, SKIN_CARE_DATA["normal"])
        analysis_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute("""INSERT INTO analyses (id, user_id, skin_type, skin_name, confidence, characteristics, recommendations, recommended_oils, method) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (analysis_id, user_id, skin_type, skin_data["name"], confidence, 
                         "|".join(skin_data["characteristics"]), "|".join(skin_data["recommendations"]), "|".join(skin_data["oils"]), method))
            conn.commit()
        return {"success": True, "skin_type": skin_type, "skin_name": skin_data["name"], "confidence": confidence,
                "characteristics": skin_data["characteristics"], "recommendations": skin_data["recommendations"],
                "recommended_oils": skin_data["oils"], "analysis_id": analysis_id}
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
# SUPER ADMIN ENDPOINTS (FULL FEATURED)
# ============================================

@app.get("/admin/stats")
async def admin_stats(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        
        # User statistics
        total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
        total_customers = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'customer'").fetchone()["count"]
        total_vendors = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'vendor'").fetchone()["count"]
        pending_vendors = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'vendor' AND is_approved = 0").fetchone()["count"]
        
        # Product statistics
        total_products = conn.execute("SELECT COUNT(*) as count FROM products").fetchone()["count"]
        pending_products = conn.execute("SELECT COUNT(*) as count FROM products WHERE is_approved = 0").fetchone()["count"]
        sponsored_products = conn.execute("SELECT COUNT(*) as count FROM products WHERE is_sponsored = 1 AND is_approved = 1").fetchone()["count"]
        
        # Order statistics
        total_orders = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()["count"]
        pending_orders = conn.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'pending'").fetchone()["count"]
        completed_orders = conn.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'delivered'").fetchone()["count"]
        total_revenue = conn.execute("SELECT SUM(total_amount) as total FROM orders WHERE status = 'delivered'").fetchone()["total"] or 0
        
        # Get all users with details
        all_users = conn.execute("SELECT id, email, name, role, is_approved, phone, address, created_at, last_login FROM users ORDER BY created_at DESC").fetchall()
        
        # Get all vendors with details
        all_vendors = conn.execute("SELECT id, email, name, role, is_approved, phone, address, created_at FROM users WHERE role = 'vendor' ORDER BY created_at DESC").fetchall()
        
        # Get pending vendors
        pending_vendors_list = conn.execute("SELECT id, email, name, phone, address, created_at FROM users WHERE role = 'vendor' AND is_approved = 0 ORDER BY created_at DESC").fetchall()
        
        # Get pending products with vendor names
        pending_products_list = conn.execute("""SELECT p.*, u.name as vendor_name, u.email as vendor_email 
                                               FROM products p JOIN users u ON p.store_id = u.id 
                                               WHERE p.is_approved = 0 ORDER BY p.created_at DESC""").fetchall()
        
        # Get recent analyses
        recent_analyses = conn.execute("""SELECT a.*, u.name as user_name, u.email as user_email 
                                         FROM analyses a JOIN users u ON a.user_id = u.id 
                                         ORDER BY a.created_at DESC LIMIT 20""").fetchall()
        
        return {
            "success": True,
            "stats": {
                "users": {"total": total_users, "customers": total_customers, "vendors": total_vendors, "pending_vendors": pending_vendors},
                "products": {"total": total_products, "pending": pending_products, "sponsored": sponsored_products},
                "orders": {"total": total_orders, "pending": pending_orders, "completed": completed_orders, "revenue": total_revenue}
            },
            "all_users": [dict(u) for u in all_users],
            "all_vendors": [dict(v) for v in all_vendors],
            "pending_vendors": [dict(v) for v in pending_vendors_list],
            "pending_products": [dict(p) for p in pending_products_list],
            "recent_analyses": [dict(a) for a in recent_analyses]
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
        
        # Get user details
        user = conn.execute("SELECT id, email, name, role, is_approved, phone, address, created_at, last_login FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if not user:
            return JSONResponse(status_code=404, content={"success": False, "message": "User not found"})
        
        # Get user's analyses
        analyses = conn.execute("SELECT id, skin_type, skin_name, confidence, created_at FROM analyses WHERE user_id = ? ORDER BY created_at DESC", (target_user_id,)).fetchall()
        
        # Get user's orders
        orders = conn.execute("SELECT id, status, total_amount, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC", (target_user_id,)).fetchall()
        
        return {
            "success": True,
            "user": dict(user),
            "analyses": [dict(a) for a in analyses],
            "orders": [dict(o) for o in orders]
        }

@app.get("/admin/vendors")
async def admin_get_vendors(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        
        vendors = conn.execute("SELECT id, email, name, is_approved, phone, address, created_at FROM users WHERE role = 'vendor' ORDER BY created_at DESC").fetchall()
        
        # Get product count for each vendor
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
