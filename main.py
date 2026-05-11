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
from typing import Dict, Optional
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
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    with get_db() as conn:
        # ============================================
        # USERS TABLE - WITH TIMESTAMPS AND APPROVAL
        # ============================================
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
        
        # Add missing columns if table already exists
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
        
        # ============================================
        # ANALYSES TABLE - FOR HISTORY
        # ============================================
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
        
        # ============================================
        # STORES TABLE
        # ============================================
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
        
        # ============================================
        # PRODUCTS TABLE
        # ============================================
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
        
        # ============================================
        # SPONSORED PRODUCTS TABLE
        # ============================================
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
        
        # ============================================
        # VENDOR_SUBSCRIPTIONS TABLE
        # ============================================
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
        
        # ============================================
        # ORDERS TABLE
        # ============================================
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
        
        # ============================================
        # ORDER ITEMS TABLE
        # ============================================
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
        
        # Create indexes for faster queries
        conn.execute('CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_products_store_id ON products(store_id)')
        
        # ============================================
        # CREATE DEFAULT ADMIN USER
        # ============================================
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
app = FastAPI(
    title="SkinGlow AI API",
    description="Professional Skin Analysis with Weather & UV Protection",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id") or payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token: no user identifier")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
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

class LoginRequest(BaseModel):
    email: str
    password: str

# ============================================
# TRY TO LOAD MEDIAPIPE (Optional)
# ============================================
MEDIAPIPE_AVAILABLE = False

try:
    import mediapipe as mp
    import cv2
    import numpy as np
    
    os.environ['GLOG_minloglevel'] = '2'
    
    mp_face_detection = mp.solutions.face_detection
    face_detection = mp_face_detection.FaceDetection(
        model_selection=1,
        min_detection_confidence=0.5
    )
    MEDIAPIPE_AVAILABLE = True
    print("✅ MediaPipe loaded successfully!")
except ImportError:
    print("⚠️ MediaPipe not available. Using fallback mode.")
except Exception as e:
    print(f"⚠️ MediaPipe error: {e}")

# ============================================
# WEATHER API CONFIGURATION (One Call 3.0)
# ============================================
WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')
WEATHER_API_URL = "https://api.openweathermap.org/data/2.5"

# ============================================
# REVERSE GEOCODING (Get City Name)
# ============================================

