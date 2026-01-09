from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db
from arq import create_pool
from arq.connections import RedisSettings
import os

router = APIRouter()

class TrustUpdate(BaseModel):
    domain: str
    trust_score: float

class CrawlRequest(BaseModel):
    url: str
    max_pages: int = 100
    max_depth: int = 3

@router.patch("/sites/trust")
async def update_trust_score(payload: TrustUpdate, db: AsyncSession = Depends(get_db)):
    """Manually update domain trust score."""
    async with db.begin():
        result = await db.execute(
            text("UPDATE sites SET trust_score = :score WHERE domain = :domain RETURNING id"),
            {"score": payload.trust_score, "domain": payload.domain}
        )
        if not result.scalar():
            raise HTTPException(status_code=404, detail="Site not found")
    return {"ok": True, "domain": payload.domain, "new_score": payload.trust_score}

@router.post("/sites/calculate-trust")
async def calculate_trust_scores(db: AsyncSession = Depends(get_db)):
    """Automatically update trust scores based on average PageRank of pages."""
    # Logic: normalize avg pagerank to trust score (simple implementation)
    # Trust = 1.0 + (AvgPageRank - 1.0) * 0.5 (Dampening factor)
    async with db.begin():
        await db.execute(text("""
            UPDATE sites s
            SET trust_score = 1.0 + (
                SELECT COALESCE(AVG(p.pagerank_score), 1.0) - 1.0
                FROM pages p 
                WHERE p.site_id = s.id
            ) * 0.5
        """))
    return {"message": "Trust scores recalculated based on PageRank"}

@router.post("/crawl")
async def trigger_crawl(payload: CrawlRequest):
    """Trigger a distributed crawl job."""
    redis = await create_pool(RedisSettings(host='redis', port=6379))
    await redis.enqueue_job('crawl_domain_task', payload.url, payload.max_pages, payload.max_depth)
    return {"message": "Crawl job enqueued", "target": payload.url}
