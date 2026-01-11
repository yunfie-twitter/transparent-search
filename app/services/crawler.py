"""Web crawler service with Redis caching integration."""
import logging
import uuid
import httpx
from typing import Optional, List, Dict, Any, Set
from datetime import datetime
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.database import get_db_session
from app.core.cache import get_redis_client, CacheManager
from app.db.models import (
    CrawlSession, CrawlJob, CrawlMetadata, PageAnalysis
)
from app.utils.metadata_analyzer import metadata_analyzer
from app.utils.page_value_scorer import page_value_scorer
from app.utils.spam_detector import spam_detector
from app.utils.query_intent_analyzer import query_intent_analyzer

logger = logging.getLogger(__name__)


class LinkExtractor(HTMLParser):
    """Extract all links from HTML content."""
    
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: Set[str] = set()
    
    def handle_starttag(self, tag: str, attrs: List[tuple]):
        if tag == 'a':
            for attr, value in attrs:
                if attr == 'href' and value:
                    try:
                        # Resolve relative URLs
                        absolute_url = urljoin(self.base_url, value)
                        # Only keep HTTP(S) URLs
                        if absolute_url.startswith(('http://', 'https://')):
                            self.links.add(absolute_url)
                    except Exception:
                        pass


class CrawlerService:
    """Service for managing crawl operations with caching."""
    
    def __init__(self):
        self.cache: Optional[CacheManager] = None
        self.http_client: Optional[httpx.AsyncClient] = None
    
    async def _get_cache(self) -> Optional[CacheManager]:
        """Get or initialize cache instance."""
        if self.cache is None:
            redis_client = await get_redis_client()
            self.cache = CacheManager(redis_client)
        return self.cache
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or initialize HTTP client."""
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
        return self.http_client
    
    async def create_crawl_session(
        self,
        domain: str,
        max_depth: int = 3,
        page_limit: int = 100,
    ) -> Optional[CrawlSession]:
        """Create a new crawl session with caching and configuration.
        
        Args:
            domain: Target domain to crawl
            max_depth: Maximum crawl depth (default: 3)
            page_limit: Maximum number of pages to crawl (default: 100)
        
        Returns:
            Created CrawlSession object
        """
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        try:
            async with get_db_session() as db:
                crawl_session = CrawlSession(
                    session_id=session_id,
                    domain=domain,
                    status="pending",
                    created_at=now,
                    session_metadata={
                        "max_depth": max_depth,
                        "page_limit": page_limit,
                        "pages_crawled": 0,
                    },
                )
                db.add(crawl_session)
                await db.commit()
                await db.refresh(crawl_session)
            
            # Try to cache session, but don't fail if cache unavailable
            try:
                cache = await self._get_cache()
                if cache:
                    await cache.set_session(
                        session_id,
                        {
                            "session_id": session_id,
                            "domain": domain,
                            "status": "pending",
                            "max_depth": max_depth,
                            "page_limit": page_limit,
                            "pages_crawled": 0,
                            "created_at": now.isoformat(),
                        }
                    )
            except Exception as cache_err:
                logger.warning(f"Cache operation failed (non-critical): {cache_err}")
            
            logger.info(f"🙋 Created crawl session: {session_id} (max_depth={max_depth}, page_limit={page_limit})")
            return crawl_session
        
        except Exception as e:
            logger.error(f"❌ Failed to create crawl session: {e}")
            raise
    
    async def create_crawl_job(
        self,
        session_id: str,
        domain: str,
        url: str,
        depth: int = 0,
        max_depth: int = 3,
        enable_js_rendering: bool = False,
    ) -> Optional[CrawlJob]:
        """Create a crawl job with score calculation and caching."""
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        try:
            # Try to get cached metadata and score, but don't fail if cache unavailable
            page_value_score = 50.0
            try:
                cache = await self._get_cache()
                if cache:
                    cached_metadata = await cache.get_metadata(url)
                    if cached_metadata:
                        logger.info(f"✅ Using cached metadata for {url}")
                    
                    cached_score = await cache.get_score(url)
                    if cached_score:
                        page_value_score = cached_score
            except Exception as cache_err:
                logger.warning(f"Cache read failed (non-critical): {cache_err}")
            
            async with get_db_session() as db:
                crawl_job = CrawlJob(
                    job_id=job_id,
                    session_id=session_id,
                    domain=domain,
                    url=url,
                    status="pending",
                    priority=int(100 - page_value_score),
                    depth=depth,
                    max_depth=max_depth,
                    page_value_score=page_value_score,
                    enable_js_rendering=enable_js_rendering,
                    created_at=now,
                )
                db.add(crawl_job)
                await db.commit()
                await db.refresh(crawl_job)
            
            # Try to cache job, but don't fail if cache unavailable
            try:
                cache = await self._get_cache()
                if cache:
                    await cache.set_job(
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
            except Exception as cache_err:
                logger.warning(f"Cache operation failed (non-critical): {cache_err}")
            
            logger.info(f"🙋 Created crawl job: {job_id} (score: {page_value_score:.1f})")
            return crawl_job
        
        except Exception as e:
            logger.error(f"❌ Failed to create crawl job: {e}")
            raise
    
    async def execute_crawl_job(
        self,
        job_id: str,
        session_id: str,
        domain: str,
        url: str,
        depth: int = 0,
        max_depth: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Execute actual crawling: fetch page, extract links, store results."""
        try:
            # Update job status to running
            await self.update_crawl_job_status(job_id, "processing")
            
            # Fetch the page
            client = await self._get_http_client()
            logger.info(f"🌐 Fetching: {url}")
            
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            
            html_content = response.text
            
            # Analyze the page
            analysis = await self.analyze_page(job_id, url, html_content)
            
            if not analysis:
                logger.warning(f"⚠️ Failed to analyze {url}")
                await self.update_crawl_job_status(job_id, "failed")
                return None
            
            # Extract links for next crawl depth
            crawled_urls = set()
            extracted_links = []
            
            if depth < max_depth:
                try:
                    extractor = LinkExtractor(url)
                    extractor.feed(html_content)
                    
                    # Filter links to stay within domain
                    domain_netloc = urlparse(f"https://{domain}").netloc
                    
                    for link in list(extractor.links)[:20]:  # Limit to 20 links per page
                        link_netloc = urlparse(link).netloc
                        if link_netloc == domain_netloc or domain_netloc in link_netloc:
                            extracted_links.append({
                                "url": link,
                                "depth": depth + 1,
                            })
                            crawled_urls.add(link)
                    
                    logger.info(f"🔗 Extracted {len(extracted_links)} internal links from {url}")
                
                except Exception as e:
                    logger.warning(f"Link extraction failed for {url}: {e}")
            
            # Store extracted links as metadata
            async with get_db_session() as db:
                stmt = select(CrawlJob).where(CrawlJob.job_id == job_id)
                result = await db.execute(stmt)
                job = result.scalar_one_or_none()
                
                if job:
                    job.status = "completed"
                    job.completed_at = datetime.utcnow()
                    job.urls_to_crawl = extracted_links
                    job.metadata_json = {
                        "links_extracted": len(extracted_links),
                        "analysis_id": analysis.analysis_id if analysis else None,
                    }
                    await db.commit()
            
            logger.info(f"✅ Completed crawl for {url} (analysis_id: {analysis.analysis_id})")
            
            return {
                "job_id": job_id,
                "url": url,
                "status": "completed",
                "links_extracted": len(extracted_links),
                "analysis_id": analysis.analysis_id if analysis else None,
                "urls_to_crawl": extracted_links,
            }
        
        except httpx.HTTPError as e:
            logger.error(f"❌ HTTP error fetching {url}: {e}")
            await self.update_crawl_job_status(job_id, "failed")
            return None
        except Exception as e:
            logger.error(f"❌ Error executing crawl job {job_id}: {e}")
            await self.update_crawl_job_status(job_id, "failed")
            return None
    
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
            
            # Cache metadata (non-critical)
            try:
                cache = await self._get_cache()
                if cache:
                    await cache.set_metadata(url, metadata)
            except Exception as cache_err:
                logger.warning(f"Cache write failed (non-critical): {cache_err}")
            
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
            
            # Cache score (non-critical)
            try:
                cache = await self._get_cache()
                if cache:
                    await cache.set_score(url, score.get("total_score", 50.0))
            except Exception as cache_err:
                logger.warning(f"Cache write failed (non-critical): {cache_err}")
            
            # Detect spam
            spam_report = spam_detector.analyze_page(
                url=url,
                metadata=metadata,
                html_content=html_content,
            )
            
            # Analyze query intent
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
                    relevance_score=0.0,
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
            
            # Update cache (non-critical)
            try:
                cache = await self._get_cache()
                if cache:
                    await cache.set_job(
                        job_id,
                        {
                            "job_id": job_id,
                            "status": status,
                            "updated_at": datetime.utcnow().isoformat(),
                        }
                    )
            except Exception as cache_err:
                logger.warning(f"Cache update failed (non-critical): {cache_err}")
            
            logger.info(f"🔄 Updated job {job_id} status to {status}")
            return job
        
        except Exception as e:
            logger.error(f"❌ Job update failed: {e}")
            return None
    
    async def invalidate_domain_cache(self, domain: str):
        """Invalidate all caches for a domain."""
        try:
            cache = await self._get_cache()
            if cache:
                await cache.invalidate_domain(domain)
        except Exception as e:
            logger.warning(f"Cache invalidation failed (non-critical): {e}")
        
        logger.info(f"♻️ Invalidated cache for domain: {domain}")
    
    async def close(self):
        """Close HTTP client."""
        if self.http_client:
            await self.http_client.aclose()


# Global service instance
crawler_service = CrawlerService()
