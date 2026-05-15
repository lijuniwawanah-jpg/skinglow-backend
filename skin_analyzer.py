# skin_analyzer.py
from typing import Dict
from models.skin_questionnaire import QuestionnaireRequest

def calculate_skin_type_from_questionnaire(data: QuestionnaireRequest) -> Dict:
    """Calculate skin type based on user's questionnaire answers"""
    scores = {"dry": 0, "oily": 0, "combination": 0, "sensitive": 0, "normal": 0}
    
    # Oiliness vs Dryness scoring
    if data.oiliness >= 4:
        scores["oily"] += 3
        scores["combination"] += 1
    elif data.oiliness >= 3:
        scores["combination"] += 2
        scores["normal"] += 1
    elif data.oiliness <= 2:
        scores["dry"] += 2
        scores["normal"] += 1
    
    if data.dryness >= 4:
        scores["dry"] += 3
        scores["sensitive"] += 1
    elif data.dryness >= 3:
        scores["combination"] += 1
        scores["normal"] += 1
    elif data.dryness <= 2:
        scores["oily"] += 1
    
    # Sensitivity scoring
    if data.sensitivity >= 4:
        scores["sensitive"] += 3
    elif data.sensitivity >= 3:
        scores["sensitive"] += 1
    
    # Acne frequency
    if data.acne_frequency >= 4:
        scores["oily"] += 2
    
    # Pores size
    if data.pores_size >= 4:
        scores["oily"] += 2
        scores["combination"] += 1
    
    # Texture
    if data.texture >= 4:
        scores["dry"] += 1
        scores["sensitive"] += 1
    
    # Cross-reference with self-assessed type
    self_assessed = data.self_assessed_skin_type.value
    
    # Get highest score
    max_score = max(scores.values())
    calculated_type = [k for k, v in scores.items() if v == max_score][0]
    
    # Calculate confidence based on score spread
    sorted_scores = sorted(scores.values(), reverse=True)
    score_spread = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]
    confidence = 0.60 + (score_spread / 15) * 0.30
    confidence = min(0.90, confidence)
    
    # Calculate matching percentage between self-assessed and calculated
    if self_assessed == calculated_type:
        matching = 0.85 + (confidence * 0.15)
    elif (self_assessed == "combination" and calculated_type in ["normal", "oily"]) or \
         (self_assessed == "normal" and calculated_type == "combination"):
        matching = 0.70
    else:
        matching = 0.50
    
    matching = min(0.98, max(0.50, matching))
    
    return {
        "calculated_skin_type": calculated_type,
        "confidence": confidence,
        "matching_percentage": matching,
        "scores": scores
    }