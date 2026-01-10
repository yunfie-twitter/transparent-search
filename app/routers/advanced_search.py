"""Advanced search endpoint with fuzzy matching and reranking."""
import json
import hashlib
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db
from ..utils.intent_detector import IntentDetector
from ..utils.fuzzy_reranker import fuzzy_reranker
from ..cache import get_redis_client
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
    3. BM25 Full-text Search (ranked by relevance)
    4. Vector Search (semantic similarity)
    5. Fuzzy Reranking (handle typos and misspellings)
    6. Ambiguity Control (penalize uncertain matches)
    """
    
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    start = time.time()
    q_lower = q.lower().strip()
    
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
    intent_data = IntentDetector.detect_intent(q_lower)
    primary_intent = intent_data['primary_intent']
    intent_confidence = intent_data['intent_confidence']
    
    try:
        # Step 3: BM25 Full-text Search (PGroonga)
        result = await db.execute(
            text("""
                SELECT 
                    p.id, p.title, p.url, p.h1, p.content,
                    p.og_title, p.og_description, p.og_image_url,
                    s.domain, s.favicon_url, s.trust_score,
                    cc.content_type, cc.type_confidence,
                    p.tracker_risk_score,
                    pgroonga_score(p.tableoid, p.ctid) AS pgroonga_relevance
                FROM pages p
                LEFT JOIN sites s ON p.site_id = s.id
                LEFT JOIN content_classifications cc ON p.id = cc.page_id
                WHERE (p.title &@~ :q OR p.h1 &@~ :q OR p.content &@~ :q)
                ORDER BY pgroonga_score(p.tableoid, p.ctid) DESC
                LIMIT :limit_val OFFSET :offset_val
            """),
            {
                "q": q,
                "limit_val": limit * 3,  # Get more results for reranking
                "offset_val": offset,
            }
        )
        rows = result.fetchall()
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
        base_results.append({
            "id": row.id,
            "title": row.title or "No title",
            "url": row.url,
            "domain": row.domain,
            "favicon": row.favicon_url,
            "og_title": row.og_title,
            "og_description": row.og_description,
            "og_image": row.og_image_url,
            "content": row.content or "",
            "content_type": row.content_type or "unknown",
            "content_confidence": float(row.type_confidence) if row.type_confidence else None,
            "tracker_risk_score": float(row.tracker_risk_score) if row.tracker_risk_score else 1.0,
        })
        
        # Base score from PGroonga (normalized)
        score = float(row.pgroonga_relevance) if row.pgroonga_relevance else 1.0
        base_scores.append(score)
    
    # Step 5: Fuzzy Reranking with Ambiguity Control
    reranked = fuzzy_reranker.rerank(
        base_results,
        q_lower,
        base_scores,
        ambiguity_control=ambiguity
    )
    
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
            "tracker_risk_score": result["tracker_risk_score"],
            "relevance_score": float(score),
        }
        
        if explain:
            item["explain"] = {
                "fuzzy_match": fuzzy_reranker.explain_relevance(result, q_lower),
                "ambiguity_control": ambiguity,
                "intent": primary_intent,
            }
        
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
    
    explanation = fuzzy_reranker.explain_relevance(result, query.lower())
    
    return {
        "query": query,
        "result": result_title,
        "explanation": explanation,
        "interpretation": _interpret_scores(explanation),
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
            return "◐ Weak match"
        else:
            return "✗ Poor match"
    
    return {
        k: interpret(v) for k, v in scores.items()
    }
