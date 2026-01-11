"""Advanced search endpoint with fuzzy matching and reranking."""
import json
import hashlib
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, and_, or_
from app.core.database import get_db
from app.db.models import SearchContent, PageAnalysis
from app.utils.intent_detector import IntentDetector
from app.utils.fuzzy_reranker import fuzzy_reranker
from app.core.cache import get_redis_client
import time

router = APIRouter()

def _get_cache_key(key_type: str, value: str) -> str:
    """Generate cache key with hash."""
    return f"{key_type}:{hashlib.sha256(value.encode()).hexdigest()[:16]}"

@router.get("/fuzzy")
async def fuzzy_search(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ambiguity: Optional[float] = Query(0.5, ge=0.0, le=1.0, description="Ambiguity control: 0 (ignore) to 1 (strict)"),
    explain: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis_client),
):
    """
    Fuzzy search with ambiguity-aware reranking.
    
    Pipeline:
    1. Input Normalization (lowercase, trim)
    2. Intent Classification (what the user wants)
    3. Full-text Search (ranked by relevance)
    4. Fuzzy Reranking (handle typos and misspellings)
    5. Ambiguity Control (penalize uncertain matches)
    """
    
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    start = time.time()
    q_lower = q.lower().strip()
    q_pattern = f"%{q_lower}%"
    
    # Step 1: Cache check
    cache_key = _get_cache_key(
        "fuzzy_search",
        f"{q_lower}:{limit}:{offset}:{ambiguity:.1f}"
    )
    
    if redis:
        try:
            cached_result = await redis.get(cache_key)
            if cached_result:
                result = json.loads(cached_result)
                result["meta"]["cache_hit"] = True
                result["meta"]["took_ms"] = int((time.time() - start) * 1000)
                return result
        except Exception:
            pass
    
    # Step 2: Intent Detection
    try:
        intent_data = IntentDetector.detect_intent(q_lower)
        primary_intent = intent_data.get('primary_intent', 'informational')
        intent_confidence = intent_data.get('intent_confidence', 0.5)
    except Exception:
        primary_intent = 'informational'
        intent_confidence = 0.5
    
    try:
        # Step 3: Full-text Search on SearchContent
        # ✅ Use ILIKE for case-insensitive substring matching
        query = select(SearchContent).where(
            or_(
                SearchContent.title.ilike(q_pattern),
                SearchContent.h1.ilike(q_pattern),
                SearchContent.description.ilike(q_pattern),
                SearchContent.content.ilike(q_pattern),
            )
        ).order_by(
            SearchContent.quality_score.desc()
        ).limit(limit * 3).offset(offset)  # Get more results for reranking
        
        result = await db.execute(query)
        rows = result.scalars().all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    
    if not rows:
        return {
            "meta": {
                "query": q,
                "took_ms": int((time.time() - start) * 1000),
                "count": 0,
                "intent": {
                    "primary": primary_intent,
                    "confidence": intent_confidence,
                },
                "cache_hit": False,
            },
            "data": [],
        }
    
    # Step 4: Prepare base scores and results
    base_results = []
    base_scores = []
    
    for i, row in enumerate(rows):
        # ✅ Extract title with priority: og_title > title > h1 > URL
        title = row.og_title or row.title or row.h1 or row.url.split('/')[-1]
        
        base_results.append({
            "id": row.id,
            "title": title,
            "url": row.url,
            "domain": row.domain,
            "favicon": None,  # Not in SearchContent
            "og_title": row.og_title,
            "og_description": row.og_description,
            "og_image": row.og_image_url,
            "content": row.content or "",
            "h1": row.h1,
            "content_type": row.content_type or "unknown",
            "content_confidence": None,  # Not in SearchContent
            "tracker_risk_score": 0.0,  # Not in SearchContent
        })
        
        # Base score from quality_score (0.0-1.0 range)
        # Normalize to 0-10 for consistency with PGroonga
        score = float(row.quality_score) * 10 if row.quality_score else 5.0
        base_scores.append(score)
    
    # Step 5: Fuzzy Reranking with Ambiguity Control
    try:
        reranked = fuzzy_reranker.rerank(
            base_results,
            q_lower,
            base_scores,
            ambiguity_control=ambiguity
        )
    except Exception as e:
        # Fallback: use base results without fuzzy reranking
        reranked = list(zip(base_results, base_scores))
    
    # Step 6: Apply limit and offset
    final_results = reranked[offset:offset + limit]
    
    # Build response
    data = []
    for result, score in final_results:
        item = {
            "id": result["id"],
            "title": result["title"],
            "url": result["url"],
            "domain": result["domain"],
            "favicon": result["favicon"],
            "og": {
                "title": result["og_title"],
                "description": result["og_description"],
                "image": result["og_image"],
            },
            "content_type": result["content_type"],
            "content_confidence": result["content_confidence"],
            "relevance_score": float(score) / 10.0,  # Normalize back to 0-1
        }
        
        if explain:
            try:
                item["explain"] = {
                    "fuzzy_match": fuzzy_reranker.explain_relevance(result, q_lower),
                    "ambiguity_control": ambiguity,
                    "intent": primary_intent,
                }
            except Exception:
                item["explain"] = {"error": "Could not explain relevance"}
        
        data.append(item)
    
    took_ms = int((time.time() - start) * 1000)
    response = {
        "meta": {
            "query": q,
            "took_ms": took_ms,
            "count": len(data),
            "total_available": len(reranked),
            "explain_mode": explain,
            "cache_hit": False,
            "ambiguity_control": ambiguity,
            "intent": {
                "primary": primary_intent,
                "confidence": intent_confidence,
            },
        },
        "data": data,
    }
    
    # Cache result
    if redis and len(data) > 0:
        try:
            await redis.setex(
                cache_key,
                300,
                json.dumps(response, default=str)
            )
        except Exception:
            pass
    
    return response


@router.get("/fuzzy/explain/{query}")
async def explain_fuzzy_match(
    query: str,
    result_title: str = Query(...),
    result_url: str = Query(...),
):
    """
    Explain why a result matches a query (for debugging).
    """
    result = {
        "title": result_title,
        "url": result_url,
        "content": "",
    }
    
    try:
        explanation = fuzzy_reranker.explain_relevance(result, query.lower())
    except Exception:
        explanation = {"error": "Could not explain relevance"}
    
    return {
        "query": query,
        "result": result_title,
        "explanation": explanation,
        "interpretation": _interpret_scores(explanation) if "error" not in explanation else {},
    }


def _interpret_scores(scores: Dict[str, float]) -> Dict[str, str]:
    """Interpret relevance scores in human-readable form."""
    def interpret(score: float) -> str:
        if score >= 0.9:
            return "⚡ Excellent match"
        elif score >= 0.7:
            return "✓ Good match"
        elif score >= 0.5:
            return "~ Fair match"
        elif score >= 0.3:
            return "◑ Weak match"
        else:
            return "✗ Poor match"
    
    return {
        k: interpret(v) for k, v in scores.items()
    }
