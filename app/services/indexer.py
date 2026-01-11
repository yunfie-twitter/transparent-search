"""Content indexer service - converts crawled content to searchable index."""
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urlparse
from html.parser import HTMLParser

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.db.models import CrawlJob, SearchContent, PageAnalysis
from app.utils.content_classifier import content_classifier

logger = logging.getLogger(__name__)


class HTMLMetadataExtractor(HTMLParser):
    """Extract metadata from HTML content."""
    
    def __init__(self):
        super().__init__()
        self.h1_tags: List[str] = []
        self.h2_tags: List[str] = []
        self.meta_description: Optional[str] = None
        self.og_title: Optional[str] = None
        self.og_description: Optional[str] = None
        self.og_image_url: Optional[str] = None
        self.current_tag: Optional[str] = None
        self.current_text: str = ""
    
    def handle_starttag(self, tag: str, attrs: List[tuple]):
        self.current_tag = tag
        
        if tag == "meta":
            attrs_dict = dict(attrs)
            if attrs_dict.get("name") == "description":
                self.meta_description = attrs_dict.get("content")
            elif attrs_dict.get("property") == "og:title":
                self.og_title = attrs_dict.get("content")
            elif attrs_dict.get("property") == "og:description":
                self.og_description = attrs_dict.get("content")
            elif attrs_dict.get("property") == "og:image":
                self.og_image_url = attrs_dict.get("content")
    
    def handle_data(self, data: str):
        if self.current_tag in ("h1", "h2"):
            self.current_text += data.strip()
    
    def handle_endtag(self, tag: str):
        if tag == "h1" and self.current_text:
            self.h1_tags.append(self.current_text.strip())
            self.current_text = ""
        elif tag == "h2" and self.current_text:
            self.h2_tags.append(self.current_text.strip())
            self.current_text = ""
        self.current_tag = None


