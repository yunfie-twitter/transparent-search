"""Scheduler administration endpoints."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
import logging

from app.services.crawl_scheduler import crawl_scheduler
from app.core.auth import verify_admin_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/scheduler", tags=["admin-scheduler"])


@router.post("/discover-all")
async def discover_and_schedule_all_sites(
    dry_run: bool = Query(False, description="Dry run - don't actually schedule"),
    token: str = Query(..., description="Admin token"),
) -> Dict[str, Any]:
    """
    Automatically discover all sites and schedule crawls.
    
    Crawls sites that:
    - Haven't been crawled in the past 24 hours
    - Have sitemaps available
    - Are already in the database
    
    Args:
        dry_run: If true, only show what would be scheduled
        token: Admin authentication token
    
    Returns:
        Discovery and scheduling statistics
    """
    try:
        # Verify admin token
        if not verify_admin_token(token):
            raise HTTPException(status_code=403, detail="Invalid admin token")
        
        logger.info(f"🔍 Auto-discovery initiated (dry_run={dry_run})")
        
        if dry_run:
            return {
                "status": "dry_run",
                "message": "Dry run mode - no actual scheduling",
                "note": "Run with dry_run=false to actually schedule crawls",
            }
        
        result = await crawl_scheduler.discover_and_schedule_sites()
        
        logger.info(
            f"✅ Discovery complete: {result['crawls_scheduled']} crawls scheduled"
        )
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Discovery error: {e}")
        raise HTTPException(status_code=500, detail=f"Discovery error: {str(e)}")


@router.post("/force-stop")
async def force_stop_all_crawls(
    confirm: bool = Query(False, description="Confirm force stop"),
    token: str = Query(..., description="Admin token"),
) -> Dict[str, Any]:
    """
    Force stop ALL active crawls immediately.
    
    ⚠️ WARNING: This will terminate all crawling operations.
    
    Args:
        confirm: Must be true to actually stop
        token: Admin authentication token
    
    Returns:
        Operation status
    """
    try:
        # Verify admin token
        if not verify_admin_token(token):
            raise HTTPException(status_code=403, detail="Invalid admin token")
        
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="Must set confirm=true to force stop"
            )
        
        logger.warning("🛑 FORCE STOP: All crawls terminated by admin")
        result = crawl_scheduler.force_stop_all()
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Force stop error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/force-pause-index")
async def force_pause_all_indexing(
    confirm: bool = Query(False, description="Confirm pause"),
    token: str = Query(..., description="Admin token"),
) -> Dict[str, Any]:
    """
    Force pause ALL indexing operations.
    
    ⚠️ WARNING: This will pause all indexing but allow crawling to continue.
    
    Args:
        confirm: Must be true to actually pause
        token: Admin authentication token
    
    Returns:
        Operation status
    """
    try:
        # Verify admin token
        if not verify_admin_token(token):
            raise HTTPException(status_code=403, detail="Invalid admin token")
        
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="Must set confirm=true to force pause"
            )
        
        logger.warning("⏸️  FORCE PAUSE: Indexing paused by admin")
        result = crawl_scheduler.force_pause_indexing()
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Force pause error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume")
async def resume_all_operations(
    token: str = Query(..., description="Admin token"),
) -> Dict[str, Any]:
    """
    Resume all operations after force stop/pause.
    
    Args:
        token: Admin authentication token
    
    Returns:
        Operation status
    """
    try:
        # Verify admin token
        if not verify_admin_token(token):
            raise HTTPException(status_code=403, detail="Invalid admin token")
        
        logger.info("▶️  Resuming all operations")
        result = crawl_scheduler.resume_all()
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_scheduler_status(
    token: str = Query(..., description="Admin token"),
) -> Dict[str, Any]:
    """
    Get current scheduler status and configuration.
    
    Args:
        token: Admin authentication token
    
    Returns:
        Current scheduler state
    """
    try:
        # Verify admin token
        if not verify_admin_token(token):
            raise HTTPException(status_code=403, detail="Invalid admin token")
        
        status = crawl_scheduler.get_status()
        
        return {
            "status": "ok",
            "scheduler": status,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-queue")
async def manually_process_crawl_queue(
    limit: int = Query(100, ge=1, le=1000, description="Max jobs to process"),
    token: str = Query(..., description="Admin token"),
) -> Dict[str, Any]:
    """
    Manually trigger crawl queue processing.
    
    Processes pending crawl jobs and triggers indexing.
    This normally runs automatically but can be triggered manually.
    
    Args:
        limit: Maximum number of jobs to process
        token: Admin authentication token
    
    Returns:
        Processing results
    """
    try:
        # Verify admin token
        if not verify_admin_token(token):
            raise HTTPException(status_code=403, detail="Invalid admin token")
        
        logger.info(f"📋 Manual queue processing (limit={limit})")
        
        result = await crawl_scheduler.process_crawl_queue()
        
        return {
            "status": "success",
            "result": result,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Queue processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ["router"]
