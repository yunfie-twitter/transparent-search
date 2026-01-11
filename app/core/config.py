"""Application configuration - Centralized environment and settings management."""

import os
from typing import Optional

# ============================================================================
# Database Configuration
# ============================================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/transparent_search"
)

# ============================================================================
# Redis/Cache Configuration
# ============================================================================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").lower() == "true"

# Cache TTLs (in seconds)
CACHE_TTL_INTENT = 3600  # 1 hour
CACHE_TTL_SEARCH = 300   # 5 minutes
CACHE_TTL_TRACKER = 86400  # 24 hours
CACHE_TTL_CONTENT = 86400  # 24 hours

# ============================================================================
# Crawler Configuration
# ============================================================================

CRAWLER_MAX_DEPTH = int(os.getenv("CRAWLER_MAX_DEPTH", 3))
CRAWLER_TIMEOUT = int(os.getenv("CRAWLER_TIMEOUT", 30))  # seconds
CRAWLER_USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "Mozilla/5.0 (compatible; TransparentSearchBot/1.0)"
)
CRAWLER_CONCURRENT_REQUESTS = int(os.getenv("CRAWLER_CONCURRENT_REQUESTS", 5))
CRAWLER_ENABLE_JS_RENDERING = os.getenv("CRAWLER_ENABLE_JS_RENDERING", "false").lower() == "true"

# ============================================================================
# Application Configuration
# ============================================================================

APP_NAME = "Transparent Search API"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Advanced web crawling and intelligent search indexing"

# ============================================================================
# Logging Configuration
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# ============================================================================
# API Configuration
# ============================================================================

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8080))
API_RELOAD = os.getenv("API_RELOAD", "false").lower() == "true"

# ============================================================================
# Feature Flags
# ============================================================================

ENABLE_SMART_CRAWLING = os.getenv("ENABLE_SMART_CRAWLING", "true").lower() == "true"
ENABLE_SPAM_DETECTION = os.getenv("ENABLE_SPAM_DETECTION", "true").lower() == "true"
ENABLE_INTENT_DETECTION = os.getenv("ENABLE_INTENT_DETECTION", "true").lower() == "true"
ENABLE_METADATA_EXTRACTION = os.getenv("ENABLE_METADATA_EXTRACTION", "true").lower() == "true"


class Config:
    """Application configuration class."""
    
    # Database
    SQLALCHEMY_DATABASE_URL = DATABASE_URL
    SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true"
    
    # Redis
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    REDIS_ENABLED = REDIS_ENABLED
    
    # Crawler
    MAX_CRAWL_DEPTH = CRAWLER_MAX_DEPTH
    CRAWLER_TIMEOUT = CRAWLER_TIMEOUT
    CONCURRENT_REQUESTS = CRAWLER_CONCURRENT_REQUESTS
    
    # API
    API_V1_STR = "/api"
    
    class Config:
        case_sensitive = True


# Environment detection
def is_development() -> bool:
    """Check if running in development environment."""
    return os.getenv("ENV", "development").lower() == "development"


def is_production() -> bool:
    """Check if running in production environment."""
    return os.getenv("ENV", "development").lower() == "production"


def is_testing() -> bool:
    """Check if running in testing environment."""
    return os.getenv("ENV", "development").lower() == "testing"
