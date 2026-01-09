from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os
import time

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@db/search_engine")

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

app = FastAPI(title="Transparent Search API")

async def get_db():
    async with async_session() as session:
        yield session

@app.get("/")
async def root():
    return {"message": "Transparent Search API is running"}

@app.get("/suggest")
async def suggest(q: str, limit: int = 10, db: AsyncSession = Depends(get_db)):
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    # 1. Popular user queries (History)
    # Using pg_trgm ILIKE or standard LIKE with the new index
    # Group by query to get unique suggestions, ordered by popularity (count)
    history_query = text("""
        SELECT query, COUNT(*) as cnt
        FROM search_queries
        WHERE query ILIKE :prefix
        GROUP BY query
        ORDER BY cnt DESC
        LIMIT :limit
    """)
    
    # 2. Page titles (Content)
    # Using PGroonga prefix match (&^)
    content_query = text("""
        SELECT DISTINCT title
        FROM pages
        WHERE title IS NOT NULL AND title &^ :q
        ORDER BY title
        LIMIT :limit
    """)

    # Execute both
    res_history = await db.execute(history_query, {"prefix": f"{q}%", "limit": limit})
    history_suggestions = [r.query for r in res_history.fetchall()]

    suggestions = []
    seen = set()

    # Prioritize history
    for s in history_suggestions:
        s_clean = s.strip()
        if s_clean and s_clean not in seen:
            suggestions.append(s_clean)
            seen.add(s_clean)

    # Fill remaining with content suggestions if needed
    if len(suggestions) < limit:
        res_content = await db.execute(content_query, {"q": q, "limit": limit})
        content_titles = [r.title for r in res_content.fetchall()]
        
        for t in content_titles:
            t_clean = t.strip()
            if t_clean and t_clean not in seen:
                suggestions.append(t_clean)
                seen.add(t_clean)
                if len(suggestions) >= limit:
                    break

    return {"meta": {"count": len(suggestions)}, "data": suggestions}

class ClickEvent(BaseModel):
    query_id: int
    page_id: int

@app.post("/click")
async def click(event: ClickEvent, db: AsyncSession = Depends(get_db)):
    # Log click + increment click_score for simple online learning
    async with db.begin():
        await db.execute(
            text("INSERT INTO clicks (query_id, page_id) VALUES (:qid, :pid)"),
            {"qid": event.query_id, "pid": event.page_id},
        )
        await db.execute(
            text("UPDATE pages SET click_score = click_score + 1 WHERE id = :pid"),
            {"pid": event.page_id},
        )

    return {"ok": True}

@app.get("/search")
async def search(q: str, limit: int = 10, offset: int = 0, db: AsyncSession = Depends(get_db)):
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    start = time.time()

    # Primary: PGroonga full-text
    query_primary = text("""
        SELECT 
            id, title, url,
            (pgroonga_score(tableoid, ctid) * 1.5)
            + (pagerank_score * 0.5)
            + (LN(1 + click_score) * 0.3) AS total_score,
            pgroonga_snippet_html(content, pgroonga_query_extract_keywords(:q)) AS snippet,
            og_title, og_description, og_image_url
        FROM pages
        WHERE title &@~ :q OR content &@~ :q
        ORDER BY total_score DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(query_primary, {"q": q, "limit": limit, "offset": offset})
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
                "snippet": row.snippet,
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
