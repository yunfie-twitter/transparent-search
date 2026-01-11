"""Crawler API router - handles all crawl-related endpoints."""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import logging
import random

from app.core.database import get_db
from app.services.crawler import crawler_service
from app.db.models import CrawlSession, CrawlJob

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="",
    tags=["crawl"],
    responses={404: {"description": "Not found"}},
)


@router.post("/start")
async def start_crawl(
    domain: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db)
):
    """
    Start a new crawl session for a domain.
    
    Args:
        domain: Target domain to crawl
        db: Database session
        
    Returns:
        Crawl session details with session_id
    """
    try:
        session = await crawler_service.create_crawl_session(domain=domain)
        return {
            "status": "success",
            "session_id": session.session_id,
            "domain": session.domain,
            "created_at": session.created_at.isoformat() if hasattr(session, 'created_at') else None,
        }
    except Exception as e:
        logger.error(f"Error starting crawl for {domain}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/job/create")
async def create_job(
    session_id: str = Query(..., min_length=1),
    domain: str = Query(..., min_length=1),
    url: str = Query(..., min_length=5),
    depth: int = Query(0, ge=0, le=10),
    max_depth: int = Query(3, ge=1, le=15),
    enable_js_rendering: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new crawl job.
    
    Args:
        session_id: Associated crawl session ID
        domain: Target domain
        url: URL to crawl
        depth: Current crawl depth
        max_depth: Maximum crawl depth
        enable_js_rendering: Enable JavaScript rendering
        db: Database session
        
    Returns:
        Created job details
    """
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
            "priority": job.priority if hasattr(job, 'priority') else None,
            "page_value_score": job.page_value_score if hasattr(job, 'page_value_score') else None,
            "created_at": job.created_at.isoformat() if hasattr(job, 'created_at') else None,
        }
    except Exception as e:
        logger.error(f"Error creating job for {url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/job/auto")
async def auto_crawl(
    max_jobs: int = Query(1, ge=1, le=100),
    max_depth: int = Query(3, ge=1, le=15),
    db: AsyncSession = Depends(get_db),
):
    """
    Automatically start crawl jobs for random registered sites until stopped.
    
    Args:
        max_jobs: Maximum number of jobs to create per call
        max_depth: Maximum crawl depth for each job
        db: Database session
        
    Returns:
        Auto crawl session details
    """
    try:
        # Get all unique domains from existing crawl sessions
        stmt = select(func.distinct(CrawlSession.domain)).order_by(CrawlSession.domain)
        result = await db.execute(stmt)
        domains = [row[0] for row in result.fetchall()]
        
        if not domains:
            raise HTTPException(
                status_code=400,
                detail="No registered sites found. Please create at least one crawl session first."
            )
        
        # Randomly select domains
        selected_domains = random.sample(domains, min(len(domains), max_jobs))
        
        created_jobs = []
        for domain in selected_domains:
            try:
                # Create session
                session = await crawler_service.create_crawl_session(domain=domain)
                
                # Create initial crawl job for domain root
                base_url = f"https://{domain}"
                job = await crawler_service.create_crawl_job(
                    session_id=session.session_id,
                    domain=domain,
                    url=base_url,
                    depth=0,
                    max_depth=max_depth,
                    enable_js_rendering=False,
                )
                
                created_jobs.append({
                    "domain": domain,
                    "session_id": session.session_id,
                    "job_id": job.job_id,
                    "url": job.url,
                })
                logger.info(f"✅ Auto-created job for {domain}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to auto-crawl {domain}: {e}")
                continue
        
        if not created_jobs:
            raise HTTPException(
                status_code=500,
                detail="Failed to create any crawl jobs"
            )
        
        return {
            "status": "success",
            "message": f"Auto-crawl started for {len(created_jobs)} site(s)",
            "total_domains": len(domains),
            "crawled_domains": len(created_jobs),
            "jobs": created_jobs,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in auto crawl: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/job/status")
async def update_job_status(
    job_id: str = Query(..., min_length=1),
    status: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    """
    Update crawl job status.
    
    Args:
        job_id: Job ID to update
        status: New status (pending, running, completed, failed)
        db: Database session
        
    Returns:
        Updated job details
    """
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
            "new_status": job.status if hasattr(job, 'status') else status,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/invalidate")
async def invalidate_domain(
    domain: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    """
    Invalidate all caches for a domain.
    
    Args:
        domain: Target domain
        db: Database session
        
    Returns:
        Invalidation confirmation
    """
    try:
        await crawler_service.invalidate_domain_cache(domain)
        return {
            "status": "success",
            "domain": domain,
            "message": "Cache invalidated for domain",
        }
    except Exception as e:
        logger.error(f"Error invalidating cache for {domain}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_crawl_stats(
    domain: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    """
    Get crawl statistics for a domain.
    
    Args:
        domain: Target domain
        db: Database session
        
    Returns:
        Crawl statistics (session count, job count)
    """
    try:
        # Count sessions
        stmt = select(func.count(CrawlSession.session_id)).where(
            CrawlSession.domain == domain
        )
        result = await db.execute(stmt)
        session_count = result.scalar() or 0
        
        # Count jobs
        stmt = select(func.count(CrawlJob.job_id)).where(
            CrawlJob.domain == domain
        )
        result = await db.execute(stmt)
        job_count = result.scalar() or 0
        
        return {
            "status": "success",
            "domain": domain,
            "total_sessions": session_count,
            "total_jobs": job_count,
        }
    except Exception as e:
        logger.error(f"Error getting stats for {domain}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ["router"]
