from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db

router = APIRouter()

@router.get("/suggest")
async def suggest(q: str, limit: int = 10, db: AsyncSession = Depends(get_db)):
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    # 1. Popular user queries (History)
    history_query = text("""
        SELECT query, COUNT(*) as cnt
        FROM search_queries
        WHERE query ILIKE :prefix
        GROUP BY query
        ORDER BY cnt DESC
        LIMIT :limit
    """)
    
    # 2. Page titles (Content)
    content_query = text("""
        SELECT DISTINCT title
        FROM pages
        WHERE title IS NOT NULL AND title &^ :q
        ORDER BY title
        LIMIT :limit
    """)

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

    # Fill remaining with content suggestions
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
