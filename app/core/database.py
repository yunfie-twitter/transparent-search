"""Database configuration and session management."""

import asyncio
import logging
import os
from sqlalchemy import event, pool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from sqlalchemy.exc import OperationalError, DBAPIError

from app.core.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Connection retry settings
DB_CONNECTION_TIMEOUT = int(os.getenv('DB_CONNECTION_TIMEOUT', '30'))
DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '20'))
DB_POOL_OVERFLOW = int(os.getenv('DB_POOL_OVERFLOW', '40'))
DB_POOL_RECYCLE = 3600  # Recycle connections every hour

# Create async engine with connection pooling
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,  # Test connection before use
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_POOL_OVERFLOW,
    pool_recycle=DB_POOL_RECYCLE,
    connect_args={
        'timeout': DB_CONNECTION_TIMEOUT,
        'command_timeout': DB_CONNECTION_TIMEOUT,
    },
)

# Create async session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base for ORM models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database session (for service layer)."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def wait_for_db(max_retries: int = 10, initial_delay: float = 2.0) -> bool:
    """Wait for database to be ready with exponential backoff.
    
    Args:
        max_retries: Maximum number of connection attempts
        initial_delay: Initial delay in seconds before first retry
    
    Returns:
        True if database is ready, False if all retries failed
    """
    delay = initial_delay
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔌 Database connection attempt {attempt}/{max_retries}...")
            
            # Try to create a connection
            async with engine.connect() as conn:
                await conn.execute("SELECT 1")
                logger.info(f"✅ Database connection successful")
                return True
                
        except (OperationalError, DBAPIError, asyncio.TimeoutError) as e:
            if attempt == max_retries:
                logger.error(f"❌ Failed to connect to database after {max_retries} attempts: {e}")
                return False
            
            logger.warning(
                f"⚠️ Database connection failed (attempt {attempt}/{max_retries}). "
                f"Retrying in {delay}s... Error: {type(e).__name__}"
            )
            await asyncio.sleep(delay)
            # Exponential backoff: double the delay each time (capped at 30s)
            delay = min(delay * 2, 30.0)
        except Exception as e:
            logger.error(f"❌ Unexpected error during database connection: {e}")
            return False
    
    return False


async def init_db():
    """Initialize database tables using SQLAlchemy metadata.
    
    This creates all tables defined in the ORM models if they don't exist.
    For complex migrations, use Alembic separately via CLI.
    
    Includes retry logic for database availability.
    """
    # First, wait for database to be ready
    db_ready = await wait_for_db(max_retries=10, initial_delay=2.0)
    if not db_ready:
        logger.error("❌ Database is not ready after retries. Skipping schema creation.")
        raise RuntimeError("Database is not available")
    
    try:
        logger.info("💾 Creating database tables from ORM models...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database schema ensured")
    except Exception as e:
        logger.error(f"❌ Failed to create database schema: {e}")
        raise


async def close_db():
    """Close database connection."""
    try:
        await engine.dispose()
        logger.info("✅ Database connection closed")
    except Exception as e:
        logger.error(f"⚠️ Error closing database connection: {e}")
