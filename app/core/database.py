"""Database configuration and session management."""

import logging
import subprocess
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from app.core.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=40,
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


def run_alembic_migrations():
    """Run Alembic migrations synchronously."""
    try:
        logger.info("🔄 Running Alembic migrations...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd="/app",
        )
        
        if result.returncode == 0:
            logger.info("✅ Alembic migrations completed successfully")
            if result.stdout:
                logger.debug(f"Migration output: {result.stdout}")
        else:
            logger.warning(f"⚠️ Alembic migration had issues: {result.stderr}")
            if "No such table" in result.stderr or "does not exist" in result.stderr:
                logger.info("📝 Creating initial schema...")
    except FileNotFoundError:
        logger.warning("⚠️ Alembic command not found")
        logger.info("📝 Falling back to Base.metadata.create_all()")
    except Exception as e:
        logger.warning(f"⚠️ Could not run Alembic migrations: {e}")
        logger.info("📝 Falling back to Base.metadata.create_all()")


async def init_db():
    """Initialize database tables with Alembic migrations."""
    # First, try to run Alembic migrations
    run_alembic_migrations()
    
    # Then create any missing tables using SQLAlchemy metadata
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database schema ensured")
    except Exception as e:
        logger.error(f"❌ Failed to create database schema: {e}")
        raise


async def close_db():
    """Close database connection."""
    await engine.dispose()
