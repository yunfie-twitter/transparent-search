"""FastAPI router for crawl-related endpoints."""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.db.database import get_db
from app.services.crawler import crawler_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/crawl",
    tags=["crawl"],
    responses={404: {"description": "Not found"}},
)


@router.post("/start")
async def start_crawl(domain: str, db: AsyncSession = Depends(get_db)):
    """Start a new crawl session for a domain."""
    try:
        session = await crawler_service.create_crawl_session(domain=domain)
        return {
            "status": "success",
            "session_id": session.session_id,
            "domain": session.domain,
            "created_at": session.created_at.isoformat(),
        }
    except Exception as e:
        logger.error(f"Error starting crawl: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/job/create")
async def create_job(
    session_id: str,
    domain: str,
    url: str,
    depth: int = 0,
    max_depth: int = 3,
    enable_js_rendering: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Create a new crawl job."""
    try:
        job = await crawler_service.create_crawl_job(
            session_id=session_id,
            domain=domain,
            url=url,
            depth=depth,
            max_depth=max_depth,
            enable_js_rendering=enable_js_rendering,
        )
        return {
            "status": "success",
            "job_id": job.job_id,
            "url": job.url,
            "priority": job.priority,
            "page_value_score": job.page_value_score,
            "created_at": job.created_at.isoformat(),
        }
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/job/status")
async def update_job_status(
    job_id: str,
    status: str,
    db: AsyncSession = Depends(get_db),
):
    """Update crawl job status."""
    try:
        job = await crawler_service.update_crawl_job_status(
            job_id=job_id,
            status=status,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "status": "success",
            "job_id": job.job_id,
            "new_status": job.status,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/invalidate")
async def invalidate_domain(
    domain: str,
    db: AsyncSession = Depends(get_db),
):
    """Invalidate all caches for a domain."""
    try:
        await crawler_service.invalidate_domain_cache(domain)
        return {
            "status": "success",
            "domain": domain,
            "message": "Cache invalidated",
        }
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_crawl_stats(
    domain: str,
    db: AsyncSession = Depends(get_db),
):
    """Get crawl statistics for a domain."""
    try:
        from sqlalchemy import select, func
        from app.db.models import CrawlSession, CrawlJob
        
        stmt = select(func.count(CrawlSession.session_id)).where(
            CrawlSession.domain == domain
        )
        result = await db.execute(stmt)
        session_count = result.scalar() or 0
        
        stmt = select(func.count(CrawlJob.job_id)).where(
            CrawlJob.domain == domain
        )
        result = await db.execute(stmt)
        job_count = result.scalar() or 0
        
        return {
            "domain": domain,
            "total_sessions": session_count,
            "total_jobs": job_count,
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
