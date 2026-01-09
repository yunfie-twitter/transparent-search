from typing import List, Dict
import math

def calculate_term_frequency(tokens: List[str]) -> Dict[str, int]:
    """Calculate term frequency."""
    tf = {}
    for token in tokens:
        tf[token] = tf.get(token, 0) + 1
    return tf

def simple_score(
    query_tokens: List[str],
    title: str,
    url: str,
    h1_text: str,
    body_text: str,
    content_length: int,
    days_since_update: int,
) -> float:
    """Simple additive scoring.
    
    Weights:
    - Title match: +10 per term
    - URL match: +6 per term
    - H1 match: +8 per term
    - Body match: +1 per occurrence
    - Exact phrase in title: +5
    - Freshness: -0.1 per day old (capped)
    - Content quality: penalty if too short
    """
    score = 0.0
    
    title_lower = title.lower()
    url_lower = url.lower()
    h1_lower = h1_text.lower()
    body_lower = body_text.lower()
    
    # Exact phrase bonus
    query_phrase = " ".join(query_tokens)
    if query_phrase in title_lower:
        score += 5.0
    
    for token in query_tokens:
        token_lower = token.lower()
        
        # Title
        if token_lower in title_lower:
            score += 10.0
        
        # URL
        if token_lower in url_lower:
            score += 6.0
        
        # H1
        if token_lower in h1_lower:
            score += 8.0
        
        # Body (count occurrences)
        body_count = body_lower.count(token_lower)
        score += body_count * 1.0
    
    # Freshness (newer is better)
    if days_since_update > 0:
        freshness_penalty = min(days_since_update * 0.1, 10.0)
        score -= freshness_penalty
    
    # Content quality
    if content_length < 100:
        score -= 5.0
    elif content_length > 1000:
        score += 2.0
    
    return max(score, 0.0)
