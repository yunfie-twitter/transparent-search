"""Admin crawl management endpoints."""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid

from ..utils.sitemap_manager import sitemap_manager
from ..utils.content_classifier import content_classifier
from ..db.models import CrawlJob, CrawlSession
from ..db.database import async_session
from sqlalchemy import select, desc, and_

router = APIRouter(prefix="/admin/crawl", tags=["admin-crawl"])

# ============================================================================
# Crawl Scheduling & Management
# ============================================================================

@router.post("/schedule")
async def schedule_crawl(
    domain: str = Query(..., description="Domain to crawl"),
    priority: int = Query(5, ge=1, le=10, description="Priority (1=highest, 10=lowest)"),
    max_pages: int = Query(1000, ge=1, le=100000, description="Max pages to crawl"),
    depth: int = Query(3, ge=1, le=5, description="Crawl depth"),
    include_js: bool = Query(False, description="Include JS rendering"),
    custom_sitemaps: Optional[List[str]] = Query(None, description="Custom sitemap URLs"),
):
    """
    Schedule a new crawl for a domain.
    
    Features:
    - Auto-detect sitemaps from robots.txt and common paths
    - Support for custom sitemaps
    - Priority queue system
    - Configurable depth and page limits
    - Optional JS rendering
    """
    try:
        # Get all URLs from sitemaps
        all_urls, auto_detected = await sitemap_manager.get_all_urls(
            domain,
            custom_sitemaps=custom_sitemaps
        )
        
        # Limit to max_pages
        urls_to_crawl = all_urls[:max_pages]
        
        # Create crawl job
        job_id = str(uuid.uuid4())
        
        async with async_session() as session:
            crawl_job = CrawlJob(
                job_id=job_id,
                domain=domain,
                status="pending",
                priority=priority,
                total_pages=len(urls_to_crawl),
                crawled_pages=0,
                failed_pages=0,
                max_depth=depth,
                enable_js_rendering=include_js,
                created_at=datetime.utcnow(),
                started_at=None,
                completed_at=None,
                urls_to_crawl=urls_to_crawl,
            )
            
            session.add(crawl_job)
            await session.commit()
        
        return {
            "status": "scheduled",
            "job_id": job_id,
            "domain": domain,
            "total_pages": len(urls_to_crawl),
            "auto_detected_sitemaps": list(auto_detected),
            "custom_sitemaps": custom_sitemaps or [],
            "priority": priority,
            "depth": depth,
            "js_rendering": include_js,
            "created_at": datetime.utcnow().isoformat(),
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scheduling error: {str(e)}")


@router.post("/schedule-urls")
async def schedule_crawl_urls(
    domain: str = Query(...),
    urls: List[str] = Body(..., description="List of URLs to crawl"),
    priority: int = Query(5, ge=1, le=10),
    include_js: bool = Query(False),
):
    """
    Schedule crawl with manually specified URLs.
    
    Useful for:
    - Targeting specific pages
    - Custom crawl patterns
    - Re-crawling failed pages
    """
    if not urls:
        raise HTTPException(status_code=400, detail="URLs list cannot be empty")
    
    if len(urls) > 50000:
        raise HTTPException(status_code=400, detail="Too many URLs (max 50,000)")
    
    try:
        job_id = str(uuid.uuid4())
        
        async with async_session() as session:
            crawl_job = CrawlJob(
                job_id=job_id,
                domain=domain,
                status="pending",
                priority=priority,
                total_pages=len(urls),
                crawled_pages=0,
                failed_pages=0,
                enable_js_rendering=include_js,
                created_at=datetime.utcnow(),
                urls_to_crawl=urls,
            )
            
            session.add(crawl_job)
            await session.commit()
        
        return {
            "status": "scheduled",
            "job_id": job_id,
            "domain": domain,
            "urls_count": len(urls),
            "priority": priority,
            "js_rendering": include_js,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/jobs")
async def list_crawl_jobs(
    status: Optional[str] = Query(None, description="Filter by status (pending, running, completed, failed)"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    List all crawl jobs with filtering.
    
    Statuses:
    - pending: Waiting to start
    - running: Currently crawling
    - completed: Finished successfully
    - failed: Failed
    - cancelled: Manually cancelled
    """
    try:
        async with async_session() as session:
            query = select(CrawlJob)
            
            if status:
                query = query.where(CrawlJob.status == status)
            
            if domain:
                query = query.where(CrawlJob.domain == domain)
            
            query = query.order_by(desc(CrawlJob.created_at))
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            jobs = result.scalars().all()
            
            return {
                "jobs": [
                    {
                        "job_id": job.job_id,
                        "domain": job.domain,
                        "status": job.status,
                        "priority": job.priority,
                        "progress": {
                            "total": job.total_pages,
                            "crawled": job.crawled_pages,
                            "failed": job.failed_pages,
                            "percentage": round((job.crawled_pages / job.total_pages * 100) if job.total_pages > 0 else 0, 2),
                        },
                        "created_at": job.created_at.isoformat() if job.created_at else None,
                        "started_at": job.started_at.isoformat() if job.started_at else None,
                        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                        "duration_seconds": (
                            (job.completed_at - job.started_at).total_seconds()
                            if job.completed_at and job.started_at else None
                        ),
                    }
                    for job in jobs
                ],
                "total": len(jobs),
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/jobs/{job_id}")
async def get_crawl_job(job_id: str):
    """
    Get detailed information about a specific crawl job.
    """
    try:
        async with async_session() as session:
            query = select(CrawlJob).where(CrawlJob.job_id == job_id)
            result = await session.execute(query)
            job = result.scalar_one_or_none()
            
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            
            return {
                "job_id": job.job_id,
                "domain": job.domain,
                "status": job.status,
                "priority": job.priority,
                "progress": {
                    "total": job.total_pages,
                    "crawled": job.crawled_pages,
                    "failed": job.failed_pages,
                    "percentage": round((job.crawled_pages / job.total_pages * 100) if job.total_pages > 0 else 0, 2),
                },
                "settings": {
                    "max_depth": job.max_depth,
                    "js_rendering": job.enable_js_rendering,
                },
                "timestamps": {
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                },
                "urls_to_crawl": job.urls_to_crawl[:10],  # First 10 URLs
                "urls_count": len(job.urls_to_crawl),
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/jobs/{job_id}/cancel")
async def cancel_crawl_job(job_id: str):
    """
    Cancel a pending or running crawl job.
    """
    try:
        async with async_session() as session:
            query = select(CrawlJob).where(CrawlJob.job_id == job_id)
            result = await session.execute(query)
            job = result.scalar_one_or_none()
            
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            
            if job.status in ["completed", "failed", "cancelled"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot cancel job with status '{job.status}'"
                )
            
            job.status = "cancelled"
            job.completed_at = datetime.utcnow()
            
            await session.commit()
            
            return {
                "status": "cancelled",
                "job_id": job_id,
                "cancelled_at": datetime.utcnow().isoformat(),
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# Batch Operations
# ============================================================================

@router.post("/batch/schedule")
async def batch_schedule_crawls(
    domains: List[str] = Body(..., description="List of domains to crawl"),
    priority: int = Query(5, ge=1, le=10),
    include_js: bool = Query(False),
):
    """
    Schedule multiple domains for crawling at once.
    """
    if not domains:
        raise HTTPException(status_code=400, detail="Domains list cannot be empty")
    
    if len(domains) > 100:
        raise HTTPException(status_code=400, detail="Too many domains (max 100)")
    
    try:
        job_ids = []
        errors = []
        
        async with async_session() as session:
            for domain in domains:
                try:
                    job_id = str(uuid.uuid4())
                    
                    crawl_job = CrawlJob(
                        job_id=job_id,
                        domain=domain,
                        status="pending",
                        priority=priority,
                        enable_js_rendering=include_js,
                        created_at=datetime.utcnow(),
                        total_pages=0,
                        crawled_pages=0,
                        failed_pages=0,
                    )
                    
                    session.add(crawl_job)
                    job_ids.append({"domain": domain, "job_id": job_id})
                
                except Exception as e:
                    errors.append({"domain": domain, "error": str(e)})
            
            await session.commit()
        
        return {
            "status": "batch_scheduled",
            "total_domains": len(domains),
            "scheduled": len(job_ids),
            "failed": len(errors),
            "jobs": job_ids,
            "errors": errors if errors else None,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/batch/cancel")
async def batch_cancel_crawls(
    job_ids: List[str] = Body(..., description="Job IDs to cancel"),
):
    """
    Cancel multiple crawl jobs at once.
    """
    if not job_ids:
        raise HTTPException(status_code=400, detail="Job IDs list cannot be empty")
    
    try:
        async with async_session() as session:
            query = select(CrawlJob).where(
                and_(
                    CrawlJob.job_id.in_(job_ids),
                    CrawlJob.status.in_(["pending", "running"])
                )
            )
            
            result = await session.execute(query)
            jobs = result.scalars().all()
            
            cancelled_count = 0
            for job in jobs:
                job.status = "cancelled"
                job.completed_at = datetime.utcnow()
                cancelled_count += 1
            
            await session.commit()
        
        return {
            "status": "batch_cancelled",
            "requested": len(job_ids),
            "cancelled": cancelled_count,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# Analytics & Reporting
# ============================================================================

@router.get("/stats")
async def crawl_statistics(
    hours: int = Query(24, ge=1, le=730, description="Last N hours"),
):
    """
    Get crawl statistics for the last N hours.
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        async with async_session() as session:
            query = select(CrawlJob).where(CrawlJob.created_at >= cutoff_time)
            result = await session.execute(query)
            jobs = result.scalars().all()
            
            stats = {
                "total_jobs": len(jobs),
                "by_status": {},
                "by_domain": {},
                "total_pages_crawled": 0,
                "total_pages_failed": 0,
                "average_pages_per_job": 0,
            }
            
            for job in jobs:
                # Count by status
                stats["by_status"][job.status] = stats["by_status"].get(job.status, 0) + 1
                
                # Count by domain
                stats["by_domain"][job.domain] = stats["by_domain"].get(job.domain, 0) + 1
                
                # Total pages
                stats["total_pages_crawled"] += job.crawled_pages
                stats["total_pages_failed"] += job.failed_pages
            
            if jobs:
                stats["average_pages_per_job"] = round(
                    stats["total_pages_crawled"] / len(jobs), 2
                )
            
            return stats
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/stats/domain/{domain}")
async def domain_crawl_stats(domain: str):
    """
    Get detailed statistics for a specific domain.
    """
    try:
        async with async_session() as session:
            query = select(CrawlJob).where(CrawlJob.domain == domain)
            result = await session.execute(query)
            jobs = result.scalars().all()
            
            if not jobs:
                raise HTTPException(status_code=404, detail="No crawl jobs found for domain")
            
            total_crawled = sum(job.crawled_pages for job in jobs)
            total_failed = sum(job.failed_pages for job in jobs)
            total_jobs = len(jobs)
            
            completed_jobs = [j for j in jobs if j.status == "completed"]
            failed_jobs = [j for j in jobs if j.status == "failed"]
            
            return {
                "domain": domain,
                "total_jobs": total_jobs,
                "completed_jobs": len(completed_jobs),
                "failed_jobs": len(failed_jobs),
                "running_jobs": len([j for j in jobs if j.status == "running"]),
                "pending_jobs": len([j for j in jobs if j.status == "pending"]),
                "total_pages_crawled": total_crawled,
                "total_pages_failed": total_failed,
                "success_rate": round(
                    (total_crawled / (total_crawled + total_failed) * 100)
                    if (total_crawled + total_failed) > 0 else 0,
                    2
                ),
                "average_duration_seconds": round(
                    sum(
                        (job.completed_at - job.started_at).total_seconds()
                        for job in completed_jobs
                        if job.completed_at and job.started_at
                    ) / len(completed_jobs)
                    if completed_jobs else 0,
                    2
                ),
                "last_crawl": max(
                    (job.completed_at or job.created_at for job in jobs),
                    default=None
                ).isoformat() if jobs else None,
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# Configuration & Settings
# ============================================================================

@router.get("/config")
async def get_crawl_config():
    """
    Get current crawl configuration and limits.
    """
    return {
        "limits": {
            "max_pages_per_job": 100000,
            "max_urls_per_schedule": 50000,
            "max_domains_per_batch": 100,
            "max_job_ids_per_batch_cancel": 1000,
        },
        "priority_levels": {
            "1": "Highest",
            "5": "Medium (default)",
            "10": "Lowest",
        },
        "supported_depths": list(range(1, 6)),
        "features": {
            "js_rendering": True,
            "auto_sitemap_detection": True,
            "custom_sitemap_support": True,
            "batch_operations": True,
            "statistics": True,
        },
    }


@router.post("/config/update")
async def update_crawl_config(
    config: Dict[str, Any] = Body(...),
):
    """
    Update crawl configuration (admin only).
    
    Note: This is a placeholder for future permission-based updates.
    """
    # TODO: Add permission checks
    return {
        "status": "success",
        "message": "Configuration would be updated (not implemented)",
        "config": config,
    }


# ============================================================================
# Documentation
# ============================================================================

@router.get("/docs")
async def crawl_api_documentation():
    """
    Get comprehensive crawl API documentation.
    """
    return {
        "title": "Crawl Management API",
        "version": "1.0",
        "sections": {
            "scheduling": {
                "POST /admin/crawl/schedule": "Schedule auto-detected sitemap crawl",
                "POST /admin/crawl/schedule-urls": "Schedule custom URL list crawl",
            },
            "management": {
                "GET /admin/crawl/jobs": "List all crawl jobs",
                "GET /admin/crawl/jobs/{job_id}": "Get specific job details",
                "POST /admin/crawl/jobs/{job_id}/cancel": "Cancel a job",
            },
            "batch_operations": {
                "POST /admin/crawl/batch/schedule": "Schedule multiple domains",
                "POST /admin/crawl/batch/cancel": "Cancel multiple jobs",
            },
            "analytics": {
                "GET /admin/crawl/stats": "Get overall statistics",
                "GET /admin/crawl/stats/domain/{domain}": "Get domain statistics",
            },
            "configuration": {
                "GET /admin/crawl/config": "Get current configuration",
                "POST /admin/crawl/config/update": "Update configuration",
            },
        },
    }
