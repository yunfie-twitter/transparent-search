from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db
from ..schemas import ClickEvent

router = APIRouter()

@router.post("/click")
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
