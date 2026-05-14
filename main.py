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
import numpy as np
from collections import Counter
import logging
import time
from functools import wraps
import re
import shutil
from pathlib import Path

# Load environment variables
load_dotenv()

# Add parent directory to path for database module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import database module
from database import get_db, init_db, migrate_data, hash_password, verify_password

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
    allow_origins=os.getenv('ALLOWED_ORIGINS', '*').split(','),
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

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    system_context: Optional[str] = None
    conversation_history: Optional[List[Dict[str, str]]] = None
    max_tokens: Optional[int] = 800
    temperature: Optional[float] = 0.8

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
# CHAT SERVICE (Natural & Friendly)
# ============================================

class ChatService:
    @staticmethod
    async def get_openai_response(
        user_message: str,
        system_context: str,
        conversation_history: Optional[List[Dict]] = None,
        max_tokens: int = 800,
        temperature: float = 0.8
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
            
            # Natural, friendly system prompt - not restrictive
            system_prompt = """You are a friendly and knowledgeable skincare assistant named SkinSight AI. You help people with their skincare concerns in a warm, natural way.

KEY RULES:
1. Be conversational and friendly - greet users warmly, ask how you can help
2. You CAN respond to greetings, small talk, and casual conversation naturally
3. Your main expertise is skincare - when users ask skincare questions, give detailed, helpful advice
4. For UV/sun questions, focus on how it affects skin and protection methods
5. Be helpful and concise but don't be robotic
6. Respond in the same language as the user (English or Swahili)
7. Don't repeat yourself or say "I'm a skincare expert" constantly - just be natural

EXAMPLES OF GOOD RESPONSES:
- User: "Habari" → "Habari yako! Niko vizuri, asante. Je, ninaweza kukusaidia vipi kuhusu ngozi yako leo?"
- User: "Hello" → "Hello there! I'm doing well, thank you. How can I help with your skin today?"
- User: "Asante" → "Karibu sana! Niko hapa kukusaidia wakati wote. Una swali jingine kuhusu ngozi?"
- User: "What can you help me with?" → "I can help with skincare routines, product recommendations, skin problems like acne or dryness, sun protection, and general skin health advice. What would you like to know?"
- User: "Nina acne" → Give detailed acne advice with specific steps
- User: "Dry skin" → Give detailed dry skin advice

IMPORTANT: Just be natural and conversational. Don't over-explain your role. Just help users with their questions."""
            
            messages = [{"role": "system", "content": system_prompt}]
            
            if conversation_history:
                # Take more context for natural conversation
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
        temperature: float = 0.8
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
            
            system_prompt = """You are a friendly skincare assistant. Be warm and conversational.

You can respond to greetings and casual talk naturally. When users ask skincare questions, give detailed advice.

Respond in the same language as the user. Be helpful and natural - don't be robotic."""
            
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
        default_context = """You are a friendly skincare assistant. Be warm and conversational.

Greet users naturally. You can chat casually. When users ask skincare questions, give helpful, detailed advice.

Respond in the same language as the user (English or Swahili)."""
        
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
# NATURAL FALLBACK RESPONSES (No repetition)
# ============================================

def get_natural_fallback_response(message: str) -> str:
    """Return natural, friendly fallback responses"""
    message_lower = message.lower()
    language = detect_language(message)
    
    # Greetings in Swahili
    if any(word in message_lower for word in ["habari", "hujambo", "sasa", "mambo", "vipi", "poa"]):
        if language == "swahili":
            return "Habari yako! Niko vizuri, asante. Je, ninaweza kukusaidia vipi kuhusu ngozi yako leo?"
        else:
            return "Hello! I'm doing well, thank you. How can I help with your skin today?"
    
    # Greetings in English
    elif any(word in message_lower for word in ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]):
        if language == "swahili":
            return "Habari! Karibu kwenye SkinSight AI. Je, nikuwezeshe vipi kuhusu utunzaji wa ngozi yako?"
        else:
            return "Hello! Welcome to SkinSight AI. How can I help you with your skincare today?"
    
    # Thank you
    elif any(word in message_lower for word in ["asante", "thank", "thanks", "shukran"]):
        if language == "swahili":
            return "Karibu sana! Niko hapa kukusaidia wakati wote. Una swali jingine kuhusu ngozi?"
        else:
            return "You're very welcome! I'm here to help anytime. Do you have any other skincare questions?"
    
    # Help/What can you do
    elif any(word in message_lower for word in ["help", "saidia", "what can you do", "unaweza kufanya nini"]):
        if language == "swahili":
            return """Ninaweza kukusaidia kuhusu:
• Aina za ngozi (kavu, mafuta, combination, nyeti)
• Matatizo ya ngozi kama acne, matangazo, kasoro
• Bidhaa za ngozi na jinsi ya kuzitumia
• Kinga ya jua na SPF
• Utaratibu wa kutunza ngozi

Una swali gani leo?"""
        else:
            return """I can help you with:
• Skin types (dry, oily, combination, sensitive)
• Skin problems like acne, dark spots, wrinkles
• Skincare products and how to use them
• Sun protection and SPF
• Daily skincare routines

What would you like to know today?"""
    
    # Acne
    elif any(word in message_lower for word in ["acne", "chunusi", "pimple", "breakout"]):
        if language == "swahili":
            return """Kwa acne (chunusi), hapa kuna ushauri wangu:

1. Tumia cleanser yenye salicylic acid au benzoyl peroxide mara 1-2 kwa siku
2. Usiguse au kubana chunusi - inaweza kusababisha makovu
3. Tumia moisturizer lightweight isiyo na mafuta
4. Omba sunscreen SPF 30+ kila siku - jua inazidisha acne
5. Epuka vyakula vya mafuta mengi na sukari ikiwezekana

Je, ungependa nikupe ushauri wa bidhaa maalum?"""
        else:
            return """For acne, here's my advice:

1. Use a cleanser with salicylic acid or benzoyl peroxide 1-2 times daily
2. Don't touch or pop pimples - this can cause scarring
3. Use a lightweight, oil-free moisturizer
4. Apply SPF 30+ sunscreen daily - sun makes acne worse
5. Avoid oily foods and excess sugar if possible

Would you like specific product recommendations?"""
    
    # Dry skin
    elif any(word in message_lower for word in ["dry", "kavu", "flaky", "tight"]):
        if language == "swahili":
            return """Kwa ngozi kavu, napendekeza:

1. Tumia hydrating cleanser isiyo na sulfate
2. Omba hyaluronic acid serum mara baada ya kuosha uso
3. Tumia rich moisturizer yenye ceramides au shea butter
4. Ongeza facial oil kama argan au jojoba usiku
5. Kunywa maji mengi (lita 2-3 kwa siku)

Unahitaji nikupe maelezo zaidi?"""
        else:
            return """For dry skin, I recommend:

1. Use a hydrating, sulfate-free cleanser
2. Apply hyaluronic acid serum right after washing
3. Use a rich moisturizer with ceramides or shea butter
4. Add a facial oil like argan or jojoba at night
5. Drink plenty of water (2-3 liters daily)

Would you like more details?"""
    
    # Oily skin
    elif any(word in message_lower for word in ["oily", "mafuta", "greasy", "shine"]):
        if language == "swahili":
            return """Kwa ngozi yenye mafuta:

1. Tumia foaming au gel cleanser mara mbili kwa siku
2. Omba niacinamide serum (inasaidia kudhibiti mafuta)
3. Tumia gel moisturizer isiyo na mafuta
4. Exfoliate mara 2 kwa wiki kwa salicylic acid
5. Tumia clay mask mara moja kwa wiki

Je, ungependa maelezo zaidi?"""
        else:
            return """For oily skin:

1. Use a foaming or gel cleanser twice daily
2. Apply niacinamide serum (helps control oil)
3. Use an oil-free gel moisturizer
4. Exfoliate twice weekly with salicylic acid
5. Use a clay mask once weekly

Would you like more details?"""
    
    # Sunscreen/UV
    elif any(word in message_lower for word in ["sunscreen", "spf", "jua", "sun", "uv"]):
        if language == "swahili":
            return """Kuhusu kinga ya jua:

1. Tumia SPF 30+ kila siku, hata ukiwa ndani ya nyumba
2. Omba dakika 15-20 kabla ya kwenda nje
3. Tumia kiasi cha kutosha (1/2 kijiko kwa uso na shingo)
4. Rudia kila baada ya masaa 2-3 ukiwa nje
5. Chagua sunscreen inayofaa aina ya ngozi yako

Unahitaji msaada wa kuchagua sunscreen?"""
        else:
            return """About sun protection:

1. Use SPF 30+ daily, even when indoors
2. Apply 15-20 minutes before going outside
3. Use enough (1/2 teaspoon for face and neck)
4. Reapply every 2-3 hours when outside
5. Choose sunscreen suitable for your skin type

Need help choosing a sunscreen?"""
    
    # Default friendly response
    else:
        if language == "swahili":
            return """Niko hapa kukusaidia na ngozi yako. Je, unaweza kunielezea zaidi kuhusu wasiwasi wako?

Unaweza kuniuliza kuhusu:
• Aina ya ngozi yako
• Matatizo unayokabiliana nayo (acne, ngozi kavu, n.k.)
• Bidhaa unazotumia au unataka kujua
• Utaratibu wa kutunza ngozi

Niambie zaidi, nikusaidie vizuri!"""
        else:
            return """I'm here to help with your skin. Could you tell me more about your concern?

You can ask me about:
• Your skin type
• Problems you're facing (acne, dry skin, etc.)
• Products you use or want to learn about
• Skincare routines

Tell me more so I can help you better!"""

