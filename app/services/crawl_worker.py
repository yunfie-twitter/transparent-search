"""Crawl worker service - processes crawl jobs from queue."""
import asyncio
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.db.models import CrawlJob, CrawlSession
from app.services.crawler import crawler_service

logger = logging.getLogger(__name__)


class CrawlWorker:
    """Worker that processes crawl jobs from the queue."""
    
    def __init__(self, max_concurrent_jobs: int = 3, poll_interval: int = 5):
        """
        Initialize crawl worker.
        
        Args:
            max_concurrent_jobs: Maximum concurrent crawls to run
            poll_interval: How often to check for new jobs (seconds)
        """
        self.max_concurrent_jobs = max_concurrent_jobs
        self.poll_interval = poll_interval
        self.is_running = False
        self.active_jobs: Dict[str, asyncio.Task] = {}
    
    async def get_pending_jobs(
        self,
        limit: int = 10,
        session_id: Optional[str] = None,
    ) -> List[CrawlJob]:
        """Get pending crawl jobs from database.
        
        Args:
            limit: Maximum number of jobs to fetch
            session_id: Filter by specific session (optional)
        
        Returns:
            List of pending CrawlJob objects
        """
        try:
            async with get_db_session() as db:
                # Build query for pending jobs
                query = select(CrawlJob).where(
                    CrawlJob.status == "pending"
                ).order_by(
                    CrawlJob.priority.asc(),  # Lower priority value = higher urgency
                    CrawlJob.created_at.asc(),  # Older jobs first
                ).limit(limit)
                
                # Filter by session if specified
                if session_id:
                    query = query.where(CrawlJob.session_id == session_id)
                
                result = await db.execute(query)
                jobs = result.scalars().all()
                
                logger.info(f"📋 Found {len(jobs)} pending jobs")
                return list(jobs)
        
        except Exception as e:
            logger.error(f"❌ Error fetching pending jobs: {e}")
            return []
    
    async def process_job(self, job: CrawlJob) -> bool:
        """Process a single crawl job.
        
        Args:
            job: CrawlJob to process
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"🔄 Processing job {job.job_id}: {job.url}")
            
            # Execute the actual crawl
            result = await crawler_service.execute_crawl_job(
                job_id=job.job_id,
                session_id=job.session_id,
                domain=job.domain,
                url=job.url,
                depth=job.depth,
                max_depth=job.max_depth,
            )
            
            if result:
                # If there are more links to crawl, queue them
                urls_to_crawl = result.get("urls_to_crawl", [])
                
                if urls_to_crawl and job.depth < job.max_depth:
                    await self.queue_child_jobs(
                        session_id=job.session_id,
                        domain=job.domain,
                        parent_depth=job.depth,
                        max_depth=job.max_depth,
                        urls=urls_to_crawl,
                    )
                
                logger.info(f"✅ Job {job.job_id} completed successfully")
                return True
            else:
                logger.warning(f"⚠️ Job {job.job_id} failed")
                return False
        
        except Exception as e:
            logger.error(f"❌ Error processing job {job.job_id}: {e}")
            await crawler_service.update_crawl_job_status(job.job_id, "failed")
            return False
    
    async def queue_child_jobs(
        self,
        session_id: str,
        domain: str,
        parent_depth: int,
        max_depth: int,
        urls: List[Dict[str, Any]],
    ):
        """Queue child jobs for extracted URLs.
        
        Args:
            session_id: Parent session ID
            domain: Domain being crawled
            parent_depth: Depth of parent job
            max_depth: Maximum crawl depth
            urls: List of URL dicts with 'url' and 'depth' keys
        """
        try:
            child_jobs = []
            
            for url_entry in urls:
                url = url_entry.get("url") if isinstance(url_entry, dict) else url_entry
                depth = parent_depth + 1
                
                if depth <= max_depth:
                    # Create job for this URL
                    job = await crawler_service.create_crawl_job(
                        session_id=session_id,
                        domain=domain,
                        url=url,
                        depth=depth,
                        max_depth=max_depth,
                        enable_js_rendering=False,
                    )
                    
                    if job:
                        child_jobs.append(job)
            
            logger.info(f"🔗 Queued {len(child_jobs)} child jobs for depth {parent_depth + 1}")
        
        except Exception as e:
            logger.error(f"❌ Error queuing child jobs: {e}")
    
    async def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get statistics for a crawl session.
        
        Args:
            session_id: Session ID
        
        Returns:
            Dictionary with session statistics
        """
        try:
            async with get_db_session() as db:
                # Get session
                stmt = select(CrawlSession).where(
                    CrawlSession.session_id == session_id
                )
                result = await db.execute(stmt)
                session = result.scalar_one_or_none()
                
                if not session:
                    return {}
                
                # Count jobs by status
                stmt = select(CrawlJob).where(
                    CrawlJob.session_id == session_id
                )
                result = await db.execute(stmt)
                all_jobs = result.scalars().all()
                
                stats = {
                    "session_id": session_id,
                    "domain": session.domain,
                    "status": session.status,
                    "total_jobs": len(all_jobs),
                    "completed_jobs": len([j for j in all_jobs if j.status == "completed"]),
                    "pending_jobs": len([j for j in all_jobs if j.status == "pending"]),
                    "processing_jobs": len([j for j in all_jobs if j.status == "processing"]),
                    "failed_jobs": len([j for j in all_jobs if j.status == "failed"]),
                }
                
                return stats
        
        except Exception as e:
            logger.error(f"❌ Error getting session stats: {e}")
            return {}
    
    async def worker_loop(self):
        """Main worker loop - continuously process pending jobs."""
        logger.info(f"🚀 Crawl worker started (max_concurrent={self.max_concurrent_jobs})")
        
        while self.is_running:
            try:
                # Get number of available slots
                available_slots = self.max_concurrent_jobs - len(self.active_jobs)
                
                if available_slots > 0:
                    # Fetch pending jobs
                    pending_jobs = await self.get_pending_jobs(limit=available_slots)
                    
                    if pending_jobs:
                        logger.info(f"📥 Fetched {len(pending_jobs)} jobs to process")
                        
                        # Process jobs concurrently
                        for job in pending_jobs:
                            if len(self.active_jobs) < self.max_concurrent_jobs:
                                task = asyncio.create_task(self.process_job(job))
                                self.active_jobs[job.job_id] = task
                    else:
                        logger.debug("⏳ No pending jobs, waiting...")
                
                # Clean up completed tasks
                completed = [job_id for job_id, task in self.active_jobs.items() if task.done()]
                for job_id in completed:
                    try:
                        result = self.active_jobs[job_id].result()
                        logger.info(f"✨ Job {job_id} result: {result}")
                    except Exception as e:
                        logger.error(f"❌ Job {job_id} failed: {e}")
                    finally:
                        del self.active_jobs[job_id]
                
                # Wait before next poll
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error(f"❌ Worker loop error: {e}")
                await asyncio.sleep(self.poll_interval)
    
    async def start(self):
        """Start the crawl worker."""
        self.is_running = True
        try:
            await self.worker_loop()
        except KeyboardInterrupt:
            logger.info("⏹️ Worker interrupted")
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the crawl worker and wait for active jobs."""
        logger.info("🛑 Stopping crawl worker...")
        self.is_running = False
        
        # Wait for active jobs to complete
        if self.active_jobs:
            logger.info(f"⏳ Waiting for {len(self.active_jobs)} active jobs to complete...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.active_jobs.values(), return_exceptions=True),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                logger.warning("⚠️ Some jobs did not complete in time")
        
        logger.info("✅ Crawl worker stopped")


# Global worker instance
crawl_worker = CrawlWorker(max_concurrent_jobs=3, poll_interval=5)
