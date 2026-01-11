"""Search endpoint with caching, intent detection, and result ranking."""
import json
import hashlib
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, and_, or_
from app.core.database import get_db
from app.db.models import CrawlJob, SearchContent, PageAnalysis
from app.utils.intent_detector import IntentDetector
from app.core.cache import get_redis_client
import time

router = APIRouter(prefix="/search")


def _get_cache_key(key_type: str, value: str) -> str:
    """Generate cache key with hash."""
    return f"{key_type}:{hashlib.sha256(value.encode()).hexdigest()[:16]}"


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    explain: bool = Query(False),
    filter_quality: Optional[float] = Query(None, ge=0.0, le=1.0),
    domain: Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis_client),
):
    """Search crawled content with caching, intent detection, and ranking.
    
    Uses existing schema:
    - SearchContent for indexed pages
    - PageAnalysis for scoring and intent
    - CrawlJob for raw crawl data fallback
    """
    
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    start = time.time()
    q_lower = q.lower().strip()
    q_pattern = f"%{q_lower}%"
    
    # Cache key for full search result
    cache_key = _get_cache_key(
        "search",
        f"{q_lower}:{limit}:{offset}:{filter_quality}:{domain}:{content_type}:{explain}"
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
            print(f"Cache read error: {e}")
    
    # Detect search intent
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
        try:
            intent_data = IntentDetector.detect_intent(q_lower)
            # Cache intent for 1 hour
            if redis:
                await redis.setex(
                    intent_cache_key,
                    3600,
                    json.dumps(intent_data)
                )
        except Exception as e:
            print(f"Intent detection error: {e}")
            # Fallback intent
            intent_data = {
                "primary_intent": "informational",
                "intent_confidence": 0.5,
            }
    
    primary_intent = intent_data.get('primary_intent', 'informational')
    intent_confidence = intent_data.get('intent_confidence', 0.5)
    
    # Build WHERE clause filters
    filters = []
    
    # Text search on title, h1, description, or content
    filters.append(
        or_(
            SearchContent.title.ilike(q_pattern),
            SearchContent.h1.ilike(q_pattern),
            SearchContent.description.ilike(q_pattern),
            SearchContent.content.ilike(q_pattern),
        )
    )
    
    # Optional domain filter
    if domain:
        filters.append(SearchContent.domain.ilike(f"%{domain}%"))
    
    # Optional content type filter
    if content_type:
        filters.append(SearchContent.content_type == content_type)
    
    # Optional quality filter
    if filter_quality is not None:
        filters.append(SearchContent.quality_score >= filter_quality)
    
    # Build ranking score expression as single SQL string
    # Must concatenate strings before wrapping in text()
    rank_score_sql = f"""
        CASE WHEN LOWER(title) LIKE '{q_pattern}' THEN 10 ELSE 0 END +
        CASE WHEN LOWER(h1) LIKE '{q_pattern}' THEN 8 ELSE 0 END +
        CASE WHEN LOWER(url) LIKE '{q_pattern}' THEN 6 ELSE 0 END +
        CASE WHEN LOWER(description) LIKE '{q_pattern}' THEN 4 ELSE 0 END +
        (quality_score * 5) +
        GREATEST(0, 3 - EXTRACT(DAY FROM NOW() - last_crawled_at) * 0.01)
    """
    
    rank_score = text(rank_score_sql)
    
    try:
        # Query with ranking
        query = (
            select(SearchContent)
            .where(and_(*filters))
            .order_by(rank_score.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await db.execute(query)
        search_content_rows = result.scalars().all()
        
    except Exception as e:
        print(f"Search query error: {e}")
        # Fallback: try simple text search without ranking
        try:
            query = (
                select(SearchContent)
                .where(and_(*filters))
                .order_by(SearchContent.quality_score.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await db.execute(query)
            search_content_rows = result.scalars().all()
        except Exception as e2:
            print(f"Fallback search error: {e2}")
            search_content_rows = []
    
    # If no search content, try to get from CrawlJob for recent crawls
    if not search_content_rows:
        try:
            query = (
                select(CrawlJob)
                .where(
                    and_(
                        CrawlJob.status == "completed",
                        or_(
                            CrawlJob.title.ilike(q_pattern),
                            CrawlJob.url.ilike(q_pattern),
                            CrawlJob.content.ilike(q_pattern),
                        )
                    )
                )
                .order_by(CrawlJob.page_value_score.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await db.execute(query)
            jobs = result.scalars().all()
            
            # Convert jobs to response format
            data = []
            for job in jobs:
                item = {
                    "id": job.job_id,
                    "title": job.title or "No title",
                    "url": job.url,
                    "score": float(job.page_value_score) if job.page_value_score else 0.0,
                    "domain": job.domain,
                    "favicon": None,
                    "snippet": job.description[:200] if job.description else None,
                    "og": {
                        "title": None,
                        "description": None,
                        "image": None,
                    },
                    "content_type": "unknown",
                    "content_confidence": None,
                    "source": "crawl_job",
                }
                data.append(item)
        except Exception as e:
            print(f"Fallback crawl job error: {e}")
            data = []
    else:
        # Convert SearchContent rows to response
        data = []
        for content in search_content_rows:
            # Try to get analysis for this URL
            try:
                analysis_query = (
                    select(PageAnalysis)
                    .where(PageAnalysis.url == content.url)
                    .order_by(PageAnalysis.analyzed_at.desc())
                    .limit(1)
                )
                analysis_result = await db.execute(analysis_query)
                analysis = analysis_result.scalar_one_or_none()
            except Exception:
                analysis = None
            
            item = {
                "id": content.id,
                "title": content.title or "No title",
                "url": content.url,
                "score": float(content.quality_score) if content.quality_score else 0.5,
                "domain": content.domain,
                "favicon": None,
                "snippet": content.description[:200] if content.description else None,
                "og": {
                    "title": content.og_title,
                    "description": None,
                    "image": content.og_image_url,
                },
                "content_type": content.content_type or "unknown",
                "content_confidence": None,
                "source": "search_content",
            }
            
            if analysis:
                item["analysis"] = {
                    "spam_score": float(analysis.spam_score),
                    "risk_level": analysis.risk_level,
                    "query_intent": analysis.query_intent,
                    "relevance_score": float(analysis.relevance_score),
                }
            
            if explain and analysis:
                item["explain"] = {
                    "spam_score": float(analysis.spam_score),
                    "content_quality": float(analysis.content_quality_score),
                    "freshness": float(analysis.freshness_score),
                    "relevance": float(analysis.relevance_score),
                    "intent_match": float(analysis.intent_match_score),
                }
            
            data.append(item)
    
    took_ms = int((time.time() - start) * 1000)
    
    response = {
        "meta": {
            "query": q,
            "took_ms": took_ms,
            "count": len(data),
            "limit": limit,
            "offset": offset,
            "explain_mode": explain,
            "cache_hit": False,
            "intent": {
                "primary": primary_intent,
                "confidence": intent_confidence,
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
        except Exception as e:
            print(f"Cache write error: {e}")
    
    return response


@router.get("/debug/intent")
async def debug_intent(q: str = Query(..., min_length=1, max_length=500)):
    """Debug endpoint to test intent detection."""
    try:
        intent_data = IntentDetector.detect_intent(q)
        return {
            "query": q,
            "intent_analysis": intent_data,
        }
    except Exception as e:
        return {
            "query": q,
            "error": str(e),
            "intent_analysis": {
                "primary_intent": "informational",
                "intent_confidence": 0.5,
            },
        }


@router.get("/debug/schema")
async def debug_schema(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to check available tables and content."""
    try:
        # Check SearchContent count
        search_result = await db.execute(
            text("""SELECT COUNT(*) as count FROM search_content""")
        )
        search_count = search_result.scalar()
        
        # Check PageAnalysis count
        analysis_result = await db.execute(
            text("""SELECT COUNT(*) as count FROM page_analysis""")
        )
        analysis_count = analysis_result.scalar()
        
        # Check CrawlJob count
        job_result = await db.execute(
            text("""SELECT COUNT(*) as count FROM crawl_jobs""")
        )
        job_count = job_result.scalar()
        
        # Sample SearchContent
        sample_result = await db.execute(
            text("""SELECT url, title, domain, content_type FROM search_content LIMIT 5""")
        )
        samples = sample_result.fetchall()
        
        return {
            "tables": {
                "search_content": {
                    "count": search_count,
                    "samples": [
                        {
                            "url": s[0],
                            "title": s[1],
                            "domain": s[2],
                            "content_type": s[3],
                        }
                        for s in samples
                    ],
                },
                "page_analysis": {"count": analysis_count},
                "crawl_jobs": {"count": job_count},
            },
        }
    except Exception as e:
        return {
            "error": str(e),
            "tables": {},
        }


@router.post("/cache/invalidate")
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