async def get_city_from_coordinates(lat: float, lon: float) -> str:
    """Get city name from coordinates using OpenStreetMap Nominatim"""
    try:
        geocode_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        response = requests.get(geocode_url, headers={'User-Agent': 'SkinGlowApp/1.0'}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            city = data.get('address', {}).get('city') or data.get('address', {}).get('town') or 'Unknown'
            return city
        return 'Unknown'
    except Exception:
        return 'Unknown'

# ============================================
# WEATHER DATA (One Call API 3.0)
# ============================================

def get_weather_data(lat: float, lon: float) -> Dict:
    """Get weather and UV data from OpenWeatherMap One Call API 3.0"""
    if not WEATHER_API_KEY:
        return {"success": False, "error": "Weather API key not configured", "uv_index": 5, "temperature": 25, "city": "Unknown"}
    
    try:
        onecall_url = "https://api.openweathermap.org/data/3.0/onecall"
        params = {'lat': lat, 'lon': lon, 'appid': WEATHER_API_KEY, 'units': 'metric'}
        response = requests.get(onecall_url, params=params, timeout=10)
        data = response.json()
        
        if response.status_code != 200:
            print(f"One Call API Error: {data.get('message', 'Unknown error')}")
            return get_weather_data_fallback(lat, lon)
        
        current = data.get('current', {})
        uv_index = current.get('uvi', 5)
        temperature = current.get('temp', 25)
        humidity = current.get('humidity', 60)
        weather_condition = current.get('weather', [{}])[0].get('description', 'clear')
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        city_name = loop.run_until_complete(get_city_from_coordinates(lat, lon))
        
        return {"success": True, "temperature": temperature, "humidity": humidity, "condition": weather_condition, "uv_index": uv_index, "city": city_name}
    except Exception as e:
        print(f"One Call API error: {e}")
        return get_weather_data_fallback(lat, lon)

def get_weather_data_fallback(lat: float, lon: float) -> Dict:
    """Fallback to old Current Weather API"""
    try:
        weather_url = f"{WEATHER_API_URL}/weather"
        weather_params = {'lat': lat, 'lon': lon, 'appid': WEATHER_API_KEY, 'units': 'metric'}
        weather_response = requests.get(weather_url, params=weather_params, timeout=10)
        weather_data = weather_response.json()
        current_hour = datetime.now().hour
        uv_index = 5 if 6 <= current_hour <= 18 else 0
        return {
            "success": True,
            "temperature": weather_data.get('main', {}).get('temp', 25),
            "humidity": weather_data.get('main', {}).get('humidity', 60),
            "condition": weather_data.get('weather', [{}])[0].get('description', 'clear'),
            "uv_index": uv_index,
            "city": weather_data.get('name', 'Unknown')
        }
    except Exception as e:
        return {"success": False, "error": str(e), "uv_index": 5, "temperature": 25, "city": "Unknown"}

def get_sunscreen_recommendation(uv_index: float, skin_type: str) -> Dict:
    """Get sunscreen recommendation based on UV index and skin type"""
    if uv_index <= 2:
        uv_level, base_spf, advice = "Low", 15, "Minimal UV risk. Daily protection still recommended."
    elif uv_index <= 5:
        uv_level, base_spf, advice = "Moderate", 30, "Moderate UV. Sunscreen required for outdoor activities."
    elif uv_index <= 7:
        uv_level, base_spf, advice = "High", 50, "High UV. Strong protection needed."
    elif uv_index <= 10:
        uv_level, base_spf, advice = "Very High", 50, "Very high UV. Maximum protection required."
    else:
        uv_level, base_spf, advice = "Extreme", 50, "EXTREME UV! Avoid sun exposure if possible."
    
    skin_advice = {
        'dry': "Use hydrating sunscreen with moisturizing ingredients",
        'oily': "Use oil-free, non-comedogenic sunscreen",
        'combination': "Use lightweight, balancing sunscreen",
        'sensitive': "Use mineral sunscreen with zinc oxide",
        'normal': "Use broad-spectrum sunscreen"
    }
    
    return {
        "uv_index": uv_index, "uv_level": uv_level, "advice": advice,
        "recommended_spf": base_spf, "reapplication_hours": 2 if uv_index > 5 else 4,
        "skin_advice": skin_advice.get(skin_type, skin_advice['normal']),
        "tips": ["Apply sunscreen 15-20 minutes before sun exposure", f"Reapply every {2 if uv_index > 5 else 4} hours", "Use 1/2 teaspoon for face and neck", "Don't forget ears, lips, and back of hands"]
    }

# ============================================
# SKIN CARE DATABASE
# ============================================
SKIN_CARE_DATA: Dict = {
    "dry": {"name": "Dry Skin", "characteristics": ["Lacks moisture", "May feel tight or flaky", "Fine lines may be visible"], "recommendations": ["🌊 Use hydrating cleanser with ceramides", "💧 Apply hyaluronic acid serum twice daily", "🧴 Use rich moisturizer with shea butter", "🌙 Add facial oil (argan or rosehip) to night routine", "💨 Use humidifier in dry environments"], "oils": ["Argan Oil", "Rosehip Oil", "Jojoba Oil", "Avocado Oil"], "products": [{"name": "CeraVe Hydrating Cleanser", "price": "$12.99", "rating": 4.7}, {"name": "The Ordinary Hyaluronic Acid 2%", "price": "$7.90", "rating": 4.5}]},
    "oily": {"name": "Oily Skin", "characteristics": ["Excess sebum production", "Shiny appearance", "Enlarged pores"], "recommendations": ["🧼 Use gentle foaming cleanser with salicylic acid", "✨ Apply niacinamide serum to control sebum", "💧 Use lightweight gel moisturizer", "🔬 Exfoliate 2-3 times weekly with BHA", "🌿 Use clay mask once weekly"], "oils": ["Grapeseed Oil", "Tea Tree Oil", "Hemp Seed Oil", "Rosehip Oil"], "products": [{"name": "La Roche-Posay Effaclar Gel", "price": "$14.99", "rating": 4.6}, {"name": "The Ordinary Niacinamide 10%", "price": "$5.90", "rating": 4.8}]},
    "combination": {"name": "Combination Skin", "characteristics": ["Oily in T-zone", "Normal or dry on cheeks"], "recommendations": ["⚖️ Use balancing cleanser with tea tree oil", "💧 Apply lightweight moisturizer everywhere", "🧴 Use richer cream on dry areas only", "🔬 Exfoliate T-zone twice weekly"], "oils": ["Jojoba Oil", "Squalane Oil", "Marula Oil", "Neroli Oil"], "products": [{"name": "COSRX Low pH Cleanser", "price": "$14.00", "rating": 4.7}, {"name": "Purito Centella Serum", "price": "$18.00", "rating": 4.6}]},
    "sensitive": {"name": "Sensitive Skin", "characteristics": ["Easily irritated", "Prone to redness"], "recommendations": ["🌸 Use fragrance-free, gentle cleanser", "🌿 Apply calming ingredients like centella asiatica", "💧 Use minimal ingredient moisturizer", "⚠️ Avoid active ingredients (retinols, acids)"], "oils": ["Chamomile Oil", "Calendula Oil", "Evening Primrose Oil", "Rose Oil"], "products": [{"name": "Avene Tolerance Cleanser", "price": "$22.00", "rating": 4.8}, {"name": "La Roche-Posay Cicaplast Baume", "price": "$15.99", "rating": 4.9}]},
    "normal": {"name": "Normal Skin", "characteristics": ["Balanced moisture", "Neither too oily nor too dry"], "recommendations": ["✨ Maintain consistent cleansing routine", "🍊 Use antioxidant serum (Vitamin C)", "☀️ Apply moisturizer with SPF daily", "🔬 Exfoliate weekly for maintenance"], "oils": ["Argan Oil", "Jojoba Oil", "Rosehip Oil", "Marula Oil"], "products": [{"name": "Krave Beauty Matcha Cleanser", "price": "$16.00", "rating": 4.7}, {"name": "Timeless Vitamin C Serum", "price": "$21.95", "rating": 4.8}]}
}

# ============================================
# HELPER FUNCTIONS
# ============================================

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
            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            x = int(bbox.xmin * w)
            y = int(bbox.ymin * h)
            width = int(bbox.width * w)
            height = int(bbox.height * h)
            face_region = image_rgb[y:y+height, x:x+width]
            if face_region.size > 0:
                gray_face = cv2.cvtColor(face_region, cv2.COLOR_RGB2GRAY)
                avg_brightness = np.mean(gray_face)
                texture_var = np.var(gray_face)
                if texture_var > 3000:
                    skin_type = "oily"
                elif texture_var < 1500:
                    skin_type = "dry"
                elif avg_brightness > 180:
                    skin_type = "sensitive"
                else:
                    skin_type = "normal"
                return {"skin_type": skin_type, "confidence": 0.85, "method": "MediaPipe AI"}
        return None
    except Exception as e:
        print(f"MediaPipe analysis error: {e}")
        return None

def analyze_with_fallback(image_bytes: bytes) -> Dict:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        pixels = list(image.getdata())
        sample_size = min(1000, len(pixels))
        step = len(pixels) // sample_size if sample_size > 0 else 1
        sample = [pixels[i] for i in range(0, len(pixels), step)][:sample_size]
        if sample:
            avg_r = sum(p[0] for p in sample) / len(sample)
            avg_g = sum(p[1] for p in sample) / len(sample)
            avg_b = sum(p[2] for p in sample) / len(sample)
            brightness = (avg_r + avg_g + avg_b) / 3
        else:
            brightness = 128
        if brightness > 200:
            skin_type = "dry"
        elif brightness < 80:
            skin_type = "oily"
        elif brightness > 150:
            skin_type = "sensitive"
        elif 100 < brightness < 150:
            skin_type = "combination"
        else:
            skin_type = "normal"
        return {"skin_type": skin_type, "confidence": 0.70, "method": "Color Analysis"}
    except Exception as e:
        return {"skin_type": "normal", "confidence": 0.50, "method": "Default"}

# ============================================
# BASIC API ENDPOINTS
# ============================================

@app.get("/")
async def root():
    return {"status": "healthy", "app": "SkinGlow AI", "version": "3.0.0", "mediapipe_available": MEDIAPIPE_AVAILABLE, "weather_api_configured": bool(WEATHER_API_KEY), "timestamp": datetime.now().isoformat()}

@app.get("/health")
async def health_check():
    return {"status": "operational", "mediapipe": MEDIAPIPE_AVAILABLE, "weather_api": bool(WEATHER_API_KEY), "skin_types": list(SKIN_CARE_DATA.keys()), "timestamp": datetime.now().isoformat()}

@app.get("/skin-types")
async def get_skin_types():
    return {"skin_types": [{"id": skin_id, "name": data["name"]} for skin_id, data in SKIN_CARE_DATA.items()]}

@app.get("/location/{lat}/{lon}")
async def get_location_name(lat: float, lon: float):
    city_name = "Unknown"
    try:
        geocode_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        response = requests.get(geocode_url, headers={'User-Agent': 'SkinGlowApp/1.0'}, timeout=5)
        if response.status_code == 200:
            data = response.json()
            city_name = data.get('address', {}).get('city') or data.get('address', {}).get('town') or 'Unknown'
    except:
        pass
    return {"success": True, "city": city_name, "latitude": lat, "longitude": lon, "timestamp": datetime.now().isoformat()}

@app.get("/sunscreen/{uv_index}")
async def get_sunscreen(uv_index: float, skin_type: str = "normal"):
    result = get_sunscreen_recommendation(uv_index, skin_type)
    return {"success": True, **result, "timestamp": datetime.now().isoformat()}

@app.get("/weather/{lat}/{lon}")
async def get_weather(lat: float, lon: float, skin_type: str = "normal", user_id: str = Depends(verify_token)):
    weather = get_weather_data(lat, lon)
    if not weather.get("success"):
        return {"success": False, "error": weather.get("error", "Weather service unavailable"), "timestamp": datetime.now().isoformat()}
    uv_index = weather.get("uv_index", 5)
    sunscreen = get_sunscreen_recommendation(uv_index, skin_type)
    return {"success": True, "weather": {"temperature": weather.get("temperature"), "humidity": weather.get("humidity"), "condition": weather.get("condition"), "uv_index": uv_index, "city": weather.get("city")}, "sunscreen": sunscreen, "timestamp": datetime.now().isoformat()}

# ============================================
# AUTH ENDPOINTS
# ============================================

@app.post("/auth/register")
async def register(request: RegisterRequest):
    try:
        email, password, name = request.email, request.password, request.name
        phone, address = request.phone, request.address
        
        with get_db() as conn:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                return JSONResponse(status_code=400, content={"success": False, "message": "Email already registered"})
            
            user_id = str(uuid.uuid4())
            password_hash = hash_password(password)
            conn.execute("INSERT INTO users (id, email, password_hash, name, phone, address, is_approved, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)", (user_id, email, password_hash, name, phone, address))
            conn.commit()
        
        token_data = {"sub": email, "user_id": user_id, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        
        return {"success": True, "message": "User registered successfully. Awaiting admin approval.", "token": token, "token_type": "bearer", "user": {"id": user_id, "email": email, "name": name, "role": "customer", "is_approved": 0, "member_since": datetime.now().isoformat()}}
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
                return JSONResponse(status_code=403, content={"success": False, "message": "Your account is pending admin approval"})
            
            user_id, user_email, user_name, user_role, is_approved, member_since, phone, address = user["id"], user["email"], user["name"], user["role"], user["is_approved"], user["created_at"], user["phone"], user["address"]
            conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
            conn.commit()
        
        token_data = {"sub": user_email, "user_id": user_id, "role": user_role, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        
        return {"success": True, "message": "Login successful", "token": token, "token_type": "bearer", "user": {"id": user_id, "email": user_email, "name": user_name, "role": user_role, "is_approved": is_approved, "member_since": member_since, "phone": phone, "address": address}}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.get("/users/me")
async def get_current_user(user_id: str = Depends(verify_token)):
    try:
        with get_db() as conn:
            user = conn.execute("SELECT id, email, name, role, is_approved, created_at, last_login, phone, address FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                return JSONResponse(status_code=404, content={"success": False, "message": "User not found"})
            return {"success": True, "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"], "is_approved": user["is_approved"], "member_since": user["created_at"], "last_login": user["last_login"], "phone": user["phone"], "address": user["address"]}}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

# ============================================
# SKIN ANALYSIS ENDPOINT
# ============================================

@app.post("/analyze")
async def analyze_skin(file: UploadFile = File(...), user_id: str = Depends(verify_token)):
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    try:
        contents = await file.read()
        analysis = analyze_with_mediapipe(contents)
        if not analysis:
            analysis = analyze_with_fallback(contents)
        skin_type, confidence, method = analysis.get("skin_type", "normal"), analysis.get("confidence", 0.75), analysis.get("method", "AI Analysis")
        skin_data = SKIN_CARE_DATA.get(skin_type, SKIN_CARE_DATA["normal"])
        analysis_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute("INSERT INTO analyses (id, user_id, skin_type, skin_name, confidence, characteristics, recommendations, recommended_oils, method) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (analysis_id, user_id, skin_type, skin_data["name"], confidence, "|".join(skin_data["characteristics"]), "|".join(skin_data["recommendations"]), "|".join(skin_data["oils"]), method))
            conn.commit()
        return {"success": True, "skin_type": skin_type, "skin_name": skin_data["name"], "confidence": round(confidence, 2), "characteristics": skin_data["characteristics"], "recommendations": skin_data["recommendations"], "recommended_oils": skin_data["oils"], "products": skin_data["products"], "method": method, "analysis_id": analysis_id, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# ============================================
# ANALYSIS HISTORY ENDPOINTS
# ============================================

@app.get("/analyses/history")
async def get_analysis_history(user_id: str = Depends(verify_token)):
    try:
        with get_db() as conn:
            analyses = conn.execute("SELECT id, skin_type, skin_name, confidence, recommendations, recommended_oils, method, created_at FROM analyses WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (user_id,)).fetchall()
            return {"success": True, "analyses": [{"id": a["id"], "skin_type": a["skin_type"], "skin_name": a["skin_name"], "confidence": a["confidence"], "recommendations": a["recommendations"].split("|") if a["recommendations"] else [], "recommended_oils": a["recommended_oils"].split("|") if a["recommended_oils"] else [], "method": a["method"], "created_at": a["created_at"]} for a in analyses]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.get("/users/stats")
async def get_user_stats(user_id: str = Depends(verify_token)):
    try:
        with get_db() as conn:
            analyses = conn.execute("SELECT skin_type, confidence, created_at FROM analyses WHERE user_id = ?", (user_id,)).fetchall()
            if not analyses:
                return {"success": True, "total_analyses": 0, "active_days": 0, "skin_health_score": 85, "avg_confidence": 0, "skin_type_trends": {}}
            skin_type_counts, active_days, total_confidence = {}, set(), 0
            for a in analyses:
                skin_type_counts[a["skin_type"]] = skin_type_counts.get(a["skin_type"], 0) + 1
                active_days.add(a["created_at"][:10])
                total_confidence += a["confidence"]
            total_analyses, avg_confidence = len(analyses), total_confidence / len(analyses)
            latest = analyses[0]
            skin_type_scores = {"normal": 92, "combination": 82, "dry": 78, "oily": 75, "sensitive": 70}
            base_score = skin_type_scores.get(latest["skin_type"], 85)
            skin_health_score = int(base_score * (latest["confidence"] * 0.3 + 0.7))
            return {"success": True, "total_analyses": total_analyses, "active_days": len(active_days), "skin_health_score": skin_health_score, "avg_confidence": round(avg_confidence, 2), "skin_type_trends": skin_type_counts}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

# ============================================
# OPENAI CHAT ENDPOINT
# ============================================

import openai

@app.post("/chat")
async def chat(request: dict, user_id: str = Depends(verify_token)):
    user_message = request.get('message', '')
    if not user_message:
        return {"success": False, "response": "Tafadhali uliza swali kuhusu ngozi yako."}
    openai.api_key = os.getenv('OPENAI_API_KEY', '')
    if not openai.api_key:
        return {"success": False, "response": "AI chat is not configured yet. Please try again later."}
    try:
        system_prompt = "You are 'SkinSight AI', a professional African skincare advisor. Give short, practical advice (under 150 words). Be friendly and warm. Always encourage sunscreen use (SPF 30+). Never give medical diagnoses."
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}], max_tokens=300, temperature=0.7)
        return {"success": True, "response": response.choices[0].message.content, "model": "gpt-3.5-turbo"}
    except Exception as e:
        print(f"OpenAI error: {str(e)}")
        return {"success": False, "response": "Samahani, nahitaji muda kidogo. Tafadhali jaribu tena."}

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
        products = conn.execute("SELECT id, name, description, price, category, skin_type, stock, is_approved, is_sponsored, views, created_at FROM products WHERE store_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        return {"success": True, "products": [dict(p) for p in products]}

@app.post("/vendor/sponsor")
async def sponsor_product(request: dict, user_id: str = Depends(verify_token)):
    product_id, amount, days = request.get('product_id'), request.get('amount', 0), request.get('days', 7)
    with get_db() as conn:
        product = conn.execute("SELECT id, is_approved FROM products WHERE id = ? AND store_id = ?", (product_id, user_id)).fetchone()
        if not product:
            return JSONResponse(status_code=404, content={"success": False, "message": "Product not found"})
        if product["is_approved"] == 0:
            return JSONResponse(status_code=400, content={"success": False, "message": "Product must be approved first"})
        sponsored_id, end_date = str(uuid.uuid4()), datetime.now() + timedelta(days=days)
        conn.execute("INSERT INTO sponsored_products (id, product_id, vendor_id, amount_paid, end_date) VALUES (?, ?, ?, ?, ?)", (sponsored_id, product_id, user_id, amount, end_date))
        conn.execute("UPDATE products SET is_sponsored = 1 WHERE id = ?", (product_id,))
        conn.commit()
    return {"success": True, "message": f"Product sponsored for {days} days", "end_date": end_date.isoformat()}

@app.get("/vendor/stats")
async def vendor_stats(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        products = conn.execute("SELECT COUNT(*) as total FROM products WHERE store_id = ?", (user_id,)).fetchone()
        sales = conn.execute("SELECT SUM(oi.quantity * oi.price) as revenue, COUNT(DISTINCT o.id) as orders FROM orders o JOIN order_items oi ON o.id = oi.order_id JOIN products p ON oi.product_id = p.id WHERE p.store_id = ? AND o.status = 'delivered'", (user_id,)).fetchone()
        views = conn.execute("SELECT SUM(views) as total_views FROM products WHERE store_id = ?", (user_id,)).fetchone()
        return {"success": True, "total_products": products["total"] if products else 0, "total_revenue": sales["revenue"] if sales and sales["revenue"] else 0, "total_orders": sales["orders"] if sales else 0, "total_views": views["total_views"] if views else 0}

# ============================================
# SUPER ADMIN ENDPOINTS
# ============================================

@app.get("/admin/stats")
async def admin_stats(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        
        total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
        total_vendors = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'vendor'").fetchone()
        pending_vendors = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'vendor' AND is_approved = 0").fetchone()
        total_products = conn.execute("SELECT COUNT(*) as count FROM products").fetchone()
        pending_products = conn.execute("SELECT COUNT(*) as count FROM products WHERE is_approved = 0").fetchone()
        total_orders = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()
        total_revenue = conn.execute("SELECT SUM(total_amount) as total FROM orders WHERE status = 'delivered'").fetchone()
        
        recent_users = conn.execute("SELECT id, email, name, role, is_approved, created_at FROM users ORDER BY created_at DESC LIMIT 10").fetchall()
        pending_products_list = conn.execute("SELECT p.*, u.name as vendor_name FROM products p JOIN users u ON p.store_id = u.id WHERE p.is_approved = 0 ORDER BY p.created_at DESC").fetchall()
        pending_vendors_list = conn.execute("SELECT id, email, name, phone, address, created_at FROM users WHERE role = 'vendor' AND is_approved = 0 ORDER BY created_at DESC").fetchall()
        
        return {"success": True, "stats": {"total_users": total_users["count"] if total_users else 0, "total_vendors": total_vendors["count"] if total_vendors else 0, "pending_vendors": pending_vendors["count"] if pending_vendors else 0, "total_products": total_products["count"] if total_products else 0, "pending_products": pending_products["count"] if pending_products else 0, "total_orders": total_orders["count"] if total_orders else 0, "total_revenue": total_revenue["total"] if total_revenue and total_revenue["total"] else 0}, "recent_users": [dict(u) for u in recent_users], "pending_products": [dict(p) for p in pending_products_list], "pending_vendors": [dict(v) for v in pending_vendors_list]}

@app.post("/admin/approve-product/{product_id}")
async def approve_product(product_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("UPDATE products SET is_approved = 1 WHERE id = ?", (product_id,))
        conn.commit()
    return {"success": True, "message": "Product approved successfully"}

@app.post("/admin/reject-product/{product_id}")
async def reject_product(product_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
    return {"success": True, "message": "Product rejected and deleted"}

@app.post("/admin/approve-vendor/{vendor_id}")
async def approve_vendor(vendor_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("UPDATE users SET is_approved = 1 WHERE id = ?", (vendor_id,))
        conn.commit()
    return {"success": True, "message": "Vendor approved successfully"}

@app.post("/admin/reject-vendor/{vendor_id}")
async def reject_vendor(vendor_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("DELETE FROM users WHERE id = ?", (vendor_id,))
        conn.commit()
    return {"success": True, "message": "Vendor application rejected"}

@app.post("/admin/delete-user/{target_user_id}")
async def admin_delete_user(target_user_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("DELETE FROM users WHERE id = ?", (target_user_id,))
        conn.commit()
    return {"success": True, "message": "User deleted successfully"}

@app.post("/admin/set-vendor-role/{target_user_id}")
async def set_vendor_role(target_user_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user or user["role"] != "admin":
            return JSONResponse(status_code=403, content={"success": False, "message": "Admin access required"})
        conn.execute("UPDATE users SET role = 'vendor' WHERE id = ?", (target_user_id,))
        conn.commit()
    return {"success": True, "message": "User role updated to vendor"}

# ============================================
# CUSTOMER PRODUCTS ENDPOINT
# ============================================

@app.get("/products/customer")
async def get_customer_products(skin_type: str = None, category: str = None, sort_by: str = "sponsored", user_id: str = Depends(verify_token)):
    try:
        with get_db() as conn:
            query = "SELECT p.*, u.name as vendor_name FROM products p JOIN users u ON p.store_id = u.id WHERE p.is_approved = 1"
            params = []
            if skin_type and skin_type != "all":
                query += " AND p.skin_type = ?"
                params.append(skin_type)
            if category and category != "all":
                query += " AND p.category = ?"
                params.append(category)
            if sort_by == "sponsored":
                query += " ORDER BY p.is_sponsored DESC, p.views DESC, p.created_at DESC"
            elif sort_by == "popular":
                query += " ORDER BY p.views DESC, p.created_at DESC"
            elif sort_by == "newest":
                query += " ORDER BY p.created_at DESC"
            elif sort_by == "price_low":
                query += " ORDER BY p.price ASC"
            elif sort_by == "price_high":
                query += " ORDER BY p.price DESC"
            else:
                query += " ORDER BY p.is_sponsored DESC, p.created_at DESC"
            
            products = conn.execute(query, params).fetchall()
            for product in products:
                conn.execute("UPDATE products SET views = views + 1 WHERE id = ?", (product["id"],))
            conn.commit()
        return {"success": True, "products": [dict(p) for p in products]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.get("/products/categories")
async def get_product_categories():
    return {"success": True, "categories": [{"id": "cleanser", "name": "Cleanser", "icon": "🧼"}, {"id": "moisturizer", "name": "Moisturizer", "icon": "💧"}, {"id": "sunscreen", "name": "Sunscreen / SPF", "icon": "☀️"}, {"id": "serum", "name": "Serum", "icon": "✨"}, {"id": "oil", "name": "Face Oil", "icon": "🌿"}, {"id": "mask", "name": "Face Mask", "icon": "🎭"}, {"id": "toner", "name": "Toner", "icon": "💦"}]}

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
    print(f"✅ One Call API 3.0: {'Enabled' if WEATHER_API_KEY else 'Disabled'}")
    print(f"✅ Skin types: {len(SKIN_CARE_DATA)}")
    print(f"✅ Database: SQLite with full vendor/admin tables")
    print("=" * 60)
    print(f"🚀 Server starting on port {port}...")
    print(f"📚 API Docs: https://skinglow-backend.up.railway.app/docs")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
