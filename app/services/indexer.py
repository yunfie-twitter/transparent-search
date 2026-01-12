"""Content indexer service - converts crawled content to searchable index."""
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urlparse
from html.parser import HTMLParser
import re

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.db.models import CrawlJob, SearchContent, PageAnalysis, PageImage, SiteFavicon
from app.services.image_extractor import AssetExtractor

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


class ContentTypeEvaluator:
    """Content-type-specific quality evaluation.
    
    Each content type has different quality criteria:
    - Blog: Rich metadata, well-structured, clear authorship
    - Video: Transcripts, descriptions, engagement metrics
    - Manga: Visual consistency, chapter structure, metadata
    - Official: Structured data, domain authority
    - Image: Alt text, resolution, usage rights
    """
    
    # Type-specific minimum scores
    MIN_SCORES = {
        "blog": 0.50,
        "video": 0.45,
        "manga": 0.48,
        "image": 0.40,
        "pdf": 0.52,
        "official_site": 0.55,
        "code_repository": 0.60,
        "social_media": 0.35,
    }
    
    # Type-specific weights for quality factors
    FACTOR_WEIGHTS = {
        "blog": {
            "content_length": 0.25,
            "title_quality": 0.20,
            "metadata_quality": 0.20,
            "url_quality": 0.15,
            "analysis_score": 0.12,
            "page_value_score": 0.08,
        },
        "video": {
            "content_length": 0.15,
            "title_quality": 0.25,
            "metadata_quality": 0.25,
            "url_quality": 0.15,
            "analysis_score": 0.12,
            "page_value_score": 0.08,
        },
        "manga": {
            "content_length": 0.10,
            "title_quality": 0.25,
            "metadata_quality": 0.30,
            "url_quality": 0.15,
            "analysis_score": 0.12,
            "page_value_score": 0.08,
        },
        "image": {
            "content_length": 0.08,
            "title_quality": 0.20,
            "metadata_quality": 0.35,
            "url_quality": 0.15,
            "analysis_score": 0.12,
            "page_value_score": 0.10,
        },
        "pdf": {
            "content_length": 0.25,
            "title_quality": 0.20,
            "metadata_quality": 0.20,
            "url_quality": 0.15,
            "analysis_score": 0.12,
            "page_value_score": 0.08,
        },
        "official_site": {
            "content_length": 0.20,
            "title_quality": 0.15,
            "metadata_quality": 0.25,
            "url_quality": 0.20,
            "analysis_score": 0.12,
            "page_value_score": 0.08,
        },
        "code_repository": {
            "content_length": 0.30,
            "title_quality": 0.15,
            "metadata_quality": 0.20,
            "url_quality": 0.15,
            "analysis_score": 0.12,
            "page_value_score": 0.08,
        },
        "social_media": {
            "content_length": 0.20,
            "title_quality": 0.15,
            "metadata_quality": 0.15,
            "url_quality": 0.20,
            "analysis_score": 0.20,
            "page_value_score": 0.10,
        },
    }
    
    @staticmethod
    def get_min_score(content_type: str) -> float:
        """Get minimum quality score for content type."""
        return ContentTypeEvaluator.MIN_SCORES.get(content_type, 0.50)
    
    @staticmethod
    def get_weights(content_type: str) -> Dict[str, float]:
        """Get quality factor weights for content type."""
        return ContentTypeEvaluator.FACTOR_WEIGHTS.get(
            content_type,
            ContentTypeEvaluator.FACTOR_WEIGHTS["blog"]
        )
    
    @staticmethod
    def evaluate_for_type(
        content_type: str,
        factors: Dict[str, float],
    ) -> float:
        """Calculate weighted quality score for specific content type."""
        weights = ContentTypeEvaluator.get_weights(content_type)
        
        score = 0.0
        total_weight = 0.0
        
        for factor_name, weight in weights.items():
            if factor_name in factors:
                score += factors[factor_name] * weight
                total_weight += weight
        
        if total_weight > 0:
            score = score / total_weight
        else:
            score = 0.5
        
        return round(score, 2)


