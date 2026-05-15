# ============================================
# SKINGLOW AI - PAN-AFRICAN MASTER PRODUCTION BACKEND v5.2
# Full Integration: Analysis, Marketplace, AI Chat (Bilingual) & Pan-African Weather
# Optimized by Ashraf Hamis Athumani (Wawanah)
# ============================================

import json
from fastapi import Form 
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
import numpy as np
from collections import Counter
import logging
import time
from functools import wraps
import re
import shutil
from pathlib import Path

# Add parent directory to path for database module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import database module
from database import get_db, init_db, migrate_data, hash_password, verify_password

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
# LIFESPAN MANAGER
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting SkinGlow AI Pan-African Production Server v5.2...")
    logger.info(f"MediaPipe: {'Available' if MEDIAPIPE_AVAILABLE else 'Not available'}")
    logger.info(f"OpenAI: {'Configured' if OPENAI_API_KEY else 'Not configured'}")
    logger.info(f"Gemini: {'Configured' if GEMINI_API_KEY else 'Not configured'}")
    logger.info(f"Weather API: {'Configured' if WEATHER_API_KEY else 'Not configured'}")
    
    # Initialize database
    await init_db()
    await migrate_data()
    
    yield
    # Shutdown
    logger.info("👋 Shutting down SkinGlow AI Server...")

# ============================================
# INITIALIZE FASTAPI
# ============================================

app = FastAPI(
    title="SkinGlow AI Master Production",
    description="Professional Skin Analysis and E-commerce API - Pan-African",
    version="5.2.0",
    lifespan=lifespan
)

# CORS Configuration for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:8000,https://skinglow.com').split(','),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
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
            async with get_db() as conn:
                if hasattr(conn, 'fetchrow'):
                    user = await conn.fetchrow("SELECT role FROM users WHERE id = $1", user_id)
                else:
                    cursor = await conn.execute("SELECT role FROM users WHERE id = ?", (user_id,))
                    user = await cursor.fetchone()
                
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
    max_tokens: Optional[int] = 800
    temperature: Optional[float] = 0.85

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
# LANGUAGE DETECTION
# ============================================

def detect_language(text: str) -> str:
    """Detect if text is primarily English or Swahili"""
    text_lower = text.lower()
    
    swahili_words = ['na', 'ya', 'wa', 'kwa', 'ni', 'cha', 'vya', 'za', 'la', 'ma', 
                     'nina', 'una', 'ana', 'tuna', 'wana', 'nilikuwa', 'alikuwa',
                     'hapa', 'kule', 'huko', 'sasa', 'basi', 'kama', 'ilikuwa', 'habari']
    
    english_words = ['the', 'and', 'of', 'to', 'in', 'for', 'is', 'on', 'that', 'with',
                     'this', 'was', 'are', 'as', 'at', 'be', 'from', 'has', 'have',
                     'hello', 'hi', 'how', 'are', 'you']
    
    swahili_count = sum(1 for word in swahili_words if word in text_lower)
    english_count = sum(1 for word in english_words if word in text_lower)
    
    if swahili_count > english_count:
        return "swahili"
    else:
        return "english"

# ============================================
# NATURAL FALLBACK RESPONSES
# ============================================

