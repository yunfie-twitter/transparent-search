"""FastAPI application - Main entry point with crawl worker integration."""

import asyncio
import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func

from app.core.database import init_db, close_db, get_db_session
from app.core.cache import init_redis, close_redis
from app.api.router import router  # ✅ Import router directly from app.api.router
from app.services.crawl_worker import crawl_worker
from app.db.models import CrawlJob

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global reference to worker task
worker_task: Optional[asyncio.Task] = None


app = FastAPI(
    title="Transparent Search API",
    description="Advanced web crawling and intelligent search indexing",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
# ✅ FIXED: router is already an APIRouter instance, no need for .router accessor
app.include_router(router, prefix="/api")


# ==================== DIAGNOSTICS ====================

async def check_pending_jobs() -> dict:
    """Check pending jobs in database."""
    try:
        async with get_db_session() as db:
            # Count pending
            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "pending"
            )
            result = await db.execute(stmt)
            pending_count = result.scalar() or 0
            
            # Count completed
            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "completed"
            )
            result = await db.execute(stmt)
            completed_count = result.scalar() or 0
            
            # Count processing
            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "processing"
            )
            result = await db.execute(stmt)
            processing_count = result.scalar() or 0
            
            # Count failed
            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "failed"
            )
            result = await db.execute(stmt)
            failed_count = result.scalar() or 0
            
            # ✅ All scalar() calls complete BEFORE exiting async with block
            total_count = pending_count + completed_count + processing_count + failed_count
            
            # Return while still in session context
            return {
                "pending": pending_count,
                "completed": completed_count,
                "processing": processing_count,
                "failed": failed_count,
                "total": total_count,
            }
    except Exception as e:
        logger.error(f"❌ Failed to check pending jobs: {e}")
        return {
            "error": str(e),
            "pending": 0,
            "completed": 0,
            "processing": 0,
            "failed": 0,
            "total": 0,
        }


async def auto_index_startup_jobs():
    """Auto-index any completed jobs that aren't indexed yet."""
    logger.info("📋 Auto-indexing startup CrawlJobs...")
    
    try:
        from app.services.indexer import content_indexer
        from app.db.models import SearchContent
        
        async with get_db_session() as db:
            # Get all completed jobs
            stmt = select(CrawlJob).where(CrawlJob.status == "completed")
            result = await db.execute(stmt)
            jobs = result.scalars().all()
            
            total = len(jobs)
            indexed = 0
            skipped = 0
            failed = 0
            
            if total == 0:
                logger.info("📋 No completed CrawlJobs to index")
                return
            
            logger.info(f"📋 Found {total} completed CrawlJobs to index")
            
            for idx, job in enumerate(jobs, 1):
                # Check if already indexed
                existing = await db.execute(
                    select(SearchContent).where(
                        SearchContent.url == job.url
                    )
                )
                
                if existing.scalar_one_or_none():
                    skipped += 1
                    continue
                
                # Index the job
                indexed_content = await content_indexer.index_crawl_job(
                    job_id=job.job_id,
                    session_id=job.session_id,
                    domain=job.domain,
                    url=job.url,
                )
                
                if indexed_content:
                    indexed += 1
                else:
                    failed += 1
                
                # Log progress every 10 jobs
                if idx % 10 == 0:
                    logger.debug(f"📋 Auto-index progress: {idx}/{total} (indexed={indexed}, skipped={skipped})")
            
            logger.info(
                f"✅ Auto-indexing complete: indexed={indexed}, skipped={skipped}, failed={failed}, total={total}"
            )
    
    except Exception as e:
        logger.error(f"❌ Auto-indexing failed: {e}", exc_info=True)


# ==================== STARTUP HANDLERS ====================

