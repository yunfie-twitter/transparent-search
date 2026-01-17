"""Application startup and initialization helpers.

This module provides helper functions for startup operations:
  - Database job statistics
  - Auto-indexing of completed crawl jobs
  - Worker initialization diagnostics
"""

import logging
from sqlalchemy import select, func

from app.core.database import get_db_session
from app.db.models import CrawlJob, SearchContent
from app.services.crawl_worker import crawl_worker

logger = logging.getLogger(__name__)


async def check_pending_jobs() -> dict:
    """Check pending jobs in database.
    
    Returns:
        Dictionary with counts for each job status
    """
    try:
        async with get_db_session() as db:
            # Count jobs by each status in a single efficient way
            stats = {}
            for status in ["pending", "completed", "processing", "failed"]:
                stmt = select(func.count(CrawlJob.job_id)).where(
                    CrawlJob.status == status
                )
                result = await db.execute(stmt)
                count = result.scalar() or 0
                stats[status] = count
            
            return {
                "pending": stats.get("pending", 0),
                "completed": stats.get("completed", 0),
                "processing": stats.get("processing", 0),
                "failed": stats.get("failed", 0),
                "total": sum(stats.values()),
            }
    except Exception as e:
        logger.error(f"❌ Failed to check pending jobs: {e}")
        return {
            "pending": 0,
            "completed": 0,
            "processing": 0,
            "failed": 0,
            "total": 0,
        }


async def auto_index_completed_jobs() -> dict:
    """Auto-index any completed crawl jobs that aren't indexed yet.
    
    This runs during startup to ensure all previously completed jobs
    are properly indexed in the search database.
    
    Returns:
        Dictionary with statistics about indexing operation
    """
    logger.info("📋 Auto-indexing completed CrawlJobs on startup...")
    
    stats = {
        "total_completed": 0,
        "already_indexed": 0,
        "newly_indexed": 0,
        "indexing_failed": 0,
    }
    
    try:
        from app.services.indexer import content_indexer
        
        async with get_db_session() as db:
            # Get all completed jobs
            stmt = select(CrawlJob).where(CrawlJob.status == "completed")
            result = await db.execute(stmt)
            jobs = result.scalars().all()
            
            stats["total_completed"] = len(jobs)
            
            if len(jobs) == 0:
                logger.info("📋 No completed CrawlJobs to index")
                return stats
            
            logger.info(f"📋 Found {len(jobs)} completed CrawlJobs to process")
            
            for idx, job in enumerate(jobs, 1):
                try:
                    # Check if already indexed
                    existing = await db.execute(
                        select(SearchContent).where(
                            SearchContent.url == job.url
                        )
                    )
                    
                    if existing.scalar_one_or_none():
                        stats["already_indexed"] += 1
                        continue
                    
                    # Index the job
                    indexed_content = await content_indexer.index_crawl_job(
                        job_id=job.job_id,
                        session_id=job.session_id,
                        domain=job.domain,
                        url=job.url,
                    )
                    
                    if indexed_content:
                        stats["newly_indexed"] += 1
                    else:
                        stats["indexing_failed"] += 1
                    
                    # Log progress every 10 jobs
                    if idx % 10 == 0:
                        logger.debug(
                            f"📋 Auto-index progress: {idx}/{len(jobs)} "
                            f"(indexed={stats['newly_indexed']}, "
                            f"skipped={stats['already_indexed']})"
                        )
                
                except Exception as e:
                    logger.warning(f"⚠️ Failed to index job {job.job_id}: {e}")
                    stats["indexing_failed"] += 1
            
            logger.info(
                f"✅ Auto-indexing complete: "
                f"newly_indexed={stats['newly_indexed']}, "
                f"already_indexed={stats['already_indexed']}, "
                f"failed={stats['indexing_failed']}, "
                f"total_completed={stats['total_completed']}"
            )
    
    except Exception as e:
        logger.error(f"❌ Auto-indexing failed: {e}", exc_info=True)
    
    return stats


async def get_worker_status() -> dict:
    """Get current worker status and statistics.
    
    Returns:
        Dictionary with worker status, active jobs, and configuration
    """
    return {
        "is_running": crawl_worker.is_running,
        "active_jobs": len(crawl_worker.active_jobs),
        "max_concurrent_jobs": crawl_worker.max_concurrent_jobs,
        "poll_interval_seconds": crawl_worker.poll_interval,
    }


async def get_startup_diagnostics() -> dict:
    """Get comprehensive startup diagnostics.
    
    Returns:
        Dictionary with full system status
    """
    job_stats = await check_pending_jobs()
    worker_status = await get_worker_status()
    
    return {
        "database_jobs": job_stats,
        "worker": worker_status,
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
    }
