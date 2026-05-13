# ============================================
# SKINGLOW AI - PAN-AFRICAN MASTER PRODUCTION BACKEND v5.2
# Full Integration: Analysis, Marketplace, AI Chat (Bilingual) & Pan-African Weather
# Optimized by Ashraf Hamis Athumani (Wawanah)
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
import numpy as np
from collections import Counter
import logging
import time
from functools import wraps
import re

# Load environment variables
load_dotenv()

# ============================================
# LOGGING CONFIGURATION
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('skinglow.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# INITIALIZE FASTAPI
# ============================================

app = FastAPI(
    title="SkinGlow AI Master Production",
    description="Professional Skin Analysis and E-commerce API - Pan-African",
    version="5.2.0"
)

# CORS Configuration for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,https://skinglow.com').split(','),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# ============================================
# DATABASE SETUP (SQLite with WAL mode)
# ============================================

DATABASE_FILE = "skinglow.db"

def get_db():
    conn = sqlite3.connect(DATABASE_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

# --- Security Functions (Upgraded to Bcrypt) ---
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
    """Initialize database with ALL production tables"""
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
                profile_image TEXT,
                fcm_token TEXT,
                email_verified INTEGER DEFAULT 0,
                verification_token TEXT,
                reset_token TEXT,
                reset_token_expiry TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
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
                image_url TEXT,
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
                banner_url TEXT,
                rating REAL DEFAULT 0,
                total_reviews INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                is_verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
                compare_price REAL,
                category TEXT,
                skin_type TEXT,
                images TEXT,
                stock INTEGER DEFAULT 0,
                rating REAL DEFAULT 0,
                total_reviews INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                is_approved INTEGER DEFAULT 0,
                is_sponsored INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                sales_count INTEGER DEFAULT 0,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        ''')
        
        # ORDERS TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                order_number TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending',
                total_amount REAL NOT NULL,
                subtotal REAL NOT NULL,
                tax REAL DEFAULT 0,
                shipping_cost REAL DEFAULT 0,
                discount REAL DEFAULT 0,
                payment_method TEXT,
                payment_status TEXT DEFAULT 'pending',
                delivery_address TEXT,
                delivery_latitude REAL,
                delivery_longitude REAL,
                tracking_number TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
                total REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        ''')
        
        # REVIEWS TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                comment TEXT,
                images TEXT,
                is_verified_purchase INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                UNIQUE(user_id, product_id)
            )
        ''')
        
        # CHAT HISTORY TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                assistant_response TEXT NOT NULL,
                provider TEXT,
                skin_context TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # NOTIFICATIONS TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                type TEXT DEFAULT 'info',
                is_read INTEGER DEFAULT 0,
                data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Add missing columns to users table
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        missing_columns = {
            'profile_image': 'TEXT',
            'fcm_token': 'TEXT',
            'email_verified': 'INTEGER DEFAULT 0',
            'verification_token': 'TEXT',
            'reset_token': 'TEXT',
            'reset_token_expiry': 'TIMESTAMP',
            'updated_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        }
        
        for col_name, col_type in missing_columns.items():
            if col_name not in columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                logger.info(f"Added column {col_name} to users table")
        
        # Create indexes for performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
            "CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_products_store_id ON products(store_id)",
            "CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)",
            "CREATE INDEX IF NOT EXISTS idx_products_skin_type ON products(skin_type)",
            "CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
            "CREATE INDEX IF NOT EXISTS idx_reviews_product_id ON reviews(product_id)",
            "CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)"
        ]
        
        for idx in indexes:
            conn.execute(idx)
        
        # Create default admin user
        admin_email = os.getenv('ADMIN_EMAIL', 'admin@skinglow.com')
        admin_password = os.getenv('ADMIN_PASSWORD', 'Admin@123')
        
        existing_admin = conn.execute("SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
        
        if not existing_admin:
            admin_id = str(uuid.uuid4())
            password_hash = hash_password(admin_password)
            conn.execute(
                """INSERT INTO users (id, email, password_hash, name, role, is_approved, email_verified, created_at) 
                   VALUES (?, ?, ?, ?, 'admin', 1, 1, CURRENT_TIMESTAMP)""",
                (admin_id, admin_email, password_hash, "Super Admin")
            )
            conn.commit()
            logger.info(f"✅ Default admin user created: {admin_email}")
        else:
            logger.info("✅ Admin user already exists")
        
        conn.commit()
        logger.info("✅ Database initialized successfully!")

# Initialize database
init_db()

# ============================================
# LIFESPAN MANAGER (For production)
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting SkinGlow AI Pan-African Production Server v5.2...")
    logger.info(f"MediaPipe: {'Available' if MEDIAPIPE_AVAILABLE else 'Not available'}")
    logger.info(f"OpenAI: {'Configured' if OPENAI_API_KEY else 'Not configured'}")
    logger.info(f"Gemini: {'Configured' if GEMINI_API_KEY else 'Not configured'}")
    logger.info(f"Weather API: {'Configured' if WEATHER_API_KEY else 'Not configured'}")
    yield
    # Shutdown
    logger.info("👋 Shutting down SkinGlow AI Server...")

# Re-initialize app with lifespan
app = FastAPI(
    title="SkinGlow AI Master Production",
    description="Professional Skin Analysis and E-commerce API - Pan-African",
    version="5.2.0",
    lifespan=lifespan
)

# Re-add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,https://skinglow.com').split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# SECURITY CONFIGURATION
# ============================================

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY or len(SECRET_KEY) < 32:
    SECRET_KEY = 'skin-sight-ai-africa-secret-key-2024-master-production'
    logger.warning("Using default SECRET_KEY. Please set a secure key in production!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '30'))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', '7'))
security = HTTPBearer()

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id") or payload.get("sub")
        token_type = payload.get("type")
        
        if not user_id or token_type != "access":
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def verify_refresh_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        token_type = payload.get("type")
        
        if not user_id or token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

def require_role(required_role: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, user_id: str = Depends(verify_token), **kwargs):
            with get_db() as conn:
                user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
                if not user or user["role"] != required_role:
                    raise HTTPException(status_code=403, detail="Insufficient permissions")
            return await func(*args, user_id=user_id, **kwargs)
        return wrapper
    return decorator

# ============================================
# REQUEST MODELS
# ============================================

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    role: Optional[str] = "customer"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    system_context: Optional[str] = None
    conversation_history: Optional[List[Dict[str, str]]] = None
    max_tokens: Optional[int] = 500
    temperature: Optional[float] = 0.7

class ProductCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    compare_price: Optional[float] = None
    category: str
    skin_type: Optional[str] = None
    images: Optional[List[str]] = None
    stock: int = Field(0, ge=0)
    tags: Optional[List[str]] = None

class ReviewCreateRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    images: Optional[List[str]] = None

class OrderCreateRequest(BaseModel):
    store_id: str
    items: List[Dict[str, Any]]
    delivery_address: str
    delivery_latitude: Optional[float] = None
    delivery_longitude: Optional[float] = None
    payment_method: str
    notes: Optional[str] = None

# ============================================
# MEDIAPIPE (Optional)
# ============================================

MEDIAPIPE_AVAILABLE = False
try:
    import mediapipe as mp
    import cv2
    os.environ['GLOG_minloglevel'] = '2'
    mp_face_detection = mp.solutions.face_detection
    face_detection = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
    MEDIAPIPE_AVAILABLE = True
    logger.info("✅ MediaPipe loaded!")
except:
    logger.warning("⚠️ MediaPipe not available - using fallback analysis")

# ============================================
# AI CONFIGURATION
# ============================================

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
AI_PROVIDER = os.getenv('AI_PROVIDER', 'openai')

if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        logger.info("✅ Gemini AI configured")
    except:
        logger.warning("⚠️ Gemini AI not available")

# ============================================
# BILINGUAL OFF-TOPIC RESPONSES
# ============================================

def detect_language(text: str) -> str:
    """Detect if text is primarily English or Swahili"""
    text_lower = text.lower()
    
    # Swahili common words
    swahili_words = ['na', 'ya', 'wa', 'kwa', 'ni', 'cha', 'vya', 'za', 'la', 'ma', 
                     'nina', 'una', 'ana', 'tuna', 'wana', 'nilikuwa', 'alikuwa',
                     'hapa', 'kule', 'huko', 'sasa', 'basi', 'kama', 'ilikuwa']
    
    # English common words
    english_words = ['the', 'and', 'of', 'to', 'in', 'for', 'is', 'on', 'that', 'with',
                     'this', 'was', 'are', 'as', 'at', 'be', 'from', 'has', 'have']
    
    swahili_count = sum(1 for word in swahili_words if word in text_lower)
    english_count = sum(1 for word in english_words if word in text_lower)
    
    if swahili_count > english_count:
        return "swahili"
    else:
        return "english"

def get_off_topic_response(message: str) -> str:
    """Return short, natural response in the same language as the user message"""
    language = detect_language(message)
    
    if language == "swahili":
        responses = [
            "Samahani, ninaweza kukusaidia tu kuhusu utunzaji wa ngozi. Una swali gani kuhusu ngozi yako?",
            "Niko hapa kwa maswali ya ngozi. Uliza kuhusu acne, ngozi kavu, au sunscreen nikusaidie.",
            "Tuongee kuhusu ngozi yako. Una changamoto gani unayokabiliana nayo?",
            "Nina mtaalamu wa ngozi. Una swali gani kuhusu utunzaji wa ngozi?",
            "Samahani, siwezi kujibu swali hili. Uliza kuhusu ngozi yako badala yake."
        ]
    else:
        responses = [
            "I can only help with skincare questions. What would you like to know about your skin?",
            "I'm here for skincare advice. Ask me about acne, dry skin, oily skin, or sunscreen.",
            "Let's talk about your skin. What skin concern are you dealing with?",
            "I specialize in skincare. Do you have a question about your skin routine?",
            "Sorry, I can only answer skincare-related questions. What's your skin concern?"
        ]
    
    import random
    return random.choice(responses)

def get_skincare_fallback_response(message: str) -> str:
    """Return skincare advice based on keywords in the user's language"""
    language = detect_language(message)
    message_lower = message.lower()
    
    # Acne related
    if any(word in message_lower for word in ["acne", "chunusi", "pimple", "breakout"]):
        if language == "swahili":
            return """Kwa acne (chunusi), napendekeza:
1. Tumia cleanser yenye salicylic acid au benzoyl peroxide
2. Usiguse au kubana chunusi (inaweza kusababisha makovu)
3. Tumia moisturizer lightweight isiyo na mafuta
4. Omba sunscreen SPF 30+ kila siku
5. Epuka vyakula vya mafuta mengi na sukari

Je, ungependa kujua zaidi kuhusu bidhaa maalum za acne?"""
        else:
            return """For acne, I recommend:
1. Use a cleanser with salicylic acid or benzoyl peroxide
2. Don't touch or pop pimples (can cause scarring)
3. Use a lightweight, oil-free moisturizer
4. Apply SPF 30+ sunscreen daily
5. Avoid oily foods and excess sugar

Would you like to know more about specific acne products?"""
    
    # Dry skin
    elif any(word in message_lower for word in ["dry", "kavu", "flaky", "tight"]):
        if language == "swahili":
            return """Kwa ngozi kavu:
1. Tumia hydrating cleanser isiyo na sulfate
2. Omba hyaluronic acid serum
3. Tumia rich moisturizer yenye ceramides au shea butter
4. Ongeza facial oil kama argan au jojoba
5. Kunywa maji mengi (lita 2-3 kwa siku)

Je, unahitaji ushauri wa bidhaa maalum?"""
        else:
            return """For dry skin:
1. Use a hydrating, sulfate-free cleanser
2. Apply hyaluronic acid serum
3. Use a rich moisturizer with ceramides or shea butter
4. Add a facial oil like argan or jojoba
5. Drink plenty of water (2-3 liters daily)

Do you need product recommendations?"""
    
    # Oily skin
    elif any(word in message_lower for word in ["oily", "mafuta", "greasy", "shine"]):
        if language == "swahili":
            return """Kwa ngozi yenye mafuta:
1. Tumia foaming au gel cleanser
2. Omba niacinamide serum (inasaidia kudhibiti mafuta)
3. Tumia gel moisturizer isiyo na mafuta
4. Exfoliate mara 2 kwa wiki kwa salicylic acid
5. Tumia clay mask mara moja kwa wiki

Je, ungependa maelezo zaidi?"""
        else:
            return """For oily skin:
1. Use a foaming or gel cleanser
2. Apply niacinamide serum (helps control oil)
3. Use an oil-free gel moisturizer
4. Exfoliate twice weekly with salicylic acid
5. Use a clay mask once weekly

Would you like more details?"""
    
    # Sunscreen/UV
    elif any(word in message_lower for word in ["sunscreen", "spf", "jua", "sun", "uv"]):
        if language == "swahili":
            return """Kuhusu kinga ya jua:
1. Tumia SPF 30+ kila siku, hata ukiwa ndani
2. Omba dakika 15-20 kabla ya kwenda nje
3. Tumia kiasi cha kutosha (1/2 kijiko kwa uso)
4. Rudia kila baada ya masaa 2-3
5. Chagua sunscreen inayofaa aina ya ngozi yako

Unahitaji msaada wa kuchagua sunscreen?"""
        else:
            return """About sun protection:
1. Use SPF 30+ daily, even indoors
2. Apply 15-20 minutes before sun exposure
3. Use enough (1/2 teaspoon for face and neck)
4. Reapply every 2-3 hours
5. Choose sunscreen suitable for your skin type

Need help choosing a sunscreen?"""
    
    # Default
    else:
        if language == "swahili":
            return """Niko hapa kukusaidia na ngozi yako. Je, una swali kuhusu:
- Aina ya ngozi yako (kavu, mafuta, combination, nyeti)
- Matatizo ya ngozi (acne, matangazo meusi, kasoro)
- Bidhaa za ngozi (cleansers, moisturizers, sunscreen)
- Kinga ya jua na UV

Tafadhali uliza swali maalum zaidi ili nikusaidie vizuri."""
        else:
            return """I'm here to help with your skin. Do you have a question about:
- Your skin type (dry, oily, combination, sensitive)
- Skin problems (acne, dark spots, wrinkles)
- Skincare products (cleansers, moisturizers, sunscreen)
- Sun protection and UV

Please ask a more specific question so I can help you better."""

# ============================================
# CHAT SERVICE (Less Restrictive, Bilingual)
# ============================================

class ChatService:
    @staticmethod
    async def get_openai_response(
        user_message: str,
        system_context: str,
        conversation_history: Optional[List[Dict]] = None,
        max_tokens: int = 600,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        if not OPENAI_API_KEY:
            return {
                "success": True,
                "response": get_skincare_fallback_response(user_message),
                "provider": "fallback"
            }
        
        try:
            import openai
            openai.api_key = OPENAI_API_KEY
            
            # Flexible system prompt
            system_prompt = """You are a skincare expert. Answer questions about skincare, skin problems, products, and sun protection.

You can respond at appropriate length to explain well. Give detailed answers with examples and recommendations.

For off-topic questions (politics, celebrities, sports, etc.), respond briefly in the same language as the user: "I can only help with skincare questions. What's your skin concern?"

Be natural and don't repeat yourself. Answer the question directly."""
            
            messages = [{"role": "system", "content": system_prompt}]
            
            if conversation_history:
                messages.extend(conversation_history[-10:])
            
            messages.append({"role": "user", "content": user_message})
            
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            ai_response = response.choices[0].message.content
            
            return {
                "success": True,
                "response": ai_response,
                "provider": "openai"
            }
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return {
                "success": True,
                "response": get_skincare_fallback_response(user_message),
                "provider": "fallback"
            }
    
    @staticmethod
    async def get_gemini_response(
        user_message: str,
        system_context: str,
        conversation_history: Optional[List[Dict]] = None,
        max_tokens: int = 600,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        if not GEMINI_API_KEY:
            return {
                "success": True,
                "response": get_skincare_fallback_response(user_message),
                "provider": "fallback"
            }
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            
            model = genai.GenerativeModel('gemini-pro')
            
            system_prompt = """You are a skincare expert. Give detailed advice about skincare routines, products, and skin problems.

Respond at appropriate length. Give examples and recommendations.

For off-topic questions, respond briefly in the same language as the user.

Be natural and direct. Don't repeat yourself."""
            
            full_prompt = f"{system_prompt}\n\n{system_context}\n\n"
            
            if conversation_history:
                for msg in conversation_history[-10:]:
                    role = "User" if msg["role"] == "user" else "Assistant"
                    full_prompt += f"{role}: {msg['content']}\n"
            
            full_prompt += f"User: {user_message}\nAssistant:"
            
            response = model.generate_content(
                full_prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                }
            )
            
            return {
                "success": True,
                "response": response.text,
                "provider": "gemini"
            }
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return {
                "success": True,
                "response": get_skincare_fallback_response(user_message),
                "provider": "fallback"
            }
    
    @classmethod
    async def get_response(cls, user_message: str, system_context: str = None, **kwargs) -> Dict[str, Any]:
        default_context = """You are a skincare expert. Give detailed, natural advice about skincare.

You can respond at appropriate length. Give examples and practical tips.

For off-topic questions, respond briefly in the same language as the user."""
        
        context = system_context or default_context
        
        if AI_PROVIDER == "openai" and OPENAI_API_KEY:
            return await cls.get_openai_response(user_message, context, **kwargs)
        elif AI_PROVIDER == "gemini" and GEMINI_API_KEY:
            return await cls.get_gemini_response(user_message, context, **kwargs)
        else:
            return {
                "success": True,
                "response": get_skincare_fallback_response(user_message),
                "provider": "fallback"
            }

# ============================================
# CHECK IF SKIN-RELATED (with language detection)
# ============================================

def is_skin_related(message: str) -> tuple:
    """Check if message is related to skincare - returns (is_related, confidence, language)"""
    message_lower = message.lower()
    language = detect_language(message)
    
    # Strong skincare keywords
    skin_keywords = [
        "ngozi", "skin", "acne", "chunusi", "pimple", "breakout", "dry", "kavu", 
        "oily", "mafuta", "moisturizer", "sunscreen", "spf", "cleanser", "serum", 
        "toner", "mask", "wrinkle", "kukunja", "rash", "upele", "redness", 
        "pigmentation", "dark spot", "doa", "dermatologist", "uv", "jua", "sun",
        "cream", "lotion", "gel", "exfoliate", "scrub", "retinol", "hyaluronic",
        "niacinamide", "salicylic", "glycolic", "ceramide", "peptide"
    ]
    
    # Calculate relevance score
    relevance_score = 0
    for keyword in skin_keywords:
        if keyword in message_lower:
            relevance_score += 1
    
    # If message has at least 1 skincare keyword, consider it related
    if relevance_score >= 1:
        return True, relevance_score, language
    
    # Off-topic indicators
    off_topic_keywords = [
        "politics", "election", "president", "football", "soccer", "basketball",
        "movie", "celebrity", "musician", "song", "album", "actor", "actress",
        "stock", "investment", "crypto", "bitcoin", "religion", "church", "mosque",
        "prayer", "god", "relationship", "dating", "marriage"
    ]
    
    for keyword in off_topic_keywords:
        if keyword in message_lower:
            return False, 0, language
    
    # Default - give benefit of doubt for short messages
    if len(message.split()) < 3:
        return True, 0.3, language
    
    return False, 0, language

# ============================================
# WEATHER CONFIGURATION (PAN-AFRICAN)
# ============================================

WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')

def get_dynamic_weather(lat: float, lon: float):
    """Pan-African weather with dynamic timezone for accurate UV"""
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
        resp = requests.get(url, timeout=10).json()
        offset = resp.get('timezone', 0)

        local_tz = timezone(timedelta(seconds=offset))
        curr_hour = datetime.now(local_tz).hour

        uv = 0.0
        if 11 <= curr_hour <= 14:
            uv = 11.0
        elif 9 <= curr_hour <= 16:
            uv = 7.0
        elif 7 <= curr_hour <= 18:
            uv = 3.0

        return {
            "uv_index": uv,
            "temperature": resp.get('main', {}).get('temp', 25),
            "humidity": resp.get('main', {}).get('humidity', 60),
            "condition": resp.get('weather', [{}])[0].get('description', 'clear'),
            "city": resp.get('name', 'Your City'),
            "offset": offset
        }
    except:
        return {
            "uv_index": 5.0,
            "temperature": 25,
            "humidity": 60,
            "condition": "clear",
            "city": "Your City",
            "offset": 0
        }

def get_sunscreen_recommendation(uv_index: float, skin_type: str) -> Dict:
    if uv_index <= 2:
        level, spf, advice = "Low", 15, "Minimal UV risk. Sunscreen optional."
    elif uv_index <= 5:
        level, spf, advice = "Moderate", 30, "Sunscreen recommended."
    elif uv_index <= 7:
        level, spf, advice = "High", 50, "Strong protection needed."
    else:
        level, spf, advice = "Extreme", 50, "Maximum protection required. Avoid peak sun hours."
    
    skin_advice = {
        'dry': "Hydrating sunscreen with moisturizers",
        'oily': "Oil-free, non-comedogenic sunscreen",
        'combination': "Lightweight, gel-based sunscreen",
        'sensitive': "Mineral sunscreen with zinc oxide",
        'normal': "Broad-spectrum SPF 30+ sunscreen"
    }
    
    return {
        "uv_index": uv_index,
        "uv_level": level,
        "advice": advice,
        "recommended_spf": spf,
        "reapplication_hours": 2 if uv_index > 5 else 4,
        "skin_advice": skin_advice.get(skin_type, skin_advice['normal']),
        "tips": [
            "Apply 15-20 minutes before sun exposure",
            f"Reapply every {2 if uv_index > 5 else 4} hours",
            "Use 1/2 teaspoon for face and neck",
            "Don't forget ears, back of neck, and lips"
        ]
    }

# ============================================
# IMAGE PROCESSING
# ============================================

def standardize_image_lighting(image_bytes: bytes) -> np.ndarray:
    """Standardize image lighting for consistent analysis"""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        image = image.resize((500, 500), Image.Resampling.LANCZOS)
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.3)
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.2)
        
        img_array = np.array(image)
        
        if 'cv2' in sys.modules:
            try:
                import cv2
                yuv = cv2.cvtColor(img_array, cv2.COLOR_RGB2YUV)
                yuv[:,:,0] = cv2.equalizeHist(yuv[:,:,0])
                img_array = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB)
            except:
                pass
        
        return img_array
    except Exception as e:
        logger.error(f"Image preprocessing error: {e}")
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        return np.array(image.resize((500, 500)))

# ============================================
# SKIN ANALYSIS FUNCTIONS
# ============================================

def analyze_with_mediapipe(image_bytes: bytes) -> Optional[Dict]:
    """Analyze skin using MediaPipe with multiple ROI sampling"""
    if not MEDIAPIPE_AVAILABLE:
        return None
    
    try:
        import cv2
        standardized_img = standardize_image_lighting(image_bytes)
        image_rgb = cv2.cvtColor(standardized_img, cv2.COLOR_RGB2BGR)
        image_rgb = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2RGB)
        
        results = face_detection.process(image_rgb)
        
        if results.detections:
            h, w, _ = standardized_img.shape
            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            x = max(0, int(bbox.xmin * w))
            y = max(0, int(bbox.ymin * h))
            width = min(w - x, int(bbox.width * w))
            height = min(h - y, int(bbox.height * h))
            
            face_region = standardized_img[y:y+height, x:x+width]
            
            if face_region.size > 0:
                fh, fw, _ = face_region.shape
                
                rois = {
                    'forehead': face_region[int(fh*0.1):int(fh*0.35), int(fw*0.25):int(fw*0.75)],
                    'left_cheek': face_region[int(fh*0.4):int(fh*0.7), int(fw*0.05):int(fw*0.3)],
                    'right_cheek': face_region[int(fh*0.4):int(fh*0.7), int(fw*0.7):int(fw*0.95)],
                    'chin': face_region[int(fh*0.7):int(fh*0.9), int(fw*0.3):int(fw*0.7)]
                }
                
                results_list = []
                for name, roi in rois.items():
                    if roi.size > 0:
                        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
                        texture_var = np.var(gray)
                        avg_bright = np.mean(gray)
                        
                        if texture_var > 3500:
                            roi_type = "oily"
                        elif texture_var < 1800:
                            roi_type = "dry"
                        elif avg_bright > 200:
                            roi_type = "sensitive"
                        elif 100 < avg_bright < 160:
                            roi_type = "combination"
                        else:
                            roi_type = "normal"
                        
                        results_list.append(roi_type)
                
                if results_list:
                    counts = Counter(results_list)
                    most_common = counts.most_common(1)[0]
                    agreement = counts[most_common[0]] / len(results_list)
                    
                    if agreement >= 0.75:
                        skin_type = most_common[0]
                        confidence = 0.85 + (agreement - 0.75) * 0.1
                    elif agreement >= 0.5:
                        scores = {
                            'dry': counts.get('dry', 0) * 1.5,
                            'oily': counts.get('oily', 0) * 1.5,
                            'combination': counts.get('combination', 0) * 1.2,
                            'sensitive': counts.get('sensitive', 0) * 1.3,
                            'normal': counts.get('normal', 0) * 1.0
                        }
                        skin_type = max(scores, key=scores.get)
                        confidence = 0.75
                    else:
                        full_face_gray = cv2.cvtColor(face_region, cv2.COLOR_RGB2GRAY)
                        texture_var = np.var(full_face_gray)
                        avg_bright = np.mean(full_face_gray)
                        
                        if texture_var > 3500:
                            skin_type = "oily"
                        elif texture_var < 1800:
                            skin_type = "dry"
                        elif avg_bright > 200:
                            skin_type = "sensitive"
                        elif 100 < avg_bright < 160:
                            skin_type = "combination"
                        else:
                            skin_type = "normal"
                        confidence = 0.70
                    
                    return {
                        "skin_type": skin_type,
                        "confidence": min(0.95, confidence),
                        "method": "AI Analysis"
                    }
        
        return None
    except Exception as e:
        logger.error(f"MediaPipe analysis error: {e}")
        return None

def analyze_with_fallback(image_bytes: bytes) -> Dict:
    """Production fallback analysis with multiple metrics"""
    try:
        std_img = standardize_image_lighting(image_bytes)
        
        try:
            import cv2
            gray = cv2.cvtColor(std_img, cv2.COLOR_RGB2GRAY)
        except:
            pil_img = Image.open(io.BytesIO(image_bytes))
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            gray = np.array(pil_img.resize((200, 200)).convert('L'))
        
        texture_var = np.var(gray)
        avg_brightness = np.mean(gray)
        
        scores = {"dry": 0, "oily": 0, "combination": 0, "sensitive": 0, "normal": 0}
        
        if texture_var > 3500:
            scores["oily"] += 4
            scores["combination"] += 2
        elif texture_var > 2500:
            scores["oily"] += 2
            scores["combination"] += 3
        elif texture_var < 1800:
            scores["dry"] += 4
            scores["normal"] += 1
        elif texture_var < 2500:
            scores["normal"] += 3
            scores["combination"] += 2
        else:
            scores["normal"] += 2
        
        if avg_brightness > 200:
            scores["dry"] += 3
            scores["sensitive"] += 2
        elif avg_brightness < 100:
            scores["oily"] += 3
        elif avg_brightness < 130:
            scores["normal"] += 2
        else:
            scores["combination"] += 2
        
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
        
        confidence = 0.65 + (max_score / 15) * 0.25
        confidence = min(0.85, confidence)
        
        return {
            "skin_type": skin_type,
            "confidence": confidence,
            "method": "Color Analysis"
        }
        
    except Exception as e:
        logger.error(f"Fallback analysis error: {e}")
        return {
            "skin_type": "normal",
            "confidence": 0.60,
            "method": "Default Analysis"
        }

def analyze_with_consistency(image_bytes: bytes) -> Dict:
    """Run multiple analyses and return consistent result"""
    results = []
    
    result1 = analyze_with_mediapipe(image_bytes)
    if result1:
        results.append(result1)
    
    if not results:
        return analyze_with_fallback(image_bytes)
    
    skin_types = [r["skin_type"] for r in results]
    confidences = [r["confidence"] for r in results]
    
    counts = Counter(skin_types)
    most_common = counts.most_common(1)[0]
    
    if len(set(skin_types)) == 1:
        avg_confidence = sum(confidences) / len(confidences)
        return {
            "skin_type": most_common[0],
            "confidence": min(0.95, avg_confidence),
            "method": results[0]["method"]
        }
    
    return analyze_with_fallback(image_bytes)

# ============================================
# SKIN CARE DATABASE
# ============================================

SKIN_CARE_DATA = {
    "dry": {
        "name": "Dry Skin",
        "characteristics": ["Lacks moisture", "May feel tight or flaky", "Fine lines visible", "Rough texture"],
        "recommendations": [
            "Use hydrating cleanser",
            "Apply hyaluronic acid serum",
            "Use rich moisturizer with ceramides",
            "Add facial oil to routine",
            "Avoid harsh exfoliants"
        ],
        "oils": ["Argan Oil", "Rosehip Oil", "Jojoba Oil", "Marula Oil"],
        "ingredients": ["Hyaluronic Acid", "Glycerin", "Ceramides", "Squalane", "Shea Butter"]
    },
    "oily": {
        "name": "Oily Skin",
        "characteristics": ["Excess sebum", "Shiny appearance", "Large pores", "Prone to acne"],
        "recommendations": [
            "Use foaming or gel cleanser",
            "Apply niacinamide serum",
            "Use lightweight gel moisturizer",
            "Exfoliate with salicylic acid",
            "Use clay mask weekly"
        ],
        "oils": ["Grapeseed Oil", "Tea Tree Oil", "Hemp Seed Oil", "Jojoba Oil"],
        "ingredients": ["Niacinamide", "Salicylic Acid", "Retinol", "Zinc", "Tea Tree"]
    },
    "combination": {
        "name": "Combination Skin",
        "characteristics": ["Oily in T-zone", "Normal or dry on cheeks", "Enlarged pores on nose"],
        "recommendations": [
            "Use balancing cleanser",
            "Lightweight moisturizer all over",
            "Exfoliate T-zone area",
            "Use gel-based products",
            "Multi-masking technique"
        ],
        "oils": ["Jojoba Oil", "Squalane Oil", "Marula Oil", "Argan Oil"],
        "ingredients": ["Niacinamide", "Hyaluronic Acid", "Green Tea", "Aloe Vera"]
    },
    "sensitive": {
        "name": "Sensitive Skin",
        "characteristics": ["Easily irritated", "Prone to redness", "Burning sensation", "Reactive to products"],
        "recommendations": [
            "Use gentle, fragrance-free cleanser",
            "Calming ingredients like centella",
            "Minimal product routine",
            "Patch test new products",
            "Avoid physical exfoliation"
        ],
        "oils": ["Chamomile Oil", "Calendula Oil", "Rose Oil", "Squalane"],
        "ingredients": ["Centella Asiatica", "Aloe Vera", "Oatmeal", "Panthenol", "Madecassoside"]
    },
    "normal": {
        "name": "Normal Skin",
        "characteristics": ["Balanced moisture", "Neither too oily nor too dry", "Small pores", "Radiant complexion"],
        "recommendations": [
            "Regular gentle cleansing",
            "Antioxidant serum (Vitamin C)",
            "SPF daily without fail",
            "Weekly exfoliation",
            "Maintain with moisturizer"
        ],
        "oils": ["Argan Oil", "Jojoba Oil", "Rosehip Oil", "Squalane"],
        "ingredients": ["Vitamin C", "Hyaluronic Acid", "Peptides", "Antioxidants", "SPF"]
    }
}

# ============================================
# HEALTH CHECK
# ============================================

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "app": "SkinGlow AI Master Production",
        "version": "5.2.0",
        "region": "Pan-African",
        "environment": os.getenv("ENVIRONMENT", "production"),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    try:
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "operational",
        "version": "5.2.0",
        "services": {
            "database": db_status,
            "mediapipe": MEDIAPIPE_AVAILABLE,
            "weather_api": bool(WEATHER_API_KEY),
            "openai": bool(OPENAI_API_KEY),
            "gemini": bool(GEMINI_API_KEY)
        },
        "timestamp": datetime.now().isoformat()
    }

# ============================================
# AUTH ENDPOINTS
# ============================================

@app.post("/auth/register")
async def register(request: RegisterRequest):
    try:
        with get_db() as conn:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (request.email,)).fetchone()
            if existing:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "message": "Email already registered"}
                )
            
            user_id = str(uuid.uuid4())
            password_hash = hash_password(request.password)
            is_approved = 1 if request.role == 'customer' else 0
            
            conn.execute(
                """INSERT INTO users (id, email, password_hash, name, role, is_approved, phone, address, created_at, updated_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                (user_id, request.email, password_hash, request.name, request.role, is_approved, request.phone, request.address)
            )
            conn.commit()
        
        access_token = create_access_token({"sub": request.email, "user_id": user_id, "role": request.role})
        refresh_token = create_refresh_token(user_id)
        
        return {
            "success": True,
            "message": "User registered successfully",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user_id,
                "email": request.email,
                "name": request.name,
                "role": request.role,
                "is_approved": is_approved
            }
        }
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )

@app.post("/auth/login")
async def login(request: LoginRequest):
    try:
        with get_db() as conn:
            user = conn.execute(
                "SELECT id, email, password_hash, name, role, is_approved, phone, address, created_at FROM users WHERE email = ?",
                (request.email,)
            ).fetchone()
            
            if not user or not verify_password(request.password, user["password_hash"]):
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "message": "Invalid email or password"}
                )
            
            if user["role"] == "vendor" and user["is_approved"] == 0:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "message": "Your vendor account is pending approval"}
                )
            
            conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
            conn.commit()
        
        access_token = create_access_token({"sub": user["email"], "user_id": user["id"], "role": user["role"]})
        refresh_token = create_refresh_token(user["id"])
        
        return {
            "success": True,
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "name": user["name"],
                "role": user["role"],
                "is_approved": user["is_approved"],
                "phone": user["phone"],
                "address": user["address"],
                "member_since": user["created_at"]
            }
        }
    except Exception as e:
        logger.error(f"Login error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )

@app.post("/auth/refresh")
async def refresh_token(request: RefreshTokenRequest):
    try:
        user_id = verify_refresh_token(request.refresh_token)
        
        with get_db() as conn:
            user = conn.execute("SELECT id, email, role FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "message": "User not found"}
                )
        
        new_access_token = create_access_token({"sub": user["email"], "user_id": user["id"], "role": user["role"]})
        
        return {
            "success": True,
            "access_token": new_access_token,
            "token_type": "bearer"
        }
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"success": False, "message": e.detail}
        )
    except Exception as e:
        logger.error(f"Refresh token error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )

@app.post("/auth/logout")
async def logout(user_id: str = Depends(verify_token)):
    return {"success": True, "message": "Logged out successfully"}

@app.get("/users/me")
async def get_current_user(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute(
            """SELECT id, email, name, role, is_approved, created_at, updated_at, last_login, phone, address, profile_image 
               FROM users WHERE id = ?""",
            (user_id,)
        ).fetchone()
        
        if not user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "User not found"}
            )
        
        return {"success": True, "user": dict(user)}

@app.put("/users/me")
async def update_profile(request: UpdateProfileRequest, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        updates = []
        params = []
        
        if request.name is not None:
            updates.append("name = ?")
            params.append(request.name)
        if request.phone is not None:
            updates.append("phone = ?")
            params.append(request.phone)
        if request.address is not None:
            updates.append("address = ?")
            params.append(request.address)
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        
        if updates:
            query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
            params.append(user_id)
            conn.execute(query, params)
            conn.commit()
        
        user = conn.execute(
            "SELECT id, email, name, role, phone, address, profile_image FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        
        return {"success": True, "user": dict(user), "message": "Profile updated successfully"}

@app.post("/auth/change-password")
async def change_password(request: ChangePasswordRequest, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        
        if not user or not verify_password(request.old_password, user["password_hash"]):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Current password is incorrect"}
            )
        
        new_password_hash = hash_password(request.new_password)
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_password_hash, user_id)
        )
        conn.commit()
    
    return {"success": True, "message": "Password changed successfully"}

# ============================================
# PROFILE IMAGE ENDPOINTS
# ============================================

UPLOAD_DIR = "uploads/profiles"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/users/profile/image")
async def upload_profile_image(file: UploadFile = File(...), user_id: str = Depends(verify_token)):
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    contents = await file.read()
    file_size = len(contents)
    
    if file_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB")
    
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    filename = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{file_extension}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    with open(filepath, "wb") as buffer:
        buffer.write(contents)
    
    image_url = f"/uploads/profiles/{filename}"
    
    with get_db() as conn:
        conn.execute("UPDATE users SET profile_image = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (image_url, user_id))
        conn.commit()
    
    return {
        "success": True,
        "profile_image": image_url,
        "message": "Profile image uploaded successfully"
    }

@app.delete("/users/profile/image")
async def delete_profile_image(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        user = conn.execute("SELECT profile_image FROM users WHERE id = ?", (user_id,)).fetchone()
        
        if user and user['profile_image']:
            filepath = os.path.join(UPLOAD_DIR, os.path.basename(user['profile_image']))
            if os.path.exists(filepath):
                os.remove(filepath)
        
        conn.execute("UPDATE users SET profile_image = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
        conn.commit()
    
    return {"success": True, "message": "Profile image deleted successfully"}

# ============================================
# SKIN ANALYSIS ENDPOINT
# ============================================

@app.post("/analyze")
async def analyze_skin(file: UploadFile = File(...), user_id: str = Depends(verify_token)):
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    try:
        contents = await file.read()
        analysis = analyze_with_consistency(contents)
        
        skin_type = analysis.get("skin_type", "normal")
        confidence = analysis.get("confidence", 0.75)
        method = analysis.get("method", "AI Analysis")
        
        skin_data = SKIN_CARE_DATA.get(skin_type, SKIN_CARE_DATA["normal"])
        
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
            "analysis_id": analysis_id,
            "skin_type": skin_type,
            "skin_name": skin_data["name"],
            "confidence": confidence,
            "characteristics": skin_data["characteristics"],
            "recommendations": skin_data["recommendations"],
            "recommended_oils": skin_data["oils"],
            "key_ingredients": skin_data.get("ingredients", []),
            "method": method,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/analyses")
async def get_user_analyses(limit: int = 10, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        analyses = conn.execute(
            """SELECT id, skin_type, skin_name, confidence, method, created_at 
               FROM analyses WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit)
        ).fetchall()
        
        return {"success": True, "analyses": [dict(a) for a in analyses]}

@app.get("/analyses/{analysis_id}")
async def get_analysis_detail(analysis_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        analysis = conn.execute(
            """SELECT * FROM analyses WHERE id = ? AND user_id = ?""",
            (analysis_id, user_id)
        ).fetchone()
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        result = dict(analysis)
        if result.get("characteristics"):
            result["characteristics"] = result["characteristics"].split("|")
        if result.get("recommendations"):
            result["recommendations"] = result["recommendations"].split("|")
        if result.get("recommended_oils"):
            result["recommended_oils"] = result["recommended_oils"].split("|")
        
        return {"success": True, "analysis": result}

@app.get("/users/stats")
async def get_user_stats(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        analyses = conn.execute(
            "SELECT skin_type, confidence, created_at FROM analyses WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        
        if not analyses:
            return {
                "success": True,
                "total_analyses": 0,
                "current_skin_type": None,
                "skin_health_score": 85,
                "skin_type_trends": {}
            }
        
        skin_type_counts = {}
        for a in analyses:
            skin_type_counts[a["skin_type"]] = skin_type_counts.get(a["skin_type"], 0) + 1
        
        latest = analyses[0]
        scores = {"normal": 92, "combination": 82, "dry": 78, "oily": 75, "sensitive": 70}
        base_score = scores.get(latest["skin_type"], 85)
        skin_health_score = int(base_score * (latest["confidence"] * 0.3 + 0.7))
        
        return {
            "success": True,
            "total_analyses": len(analyses),
            "current_skin_type": latest["skin_type"],
            "skin_health_score": skin_health_score,
            "skin_type_trends": skin_type_counts,
            "average_confidence": sum(a["confidence"] for a in analyses) / len(analyses)
        }

# ============================================
# WEATHER ENDPOINTS (PAN-AFRICAN)
# ============================================

@app.get("/weather/{lat}/{lon}")
async def get_weather(lat: float, lon: float, skin_type: str = "normal", user_id: str = Depends(verify_token)):
    weather = get_dynamic_weather(lat, lon)
    sunscreen = get_sunscreen_recommendation(weather.get("uv_index", 5), skin_type)
    
    uv = weather.get("uv_index", 5)
    if uv >= 8:
        uv_level, advice = "Extreme", "Seek shade and wear SPF 50+. Avoid direct sun between 11 AM - 4 PM."
    elif uv >= 5:
        uv_level, advice = "High", "Wear a hat and apply SPF 30+. Reapply every 2 hours."
    else:
        uv_level, advice = "Moderate", "UV is safe. Wear light sunscreen if outdoors for long periods."
    
    return {
        "success": True,
        "weather": {
            "uv_index": weather["uv_index"],
            "uv_level": uv_level,
            "advice": advice,
            "temperature": weather["temperature"],
            "humidity": weather["humidity"],
            "condition": weather["condition"],
            "city": weather["city"]
        },
        "sunscreen": sunscreen
    }

@app.get("/location/{lat}/{lon}")
async def get_location(lat: float, lon: float):
    weather = get_dynamic_weather(lat, lon)
    return {"success": True, "city": weather["city"], "latitude": lat, "longitude": lon}

@app.get("/sunscreen/{uv_index}")
async def get_sunscreen_recommendation_endpoint(uv_index: float, skin_type: str = "normal"):
    return {"success": True, **get_sunscreen_recommendation(uv_index, skin_type)}

# ============================================
# CHAT ENDPOINT (BILINGUAL, LESS RESTRICTIVE)
# ============================================

@app.post("/chat")
async def chat_endpoint(request: ChatRequest, user_id: str = Depends(verify_token)):
    if not request.message or not request.message.strip():
        language = detect_language(request.message) if request.message else "english"
        if language == "swahili":
            return {"success": False, "response": "Tafadhali andika swali lako."}
        else:
            return {"success": False, "response": "Please write your question."}
    
    # Check if message is skin-related
    is_related, confidence, language = is_skin_related(request.message)
    
    if not is_related:
        # Return short, natural response in the same language
        return {
            "success": True,
            "response": get_off_topic_response(request.message),
            "is_filtered": True,
            "language": language
        }
    
    # Get user context
    with get_db() as conn:
        latest_analysis = conn.execute(
            "SELECT skin_type FROM analyses WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        
        user = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
    
    # Natural system context - not too restrictive
    system_context = """You are a skincare expert. Give detailed, natural advice about skincare.

You can respond at appropriate length. Give examples, reasons, and practical tips.

For UV questions, discuss sun effects on skin and sunscreen importance.

Be natural and direct. Don't repeat yourself unnecessarily.

Respond in the same language as the user (Swahili or English)."""
    
    if latest_analysis:
        skin_type_map = {
            "dry": "dry",
            "oily": "oily", 
            "combination": "combination",
            "sensitive": "sensitive",
            "normal": "normal"
        }
        skin_name = skin_type_map.get(latest_analysis['skin_type'], latest_analysis['skin_type'])
        
        if language == "swahili":
            system_context += f"\n\nThe user has {skin_name} skin type. Provide advice tailored to this skin type."
        else:
            system_context += f"\n\nThe user has {skin_name} skin type. Provide advice tailored to this skin type."
    
    if user and user['name']:
        if language == "swahili":
            system_context += f"\n\nThe user's name is {user['name']}."
        else:
            system_context += f"\n\nThe user's name is {user['name']}."
    
    # Get AI response with higher limits
    result = await ChatService.get_response(
        user_message=request.message,
        system_context=system_context,
        conversation_history=request.conversation_history,
        max_tokens=request.max_tokens or 600,
        temperature=request.temperature or 0.7
    )
    
    # Save to database
    if result.get("success"):
        with get_db() as conn:
            chat_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO chat_history (id, user_id, user_message, assistant_response, provider, skin_context) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chat_id, user_id, request.message, result["response"], result.get("provider"), 
                 latest_analysis["skin_type"] if latest_analysis else None)
            )
            conn.commit()
    
    # Ensure response exists
    if not result.get("response"):
        result["response"] = get_skincare_fallback_response(request.message)
    
    return result

@app.get("/chat/history")
async def get_chat_history(limit: int = 50, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        history = conn.execute(
            """SELECT id, user_message, assistant_response, provider, created_at 
               FROM chat_history 
               WHERE user_id = ? 
               ORDER BY created_at ASC 
               LIMIT ?""",
            (user_id, limit)
        ).fetchall()
        
        # Format for chat display
        messages = []
        for h in history:
            messages.append({"role": "user", "content": h["user_message"], "timestamp": h["created_at"]})
            messages.append({"role": "assistant", "content": h["assistant_response"], "timestamp": h["created_at"]})
        
        return {
            "success": True,
            "messages": messages,
            "total": len(history)
        }

@app.delete("/chat/history")
async def clear_chat_history(user_id: str = Depends(verify_token)):
    with get_db() as conn:
        conn.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
        conn.commit()
    
    return {"success": True, "message": "Chat history cleared successfully"}

@app.delete("/chat/history/{message_id}")
async def delete_chat_message(message_id: str, user_id: str = Depends(verify_token)):
    with get_db() as conn:
        chat = conn.execute(
            "SELECT id FROM chat_history WHERE id = ? AND user_id = ?",
            (message_id, user_id)
        ).fetchone()
        
        if not chat:
            raise HTTPException(status_code=404, detail="Chat message not found")
        
        conn.execute("DELETE FROM chat_history WHERE id = ?", (message_id,))
        conn.commit()
    
    return {"success": True, "message": "Chat message deleted successfully"}

@app.post("/chat/check-topic")
async def check_topic_relevance(request: ChatRequest, user_id: str = Depends(verify_token)):
    """Check if a question is skin-related before sending to AI"""
    is_related, confidence, language = is_skin_related(request.message)
    
    if is_related:
        if language == "swahili":
            return {
                "success": True,
                "is_relevant": True,
                "message": "Swali linalohusiana na ngozi. Ruhusiwa.",
                "confidence": confidence
            }
        else:
            return {
                "success": True,
                "is_relevant": True,
                "message": "Question is skin-related. Allowed.",
                "confidence": confidence
            }
    else:
        if language == "swahili":
            return {
                "success": True,
                "is_relevant": False,
                "message": "Swali haliuhusiani na ngozi. Tafadhali uliza kuhusu utunzaji wa ngozi.",
                "suggestions": [
                    "Nina acne kwenye uso, nifanye nini?",
                    "Ni sunscreen gani inafaa kwa ngozi yangu?",
                    "Je, ngozi yangu kavu inahitaji moisturizer mara ngapi?",
                    "Nina matangazo meusi, ni bidhaa gani napaswa kutumia?"
                ]
            }
        else:
            return {
                "success": True,
                "is_relevant": False,
                "message": "Your question is not related to skincare. Please ask about skincare instead.",
                "suggestions": [
                    "I have acne on my face, what should I do?",
                    "Which sunscreen is best for my skin?",
                    "How often should I moisturize dry skin?",
                    "I have dark spots, what products should I use?"
                ]
            }

# ============================================
# PRODUCT ENDPOINTS
# ============================================

@app.get("/products")
async def get_products(
    category: Optional[str] = None,
    skin_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    search: Optional[str] = None,
    sort_by: str = "newest",
    limit: int = 20,
    offset: int = 0
):
    with get_db() as conn:
        query = """
            SELECT p.*, s.name as store_name, s.logo_url as store_logo
            FROM products p
            JOIN stores s ON p.store_id = s.id
            WHERE p.is_approved = 1 AND p.is_active = 1
        """
        params = []
        
        if category and category != "all":
            query += " AND p.category = ?"
            params.append(category)
        if skin_type and skin_type != "all":
            query += " AND p.skin_type = ?"
            params.append(skin_type)
        if min_price is not None:
            query += " AND p.price >= ?"
            params.append(min_price)
        if max_price is not None:
            query += " AND p.price <= ?"
            params.append(max_price)
        if search:
            query += " AND (p.name LIKE ? OR p.description LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        
        sort_map = {
            "newest": "p.created_at DESC",
            "price_low": "p.price ASC",
            "price_high": "p.price DESC",
            "popular": "p.sales_count DESC",
            "rating": "p.rating DESC"
        }
        query += f" ORDER BY {sort_map.get(sort_by, 'p.created_at DESC')} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        products = conn.execute(query, params).fetchall()
        
        total = conn.execute(
            "SELECT COUNT(*) as count FROM products WHERE is_approved = 1 AND is_active = 1",
            []
        ).fetchone()["count"]
        
        return {
            "success": True,
            "products": [dict(p) for p in products],
            "total": total,
            "limit": limit,
            "offset": offset
        }

@app.get("/products/categories")
async def get_categories():
    return {
        "success": True,
        "categories": [
            {"id": "cleanser", "name": "Cleanser", "icon": "🧼", "description": "Face washes and cleansers"},
            {"id": "moisturizer", "name": "Moisturizer", "icon": "💧", "description": "Creams and lotions"},
            {"id": "sunscreen", "name": "Sunscreen", "icon": "☀️", "description": "SPF protection"},
            {"id": "serum", "name": "Serum", "icon": "✨", "description": "Concentrated treatments"},
            {"id": "oil", "name": "Face Oil", "icon": "🌿", "description": "Natural oils"},
            {"id": "mask", "name": "Mask", "icon": "🎭", "description": "Face masks"},
            {"id": "toner", "name": "Toner", "icon": "💦", "description": "Toning lotions"},
            {"id": "exfoliator", "name": "Exfoliator", "icon": "🔬", "description": "Scrubs and exfoliants"},
            {"id": "eye_cream", "name": "Eye Cream", "icon": "👁️", "description": "Eye area care"},
            {"id": "lip_care", "name": "Lip Care", "icon": "💋", "description": "Lip balms and treatments"}
        ]
    }

@app.get("/products/recommend")
async def recommend_products(lat: float, lon: float, skin_type: str):
    """Recommend products based on weather and skin type"""
    weather = get_dynamic_weather(lat, lon)
    
    with get_db() as conn:
        products = conn.execute(
            """SELECT * FROM products 
               WHERE is_approved = 1 AND is_active = 1 
               AND (skin_type = ? OR skin_type = 'all')
               ORDER BY rating DESC, sales_count DESC
               LIMIT 10""",
            (skin_type,)
        ).fetchall()
        
        return {
            "success": True,
            "products": [dict(p) for p in products],
            "weather_context": {
                "uv_index": weather["uv_index"],
                "temperature": weather["temperature"],
                "condition": weather["condition"]
            }
        }

@app.get("/products/{product_id}")
async def get_product_detail(product_id: str):
    with get_db() as conn:
        conn.execute("UPDATE products SET views = views + 1 WHERE id = ?", (product_id,))
        conn.commit()
        
        product = conn.execute(
            """SELECT p.*, s.name as store_name, s.address as store_address, s.rating as store_rating
               FROM products p
               JOIN stores s ON p.store_id = s.id
               WHERE p.id = ? AND p.is_approved = 1""",
            (product_id,)
        ).fetchone()
        
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        reviews = conn.execute(
            """SELECT r.*, u.name as user_name, u.profile_image as user_image
               FROM reviews r
               JOIN users u ON r.user_id = u.id
               WHERE r.product_id = ?
               ORDER BY r.created_at DESC LIMIT 10""",
            (product_id,)
        ).fetchall()
        
        related = conn.execute(
            """SELECT id, name, price, images, rating
               FROM products
               WHERE skin_type = ? AND id != ? AND is_approved = 1
               LIMIT 5""",
            (product["skin_type"], product_id)
        ).fetchall()
        
        return {
            "success": True,
            "product": dict(product),
            "reviews": [dict(r) for r in reviews],
            "related_products": [dict(r) for r in related]
        }

# ============================================
# VENDOR ENDPOINTS (Continued in next message due to length)
# ============================================

# ... (Vendor endpoints remain the same as previous version)

# ============================================
# STATIC FILES (for local uploads)
# ============================================

if os.path.exists("uploads"):
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ============================================
# RUN SERVER
# ============================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    print("=" * 70)
    print("🌟 SKINGLOW AI PAN-AFRICAN MASTER PRODUCTION v5.2")
    print("=" * 70)
    print(f"📍 Host: {host}")
    print(f"🔌 Port: {port}")
    print(f"🤖 MediaPipe: {'✅ Available' if MEDIAPIPE_AVAILABLE else '❌ Not available'}")
    print(f"🌍 Weather API: {'✅ Configured' if WEATHER_API_KEY else '❌ Not configured'}")
    print(f"🤖 OpenAI: {'✅ Configured' if OPENAI_API_KEY else '❌ Not configured'}")
    print(f"🤖 Gemini: {'✅ Configured' if GEMINI_API_KEY else '❌ Not configured'}")
    print(f"💾 Database: SQLite with WAL mode")
    print(f"🌍 Region: Pan-African")
    print(f"💬 Chat Mode: Bilingual - Skincare Focused")
    print("=" * 70)
    print("🚀 Server is ready for production deployment!")
    print("=" * 70)
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
        proxy_headers=True,
        forwarded_allow_ips="*"
    )
