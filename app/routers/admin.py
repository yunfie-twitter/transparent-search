"""Admin endpoints for crawl management and cancellation."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from ..crawler_state import crawler_state

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/crawl/{crawl_id}/status")
async def get_crawl_status(crawl_id: str):
    """Get current crawl status."""
    state = await crawler_state.get_state(crawl_id)
    if not state:
        raise HTTPException(status_code=404, detail="Crawl not found")
    
    return {
        "crawl_id": crawl_id,
        "status": state.get("status"),
        "domain": state.get("domain"),
        "started_at": state.get("started_at"),
        "ended_at": state.get("ended_at"),
        "cancelled_at": state.get("cancelled_at"),
        "progress": {
            "pages_crawled": state.get("pages_crawled", 0),
            "pages_failed": state.get("pages_failed", 0),
            "pages_skipped": state.get("pages_skipped", 0),
            "current_url": state.get("current_url"),
            "last_updated": state.get("last_updated"),
        },
        "cancelled": state.get("cancelled", False),
    }

@router.post("/crawl/{crawl_id}/cancel")
async def cancel_crawl(crawl_id: str):
    """Cancel an ongoing crawl."""
    success = await crawler_state.cancel_crawl(crawl_id)
    if not success:
        raise HTTPException(status_code=404, detail="Crawl not found or already ended")
    
    return {
        "status": "success",
        "message": f"Crawl {crawl_id} cancellation requested",
        "crawl_id": crawl_id,
    }

@router.delete("/crawl/{crawl_id}")
async def delete_crawl_state(crawl_id: str):
    """Delete crawl state from Redis (cleanup)."""
    success = await crawler_state.cleanup(crawl_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cleanup crawl state")
    
    return {
        "status": "success",
        "message": f"Crawl {crawl_id} state deleted",
        "crawl_id": crawl_id,
    }

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "message": "Admin API is running",
    }

@router.get("/docs")
async def api_docs():
    """Get API documentation."""
    return {
        "title": "Transparent Search - Admin API",
        "version": "1.0",
        "endpoints": {
            "GET /admin/health": "Health check",
            "GET /admin/crawl/{crawl_id}/status": "Get crawl status and progress",
            "POST /admin/crawl/{crawl_id}/cancel": "Cancel an ongoing crawl",
            "DELETE /admin/crawl/{crawl_id}": "Delete crawl state (cleanup)",
        },
        "examples": {
            "check_status": "curl http://localhost:8080/admin/crawl/abc123/status",
            "cancel_crawl": "curl -X POST http://localhost:8080/admin/crawl/abc123/cancel",
            "cleanup": "curl -X DELETE http://localhost:8080/admin/crawl/abc123",
        },
    }
