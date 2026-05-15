# skin_analyzer.py
from typing import Dict
from models.skin_questionnaire import QuestionnaireRequest

def calculate_skin_type_from_questionnaire(data: QuestionnaireRequest) -> Dict:
    """Calculate skin type based on user's questionnaire answers - IMPROVED"""
    scores = {"dry": 0, "oily": 0, "combination": 0, "sensitive": 0, "normal": 0}
    
    # ============================================
    # 1. OILINESS VS DRYNESS SCORING (IMPROVED)
    # ============================================
    # Oiliness (1-5: 1=Very Dry, 5=Very Oily)
    if data.oiliness >= 4:
        scores["oily"] += 4
        scores["combination"] += 2
    elif data.oiliness >= 3:
        scores["combination"] += 3
        scores["normal"] += 1
    elif data.oiliness <= 2:
        scores["dry"] += 3
        scores["normal"] += 1
    
    # Dryness (1-5: 1=No dryness, 5=Severe dryness)
    if data.dryness >= 4:
        scores["dry"] += 4
        scores["sensitive"] += 1
    elif data.dryness >= 3:
        scores["combination"] += 2
        scores["normal"] += 1
    elif data.dryness <= 2:
        scores["oily"] += 2
    
    # Check if user has both high oiliness and high dryness -> Combination
    if data.oiliness >= 3 and data.dryness >= 3:
        scores["combination"] += 3
    
    # ============================================
    # 2. SENSITIVITY SCORING
    # ============================================
    if data.sensitivity >= 4:
        scores["sensitive"] += 5
    elif data.sensitivity >= 3:
        scores["sensitive"] += 2
        scores["normal"] -= 1
    
    # ============================================
    # 3. ACNE FREQUENCY (Associated with oily skin)
    # ============================================
    if data.acne_frequency >= 4:
        scores["oily"] += 3
    elif data.acne_frequency >= 3:
        scores["combination"] += 1
    
    # ============================================
    # 4. REDNESS (Associated with sensitive skin)
    # ============================================
    if data.redness >= 4:
        scores["sensitive"] += 3
        scores["dry"] += 1
    
    # ============================================
    # 5. PORES SIZE (Associated with oily skin)
    # ============================================
    if data.pores_size >= 4:
        scores["oily"] += 2
        scores["combination"] += 1
    elif data.pores_size <= 2:
        scores["dry"] += 1
    
    # ============================================
    # 6. TEXTURE (Associated with dry/sensitive)
    # ============================================
    if data.texture >= 4:
        scores["dry"] += 2
        scores["sensitive"] += 2
    elif data.texture <= 2:
        scores["normal"] += 1
    
    # ============================================
    # 7. SUNSCREEN USAGE (Protects skin)
    # ============================================
    if data.uses_sunscreen:
        scores["normal"] += 1
    
    # ============================================
    # 8. SELF-ASSESSED SKIN TYPE (BONUS)
    # ============================================
    self_assessed = data.self_assessed_skin_type.value
    scores[self_assessed] += 2  # User knows their skin best
    
    # ============================================
    # 9. SKIN CONCERNS (ADJUST SCORES)
    # ============================================
    for concern in data.skin_concerns:
        if concern.value == "acne":
            scores["oily"] += 2
            scores["combination"] += 1
        elif concern.value == "dark_spots":
            scores["normal"] -= 1
            scores["combination"] += 1
        elif concern.value == "wrinkles":
            scores["dry"] += 2
        elif concern.value == "redness":
            scores["sensitive"] += 3
        elif concern.value == "large_pores":
            scores["oily"] += 1
            scores["combination"] += 1
        elif concern.value == "dullness":
            scores["dry"] += 1
            scores["normal"] -= 1
    
    # ============================================
    # 10. GET HIGHEST SCORE
    # ============================================
    max_score = max(scores.values())
    candidates = [k for k, v in scores.items() if v == max_score]
    
    # Handle ties
    if len(candidates) > 1:
        # Priority order: combination > normal > others
        if "combination" in candidates:
            calculated_type = "combination"
        elif "normal" in candidates:
            calculated_type = "normal"
        else:
            calculated_type = candidates[0]
    else:
        calculated_type = candidates[0]
    
    # ============================================
    # 11. CALCULATE CONFIDENCE (IMPROVED)
    # ============================================
    # Get top two scores
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_score = sorted_scores[0][1]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0
    
    # Calculate spread and confidence
    if top_score == 0:
        confidence = 0.50
    else:
        spread = (top_score - second_score) / top_score if top_score > 0 else 0
        confidence = 0.60 + (spread * 0.30)
        confidence = min(0.92, max(0.60, confidence))
    
    # ============================================
    # 12. MATCHING PERCENTAGE
    # ============================================
    if self_assessed == calculated_type:
        matching = 0.80 + (confidence * 0.15)
    elif (self_assessed == "combination" and calculated_type in ["normal", "oily"]) or \
         (self_assessed == "normal" and calculated_type == "combination"):
        matching = 0.65
    else:
        matching = 0.50
    
    matching = min(0.95, max(0.45, matching))
    
    return {
        "calculated_skin_type": calculated_type,
        "confidence": confidence,
        "matching_percentage": matching,
        "scores": scores,
        "top_score": top_score,
        "second_score": second_score
    }
