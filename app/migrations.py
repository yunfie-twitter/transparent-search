"""Database migration and initialization module.

This module is executed on container startup to ensure the database schema
is created and properly initialized before the FastAPI application runs.

Handles both:
  1. Fresh database initialization (creates all tables and indexes)
  2. Existing database (skips already-created tables and indexes)
"""

import logging
import asyncio

from sqlalchemy import inspect, text
from app.core.database import engine, Base
from app.db.models import CrawlSession, CrawlJob, CrawlMetadata, PageAnalysis, SearchContent

logger = logging.getLogger(__name__)


async def run_migrations():
    """Run all database migrations and initialization.
    
    Strategy:
    1. Check if tables already exist
    2. If fresh DB: create all tables + indexes (via Base.metadata.create_all)
    3. If existing DB: skip (tables already exist with indexes)
    
    Why this approach:
    - SQLAlchemy's create_all() is idempotent for tables
    - But composite indexes can fail if they already exist
    - Better to check first and only create what's missing
    """
    logger.info("🔧 Running database migrations...")
    
    try:
        # Connect to database and check for existing tables
        async with engine.begin() as conn:
            # Get inspector to check existing tables
            inspector = inspect(conn)
            existing_tables = await conn.run_sync(inspector.get_table_names)
            
            logger.info(f"📊 Existing tables in database: {existing_tables}")
            
            if not existing_tables:
                # Fresh database: create all tables with indexes
                logger.info("✨ Fresh database detected - Creating all tables and indexes...")
                await conn.run_sync(Base.metadata.create_all)
                logger.info("✅ All tables and indexes created successfully")
            else:
                # Existing database: verify required tables exist
                logger.info("📁 Existing database detected - Verifying schema...")
                
                required_tables = {
                    'crawl_sessions',
                    'crawl_jobs',
                    'crawl_metadata',
                    'page_analysis',
                    'search_content',
                }
                
                missing_tables = required_tables - set(existing_tables)
                
                if missing_tables:
                    logger.warning(f"⚠️  Missing tables: {missing_tables}")
                    logger.info("🔨 Creating missing tables...")
                    # Only create missing tables
                    for table in Base.metadata.sorted_tables:
                        if table.name in missing_tables:
                            logger.info(f"   Creating table: {table.name}")
                            table.create(conn, checkfirst=True)
                else:
                    logger.info("✅ All required tables exist")
                
                logger.info("📋 Schema verification complete")
        
        logger.info("✅ Database migration completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Database migration failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    """Run migrations when executed as module (python -m app.migrations)."""
    logger.info("🚀 Starting database migrations...")
    asyncio.run(run_migrations())
    logger.info("🌟 Migration script completed")