class QualityScoreCalculator:
    """Enhanced quality score calculation with content-type-specific criteria."""
    
    # Content requirements (base)
    MIN_TITLE_LENGTH = 5
    MIN_CONTENT_LENGTH = 50
    MAX_TITLE_LENGTH = 200
    
    # Type-specific content requirements
    TYPE_CONTENT_REQUIREMENTS = {
        "blog": 100,
        "video": 30,
        "manga": 50,
        "image": 20,
        "pdf": 100,
        "official_site": 80,
        "code_repository": 120,
        "social_media": 10,
    }
    
    @staticmethod
    def calculate(
        content_type: str,
        extractor: 'HTMLMetadataExtractor',
        content: str,
        url: str,
        analysis_score: Optional[float] = None,
        page_value_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Calculate comprehensive quality score with type-specific criteria."""
        factors = {}
        reject_reasons = []
        
        # Get type-specific minimum content length
        min_content_length = QualityScoreCalculator.TYPE_CONTENT_REQUIREMENTS.get(
            content_type,
            QualityScoreCalculator.MIN_CONTENT_LENGTH
        )
        
        # 1. Content length check
        content_length = len(content.strip())
        if content_length < min_content_length:
            reject_reasons.append(f"insufficient_content({content_length}/{min_content_length})")
            factors['content_length'] = max(0.1, content_length / min_content_length * 0.5)
        else:
            # Score based on content length (optimal varies by type)
            optimal_length = min_content_length * 10
            if content_length > optimal_length:
                factors['content_length'] = 1.0
            else:
                factors['content_length'] = min(1.0, content_length / optimal_length)
        
        # 2. Title quality
        title = extractor.og_title or extractor.title or ""
        title_length = len(title.strip())
        
        if title_length < QualityScoreCalculator.MIN_TITLE_LENGTH:
            reject_reasons.append(f"missing_title")
            factors['title_quality'] = 0.1
        else:
            # Penalize excessively long titles
            if title_length > QualityScoreCalculator.MAX_TITLE_LENGTH:
                factors['title_quality'] = 0.6
            else:
                factors['title_quality'] = 0.95
        
        # 3. Metadata completeness (type-specific)
        metadata_score = 0.3
        
        # Common metadata
        if extractor.meta_description:
            metadata_score += 0.15
        if extractor.og_title:
            metadata_score += 0.15
        if extractor.og_description:
            metadata_score += 0.10
        if extractor.og_image_url:
            metadata_score += 0.10
        
        # Type-specific metadata bonuses
        if content_type == "blog":
            if extractor.h1_tags and len(extractor.h1_tags) > 0:
                metadata_score += 0.10
            if extractor.h2_tags and len(extractor.h2_tags) > 2:
                metadata_score += 0.05
        
        elif content_type == "video":
            if len(extractor.meta_description or "") > 50:
                metadata_score += 0.15
            if "video" in content.lower() or "transcript" in content.lower():
                metadata_score += 0.05
        
        elif content_type == "manga":
            if extractor.h1_tags:
                metadata_score += 0.10
            if extractor.h2_tags:
                metadata_score += 0.10
        
        elif content_type == "image":
            alt_text_count = len(re.findall(r'alt=["\']([^"\']*)["]', content))
            if alt_text_count > 0:
                metadata_score += 0.15
        
        elif content_type == "official_site":
            if extractor.og_title and extractor.og_description:
                metadata_score += 0.15
            if "json-ld" in content.lower() or "schema" in content.lower():
                metadata_score += 0.10
        
        elif content_type == "code_repository":
            if "readme" in content.lower() or "documentation" in content.lower():
                metadata_score += 0.20
            if "github" in url.lower() or "gitlab" in url.lower():
                metadata_score += 0.10
        
        factors['metadata_quality'] = min(1.0, metadata_score)
        
        # 4. Analysis score (if available)
        if analysis_score is not None:
            analysis_normalized = max(0, min(1.0, analysis_score / 100))
            factors['analysis_score'] = analysis_normalized
        else:
            factors['analysis_score'] = 0.5
        
        # 5. Page value score (if available)
        if page_value_score is not None:
            page_value_normalized = max(0, min(1.0, page_value_score / 100))
            factors['page_value_score'] = page_value_normalized
        else:
            factors['page_value_score'] = 0.5
        
        # 6. URL quality (spam detection)
        url_score = 1.0
        url_lower = url.lower()
        
        spam_patterns = [
            '/download', '/redirect', '/click',
            '/ads', '/ad/', '/banner',
            'utm_', 'tracking', 'referrer=',
            'onclick', 'onclick=',
        ]
        
        for pattern in spam_patterns:
            if pattern in url_lower:
                url_score -= 0.15
                reject_reasons.append(f"spam_pattern({pattern})")
        
        # Boost score for known quality domains
        quality_domains = [
            "github.com", "medium.com", "dev.to",
            "stackoverflow.com", "wikipedia.org",
            "arxiv.org", "nature.com", "science.org",
        ]
        if any(domain in url_lower for domain in quality_domains):
            url_score = min(1.0, url_score + 0.15)
        
        factors['url_quality'] = max(0.2, url_score)
        
        # 7. Calculate weighted final score using type-specific weights
        final_score = ContentTypeEvaluator.evaluate_for_type(content_type, factors)
        
        # 8. Apply type-specific minimum threshold
        min_score = ContentTypeEvaluator.get_min_score(content_type)
        
        # Determine rejection
        reject_reason = None
        should_index = final_score >= min_score
        
        if final_score < min_score:
            reject_reason = f"below_threshold({final_score:.2f} < {min_score:.2f})"
        
        if reject_reasons and not should_index:
            reject_reason = " + ".join(reject_reasons[:3])
        
        return {
            'score': final_score,
            'factors': factors,
            'reject_reason': reject_reason,
            'should_index': should_index,
            'content_type': content_type,
            'min_required_score': min_score,
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
            self.title = self.current_text.strip()[:200]
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
        self.asset_extractor = AssetExtractor()
    
    def _extract_title(self, extractor: HTMLMetadataExtractor, url: str) -> str:
        """Extract best available title from page metadata."""
        if extractor.og_title:
            return extractor.og_title[:200]
        elif extractor.title:
            return extractor.title[:200]
        elif extractor.h1_tags:
            return extractor.h1_tags[0][:200]
        else:
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split('/') if p]
            if path_parts:
                return path_parts[-1].replace('-', ' ').replace('_', ' ')[:200]
            return parsed.netloc or url
    
    async def _save_images(
        self,
        db: AsyncSession,
        page_id: int,
        images: List[Dict[str, Any]],
    ) -> int:
        """Save extracted images to database.
        
        Returns:
            Count of saved images
        """
        saved_count = 0
        
        for image_data in images:
            try:
                page_image = PageImage(
                    page_id=page_id,
                    url=image_data["url"],
                    alt_text=image_data["alt_text"] if image_data["alt_text"] else None,
                    title=image_data["title"] if image_data["title"] else None,
                    width=image_data["width"],
                    height=image_data["height"],
                    is_responsive=image_data["is_responsive"],
                    position_index=image_data["position_index"],
                )
                db.add(page_image)
                saved_count += 1
            except Exception as e:
                logger.warning(f"Failed to save image: {image_data['url']} - {e}")
        
        if saved_count > 0:
            logger.debug(f"Saved {saved_count} images for page {page_id}")
        
        return saved_count
    
    async def _save_favicon(
        self,
        db: AsyncSession,
        domain: str,
        favicon_data: Dict[str, str],
    ) -> None:
        """Save favicon to database."""
        try:
            # Check if favicon already exists for domain
            existing = await db.execute(
                select(SiteFavicon).where(SiteFavicon.domain == domain)
            )
            existing_favicon = existing.scalar_one_or_none()
            
            if existing_favicon:
                # Update existing
                existing_favicon.url = favicon_data["url"]
                existing_favicon.format = favicon_data.get("format")
                existing_favicon.size = favicon_data.get("size")
                existing_favicon.last_verified_at = datetime.utcnow()
            else:
                # Create new
                favicon = SiteFavicon(
                    domain=domain,
                    url=favicon_data["url"],
                    format=favicon_data.get("format"),
                    size=favicon_data.get("size"),
                )
                db.add(favicon)
            
            logger.debug(f"Saved favicon for {domain}: {favicon_data['url']}")
        
        except Exception as e:
            logger.warning(f"Failed to save favicon for {domain}: {e}")
    
    async def index_crawl_job(
        self,
        job_id: str,
        session_id: str,
        domain: str,
        url: str,
    ) -> Optional[SearchContent]:
        """Index a completed crawl job into SearchContent with images and favicon."""
        job_key = job_id[:8]
        logger.info(f"🔍 [{job_key}] Processing: {url}")
        
        try:
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
                    logger.debug(f"[{job_key}] Already indexed")
                    return None
                
                # Extract metadata
                html_content = job.content or ""
                extractor = HTMLMetadataExtractor()
                try:
                    extractor.feed(html_content)
                except Exception as e:
                    logger.warning(f"[{job_key}] HTML parsing warning: {e}")
                
                # Get analysis
                analysis_stmt = select(PageAnalysis).where(
                    PageAnalysis.url == url
                ).order_by(PageAnalysis.analyzed_at.desc()).limit(1)
                analysis_result = await db.execute(analysis_stmt)
                analysis = analysis_result.scalar_one_or_none()
                
                # Classify and evaluate
                content_type = self.classifier.classify_by_url(url)
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
                
                # Filter decision
                if not quality_result['should_index']:
                    logger.warning(
                        f"⛔ [{job_key}] FILTERED: {content_type} "
                        f"(score={quality_score:.2f}, reason={reject_reason})"
                    )
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
                
                # Extract title
                title = self._extract_title(extractor, url)
                logger.debug(f"[{job_key}] Title: {title}")
                
                # Extract images and favicon
                images, images_with_alt = self.asset_extractor.extract_images(
                    html_content, url
                )
                favicon = self.asset_extractor.extract_favicon(
                    html_content, url
                )
                
                # Create SearchContent
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
                    favicon_url=favicon["url"] if favicon else None,
                    indexed_at=now,
                    last_crawled_at=job.completed_at or now,
                )
                
                db.add(search_content)
                await db.flush()  # Get the ID
                
                # Save images
                if images:
                    await self._save_images(db, search_content.id, images)
                
                # Save favicon
                if favicon:
                    await self._save_favicon(db, domain, favicon)
                
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
                    "images_extracted": len(images),
                    "images_with_alt": images_with_alt,
                    "favicon_found": favicon is not None,
                }
                
                await db.commit()
                await db.refresh(search_content)
                
                logger.info(
                    f"✅ [{job_key}] Indexed: {content_type} "
                    f"(score={quality_score:.2f}, images={len(images)}, "
                    f"with_alt={images_with_alt}, favicon={'yes' if favicon else 'no'})"
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
        """Reindex all completed jobs in a session."""
        logger.info(f"🔄 Reindexing session: {session_id}")
        
        try:
            async with get_db_session() as db:
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
                type_stats = {}
                total_images = 0
                
                for job in jobs:
                    if skip_existing:
                        existing = await db.execute(
                            select(SearchContent).where(
                                SearchContent.url == job.url
                            )
                        )
                        if existing.scalar_one_or_none():
                            skipped_count += 1
                            continue
                    
                    result = await self.index_crawl_job(
                        job_id=job.job_id,
                        session_id=job.session_id,
                        domain=job.domain,
                        url=job.url,
                    )
                    
                    if result:
                        indexed_count += 1
                        content_type = result.content_type
                        type_stats[content_type] = type_stats.get(content_type, 0) + 1
                        if result.images:
                            total_images += len(result.images)
                    else:
                        if job.metadata_json and job.metadata_json.get('rejected'):
                            filtered_count += 1
                        else:
                            failed_count += 1
                
                logger.info(
                    f"✨ Session {session_id}: "
                    f"indexed={indexed_count}, filtered={filtered_count}, "
                    f"skipped={skipped_count}, failed={failed_count}, "
                    f"images={total_images}"
                )
                logger.info(f"📊 By type: {type_stats}")
                
                return {
                    "session_id": session_id,
                    "indexed": indexed_count,
                    "filtered": filtered_count,
                    "skipped": skipped_count,
                    "failed": failed_count,
                    "by_type": type_stats,
                    "total_images": total_images,
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
        """Reindex all completed jobs for a domain."""
        logger.info(f"🔄 Reindexing domain: {domain}")
        
        try:
            async with get_db_session() as db:
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
                type_stats = {}
                total_images = 0
                
                for job in jobs:
                    if skip_existing:
                        existing = await db.execute(
                            select(SearchContent).where(
                                SearchContent.url == job.url
                            )
                        )
                        if existing.scalar_one_or_none():
                            skipped_count += 1
                            continue
                    
                    result = await self.index_crawl_job(
                        job_id=job.job_id,
                        session_id=job.session_id,
                        domain=job.domain,
                        url=job.url,
                    )
                    
                    if result:
                        indexed_count += 1
                        content_type = result.content_type
                        type_stats[content_type] = type_stats.get(content_type, 0) + 1
                        if result.images:
                            total_images += len(result.images)
                    else:
                        if job.metadata_json and job.metadata_json.get('rejected'):
                            filtered_count += 1
                        else:
                            failed_count += 1
                
                logger.info(
                    f"✨ Domain {domain}: "
                    f"indexed={indexed_count}, filtered={filtered_count}, "
                    f"skipped={skipped_count}, failed={failed_count}, "
                    f"images={total_images}"
                )
                logger.info(f"📊 By type: {type_stats}")
                
                return {
                    "domain": domain,
                    "indexed": indexed_count,
                    "filtered": filtered_count,
                    "skipped": skipped_count,
                    "failed": failed_count,
                    "by_type": type_stats,
                    "total_images": total_images,
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
