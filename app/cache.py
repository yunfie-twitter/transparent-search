"""Redis cache client for search results and intent detection."""

import os
import redis.asyncio as redis
from typing import Optional

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").lower() == "true"

# Cache TTLs (in seconds)
CACHE_TTL_INTENT = 3600  # 1 hour for intent detection
CACHE_TTL_SEARCH = 300   # 5 minutes for search results
CACHE_TTL_TRACKER = 86400  # 24 hours for tracker risk distribution
CACHE_TTL_CONTENT = 86400  # 24 hours for content type distribution

_redis_pool: Optional[redis.ConnectionPool] = None
_redis_client: Optional[redis.Redis] = None


async def init_redis() -> Optional[redis.Redis]:
    """Initialize Redis connection pool."""
    global _redis_pool, _redis_client
    
    if not REDIS_ENABLED:
        return None
    
    try:
        _redis_pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            max_connections=20,
            decode_responses=True,
        )
        _redis_client = redis.Redis(connection_pool=_redis_pool)
        
        # Test connection
        await _redis_client.ping()
        print(f"✓ Redis connected: {REDIS_HOST}:{REDIS_PORT}")
        return _redis_client
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        return None


async def close_redis():
    """Close Redis connection pool."""
    global _redis_pool, _redis_client
    
    if _redis_client:
        await _redis_client.close()
    if _redis_pool:
        await _redis_pool.disconnect()
    
    _redis_client = None
    _redis_pool = None


async def get_redis_client() -> Optional[redis.Redis]:
    """Get Redis client for dependency injection."""
    global _redis_client
    
    if not REDIS_ENABLED:
        return None
    
    if _redis_client is None:
        await init_redis()
    
    try:
        # Test connection
        if _redis_client:
            await _redis_client.ping()
            return _redis_client
    except Exception:
        # Reconnect on failure
        try:
            await close_redis()
            await init_redis()
        except Exception:
            pass
    
    return _redis_client


class CacheManager:
    """High-level cache manager for search operations."""
    
    def __init__(self, redis_client: Optional[redis.Redis]):
        self.redis = redis_client
    
    async def get_intent(self, query: str) -> Optional[dict]:
        """Get cached intent detection result."""
        if not self.redis:
            return None
        
        try:
            import json
            import hashlib
            
            cache_key = f"intent:{hashlib.sha256(query.encode()).hexdigest()[:16]}"
            result = await self.redis.get(cache_key)
            
            if result:
                return json.loads(result)
        except Exception:
            pass
        
        return None
    
    async def set_intent(self, query: str, intent_data: dict, ttl: int = CACHE_TTL_INTENT):
        """Cache intent detection result."""
        if not self.redis:
            return
        
        try:
            import json
            import hashlib
            
            cache_key = f"intent:{hashlib.sha256(query.encode()).hexdigest()[:16]}"
            await self.redis.setex(
                cache_key,
                ttl,
                json.dumps(intent_data)
            )
        except Exception:
            pass
    
    async def get_search(self, query: str, limit: int, offset: int, filters: str) -> Optional[dict]:
        """Get cached search result."""
        if not self.redis:
            return None
        
        try:
            import json
            import hashlib
            
            query_key = f"{query}:{limit}:{offset}:{filters}"
            cache_key = f"search:{hashlib.sha256(query_key.encode()).hexdigest()[:16]}"
            result = await self.redis.get(cache_key)
            
            if result:
                return json.loads(result)
        except Exception:
            pass
        
        return None
    
    async def set_search(self, query: str, limit: int, offset: int, filters: str, result: dict, ttl: int = CACHE_TTL_SEARCH):
        """Cache search result."""
        if not self.redis:
            return
        
        try:
            import json
            import hashlib
            
            query_key = f"{query}:{limit}:{offset}:{filters}"
            cache_key = f"search:{hashlib.sha256(query_key.encode()).hexdigest()[:16]}"
            await self.redis.setex(
                cache_key,
                ttl,
                json.dumps(result, default=str)
            )
        except Exception:
            pass
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all cache keys matching pattern."""
        if not self.redis:
            return 0
        
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                return await self.redis.delete(*keys)
        except Exception:
            pass
        
        return 0
    
    async def invalidate_all(self) -> int:
        """Invalidate all search-related cache."""
        if not self.redis:
            return 0
        
        count = 0
        for pattern in ["search:*", "intent:*", "tracker:*", "content:*"]:
            count += await self.invalidate_pattern(pattern)
        
        return count
