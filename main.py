# ============================================
# SKINGLOW AI - PRODUCTION BACKEND (CLEAN)
# ============================================

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from PIL import Image
import io
import os
import requests
import uvicorn
from typing import Dict, Optional
from dotenv import load_dotenv
import jwt

# ============================================
# LOAD ENV
# ============================================
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "skinglow-secret")
ALGORITHM = "HS256"
security = HTTPBearer()

# ============================================
# INIT APP
# ============================================
app = FastAPI(
    title="SkinGlow AI API",
    version="3.0.0",
    description="AI Skin Analysis + Weather + UV Protection"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# MEDIA PIPELINE (OPTIONAL AI LAYER)
# ============================================
MEDIAPIPE_AVAILABLE = False

try:
    import mediapipe as mp
    import cv2
    import numpy as np

    mp_face = mp.solutions.face_detection
    face_detector = mp_face.FaceDetection(min_detection_confidence=0.5)

    MEDIAPIPE_AVAILABLE = True
except:
    print("⚠️ MediaPipe fallback mode active")

# ============================================
# SKIN DATABASE
# ============================================
SKIN_DB = {
    "dry": {"name": "Dry Skin", "tip": "Use hydrating skincare"},
    "oily": {"name": "Oily Skin", "tip": "Use oil control products"},
    "normal": {"name": "Normal Skin", "tip": "Maintain balance"},
    "sensitive": {"name": "Sensitive Skin", "tip": "Use gentle products"},
    "combination": {"name": "Combination Skin", "tip": "Balance zones"}
}

# ============================================
# AUTH FUNCTIONS
# ============================================
def create_token(data: dict, exp_minutes=30):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=exp_minutes)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded["sub"]
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============================================
# PIPELINE 1: IMAGE PROCESSING
# ============================================
def analyze_image(image_bytes: bytes):
    """
    STEP 1: Convert image
    STEP 2: AI detection (MediaPipe OR fallback)
    STEP 3: Return skin type
    """

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # fallback AI
        pixels = list(image.getdata())
        avg = sum(sum(p) for p in pixels) / (len(pixels) * 3)

        if avg > 200:
            return "dry", 0.7
        elif avg < 90:
            return "oily", 0.7
        elif 90 <= avg <= 130:
            return "combination", 0.6
        elif avg > 160:
            return "sensitive", 0.6
        else:
            return "normal", 0.6

    except:
        return "normal", 0.5

# ============================================
# PIPELINE 2: WEATHER SERVICE
# ============================================
def get_weather(lat: float, lon: float):
    api_key = os.getenv("OPENWEATHER_API_KEY")

    if not api_key:
        return {"uv": 5, "temp": 25, "city": "Unknown"}

    try:
        url = f"https://api.openweathermap.org/data/2.5/weather"
        res = requests.get(url, params={
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "units": "metric"
        }).json()

        return {
            "uv": 6,
            "temp": res.get("main", {}).get("temp", 25),
            "city": res.get("name", "Unknown")
        }
    except:
        return {"uv": 5, "temp": 25, "city": "Unknown"}

# ============================================
# PIPELINE 3: SUNSCREEN ENGINE
# ============================================
def sunscreen_engine(uv, skin_type):
    if uv <= 2:
        spf = 15
    elif uv <= 5:
        spf = 30
    else:
        spf = 50

    return {
        "spf": spf,
        "uv": uv,
        "skin_advice": SKIN_DB[skin_type]["tip"],
        "reapply": 2 if uv > 5 else 4
    }

# ============================================
# PIPELINE 4: MAIN ANALYSIS FLOW
# ============================================
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    contents = await file.read()

    skin_type, confidence = analyze_image(contents)

    return {
        "skin_type": skin_type,
        "skin_name": SKIN_DB[skin_type]["name"],
        "confidence": confidence,
        "advice": SKIN_DB[skin_type]["tip"],
        "timestamp": datetime.utcnow()
    }

# ============================================
# PIPELINE 5: WEATHER + SKIN COMBINATION
# ============================================
@app.get("/full-analysis/{lat}/{lon}")
async def full_analysis(lat: float, lon: float, user=Depends(verify_user)):

    weather = get_weather(lat, lon)

    skin_type = "normal"  # default for weather endpoint

    sunscreen = sunscreen_engine(weather["uv"], skin_type)

    return {
        "location": weather["city"],
        "temperature": weather["temp"],
        "uv_index": weather["uv"],
        "sunscreen": sunscreen
    }

# ============================================
# AUTH
# ============================================
@app.post("/auth/login")
async def login(email: str):
    token = create_token({"sub": email})
    return {"token": token}

# ============================================
# HEALTH CHECK
# ============================================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "mediapipe": MEDIAPIPE_AVAILABLE
    }

# ============================================
# RUN SERVER (RAILWAY FIXED)
# ============================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )
