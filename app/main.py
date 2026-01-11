"""FastAPI application - Main entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db, close_db
from app.core.cache import init_redis, close_redis
from app.api import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
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
    
    logger.info("🌟 Application ready")
    
    yield
    
    # Shutdown
    logger.info("🙋 Shutting down application...")
    
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
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "api": "operational",
            "search": "operational",
        }
    }


@app.get("/admin")
async def admin_overview():
    """Admin panel overview and API endpoints summary."""
    return {
        "title": "Transparent Search Admin Panel",
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
