import json
import hashlib
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.utils.intent_detector import IntentDetector
from app.core.cache import get_redis_client
import time

router = APIRouter()

def _get_cache_key(key_type: str, value: str) -> str:
    """Generate cache key with hash."""
    return f"{key_type}:{hashlib.sha256(value.encode()).hexdigest()[:16]}"

@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    explain: bool = Query(False),
    filter_tracker_risk: Optional[str] = Query(None, pattern="^(clean|minimal|moderate|heavy|severe)$"),
    content_types: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis_client),
):
    """Search with caching, intent detection, content-type matching, and tracker filtering."""
    
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    start = time.time()
    q_lower = q.lower().strip()
    
    # Cache key for full search result
    cache_key = _get_cache_key(
        "search",
        f"{q_lower}:{limit}:{offset}:{filter_tracker_risk}:{content_types}:{explain}"
    )
    
    # Try to get from cache
    if redis:
        try:
            cached_result = await redis.get(cache_key)
            if cached_result:
                result = json.loads(cached_result)
                result["meta"]["cache_hit"] = True
                result["meta"]["took_ms"] = int((time.time() - start) * 1000)
                return result
        except Exception as e:
            # If cache fails, continue with normal flow
            print(f"Cache read error: {e}")
    
    # Detect search intent (cache this separately)
    intent_cache_key = _get_cache_key("intent", q_lower)
    intent_data = None
    
    if redis:
        try:
            cached_intent = await redis.get(intent_cache_key)
            if cached_intent:
                intent_data = json.loads(cached_intent)
        except Exception:
            pass
    
    # If not cached, detect intent
    if not intent_data:
        intent_data = IntentDetector.detect_intent(q_lower)
        # Cache intent for 1 hour
        if redis:
            try:
                await redis.setex(
                    intent_cache_key,
                    3600,
                    json.dumps(intent_data)
                )
            except Exception:
                pass
    
    primary_intent = intent_data['primary_intent']
    intent_confidence = intent_data['intent_confidence']
    preferred_content_type = IntentDetector.get_best_content_type_for_intent(primary_intent)
    
    # Build content type filter
    content_type_filter = ""
    if content_types:
        valid_types = {'text_article', 'manga', 'video', 'image', 'forum', 'tool', 'unknown'}
        types_list = [
            f"'{t.strip()}'" for t in content_types.split(',')
            if t.strip() in valid_types
        ]
        if types_list:
            content_type_filter = f"AND cc.content_type IN ({','.join(types_list)})" 
    
    # Build tracker risk filter
    tracker_risk_filter = ""
    if filter_tracker_risk:
        risk_thresholds = {
            'clean': 0.9,
            'minimal': 0.7,
            'moderate': 0.5,
            'heavy': 0.3,
        }
        threshold = risk_thresholds.get(filter_tracker_risk, 0.0)
        tracker_risk_filter = f"AND p.tracker_risk_score >= {threshold}"
    
    # Enhanced ranking query
    query_sql = text("""
        WITH scored AS (
            SELECT 
                p.id, p.title, p.url, p.h1, p.content,
                p.og_title, p.og_description, p.og_image_url,
                p.last_crawled_at, p.tracker_risk_score,
                s.domain, s.favicon_url, s.trust_score,
                cc.content_type, cc.type_confidence,
                ic.primary_intent, ic.intent_confidence as intent_db_confidence,
                
                pgroonga_score(p.tableoid, p.ctid) AS pgroonga_relevance,
                
                CASE WHEN LOWER(p.title) LIKE :q_pattern THEN 10 ELSE 0 END AS title_bonus,
                CASE WHEN LOWER(p.url) LIKE :q_pattern THEN 6 ELSE 0 END AS url_bonus,
                CASE WHEN LOWER(COALESCE(p.h1, '')) LIKE :q_pattern THEN 8 ELSE 0 END AS h1_bonus,
                CASE WHEN LOWER(p.title) = :q_lower THEN 5 ELSE 0 END AS exact_bonus,
                
                GREATEST(0, 10 - EXTRACT(DAY FROM NOW() - p.last_crawled_at) * 0.1) AS freshness_score,
                
                CASE 
                    WHEN LENGTH(p.content) < 100 THEN -5
                    WHEN LENGTH(p.content) > 1000 THEN 2
                    ELSE 0
                END AS quality_score,
                
                COALESCE(p.pagerank_score, 0) * 0.5 AS pagerank_contribution,
                LN(1 + COALESCE(p.click_score, 0)) * 0.3 AS click_contribution,
                
                (1.0 - 0.3 * (1.0 - COALESCE(p.tracker_risk_score, 1.0))) AS tracker_factor,
                
                CASE 
                    WHEN cc.content_type IS NULL THEN 0.5
                    WHEN cc.content_type = :preferred_content_type THEN 1.0
                    WHEN (
                        (:primary_intent = 'question' AND cc.content_type IN ('text_article', 'forum')) OR
                        (:primary_intent = 'debugging' AND cc.content_type IN ('text_article', 'forum')) OR
                        (:primary_intent = 'transactional' AND cc.content_type = 'tool') OR
                        (:primary_intent = 'product_research' AND cc.content_type IN ('forum', 'text_article')) OR
                        (:primary_intent = 'research' AND cc.content_type = 'text_article') OR
                        (:primary_intent = 'navigation' AND cc.content_type = 'tool')
                    ) THEN 0.85
                    ELSE 0.6
                END AS intent_match_bonus
                
            FROM pages p
            LEFT JOIN sites s ON p.site_id = s.id
            LEFT JOIN content_classifications cc ON p.id = cc.page_id
            LEFT JOIN query_clusters qc ON TRUE
            LEFT JOIN intent_classifications ic ON qc.id = ic.query_cluster_id
            WHERE (p.title &@~ :q OR p.h1 &@~ :q OR p.content &@~ :q)
            """ + tracker_risk_filter + content_type_filter + """
        )
        SELECT 
            *,
            (
                (
                    pgroonga_relevance * 1.5 +
                    title_bonus +
                    url_bonus +
                    h1_bonus +
                    exact_bonus +
                    pgroonga_relevance +
                    freshness_score +
                    quality_score +
                    pagerank_contribution +
                    click_contribution +
                    (intent_match_bonus * 2.0)
                ) * trust_score
                * tracker_factor
            ) AS total_score
        FROM scored
        ORDER BY total_score DESC
        LIMIT :limit OFFSET :offset
    """)

    try:
        result = await db.execute(
            query_sql, 
            {
                "q": q, 
                "q_lower": q_lower,
                "q_pattern": f"%{q_lower}%",
                "limit": limit, 
                "offset": offset,
                "primary_intent": primary_intent,
                "preferred_content_type": preferred_content_type,
            }
        )
        rows = result.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")

    took_ms = int((time.time() - start) * 1000)
    data = []
    
    for row in rows:
        item = {
            "id": row.id,
            "title": row.title or "No title",
            "url": row.url,
            "score": float(row.total_score),
            "domain": row.domain,
            "favicon": row.favicon_url,
            "snippet": None,
            "og": {
                "title": row.og_title,
                "description": row.og_description,
                "image": row.og_image_url,
            },
            "content_type": row.content_type or "unknown",
            "content_confidence": float(row.type_confidence) if row.type_confidence else None,
            "tracker_risk_score": float(row.tracker_risk_score) if row.tracker_risk_score else 1.0,
        }
        
        if explain:
            item["explain"] = {
                "pgroonga_base": float(row.pgroonga_relevance),
                "title_bonus": float(row.title_bonus),
                "url_bonus": float(row.url_bonus),
                "h1_bonus": float(row.h1_bonus),
                "exact_bonus": float(row.exact_bonus),
                "freshness": float(row.freshness_score),
                "quality": float(row.quality_score),
                "pagerank": float(row.pagerank_contribution),
                "click_bonus": float(row.click_contribution),
                "domain_trust_multiplier": float(row.trust_score),
                "tracker_factor": float(row.tracker_factor),
                "intent_match_bonus": float(row.intent_match_bonus),
                "tracker_risk_score": float(row.tracker_risk_score),
            }
        
        data.append(item)

    # Log search query
    try:
        async with db.begin():
            await db.execute(
                text("""
                    INSERT INTO search_queries 
                    (query, took_ms, results_count) 
                    VALUES (:q, :t, :c)
                """),
                {
                    "q": q, 
                    "t": took_ms, 
                    "c": len(data),
                },
            )
    except Exception:
        # If query logging fails, continue anyway
        pass

    response = {
        "meta": {
            "query_id": None,
            "query": q,
            "took_ms": took_ms,
            "count": len(data),
            "explain_mode": explain,
            "cache_hit": False,
            "intent": {
                "primary": primary_intent,
                "confidence": intent_confidence,
                "preferred_content_type": preferred_content_type,
            },
        },
        "data": data,
    }
    
    # Cache successful result for 5 minutes
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


