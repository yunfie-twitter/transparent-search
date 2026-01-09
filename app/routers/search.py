from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db
from ..utils.intent_detector import IntentDetector
import time

router = APIRouter()

@router.get("/search")
async def search(
    q: str, 
    limit: int = 10, 
    offset: int = 0, 
    explain: bool = False,
    filter_tracker_risk: str = None,  # 'clean', 'minimal', 'moderate', 'heavy', 'severe'
    content_types: str = None,  # comma-separated: 'text_article,video,forum'
    db: AsyncSession = Depends(get_db)
):
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    start = time.time()
    q_lower = q.lower()
    
    # Detect search intent from query
    intent_data = IntentDetector.detect_intent(q)
    primary_intent = intent_data['primary_intent']
    intent_confidence = intent_data['intent_confidence']
    preferred_content_type = IntentDetector.get_best_content_type_for_intent(primary_intent)
    
    # Build content type filter if specified
    content_type_filter = ""
    if content_types:
        types_list = [f"'{t.strip()}'" for t in content_types.split(',')]
        content_type_filter = f"AND cc.content_type IN ({','.join(types_list)})" 
    
    # Build tracker risk filter if specified
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
    
    # Enhanced Ranking Query with Content + Intent + Tracker Integration
    query_sql = text("""
        WITH scored AS (
            SELECT 
                p.id, p.title, p.url, p.h1, p.content,
                p.og_title, p.og_description, p.og_image_url,
                p.last_crawled_at, p.tracker_risk_score,
                s.domain, s.favicon_url, s.trust_score,
                cc.content_type, cc.type_confidence,
                ic.primary_intent, ic.intent_confidence as intent_db_confidence,
                
                -- Base PGroonga relevance
                pgroonga_score(p.tableoid, p.ctid) AS pgroonga_relevance,
                
                -- Component Scores
                CASE WHEN LOWER(p.title) LIKE '%' || :q_lower || '%' THEN 10 ELSE 0 END AS title_bonus,
                CASE WHEN LOWER(p.url) LIKE '%' || :q_lower || '%' THEN 6 ELSE 0 END AS url_bonus,
                CASE WHEN LOWER(COALESCE(p.h1, '')) LIKE '%' || :q_lower || '%' THEN 8 ELSE 0 END AS h1_bonus,
                CASE WHEN LOWER(p.title) = :q_lower THEN 5 ELSE 0 END AS exact_bonus,
                
                GREATEST(0, 10 - EXTRACT(DAY FROM NOW() - p.last_crawled_at) * 0.1) AS freshness_score,
                
                CASE 
                    WHEN LENGTH(p.content) < 100 THEN -5
                    WHEN LENGTH(p.content) > 1000 THEN 2
                    ELSE 0
                END AS quality_score,
                
                p.pagerank_score * 0.5 AS pagerank_contribution,
                LN(1 + p.click_score) * 0.3 AS click_contribution,
                
                -- NEW: Tracker Risk Score (0.1-1.0, higher is better)
                -- Factor: reduces score for high-risk pages
                (1.0 - 0.3 * (1.0 - COALESCE(p.tracker_risk_score, 1.0))) AS tracker_factor,
                
                -- NEW: Content-Intent Match Score (0.0-1.0)
                -- Bonus if content type matches search intent
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
            -- Final Score: Base Score * Tracker Factor * Content-Intent Match
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
                    (intent_match_bonus * 2.0)  -- Boost content-intent match
                ) * trust_score
                * tracker_factor  -- Apply tracker penalty
            ) AS total_score
        FROM scored
        ORDER BY total_score DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(
        query_sql, 
        {
            "q": q, 
            "q_lower": q_lower, 
            "limit": limit, 
            "offset": offset,
            "primary_intent": primary_intent,
            "preferred_content_type": preferred_content_type,
        }
    )
    rows = result.fetchall()

    took_ms = int((time.time() - start) * 1000)
    data = []
    
    for row in rows:
        item = {
            "id": row.id,
            "title": row.title,
            "url": row.url,
            "score": row.total_score,
            "domain": row.domain,
            "favicon": row.favicon_url,
            "snippet": None,
            "og": {
                "title": row.og_title,
                "description": row.og_description,
                "image": row.og_image_url,
            },
            # NEW: Content & Intent metadata
            "content_type": row.content_type,
            "content_confidence": float(row.type_confidence) if row.type_confidence else None,
            "tracker_risk_score": float(row.tracker_risk_score) if row.tracker_risk_score else 1.0,
        }
        
        # Add Explain Data if requested
        if explain:
            item["explain"] = {
                "pgroonga_base": row.pgroonga_relevance,
                "title_bonus": row.title_bonus,
                "url_bonus": row.url_bonus,
                "h1_bonus": row.h1_bonus,
                "exact_bonus": row.exact_bonus,
                "freshness": row.freshness_score,
                "quality": row.quality_score,
                "pagerank": row.pagerank_contribution,
                "click_bonus": row.click_contribution,
                "domain_trust_multiplier": row.trust_score,
                # NEW: Additional factors
                "tracker_factor": row.tracker_factor,
                "intent_match_bonus": row.intent_match_bonus,
                "tracker_risk_score": row.tracker_risk_score,
            }
        
        data.append(item)

    # Log query with intent data
    async with db.begin():
        qres = await db.execute(
            text("""
                INSERT INTO search_queries 
                (query, took_ms, results_count, primary_intent, intent_confidence) 
                VALUES (:q, :t, :c, :intent, :intent_conf) 
                RETURNING id
            """),
            {
                "q": q, 
                "t": took_ms, 
                "c": len(data),
                "intent": primary_intent,
                "intent_conf": intent_confidence,
            },
        )
        query_id = qres.scalar()

    return {
        "meta": {
            "query_id": query_id,
            "query": q,
            "took_ms": took_ms,
            "count": len(data),
            "explain_mode": explain,
            # NEW: Intent detection info
            "intent": {
                "primary": primary_intent,
                "confidence": intent_confidence,
                "preferred_content_type": preferred_content_type,
            },
        },
        "data": data,
    }


@router.get("/search/debug/intent")
async def debug_intent(q: str = Query(..., description="Query to analyze")):
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
                "avg_score": row.avg_score,
                "min_score": row.min_score,
                "max_score": row.max_score,
            }
            for row in rows
        ]
    }


@router.get("/search/debug/content-types")
async def debug_content_types(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to check content type distribution."""
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
                "avg_confidence": row.avg_confidence,
                "min_confidence": row.min_confidence,
                "max_confidence": row.max_confidence,
            }
            for row in rows
        ]
    }
