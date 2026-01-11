"""Core module - Application core functionality (config, database, cache, schemas)."""

from app.core.cache import (
    init_redis,
    close_redis,
    get_redis_client,
    CacheManager,
)
from app.core.database import (
    engine,
    async_session,
    Base,
    get_db,
    get_db_session,
    init_db,
    close_db,
)
from app.core.config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    DATABASE_URL,
)

__all__ = [
    # Cache
    "init_redis",
    "close_redis",
    "get_redis_client",
    "CacheManager",
    # Database
    "engine",
    "async_session",
    "Base",
    "get_db",
    "get_db_session",
    "init_db",
    "close_db",
    # Config
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "DATABASE_URL",
]
