#!/usr/bin/env python3
"""Cleanup corrupted search content entries."""
import asyncio
import logging
from sqlalchemy import select

from app.core.database import get_db_session
from app.db.models import SearchContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cleanup_empty_titles():
    """Delete SearchContent entries with NULL or 'Untitled' titles."""
    async with get_db_session() as db:
        # Query for entries with NULL or 'Untitled' titles
        query = select(SearchContent).where(
            (SearchContent.title == None) |  # NULL
            (SearchContent.title == "Untitled") |  # "Untitled" default
            (SearchContent.title == "")  # Empty string
        )
        
        result = await db.execute(query)
        items = result.scalars().all()
        
        logger.info(f"Found {len(items)} SearchContent entries with empty/untitled titles")
        
        if not items:
            logger.info("No cleanup needed")
            return
        
        # Delete them
        for item in items:
            logger.info(f"Deleting: {item.url} (title='{item.title}')")
            await db.delete(item)
        
        await db.commit()
        logger.info(f"✅ Deleted {len(items)} corrupted entries")
        logger.info("Now run: POST /api/admin/index/bulk-reindex?skip_existing=false")


async def main():
    """Main entry point."""
    logger.info("🧹 Starting search index cleanup...")
    await cleanup_empty_titles()
    logger.info("✅ Cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