class ContentIndexer:
    """Index crawled content for search."""
    
    async def index_crawl_job(
        self,
        job_id: str,
        session_id: str,
        domain: str,
        url: str,
    ) -> Optional[SearchContent]:
        """Index a completed crawl job into SearchContent.
        
        Args:
            job_id: CrawlJob ID
            session_id: Session ID
            domain: Domain being crawled
            url: URL that was crawled
        
        Returns:
            SearchContent record or None if indexing failed
        """
        job_key = job_id[:8]
        logger.info(f"📇 [{job_key}] Indexing: {url}")
        
        try:
            # Fetch the completed job
            async with get_db_session() as db:
                stmt = select(CrawlJob).where(CrawlJob.job_id == job_id)
                result = await db.execute(stmt)
                job = result.scalar_one_or_none()
                
                if not job or job.status != "completed":
                    logger.warning(f"[{job_key}] Job not found or not completed")
                    return None
                
                # Check if already indexed
                existing = await db.execute(
                    select(SearchContent).where(SearchContent.url == url)
                )
                if existing.scalar_one_or_none():
                    logger.debug(f"[{job_key}] Already indexed: {url}")
                    return None
                
                # Extract metadata from HTML
                html_content = job.content or ""
                extractor = HTMLMetadataExtractor()
                try:
                    extractor.feed(html_content)
                except Exception as e:
                    logger.warning(f"[{job_key}] HTML parsing warning: {e}")
                
                # Get analysis if available
                analysis_stmt = select(PageAnalysis).where(
                    PageAnalysis.url == url
                ).order_by(PageAnalysis.analyzed_at.desc()).limit(1)
                analysis_result = await db.execute(analysis_stmt)
                analysis = analysis_result.scalar_one_or_none()
                
                # Classify content
                content_type = "unknown"
                try:
                    classification = content_classifier.classify_by_url(url)
                    content_type = classification.get("type", "unknown")
                except Exception as e:
                    logger.warning(f"[{job_key}] Classification failed: {e}")
                
                # Determine quality score
                quality_score = 0.5
                if analysis:
                    quality_score = analysis.total_score / 100 if analysis.total_score else 0.5
                elif job.page_value_score:
                    quality_score = job.page_value_score / 100
                
                # Create SearchContent record
                now = datetime.utcnow()
                search_content = SearchContent(
                    url=url,
                    domain=domain,
                    title=job.title or "Untitled",
                    description=job.description or "",
                    content=html_content[:10000] if html_content else "",  # Store first 10K chars
                    content_type=content_type,
                    quality_score=quality_score,
                    h1=extractor.h1_tags[0] if extractor.h1_tags else None,
                    h2_tags=extractor.h2_tags if extractor.h2_tags else [],
                    meta_description=extractor.meta_description,
                    og_title=extractor.og_title,
                    og_description=extractor.og_description,
                    og_image_url=extractor.og_image_url,
                    indexed_at=now,
                    last_crawled_at=job.completed_at or now,
                    metadata_json={
                        "job_id": job_id,
                        "session_id": session_id,
                        "crawl_depth": job.depth,
                        "analysis_id": analysis.analysis_id if analysis else None,
                    },
                )
                
                db.add(search_content)
                await db.commit()
                await db.refresh(search_content)
                
                logger.info(
                    f"✅ [{job_key}] Indexed: {url} "
                    f"(type={content_type}, score={quality_score:.2f})"
                )
                return search_content
        
        except Exception as e:
            logger.error(f"❌ [{job_key}] Indexing failed: {e}", exc_info=True)
            return None
    
    async def reindex_session(
        self,
        session_id: str,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """Reindex all completed jobs in a session.
        
        Args:
            session_id: Session ID
            skip_existing: Skip already indexed URLs
        
        Returns:
            Dictionary with indexing results
        """
        logger.info(f"🔄 Reindexing session: {session_id}")
        
        try:
            async with get_db_session() as db:
                # Get all completed jobs in session
                stmt = select(CrawlJob).where(
                    and_(
                        CrawlJob.session_id == session_id,
                        CrawlJob.status == "completed",
                    )
                )
                result = await db.execute(stmt)
                jobs = result.scalars().all()
                
                indexed_count = 0
                skipped_count = 0
                failed_count = 0
                
                for job in jobs:
                    # Check if already indexed
                    if skip_existing:
                        existing = await db.execute(
                            select(SearchContent).where(
                                SearchContent.url == job.url
                            )
                        )
                        if existing.scalar_one_or_none():
                            skipped_count += 1
                            continue
                    
                    # Index the job
                    result = await self.index_crawl_job(
                        job_id=job.job_id,
                        session_id=job.session_id,
                        domain=job.domain,
                        url=job.url,
                    )
                    
                    if result:
                        indexed_count += 1
                    else:
                        failed_count += 1
                
                logger.info(
                    f"✨ Session {session_id}: "
                    f"indexed={indexed_count}, skipped={skipped_count}, failed={failed_count}"
                )
                
                return {
                    "session_id": session_id,
                    "indexed": indexed_count,
                    "skipped": skipped_count,
                    "failed": failed_count,
                    "total_processed": indexed_count + skipped_count + failed_count,
                }
        
        except Exception as e:
            logger.error(f"❌ Session reindex failed: {e}", exc_info=True)
            return {
                "session_id": session_id,
                "error": str(e),
                "indexed": 0,
                "skipped": 0,
                "failed": 0,
            }
    
    async def reindex_domain(
        self,
        domain: str,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """Reindex all completed jobs for a domain.
        
        Args:
            domain: Domain to reindex
            skip_existing: Skip already indexed URLs
        
        Returns:
            Dictionary with indexing results
        """
        logger.info(f"🔄 Reindexing domain: {domain}")
        
        try:
            async with get_db_session() as db:
                # Get all completed jobs for domain
                stmt = select(CrawlJob).where(
                    and_(
                        CrawlJob.domain == domain,
                        CrawlJob.status == "completed",
                    )
                )
                result = await db.execute(stmt)
                jobs = result.scalars().all()
                
                indexed_count = 0
                skipped_count = 0
                failed_count = 0
                
                for job in jobs:
                    # Check if already indexed
                    if skip_existing:
                        existing = await db.execute(
                            select(SearchContent).where(
                                SearchContent.url == job.url
                            )
                        )
                        if existing.scalar_one_or_none():
                            skipped_count += 1
                            continue
                    
                    # Index the job
                    result = await self.index_crawl_job(
                        job_id=job.job_id,
                        session_id=job.session_id,
                        domain=job.domain,
                        url=job.url,
                    )
                    
                    if result:
                        indexed_count += 1
                    else:
                        failed_count += 1
                
                logger.info(
                    f"✨ Domain {domain}: "
                    f"indexed={indexed_count}, skipped={skipped_count}, failed={failed_count}"
                )
                
                return {
                    "domain": domain,
                    "indexed": indexed_count,
                    "skipped": skipped_count,
                    "failed": failed_count,
                    "total_processed": indexed_count + skipped_count + failed_count,
                }
        
        except Exception as e:
            logger.error(f"❌ Domain reindex failed: {e}", exc_info=True)
            return {
                "domain": domain,
                "error": str(e),
                "indexed": 0,
                "skipped": 0,
                "failed": 0,
            }


# Global indexer instance
content_indexer = ContentIndexer()