def get_natural_fallback_response(message: str) -> str:
    """Return natural, friendly fallback responses"""
    message_lower = message.lower()
    language = detect_language(message)
    
    # Greetings in Swahili
    if any(word in message_lower for word in ["habari", "hujambo", "sasa", "mambo", "vipi", "poa", "nzuri"]):
        if language == "swahili":
            return "Habari yako! Niko vizuri, asante. Je, ninaweza kukusaidia vipi kuhusu ngozi yako leo?"
        else:
            return "Hello! I'm doing well, thank you. How can I help with your skin today?"
    
    # Greetings in English
    elif any(word in message_lower for word in ["hello", "hi", "hey", "good morning", "good afternoon", "good evening", "how are you", "how's it going"]):
        if language == "swahili":
            return "Habari! Karibu. Niko vizuri, asante. Una swali kuhusu utunzaji wa ngozi?"
        else:
            return "Hello! Welcome. I'm doing well, thanks. Do you have a skincare question?"
    
    # Thank you
    elif any(word in message_lower for word in ["asante", "thank", "thanks", "shukran"]):
        if language == "swahili":
            return "Karibu sana! Niko hapa kukusaidia wakati wote. Una swali jingine?"
        else:
            return "You're very welcome! I'm here to help anytime. Any other questions?"
    
    # Goodbye
    elif any(word in message_lower for word in ["kwaheri", "bye", "goodbye", "see you", "later", "tutaonana"]):
        if language == "swahili":
            return "Kwaheri! Kumbuka kutunza ngozi yako kila siku. Tutaonana tena!"
        else:
            return "Goodbye! Remember to take care of your skin daily. See you next time!"
    
    # Help/What can you do
    elif any(word in message_lower for word in ["help", "saidia", "what can you do", "unaweza kufanya nini", "what do you do"]):
        if language == "swahili":
            return """Ninaweza kukusaidia kuhusu:
• Aina za ngozi (kavu, mafuta, combination, nyeti)
• Matatizo ya ngozi (acne, matangazo, kasoro, kukauka)
• Bidhaa za ngozi na jinsi ya kuzitumia
• Kinga ya jua na SPF
• Utaratibu wa kutunza ngozi asubuhi na jioni

Una swali gani leo?"""
        else:
            return """I can help you with:
• Skin types (dry, oily, combination, sensitive)
• Skin problems (acne, dark spots, wrinkles, dryness)
• Skincare products and how to use them
• Sun protection and SPF
• Morning and evening skincare routines

What would you like to know today?"""
    
    # Name
    elif any(word in message_lower for word in ["what is your name", "who are you", "jina lako nani", "wewe ni nani"]):
        if language == "swahili":
            return "Jina langu ni SkinSight AI! Mimi ni msaidizi wako wa ngozi. Niko hapa kukusaidia kuhusu utunzaji wa ngozi. Unaweza kuniuliza lolote kuhusu ngozi yako!"
        else:
            return "My name is SkinSight AI! I'm your skincare assistant. I'm here to help with all your skincare questions. What can I help you with today?"
    
    # Acne
    elif any(word in message_lower for word in ["acne", "chunusi", "pimple", "breakout", "spots"]):
        if language == "swahili":
            return """Kwa acne (chunusi), napendekeza:

1️⃣ Tumia cleanser yenye salicylic acid au benzoyl peroxide mara 1-2 kwa siku
2️⃣ Usiguse au kubana chunusi - hii inaweza kusababisha makovu
3️⃣ Tumia moisturizer lightweight isiyo na mafuta
4️⃣ Omba sunscreen SPF 30+ kila siku - jua inazidisha acne
5️⃣ Epuka vyakula vya mafuta mengi na sukari ikiwezekana

Je, unataka nikupe ushauri wa bidhaa maalum?"""
        else:
            return """For acne, I recommend:

1️⃣ Use a cleanser with salicylic acid or benzoyl peroxide 1-2 times daily
2️⃣ Don't touch or pop pimples - this can cause scarring
3️⃣ Use a lightweight, oil-free moisturizer
4️⃣ Apply SPF 30+ sunscreen daily - sun makes acne worse
5️⃣ Avoid oily foods and excess sugar if possible

Would you like specific product recommendations?"""
    
    # Dry skin
    elif any(word in message_lower for word in ["dry", "kavu", "flaky", "tight", "rough"]):
        if language == "swahili":
            return """Kwa ngozi kavu, napendekeza:

1️⃣ Tumia hydrating cleanser isiyo na sulfate
2️⃣ Omba hyaluronic acid serum mara baada ya kuosha uso
3️⃣ Tumia rich moisturizer yenye ceramides au shea butter
4️⃣ Ongeza facial oil kama argan au jojoba usiku
5️⃣ Kunywa maji mengi (lita 2-3 kwa siku)

Unahitaji nikupe maelezo zaidi?"""
        else:
            return """For dry skin, I recommend:

1️⃣ Use a hydrating, sulfate-free cleanser
2️⃣ Apply hyaluronic acid serum right after washing
3️⃣ Use a rich moisturizer with ceramides or shea butter
4️⃣ Add a facial oil like argan or jojoba at night
5️⃣ Drink plenty of water (2-3 liters daily)

Would you like more details?"""
    
    # Oily skin
    elif any(word in message_lower for word in ["oily", "mafuta", "greasy", "shine", "shiny"]):
        if language == "swahili":
            return """Kwa ngozi yenye mafuta:

1️⃣ Tumia foaming au gel cleanser mara mbili kwa siku
2️⃣ Omba niacinamide serum (inasaidia kudhibiti mafuta)
3️⃣ Tumia gel moisturizer isiyo na mafuta
4️⃣ Exfoliate mara 2 kwa wiki kwa salicylic acid
5️⃣ Tumia clay mask mara moja kwa wiki

Je, ungependa maelezo zaidi?"""
        else:
            return """For oily skin:

1️⃣ Use a foaming or gel cleanser twice daily
2️⃣ Apply niacinamide serum (helps control oil)
3️⃣ Use an oil-free gel moisturizer
4️⃣ Exfoliate twice weekly with salicylic acid
5️⃣ Use a clay mask once weekly

Would you like more details?"""
    
    # Sunscreen/UV
    elif any(word in message_lower for word in ["sunscreen", "spf", "jua", "sun", "uv", "protection", "kinga"]):
        if language == "swahili":
            return """Kuhusu kinga ya jua:

🌞 Tumia SPF 30+ kila siku, hata ukiwa ndani ya nyumba
🌞 Omba dakika 15-20 kabla ya kwenda nje
🌞 Tumia kiasi cha kutosha (1/2 kijiko kwa uso na shingo)
🌞 Rudia kila baada ya masaa 2-3 ukiwa nje
🌞 Chagua sunscreen inayofaa aina ya ngozi yako

Unahitaji msaada wa kuchagua sunscreen?"""
        else:
            return """About sun protection:

🌞 Use SPF 30+ daily, even when indoors
🌞 Apply 15-20 minutes before going outside
🌞 Use enough (1/2 teaspoon for face and neck)
🌞 Reapply every 2-3 hours when outside
🌞 Choose sunscreen suitable for your skin type

Need help choosing a sunscreen?"""
    
    # Default friendly response
    else:
        if language == "swahili":
            return """Niko hapa kukusaidia na ngozi yako! 😊

Unaweza kuniuliza kuhusu:
• Aina ya ngozi yako (kavu, mafuta, combination, nyeti)
• Matatizo unayokabiliana nayo (acne, matangazo, kasoro)
• Bidhaa unazotumia au unataka kujua
• Utaratibu wa kutunza ngozi asubuhi na jioni

Niambie zaidi, nikusaidie vizuri!"""
        else:
            return """I'm here to help with your skin! 😊

You can ask me about:
• Your skin type (dry, oily, combination, sensitive)
• Problems you're facing (acne, dark spots, wrinkles)
• Products you use or want to learn about
• Morning and evening skincare routines

Tell me more so I can help you better!"""

# ============================================
# CHAT SERVICE (Natural & Friendly)
# ============================================

class ChatService:
    @staticmethod
    async def get_openai_response(
        user_message: str,
        system_context: str,
        conversation_history: Optional[List[Dict]] = None,
        max_tokens: int = 800,
        temperature: float = 0.85
    ) -> Dict[str, Any]:
        if not OPENAI_API_KEY:
            return {
                "success": True,
                "response": get_natural_fallback_response(user_message),
                "provider": "fallback"
            }
        
        try:
            import openai
            openai.api_key = OPENAI_API_KEY
            
            system_prompt = """You are SkinSight AI, a friendly and knowledgeable skincare assistant.

PERSONALITY:
- Warm, conversational, and approachable
- You can respond to greetings, small talk, and casual conversation naturally
- You don't need to announce yourself every time - just be natural
- You remember context from previous messages

WHAT YOU DO:
- Help with skincare routines, products, and skin problems
- Answer questions about acne, dry skin, oily skin, aging, hyperpigmentation, etc.
- Give advice on sun protection and UV
- Recommend products based on skin types and concerns

WHAT YOU DON'T DO:
- Give medical diagnoses (refer to dermatologists for serious issues)
- Answer off-topic questions about politics, celebrities, sports, finance, etc.

GUIDELINES:
- Respond naturally - if someone says "Habari", reply with greeting like "Habari yako! Niko vizuri, asante. Una swali kuhusu ngozi yako?"
- If someone thanks you, say "Karibu!" or "You're welcome!"
- If someone asks "What can you help with?", list your skincare expertise
- Keep responses helpful but not overly long
- Use the same language as the user (English or Swahili)

Remember: Be a helpful friend who knows about skincare, not a robot repeating the same phrases."""
            
            messages = [{"role": "system", "content": system_prompt}]
            
            if conversation_history:
                messages.extend(conversation_history[-15:])
            
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
                "response": get_natural_fallback_response(user_message),
                "provider": "fallback"
            }
    
    @staticmethod
    async def get_gemini_response(
        user_message: str,
        system_context: str,
        conversation_history: Optional[List[Dict]] = None,
        max_tokens: int = 800,
        temperature: float = 0.85
    ) -> Dict[str, Any]:
        if not GEMINI_API_KEY:
            return {
                "success": True,
                "response": get_natural_fallback_response(user_message),
                "provider": "fallback"
            }
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            
            model = genai.GenerativeModel('gemini-pro')
            
            system_prompt = """You are SkinSight AI, a friendly skincare assistant.

Be warm and conversational. Respond to greetings naturally. Give helpful skincare advice.

Keep responses natural and not robotic. Use the same language as the user."""
            
            full_prompt = f"{system_prompt}\n\n{system_context}\n\n"
            
            if conversation_history:
                for msg in conversation_history[-15:]:
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
                "response": get_natural_fallback_response(user_message),
                "provider": "fallback"
            }
    
    @classmethod
    async def get_response(cls, user_message: str, system_context: str = None, **kwargs) -> Dict[str, Any]:
        default_context = """You are a friendly skincare assistant named SkinSight AI.

Be warm and conversational. Respond to greetings naturally. Give helpful skincare advice when asked.

Keep responses natural. Don't repeat yourself. Use the same language as the user."""
        
        context = system_context or default_context
        
        if AI_PROVIDER == "openai" and OPENAI_API_KEY:
            return await cls.get_openai_response(user_message, context, **kwargs)
        elif AI_PROVIDER == "gemini" and GEMINI_API_KEY:
            return await cls.get_gemini_response(user_message, context, **kwargs)
        else:
            return {
                "success": True,
                "response": get_natural_fallback_response(user_message),
                "provider": "fallback"
            }

