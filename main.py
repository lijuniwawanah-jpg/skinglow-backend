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
        # USERS TABLE - WITH TIMESTAMPS
        # ============================================
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                role TEXT DEFAULT 'customer',
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (store_id) REFERENCES stores(id)
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
            city = data.get('address', {}).get('city') or \
                   data.get('address', {}).get('town') or \
                   data.get('address', {}).get('village') or \
                   'Unknown'
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
        return {
            "success": False,
            "error": "Weather API key not configured",
            "uv_index": 5,
            "temperature": 25,
            "city": "Unknown"
        }
    
    try:
        # ============================================
        # USE ONE CALL API 3.0 (After subscription)
        # ============================================
        onecall_url = "https://api.openweathermap.org/data/3.0/onecall"
        params = {
            'lat': lat,
            'lon': lon,
            'appid': WEATHER_API_KEY,
            'units': 'metric'
        }
        
        response = requests.get(onecall_url, params=params, timeout=10)
        data = response.json()
        
        if response.status_code != 200:
            print(f"One Call API Error: {data.get('message', 'Unknown error')}")
            return get_weather_data_fallback(lat, lon)
        
        current = data.get('current', {})
        
        # Get UV Index from One Call API
        uv_index = current.get('uvi', 5)
        temperature = current.get('temp', 25)
        humidity = current.get('humidity', 60)
        weather_condition = current.get('weather', [{}])[0].get('description', 'clear')
        
        # Get city name - run async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        city_name = loop.run_until_complete(get_city_from_coordinates(lat, lon))
        
        print(f"🌤️ One Call API - UV: {uv_index}, Temp: {temperature}°C, City: {city_name}")
        
        return {
            "success": True,
            "temperature": temperature,
            "humidity": humidity,
            "condition": weather_condition,
            "uv_index": uv_index,
            "city": city_name
        }
        
    except Exception as e:
        print(f"One Call API error: {e}")
        return get_weather_data_fallback(lat, lon)

def get_weather_data_fallback(lat: float, lon: float) -> Dict:
    """Fallback to old Current Weather API if One Call fails"""
    try:
        weather_url = f"{WEATHER_API_URL}/weather"
        weather_params = {
            'lat': lat,
            'lon': lon,
            'appid': WEATHER_API_KEY,
            'units': 'metric'
        }
        weather_response = requests.get(weather_url, params=weather_params, timeout=10)
        weather_data = weather_response.json()
        
        # Estimate UV based on time (old API doesn't have UV)
        current_hour = datetime.now().hour
        if 6 <= current_hour <= 18:
            uv_index = 5
        else:
            uv_index = 0
        
        return {
            "success": True,
            "temperature": weather_data.get('main', {}).get('temp', 25),
            "humidity": weather_data.get('main', {}).get('humidity', 60),
            "condition": weather_data.get('weather', [{}])[0].get('description', 'clear'),
            "uv_index": uv_index,
            "city": weather_data.get('name', 'Unknown')
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "uv_index": 5,
            "temperature": 25,
            "city": "Unknown"
        }

def get_sunscreen_recommendation(uv_index: float, skin_type: str) -> Dict:
    """Get sunscreen recommendation based on UV index and skin type"""
    
    if uv_index <= 2:
        uv_level = "Low"
        base_spf = 15
        advice = "Minimal UV risk. Daily protection still recommended."
    elif uv_index <= 5:
        uv_level = "Moderate"
        base_spf = 30
        advice = "Moderate UV. Sunscreen required for outdoor activities."
    elif uv_index <= 7:
        uv_level = "High"
        base_spf = 50
        advice = "High UV. Strong protection needed."
    elif uv_index <= 10:
        uv_level = "Very High"
        base_spf = 50
        advice = "Very high UV. Maximum protection required."
    else:
        uv_level = "Extreme"
        base_spf = 50
        advice = "EXTREME UV! Avoid sun exposure if possible."
    
    skin_advice = {
        'dry': "Use hydrating sunscreen with moisturizing ingredients",
        'oily': "Use oil-free, non-comedogenic sunscreen",
        'combination': "Use lightweight, balancing sunscreen",
        'sensitive': "Use mineral sunscreen with zinc oxide",
        'normal': "Use broad-spectrum sunscreen"
    }
    
    return {
        "uv_index": uv_index,
        "uv_level": uv_level,
        "advice": advice,
        "recommended_spf": base_spf,
        "reapplication_hours": 2 if uv_index > 5 else 4,
        "skin_advice": skin_advice.get(skin_type, skin_advice['normal']),
        "tips": [
            "Apply sunscreen 15-20 minutes before sun exposure",
            f"Reapply every {2 if uv_index > 5 else 4} hours",
            "Use 1/2 teaspoon for face and neck",
            "Don't forget ears, lips, and back of hands"
        ]
    }

