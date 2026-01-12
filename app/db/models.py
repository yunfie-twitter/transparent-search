"""SQLAlchemy ORM models for database."""
from sqlalchemy import Column, String, Integer, DateTime, Float, Boolean, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base
import uuid


class CrawlSession(Base):
    """Represents a crawl session."""
    __tablename__ = "crawl_sessions"
    
    session_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    domain = Column(String(255), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="pending")  # pending, running, completed, failed
    total_pages = Column(Integer, default=0)
    crawled_pages = Column(Integer, default=0)
    failed_pages = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    session_metadata = Column(JSON, nullable=True)  # Changed from 'metadata' (reserved word)
    
    # Relationships
    jobs = relationship("CrawlJob", back_populates="session", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_domain_status", "domain", "status"),
        Index("idx_created_at", "created_at"),
    )


class CrawlJob(Base):
    """Represents a single crawl job."""
    __tablename__ = "crawl_jobs"
    
    job_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("crawl_sessions.session_id"), nullable=True, index=True)
    domain = Column(String(255), nullable=False, index=True)
    url = Column(String(2048), nullable=True, index=True)
    status = Column(String(50), nullable=False, default="pending")  # pending, running, completed, failed, cancelled
    priority = Column(Integer, default=5)  # 1-10 (1 = highest)
    depth = Column(Integer, default=0)
    max_depth = Column(Integer, default=3)
    
    # Page metrics
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    word_count = Column(Integer, default=0)
    headings_count = Column(Integer, default=0)
    
    # Links
    internal_links_count = Column(Integer, default=0)
    external_links_count = Column(Integer, default=0)
    
    # Scoring
    page_value_score = Column(Float, default=0.0)
    spam_score = Column(Float, default=0.0)
    relevance_score = Column(Float, default=0.0)
    
    # Flags
    has_structured_data = Column(Boolean, default=False)
    has_og_tags = Column(Boolean, default=False)
    has_meta_description = Column(Boolean, default=False)
    enable_js_rendering = Column(Boolean, default=False)
    
    # Content
    content = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    
    # Crawl info
    total_pages = Column(Integer, default=1)
    crawled_pages = Column(Integer, default=0)
    failed_pages = Column(Integer, default=0)
    urls_to_crawl = Column(JSON, nullable=True)  # List of URLs
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationship
    session = relationship("CrawlSession", back_populates="jobs")
    
    __table_args__ = (
        Index("idx_domain_status", "domain", "status"),
        Index("idx_created_at", "created_at"),
        Index("idx_page_value", "page_value_score"),
        Index("idx_spam_score", "spam_score"),
        Index("idx_priority_status", "priority", "status"),
    )


class CrawlMetadata(Base):
    """Stores extracted metadata from crawled pages."""
    __tablename__ = "crawl_metadata"
    
    metadata_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("crawl_jobs.job_id"), nullable=False, index=True)
    url = Column(String(2048), nullable=False, index=True)
    
    # OG Tags
    og_title = Column(String(500), nullable=True)
    og_description = Column(Text, nullable=True)
    og_image = Column(String(2048), nullable=True)
    og_type = Column(String(100), nullable=True)
    og_url = Column(String(2048), nullable=True)
    
    # Twitter Card
    twitter_card = Column(String(100), nullable=True)
    twitter_title = Column(String(500), nullable=True)
    twitter_description = Column(Text, nullable=True)
    twitter_image = Column(String(2048), nullable=True)
    
    # Structured Data (JSON-LD)
    structured_data = Column(JSON, nullable=True)
    
    # Basic metadata
    canonical_url = Column(String(2048), nullable=True)
    robots_directive = Column(String(255), nullable=True)
    language = Column(String(10), nullable=True)
    charset = Column(String(50), nullable=True)
    
    # Publishing info
    publish_date = Column(DateTime, nullable=True)
    modified_date = Column(DateTime, nullable=True)
    author = Column(String(255), nullable=True)
    
    # Content structure
    h1_count = Column(Integer, default=0)
    h2_count = Column(Integer, default=0)
    h3_count = Column(Integer, default=0)
    
    # Images
    images_count = Column(Integer, default=0)
    images_with_alt = Column(Integer, default=0)
    images_data = Column(JSON, nullable=True)
    
    # Links
    internal_links = Column(JSON, nullable=True)
    external_links = Column(JSON, nullable=True)
    
    extracted_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index("idx_job_url", "job_id", "url"),
        Index("idx_extracted_at", "extracted_at"),
    )