# ============================================
# WEATHER CONFIGURATION
# ============================================

WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')

def get_dynamic_weather(lat: float, lon: float):
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
            "city": resp.get('name', 'Your City')
        }
    except:
        return {
            "uv_index": 5.0,
            "temperature": 25,
            "humidity": 60,
            "condition": "clear",
            "city": "Your City"
        }

def get_sunscreen_recommendation(uv_index: float, skin_type: str) -> Dict:
    if uv_index <= 2:
        level, spf, advice = "Low", 15, "Minimal UV risk."
    elif uv_index <= 5:
        level, spf, advice = "Moderate", 30, "Sunscreen recommended."
    elif uv_index <= 7:
        level, spf, advice = "High", 50, "Strong protection needed."
    else:
        level, spf, advice = "Extreme", 50, "Maximum protection required."
    
    skin_advice = {
        'dry': "Hydrating sunscreen",
        'oily': "Oil-free sunscreen",
        'combination': "Lightweight sunscreen",
        'sensitive': "Mineral sunscreen",
        'normal': "Broad-spectrum sunscreen"
    }
    
    return {
        "uv_index": uv_index,
        "uv_level": level,
        "advice": advice,
        "recommended_spf": spf,
        "reapplication_hours": 2 if uv_index > 5 else 4,
        "skin_advice": skin_advice.get(skin_type, skin_advice['normal'])
    }

# ============================================
# IMAGE PROCESSING
# ============================================

def standardize_image_lighting(image_bytes: bytes) -> np.ndarray:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        image = image.resize((500, 500), Image.Resampling.LANCZOS)
        return np.array(image)
    except Exception as e:
        logger.error(f"Image error: {e}")
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        return np.array(image.resize((500, 500)))

# ============================================
# SKIN ANALYSIS FUNCTIONS (IMPROVED - NO BIAS)
# ============================================

SKIN_CARE_DATA = {
    "dry": {
        "name": "Dry Skin",
        "characteristics": ["Lacks moisture", "May feel tight or flaky"],
        "recommendations": ["Use hydrating cleanser", "Apply hyaluronic acid", "Use rich moisturizer"],
        "oils": ["Argan Oil", "Jojoba Oil"],
        "ingredients": ["Hyaluronic Acid", "Ceramides", "Shea Butter"]
    },
    "oily": {
        "name": "Oily Skin",
        "characteristics": ["Excess sebum", "Shiny appearance"],
        "recommendations": ["Use foaming cleanser", "Apply niacinamide", "Use gel moisturizer"],
        "oils": ["Grapeseed Oil", "Tea Tree Oil"],
        "ingredients": ["Niacinamide", "Salicylic Acid", "Zinc"]
    },
    "combination": {
        "name": "Combination Skin",
        "characteristics": ["Oily in T-zone", "Normal or dry on cheeks"],
        "recommendations": ["Use balancing cleanser", "Lightweight moisturizer", "Exfoliate T-zone"],
        "oils": ["Jojoba Oil", "Squalane Oil"],
        "ingredients": ["Niacinamide", "Hyaluronic Acid", "Green Tea"]
    },
    "sensitive": {
        "name": "Sensitive Skin",
        "characteristics": ["Easily irritated", "Prone to redness"],
        "recommendations": ["Use gentle cleanser", "Calming ingredients", "Minimal products"],
        "oils": ["Chamomile Oil", "Squalane"],
        "ingredients": ["Centella Asiatica", "Aloe Vera", "Panthenol"]
    },
    "normal": {
        "name": "Normal Skin",
        "characteristics": ["Balanced moisture", "Clear complexion"],
        "recommendations": ["Regular cleansing", "Antioxidant serum", "SPF daily"],
        "oils": ["Argan Oil", "Rosehip Oil"],
        "ingredients": ["Vitamin C", "Hyaluronic Acid", "Peptides"]
    }
}

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
    """Improved fallback analysis with multiple metrics - NO BIAS"""
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
        
        # Initialize all scores to 0 - NO DEFAULT BIAS
        scores = {"dry": 0, "oily": 0, "combination": 0, "sensitive": 0, "normal": 0}
        
        # Texture variance scoring
        if texture_var > 3800:
            scores["oily"] += 5
            scores["combination"] += 2
        elif texture_var > 3200:
            scores["oily"] += 4
            scores["combination"] += 3
        elif texture_var > 2600:
            scores["oily"] += 2
            scores["combination"] += 4
        elif texture_var > 2000:
            scores["combination"] += 3
            scores["normal"] += 2
        elif texture_var > 1400:
            scores["normal"] += 3
            scores["combination"] += 1
        elif texture_var > 800:
            scores["dry"] += 2
            scores["normal"] += 2
            scores["sensitive"] += 1
        else:
            scores["dry"] += 4
            scores["sensitive"] += 2
        
        # Brightness scoring
        if avg_brightness > 220:
            scores["dry"] += 4
            scores["sensitive"] += 3
        elif avg_brightness > 190:
            scores["dry"] += 3
            scores["sensitive"] += 2
            scores["normal"] += 1
        elif avg_brightness > 160:
            scores["normal"] += 3
            scores["combination"] += 1
        elif avg_brightness > 130:
            scores["combination"] += 3
            scores["normal"] += 2
        elif avg_brightness > 100:
            scores["combination"] += 2
            scores["oily"] += 2
        elif avg_brightness > 70:
            scores["oily"] += 3
            scores["combination"] += 2
        else:
            scores["oily"] += 4
        
        # Get highest score
        max_score = max(scores.values())
        candidates = [k for k, v in scores.items() if v == max_score]
        
        if len(candidates) > 1:
            if "normal" in candidates:
                if texture_var > 2000:
                    return {"skin_type": "combination", "confidence": 0.72, "method": "Color Analysis"}
                elif texture_var < 1200:
                    return {"skin_type": "dry", "confidence": 0.70, "method": "Color Analysis"}
            
            if "oily" in candidates and "combination" in candidates:
                if texture_var > 3000:
                    return {"skin_type": "oily", "confidence": 0.73, "method": "Color Analysis"}
                else:
                    return {"skin_type": "combination", "confidence": 0.71, "method": "Color Analysis"}
            
            skin_type = candidates[0]
        else:
            skin_type = candidates[0]
        
        sorted_scores = sorted(scores.values(), reverse=True)
        score_spread = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]
        confidence = 0.65 + (score_spread / 20) * 0.25
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
    
    fallback_result = analyze_with_fallback(image_bytes)
    results.append(fallback_result)
    
    skin_types = [r["skin_type"] for r in results]
    confidences = [r["confidence"] for r in results]
    
    counts = Counter(skin_types)
    most_common = counts.most_common(1)[0]
    
    if len(set(skin_types)) == 1 or most_common[1] >= 2:
        avg_confidence = sum(confidences) / len(confidences)
        return {
            "skin_type": most_common[0],
            "confidence": min(0.95, avg_confidence),
            "method": "Consensus Analysis"
        }
    
    try:
        import cv2
        std_img = standardize_image_lighting(image_bytes)
        gray = cv2.cvtColor(std_img, cv2.COLOR_RGB2GRAY)
        texture_var = np.var(gray)
        
        if texture_var > 3500:
            return {"skin_type": "oily", "confidence": 0.72, "method": "Texture Analysis"}
        elif texture_var < 1500:
            return {"skin_type": "dry", "confidence": 0.70, "method": "Texture Analysis"}
        elif 2200 < texture_var < 3200:
            return {"skin_type": "combination", "confidence": 0.68, "method": "Texture Analysis"}
        else:
            return fallback_result
    except:
        return fallback_result

