"""Database initialization and migration utilities"""
import asyncio
import logging
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost/search_engine"
)

async def check_table_exists(engine, table_name: str) -> bool:
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

async def init_db():
    """Initialize database with schema from init.sql"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    try:
        # Read init.sql
        sql_file = '/code/db/init.sql'
        if not os.path.exists(sql_file):
            logger.error(f"⚠️ init.sql not found at {sql_file}")
            raise FileNotFoundError(f"init.sql not found at {sql_file}")
        
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        if not sql_content.strip():
            logger.error("⚠️ init.sql is empty")
            raise ValueError("init.sql is empty")
        
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
                    # Log but continue for idempotent operations (e.g., CREATE TABLE IF NOT EXISTS)
                    logger.debug(f"⚠️ Statement {i} warning (may be expected): {type(e).__name__}")
            
            await conn.commit()
            logger.info(f"✅ Database initialized: {successful} successful, {failed} warnings")
        
        # Verify critical tables
        critical_tables = ['sites', 'pages', 'content_classifications', 'query_clusters', 'intent_classifications']
        missing_tables = []
        
        for table in critical_tables:
            exists = await check_table_exists(engine, table)
            if not exists:
                missing_tables.append(table)
                logger.warning(f"⚠️ Table '{table}' not found")
        
        if missing_tables:
            raise RuntimeError(f"Critical tables missing: {', '.join(missing_tables)}")
        
        logger.info("✅ All critical tables verified")
        
    except FileNotFoundError as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    finally:
        await engine.dispose()

async def run_migrations():
    """Run pending database migrations"""
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
