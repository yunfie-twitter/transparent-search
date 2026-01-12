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

logger = logging.getLogger(__name__)


class ContentClassifier:
    """Content type classifier - detects content type without discrimination."""
    
    @staticmethod
    def classify_by_url(url: str) -> str:
        """Classify content type based on URL pattern.
        Neutral classification - all types are evaluated equally by quality score.
        
        Args:
            url: URL to classify
        
        Returns:
            Content type string
        """
        url_lower = url.lower()
        
        # Video/Streaming sites
        if any(x in url_lower for x in [
            "youtube.com", "youtu.be",
            "vimeo.com", "dailymotion.com",
            "netflix.com", "hulu.com",
            "twitch.tv", "niconico.jp",
            "/video", "/videos", "/stream",
            ".mp4", ".webm", ".mov",
        ]):
            return "video"
        
        # Manga/Comic sites
        if any(x in url_lower for x in [
            "manga", "manganelo", "mangakakalot",
            "webtoon", "comic", "doujin",
            "pixiv", "booth", "dlsite",
            "/ch/", "/episode",
        ]):
            return "manga"
        
        # Image galleries
        if any(x in url_lower for x in [
            ".jpg", ".png", ".gif", ".webp",
            "/image", "/images", "/photo", "/gallery",
            "imgur", "flickr", "500px",
        ]):
            return "image"
        
        # PDF documents
        if any(x in url_lower for x in [".pdf", "/pdf"]):
            return "pdf"
        
        # Code repositories
        if any(x in url_lower for x in ["/github", "/gitlab", "/bitbucket"]):
            return "code_repository"
        
        # Social media
        if any(x in url_lower for x in [
            "/twitter", "/facebook", "/instagram", "/tiktok",
            "twitter.com", "facebook.com", "instagram.com",
            "tiktok.com", "x.com"
        ]):
            return "social_media"
        
        # Official sites (but don't reject - just classify)
        if any(p in url_lower for p in [
            'www.',
            '/official',
            '/about',
            '/company',
            '/products',
            '/service',
            '/contact',
        ]):
            return "official_site"
        
        # Default to blog/article
        return "blog"


