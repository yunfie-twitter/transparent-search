"""Web crawler service with Redis caching integration."""
import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.db.database import get_db_session
from app.db.cache import crawl_cache
from app.db.models import (
    CrawlSession, CrawlJob, CrawlMetadata, PageAnalysis
)
from app.utils.metadata_analyzer import metadata_analyzer
from app.utils.page_value_scorer import page_value_scorer
from app.utils.spam_detector import spam_detector
from app.utils.query_intent_analyzer import query_intent_analyzer

logger = logging.getLogger(__name__)


class CrawlerService:
    """Service for managing crawl operations with caching."""
    
    async def create_crawl_session(self, domain: str) -> CrawlSession:
        """Create a new crawl session with caching."""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        async with get_db_session() as db:
            crawl_session = CrawlSession(
                session_id=session_id,
                domain=domain,
                status="pending",
                created_at=now,
            )
            db.add(crawl_session)
            await db.commit()
            await db.refresh(crawl_session)
        
        # Cache session
        await crawl_cache.set_session(
            session_id,
            {
                "session_id": session_id,
                "domain": domain,
                "status": "pending",
                "created_at": now.isoformat(),
            }
        )
        
        logger.info(f"🙋 Created crawl session: {session_id}")
        return crawl_session
    
    async def create_crawl_job(
        self,
        session_id: str,
        domain: str,
        url: str,
        depth: int = 0,
        max_depth: int = 3,
        enable_js_rendering: bool = False,
    ) -> CrawlJob:
        """Create a crawl job with score calculation and caching."""
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        # Try to get cached metadata first
        cached_metadata = await crawl_cache.get_metadata(url)
        if cached_metadata:
            logger.info(f"✅ Using cached metadata for {url}")
        else:
            # If not cached, we'll extract during crawl
            cached_metadata = None
        
        # Try to get cached score
        cached_score = await crawl_cache.get_score(url)
        page_value_score = cached_score or 50.0  # Default score
        
        async with get_db_session() as db:
            crawl_job = CrawlJob(
                job_id=job_id,
                session_id=session_id,
                domain=domain,
                url=url,
                status="pending",
                priority=int(100 - page_value_score),  # Higher score = lower priority number
                depth=depth,
                max_depth=max_depth,
                page_value_score=page_value_score,
                enable_js_rendering=enable_js_rendering,
                created_at=now,
            )
            db.add(crawl_job)
            await db.commit()
            await db.refresh(crawl_job)
        
        # Cache job
        await crawl_cache.set_job(
            job_id,
            {
                "job_id": job_id,
                "session_id": session_id,
                "domain": domain,
                "url": url,
                "status": "pending",
                "priority": int(100 - page_value_score),
                "page_value_score": page_value_score,
                "created_at": now.isoformat(),
            }
        )
        
        logger.info(f"🙋 Created crawl job: {job_id} (score: {page_value_score:.1f})")
        return crawl_job
    
    async def analyze_page(
        self,
        job_id: str,
        url: str,
        html_content: str,
    ) -> Optional[PageAnalysis]:
        """Analyze page with metadata extraction, scoring, and caching."""
        try:
            analysis_id = str(uuid.uuid4())
            now = datetime.utcnow()
            
            # Extract metadata
            metadata = metadata_analyzer.extract_metadata(html_content, url)
            
            # Cache metadata
            await crawl_cache.set_metadata(url, metadata)
            
            # Calculate page value score
            score = page_value_scorer.score_page(
                url=url,
                content_metrics={
                    "has_structured_data": bool(metadata.get("structured_data")),
                    "is_article": metadata.get("page_type") == "article",
                    "has_publish_date": bool(metadata.get("publish_date")),
                    "has_author": bool(metadata.get("author")),
                    "has_og_tags": bool(metadata.get("og_title")),
                    "word_count": metadata.get("word_count", 0),
                    "headings_count": metadata.get("headings_count", 0),
                    "has_meta_description": bool(metadata.get("description")),
                },
            )
            
            # Cache score
            await crawl_cache.set_score(url, score.get("total_score", 50.0))
            
            # Detect spam
            spam_report = spam_detector.analyze_page(
                url=url,
                metadata=metadata,
                html_content=html_content,
            )
            
            # Analyze query intent
            # Note: This would need a query context in real scenario
            intent = query_intent_analyzer.analyze_query(
                metadata.get("title", "")
            )
            
            # Store analysis
            async with get_db_session() as db:
                analysis = PageAnalysis(
                    analysis_id=analysis_id,
                    job_id=job_id,
                    url=url,
                    total_score=score.get("total_score", 50.0),
                    crawl_priority=score.get("crawl_priority", 5),
                    recommendation=score.get("recommendation", "CRAWL_LATER"),
                    spam_score=spam_report.get("spam_score", 0.0),
                    risk_level=spam_report.get("risk_level", "clean"),
                    query_intent=intent.get("primary_intent"),
                    relevance_score=0.0,  # Would need query context
                    analyzed_at=now,
                )
                db.add(analysis)
                await db.commit()
                await db.refresh(analysis)
            
            logger.info(f"📁 Analyzed page {url} (score: {score.get('total_score', 50.0):.1f})")
            return analysis
        
        except Exception as e:
            logger.error(f"❌ Page analysis failed for {url}: {e}")
            return None
    
    async def update_crawl_job_status(
        self,
        job_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[CrawlJob]:
        """Update job status and clear cache if needed."""
        try:
            async with get_db_session() as db:
                stmt = select(CrawlJob).where(CrawlJob.job_id == job_id)
                result = await db.execute(stmt)
                job = result.scalar_one_or_none()
                
                if not job:
                    return None
                
                # Update job
                job.status = status
                if status == "completed":
                    job.completed_at = datetime.utcnow()
                elif status == "processing":
                    job.started_at = datetime.utcnow()
                
                if metadata:
                    job.metadata_json = metadata
                
                await db.commit()
                await db.refresh(job)
            
            # Update cache
            await crawl_cache.set_job(
                job_id,
                {
                    "job_id": job_id,
                    "status": status,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            
            logger.info(f"🔄 Updated job {job_id} status to {status}")
            return job
        
        except Exception as e:
            logger.error(f"❌ Job update failed: {e}")
            return None
    
    async def invalidate_domain_cache(self, domain: str):
        """Invalidate all caches for a domain."""
        await crawl_cache.invalidate_domain(domain)
        logger.info(f"♻️ Invalidated cache for domain: {domain}")


# Global service instance
crawler_service = CrawlerService()
