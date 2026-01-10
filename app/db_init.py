"""Database initialization and migration utilities"""
import asyncio
import logging
from sqlalchemy import text, inspect
import os

from .db.database import Base, engine, init_db as db_init
from .db import models  # Import all models to register them

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost/search_engine"
)

async def check_table_exists(table_name: str) -> bool:
    """Check if table exists."""
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = :table_name
                    )
                """)
                ,
                {"table_name": table_name}
            )
            return result.scalar()
    except Exception as e:
        logger.error(f"⚠️ Table existence check failed: {e}")
        return False

async def create_tables_from_init_sql():
    """Create tables from init.sql if it exists (legacy support)."""
    sql_file = '/code/db/init.sql'
    
    if not os.path.exists(sql_file):
        logger.info("ℹ️ init.sql not found (using SQLAlchemy models)")
        return True
    
    try:
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        if not sql_content.strip():
            logger.info("ℹ️ init.sql is empty (using SQLAlchemy models)")
            return True
        
        # Execute statements
        async with engine.begin() as conn:
            statements = sql_content.split(';')
            successful = 0
            failed = 0
            
            for i, statement in enumerate(statements):
                statement = statement.strip()
                if not statement:
                    continue
                
                try:
                    await conn.execute(text(statement))
                    successful += 1
                except Exception as e:
                    failed += 1
                    logger.debug(f"⚠️ Statement {i} warning (may be expected): {type(e).__name__}")
            
            await conn.commit()
            logger.info(f"✅ Legacy init.sql applied: {successful} successful, {failed} warnings")
        
        return True
    
    except Exception as e:
        logger.error(f"⚠️ Failed to execute init.sql: {e}")
        return False

async def init_db():
    """Initialize database with SQLAlchemy models."""
    
    try:
        logger.info("📋 Creating database tables from SQLAlchemy models...")
        
        # Create tables using SQLAlchemy
        await db_init()
        logger.info("✅ SQLAlchemy models created successfully")
        
        # Try to execute legacy init.sql (for existing data/functions)
        legacy_result = await create_tables_from_init_sql()
        
        # Verify critical crawl tables
        critical_tables = [
            'crawl_sessions',
            'crawl_jobs',
            'crawl_metadata',
            'page_analysis',
        ]
        
        missing_tables = []
        for table in critical_tables:
            exists = await check_table_exists(table)
            if not exists:
                missing_tables.append(table)
                logger.warning(f"⚠️ Table '{table}' not found")
        
        if missing_tables:
            raise RuntimeError(f"Critical tables missing: {', '.join(missing_tables)}")
        
        logger.info("✅ All critical crawl tables verified")
        
        # Try to verify search tables from init.sql
        legacy_tables = ['sites', 'pages', 'content_classifications', 'query_clusters', 'intent_classifications']
        legacy_missing = []
        
        for table in legacy_tables:
            exists = await check_table_exists(table)
            if not exists:
                legacy_missing.append(table)
        
        if legacy_missing:
            logger.warning(f"⚠️ Legacy search tables missing: {', '.join(legacy_missing)}")
            logger.info("ℹ️ These tables are optional if using new ORM schema")
        
        logger.info("✅ Database initialization completed successfully")
        
    except FileNotFoundError as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise

async def run_migrations():
    """Run pending database migrations."""
    try:
        await init_db()
        logger.info("✅ Database migrations completed successfully")
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(run_migrations())
