# models/skin_questionnaire.py
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class SkinType(str, Enum):
    DRY = "dry"
    OILY = "oily"
    COMBINATION = "combination"
    SENSITIVE = "sensitive"
    NORMAL = "normal"

class SkinConcern(str, Enum):
    ACNE = "acne"
    DARK_SPOTS = "dark_spots"
    WRINKLES = "wrinkles"
    REDNESS = "redness"
    PIGMENTATION = "pigmentation"
    LARGE_PORES = "large_pores"
    DULLNESS = "dullness"
    DEHYDRATION = "dehydration"

class QuestionnaireRequest(BaseModel):
    # Personal Info
    age: Optional[int] = None
    gender: Optional[str] = None
    
    # Skin Self-Assessment
    self_assessed_skin_type: SkinType
    skin_concerns: List[SkinConcern] = []
    
    # Symptoms (Multiple choice - user chooses)
    oiliness: int = Field(..., ge=1, le=5, description="1=Very Dry, 5=Very Oily")
    dryness: int = Field(..., ge=1, le=5, description="1=No dryness, 5=Severe dryness")
    sensitivity: int = Field(..., ge=1, le=5, description="1=Not sensitive, 5=Very sensitive")
    acne_frequency: int = Field(..., ge=1, le=5, description="1=Never, 5=Very often")
    redness: int = Field(..., ge=1, le=5, description="1=None, 5=Severe")
    pores_size: int = Field(..., ge=1, le=5, description="1=Small/Invisible, 5=Very large")
    texture: int = Field(..., ge=1, le=5, description="1=Smooth, 5=Rough/Uneven")
    
    # Daily Routine
    uses_sunscreen: bool = False
    cleanser_type: Optional[str] = None
    moisturizer_type: Optional[str] = None
    
    # Lifestyle
    water_intake: Optional[str] = None
    sleep_hours: Optional[float] = None
    diet: Optional[str] = None

class QuestionnaireResponse(BaseModel):
    success: bool
    questionnaire_id: str
    user_id: str
    calculated_skin_type: SkinType
    confidence: float
    matching_percentage: float
    recommendations: List[str]