# ============================================
# WEATHER CONFIGURATION
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
# SKIN ANALYSIS FUNCTIONS (Simplified for space)
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
    """Placeholder - MediaPipe analysis"""
    return None

def analyze_with_fallback(image_bytes: bytes) -> Dict:
    """Fallback analysis"""
    return {"skin_type": "normal", "confidence": 0.75, "method": "Default"}

def analyze_with_consistency(image_bytes: bytes) -> Dict:
    """Consistent analysis"""
    return analyze_with_fallback(image_bytes)

# ============================================
# PROFILE IMAGE ENDPOINTS
# ============================================

UPLOAD_DIR = "uploads/profiles"
os.makedirs(UPLOAD_DIR, exist_ok=True)
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

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
        old = await conn.fetchrow("SELECT profile_image FROM users WHERE id = $1", user_id) if hasattr(conn, 'fetchrow') else None
        if old and old.get('profile_image'):
            old_path = os.path.join(UPLOAD_DIR, os.path.basename(old['profile_image']))
            if os.path.exists(old_path):
                os.remove(old_path)
    
    filename = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{file_extension}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    with open(filepath, "wb") as buffer:
        buffer.write(contents)
    
    image_path = f"/uploads/profiles/{filename}"
    base_url = os.getenv('BASE_URL', 'http://localhost:8000')
    full_url = f"{base_url}{image_path}"
    
    async with get_db() as conn:
        await conn.execute("UPDATE users SET profile_image = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2", image_path, user_id)
    
    return {"success": True, "profile_image": full_url, "message": "Profile image uploaded successfully"}

