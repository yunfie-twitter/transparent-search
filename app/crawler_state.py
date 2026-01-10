"""Crawler state management for tracking and cancellation."""
import os
from typing import Optional, Dict, Any
import redis.asyncio as redis
import json
from datetime import datetime, timedelta

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

class CrawlerState:
    """Manages crawler state in Redis for cancellation and progress tracking."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        self.prefix = "crawler:"
    
    async def get_redis(self) -> Optional[redis.Redis]:
        """Get or create Redis client."""
        if self.redis:
            return self.redis
        try:
            self.redis = await redis.from_url(REDIS_URL)
            return self.redis
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e}")
            return None
    
    async def start_crawl(self, crawl_id: str, domain: str) -> bool:
        """Mark crawl as started."""
        try:
            redis_client = await self.get_redis()
            if not redis_client:
                return False
            
            state = {
                "crawl_id": crawl_id,
                "domain": domain,
                "status": "running",
                "started_at": datetime.now().isoformat(),
                "pages_crawled": 0,
                "pages_failed": 0,
                "pages_skipped": 0,
                "current_url": None,
                "cancelled": False,
            }
            
            await redis_client.setex(
                f"{self.prefix}{crawl_id}",
                3600,  # 1 hour expiry
                json.dumps(state)
            )
            return True
        except Exception as e:
            print(f"⚠️ Start crawl state error: {e}")
            return False
    
    async def is_cancelled(self, crawl_id: str) -> bool:
        """Check if crawl should be cancelled."""
        try:
            redis_client = await self.get_redis()
            if not redis_client:
                return False
            
            data = await redis_client.get(f"{self.prefix}{crawl_id}")
            if not data:
                return False
            
            state = json.loads(data)
            return state.get("cancelled", False)
        except Exception as e:
            print(f"⚠️ Check cancelled error: {e}")
            return False
    
    async def cancel_crawl(self, crawl_id: str) -> bool:
        """Cancel a crawl by setting cancelled flag."""
        try:
            redis_client = await self.get_redis()
            if not redis_client:
                return False
            
            data = await redis_client.get(f"{self.prefix}{crawl_id}")
            if not data:
                return False
            
            state = json.loads(data)
            state["cancelled"] = True
            state["cancelled_at"] = datetime.now().isoformat()
            state["status"] = "cancelled"
            
            await redis_client.setex(
                f"{self.prefix}{crawl_id}",
                3600,
                json.dumps(state)
            )
            return True
        except Exception as e:
            print(f"⚠️ Cancel crawl error: {e}")
            return False
    
    async def update_progress(
        self,
        crawl_id: str,
        pages_crawled: int = 0,
        pages_failed: int = 0,
        pages_skipped: int = 0,
        current_url: Optional[str] = None,
    ) -> bool:
        """Update crawl progress."""
        try:
            redis_client = await self.get_redis()
            if not redis_client:
                return False
            
            data = await redis_client.get(f"{self.prefix}{crawl_id}")
            if not data:
                return False
            
            state = json.loads(data)
            state["pages_crawled"] = pages_crawled
            state["pages_failed"] = pages_failed
            state["pages_skipped"] = pages_skipped
            if current_url:
                state["current_url"] = current_url
            state["last_updated"] = datetime.now().isoformat()
            
            await redis_client.setex(
                f"{self.prefix}{crawl_id}",
                3600,
                json.dumps(state)
            )
            return True
        except Exception as e:
            print(f"⚠️ Update progress error: {e}")
            return False
    
    async def get_state(self, crawl_id: str) -> Optional[Dict[str, Any]]:
        """Get current crawl state."""
        try:
            redis_client = await self.get_redis()
            if not redis_client:
                return None
            
            data = await redis_client.get(f"{self.prefix}{crawl_id}")
            if not data:
                return None
            
            return json.loads(data)
        except Exception as e:
            print(f"⚠️ Get state error: {e}")
            return None
    
    async def end_crawl(self, crawl_id: str, status: str = "completed") -> bool:
        """Mark crawl as ended."""
        try:
            redis_client = await self.get_redis()
            if not redis_client:
                return False
            
            data = await redis_client.get(f"{self.prefix}{crawl_id}")
            if not data:
                return False
            
            state = json.loads(data)
            state["status"] = status
            state["ended_at"] = datetime.now().isoformat()
            
            await redis_client.setex(
                f"{self.prefix}{crawl_id}",
                3600,
                json.dumps(state)
            )
            return True
        except Exception as e:
            print(f"⚠️ End crawl error: {e}")
            return False
    
    async def cleanup(self, crawl_id: str) -> bool:
        """Delete crawl state."""
        try:
            redis_client = await self.get_redis()
            if not redis_client:
                return False
            
            await redis_client.delete(f"{self.prefix}{crawl_id}")
            return True
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")
            return False

# Global instance
crawler_state = CrawlerState()
