"""Autonomous crawl scheduling system with random intervals."""
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
import logging

from app.db.models import (
    CrawlSession,
    CrawlJob,
    Site,
    SearchContent,
)
from app.core.database import get_db_session
from app.services.crawler import crawler_service
from app.utils.sitemap_manager import sitemap_manager

logger = logging.getLogger(__name__)

class CrawlScheduler:
    """Manages autonomous crawling with random scheduling."""
    
    # Scheduling configuration
    MIN_CRAWL_INTERVAL_HOURS = 4
    MAX_CRAWL_INTERVAL_HOURS = 24
    
    # Global control flags
    _crawl_enabled = True
    _index_enabled = True
    _force_stop = False
    _force_pause_index = False
    
    @classmethod
    def set_crawl_enabled(cls, enabled: bool) -> None:
        """Enable/disable crawling globally."""
        cls._crawl_enabled = enabled
        logger.info(f"Crawl enabled: {enabled}")
    
    @classmethod
    def set_index_enabled(cls, enabled: bool) -> None:
        """Enable/disable indexing globally."""
        cls._index_enabled = enabled
        logger.info(f"Index enabled: {enabled}")
    
    @classmethod
    def force_stop_all(cls) -> Dict[str, Any]:
        """Force stop all crawls immediately."""
        cls._force_stop = True
        cls._crawl_enabled = False
        logger.warning("FORCE STOP: All crawls stopped")
        return {
            "status": "force_stopped",
            "message": "All crawls have been forcefully stopped",
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    @classmethod
    def force_pause_indexing(cls) -> Dict[str, Any]:
        """Force pause all indexing operations."""
        cls._force_pause_index = True
        cls._index_enabled = False
        logger.warning("FORCE PAUSE: Indexing paused")
        return {
            "status": "index_paused",
            "message": "All indexing operations have been paused",
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    @classmethod
    def resume_all(cls) -> Dict[str, Any]:
        """Resume all operations."""
        cls._force_stop = False
        cls._force_pause_index = False
        cls._crawl_enabled = True
        cls._index_enabled = True
        logger.info("Operations resumed")
        return {
            "status": "resumed",
            "message": "All operations resumed",
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Get current scheduler status."""
        return {
            "crawl_enabled": cls._crawl_enabled,
            "index_enabled": cls._index_enabled,
            "force_stop": cls._force_stop,
            "force_pause_index": cls._force_pause_index,
            "min_interval_hours": cls.MIN_CRAWL_INTERVAL_HOURS,
            "max_interval_hours": cls.MAX_CRAWL_INTERVAL_HOURS,
        }
    
    @staticmethod
    async def discover_and_schedule_sites() -> Dict[str, Any]:
        """Automatically discover all sites and schedule crawls.
        
        Returns:
            Statistics on discovered sites and scheduled crawls
        """
        try:
            async with get_db_session() as db:
                # Find all sites without recent crawl sessions
                sites_query = select(Site).order_by(Site.domain)
                result = await db.execute(sites_query)
                all_sites = result.scalars().all()
                
                if not all_sites:
                    logger.info("No sites found in database")
                    return {
                        "status": "no_sites",
                        "message": "No sites available for crawling",
                        "sites_found": 0,
                        "crawls_scheduled": 0,
                    }
                
                scheduled = []
                skipped = []
                
                for site in all_sites:
                    # Check if site has recent crawl session
                    recent_session = await CrawlScheduler._get_recent_session(
                        db, site.domain
                    )
                    
                    if recent_session:
                        skipped.append({
                            "domain": site.domain,
                            "reason": "recent_crawl",
                            "last_crawl": recent_session.created_at.isoformat(),
                        })
                        continue
                    
                    # Schedule crawl for this site
                    try:
                        job = await CrawlScheduler._schedule_site_crawl(
                            db, site
                        )
                        if job:
                            scheduled.append({
                                "domain": site.domain,
                                "session_id": job.session_id,
                                "job_id": job.job_id,
                            })
                    except Exception as e:
                        logger.error(f"Failed to schedule crawl for {site.domain}: {e}")
                        skipped.append({
                            "domain": site.domain,
                            "reason": "error",
                            "error": str(e),
                        })
                
                logger.info(
                    f"Auto-discovery: {len(scheduled)} crawls scheduled, "
                    f"{len(skipped)} sites skipped"
                )
                
                return {
                    "status": "success",
                    "message": f"Scheduled {len(scheduled)} crawls",
                    "sites_found": len(all_sites),
                    "crawls_scheduled": len(scheduled),
                    "sites_skipped": len(skipped),
                    "scheduled": scheduled[:20],  # Return first 20
                    "skipped": skipped[:20],
                }
        
        except Exception as e:
            logger.error(f"Auto-discovery error: {e}")
            return {
                "status": "error",
                "message": str(e),
                "sites_found": 0,
                "crawls_scheduled": 0,
            }
    
    @staticmethod
    async def _get_recent_session(
        db: AsyncSession,
        domain: str,
        hours: int = 24
    ) -> Optional[CrawlSession]:
        """Check if site has crawl session in the past N hours."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        query = select(CrawlSession).where(
            and_(
                CrawlSession.domain == domain,
                CrawlSession.created_at >= cutoff_time,
            )
        ).order_by(CrawlSession.created_at.desc()).limit(1)
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def _schedule_site_crawl(
        db: AsyncSession,
        site: Site
    ) -> Optional[CrawlJob]:
        """Schedule a crawl for a specific site."""
        try:
            # Auto-detect sitemaps
            sitemaps = await sitemap_manager.detect_sitemaps(site.domain)
            
            # Create crawl session
            session = await crawler_service.create_crawl_session(
                domain=site.domain,
                max_depth=3,
                page_limit=1000,
            )
            
            if not session:
                logger.error(f"Failed to create session for {site.domain}")
                return None
            
            # Create jobs from sitemaps
            if sitemaps:
                for sitemap_url in sitemaps[:3]:  # Limit to 3 sitemaps
                    try:
                        urls, _ = await sitemap_manager.parse_sitemap(sitemap_url)
                        for url in urls[:100]:  # Limit URLs from each sitemap
                            await crawler_service.create_crawl_job(
                                session_id=session.session_id,
                                domain=site.domain,
                                url=url,
                                depth=0,
                                max_depth=3,
                                enable_js_rendering=False,
                            )
                    except Exception as e:
                        logger.warning(f"Failed to parse sitemap {sitemap_url}: {e}")
            
            # If no URLs from sitemaps, create base domain job
            if not sitemaps:
                await crawler_service.create_crawl_job(
                    session_id=session.session_id,
                    domain=site.domain,
                    url=f"https://{site.domain}",
                    depth=0,
                    max_depth=3,
                    enable_js_rendering=False,
                )
            
            logger.info(f"Scheduled crawl for {site.domain} (session: {session.session_id})")
            return session
        
        except Exception as e:
            logger.error(f"Error scheduling crawl for {site.domain}: {e}")
            return None
    
    @staticmethod
    async def process_crawl_queue() -> Dict[str, Any]:
        """Process pending crawl jobs and trigger indexing.
        
        This runs automatically in background.
        """
        if not CrawlScheduler._crawl_enabled or CrawlScheduler._force_stop:
            return {"status": "crawling_disabled", "processed": 0}
        
        try:
            async with get_db_session() as db:
                # Find pending crawl jobs
                pending_query = select(CrawlJob).where(
                    CrawlJob.status == "pending"
                ).limit(100)
                
                result = await db.execute(pending_query)
                pending_jobs = result.scalars().all()
                
                processed = 0
                for job in pending_jobs:
                    if CrawlScheduler._force_stop:
                        break
                    
                    try:
                        # Process job (actual crawling)
                        await crawler_service.process_crawl_job(job)
                        processed += 1
                    except Exception as e:
                        logger.error(f"Error processing job {job.job_id}: {e}")
                
                # Trigger indexing if enabled
                if CrawlScheduler._index_enabled and not CrawlScheduler._force_pause_index:
                    await CrawlScheduler._trigger_indexing()
                
                return {
                    "status": "success",
                    "processed": processed,
                    "remaining_jobs": len(pending_jobs) - processed,
                }
        
        except Exception as e:
            logger.error(f"Crawl queue processing error: {e}")
            return {"status": "error", "message": str(e), "processed": 0}
    
    @staticmethod
    async def _trigger_indexing() -> None:
        """Trigger indexing of newly crawled content."""
        try:
            async with get_db_session() as db:
                # Find unindexed crawl jobs
                unindexed_query = select(CrawlJob).where(
                    and_(
                        CrawlJob.status == "completed",
                        CrawlJob.indexed == False,  # noqa: E712
                    )
                ).limit(50)
                
                result = await db.execute(unindexed_query)
                unindexed_jobs = result.scalars().all()
                
                for job in unindexed_jobs:
                    if CrawlScheduler._force_pause_index:
                        break
                    
                    try:
                        # Index the crawled content
                        await crawler_service.index_crawl_result(job)
                        logger.info(f"Indexed crawl result: {job.job_id}")
                    except Exception as e:
                        logger.warning(f"Failed to index job {job.job_id}: {e}")
        
        except Exception as e:
            logger.error(f"Indexing trigger error: {e}")


crawl_scheduler = CrawlScheduler()