@app.on_event("startup")
async def startup_event():
    """Application startup event handler."""
    global worker_task
    
    logger.info("🚀 Starting Transparent Search application...")
    
    # Initialize database
    logger.info("💾 Initializing database...")
    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return
    
    # Connect to Redis cache
    logger.info("🎯 Connecting to Redis cache...")
    try:
        await init_redis()
        logger.info("✅ Redis cache connected")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
    
    # Auto-index startup jobs
    logger.info("📋 Processing startup queue...")
    try:
        await auto_index_startup_jobs()
    except Exception as e:
        logger.error(f"❌ Auto-indexing failed: {e}")
    
    # Check pending jobs
    logger.info("🔍 Checking pending jobs in database...")
    try:
        job_stats = await check_pending_jobs()
        logger.info(
            f"📋 Database Job Stats: "
            f"total={job_stats['total']}, "
            f"pending={job_stats['pending']}, "
            f"processing={job_stats['processing']}, "
            f"completed={job_stats['completed']}, "
            f"failed={job_stats['failed']}"
        )
    except Exception as e:
        logger.error(f"❌ Failed to retrieve job stats: {e}")
    
    # Start crawl worker
    logger.info("🤖 Starting crawl worker...")
    try:
        # Set worker to running state BEFORE creating task
        crawl_worker.is_running = True
        logger.info(
            f"🔒 Worker configuration: "
            f"max_concurrent_jobs={crawl_worker.max_concurrent_jobs}, "
            f"poll_interval={crawl_worker.poll_interval}s"
        )
        # Create background task for worker
        worker_task = asyncio.create_task(crawl_worker.worker_loop())
        logger.info("✅ Crawl worker task created and running")
        # Give worker a moment to start polling
        await asyncio.sleep(1.0)
    except Exception as e:
        logger.error(f"❌ Crawl worker startup failed: {e}")
        crawl_worker.is_running = False
    
    logger.info("🌟 Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event handler."""
    global worker_task
    
    logger.info("🛑 Shutting down application...")
    
    # Stop crawl worker
    logger.info("🤖 Stopping crawl worker...")
    try:
        # Signal worker to stop
        crawl_worker.is_running = False
        logger.info(
            f"💾 Final worker stats: "
            f"active_jobs={len(crawl_worker.active_jobs)}, "
            f"is_running={crawl_worker.is_running}"
        )
        
        # Wait for active jobs to complete (with timeout)
        if crawl_worker.active_jobs:
            logger.info(f"⏳ Waiting for {len(crawl_worker.active_jobs)} active jobs...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*crawl_worker.active_jobs.values(), return_exceptions=True),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("⚠️ Some jobs did not complete in time")
        
        # Wait for worker task to complete
        if worker_task and not worker_task.done():
            try:
                await asyncio.wait_for(worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("⚠️ Worker task did not stop in time, cancelling...")
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
        
        logger.info("✅ Crawl worker stopped")
    except Exception as e:
        logger.error(f"❌ Crawl worker shutdown error: {e}")
    
    # Close Redis
    logger.info("🎯 Disconnecting from Redis cache...")
    try:
        await close_redis()
        logger.info("✅ Redis cache disconnected")
    except Exception as e:
        logger.error(f"❌ Redis shutdown error: {e}")
    
    # Close database
    logger.info("💾 Disconnecting from database...")
    try:
        await close_db()
        logger.info("✅ Database disconnected")
    except Exception as e:
        logger.error(f"❌ Database shutdown error: {e}")
    
    logger.info("🛑 Application shutdown complete")


# ==================== ENDPOINTS ====================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "status": "ok",
        "name": "Transparent Search API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    # Check worker status
    worker_status = "operational" if crawl_worker.is_running else "stopped"
    active_jobs = len(crawl_worker.active_jobs)
    
    # Check pending jobs
    job_stats = await check_pending_jobs()
    
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "api": "operational",
            "search": "operational",
            "crawl_worker": worker_status,
            "active_crawl_jobs": active_jobs,
        },
        "database_stats": job_stats,
    }


@app.get("/admin")
async def admin_overview():
    """Admin panel overview and API endpoints summary."""
    job_stats = await check_pending_jobs()
    
    return {
        "title": "Transparent Search Admin Panel",
        "worker_status": {
            "is_running": crawl_worker.is_running,
            "active_jobs": len(crawl_worker.active_jobs),
            "max_concurrent_jobs": crawl_worker.max_concurrent_jobs,
            "poll_interval": crawl_worker.poll_interval,
        },
        "database_stats": job_stats,
        "api_endpoints": {
            "search": {
                "base": "/api/search",
                "endpoints": [
                    "GET /api/search?q=...",
                    "GET /api/search/debug/intent?q=...",
                    "GET /api/search/debug/tracker-risk",
                    "GET /api/search/debug/content-types",
                    "POST /api/search/cache/invalidate",
                ]
            },
            "crawl": {
                "base": "/api/crawl",
                "endpoints": [
                    "POST /api/crawl/start?domain=...",
                    "POST /api/crawl/job/create",
                    "POST /api/crawl/job/auto",
                    "POST /api/crawl/job/status",
                    "POST /api/crawl/invalidate?domain=...",
                    "GET /api/crawl/stats?domain=...",
                ]
            },
        },
        "documentation": {
            "swagger": "/docs",
            "openapi": "/openapi.json",
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )
