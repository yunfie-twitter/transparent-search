"""FastAPI application with Redis caching and Alembic migration support."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db
from app.db.cache import crawl_cache
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
    await init_db()
    logger.info("✅ Database initialized")
    
    # Connect to Redis cache
    logger.info("🙋 Connecting to Redis cache...")
    await crawl_cache.connect()
    logger.info("✅ Redis cache connected")
    
    logger.info("🌟 Application ready")
    
    yield
    
    # Shutdown
    logger.info("🙋 Shutting down application...")
    
    # Disconnect from Redis
    logger.info("🙋 Disconnecting from Redis cache...")
    await crawl_cache.disconnect()
    logger.info("✅ Redis cache disconnected")
    
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
        "redis": "connected" if crawl_cache.redis else "disconnected",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "cache": "connected" if crawl_cache.redis else "disconnected",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )
