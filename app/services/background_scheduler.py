"""Background scheduler for autonomous crawling operations."""
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from app.services.crawl_scheduler import crawl_scheduler

logger = logging.getLogger(__name__)

class BackgroundScheduler:
    """Manages background crawling tasks."""
    
    _scheduler: Optional[AsyncIOScheduler] = None
    _is_running = False
    
    @classmethod
    def initialize(cls) -> None:
        """Initialize background scheduler."""
        if cls._scheduler is not None:
            return
        
        cls._scheduler = AsyncIOScheduler()
        cls._setup_tasks()
        logger.info("🔄 Background scheduler initialized")
    
    @classmethod
    def _setup_tasks(cls) -> None:
        """Setup background tasks."""
        if cls._scheduler is None:
            return
        
        # Task 1: Auto-discover sites every 6 hours
        cls._scheduler.add_job(
            cls._auto_discover_sites_task,
            trigger=IntervalTrigger(hours=6),
            id="auto_discover_sites",
            name="Auto-discover sites for crawling",
            replace_existing=True,
        )
        logger.info("✅ Scheduled: Auto-discovery every 6 hours")
        
        # Task 2: Process crawl queue every 30 seconds
        cls._scheduler.add_job(
            cls._process_queue_task,
            trigger=IntervalTrigger(seconds=30),
            id="process_crawl_queue",
            name="Process crawl queue",
            replace_existing=True,
        )
        logger.info("✅ Scheduled: Queue processing every 30 seconds")
        
        # Task 3: Random interval crawl for each site (4-24 hours)
        # This runs once on startup and reschedules itself
        cls._scheduler.add_job(
            cls._schedule_random_crawls_task,
            trigger=IntervalTrigger(hours=12),
            id="schedule_random_crawls",
            name="Schedule random interval crawls",
            replace_existing=True,
        )
        logger.info("✅ Scheduled: Random crawl scheduling every 12 hours")
    
    @classmethod
    async def start(cls) -> None:
        """Start background scheduler."""
        if cls._scheduler is None:
            cls.initialize()
        
        if cls._is_running:
            logger.warning("Scheduler already running")
            return
        
        cls._scheduler.start()
        cls._is_running = True
        logger.info("🚀 Background scheduler started")
    
    @classmethod
    async def stop(cls) -> None:
        """Stop background scheduler gracefully."""
        if cls._scheduler is None or not cls._is_running:
            return
        
        cls._scheduler.shutdown(wait=True)
        cls._is_running = False
        logger.info("🛛️ Background scheduler stopped")
    
    @classmethod
    def get_jobs(cls) -> list:
        """Get list of scheduled jobs."""
        if cls._scheduler is None:
            return []
        
        jobs = []
        for job in cls._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "trigger": str(job.trigger),
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        
        return jobs
    
    @classmethod
    async def _auto_discover_sites_task(cls) -> None:
        """Background task: Auto-discover sites and schedule crawls."""
        logger.info("🔍 Running auto-discovery task...")
        
        try:
            result = await crawl_scheduler.discover_and_schedule_sites()
            logger.info(
                f"✅ Auto-discovery complete: {result['crawls_scheduled']} crawls scheduled"
            )
        except Exception as e:
            logger.error(f"Auto-discovery task error: {e}")
    
    @classmethod
    async def _process_queue_task(cls) -> None:
        """Background task: Process crawl queue continuously."""
        # This runs every 30 seconds but only if not paused
        if not crawl_scheduler._crawl_enabled or crawl_scheduler._force_stop:
            return
        
        try:
            result = await crawl_scheduler.process_crawl_queue()
            if result["processed"] > 0:
                logger.info(f"📋 Processed {result['processed']} crawl jobs")
        except Exception as e:
            logger.error(f"Queue processing task error: {e}")
    
    @classmethod
    async def _schedule_random_crawls_task(cls) -> None:
        """Background task: Schedule random interval crawls."""
        logger.info("🌀 Running random crawl scheduling...")
        
        try:
            # This will be expanded to schedule individual site crawls
            # with random intervals
            result = await crawl_scheduler.discover_and_schedule_sites()
            logger.info(f"✅ Random scheduling complete: {result['crawls_scheduled']} sites")
        except Exception as e:
            logger.error(f"Random scheduling task error: {e}")


background_scheduler = BackgroundScheduler()


# FastAPI startup/shutdown hooks
async def start_background_scheduler() -> None:
    """Called on FastAPI startup."""
    logger.info("🚀 Starting background scheduler...")
    await background_scheduler.start()


async def stop_background_scheduler() -> None:
    """Called on FastAPI shutdown."""
    logger.info("🛑 Stopping background scheduler...")
    await background_scheduler.stop()
