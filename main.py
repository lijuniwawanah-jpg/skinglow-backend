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

# Load environment variables
load_dotenv()

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
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

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
# WEATHER API CONFIGURATION
# ============================================
WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')
WEATHER_API_URL = "https://api.openweathermap.org/data/2.5"

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
# REVERSE GEOCODING FUNCTION
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
                   data.get('address', {}).get('state_district') or \
                   'Unknown'
            return city
        return 'Unknown'
    except Exception:
        return 'Unknown'

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

def get_weather_data(lat: float, lon: float) -> Dict:
    """Get weather and UV data from OpenWeatherMap"""
    if not WEATHER_API_KEY:
        return {
            "success": False,
            "error": "Weather API key not configured",
            "uv_index": 5,
            "temperature": 25,
            "city": "Unknown"
        }
    
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
        
        uv_url = f"https://api.openweathermap.org/data/2.5/uvi"
        uv_params = {
            'lat': lat,
            'lon': lon,
            'appid': WEATHER_API_KEY
        }
        uv_response = requests.get(uv_url, params=uv_params, timeout=10)
        uv_data = uv_response.json() if uv_response.status_code == 200 else {'value': 5}
        
        city_name = weather_data.get('name', 'Unknown')
        
        return {
            "success": True,
            "temperature": weather_data.get('main', {}).get('temp', 25),
            "humidity": weather_data.get('main', {}).get('humidity', 60),
            "condition": weather_data.get('weather', [{}])[0].get('description', 'clear'),
            "uv_index": uv_data.get('value', 5),
            "city": city_name
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

@app.post("/analyze")
async def analyze_skin(file: UploadFile = File(...)):
    """Analyze skin from uploaded image"""
    
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
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/weather/{lat}/{lon}")
async def get_weather(
    lat: float,
    lon: float,
    skin_type: str = "normal"
):
    """Get weather and sunscreen advice"""
    
    weather = get_weather_data(lat, lon)
    
    city_name = weather.get("city", "Unknown")
    if city_name == "Unknown" or city_name == "":
        city_name = await get_city_from_coordinates(lat, lon)
    
    if not weather.get("success"):
        return {
            "success": False,
            "error": weather.get("error", "Weather service unavailable"),
            "city": city_name,
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
            "city": city_name
        },
        "sunscreen": sunscreen,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/location/{lat}/{lon}")
async def get_location_name(lat: float, lon: float):
    """Get location name from coordinates"""
    city_name = await get_city_from_coordinates(lat, lon)
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

@app.get("/skin-types")
async def get_skin_types():
    """Get all available skin types"""
    return {
        "skin_types": [
            {"id": skin_id, "name": data["name"]}
            for skin_id, data in SKIN_CARE_DATA.items()
        ]
    }
# ============================================
# AUTH ENDPOINTS (COMPLETE FIX)
# ============================================

from pydantic import BaseModel
import uuid
from typing import Optional

# Request models
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

# Temporary storage (kwa testing tu)
temp_users = {}

@app.post("/auth/register")
async def register(request: RegisterRequest):
    """Register new user"""
    try:
        email = request.email
        password = request.password
        name = request.name
        
        # Check if user exists
        if email in temp_users:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Email already registered"}
            )
        
        # Save user
        user_id = str(uuid.uuid4())
        temp_users[email] = {
            "id": user_id,
            "email": email,
            "password": password,
            "name": name
        }
        
        # Create token
        token = create_access_token(data={"sub": email, "user_id": user_id})
        
        return {
            "success": True,
            "message": "User registered successfully",
            "token": token,
            "token_type": "bearer",
            "user": {
                "id": user_id,
                "email": email,
                "name": name
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

@app.post("/auth/login")
async def login(request: LoginRequest):
    """Login user"""
    try:
        email = request.email
        password = request.password
        
        # Find user
        user = temp_users.get(email)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Invalid email or password"}
            )
        
        if user.get("password") != password:
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Invalid email or password"}
            )
        
        # Create token
        token = create_access_token(data={"sub": email, "user_id": user["id"]})
        
        return {
            "success": True,
            "message": "Login successful",
            "token": token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "email": email,
                "name": user.get("name")
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

@app.get("/users/me")
async def get_current_user(user_id: str = Depends(verify_token)):
    """Get current user info"""
    for user in temp_users.values():
        if user["id"] == user_id:
            return {
                "success": True,
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "name": user.get("name")
                }
            }
    
    return JSONResponse(
        status_code=404,
        content={"success": False, "message": "User not found"}
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
    print(f"✅ Skin types: {len(SKIN_CARE_DATA)}")
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