# ============================================
# SKIN CARE DATABASE
# ============================================
SKIN_CARE_DATA: Dict = {
    "dry": {
        "name": "Dry Skin",
        "characteristics": [
            "Lacks moisture",
            "May feel tight or flaky",
            "Fine lines may be visible"
        ],
        "recommendations": [
            "🌊 Use hydrating cleanser with ceramides",
            "💧 Apply hyaluronic acid serum twice daily",
            "🧴 Use rich moisturizer with shea butter",
            "🌙 Add facial oil (argan or rosehip) to night routine",
            "💨 Use humidifier in dry environments"
        ],
        "oils": ["Argan Oil", "Rosehip Oil", "Jojoba Oil", "Avocado Oil"],
        "products": [
            {"name": "CeraVe Hydrating Cleanser", "price": "$12.99", "rating": 4.7},
            {"name": "The Ordinary Hyaluronic Acid 2%", "price": "$7.90", "rating": 4.5}
        ]
    },
    "oily": {
        "name": "Oily Skin",
        "characteristics": [
            "Excess sebum production",
            "Shiny appearance",
            "Enlarged pores"
        ],
        "recommendations": [
            "🧼 Use gentle foaming cleanser with salicylic acid",
            "✨ Apply niacinamide serum to control sebum",
            "💧 Use lightweight gel moisturizer",
            "🔬 Exfoliate 2-3 times weekly with BHA",
            "🌿 Use clay mask once weekly"
        ],
        "oils": ["Grapeseed Oil", "Tea Tree Oil", "Hemp Seed Oil", "Rosehip Oil"],
        "products": [
            {"name": "La Roche-Posay Effaclar Gel", "price": "$14.99", "rating": 4.6},
            {"name": "The Ordinary Niacinamide 10%", "price": "$5.90", "rating": 4.8}
        ]
    },
    "combination": {
        "name": "Combination Skin",
        "characteristics": [
            "Oily in T-zone",
            "Normal or dry on cheeks"
        ],
        "recommendations": [
            "⚖️ Use balancing cleanser with tea tree oil",
            "💧 Apply lightweight moisturizer everywhere",
            "🧴 Use richer cream on dry areas only",
            "🔬 Exfoliate T-zone twice weekly"
        ],
        "oils": ["Jojoba Oil", "Squalane Oil", "Marula Oil", "Neroli Oil"],
        "products": [
            {"name": "COSRX Low pH Cleanser", "price": "$14.00", "rating": 4.7},
            {"name": "Purito Centella Serum", "price": "$18.00", "rating": 4.6}
        ]
    },
    "sensitive": {
        "name": "Sensitive Skin",
        "characteristics": [
            "Easily irritated",
            "Prone to redness"
        ],
        "recommendations": [
            "🌸 Use fragrance-free, gentle cleanser",
            "🌿 Apply calming ingredients like centella asiatica",
            "💧 Use minimal ingredient moisturizer",
            "⚠️ Avoid active ingredients (retinols, acids)"
        ],
        "oils": ["Chamomile Oil", "Calendula Oil", "Evening Primrose Oil", "Rose Oil"],
        "products": [
            {"name": "Avene Tolerance Cleanser", "price": "$22.00", "rating": 4.8},
            {"name": "La Roche-Posay Cicaplast Baume", "price": "$15.99", "rating": 4.9}
        ]
    },
    "normal": {
        "name": "Normal Skin",
        "characteristics": [
            "Balanced moisture",
            "Neither too oily nor too dry"
        ],
        "recommendations": [
            "✨ Maintain consistent cleansing routine",
            "🍊 Use antioxidant serum (Vitamin C)",
            "☀️ Apply moisturizer with SPF daily",
            "🔬 Exfoliate weekly for maintenance"
        ],
        "oils": ["Argan Oil", "Jojoba Oil", "Rosehip Oil", "Marula Oil"],
        "products": [
            {"name": "Krave Beauty Matcha Cleanser", "price": "$16.00", "rating": 4.7},
            {"name": "Timeless Vitamin C Serum", "price": "$21.95", "rating": 4.8}
        ]
    }
}

# ============================================
# HELPER FUNCTIONS
# ============================================

def analyze_with_mediapipe(image_bytes: bytes) -> Optional[Dict]:
    """Analyze skin using MediaPipe (if available)"""
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
                
                return {
                    "skin_type": skin_type,
                    "confidence": 0.85,
                    "method": "MediaPipe AI"
                }
        
        return None
    except Exception as e:
        print(f"MediaPipe analysis error: {e}")
        return None

def analyze_with_fallback(image_bytes: bytes) -> Dict:
    """Fallback analysis using basic image processing"""
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
        
        return {
            "skin_type": skin_type,
            "confidence": 0.70,
            "method": "Color Analysis"
        }
    except Exception as e:
        return {
            "skin_type": "normal",
            "confidence": 0.50,
            "method": "Default"
        }

# ============================================
# API ENDPOINTS
# ============================================

@app.get("/")
async def root():
    """API health check"""
    return {
        "status": "healthy",
        "app": "SkinGlow AI",
        "version": "3.0.0",
        "mediapipe_available": MEDIAPIPE_AVAILABLE,
        "weather_api_configured": bool(WEATHER_API_KEY),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "operational",
        "mediapipe": MEDIAPIPE_AVAILABLE,
        "weather_api": bool(WEATHER_API_KEY),
        "skin_types": list(SKIN_CARE_DATA.keys()),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/skin-types")
async def get_skin_types():
    """Get all available skin types"""
    return {
        "skin_types": [
            {"id": skin_id, "name": data["name"]}
            for skin_id, data in SKIN_CARE_DATA.items()
        ]
    }

@app.get("/location/{lat}/{lon}")
async def get_location_name(lat: float, lon: float):
    """Get location name from coordinates"""
    city_name = "Unknown"
    try:
        geocode_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        response = requests.get(geocode_url, headers={'User-Agent': 'SkinGlowApp/1.0'}, timeout=5)
        if response.status_code == 200:
            data = response.json()
            city_name = data.get('address', {}).get('city') or data.get('address', {}).get('town') or 'Unknown'
    except:
        pass
    
    return {
        "success": True,
        "city": city_name,
        "latitude": lat,
        "longitude": lon,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/sunscreen/{uv_index}")
async def get_sunscreen(uv_index: float, skin_type: str = "normal"):
    """Get sunscreen recommendation by UV index only"""
    result = get_sunscreen_recommendation(uv_index, skin_type)
    return {
        "success": True,
        **result,
        "timestamp": datetime.now().isoformat()
    }

# ============================================
# WEATHER ENDPOINTS (UPDATED with One Call API)
# ============================================

@app.get("/weather/{lat}/{lon}")
async def get_weather(
    lat: float,
    lon: float,
    skin_type: str = "normal",
    user_id: str = Depends(verify_token)
):
    """Get weather and sunscreen advice using One Call API 3.0"""
    
    weather = get_weather_data(lat, lon)
    
    if not weather.get("success"):
        return {
            "success": False,
            "error": weather.get("error", "Weather service unavailable"),
            "timestamp": datetime.now().isoformat()
        }
    
    uv_index = weather.get("uv_index", 5)
    sunscreen = get_sunscreen_recommendation(uv_index, skin_type)
    
    return {
        "success": True,
        "weather": {
            "temperature": weather.get("temperature"),
            "humidity": weather.get("humidity"),
            "condition": weather.get("condition"),
            "uv_index": uv_index,
            "city": weather.get("city")
        },
        "sunscreen": sunscreen,
        "timestamp": datetime.now().isoformat()
    }

# ============================================
# AUTH ENDPOINTS
# ============================================

@app.post("/auth/register")
async def register(request: RegisterRequest):
    """Register new user"""
    try:
        email = request.email
        password = request.password
        name = request.name
        
        with get_db() as conn:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "message": "Email already registered"}
                )
            
            user_id = str(uuid.uuid4())
            password_hash = hash_password(password)
            conn.execute(
                "INSERT INTO users (id, email, password_hash, name, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (user_id, email, password_hash, name)
            )
            conn.commit()
        
        token_data = {
            "sub": email,
            "user_id": user_id,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        }
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        
        return {
            "success": True,
            "message": "User registered successfully",
            "token": token,
            "token_type": "bearer",
            "user": {
                "id": user_id,
                "email": email,
                "name": name,
                "member_since": datetime.now().isoformat()
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

@app.post("/auth/login")
async def login(request: LoginRequest):
    """Login user with last_login update"""
    try:
        email = request.email
        password = request.password
        
        with get_db() as conn:
            user = conn.execute(
                "SELECT id, email, password_hash, name, role, created_at FROM users WHERE email = ?",
                (email,)
            ).fetchone()
            
            if not user or user["password_hash"] != hash_password(password):
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "message": "Invalid email or password"}
                )
            
            user_id = user["id"]
            user_email = user["email"]
            user_name = user["name"]
            user_role = user["role"] if user["role"] else "customer"
            member_since = user["created_at"]
            
            conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
            conn.commit()
        
        token_data = {
            "sub": user_email,
            "user_id": user_id,
            "role": user_role,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        }
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        
        return {
            "success": True,
            "message": "Login successful",
            "token": token,
            "token_type": "bearer",
            "user": {
                "id": user_id,
                "email": user_email,
                "name": user_name,
                "role": user_role,
                "member_since": member_since
            }
        }
    except Exception as e:
        print(f"Login error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

@app.get("/users/me")
async def get_current_user(user_id: str = Depends(verify_token)):
    """Get current user info"""
    try:
        with get_db() as conn:
            user = conn.execute(
                "SELECT id, email, name, role, created_at, last_login FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()
            
            if not user:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "message": "User not found"}
                )
            
            return {
                "success": True,
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "name": user["name"],
                    "role": user["role"],
                    "member_since": user["created_at"],
                    "last_login": user["last_login"]
                }
            }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ============================================
