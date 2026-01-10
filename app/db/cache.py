"""Redis caching layer for crawl operations."""
import json
import logging
from typing import Any, Optional, Dict, List
from datetime import timedelta
from redis.asyncio import Redis
import os

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = 3600  # 1 hour default


class CrawlCache:
    """Redis-backed cache for crawl operations."""
    
    def __init__(self):
        self.redis: Optional[Redis] = None
        self.prefix = "crawl:"
    
    async def connect(self):
        """Connect to Redis."""
        try:
            self.redis = await Redis.from_url(REDIS_URL, decode_responses=True)
            await self.redis.ping()
            logger.info("✅ Connected to Redis cache")
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed: {e}")
            self.redis = None
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            logger.info("🛑 Redis connection closed")
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get cached crawl job."""
        if not self.redis:
            return None
        
        try:
            key = f"{self.prefix}job:{job_id}"
            data = await self.redis.get(key)
            if data:
                logger.debug(f"✅ Cache hit: {key}")
                return json.loads(data)
            logger.debug(f"❌ Cache miss: {key}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ Cache get failed: {e}")
            return None
    
    async def set_job(self, job_id: str, data: Dict[str, Any], ttl: int = CACHE_TTL):
        """Cache crawl job data."""
        if not self.redis:
            return
        
        try:
            key = f"{self.prefix}job:{job_id}"
            await self.redis.setex(
                key,
                ttl,
                json.dumps(data, default=str)  # default=str for datetime
            )
            logger.debug(f"💾 Cached: {key}")
        except Exception as e:
            logger.warning(f"⚠️ Cache set failed: {e}")
    
    async def delete_job(self, job_id: str):
        """Delete cached crawl job."""
        if not self.redis:
            return
        
        try:
            key = f"{self.prefix}job:{job_id}"
            await self.redis.delete(key)
            logger.debug(f"🗑️ Cache deleted: {key}")
        except Exception as e:
            logger.warning(f"⚠️ Cache delete failed: {e}")
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get cached crawl session."""
        if not self.redis:
            return None
        
        try:
            key = f"{self.prefix}session:{session_id}"
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"⚠️ Cache get failed: {e}")
            return None
    
    async def set_session(self, session_id: str, data: Dict[str, Any], ttl: int = CACHE_TTL):
        """Cache crawl session data."""
        if not self.redis:
            return
        
        try:
            key = f"{self.prefix}session:{session_id}"
            await self.redis.setex(
                key,
                ttl,
                json.dumps(data, default=str)
            )
        except Exception as e:
            logger.warning(f"⚠️ Cache set failed: {e}")
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Get cached page metadata."""
        if not self.redis:
            return None
        
        try:
            key = f"{self.prefix}metadata:{url}"
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"⚠️ Cache get failed: {e}")
            return None
    
    async def set_metadata(self, url: str, data: Dict[str, Any], ttl: int = CACHE_TTL * 24):  # 24 hours
        """Cache page metadata (longer TTL)."""
        if not self.redis:
            return
        
        try:
            key = f"{self.prefix}metadata:{url}"
            await self.redis.setex(
                key,
                ttl,
                json.dumps(data, default=str)
            )
        except Exception as e:
            logger.warning(f"⚠️ Cache set failed: {e}")
    
    async def get_score(self, url: str) -> Optional[float]:
        """Get cached page value score."""
        if not self.redis:
            return None
        
        try:
            key = f"{self.prefix}score:{url}"
            data = await self.redis.get(key)
            if data:
                return float(data)
            return None
        except Exception as e:
            logger.warning(f"⚠️ Cache get failed: {e}")
            return None
    
    async def set_score(self, url: str, score: float, ttl: int = CACHE_TTL * 24):
        """Cache page value score."""
        if not self.redis:
            return
        
        try:
            key = f"{self.prefix}score:{url}"
            await self.redis.setex(key, ttl, str(score))
        except Exception as e:
            logger.warning(f"⚠️ Cache set failed: {e}")
    
    async def get_jobs_by_domain(self, domain: str) -> Optional[List[str]]:
        """Get cached job IDs for a domain."""
        if not self.redis:
            return None
        
        try:
            key = f"{self.prefix}domain:{domain}:jobs"
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"⚠️ Cache get failed: {e}")
            return None
    
    async def set_jobs_by_domain(self, domain: str, job_ids: List[str], ttl: int = CACHE_TTL):
        """Cache job IDs for a domain."""
        if not self.redis:
            return
        
        try:
            key = f"{self.prefix}domain:{domain}:jobs"
            await self.redis.setex(
                key,
                ttl,
                json.dumps(job_ids)
            )
        except Exception as e:
            logger.warning(f"⚠️ Cache set failed: {e}")
    
    async def invalidate_domain(self, domain: str):
        """Invalidate all caches for a domain."""
        if not self.redis:
            return
        
        try:
            pattern = f"{self.prefix}domain:{domain}:*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern)
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break
            logger.info(f"♻️ Invalidated cache for domain: {domain}")
        except Exception as e:
            logger.warning(f"⚠️ Cache invalidation failed: {e}")
    
    async def clear_all(self):
        """Clear all cache entries."""
        if not self.redis:
            return
        
        try:
            pattern = f"{self.prefix}*"
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern)
                if keys:
                    deleted += await self.redis.delete(*keys)
                if cursor == 0:
                    break
            logger.info(f"🗑️ Cleared {deleted} cache entries")
        except Exception as e:
            logger.warning(f"⚠️ Cache clear failed: {e}")


# Global cache instance
crawl_cache = CrawlCache()
