"""FastAPI main router that combines all sub-routers."""
from fastapi import APIRouter
import logging

# Import all routers
from app.routers import (
    search,
    advanced_search,
    admin,
    admin_crawl,
    admin_index,
    analytics,
    click,
    images,
    sitemap_admin,
    suggest,
)
from app.api import crawler_router

logger = logging.getLogger(__name__)

# Create main router
router = APIRouter()

# Include all routers
logger.info("📚 Registering routers...")

# Search routers
router.include_router(search.router, prefix="/search", tags=["search"])
logger.info("✅ Registered: /api/search")

router.include_router(advanced_search.router, prefix="/search", tags=["search"])
logger.info("✅ Registered: /api/search (advanced)")

# Crawler routers
router.include_router(crawler_router.router, prefix="/crawl", tags=["crawl"])
logger.info("✅ Registered: /api/crawl")

# Admin routers
router.include_router(admin.router, prefix="/admin", tags=["admin"])
logger.info("✅ Registered: /admin")

router.include_router(admin_crawl.router, prefix="/admin", tags=["admin"])
logger.info("✅ Registered: /admin/crawl")

router.include_router(admin_index.router, prefix="/admin", tags=["admin"])
logger.info("✅ Registered: /admin/index")

router.include_router(sitemap_admin.router, prefix="/admin", tags=["admin"])
logger.info("✅ Registered: /admin/sitemap")

# Analytics routers
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
logger.info("✅ Registered: /api/analytics")

# Utility routers
router.include_router(click.router, prefix="/click", tags=["utility"])
logger.info("✅ Registered: /api/click")

router.include_router(images.router, prefix="/images", tags=["utility"])
logger.info("✅ Registered: /api/images")

router.include_router(suggest.router, prefix="/suggest", tags=["utility"])
logger.info("✅ Registered: /api/suggest")

logger.info("🚀 All routers registered successfully!")

__all__ = ["router"]