@router.get("/search/debug/intent")
async def debug_intent(q: str = Query(..., min_length=1, max_length=500)):
    """Debug endpoint to test intent detection."""
    intent_data = IntentDetector.detect_intent(q)
    best_content = IntentDetector.get_best_content_type_for_intent(intent_data['primary_intent'])
    
    return {
        "query": q,
        "intent_analysis": intent_data,
        "recommended_content_type": best_content,
        "intent_match_examples": {
            "text_article": IntentDetector.calculate_intent_match_score(
                intent_data['primary_intent'], 'text_article'
            ),
            "forum": IntentDetector.calculate_intent_match_score(
                intent_data['primary_intent'], 'forum'
            ),
            "video": IntentDetector.calculate_intent_match_score(
                intent_data['primary_intent'], 'video'
            ),
            "tool": IntentDetector.calculate_intent_match_score(
                intent_data['primary_intent'], 'tool'
            ),
            "manga": IntentDetector.calculate_intent_match_score(
                intent_data['primary_intent'], 'manga'
            ),
        },
    }


@router.get("/search/debug/tracker-risk")
async def debug_tracker_risk(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to check tracker risk distribution."""
    try:
        result = await db.execute(
            text("""
                SELECT 
                    CASE 
                        WHEN tracker_risk_score >= 0.9 THEN 'clean'
                        WHEN tracker_risk_score >= 0.7 THEN 'minimal'
                        WHEN tracker_risk_score >= 0.5 THEN 'moderate'
                        WHEN tracker_risk_score >= 0.3 THEN 'heavy'
                        ELSE 'severe'
                    END as risk_category,
                    COUNT(*) as count,
                    ROUND(AVG(tracker_risk_score)::numeric, 3) as avg_score,
                    ROUND(MIN(tracker_risk_score)::numeric, 3) as min_score,
                    ROUND(MAX(tracker_risk_score)::numeric, 3) as max_score
                FROM pages
                WHERE tracker_risk_score IS NOT NULL
                GROUP BY risk_category
                ORDER BY avg_score DESC
            """)
        )
        rows = result.fetchall()
        return {
            "distribution": [
                {
                    "category": row.risk_category,
                    "count": row.count,
                    "avg_score": float(row.avg_score),
                    "min_score": float(row.min_score),
                    "max_score": float(row.max_score),
                }
                for row in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")


@router.get("/search/debug/content-types")
async def debug_content_types(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to check content type distribution."""
    try:
        result = await db.execute(
            text("""
                SELECT 
                    content_type,
                    COUNT(*) as count,
                    ROUND(AVG(type_confidence)::numeric, 3) as avg_confidence,
                    ROUND(MIN(type_confidence)::numeric, 3) as min_confidence,
                    ROUND(MAX(type_confidence)::numeric, 3) as max_confidence
                FROM content_classifications
                WHERE content_type IS NOT NULL
                GROUP BY content_type
                ORDER BY count DESC
            """)
        )
        rows = result.fetchall()
        return {
            "distribution": [
                {
                    "content_type": row.content_type,
                    "count": row.count,
                    "avg_confidence": float(row.avg_confidence),
                    "min_confidence": float(row.min_confidence),
                    "max_confidence": float(row.max_confidence),
                }
                for row in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")


@router.post("/search/cache/invalidate")
async def invalidate_cache(redis=Depends(get_redis_client)):
    """Invalidate all search cache."""
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    try:
        # Delete all search:* keys
        keys = await redis.keys("search:*")
        if keys:
            await redis.delete(*keys)
        
        # Delete all intent:* keys
        intent_keys = await redis.keys("intent:*")
        if intent_keys:
            await redis.delete(*intent_keys)
        
        return {
            "status": "success",
            "message": f"Invalidated {len(keys) + len(intent_keys)} cache entries"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache invalidation error: {str(e)}")
