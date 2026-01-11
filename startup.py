#!/usr/bin/env python3
"""Pre-startup initialization script for Transparent Search.

This script ensures critical initialization happens BEFORE Uvicorn starts,
including database setup, Redis connection, and worker startup.
"""

import asyncio
import logging
import sys

from app.core.database import init_db, get_db_session
from app.core.cache import init_redis
from app.services.crawl_worker import crawl_worker
from app.services.crawler import crawler_service
from sqlalchemy import select, func
from app.db.models import CrawlJob, CrawlSession

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_pending_jobs() -> dict:
    """Check pending jobs in database."""
    try:
        async with get_db_session() as db:
            # Count all jobs by status
            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "pending"
            )
            result = await db.execute(stmt)
            pending_count = result.scalar() or 0

            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "completed"
            )
            result = await db.execute(stmt)
            completed_count = result.scalar() or 0

            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "processing"
            )
            result = await db.execute(stmt)
            processing_count = result.scalar() or 0

            stmt = select(func.count(CrawlJob.job_id)).where(
                CrawlJob.status == "failed"
            )
            result = await db.execute(stmt)
            failed_count = result.scalar() or 0

            return {
                "pending": pending_count,
                "completed": completed_count,
                "processing": processing_count,
                "failed": failed_count,
                "total": pending_count + completed_count + processing_count + failed_count,
            }
    except Exception as e:
        logger.error(f"❌ Failed to check pending jobs: {e}")
        return {
            "error": str(e),
            "pending": 0,
            "completed": 0,
            "processing": 0,
            "failed": 0,
            "total": 0,
        }


async def create_test_jobs():
    """Create test crawl jobs for worker to process."""
    try:
        logger.info("🤓 Creating test crawl session and jobs...")
        
        # Create a test crawl session
        session = await crawler_service.create_crawl_session(
            domain="momon-ga.com",
            max_depth=3,
            page_limit=100
        )
        logger.info(f"✅ Created session: {session.session_id}")
        
        # Create initial job for domain root
        job = await crawler_service.create_crawl_job(
            session_id=session.session_id,
            domain="momon-ga.com",
            url="https://momon-ga.com",
            depth=0,
            max_depth=3,
            enable_js_rendering=False,
        )
        logger.info(f"✅ Created job: {job.job_id} for {job.url}")
        
        return True
    except Exception as e:
        logger.warning(f"⚠️ Failed to create test jobs: {e}")
        return False


async def startup_tasks():
    """Run all startup tasks before Uvicorn starts."""
    logger.info("🚀 Pre-startup initialization beginning...")

    # Initialize database
    logger.info("💾 Initializing database...")
    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False

    # Connect to Redis cache
    logger.info("🙋 Connecting to Redis cache...")
    try:
        await init_redis()
        logger.info("✅ Redis cache connected")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        return False

    # Check pending jobs
    logger.info("🔍 Checking pending jobs in database...")
    try:
        job_stats = await check_pending_jobs()
        logger.info(
            f"📋 Database Job Stats: "
            f"total={job_stats['total']}, "
            f"pending={job_stats['pending']}, "
            f"processing={job_stats['processing']}, "
            f"completed={job_stats['completed']}, "
            f"failed={job_stats['failed']}"
        )
        
        # If no pending jobs, create test jobs
        if job_stats['pending'] == 0:
            logger.info("😵 No pending jobs found, creating test jobs...")
            test_created = await create_test_jobs()
            if test_created:
                # Re-check stats after creating test jobs
                job_stats = await check_pending_jobs()
                logger.info(
                    f"📋 Updated Job Stats: "
                    f"total={job_stats['total']}, "
                    f"pending={job_stats['pending']}, "
                    f"processing={job_stats['processing']}, "
                    f"completed={job_stats['completed']}, "
                    f"failed={job_stats['failed']}"
                )
        
        if job_stats['pending'] > 0:
            logger.info(f"🔄 Will process {job_stats['pending']} pending job(s) when worker starts")
    except Exception as e:
        logger.error(f"❌ Failed to retrieve job stats: {e}")

    logger.info("🌟 Pre-startup initialization complete")
    return True


def main():
    """Main entry point."""
    logger.info("🚀 Transparent Search startup sequence starting...")

    try:
        # Run async startup tasks
        success = asyncio.run(startup_tasks())
        if not success:
            logger.error("❌ Startup failed")
            sys.exit(1)

        logger.info("✅ All startup tasks completed successfully")
        logger.info("🎯 Ready to start Uvicorn server")
        return True

    except Exception as e:
        logger.error(f"❌ Unexpected error during startup: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
