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
from sqlalchemy.schema import CreateTable, CreateIndex
from app.core.database import engine, Base
from app.db.models import CrawlSession, CrawlJob, CrawlMetadata, PageAnalysis, SearchContent

logger = logging.getLogger(__name__)


def _get_table_names(connection):
    """Get existing table names (sync function for run_sync)."""
    inspector = inspect(connection)
    return inspector.get_table_names()


def _create_all_tables_and_indexes(connection):
    """Create all tables and indexes manually with if_not_exists.
    
    Strategy:
    - DON'T use Base.metadata.create_all() (doesn't support if_not_exists for indexes)
    - Manually create each table with CreateTable(..., if_not_exists=True)
    - Manually create each index with CreateIndex(..., if_not_exists=True)
    
    Why manual creation:
    1. Idempotent: if_not_exists prevents "already exists" errors
    2. Safe: Can run multiple times without side effects
    3. Clear: Explicit control over what's being created
    """
    logger.info("   Creating tables and indexes manually...")
    
    # Create tables first (in dependency order)
    for table in Base.metadata.sorted_tables:
        try:
            create_table = CreateTable(table, if_not_exists=True)
            connection.execute(create_table)
            logger.debug(f"   Table ensured: {table.name}")
        except Exception as e:
            logger.error(f"   Failed to create table {table.name}: {e}")
            raise
    
    # Then create indexes with if_not_exists
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            try:
                create_index = CreateIndex(index, if_not_exists=True)
                connection.execute(create_index)
                logger.debug(f"   Index ensured: {index.name}")
            except Exception as e:
                logger.error(f"   Failed to create index {index.name}: {e}")
                raise


def _create_missing_tables_and_indexes(connection, missing_tables):
    """Create only missing tables and their indexes (sync function for run_sync).
    
    Uses same manual creation strategy as _create_all_tables_and_indexes.
    """
    logger.info("   Creating missing tables and indexes manually...")
    
    # Create only missing tables
    for table in Base.metadata.sorted_tables:
        if table.name in missing_tables:
            try:
                create_table = CreateTable(table, if_not_exists=True)
                connection.execute(create_table)
                logger.debug(f"   Table created: {table.name}")
            except Exception as e:
                logger.error(f"   Failed to create table {table.name}: {e}")
                raise
    
    # Create indexes for missing tables with if_not_exists
    for table in Base.metadata.sorted_tables:
        if table.name in missing_tables:
            for index in table.indexes:
                try:
                    create_index = CreateIndex(index, if_not_exists=True)
                    connection.execute(create_index)
                    logger.debug(f"   Index created: {index.name}")
                except Exception as e:
                    logger.error(f"   Failed to create index {index.name}: {e}")
                    raise


async def run_migrations():
    """Run all database migrations and initialization.
    
    Strategy:
    1. Check if tables already exist via inspector
    2. If fresh DB: manually create all tables + indexes with if_not_exists
    3. If existing DB: verify required tables exist, create missing ones only
    
    Idempotent Design:
    - All table/index creation uses if_not_exists=True
    - Safe to run multiple times
    - No "already exists" errors
    
    AsyncConnection Note:
    - AsyncConnection doesn't support inspect() directly
    - Must use connection.run_sync(callable) to run sync code
    - This runs the callable in a thread pool executor
    """
    logger.info("🔧 Running database migrations...")
    
    try:
        # Connect to database and check for existing tables
        async with engine.begin() as conn:
            # Get existing tables using run_sync
            # inspect() requires sync code, so wrap it with run_sync
            existing_tables = await conn.run_sync(_get_table_names)
            
            logger.info(f"📚 Existing tables in database: {existing_tables}")
            
            if not existing_tables:
                # Fresh database: create all tables with indexes
                logger.info("✨ Fresh database detected - Creating all tables and indexes...")
                await conn.run_sync(_create_all_tables_and_indexes)
                logger.info("✅ All tables and indexes created successfully")
            else:
                # Existing database: verify required tables exist
                logger.info("📑 Existing database detected - Verifying schema...")
                
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
                    # Create only missing tables and their indexes
                    await conn.run_sync(_create_missing_tables_and_indexes, missing_tables)
                    logger.info("✅ Missing tables and indexes created successfully")
                else:
                    logger.info("✅ All required tables exist - Skipping schema creation")
                
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
