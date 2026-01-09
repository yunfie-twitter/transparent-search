from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os
import time

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@db/search_engine")

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

app = FastAPI(title="Transparent Search API")

async def get_db():
    async with async_session() as session:
        yield session

@app.get("/")
async def root():
    return {"message": "Transparent Search API is running"}

@app.get("/search")
async def search(q: str, limit: int = 10, offset: int = 0, db: AsyncSession = Depends(get_db)):
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    start_time = time.time()
    
    # Using PGroonga match operator &@~ for full text search with ranking logic
    # Score = (Content Match * 1.5) + (PageRank * 0.5)
    query = text("""
        SELECT 
            id, title, url,
            (pgroonga_score(tableoid, ctid) * 1.5) + (pagerank_score * 0.5) AS total_score,
            pgroonga_snippet_html(content, pgroonga_query_extract_keywords(:q)) AS snippet
        FROM pages
        WHERE title &@~ :q OR content &@~ :q
        ORDER BY total_score DESC
        LIMIT :limit OFFSET :offset
    """)
    
    result = await db.execute(query, {"q": q, "limit": limit, "offset": offset})
    rows = result.fetchall()
    
    data = []
    for row in rows:
        data.append({
            "id": row.id,
            "title": row.title,
            "url": row.url,
            "score": row.total_score,
            "snippet": row.snippet
        })

    return {
        "meta": {
            "took": time.time() - start_time,
            "count": len(data)
        },
        "data": data
    }
