"""FastAPI application with Redis caching, database, and crawl worker integration."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import select, func

from app.core.database import init_db, get_db_session
from app.core.cache import init_crawl_cache, close_redis, get_redis_client, crawl_cache
from app.api import router
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

# Get the absolute path to the project root
PROJECT_ROOT = Path(__file__).resolve().parent
logger.info(f"📁 Project root: {PROJECT_ROOT}")

# Static files directory
STATIC_DIR = PROJECT_ROOT / "app" / "static"
INDEX_HTML = STATIC_DIR / "index.html"
logger.info(f"📁 Static directory: {STATIC_DIR}")
logger.info(f"📄 Index HTML path: {INDEX_HTML}")
logger.info(f"📄 Index HTML exists: {INDEX_HTML.exists()}")

if INDEX_HTML.exists():
    logger.info(f"✅ Found index.html at {INDEX_HTML}")
else:
    logger.warning(f"⚠️ index.html NOT found at {INDEX_HTML}")
    logger.warning(f"   Current working directory: {os.getcwd()}")
    logger.warning(f"   Script location: {__file__}")


async def check_pending_jobs() -> dict:
    """Check pending jobs in database."""
    try:
        async with get_db_session() as db:
            # Count all jobs by status
            for status in ["pending", "completed", "processing", "failed"]:
                stmt = select(func.count(CrawlJob.job_id)).where(
                    CrawlJob.status == status
                )
                result = await db.execute(stmt)
                counts = {status: result.scalar() or 0 for status in ["pending", "completed", "processing", "failed"]}
            
            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "pending"
            )
            result = await db.execute(stmt)
            pending_count = result.scalar() or 0
            
            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "completed"
            )
            result = await db.execute(stmt)
            completed_count = result.scalar() or 0
            
            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "processing"
            )
            result = await db.execute(stmt)
            processing_count = result.scalar() or 0
            
            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "failed"
            )
            result = await db.execute(stmt)
            failed_count = result.scalar() or 0
            
            return {
                "pending": pending_count,
                "completed": completed_count,
                "processing": processing_count,
                "failed": failed_count,
                "total": pending_count + completed_count + processing_count + failed_count,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    global worker_task
    
    # ==================== STARTUP ====================
    logger.info("🚀 Starting Transparent Search application...")
    
    # Initialize database
    logger.info("💾 Initializing database...")
    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        yield
        return
    
    # Initialize Redis cache
    logger.info("🎯 Connecting to Redis cache...")
    try:
        await init_crawl_cache()
        logger.info("✅ Redis cache connected")
    except Exception as e:
        logger.warning(f"⚠️ Redis connection failed (non-critical): {e}")
    
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
        
        if job_stats['pending'] > 0:
            logger.info(f"🔵 Ready to process {job_stats['pending']} pending job(s)")
    except Exception as e:
        logger.error(f"❌ Failed to retrieve job stats: {e}")
    
    # Start crawl worker
    logger.info("🤖 Starting crawl worker...")
    try:
        crawl_worker.is_running = True
        logger.info(
            f"🔒 Worker configuration: "
            f"max_concurrent={crawl_worker.max_concurrent_jobs}, "
            f"poll_interval={crawl_worker.poll_interval}s"
        )
        worker_task = asyncio.create_task(crawl_worker.worker_loop())
        logger.info("✅ Crawl worker task created")
        await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"❌ Crawl worker startup failed: {e}")
        crawl_worker.is_running = False
    
    logger.info("🌟 Application startup complete")
    
    yield
    
    # ==================== SHUTDOWN ====================
    logger.info("🙋 Shutting down application...")
    
    # Stop crawl worker
    logger.info("🤖 Stopping crawl worker...")
    try:
        crawl_worker.is_running = False
        logger.info(f"💾 Worker stats: active_jobs={len(crawl_worker.active_jobs)}")
        
        # Wait for active jobs
        if crawl_worker.active_jobs:
            logger.info(f"⏳ Waiting for {len(crawl_worker.active_jobs)} active jobs...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*crawl_worker.active_jobs.values(), return_exceptions=True),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("⚠️ Some jobs timeout")
        
        # Wait for worker task
        if worker_task and not worker_task.done():
            try:
                await asyncio.wait_for(worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("⚠️ Worker task timeout")
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
        
        logger.info("✅ Crawl worker stopped")
    except Exception as e:
        logger.error(f"❌ Crawl worker shutdown error: {e}")
    
    # Disconnect Redis
    logger.info("🎯 Disconnecting from Redis cache...")
    try:
        await close_redis()
        logger.info("✅ Redis cache disconnected")
    except Exception as e:
        logger.warning(f"⚠️ Redis disconnect error (non-critical): {e}")
    
    logger.info("🙋 Application shutdown complete")


app = FastAPI(
    title="Transparent Search API",
    description="Advanced web crawling and intelligent search indexing",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router (MUST come before mounting static files)
app.include_router(router, prefix="/api")

# ==================== STATIC FILES CONFIGURATION ====================
if STATIC_DIR.exists():
    # Mount /static directory for CSS, JS, images, etc.
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info(f"✅ Static files mounted at {STATIC_DIR}")
else:
    logger.warning(f"⚠️ Static directory not found: {STATIC_DIR}")


# ==================== ROOT ENDPOINT ====================
@app.get("/")
async def root():
    """Root endpoint - serves index.html from static directory."""
    logger.debug(f"Root endpoint called - checking for index.html at {INDEX_HTML}")
    
    if INDEX_HTML.exists():
        logger.info(f"✅ Serving index.html from {INDEX_HTML}")
        return FileResponse(
            str(INDEX_HTML),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )
    else:
        # Fallback JSON response if index.html not found
        logger.warning(f"⚠️ index.html not found at {INDEX_HTML}")
        logger.warning(f"   Static dir exists: {STATIC_DIR.exists()}")
        logger.warning(f"   Static dir contents: {list(STATIC_DIR.glob('*')) if STATIC_DIR.exists() else 'N/A'}")
        logger.warning(f"   Current working directory: {os.getcwd()}")
        logger.warning(f"   __file__: {__file__}")
        
        redis_client = await get_redis_client()
        return {
            "status": "ok",
            "name": "Transparent Search API",
            "version": "1.0.0",
            "docs": "/api/docs",
            "redis": "connected" if redis_client else "disconnected",
            "ui": "/static/index.html",
            "debug": {
                "index_html_path": str(INDEX_HTML),
                "index_html_exists": INDEX_HTML.exists(),
                "static_dir": str(STATIC_DIR),
                "static_dir_exists": STATIC_DIR.exists(),
                "cwd": os.getcwd(),
                "script": __file__,
            }
        }


@app.get("/health")
async def health():
    """Health check endpoint."""
    redis_client = await get_redis_client()
    worker_status = "operational" if crawl_worker.is_running else "stopped"
    active_jobs = len(crawl_worker.active_jobs)
    job_stats = await check_pending_jobs()
    
    return {
        "status": "healthy",
        "cache": "connected" if redis_client else "disconnected",
        "worker": worker_status,
        "active_jobs": active_jobs,
        "database_stats": job_stats,
    }


@app.get("/admin")
async def admin_overview():
    """Admin panel overview."""
    job_stats = await check_pending_jobs()
    
    return {
        "title": "Transparent Search Admin",
        "worker": {
            "is_running": crawl_worker.is_running,
            "active_jobs": len(crawl_worker.active_jobs),
            "max_concurrent": crawl_worker.max_concurrent_jobs,
            "poll_interval": crawl_worker.poll_interval,
        },
        "stats": job_stats,
        "endpoints": {
            "worker_status": "GET /api/crawl/worker/status",
            "session_stats": "GET /api/crawl/worker/session/{session_id}",
            "start_crawl": "POST /api/crawl/start?domain=...",
        },
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )
