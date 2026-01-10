"""Tests for Redis cache and database consistency."""
import pytest
from datetime import datetime
from app.db.cache import crawl_cache
from app.services.crawler import crawler_service
from app.db.database import get_db_session
from app.db.models import CrawlJob, CrawlSession


@pytest.mark.asyncio
class TestCacheIntegration:
    """Cache and database integration tests."""
    
    async def test_session_cache_consistency(self):
        """Test crawl session cache consistency."""
        # Create session
        session = await crawler_service.create_crawl_session(domain="test.example.com")
        
        # Verify in cache
        cached = await crawl_cache.get_session(session.session_id)
        assert cached is not None
        assert cached["session_id"] == session.session_id
        assert cached["domain"] == "test.example.com"
        assert cached["status"] == "pending"
    
    async def test_job_cache_consistency(self):
        """Test crawl job cache consistency."""
        # Create session first
        session = await crawler_service.create_crawl_session(domain="test.example.com")
        
        # Create job
        job = await crawler_service.create_crawl_job(
            session_id=session.session_id,
            domain="test.example.com",
            url="https://test.example.com/article",
            depth=1,
            max_depth=3,
        )
        
        # Verify in cache
        cached = await crawl_cache.get_job(job.job_id)
        assert cached is not None
        assert cached["job_id"] == job.job_id
        assert cached["url"] == "https://test.example.com/article"
        assert "page_value_score" in cached
    
    async def test_metadata_cache_lifecycle(self):
        """Test metadata cache lifecycle."""
        url = "https://test.example.com/page"
        metadata = {
            "title": "Test Page",
            "description": "Test description",
            "og_title": "OG Title",
            "word_count": 1500,
        }
        
        # Set metadata
        await crawl_cache.set_metadata(url, metadata)
        
        # Retrieve
        cached = await crawl_cache.get_metadata(url)
        assert cached == metadata
        
        # Verify structure
        assert cached["word_count"] == 1500
    
    async def test_score_cache_storage(self):
        """Test page value score caching."""
        url = "https://test.example.com/article"
        score = 82.5
        
        # Store score
        await crawl_cache.set_score(url, score)
        
        # Retrieve
        cached = await crawl_cache.get_score(url)
        assert cached == score
    
    async def test_domain_job_grouping(self):
        """Test domain-based job grouping cache."""
        domain = "test.example.com"
        job_ids = ["job1", "job2", "job3"]
        
        # Store grouped jobs
        await crawl_cache.set_jobs_by_domain(domain, job_ids)
        
        # Retrieve
        cached = await crawl_cache.get_jobs_by_domain(domain)
        assert cached == job_ids
        assert len(cached) == 3
    
    async def test_cache_invalidation(self):
        """Test domain cache invalidation."""
        domain = "test.example.com"
        job_ids = ["job1", "job2"]
        
        # Store data
        await crawl_cache.set_jobs_by_domain(domain, job_ids)
        assert await crawl_cache.get_jobs_by_domain(domain) is not None
        
        # Invalidate
        await crawl_cache.invalidate_domain(domain)
        
        # Verify cleared
        assert await crawl_cache.get_jobs_by_domain(domain) is None
    
    async def test_cache_miss_fallback(self):
        """Test fallback behavior on cache miss."""
        url = "https://nonexistent.example.com"
        
        # Try to retrieve non-existent
        cached = await crawl_cache.get_metadata(url)
        assert cached is None
        
        # Try to retrieve non-existent score
        score = await crawl_cache.get_score(url)
        assert score is None
    
    async def test_job_status_update_consistency(self):
        """Test job status update consistency across cache and DB."""
        # Create session and job
        session = await crawler_service.create_crawl_session(domain="test.example.com")
        job = await crawler_service.create_crawl_job(
            session_id=session.session_id,
            domain="test.example.com",
            url="https://test.example.com/page",
        )
        
        # Update status
        updated_job = await crawler_service.update_crawl_job_status(
            job_id=job.job_id,
            status="processing",
        )
        
        # Verify DB
        assert updated_job.status == "processing"
        assert updated_job.started_at is not None
        
        # Verify cache
        cached = await crawl_cache.get_job(job.job_id)
        assert cached["status"] == "processing"
    
    async def test_concurrent_cache_access(self):
        """Test concurrent cache access patterns."""
        import asyncio
        
        async def create_and_cache(job_num: int):
            session = await crawler_service.create_crawl_session(
                domain=f"test{job_num}.example.com"
            )
            job = await crawler_service.create_crawl_job(
                session_id=session.session_id,
                domain=f"test{job_num}.example.com",
                url=f"https://test{job_num}.example.com/page",
            )
            return job
        
        # Create multiple jobs concurrently
        jobs = await asyncio.gather(
            create_and_cache(1),
            create_and_cache(2),
            create_and_cache(3),
        )
        
        # Verify all cached
        for job in jobs:
            cached = await crawl_cache.get_job(job.job_id)
            assert cached is not None
            assert cached["job_id"] == job.job_id
    
    async def test_cache_ttl_variation(self):
        """Test different TTL values for different cache types."""
        url = "https://test.example.com/page"
        
        # Job cache: 1 hour (3600s)
        job_data = {"job_id": "job1", "status": "pending"}
        await crawl_cache.set_job("job1", job_data, ttl=3600)
        assert await crawl_cache.get_job("job1") is not None
        
        # Metadata cache: 24 hours (86400s)
        metadata = {"title": "Test", "description": "Desc"}
        await crawl_cache.set_metadata(url, metadata, ttl=86400)
        assert await crawl_cache.get_metadata(url) is not None
        
        # Score cache: 24 hours
        await crawl_cache.set_score(url, 82.5, ttl=86400)
        assert await crawl_cache.get_score(url) is not None