# ============================================
# PROFILE IMAGE CONFIGURATION
# ============================================

UPLOAD_DIR = "uploads/profiles"
os.makedirs(UPLOAD_DIR, exist_ok=True)
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

def create_default_avatar():
    avatar_path = os.path.join(STATIC_DIR, "default-avatar.png")
    if not os.path.exists(avatar_path):
        try:
            from PIL import Image, ImageDraw
            size = 200
            img = Image.new('RGB', (size, size), color='#6C63FF')
            draw = ImageDraw.Draw(img)
            draw.ellipse((40, 40, 160, 160), fill='white')
            draw.ellipse((70, 90, 90, 110), fill='#6C63FF')
            draw.ellipse((110, 90, 130, 110), fill='#6C63FF')
            draw.arc((70, 120, 130, 150), start=0, end=180, fill='#6C63FF', width=5)
            img.save(avatar_path)
            logger.info("✅ Created default avatar")
        except:
            img = Image.new('RGB', (200, 200), color='#6C63FF')
            img.save(avatar_path)

create_default_avatar()

# ============================================
# PROFILE IMAGE ENDPOINTS
# ============================================

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
    
    async with get_db() as conn:
        if hasattr(conn, 'fetchrow'):
            old = await conn.fetchrow("SELECT profile_image FROM users WHERE id = $1", user_id)
        else:
            cursor = await conn.execute("SELECT profile_image FROM users WHERE id = ?", (user_id,))
            old = await cursor.fetchone()
        
        if old and old.get('profile_image'):
            old_path = os.path.join(UPLOAD_DIR, os.path.basename(old['profile_image']))
            if os.path.exists(old_path):
                os.remove(old_path)
    
    filename = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{file_extension}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    with open(filepath, "wb") as buffer:
        buffer.write(contents)
    
    image_path = f"/uploads/profiles/{filename}"
    base_url = os.getenv('BASE_URL', 'https://skinglow-backend-production.up.railway.app')
    full_url = f"{base_url}{image_path}"
    
    async with get_db() as conn:
        if hasattr(conn, 'execute'):
            await conn.execute("UPDATE users SET profile_image = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2", image_path, user_id)
        else:
            await conn.execute("UPDATE users SET profile_image = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", image_path, user_id)
    
    return {"success": True, "profile_image": full_url, "message": "Profile image uploaded successfully"}