# SKIN ANALYSIS ENDPOINT
# ============================================

@app.post("/analyze")
async def analyze_skin(file: UploadFile = File(...), user_id: str = Depends(verify_token)):
    """Analyze skin and save to history"""
    
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    try:
        contents = await file.read()
        
        analysis = analyze_with_mediapipe(contents)
        if not analysis:
            analysis = analyze_with_fallback(contents)
        
        skin_type = analysis.get("skin_type", "normal")
        confidence = analysis.get("confidence", 0.75)
        method = analysis.get("method", "AI Analysis")
        
        skin_data = SKIN_CARE_DATA.get(skin_type, SKIN_CARE_DATA["normal"])
        
        analysis_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                """INSERT INTO analyses 
                   (id, user_id, skin_type, skin_name, confidence, characteristics, 
                    recommendations, recommended_oils, method) 
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
            "confidence": round(confidence, 2),
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

# ============================================
# ANALYSIS HISTORY ENDPOINTS
# ============================================

@app.get("/analyses/history")
async def get_analysis_history(user_id: str = Depends(verify_token)):
    """Get user's analysis history"""
    try:
        with get_db() as conn:
            analyses = conn.execute(
                """SELECT id, skin_type, skin_name, confidence, 
                          recommendations, recommended_oils, method, created_at 
                   FROM analyses 
                   WHERE user_id = ? 
                   ORDER BY created_at DESC 
                   LIMIT 50""",
                (user_id,)
            ).fetchall()
        
        return {
            "success": True,
            "analyses": [
                {
                    "id": a["id"],
                    "skin_type": a["skin_type"],
                    "skin_name": a["skin_name"],
                    "confidence": a["confidence"],
                    "recommendations": a["recommendations"].split("|") if a["recommendations"] else [],
                    "recommended_oils": a["recommended_oils"].split("|") if a["recommended_oils"] else [],
                    "method": a["method"],
                    "created_at": a["created_at"]
                }
                for a in analyses
            ]
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

@app.get("/users/stats")
async def get_user_stats(user_id: str = Depends(verify_token)):
    """Get user statistics including active days and skin health score"""
    try:
        with get_db() as conn:
            analyses = conn.execute(
                "SELECT skin_type, confidence, created_at FROM analyses WHERE user_id = ?",
                (user_id,)
            ).fetchall()
            
            if not analyses:
                return {
                    "success": True,
                    "total_analyses": 0,
                    "active_days": 0,
                    "skin_health_score": 85,
                    "avg_confidence": 0,
                    "skin_type_trends": {}
                }
            
            skin_type_counts = {}
            active_days = set()
            total_confidence = 0
            
            for a in analyses:
                skin_type = a["skin_type"]
                skin_type_counts[skin_type] = skin_type_counts.get(skin_type, 0) + 1
                active_days.add(a["created_at"][:10])
                total_confidence += a["confidence"]
            
            total_analyses = len(analyses)
            avg_confidence = total_confidence / total_analyses if total_analyses > 0 else 0
            
            latest = analyses[0]
            skin_type_scores = {
                "normal": 92,
                "combination": 82,
                "dry": 78,
                "oily": 75,
                "sensitive": 70
            }
            base_score = skin_type_scores.get(latest["skin_type"], 85)
            skin_health_score = int(base_score * (latest["confidence"] * 0.3 + 0.7))
            
            return {
                "success": True,
                "total_analyses": total_analyses,
                "active_days": len(active_days),
                "skin_health_score": skin_health_score,
                "avg_confidence": round(avg_confidence, 2),
                "skin_type_trends": skin_type_counts
            }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ============================================
# OPENAI CHAT ENDPOINT
# ============================================

import openai

@app.post("/chat")
async def chat(request: dict, user_id: str = Depends(verify_token)):
    """AI Chat Assistant using OpenAI GPT-3.5"""
    
    user_message = request.get('message', '')
    
    if not user_message:
        return {
            "success": False,
            "response": "Tafadhali uliza swali kuhusu ngozi yako."
        }
    
    openai.api_key = os.getenv('OPENAI_API_KEY', '')
    
    if not openai.api_key:
        print("⚠️ OPENAI_API_KEY not set in environment")
        return {
            "success": False,
            "response": "AI chat is not configured yet. Please try again later."
        }
    
    try:
        system_prompt = """You are 'SkinSight AI', a professional African skincare advisor.
        
RULES:
- Give short, practical advice (under 150 words)
- Be friendly and warm
- Always encourage sunscreen use (SPF 30+)
- Never give medical diagnoses

TOPICS YOU CAN HELP WITH:
- Skin types (dry, oily, combination, sensitive, normal)
- Sun protection (UV index in Tanzania is extreme)
- Daily skincare routines
- Natural remedies (aloe vera, shea butter, coconut oil)"""
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=300,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        return {
            "success": True,
            "response": ai_response,
            "model": "gpt-3.5-turbo"
        }
        
    except Exception as e:
        print(f"OpenAI error: {str(e)}")
        return {
            "success": False,
            "response": "Samahani, nahitaji muda kidogo. Tafadhali jaribu tena."
        }

# ============================================
# PRODUCT RECOMMENDATION ENDPOINT
# ============================================

@app.get("/products/recommend")
async def get_recommended_products(
    lat: float,
    lon: float,
    skin_type: str = "normal",
    user_id: str = Depends(verify_token)
):
    """Get products recommended based on skin type"""
    try:
        return {
            "success": True,
            "products": [
                {
                    "id": "1",
                    "name": "Hydrating Face Cream",
                    "description": "Deeply moisturizes dry skin",
                    "price": 25000,
                    "category": "moisturizer",
                    "skin_type": skin_type,
                    "store_name": "SkinCare Tanzania",
                    "rating": 4.5
                },
                {
                    "id": "2",
                    "name": "Gentle Foaming Cleanser",
                    "description": "For oily and combination skin",
                    "price": 18000,
                    "category": "cleanser",
                    "skin_type": skin_type,
                    "store_name": "Glow Beauty",
                    "rating": 4.3
                }
            ]
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

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
    print(f"✅ Database: SQLite with users, analyses tables")
    print("=" * 60)
    print(f"🚀 Server starting on port {port}...")
    print(f"📚 API Docs: https://skinglow-backend.up.railway.app/docs")
    print("=" * 60)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