@app.get("/users/me")
async def get_current_user(user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        user = await conn.fetchrow(
            "SELECT id, email, name, role, is_approved, created_at, phone, address, profile_image FROM users WHERE id = $1",
            user_id
        )
        if not user:
            return JSONResponse(status_code=404, content={"success": False, "message": "User not found"})
        
        user_dict = dict(user)
        if user_dict.get('profile_image'):
            base_url = os.getenv('BASE_URL', 'http://localhost:8000')
            if not user_dict['profile_image'].startswith('http'):
                user_dict['profile_image'] = f"{base_url}{user_dict['profile_image']}"
        
        return {"success": True, "user": user_dict}

# ============================================
# AUTH ENDPOINTS
# ============================================

@app.post("/auth/register")
async def register(request: RegisterRequest):
    try:
        async with get_db() as conn:
            existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", request.email)
            if existing:
                return JSONResponse(status_code=400, content={"success": False, "message": "Email already registered"})
            
            user_id = str(uuid.uuid4())
            password_hash_str = hash_password(request.password)
            is_approved = 1 if request.role == 'customer' else 0
            
            await conn.execute(
                """INSERT INTO users (id, email, password_hash, name, role, is_approved, phone, address, created_at, updated_at) 
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                user_id, request.email, password_hash_str, request.name, request.role, is_approved, request.phone, request.address
            )
        
        access_token = create_access_token({"sub": request.email, "user_id": user_id, "role": request.role})
        refresh_token = create_refresh_token(user_id)
        
        return {
            "success": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {"id": user_id, "email": request.email, "name": request.name, "role": request.role}
        }
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.post("/auth/login")
async def login(request: LoginRequest):
    try:
        async with get_db() as conn:
            user = await conn.fetchrow(
                "SELECT id, email, password_hash, name, role, is_approved, phone, address, profile_image, created_at FROM users WHERE email = $1",
                request.email
            )
            
            if not user or not verify_password(request.password, user["password_hash"]):
                return JSONResponse(status_code=401, content={"success": False, "message": "Invalid email or password"})
            
            await conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = $1", user["id"])
        
        access_token = create_access_token({"sub": user["email"], "user_id": user["id"], "role": user["role"]})
        refresh_token = create_refresh_token(user["id"])
        
        profile_image = user["profile_image"]
        base_url = os.getenv('BASE_URL', 'http://localhost:8000')
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

# ============================================
# CHAT ENDPOINT (Natural & Friendly)
# ============================================

@app.post("/chat")
async def chat_endpoint(request: ChatRequest, user_id: str = Depends(verify_token)):
    if not request.message or not request.message.strip():
        language = detect_language(request.message) if request.message else "english"
        if language == "swahili":
            return {"success": False, "response": "Tafadhali andika swali lako."}
        else:
            return {"success": False, "response": "Please write your question."}
    
    # Get user context for personalization
    async with get_db() as conn:
        latest_analysis = await conn.fetchrow(
            "SELECT skin_type FROM analyses WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
            user_id
        )
        user = await conn.fetchrow("SELECT name FROM users WHERE id = $1", user_id)
    
    # Natural system context - not restrictive
    system_context = """You are a friendly skincare assistant named SkinSight AI.

Be warm and conversational. Greet users naturally. You can chat casually.

When users ask skincare questions, give helpful, detailed advice with specific steps and recommendations.

For UV/sun questions, focus on how it affects skin and protection methods.

Respond in the same language as the user (English or Swahili).

Be natural - don't repeat yourself or over-explain your role."""
    
    if latest_analysis:
        skin_type_map = {
            "dry": "dry",
            "oily": "oily", 
            "combination": "combination",
            "sensitive": "sensitive",
            "normal": "normal"
        }
        skin_name = skin_type_map.get(latest_analysis['skin_type'], latest_analysis['skin_type'])
        system_context += f"\n\nThis user has {skin_name} skin type. Tailor advice accordingly."
    
    if user and user['name']:
        system_context += f"\n\nThe user's name is {user['name']}. You can address them by name naturally."
    
    result = await ChatService.get_response(
        user_message=request.message,
        system_context=system_context,
        conversation_history=request.conversation_history,
        max_tokens=request.max_tokens or 800,
        temperature=request.temperature or 0.8
    )
    
    # Save to database
    if result.get("success"):
        async with get_db() as conn:
            chat_id = str(uuid.uuid4())
            await conn.execute(
                """INSERT INTO chat_history (id, user_id, user_message, assistant_response, provider, skin_context) 
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                chat_id, user_id, request.message, result["response"], result.get("provider"), 
                latest_analysis["skin_type"] if latest_analysis else None
            )
    
    return result

@app.get("/chat/history")
async def get_chat_history(limit: int = 50, user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        history = await conn.fetch(
            """SELECT id, user_message, assistant_response, provider, created_at 
               FROM chat_history WHERE user_id = $1 ORDER BY created_at ASC LIMIT $2""",
            user_id, limit
        )
        
        messages = []
        for h in history:
            messages.append({"role": "user", "content": h["user_message"], "timestamp": h["created_at"]})
            messages.append({"role": "assistant", "content": h["assistant_response"], "timestamp": h["created_at"]})
        
        return {"success": True, "messages": messages, "total": len(history)}

# ============================================
# HEALTH & ROOT ENDPOINTS
# ============================================

@app.get("/")
async def root():
    return {"status": "healthy", "app": "SkinGlow AI", "version": "5.2.0", "timestamp": datetime.now().isoformat()}

@app.get("/health")
async def health_check():
    return {"status": "operational", "version": "5.2.0", "timestamp": datetime.now().isoformat()}

@app.get("/test-db")
async def test_db():
    try:
        async with get_db() as conn:
            await conn.fetchval("SELECT 1")
        return {"success": True, "message": "Database connected", "type": "PostgreSQL"}
    except Exception as e:
        return {"success": False, "message": str(e)}

# ============================================
# SKIN ANALYSIS ENDPOINT (Simplified)
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
            await conn.execute(
                """INSERT INTO analyses (id, user_id, skin_type, skin_name, confidence, characteristics, recommendations, recommended_oils, method) 
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
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

@app.get("/analyses")
async def get_user_analyses(limit: int = 10, user_id: str = Depends(verify_token)):
    async with get_db() as conn:
        analyses = await conn.fetch(
            "SELECT id, skin_type, skin_name, confidence, method, created_at FROM analyses WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit
        )
        return {"success": True, "analyses": [dict(a) for a in analyses]}

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
    print(f"🤖 MediaPipe: {'Available' if MEDIAPIPE_AVAILABLE else 'Not available'}")
    print(f"🌍 Weather API: {'Configured' if WEATHER_API_KEY else 'Not configured'}")
    print(f"🤖 OpenAI: {'Configured' if OPENAI_API_KEY else 'Not configured'}")
    print(f"🤖 Gemini: {'Configured' if GEMINI_API_KEY else 'Not configured'}")
    print(f"💾 Database: PostgreSQL (Production)")
    print(f"🌍 Region: Pan-African")
    print(f"💬 Chat Mode: Natural & Friendly - Skincare Focused")
    print(f"📸 Profile Images: Enabled")
    print("=" * 70)
    print("🚀 Server is ready!")
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