class PageAnalysis(Base):
    """Stores page analysis results (scoring, spam detection, etc)."""
    __tablename__ = "page_analysis"
    
    analysis_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("crawl_jobs.job_id"), nullable=False, index=True)
    url = Column(String(2048), nullable=False, index=True)
    
    # Value Scoring
    depth_score = Column(Float, default=0.0)
    link_popularity_score = Column(Float, default=0.0)
    content_quality_score = Column(Float, default=0.0)
    metadata_completeness_score = Column(Float, default=0.0)
    freshness_score = Column(Float, default=0.0)
    uniqueness_score = Column(Float, default=0.0)
    total_score = Column(Float, default=0.0)
    crawl_priority = Column(Integer, default=5)  # 1-10
    recommendation = Column(String(50), nullable=True)  # CRAWL_NOW, CRAWL_SOON, CRAWL_LATER, LOW_VALUE
    
    # Spam Detection
    link_farm_score = Column(Float, default=0.0)
    reciprocal_linking_score = Column(Float, default=0.0)
    content_duplication_score = Column(Float, default=0.0)
    cms_anomaly_score = Column(Float, default=0.0)
    ip_reputation_score = Column(Float, default=0.0)
    spam_score = Column(Float, default=0.0)
    risk_level = Column(String(50), nullable=True)  # clean, suspicious, spam
    spam_signals = Column(JSON, nullable=True)
    
    # Query Intent Analysis
    query_intent = Column(String(50), nullable=True)  # informational, navigational, transactional, commercial, local
    intent_confidence = Column(Float, default=0.0)
    page_type = Column(String(100), nullable=True)
    relevance_score = Column(Float, default=0.0)
    intent_match_score = Column(Float, default=0.0)
    content_match_score = Column(Float, default=0.0)
    
    analyzed_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index("idx_job_url", "job_id", "url"),
        Index("idx_total_score", "total_score"),
        Index("idx_spam_score", "spam_score"),
        Index("idx_relevance", "relevance_score"),
    )


class SearchContent(Base):
    """Indexed search content."""
    __tablename__ = "search_content"
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), nullable=False, unique=True, index=True)
    domain = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    h1 = Column(String(500), nullable=True)
    h2_tags = Column(JSON, nullable=True)  # List of H2 headings
    meta_description = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)  # Full page content
    content_type = Column(String(100), nullable=True, index=True)  # text_article, video, image, etc.
    quality_score = Column(Float, default=0.5, index=True)  # 0.0-1.0
    
    # Metadata
    og_title = Column(String(500), nullable=True)
    og_description = Column(Text, nullable=True)
    og_image_url = Column(String(2048), nullable=True)
    favicon_url = Column(String(2048), nullable=True)  # Site favicon
    
    # Timestamps
    indexed_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_crawled_at = Column(DateTime, nullable=True)
    
    # Relationships
    images = relationship("PageImage", back_populates="page", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_domain_type", "domain", "content_type"),
        Index("idx_quality", "quality_score"),
        Index("idx_indexed_at", "indexed_at"),
    )


class PageImage(Base):
    """Images found on indexed pages."""
    __tablename__ = "page_images"
    
    image_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    page_id = Column(Integer, ForeignKey("search_content.id"), nullable=False, index=True)
    url = Column(String(2048), nullable=False)
    alt_text = Column(Text, nullable=True)  # ALT text for search
    title = Column(String(500), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    is_responsive = Column(Boolean, default=False)
    position_index = Column(Integer, default=0)  # Position on page
    discovered_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    page = relationship("SearchContent", back_populates="images")
    
    __table_args__ = (
        Index("idx_page_url", "page_id", "url"),
        Index("idx_alt_text", "alt_text"),
        Index("idx_discovered_at", "discovered_at"),
    )


class SiteFavicon(Base):
    """Website favicons."""
    __tablename__ = "site_favicons"
    
    favicon_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    domain = Column(String(255), nullable=False, unique=True, index=True)
    url = Column(String(2048), nullable=False)
    format = Column(String(50), nullable=True)  # ico, png, jpg, svg, etc.
    size = Column(String(50), nullable=True)  # e.g., "32x32", "64x64"
    discovered_at = Column(DateTime, default=datetime.utcnow)
    last_verified_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("idx_domain", "domain"),
    )
