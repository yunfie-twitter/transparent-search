from fastapi import FastAPI
from contextlib import asynccontextmanager
from .routers import (
    search, suggest, click, images, admin,
    advanced_search, sitemap_admin, admin_crawl, admin_index
)
from .db_init import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Initializing database...")
    try:
        await init_db()
        print("✅ Database initialization complete")
    except Exception as e:
        print(f"⚠️ Database initialization warning: {e}")
    yield
    # Shutdown
    print("🛑 Shutting down...")

app = FastAPI(
    title="Transparent Search API",
    lifespan=lifespan
)

# Search endpoints
app.include_router(search.router)
app.include_router(suggest.router)
app.include_router(click.router)
app.include_router(advanced_search.router, prefix="/search")  # /search/fuzzy
app.include_router(images.router, prefix="/search") # /search/images

# Admin endpoints - Sitemap management
app.include_router(sitemap_admin.router)  # /admin/sitemap/*

# Admin endpoints - Crawl management
app.include_router(admin_crawl.router)  # /admin/crawl/*

# Admin endpoints - Index management
app.include_router(admin_index.router)  # /admin/index/*

# Admin endpoints - General
app.include_router(admin.router, prefix="/admin")  # /admin/*

@app.get("/")
async def root():
    return {"message": "Transparent Search API is running"}

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0",
        "components": {
            "search": "operational",
            "admin": "operational",
        }
    }

@app.get("/admin")
async def admin_overview():
    """
    Admin panel overview and API endpoints summary.
    """
    return {
        "title": "Transparent Search Admin Panel",
        "api_endpoints": {
            "sitemap": {
                "base": "/admin/sitemap",
                "endpoints": [
                    "POST /admin/sitemap/detect/{domain}",
                    "POST /admin/sitemap/parse?url=...",
                    "POST /admin/sitemap/get-all?domain=...",
                    "POST /admin/sitemap/add?domain=...&sitemap_url=...",
                    "GET /admin/sitemap/common-paths",
                    "GET /admin/sitemap/docs",
                ]
            },
            "crawl": {
                "base": "/admin/crawl",
                "endpoints": [
                    "POST /admin/crawl/schedule",
                    "POST /admin/crawl/schedule-urls",
                    "GET /admin/crawl/jobs",
                    "GET /admin/crawl/jobs/{job_id}",
                    "POST /admin/crawl/jobs/{job_id}/cancel",
                    "POST /admin/crawl/batch/schedule",
                    "POST /admin/crawl/batch/cancel",
                    "GET /admin/crawl/stats",
                    "GET /admin/crawl/stats/domain/{domain}",
                    "GET /admin/crawl/config",
                    "GET /admin/crawl/docs",
                ]
            },
            "index": {
                "base": "/admin/index",
                "endpoints": [
                    "POST /admin/index/reindex",
                    "POST /admin/index/optimize",
                    "POST /admin/index/clear",
                    "GET /admin/index/contents",
                    "GET /admin/index/contents/{id}",
                    "DELETE /admin/index/contents/{id}",
                    "POST /admin/index/contents/{id}/recrawl",
                    "POST /admin/index/classify-url",
                    "POST /admin/index/classify-content",
                    "GET /admin/index/stats",
                    "GET /admin/index/config",
                    "GET /admin/index/docs",
                ]
            },
        },
        "documentation": {
            "get_docs": "/docs (Swagger UI)",
            "get_openapi": "/openapi.json",
            "sitemap_docs": "GET /admin/sitemap/docs",
            "crawl_docs": "GET /admin/crawl/docs",
            "index_docs": "GET /admin/index/docs",
        }
    }
