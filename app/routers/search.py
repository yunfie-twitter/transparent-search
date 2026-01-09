from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db
import time

router = APIRouter()

@router.get("/search")
async def search(
    q: str, 
    limit: int = 10, 
    offset: int = 0, 
    explain: bool = False,
    db: AsyncSession = Depends(get_db)
):
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    start = time.time()
    q_lower = q.lower()

    # Explainable Ranking Query
    # Includes 'sites' join for Trust Score
    query_sql = text("""
        WITH scored AS (
            SELECT 
                p.id, p.title, p.url, p.h1, p.content,
                p.og_title, p.og_description, p.og_image_url,
                p.last_crawled_at,
                s.domain, s.favicon_url, s.trust_score,
                
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
                LN(1 + p.click_score) * 0.3 AS click_contribution
                
            FROM pages p
            LEFT JOIN sites s ON p.site_id = s.id
            WHERE (p.title &@~ :q OR p.h1 &@~ :q OR p.content &@~ :q)
        )
        SELECT 
            *,
            -- Total Score Calculation
            (
                (
                    pgroonga_relevance * 1.5 +
                    title_bonus +
                    url_bonus +
                    h1_bonus +
                    exact_bonus +
                    pgroonga_relevance + -- body_score approximation
                    freshness_score +
                    quality_score +
                    pagerank_contribution +
                    click_contribution
                ) * trust_score -- Multiply by Domain Trust
            ) AS total_score
        FROM scored
        ORDER BY total_score DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(query_sql, {"q": q, "q_lower": q_lower, "limit": limit, "offset": offset})
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
            "snippet": None, # Should generate snippet separately if needed
            "og": {
                "title": row.og_title,
                "description": row.og_description,
                "image": row.og_image_url,
            }
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
                "domain_trust_multiplier": row.trust_score
            }
        
        data.append(item)

    # Log query
    async with db.begin():
        qres = await db.execute(
            text("INSERT INTO search_queries (query, took_ms, results_count) VALUES (:q, :t, :c) RETURNING id"),
            {"q": q, "t": took_ms, "c": len(data)},
        )
        query_id = qres.scalar()

    return {
        "meta": {
            "query_id": query_id,
            "took_ms": took_ms,
            "count": len(data),
            "explain_mode": explain
        },
        "data": data,
    }