@pytest.mark.asyncio
class TestCacheDatabaseConsistency:
    """Test consistency between cache and database."""
    
    async def test_create_session_both_stores(self):
        """Test session is saved to both DB and cache."""
        session = await crawler_service.create_crawl_session(
            domain="consistency.test.com"
        )
        
        # Check database
        async with get_db_session() as db:
            from sqlalchemy import select
            stmt = select(CrawlSession).where(
                CrawlSession.session_id == session.session_id
            )
            result = await db.execute(stmt)
            db_session = result.scalar_one_or_none()
            assert db_session is not None
            assert db_session.domain == "consistency.test.com"
        
        # Check cache
        cached = await crawl_cache.get_session(session.session_id)
        assert cached is not None
        assert cached["domain"] == "consistency.test.com"
    
    async def test_create_job_score_calculation_consistent(self):
        """Test job score is calculated and cached consistently."""
        session = await crawler_service.create_crawl_session(
            domain="score.test.com"
        )
        job = await crawler_service.create_crawl_job(
            session_id=session.session_id,
            domain="score.test.com",
            url="https://score.test.com/article",
            depth=1,
            max_depth=3,
        )
        
        # Check database score
        async with get_db_session() as db:
            from sqlalchemy import select
            stmt = select(CrawlJob).where(CrawlJob.job_id == job.job_id)
            result = await db.execute(stmt)
            db_job = result.scalar_one_or_none()
            assert db_job.page_value_score > 0
            db_score = db_job.page_value_score
        
        # Check cache score
        cached = await crawl_cache.get_job(job.job_id)
        assert cached["page_value_score"] == db_score
    
    async def test_domain_cache_isolation(self):
        """Test domain caches are properly isolated."""
        # Create sessions for different domains
        session1 = await crawler_service.create_crawl_session(
            domain="domain1.test.com"
        )
        session2 = await crawler_service.create_crawl_session(
            domain="domain2.test.com"
        )
        
        # Set domain-specific job lists
        await crawl_cache.set_jobs_by_domain(
            "domain1.test.com", ["job1", "job2"]
        )
        await crawl_cache.set_jobs_by_domain(
            "domain2.test.com", ["job3", "job4", "job5"]
        )
        
        # Verify isolation
        jobs1 = await crawl_cache.get_jobs_by_domain("domain1.test.com")
        jobs2 = await crawl_cache.get_jobs_by_domain("domain2.test.com")
        
        assert jobs1 == ["job1", "job2"]
        assert jobs2 == ["job3", "job4", "job5"]
        assert len(jobs1) != len(jobs2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
