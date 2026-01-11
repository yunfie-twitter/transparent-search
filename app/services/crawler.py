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
from app.utils.page_value_scorer import page_value_scorer, LinkMetrics, ContentMetrics
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
            try:
                redis_client = await get_redis_client()
                self.cache = CacheManager(redis_client)
            except Exception as e:
                logger.warning(f"Cache initialization failed: {e}")
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
        """Create a new crawl session with caching and configuration."""
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
            
            # Try to cache session
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
            logger.error(f"❌ Failed to create crawl session: {e}", exc_info=True)
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
            page_value_score = 50.0
            try:
                cache = await self._get_cache()
                if cache:
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
            
            logger.info(f"📋 [{session_id[:8]}] Queued: {url} (depth={depth}, score={page_value_score:.1f})")
            return crawl_job
        
        except Exception as e:
            logger.error(f"❌ Failed to create crawl job: {e}", exc_info=True)
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
        job_key = job_id[:8]
        logger.info(f"🔄 [{job_key}] Starting execution for {url}")
        
        try:
            # Fetch the page
            client = await self._get_http_client()
            logger.info(f"🌐 [{job_key}] Fetching: {url}")
            
            try:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
            except httpx.HTTPError as http_err:
                logger.error(f"❌ [{job_key}] HTTP error: {http_err}")
                await self.update_crawl_job_status(job_id, "failed")
                return None
            
            html_content = response.text
            logger.debug(f"[{job_key}] Fetched {len(html_content)} bytes")
            
            # Analyze the page
            logger.debug(f"[{job_key}] Analyzing page content")
            analysis = await self.analyze_page(job_id, url, html_content)
            
            if not analysis:
                logger.warning(f"⚠️ [{job_key}] Failed to analyze {url}")
                await self.update_crawl_job_status(job_id, "failed")
                return None
            
            # Extract links for next crawl depth
            extracted_links = []
            
            if depth < max_depth:
                try:
                    logger.info(f"🔍 [{job_key}] Extracting links from {url}")
                    extractor = LinkExtractor(url)
                    extractor.feed(html_content)
                    
                    logger.debug(f"[{job_key}] Found {len(extractor.links)} total links")
                    
                    # Filter links to stay within domain
                    domain_netloc = urlparse(f"https://{domain}").netloc
                    
                    filtered_links = []
                    for link in list(extractor.links)[:20]:  # Limit to 20 links per page
                        link_netloc = urlparse(link).netloc
                        if link_netloc == domain_netloc or domain_netloc in link_netloc:
                            filtered_links.append(link)
                    
                    logger.info(f"✅ [{job_key}] Filtered to {len(filtered_links)} internal links")
                    
                    # Create pending jobs for each extracted link
                    logger.info(f"📬 [{job_key}] Adding {len(filtered_links)} URLs to pending queue...")
                    for idx, link in enumerate(filtered_links, 1):
                        try:
                            # Create job for extracted link
                            new_job = await self.create_crawl_job(
                                session_id=session_id,
                                domain=domain,
                                url=link,
                                depth=depth + 1,
                                max_depth=max_depth,
                                enable_js_rendering=False,
                            )
                            if new_job:
                                extracted_links.append({
                                    "url": link,
                                    "depth": depth + 1,
                                    "job_id": new_job.job_id,
                                })
                        except Exception as e:
                            logger.warning(f"[{job_key}] Failed to queue {link}: {e}")
                    
                    logger.info(f"✨ [{job_key}] Pending queue updated: {len(extracted_links)} new jobs created")
                
                except Exception as e:
                    logger.warning(f"[{job_key}] Link extraction failed: {e}")
            else:
                logger.info(f"🛑 [{job_key}] Max depth ({max_depth}) reached, no more links will be extracted")
            
            # Update job status to completed with extracted links
            logger.debug(f"[{job_key}] Updating job with completion status")
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
                    logger.debug(f"[{job_key}] Job marked as completed in DB")
                else:
                    logger.error(f"[{job_key}] Job not found in database!")
            
            logger.info(f"🎉 [{job_key}] Completed: {url}")
            
            return {
                "job_id": job_id,
                "url": url,
                "status": "completed",
                "links_extracted": len(extracted_links),
                "analysis_id": analysis.analysis_id if analysis else None,
                "urls_to_crawl": extracted_links,
            }
        
        except Exception as e:
            logger.error(f"❌ [{job_key}] Error executing crawl job: {e}", exc_info=True)
            try:
                await self.update_crawl_job_status(job_id, "failed")
            except Exception as update_err:
                logger.error(f"[{job_key}] Failed to update status to failed: {update_err}")
            return None
    
    async def analyze_page(
        self,
        job_id: str,
        url: str,
        html_content: str,
    ) -> Optional[PageAnalysis]:
        """Analyze page with metadata extraction, scoring, and caching."""
        job_key = job_id[:8]
        try:
            analysis_id = str(uuid.uuid4())
            now = datetime.utcnow()
            
            logger.debug(f"[{job_key}] Extracting metadata from page")
            metadata = metadata_analyzer.extract_metadata(html_content, url)
            
            try:
                cache = await self._get_cache()
                if cache:
                    await cache.set_metadata(url, metadata)
            except Exception as cache_err:
                logger.warning(f"Cache write failed (non-critical): {cache_err}")
            
            logger.debug(f"[{job_key}] Calculating page value score")
            
            # Create LinkMetrics for scoring (simplified - would enhance in production)
            link_metrics = LinkMetrics(
                depth_from_root=0,
                internal_link_count=0,
                external_backlink_estimate=0,
                outgoing_internal_links=0,
                outgoing_external_links=0,
            )
            
            # Create ContentMetrics for scoring
            content_metrics = ContentMetrics(
                has_structured_data=bool(metadata.get("structured_data")),
                is_article=metadata.get("page_type") == "article",
                has_publish_date=bool(metadata.get("publish_date")),
                has_author=bool(metadata.get("author")),
                has_og_tags=bool(metadata.get("og_title")),
                word_count=metadata.get("word_count", 0),
                headings_count=metadata.get("headings_count", 0),
                has_meta_description=bool(metadata.get("description")),
            )
            
            # Calculate score with proper arguments
            score = page_value_scorer.score_page(
                url=url,
                link_metrics=link_metrics,
                content_metrics=content_metrics,
            )
            
            try:
                cache = await self._get_cache()
                if cache:
                    await cache.set_score(url, score.total_score)
            except Exception as cache_err:
                logger.warning(f"Cache write failed (non-critical): {cache_err}")
            
            # ✅ Use analyze_domain instead of analyze_page
            logger.debug(f"[{job_key}] Running spam detection")
            spam_report = spam_detector.analyze_domain(
                domain=urlparse(url).netloc,
                pages_crawled=[{
                    "url": url,
                    "content": html_content,
                    "word_count": metadata.get("word_count", 0),
                    "link_count": metadata.get("link_count", 0),
                    "internal_links": 0,
                    "external_links": 0,
                }],
                link_graph={},
            )
            
            logger.debug(f"[{job_key}] Analyzing query intent")
            intent = query_intent_analyzer.analyze_query(
                metadata.get("title", "")
            )
            
            # Store analysis
            async with get_db_session() as db:
                analysis = PageAnalysis(
                    analysis_id=analysis_id,
                    job_id=job_id,
                    url=url,
                    total_score=score.total_score,
                    crawl_priority=score.crawl_priority,
                    recommendation=score.recommendation,
                    spam_score=spam_report.spam_score if spam_report else 0.0,
                    risk_level=spam_report.risk_level if spam_report else "clean",
                    query_intent=intent.get("primary_intent"),
                    relevance_score=0.0,
                    analyzed_at=now,
                )
                db.add(analysis)
                await db.commit()
                await db.refresh(analysis)
            
            logger.info(f"📊 [{job_key}] Analyzed: {url} (score: {score.total_score:.1f})")
            return analysis
        
        except Exception as e:
            logger.error(f"❌ [{job_key}] Page analysis failed: {e}", exc_info=True)
            return None
    
    async def update_crawl_job_status(
        self,
        job_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[CrawlJob]:
        """Update job status and clear cache if needed."""
        job_key = job_id[:8]
        logger.debug(f"[{job_key}] Updating status to '{status}'")
        
        try:
            async with get_db_session() as db:
                stmt = select(CrawlJob).where(CrawlJob.job_id == job_id)
                result = await db.execute(stmt)
                job = result.scalar_one_or_none()
                
                if not job:
                    logger.error(f"[{job_key}] Job not found in database!")
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
                logger.debug(f"[{job_key}] Status updated to '{status}' in database")
            
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
            
            return job
        
        except Exception as e:
            logger.error(f"❌ [{job_key}] Job update failed: {e}", exc_info=True)
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
