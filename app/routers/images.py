from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db
import time

router = APIRouter()

@router.get("/images")
async def image_search(q: str, limit: int = 20, offset: int = 0, db: AsyncSession = Depends(get_db)):
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    start = time.time()
    
    # Image Search using PGroonga on alt_text
    query = text("""
        SELECT 
            i.id, i.url, i.alt_text,
            p.title as page_title, p.url as page_url,
            pgroonga_score(i.tableoid, i.ctid) AS score
        FROM images i
        JOIN pages p ON i.page_id = p.id
        WHERE i.alt_text &@~ :q
        ORDER BY score DESC
        LIMIT :limit OFFSET :offset
    """)
    
    result = await db.execute(query, {"q": q, "limit": limit, "offset": offset})
    rows = result.fetchall()
    
    took_ms = int((time.time() - start) * 1000)
    data = []
    for row in rows:
        data.append({
            "id": row.id,
            "image_url": row.url,
            "alt": row.alt_text,
            "page": {
                "title": row.page_title,
                "url": row.page_url
            },
            "score": row.score
        })

    return {
        "meta": {"took_ms": took_ms, "count": len(data)},
        "data": data
    }
