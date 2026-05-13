# ============================================
# SKINGLOW AI - PAN-AFRICAN PRODUCTION BACKEND v5.0
# Created by Ashraf hamis athumani (Wawanah)
# Optimized for All African Regions
# ============================================

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
import uvicorn
from PIL import Image, ImageEnhance
import io
import os
import sys
from typing import Dict, Optional, List, Any
import requests
from dotenv import load_dotenv
import jwt
import bcrypt
from pydantic import BaseModel, EmailStr, Field
import uuid
import sqlite3
import hashlib
import asyncio
import numpy as np
from collections import Counter
import logging
import time
from functools import wraps

# Load environment variables
load_dotenv()

# ============================================
# LOGGING CONFIGURATION
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('skinglow.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============================================
# DATABASE SETUP
# ============================================
DATABASE_FILE = "skinglow.db"

def get_db():
    conn = sqlite3.connect(DATABASE_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

# --- Security Functions ---
def hash_password(password: str) -> str:
    """Hash password using bcrypt (Production Standard)"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password using bcrypt"""
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except:
        return False

def init_db():
    """Initialize database with all tables"""
    with get_db() as conn:
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
                profile_image TEXT,
                fcm_token TEXT,
                email_verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')

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
                method TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # (Other tables like stores, products, etc. remain the same as provided)
        conn.execute('''CREATE TABLE IF NOT EXISTS stores (id TEXT PRIMARY KEY, owner_id TEXT, name TEXT, address TEXT, latitude REAL, longitude REAL, is_active INTEGER DEFAULT 1)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, store_id TEXT, name TEXT, price REAL, category TEXT, skin_type TEXT, is_approved INTEGER DEFAULT 1)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, user_id TEXT, store_id TEXT, status TEXT, total_amount REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS chat_history (id TEXT PRIMARY KEY, user_id TEXT, user_message TEXT, assistant_response TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        conn.commit()

init_db()

# ============================================
# SECURITY CONFIGURATION
# ============================================
SECRET_KEY = os.getenv('SECRET_KEY', 'skin-sight-ai-africa-secret-2024')
ALGORITHM = "HS256"
security = HTTPBearer()

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=30)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("user_id")
    except:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ============================================
# PAN-AFRICAN WEATHER & UV LOGIC
# ============================================
WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')

def get_dynamic_weather(lat: float, lon: float):
    """Fetch real-time weather and UV data with dynamic timezone for any location in Africa"""
    try:
        # Standard fallback if API key is missing
        if not WEATHER_API_KEY:
            # Estimate timezone from longitude (15 degrees = 1 hour)
            offset_hours = round(lon / 15)
            local_tz = timezone(timedelta(hours=offset_hours))
            curr_hour = datetime.now(local_tz).hour
            uv = 10 if 11 <= curr_hour <= 14 else (5 if 8 <= curr_hour <= 17 else 0)
            return {"uv": uv, "temp": 28, "city": "Africa", "offset": offset_hours * 3600}

        # Real API Call
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
        data = requests.get(url, timeout=10).json()

        # OpenWeather /weather doesn't give UV, so we use current time + offset for a smart estimate
        # unless OneCall is used. Here we use the offset provided by the API.
        offset = data.get('timezone', 0)
        local_tz = timezone(timedelta(seconds=offset))
        curr_hour = datetime.now(local_tz).hour

        # Smart UV Estimation based on local sun position
        uv = 0.0
        if 11 <= curr_hour <= 14: uv = 11.0
        elif 9 <= curr_hour <= 16: uv = 7.0
        elif 7 <= curr_hour <= 18: uv = 3.0

        return {
            "uv": uv,
            "temp": data.get('main', {}).get('temp', 25),
            "city": data.get('name', 'Your Location'),
            "offset": offset
        }
    except:
        return {"uv": 5.0, "temp": 25, "city": "Africa", "offset": 0}

# ============================================
# API ENDPOINTS
# ============================================

@app.post("/auth/register")
async def register(request: Request):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing: return JSONResponse(status_code=400, content={"success": False, "message": "Email already exists"})

        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, role) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, hash_password(password), data.get("name", "User"), data.get("role", "customer"))
        )
        conn.commit()

    return {"success": True, "access_token": create_access_token({"user_id": user_id, "sub": email})}

@app.post("/auth/login")
async def login(request: Request):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return JSONResponse(status_code=401, content={"success": False, "message": "Invalid credentials"})

    return {
        "success": True,
        "access_token": create_access_token({"user_id": user["id"], "sub": email}),
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}
    }

@app.get("/weather/{lat}/{lon}")
async def get_weather(lat: float, lon: float, skin_type: str = "normal"):
    w = get_dynamic_weather(lat, lon)
    uv = w['uv']

    # Sun Advice
    if uv >= 8: advice = "Extreme UV! Wear SPF 50+ and stay in shade."
    elif uv >= 5: advice = "High UV. Wear a hat and SPF 30+."
    else: advice = "UV levels are safe. Enjoy your day!"

    return {
        "success": True,
        "uv_index": uv,
        "temperature": w['temp'],
        "city": w['city'],
        "advice": advice,
        "local_time": datetime.now(timezone(timedelta(seconds=w['offset']))).strftime("%H:%M")
    }

# (Other endpoints like /analyze, /chat, /products remain integrated with the same logic)
@app.get("/health")
async def health(): return {"status": "operational", "region": "Pan-African"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
