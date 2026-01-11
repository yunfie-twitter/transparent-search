"""Crawl worker service - processes crawl jobs from queue with optimized management."""
import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.db.models import CrawlJob, CrawlSession
from app.services.crawler import crawler_service

logger = logging.getLogger(__name__)


@dataclass
class WorkerMetrics:
    """Worker performance metrics."""
    total_processed: int = 0
    total_successful: int = 0
    total_failed: int = 0
    total_queued: int = 0
    avg_job_time: float = 0.0
    start_time: datetime = None
    
    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.utcnow()
    
    @property
    def uptime_seconds(self) -> float:
        """Get worker uptime in seconds."""
        return (datetime.utcnow() - self.start_time).total_seconds()
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_processed == 0:
            return 0.0
        return (self.total_successful / self.total_processed) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_processed": self.total_processed,
            "total_successful": self.total_successful,
            "total_failed": self.total_failed,
            "total_queued": self.total_queued,
            "success_rate": f"{self.success_rate:.1f}%",
            "avg_job_time_ms": f"{self.avg_job_time:.0f}ms",
            "uptime_seconds": f"{self.uptime_seconds:.1f}s",
        }


class CrawlWorker:
    """Worker that processes crawl jobs from the queue with optimized management."""
    
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
        self.job_times: Dict[str, float] = {}  # Track job execution times
        self.metrics = WorkerMetrics()
    
    async def get_pending_jobs(
        self,
        limit: int = 10,
        session_id: Optional[str] = None,
    ) -> List[CrawlJob]:
        """Get pending crawl jobs from database with priority sorting.
        
        Args:
            limit: Maximum number of jobs to fetch
            session_id: Filter by specific session (optional)
        
        Returns:
            List of pending CrawlJob objects sorted by priority
        """
        try:
            async with get_db_session() as db:
                # Build query for pending jobs with multi-level priority
                query = select(CrawlJob).where(
                    CrawlJob.status == "pending"
                ).order_by(
                    CrawlJob.depth.asc(),  # Shallower depths first (breadth-first)
                    CrawlJob.priority.asc(),  # Then by priority (lower = higher urgency)
                    CrawlJob.created_at.asc(),  # Then by creation time (FIFO)
                ).limit(limit)
                
                # Filter by session if specified
                if session_id:
                    query = query.where(CrawlJob.session_id == session_id)
                
                result = await db.execute(query)
                jobs = result.scalars().all()
                
                if jobs:
                    logger.info(
                        f"📬 Found {len(jobs)} pending jobs "
                        f"(available slots: {self.max_concurrent_jobs - len(self.active_jobs)})"
                    )
                return list(jobs)
        
        except Exception as e:
            logger.error(f"❌ Error fetching pending jobs: {e}")
            return []
    
    async def process_job(self, job: CrawlJob) -> bool:
        """Process a single crawl job with timing tracking.
        
        Args:
            job: CrawlJob to process
        
        Returns:
            True if successful, False otherwise
        """
        job_id = job.job_id
        job_key = job_id[:8]
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"🔄 Processing job {job_key}: {job.url} (depth: {job.depth})")
            self.metrics.total_processed += 1
            
            # Execute the actual crawl
            result = await crawler_service.execute_crawl_job(
                job_id=job.job_id,
                session_id=job.session_id,
                domain=job.domain,
                url=job.url,
                depth=job.depth,
                max_depth=job.max_depth,
            )
            
            # Calculate execution time
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.job_times[job_id] = execution_time
            
            # Update average job time
            if self.metrics.total_processed > 0:
                self.metrics.avg_job_time = sum(self.job_times.values()) / len(self.job_times)
            
            if result:
                urls_to_crawl = result.get("urls_to_crawl", [])
                self.metrics.total_queued += len(urls_to_crawl)
                
                logger.info(
                    f"✅ Job {job_key} completed in {execution_time:.0f}ms "
                    f"→ {len(urls_to_crawl)} URLs queued"
                )
                self.metrics.total_successful += 1
                return True
            else:
                logger.warning(f"⚠️ Job {job_key} failed (execution time: {execution_time:.0f}ms)")
                self.metrics.total_failed += 1
                return False
        
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(f"❌ Error processing job {job_key}: {e} (execution time: {execution_time:.0f}ms)")
            await crawler_service.update_crawl_job_status(job.job_id, "failed")
            self.metrics.total_failed += 1
            return False
    
    async def get_worker_status(self) -> Dict[str, Any]:
        """Get current worker status and metrics.
        
        Returns:
            Dictionary with worker status
        """
        try:
            active_count = len(self.active_jobs)
            available_slots = self.max_concurrent_jobs - active_count
            
            # Get global queue stats
            async with get_db_session() as db:
                pending_stmt = select(func.count(CrawlJob.job_id)).where(
                    CrawlJob.status == "pending"
                )
                pending_result = await db.execute(pending_stmt)
                total_pending = pending_result.scalar() or 0
                
                processing_stmt = select(func.count(CrawlJob.job_id)).where(
                    CrawlJob.status == "processing"
                )
                processing_result = await db.execute(processing_stmt)
                total_processing = processing_result.scalar() or 0
            
            return {
                "is_running": self.is_running,
                "active_jobs": active_count,
                "available_slots": available_slots,
                "max_concurrent_jobs": self.max_concurrent_jobs,
                "poll_interval": self.poll_interval,
                "global_queue": {
                    "pending": total_pending,
                    "processing": total_processing,
                },
                "metrics": self.metrics.to_dict(),
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting worker status: {e}")
            return {}
    
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
                
                completed = [j for j in all_jobs if j.status == "completed"]
                pending = [j for j in all_jobs if j.status == "pending"]
                processing = [j for j in all_jobs if j.status == "processing"]
                failed = [j for j in all_jobs if j.status == "failed"]
                
                # Calculate progress
                total = len(all_jobs)
                progress = (len(completed) / total * 100) if total > 0 else 0
                
                stats = {
                    "session_id": session_id,
                    "domain": session.domain,
                    "status": session.status,
                    "progress": f"{progress:.1f}%",
                    "total_jobs": total,
                    "completed_jobs": len(completed),
                    "pending_jobs": len(pending),
                    "processing_jobs": len(processing),
                    "failed_jobs": len(failed),
                    "avg_depth": sum(j.depth for j in all_jobs) / total if total > 0 else 0,
                }
                
                return stats
        
        except Exception as e:
            logger.error(f"❌ Error getting session stats: {e}")
            return {}
    
    async def worker_loop(self):
        """Main worker loop - continuously process pending jobs with optimization."""
        logger.info(
            f"🚀 Crawl worker started "
            f"(max_concurrent={self.max_concurrent_jobs}, poll_interval={self.poll_interval}s)"
        )
        
        consecutive_empty_polls = 0
        adaptive_poll_interval = self.poll_interval
        
        try:
            while self.is_running:
                try:
                    # Get number of available slots
                    available_slots = self.max_concurrent_jobs - len(self.active_jobs)
                    
                    if available_slots > 0:
                        # Fetch pending jobs
                        pending_jobs = await self.get_pending_jobs(limit=available_slots)
                        
                        if pending_jobs:
                            consecutive_empty_polls = 0
                            adaptive_poll_interval = self.poll_interval
                            
                            logger.info(
                                f"📥 Starting {len(pending_jobs)} jobs "
                                f"(active: {len(self.active_jobs)}/{self.max_concurrent_jobs})"
                            )
                            
                            # Process jobs concurrently
                            for job in pending_jobs:
                                if len(self.active_jobs) < self.max_concurrent_jobs:
                                    task = asyncio.create_task(self.process_job(job))
                                    self.active_jobs[job.job_id] = task
                        else:
                            # Adaptive polling: increase interval when queue is empty
                            if len(self.active_jobs) == 0:
                                consecutive_empty_polls += 1
                                # Gradually increase poll interval up to 30 seconds
                                adaptive_poll_interval = min(
                                    self.poll_interval + (consecutive_empty_polls * 2),
                                    30
                                )
                                logger.debug(
                                    f"⏳ No pending jobs, idle... "
                                    f"(adaptive poll_interval: {adaptive_poll_interval}s)"
                                )
                    
                    # Clean up completed tasks
                    completed = [job_id for job_id, task in self.active_jobs.items() if task.done()]
                    for job_id in completed:
                        try:
                            result = self.active_jobs[job_id].result()
                            logger.debug(f"✨ Job {job_id[:8]} task completed")
                        except Exception as e:
                            logger.error(f"❌ Job {job_id[:8]} task failed: {e}")
                        finally:
                            del self.active_jobs[job_id]
                    
                    # Wait before next poll (using adaptive interval)
                    await asyncio.sleep(adaptive_poll_interval)
                
                except asyncio.CancelledError:
                    logger.info("⏹️ Worker loop cancelled")
                    raise
                except Exception as e:
                    logger.error(f"❌ Worker loop error: {e}", exc_info=True)
                    await asyncio.sleep(adaptive_poll_interval)
        
        finally:
            logger.info(
                f"🛑 Crawl worker stopped "
                f"(stats: {self.metrics.to_dict()})"
            )
    
    async def stop(self):
        """Stop the crawl worker and wait for active jobs."""
        logger.info(f"🙋 Stopping crawl worker (active jobs: {len(self.active_jobs)})...")
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
                # Force cancel remaining tasks
                for task in self.active_jobs.values():
                    if not task.done():
                        task.cancel()
        
        logger.info(f"✅ Crawl worker cleanup complete")


# Global worker instance
crawl_worker = CrawlWorker(max_concurrent_jobs=3, poll_interval=5)