@app.get("/users/profile/image")
async def get_profile_image(user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        if hasattr(conn, 'fetchrow'):
            user = await conn.fetchrow("SELECT profile_image FROM users WHERE id = $1", user_id)
        else:
            cursor = await conn.execute("SELECT profile_image FROM users WHERE id = ?", (user_id,))
            user = await cursor.fetchone()
        
        if not user or not user['profile_image']:
            return {"success": True, "profile_image": None}
        
        base_url = os.getenv('BASE_URL', 'https://skinglow-backend-production.up.railway.app')
        if user['profile_image'].startswith('http'):
            image_url = user['profile_image']
        else:
            image_url = f"{base_url}{user['profile_image']}"
        
        return {"success": True, "profile_image": image_url}

@app.delete("/users/profile/image")
async def delete_profile_image(user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        if hasattr(conn, 'fetchrow'):
            user = await conn.fetchrow("SELECT profile_image FROM users WHERE id = $1", user_id)
        else:
            cursor = await conn.execute("SELECT profile_image FROM users WHERE id = ?", (user_id,))
            user = await cursor.fetchone()
        
        if user and user.get('profile_image'):
            filepath = os.path.join(UPLOAD_DIR, os.path.basename(user['profile_image']))
            if os.path.exists(filepath):
                os.remove(filepath)
        
        if hasattr(conn, 'execute'):
            await conn.execute("UPDATE users SET profile_image = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = $1", user_id)
        else:
            await conn.execute("UPDATE users SET profile_image = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?", user_id)
    
    return {"success": True, "message": "Profile image deleted successfully"}

@app.get("/users/{target_user_id}/profile-image")
async def get_other_profile_image(target_user_id: str):
    async with get_db() as conn:
        if hasattr(conn, 'fetchrow'):
            user = await conn.fetchrow("SELECT profile_image FROM users WHERE id = $1", target_user_id)
        else:
            cursor = await conn.execute("SELECT profile_image FROM users WHERE id = ?", (target_user_id,))
            user = await cursor.fetchone()
        
        if not user or not user.get('profile_image'):
            default_path = os.path.join(STATIC_DIR, "default-avatar.png")
            if os.path.exists(default_path):
                return FileResponse(default_path, media_type="image/png")
            else:
                raise HTTPException(status_code=404, detail="No profile image")
        
        filename = os.path.basename(user['profile_image'])
        filepath = os.path.join(UPLOAD_DIR, filename)
        
        if os.path.exists(filepath):
            return FileResponse(filepath, media_type="image/jpeg")
        else:
            default_path = os.path.join(STATIC_DIR, "default-avatar.png")
            if os.path.exists(default_path):
                return FileResponse(default_path, media_type="image/png")
            else:
                raise HTTPException(status_code=404, detail="No profile image")

# ============================================
# HEALTH CHECK
# ============================================

@app.get("/")
async def root():
    return {"status": "healthy", "app": "SkinGlow AI", "version": "5.2.0"}

@app.get("/health")
async def health_check():
    return {"status": "operational", "version": "5.2.0"}

@app.get("/test-db")
async def test_db():
    try:
        async with get_db() as conn:
            if hasattr(conn, 'fetchval'):
                await conn.fetchval("SELECT 1")
            else:
                await conn.execute("SELECT 1")
        return {"success": True, "message": "Database connected"}
    except Exception as e:
        return {"success": False, "message": str(e)}

# ============================================
# AUTH ENDPOINTS
# ============================================

@app.post("/auth/register")
async def register(request: RegisterRequest):
    try:
        async with get_db() as conn:
            if hasattr(conn, 'fetchrow'):
                existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", request.email)
            else:
                cursor = await conn.execute("SELECT id FROM users WHERE email = ?", (request.email,))
                existing = await cursor.fetchone()
            
            if existing:
                return JSONResponse(status_code=400, content={"success": False, "message": "Email already registered"})
            
            user_id = str(uuid.uuid4())
            password_hash = hash_password(request.password)
            is_approved = 1 if request.role == 'customer' else 0
            
            if hasattr(conn, 'execute'):
                await conn.execute(
                    """INSERT INTO users (id, email, password_hash, name, role, is_approved, phone, address, created_at, updated_at) 
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                    user_id, request.email, password_hash, request.name, request.role, is_approved, request.phone, request.address
                )
            else:
                await conn.execute(
                    """INSERT INTO users (id, email, password_hash, name, role, is_approved, phone, address, created_at, updated_at) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                    user_id, request.email, password_hash, request.name, request.role, is_approved, request.phone, request.address
                )
        
        access_token = create_access_token({"sub": request.email, "user_id": user_id, "role": request.role})
        refresh_token = create_refresh_token(user_id)
        
        return {
            "success": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {"id": user_id, "email": request.email, "name": request.name, "role": request.role, "is_approved": is_approved}
        }
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.post("/auth/login")
async def login(request: LoginRequest):
    try:
        async with get_db() as conn:
            if hasattr(conn, 'fetchrow'):
                user = await conn.fetchrow(
                    "SELECT id, email, password_hash, name, role, is_approved, phone, address, profile_image, created_at FROM users WHERE email = $1",
                    request.email
                )
            else:
                cursor = await conn.execute(
                    "SELECT id, email, password_hash, name, role, is_approved, phone, address, profile_image, created_at FROM users WHERE email = ?",
                    (request.email,)
                )
                user = await cursor.fetchone()
            
            if not user or not verify_password(request.password, user["password_hash"]):
                return JSONResponse(status_code=401, content={"success": False, "message": "Invalid email or password"})
            
            if user["role"] == "vendor" and user["is_approved"] == 0:
                return JSONResponse(status_code=403, content={"success": False, "message": "Your vendor account is pending approval"})
            
            if hasattr(conn, 'execute'):
                await conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = $1", user["id"])
            else:
                await conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?", user["id"])
        
        access_token = create_access_token({"sub": user["email"], "user_id": user["id"], "role": user["role"]})
        refresh_token = create_refresh_token(user["id"])
        
        profile_image = user.get("profile_image")
        base_url = os.getenv('BASE_URL', 'https://skinglow-backend-production.up.railway.app')
        if profile_image and not profile_image.startswith('http'):
            profile_image = f"{base_url}{profile_image}"
        
        return {
            "success": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "name": user["name"],
                "role": user["role"],
                "is_approved": user["is_approved"],
                "phone": user["phone"],
                "address": user["address"],
                "profile_image": profile_image,
                "created_at": user["created_at"]
            }
        }
    except Exception as e:
        logger.error(f"Login error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.post("/auth/refresh")
async def refresh_token(request: RefreshTokenRequest):
    try:
        user_id = verify_refresh_token(request.refresh_token)
        async with get_db() as conn:
            if hasattr(conn, 'fetchrow'):
                user = await conn.fetchrow("SELECT id, email, role FROM users WHERE id = $1", user_id)
            else:
                cursor = await conn.execute("SELECT id, email, role FROM users WHERE id = ?", (user_id,))
                user = await cursor.fetchone()
            
            if not user:
                return JSONResponse(status_code=401, content={"success": False, "message": "User not found"})
        
        new_access_token = create_access_token({"sub": user["email"], "user_id": user["id"], "role": user["role"]})
        return {"success": True, "access_token": new_access_token}
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"success": False, "message": e.detail})
    except Exception as e:
        logger.error(f"Refresh token error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.post("/auth/logout")
async def logout(user_id: str = Depends(verify_token)):
    return {"success": True, "message": "Logged out successfully"}

@app.get("/users/me")
async def get_current_user(user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        if hasattr(conn, 'fetchrow'):
            user = await conn.fetchrow(
                """SELECT id, email, name, role, is_approved, created_at, updated_at, 
                          last_login, phone, address, profile_image 
                   FROM users WHERE id = $1""",
                user_id
            )
        else:
            cursor = await conn.execute(
                """SELECT id, email, name, role, is_approved, created_at, updated_at, 
                          last_login, phone, address, profile_image 
                   FROM users WHERE id = ?""",
                (user_id,)
            )
            user = await cursor.fetchone()
        
        if not user:
            return JSONResponse(status_code=404, content={"success": False, "message": "User not found"})
        
        user_dict = dict(user)
        if user_dict.get('profile_image'):
            base_url = os.getenv('BASE_URL', 'https://skinglow-backend-production.up.railway.app')
            if not user_dict['profile_image'].startswith('http'):
                user_dict['profile_image'] = f"{base_url}{user_dict['profile_image']}"
        
        return {"success": True, "user": user_dict}

@app.put("/users/me")
async def update_profile(request: UpdateProfileRequest, user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        updates = []
        params = []
        if request.name is not None:
            if hasattr(conn, 'execute'):
                updates.append(f"name = ${len(params) + 1}")
            else:
                updates.append("name = ?")
            params.append(request.name)
        if request.phone is not None:
            if hasattr(conn, 'execute'):
                updates.append(f"phone = ${len(params) + 1}")
            else:
                updates.append("phone = ?")
            params.append(request.phone)
        if request.address is not None:
            if hasattr(conn, 'execute'):
                updates.append(f"address = ${len(params) + 1}")
            else:
                updates.append("address = ?")
            params.append(request.address)
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            if hasattr(conn, 'execute'):
                query = f"UPDATE users SET {', '.join(updates)} WHERE id = ${len(params) + 1}"
            else:
                query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
            params.append(user_id)
            await conn.execute(query, *params)
        
        if hasattr(conn, 'fetchrow'):
            user = await conn.fetchrow(
                "SELECT id, email, name, role, phone, address, profile_image FROM users WHERE id = $1",
                user_id
            )
        else:
            cursor = await conn.execute(
                "SELECT id, email, name, role, phone, address, profile_image FROM users WHERE id = ?",
                (user_id,)
            )
            user = await cursor.fetchone()
        
        user_dict = dict(user)
        if user_dict.get('profile_image'):
            base_url = os.getenv('BASE_URL', 'https://skinglow-backend-production.up.railway.app')
            if not user_dict['profile_image'].startswith('http'):
                user_dict['profile_image'] = f"{base_url}{user_dict['profile_image']}"
        
        return {"success": True, "user": user_dict, "message": "Profile updated successfully"}

@app.post("/auth/change-password")
async def change_password(request: ChangePasswordRequest, user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        if hasattr(conn, 'fetchrow'):
            user = await conn.fetchrow("SELECT password_hash FROM users WHERE id = $1", user_id)
        else:
            cursor = await conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
            user = await cursor.fetchone()
        
        if not user or not verify_password(request.old_password, user["password_hash"]):
            return JSONResponse(status_code=400, content={"success": False, "message": "Current password is incorrect"})
        
        new_password_hash = hash_password(request.new_password)
        if hasattr(conn, 'execute'):
            await conn.execute("UPDATE users SET password_hash = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2", new_password_hash, user_id)
        else:
            await conn.execute("UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", new_password_hash, user_id)
    
    return {"success": True, "message": "Password changed successfully"}

# ============================================
# SKIN ANALYSIS ENDPOINT (Standard)
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
        async with get_db() as conn:
            if hasattr(conn, 'execute'):
                await conn.execute(
                    """INSERT INTO analyses (id, user_id, skin_type, skin_name, confidence, characteristics, recommendations, recommended_oils, method) 
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                    analysis_id, user_id, skin_type, skin_data["name"], confidence,
                    "|".join(skin_data["characteristics"]),
                    "|".join(skin_data["recommendations"]),
                    "|".join(skin_data["oils"]),
                    method
                )
            else:
                await conn.execute(
                    """INSERT INTO analyses (id, user_id, skin_type, skin_name, confidence, characteristics, recommendations, recommended_oils, method) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    analysis_id, user_id, skin_type, skin_data["name"], confidence,
                    "|".join(skin_data["characteristics"]),
                    "|".join(skin_data["recommendations"]),
                    "|".join(skin_data["oils"]),
                    method
                )
        
        return {
            "success": True,
            "analysis_id": analysis_id,
            "skin_type": skin_type,
            "skin_name": skin_data["name"],
            "confidence": confidence,
            "characteristics": skin_data["characteristics"],
            "recommendations": skin_data["recommendations"],
            "recommended_oils": skin_data["oils"],
            "method": method,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# ============================================
# FIXED: GET ANALYSES ENDPOINT (Proper format for Flutter)
# ============================================

@app.get("/analyses")
async def get_user_analyses(limit: int = 50, user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        if hasattr(conn, 'fetch'):
            analyses = await conn.fetch(
                """SELECT id, skin_type, skin_name, confidence, method, created_at 
                   FROM analyses WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2""",
                user_id, limit
            )
        else:
            cursor = await conn.execute(
                """SELECT id, skin_type, skin_name, confidence, method, created_at 
                   FROM analyses WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit)
            )
            analyses = await cursor.fetchall()
        
        # Convert to list of dictionaries with proper format for Flutter
        result = []
        for a in analyses:
            # Handle datetime conversion for JSON serialization
            created_at = a["created_at"]
            if hasattr(created_at, 'isoformat'):
                created_at_str = created_at.isoformat()
            else:
                created_at_str = str(created_at)
            
            result.append({
                "id": a["id"],
                "skin_type": a["skin_type"],
                "skin_name": a["skin_name"],
                "confidence": float(a["confidence"]) if a["confidence"] else 0.0,
                "method": a["method"] if a["method"] else "AI Analysis",
                "created_at": created_at_str,
                "characteristics": [],  # Empty for history list view
                "recommendations": [],   # Empty for history list view
                "recommended_oils": []   # Empty for history list view
            })
        
        return {
            "success": True,
            "analyses": result,
            "total": len(result)
        }

# ============================================
# HYBRID ANALYSIS ENDPOINT (AI + Questionnaire)
# ============================================

@app.post("/analyze-with-questionnaire")
async def analyze_with_questionnaire(
    file: UploadFile = File(...),
    questionnaire: str = Form(...),
    user_id: str = Depends(verify_token)
):
    """Enhanced analysis that combines AI scan with user questionnaire - HIGHER ACCURACY"""
    import json
    from models.skin_questionnaire import QuestionnaireRequest
    from skin_analyzer import calculate_skin_type_from_questionnaire
    
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    try:
        # Parse questionnaire JSON string
        questionnaire_data = json.loads(questionnaire)
        
        # 1. Perform AI analysis on image
        contents = await file.read()
        ai_analysis = analyze_with_consistency(contents)
        ai_skin_type = ai_analysis.get("skin_type", "normal")
        ai_confidence = ai_analysis.get("confidence", 0.75)
        
        # 2. Calculate skin type from questionnaire
        q_request = QuestionnaireRequest(
            self_assessed_skin_type=questionnaire_data.get("self_assessed_skin_type", "normal"),
            skin_concerns=questionnaire_data.get("skin_concerns", []),
            oiliness=questionnaire_data.get("oiliness", 3),
            dryness=questionnaire_data.get("dryness", 3),
            sensitivity=questionnaire_data.get("sensitivity", 3),
            acne_frequency=questionnaire_data.get("acne_frequency", 3),
            redness=questionnaire_data.get("redness", 3),
            pores_size=questionnaire_data.get("pores_size", 3),
            texture=questionnaire_data.get("texture", 3),
            uses_sunscreen=questionnaire_data.get("uses_sunscreen", False),
            age=questionnaire_data.get("age"),
            gender=questionnaire_data.get("gender"),
            cleanser_type=questionnaire_data.get("cleanser_type"),
            moisturizer_type=questionnaire_data.get("moisturizer_type"),
            water_intake=questionnaire_data.get("water_intake"),
            sleep_hours=questionnaire_data.get("sleep_hours"),
            diet=questionnaire_data.get("diet")
        )
        
        questionnaire_result = calculate_skin_type_from_questionnaire(q_request)
        q_skin_type = questionnaire_result["calculated_skin_type"]
        q_confidence = questionnaire_result["confidence"]
        matching = questionnaire_result["matching_percentage"]
        
        # 3. Combine results with DYNAMIC WEIGHTING
        type_scores = {"dry": 0, "oily": 0, "combination": 0, "sensitive": 0, "normal": 0}
        
        # Dynamic weighting based on AI confidence
        if ai_confidence > 0.80:
            ai_weight = 0.70
            q_weight = 0.30
        elif ai_confidence < 0.65:
            ai_weight = 0.50
            q_weight = 0.50
        else:
            ai_weight = 0.60
            q_weight = 0.40
        
        # Add weighted scores
        type_scores[ai_skin_type] += ai_weight * ai_confidence
        type_scores[q_skin_type] += q_weight * q_confidence
        
        # Agreement bonus
        agreement_bonus = 1.0
        if ai_skin_type == q_skin_type:
            agreement_bonus = 1.15
            type_scores[ai_skin_type] += 0.1
        elif (ai_skin_type == "combination" and q_skin_type in ["normal", "oily"]) or \
             (q_skin_type == "combination" and ai_skin_type in ["normal", "oily"]):
            agreement_bonus = 1.05
        
        # Consider second best from questionnaire
        if questionnaire_result.get("second_score", 0) > 0:
            second_best = sorted(questionnaire_result["scores"].items(), key=lambda x: x[1], reverse=True)[1][0]
            type_scores[second_best] += 0.05 * q_confidence
        
        # Get final skin type
        final_skin_type = max(type_scores, key=type_scores.get)
        final_score = type_scores[final_skin_type]
        
        # Calculate final confidence
        final_confidence = final_score * agreement_bonus * (0.65 + matching * 0.35)
        final_confidence = min(0.94, max(0.60, final_confidence))
        
        # 4. Get skin care data
        skin_data = SKIN_CARE_DATA.get(final_skin_type, SKIN_CARE_DATA["normal"])
        
        # Add personalized recommendations
        personalized_recommendations = list(skin_data["recommendations"])
        for concern in questionnaire_data.get("skin_concerns", []):
            if concern == "acne" and "salicylic" not in str(personalized_recommendations).lower():
                personalized_recommendations.append("Use salicylic acid or benzoyl peroxide for acne")
            elif concern == "dark_spots":
                personalized_recommendations.append("Apply vitamin C serum in the morning")
            elif concern == "wrinkles":
                personalized_recommendations.append("Use retinol at night (start with low concentration)")
            elif concern == "redness":
                personalized_recommendations.append("Use calming ingredients like centella or niacinamide")
            elif concern == "large_pores":
                personalized_recommendations.append("Use niacinamide to help minimize pores")
            elif concern == "dullness":
                personalized_recommendations.append("Use vitamin C or glycolic acid for brightness")
        
        # 5. Save to database
        analysis_id = str(uuid.uuid4())
        questionnaire_id = str(uuid.uuid4())
        
        async with get_db() as conn:
            # Save analysis
            if hasattr(conn, 'execute'):
                await conn.execute(
                    """INSERT INTO analyses (id, user_id, skin_type, skin_name, confidence, characteristics, recommendations, recommended_oils, method) 
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                    analysis_id, user_id, final_skin_type, skin_data["name"], final_confidence,
                    "|".join(skin_data["characteristics"]),
                    "|".join(personalized_recommendations),
                    "|".join(skin_data["oils"]),
                    "AI + Questionnaire Analysis"
                )
            else:
                await conn.execute(
                    """INSERT INTO analyses (id, user_id, skin_type, skin_name, confidence, characteristics, recommendations, recommended_oils, method) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    analysis_id, user_id, final_skin_type, skin_data["name"], final_confidence,
                    "|".join(skin_data["characteristics"]),
                    "|".join(personalized_recommendations),
                    "|".join(skin_data["oils"]),
                    "AI + Questionnaire Analysis"
                )
            
            # Save questionnaire
            if hasattr(conn, 'execute'):
                await conn.execute(
                    """INSERT INTO skin_questionnaires 
                       (id, user_id, self_assessed_skin_type, calculated_skin_type, confidence, matching_percentage,
                        oiliness, dryness, sensitivity, acne_frequency, redness, pores_size, texture, uses_sunscreen)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)""",
                    questionnaire_id, user_id, questionnaire_data.get("self_assessed_skin_type", "normal"),
                    q_skin_type, q_confidence, matching,
                    questionnaire_data.get("oiliness", 3), questionnaire_data.get("dryness", 3),
                    questionnaire_data.get("sensitivity", 3), questionnaire_data.get("acne_frequency", 3),
                    questionnaire_data.get("redness", 3), questionnaire_data.get("pores_size", 3),
                    questionnaire_data.get("texture", 3), 1 if questionnaire_data.get("uses_sunscreen", False) else 0
                )
            else:
                await conn.execute(
                    """INSERT INTO skin_questionnaires 
                       (id, user_id, self_assessed_skin_type, calculated_skin_type, confidence, matching_percentage,
                        oiliness, dryness, sensitivity, acne_frequency, redness, pores_size, texture, uses_sunscreen)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    questionnaire_id, user_id, questionnaire_data.get("self_assessed_skin_type", "normal"),
                    q_skin_type, q_confidence, matching,
                    questionnaire_data.get("oiliness", 3), questionnaire_data.get("dryness", 3),
                    questionnaire_data.get("sensitivity", 3), questionnaire_data.get("acne_frequency", 3),
                    questionnaire_data.get("redness", 3), questionnaire_data.get("pores_size", 3),
                    questionnaire_data.get("texture", 3), 1 if questionnaire_data.get("uses_sunscreen", False) else 0
                )
        
        return {
            "success": True,
            "analysis_id": analysis_id,
            "questionnaire_id": questionnaire_id,
            "skin_type": final_skin_type,
            "skin_name": skin_data["name"],
            "confidence": final_confidence,
            "ai_analysis": {
                "skin_type": ai_skin_type,
                "confidence": ai_confidence
            },
            "questionnaire_analysis": {
                "calculated_skin_type": q_skin_type,
                "confidence": q_confidence,
                "matching_percentage": matching
            },
            "characteristics": skin_data["characteristics"],
            "recommendations": personalized_recommendations,
            "recommended_oils": skin_data["oils"],
            "method": "Hybrid Analysis (AI + Questionnaire)",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Questionnaire analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# ============================================
# DEBUG ENDPOINT
# ============================================

@app.get("/analyze/debug/{analysis_id}")
async def debug_hybrid_analysis(analysis_id: str, user_id: str = Depends(verify_token)):
    """Debug endpoint to check hybrid analysis details"""
    async with get_db() as conn:
        if hasattr(conn, 'fetchrow'):
            analysis = await conn.fetchrow(
                """SELECT * FROM analyses WHERE id = $1 AND user_id = $2""",
                analysis_id, user_id
            )
            questionnaire = await conn.fetchrow(
                """SELECT * FROM skin_questionnaires WHERE user_id = $2 ORDER BY created_at DESC LIMIT 1""",
                user_id
            )
        else:
            cursor = await conn.execute(
                """SELECT * FROM analyses WHERE id = ? AND user_id = ?""",
                (analysis_id, user_id)
            )
            analysis = await cursor.fetchone()
            
            cursor2 = await conn.execute(
                """SELECT * FROM skin_questionnaires WHERE user_id = ? ORDER BY created_at DESC LIMIT 1""",
                (user_id,)
            )
            questionnaire = await cursor2.fetchone()
        
        return {
            "analysis": dict(analysis) if analysis else None,
            "questionnaire": dict(questionnaire) if questionnaire else None,
            "message": "Debug information for hybrid analysis"
        }

# ============================================
# WEATHER ENDPOINTS
# ============================================

@app.get("/weather/{lat}/{lon}")
async def get_weather(lat: float, lon: float, skin_type: str = "normal", user_id: str = Depends(verify_token)):
    weather = get_dynamic_weather(lat, lon)
    sunscreen = get_sunscreen_recommendation(weather.get("uv_index", 5), skin_type)
    return {"success": True, "weather": weather, "sunscreen": sunscreen}

@app.get("/location/{lat}/{lon}")
async def get_location(lat: float, lon: float):
    weather = get_dynamic_weather(lat, lon)
    return {"success": True, "city": weather["city"]}

@app.get("/sunscreen/{uv_index}")
async def get_sunscreen_recommendation_endpoint(uv_index: float, skin_type: str = "normal"):
    return {"success": True, **get_sunscreen_recommendation(uv_index, skin_type)}

# ============================================
# CHAT ENDPOINT (Natural & Friendly)
# ============================================

@app.post("/chat")
async def chat_endpoint(request: ChatRequest, user_id: str = Depends(verify_token)):
    if not request.message or not request.message.strip():
        language = detect_language(request.message) if request.message else "english"
        return {"success": False, "response": "Tafadhali andika swali lako." if language == "swahili" else "Please write your question."}
    
    async with get_db() as conn:
        if hasattr(conn, 'fetchrow'):
            latest_analysis = await conn.fetchrow(
                "SELECT skin_type FROM analyses WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
                user_id
            )
            user = await conn.fetchrow("SELECT name FROM users WHERE id = $1", user_id)
        else:
            cursor1 = await conn.execute("SELECT skin_type FROM analyses WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,))
            latest_analysis = await cursor1.fetchone()
            cursor2 = await conn.execute("SELECT name FROM users WHERE id = ?", (user_id,))
            user = await cursor2.fetchone()
    
    system_context = """You are SkinSight AI, a friendly skincare assistant.

Be warm and conversational. Respond to greetings naturally.

You can chat casually, but your main expertise is skincare. When users ask about skincare, give helpful, detailed advice.

Respond in the same language as the user (English or Swahili).

Be natural - don't say "I'm a skincare expert" every time. Just be helpful like a friend who knows about skin."""
    
    if latest_analysis:
        system_context += f"\n\nThis user has {latest_analysis['skin_type']} skin type."
    if user and user['name']:
        system_context += f"\n\nThe user's name is {user['name']}."
    
    result = await ChatService.get_response(
        user_message=request.message,
        system_context=system_context,
        conversation_history=request.conversation_history,
        max_tokens=request.max_tokens or 800,
        temperature=request.temperature or 0.85
    )
    
    if result.get("success") and result.get("response"):
        try:
            async with get_db() as conn:
                chat_id = str(uuid.uuid4())
                if hasattr(conn, 'execute'):
                    await conn.execute(
                        """INSERT INTO chat_history (id, user_id, user_message, assistant_response, provider, skin_context) 
                           VALUES ($1, $2, $3, $4, $5, $6)""",
                        chat_id, user_id, request.message, result["response"], result.get("provider"), 
                        latest_analysis["skin_type"] if latest_analysis else None
                    )
                else:
                    await conn.execute(
                        """INSERT INTO chat_history (id, user_id, user_message, assistant_response, provider, skin_context) 
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        chat_id, user_id, request.message, result["response"], result.get("provider"), 
                        latest_analysis["skin_type"] if latest_analysis else None
                    )
        except:
            pass
    
    if not result.get("response"):
        result["response"] = get_natural_fallback_response(request.message)
    
    return result

@app.get("/chat/history")
async def get_chat_history(limit: int = 50, user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        if hasattr(conn, 'fetch'):
            history = await conn.fetch(
                "SELECT id, user_message, assistant_response, provider, created_at FROM chat_history WHERE user_id = $1 ORDER BY created_at ASC LIMIT $2",
                user_id, limit
            )
        else:
            cursor = await conn.execute(
                "SELECT id, user_message, assistant_response, provider, created_at FROM chat_history WHERE user_id = ? ORDER BY created_at ASC LIMIT ?",
                (user_id, limit)
            )
            history = await cursor.fetchall()
        
        messages = []
        for h in history:
            messages.append({"role": "user", "content": h["user_message"], "timestamp": h["created_at"]})
            messages.append({"role": "assistant", "content": h["assistant_response"], "timestamp": h["created_at"]})
        
        return {"success": True, "messages": messages, "total": len(history)}

@app.delete("/chat/history")
async def clear_chat_history(user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        if hasattr(conn, 'execute'):
            await conn.execute("DELETE FROM chat_history WHERE user_id = $1", user_id)
        else:
            await conn.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
    return {"success": True, "message": "Chat history cleared"}

# ============================================
# PRODUCT ENDPOINTS
# ============================================

@app.get("/products")
async def get_products(category: Optional[str] = None, limit: int = 20, offset: int = 0):
    async with get_db() as conn:
        if hasattr(conn, 'fetch'):
            products = await conn.fetch("SELECT * FROM products WHERE is_approved = 1 LIMIT $1 OFFSET $2", limit, offset)
        else:
            cursor = await conn.execute("SELECT * FROM products WHERE is_approved = 1 LIMIT ? OFFSET ?", (limit, offset))
            products = await cursor.fetchall()
        return {"success": True, "products": [dict(p) for p in products]}

@app.get("/products/categories")
async def get_categories():
    return {"success": True, "categories": ["cleanser", "moisturizer", "sunscreen", "serum", "mask", "toner"]}

# ============================================
# STATIC FILES
# ============================================

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

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
    print(f"💾 Database: PostgreSQL (Production) / SQLite (Local)")
    print(f"💬 Chat Mode: Natural & Friendly - Skincare Focused")
    print(f"🔬 Analysis Mode: AI + Questionnaire (Hybrid)")
    print("=" * 70)
    print("🚀 Server is ready!")
    print("=" * 70)
    
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True, proxy_headers=True)
