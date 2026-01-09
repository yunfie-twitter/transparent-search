from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db
import time

router = APIRouter()

@router.get("/search")
async def search(q: str, limit: int = 10, offset: int = 0, db: AsyncSession = Depends(get_db)):
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    start = time.time()
    q_lower = q.lower()

    # Additive Scoring Logic (SQL-based)
    # - Title match: +10 per query word
    # - URL match: +6 per query word
    # - H1 match: +8 per query word
    # - Body match: +1 per occurrence
    # - Exact phrase in title: +5
    # - Freshness: newer pages get bonus (days_old penalty capped at 10)
    # - Content quality: short content penalty, long content bonus
    # - PageRank: +0.5 * pagerank_score
    # - Click score: +0.3 * LN(1 + click_score)
    
    query_primary = text("""
        WITH scored AS (
            SELECT 
                id, title, url, h1, content,
                og_title, og_description, og_image_url,
                last_crawled_at,
                -- Base PGroonga relevance
                pgroonga_score(tableoid, ctid) AS pgroonga_relevance,
                
                -- Title bonus: +10 if query in title (case insensitive)
                CASE WHEN LOWER(title) LIKE '%' || :q_lower || '%' THEN 10 ELSE 0 END AS title_bonus,
                
                -- URL bonus: +6 if query in URL
                CASE WHEN LOWER(url) LIKE '%' || :q_lower || '%' THEN 6 ELSE 0 END AS url_bonus,
                
                -- H1 bonus: +8 if query in h1
                CASE WHEN LOWER(COALESCE(h1, '')) LIKE '%' || :q_lower || '%' THEN 8 ELSE 0 END AS h1_bonus,
                
                -- Exact phrase bonus: +5
                CASE WHEN LOWER(title) = :q_lower THEN 5 ELSE 0 END AS exact_bonus,
                
                -- Body match count (simplified: just check presence for now, PGroonga handles frequency)
                pgroonga_score(tableoid, ctid) AS body_score,
                
                -- Freshness: penalize old pages (days since crawl, capped at 10)
                GREATEST(0, 10 - EXTRACT(DAY FROM NOW() - last_crawled_at) * 0.1) AS freshness_score,
                
                -- Content quality
                CASE 
                    WHEN LENGTH(content) < 100 THEN -5
                    WHEN LENGTH(content) > 1000 THEN 2
                    ELSE 0
                END AS quality_score,
                
                -- PageRank
                pagerank_score * 0.5 AS pagerank_contribution,
                
                -- Click learning
                LN(1 + click_score) * 0.3 AS click_contribution
                
            FROM pages
            WHERE (title &@~ :q OR h1 &@~ :q OR content &@~ :q)
        )
        SELECT 
            id, title, url, og_title, og_description, og_image_url,
            pgroonga_snippet_html(content, pgroonga_query_extract_keywords(:q)) AS snippet,
            (
                pgroonga_relevance * 1.5 +
                title_bonus +
                url_bonus +
                h1_bonus +
                exact_bonus +
                body_score +
                freshness_score +
                quality_score +
                pagerank_contribution +
                click_contribution
            ) AS total_score
        FROM scored
        ORDER BY total_score DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(query_primary, {"q": q, "q_lower": q_lower, "limit": limit, "offset": offset})
    rows = result.fetchall()

    used_fuzzy = False
    did_you_mean = None

    # Fallback: pg_trgm fuzzy search on title when no results
    if len(rows) == 0:
        used_fuzzy = True
        query_fuzzy = text("""
            SELECT 
                id, title, url,
                (similarity(title, :q) * 1.2)
                + (pagerank_score * 0.5)
                + (LN(1 + click_score) * 0.3) AS total_score,
                NULL::text AS snippet,
                og_title, og_description, og_image_url
            FROM pages
            WHERE title IS NOT NULL
              AND similarity(title, :q) > 0.2
            ORDER BY similarity(title, :q) DESC
            LIMIT :limit OFFSET :offset
        """)
        result2 = await db.execute(query_fuzzy, {"q": q, "limit": limit, "offset": offset})
        rows = result2.fetchall()

        # Lightweight "did you mean" from best fuzzy hit
        if len(rows) > 0 and rows[0].title:
            did_you_mean = rows[0].title

    took_ms = int((time.time() - start) * 1000)

    data = []
    for row in rows:
        data.append(
            {
                "id": row.id,
                "title": row.title,
                "url": row.url,
                "score": row.total_score,
                "snippet": row.snippet if hasattr(row, 'snippet') else None,
                "og": {
                    "title": row.og_title,
                    "description": row.og_description,
                    "image": row.og_image_url,
                },
            }
        )

    # Log query (and return query_id for click learning)
    async with db.begin():
        qres = await db.execute(
            text(
                "INSERT INTO search_queries (query, took_ms, results_count) VALUES (:q, :t, :c) RETURNING id"
            ),
            {"q": q, "t": took_ms, "c": len(data)},
        )
        query_id = qres.scalar()

    return {
        "meta": {
            "query_id": query_id,
            "took_ms": took_ms,
            "count": len(data),
            "used_fuzzy": used_fuzzy,
            "did_you_mean": did_you_mean,
        },
        "data": data,
    }
