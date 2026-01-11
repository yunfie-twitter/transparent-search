"""Redis cache client for search results and intent detection."""

import redis.asyncio as redis
from typing import Optional
import json
import hashlib

from app.core.config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PASSWORD,
    REDIS_ENABLED,
    CACHE_TTL_INTENT,
    CACHE_TTL_SEARCH,
    CACHE_TTL_TRACKER,
    CACHE_TTL_CONTENT,
)

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
    
    @staticmethod
    def _make_cache_key(prefix: str, value: str) -> str:
        """Generate cache key with hash."""
        return f"{prefix}:{hashlib.sha256(value.encode()).hexdigest()[:16]}"
    
    async def get_intent(self, query: str) -> Optional[dict]:
        """Get cached intent detection result."""
        if not self.redis:
            return None
        
        try:
            cache_key = self._make_cache_key("intent", query)
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
            cache_key = self._make_cache_key("intent", query)
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
            query_key = f"{query}:{limit}:{offset}:{filters}"
            cache_key = self._make_cache_key("search", query_key)
            result = await self.redis.get(cache_key)
            
            if result:
                return json.loads(result)
        except Exception:
            pass
        
        return None
    
    async def set_search(
        self,
        query: str,
        limit: int,
        offset: int,
        filters: str,
        result: dict,
        ttl: int = CACHE_TTL_SEARCH
    ):
        """Cache search result."""
        if not self.redis:
            return
        
        try:
            query_key = f"{query}:{limit}:{offset}:{filters}"
            cache_key = self._make_cache_key("search", query_key)
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
    
    # Crawler-specific cache methods
    async def get_metadata(self, url: str) -> Optional[dict]:
        """Get cached page metadata."""
        if not self.redis:
            return None
        
        try:
            cache_key = self._make_cache_key("metadata", url)
            result = await self.redis.get(cache_key)
            if result:
                return json.loads(result)
        except Exception:
            pass
        
        return None
    
    async def set_metadata(self, url: str, metadata: dict, ttl: int = CACHE_TTL_CONTENT):
        """Cache page metadata."""
        if not self.redis:
            return
        
        try:
            cache_key = self._make_cache_key("metadata", url)
            await self.redis.setex(cache_key, ttl, json.dumps(metadata, default=str))
        except Exception:
            pass
    
    async def get_score(self, url: str) -> Optional[float]:
        """Get cached page value score."""
        if not self.redis:
            return None
        
        try:
            cache_key = self._make_cache_key("score", url)
            result = await self.redis.get(cache_key)
            if result:
                return float(result)
        except Exception:
            pass
        
        return None
    
    async def set_score(self, url: str, score: float, ttl: int = CACHE_TTL_TRACKER):
        """Cache page value score."""
        if not self.redis:
            return
        
        try:
            cache_key = self._make_cache_key("score", url)
            await self.redis.setex(cache_key, ttl, json.dumps(score))
        except Exception:
            pass
    
    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get cached crawl session."""
        if not self.redis:
            return None
        
        try:
            cache_key = f"session:{session_id}"
            result = await self.redis.get(cache_key)
            if result:
                return json.loads(result)
        except Exception:
            pass
        
        return None
    
    async def set_session(self, session_id: str, session_data: dict, ttl: int = 3600):
        """Cache crawl session."""
        if not self.redis:
            return
        
        try:
            cache_key = f"session:{session_id}"
            await self.redis.setex(cache_key, ttl, json.dumps(session_data, default=str))
        except Exception:
            pass
    
    async def get_job(self, job_id: str) -> Optional[dict]:
        """Get cached crawl job."""
        if not self.redis:
            return None
        
        try:
            cache_key = f"job:{job_id}"
            result = await self.redis.get(cache_key)
            if result:
                return json.loads(result)
        except Exception:
            pass
        
        return None
    
    async def set_job(self, job_id: str, job_data: dict, ttl: int = 3600):
        """Cache crawl job."""
        if not self.redis:
            return
        
        try:
            cache_key = f"job:{job_id}"
            await self.redis.setex(cache_key, ttl, json.dumps(job_data, default=str))
        except Exception:
            pass
    
    async def invalidate_domain(self, domain: str) -> int:
        """Invalidate all cache for a domain."""
        if not self.redis:
            return 0
        
        count = 0
        for pattern in [f"*:{domain}:*", f"session:*", f"job:*"]:
            count += await self.invalidate_pattern(pattern)
        
        return count


# Global crawler cache instance
crawl_cache: Optional[CacheManager] = None


async def init_crawl_cache() -> CacheManager:
    """Initialize global crawler cache instance."""
    global crawl_cache
    redis_client = await get_redis_client()
    crawl_cache = CacheManager(redis_client)
    return crawl_cache