class QualityScoreCalculator:
    """Enhanced quality score calculation - evaluates all content types equally."""
    
    # Quality score thresholds
    MIN_QUALITY_SCORE = 0.45  # Minimum score to be indexed (applies to ALL types)
    EXCELLENT_SCORE = 0.8
    GOOD_SCORE = 0.6
    
    # Content requirements
    MIN_TITLE_LENGTH = 5
    MIN_CONTENT_LENGTH = 100
    MAX_TITLE_LENGTH = 200
    
    @staticmethod
    def calculate(
        content_type: str,
        extractor: 'HTMLMetadataExtractor',
        content: str,
        url: str,
        analysis_score: Optional[float] = None,
        page_value_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Calculate comprehensive quality score.
        
        All content types (blog, manga, video, official_site, etc.) are evaluated
        using the same criteria. No discrimination based on content type.
        
        Args:
            content_type: Detected content type (informational only)
            extractor: HTMLMetadataExtractor with extracted metadata
            content: Full HTML content
            url: Page URL
            analysis_score: PageAnalysis score (0-100)
            page_value_score: CrawlJob page value score (0-100)
        
        Returns:
            Dictionary with:
            - score: Final quality score (0-1)
            - factors: Individual scoring factors
            - reject_reason: Why page was rejected (if any)
            - should_index: Whether to index this content
        """
        factors = {}
        reject_reasons = []
        
        # 1. Content length check (critical)
        content_length = len(content.strip())
        if content_length < QualityScoreCalculator.MIN_CONTENT_LENGTH:
            reject_reasons.append(f"too_short_content({content_length}chars)")
            factors['content_length'] = 0.1
        else:
            # Score based on content length (100-5000 chars optimal)
            if content_length > 5000:
                factors['content_length'] = 1.0
            else:
                factors['content_length'] = min(1.0, content_length / 5000)
        
        # 2. Title quality (important)
        title = extractor.og_title or extractor.title or ""
        title_length = len(title.strip())
        
        if title_length < QualityScoreCalculator.MIN_TITLE_LENGTH:
            reject_reasons.append(f"poor_title({title_length}chars)")
            factors['title_quality'] = 0.2
        else:
            # Title quality score
            if title_length > QualityScoreCalculator.MAX_TITLE_LENGTH:
                factors['title_quality'] = 0.7  # Too long
            else:
                factors['title_quality'] = 0.9  # Good
        
        # 3. Structured data (metadata)
        metadata_score = 0.5
        if extractor.meta_description:
            metadata_score += 0.2
        if extractor.og_title or extractor.og_description:
            metadata_score += 0.2
        if extractor.h1_tags:
            metadata_score += 0.1
        factors['metadata_quality'] = min(1.0, metadata_score)
        
        # 4. Analysis score (if available)
        if analysis_score is not None:
            analysis_normalized = max(0, min(1.0, analysis_score / 100))
            factors['analysis_score'] = analysis_normalized
        
        # 5. Page value score (if available)
        if page_value_score is not None:
            page_value_normalized = max(0, min(1.0, page_value_score / 100))
            factors['page_value_score'] = page_value_normalized
        
        # 6. URL quality (avoid suspicious patterns)
        url_score = 1.0
        url_lower = url.lower()
        
        # Check for spam indicators
        spam_patterns = [
            '/download', '/redirect', '/click',
            '/ads', '/ad/', '/banner',
            'utm_', 'tracking', 'referrer=',
        ]
        for pattern in spam_patterns:
            if pattern in url_lower:
                url_score -= 0.1
                reject_reasons.append(f"spam_url_pattern({pattern})")
        
        factors['url_quality'] = max(0.3, url_score)
        
        # Calculate weighted final score
        # All content types use same weights - no discrimination
        weights = {
            'content_length': 0.25,
            'title_quality': 0.20,
            'metadata_quality': 0.15,
            'url_quality': 0.15,
            'analysis_score': 0.15,
            'page_value_score': 0.10,
        }
        
        final_score = 0.0
        total_weight = 0.0
        for factor_name, weight in weights.items():
            if factor_name in factors:
                final_score += factors[factor_name] * weight
                total_weight += weight
        
        if total_weight > 0:
            final_score = final_score / total_weight
        else:
            final_score = 0.5
        
        # Round to 2 decimals
        final_score = round(final_score, 2)
        
        # Determine reject reason
        reject_reason = None
        if final_score < QualityScoreCalculator.MIN_QUALITY_SCORE:
            reject_reason = f"low_score({final_score})"
        if reject_reasons and not reject_reason:
            reject_reason = " + ".join(reject_reasons[:2])
        
        return {
            'score': final_score,
            'factors': factors,
            'reject_reason': reject_reason,
            'should_index': final_score >= QualityScoreCalculator.MIN_QUALITY_SCORE and not reject_reasons,
            'content_type': content_type,
        }


class HTMLMetadataExtractor(HTMLParser):
    """Extract metadata from HTML content."""
    
    def __init__(self):
        super().__init__()
        self.title: Optional[str] = None
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
        
        if tag == "title" and not self.title:
            self.current_text = ""
        elif tag == "meta":
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
        if self.current_tag == "title":
            self.current_text += data.strip()
        elif self.current_tag in ("h1", "h2"):
            self.current_text += data.strip()
    
    def handle_endtag(self, tag: str):
        if tag == "title" and self.current_text and not self.title:
            self.title = self.current_text.strip()[:200]  # Limit to 200 chars
            self.current_text = ""
        elif tag == "h1" and self.current_text:
            self.h1_tags.append(self.current_text.strip())
            self.current_text = ""
        elif tag == "h2" and self.current_text:
            self.h2_tags.append(self.current_text.strip())
            self.current_text = ""
        self.current_tag = None


class ContentIndexer:
    """Index crawled content for search."""
    
    def __init__(self):
        self.classifier = ContentClassifier()
        self.quality_calculator = QualityScoreCalculator()
    
    def _extract_title(self, extractor: HTMLMetadataExtractor, url: str) -> str:
        """Extract best available title from page metadata.
        
        Args:
            extractor: HTMLMetadataExtractor with extracted metadata
            url: URL for fallback title generation
        
        Returns:
            Best available title or URL as fallback
        """
        # Priority order: og:title > title tag > h1 > domain
        if extractor.og_title:
            return extractor.og_title[:200]
        elif extractor.title:
            return extractor.title[:200]
        elif extractor.h1_tags:
            return extractor.h1_tags[0][:200]
        else:
            # Fallback: use domain/path
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split('/') if p]
            if path_parts:
                return path_parts[-1].replace('-', ' ').replace('_', ' ')[:200]
            return parsed.netloc or url
    
    async def index_crawl_job(
        self,
        job_id: str,
        session_id: str,
        domain: str,
        url: str,
    ) -> Optional[SearchContent]:
        """Index a completed crawl job into SearchContent.
        
        All content types are evaluated equally by quality score.
        
        Args:
            job_id: CrawlJob ID
            session_id: Session ID
            domain: Domain being crawled
            url: URL that was crawled
        
        Returns:
            SearchContent record or None if indexing failed or filtered
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
                
                # Classify content type (informational only)
                content_type = self.classifier.classify_by_url(url)
                logger.debug(f"[{job_key}] Content type: {content_type}")
                
                # Calculate quality score (same criteria for all types)
                quality_result = self.quality_calculator.calculate(
                    content_type=content_type,
                    extractor=extractor,
                    content=html_content,
                    url=url,
                    analysis_score=analysis.total_score if analysis else None,
                    page_value_score=job.page_value_score,
                )
                
                quality_score = quality_result['score']
                reject_reason = quality_result['reject_reason']
                
                # Enforce quality filtering (applies equally to all content types)
                if not quality_result['should_index']:
                    logger.warning(
                        f"⛔ [{job_key}] FILTERED OUT: {url} "
                        f"(type={content_type}, score={quality_score:.2f}, reason={reject_reason})"
                    )
                    # Mark job as indexed but record rejection reason
                    job.metadata_json = {
                        "indexed_at": datetime.utcnow().isoformat(),
                        "rejected": True,
                        "reject_reason": reject_reason,
                        "content_type": content_type,
                        "quality_score": quality_score,
                        "quality_factors": quality_result['factors'],
                    }
                    await db.commit()
                    return None
                
                # Extract title using priority chain
                title = self._extract_title(extractor, url)
                logger.debug(f"[{job_key}] Extracted title: {title}")
                
                # Create SearchContent record
                now = datetime.utcnow()
                search_content = SearchContent(
                    url=url,
                    domain=domain,
                    title=title,
                    description=extractor.meta_description or "",
                    content=html_content[:10000] if html_content else "",
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
                )
                
                # Store metadata in CrawlJob
                job.metadata_json = {
                    "indexed_at": now.isoformat(),
                    "content_type": content_type,
                    "quality_score": quality_score,
                    "quality_factors": quality_result['factors'],
                    "title_source": (
                        "og:title" if extractor.og_title else
                        "title_tag" if extractor.title else
                        "h1" if extractor.h1_tags else
                        "url_path"
                    ),
                    "analysis_id": analysis.analysis_id if analysis else None,
                }
                
                db.add(search_content)
                await db.commit()
                await db.refresh(search_content)
                
                logger.info(
                    f"✅ [{job_key}] Indexed: {url} "
                    f"(type={content_type}, score={quality_score:.2f}, title='{title[:50]}...')"
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
                filtered_count = 0
                
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
                        # Check if filtered or failed
                        if job.metadata_json and job.metadata_json.get('rejected'):
                            filtered_count += 1
                        else:
                            failed_count += 1
                
                logger.info(
                    f"✨ Session {session_id}: "
                    f"indexed={indexed_count}, filtered={filtered_count}, "
                    f"skipped={skipped_count}, failed={failed_count}"
                )
                
                return {
                    "session_id": session_id,
                    "indexed": indexed_count,
                    "filtered": filtered_count,
                    "skipped": skipped_count,
                    "failed": failed_count,
                    "total_processed": indexed_count + filtered_count + skipped_count + failed_count,
                }
        
        except Exception as e:
            logger.error(f"❌ Session reindex failed: {e}", exc_info=True)
            return {
                "session_id": session_id,
                "error": str(e),
                "indexed": 0,
                "filtered": 0,
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
                filtered_count = 0
                
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
                        # Check if filtered or failed
                        if job.metadata_json and job.metadata_json.get('rejected'):
                            filtered_count += 1
                        else:
                            failed_count += 1
                
                logger.info(
                    f"✨ Domain {domain}: "
                    f"indexed={indexed_count}, filtered={filtered_count}, "
                    f"skipped={skipped_count}, failed={failed_count}"
                )
                
                return {
                    "domain": domain,
                    "indexed": indexed_count,
                    "filtered": filtered_count,
                    "skipped": skipped_count,
                    "failed": failed_count,
                    "total_processed": indexed_count + filtered_count + skipped_count + failed_count,
                }
        
        except Exception as e:
            logger.error(f"❌ Domain reindex failed: {e}", exc_info=True)
            return {
                "domain": domain,
                "error": str(e),
                "indexed": 0,
                "filtered": 0,
                "skipped": 0,
                "failed": 0,
            }


# Global indexer instance
content_indexer = ContentIndexer()
