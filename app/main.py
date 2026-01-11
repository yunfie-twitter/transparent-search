"""FastAPI application - Main entry point with crawl worker integration."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db, close_db
from app.core.cache import init_redis, close_redis
from app.api import router
from app.services.crawl_worker import crawl_worker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global reference to worker task
worker_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    global worker_task
    
    # Startup
    logger.info("🚀 Starting Transparent Search application...")
    
    # Initialize database
    logger.info("💾 Initializing database...")
    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.warning(f"⚠️ Database initialization warning: {e}")
    
    # Connect to Redis cache
    logger.info("🙋 Connecting to Redis cache...")
    try:
        await init_redis()
        logger.info("✅ Redis cache connected")
    except Exception as e:
        logger.warning(f"⚠️ Redis connection warning: {e}")
    
    # Start crawl worker
    logger.info("🤖 Starting crawl worker...")
    try:
        # Set worker to running state
        crawl_worker.is_running = True
        # Create background task for worker
        worker_task = asyncio.create_task(crawl_worker.worker_loop())
        logger.info("✅ Crawl worker started (background task created)")
    except Exception as e:
        logger.error(f"❌ Crawl worker startup failed: {e}")
        crawl_worker.is_running = False
    
    logger.info("🌟 Application ready")
    
    yield
    
    # Shutdown
    logger.info("🙋 Shutting down application...")
    
    # Stop crawl worker
    logger.info("🤖 Stopping crawl worker...")
    try:
        # Signal worker to stop
        crawl_worker.is_running = False
        
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
    logger.info("🙋 Disconnecting from Redis cache...")
    try:
        await close_redis()
        logger.info("✅ Redis cache disconnected")
    except Exception as e:
        logger.warning(f"⚠️ Redis shutdown warning: {e}")
    
    # Close database
    logger.info("🙋 Disconnecting from database...")
    try:
        await close_db()
        logger.info("✅ Database disconnected")
    except Exception as e:
        logger.warning(f"⚠️ Database shutdown warning: {e}")
    
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

# Include API router
app.include_router(router.router, prefix="/api")


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
    
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "api": "operational",
            "search": "operational",
            "crawl_worker": worker_status,
            "active_crawl_jobs": active_jobs,
        }
    }


@app.get("/admin")
async def admin_overview():
    """Admin panel overview and API endpoints summary."""
    return {
        "title": "Transparent Search Admin Panel",
        "worker_status": {
            "is_running": crawl_worker.is_running,
            "active_jobs": len(crawl_worker.active_jobs),
            "max_concurrent_jobs": crawl_worker.max_concurrent_jobs,
            "poll_interval": crawl_worker.poll_interval,
        },
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
        reload=True,
    )
