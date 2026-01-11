"""Database migration and initialization module.

This module is executed on container startup to ensure the database schema
is created and properly initialized before the FastAPI application runs.
"""

import logging
import asyncio

from app.core.database import init_db

logger = logging.getLogger(__name__)


async def run_migrations():
    """Run all database migrations and initialization."""
    logger.info("🔧 Running database migrations...")
    
    try:
        # Initialize database: create tables, indexes, etc.
        await init_db()
        logger.info("✅ Database migration completed successfully")
    except Exception as e:
        logger.error(f"❌ Database migration failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    """Run migrations when executed as module (python -m app.migrations)."""
    logger.info("🚀 Starting database migrations...")
    asyncio.run(run_migrations())
    logger.info("🌟 Migration script completed")
