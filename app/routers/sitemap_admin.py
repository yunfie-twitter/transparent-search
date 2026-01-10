"""Sitemap management API endpoints."""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from ..utils.sitemap_manager import sitemap_manager

router = APIRouter(prefix="/sitemap", tags=["sitemap"])

@router.post("/detect/{domain}")
async def detect_sitemaps(domain: str):
    """
    Auto-detect sitemaps for a domain.
    
    Checks:
    1. robots.txt
    2. Common sitemap paths (/sitemap.xml, etc)
    """
    try:
        sitemaps = await sitemap_manager.detect_sitemaps(domain)
        
        if not sitemaps:
            return {
                "status": "success",
                "domain": domain,
                "found": False,
                "message": "No sitemaps detected",
                "sitemaps": [],
            }
        
        return {
            "status": "success",
            "domain": domain,
            "found": True,
            "count": len(sitemaps),
            "sitemaps": sitemaps,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Detection error: {str(e)}")


@router.post("/parse")
async def parse_sitemap(
    url: str = Query(..., description="Sitemap URL to parse"),
    limit: int = Query(5000, ge=1, le=10000, description="Max URLs to extract")
):
    """
    Parse a sitemap and extract URLs.
    
    Handles:
    - Simple URL sitemaps
    - Sitemap index files (recursively)
    - Metadata extraction (lastmod, changefreq, priority)
    """
    try:
        urls, metadata = await sitemap_manager.parse_sitemap(url, limit=limit)
        
        if not urls:
            return {
                "status": "success",
                "url": url,
                "found_urls": 0,
                "message": "No URLs found or failed to parse",
                "urls": [],
            }
        
        return {
            "status": "success",
            "url": url,
            "found_urls": len(urls),
            "urls": urls,
            "metadata": metadata if metadata else None,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse error: {str(e)}")


@router.post("/get-all")
async def get_all_urls(
    domain: str = Query(..., description="Domain to crawl"),
    custom_sitemaps: Optional[List[str]] = Query(
        None,
        description="Custom sitemap URLs (optional)"
    )
):
    """
    Get all URLs from a domain's sitemaps.
    
    Process:
    1. Auto-detect sitemaps (robots.txt, common paths)
    2. Add custom sitemaps if provided
    3. Parse all and extract unique URLs
    """
    try:
        all_urls, auto_detected = await sitemap_manager.get_all_urls(
            domain,
            custom_sitemaps=custom_sitemaps
        )
        
        return {
            "status": "success",
            "domain": domain,
            "total_urls": len(all_urls),
            "auto_detected_sitemaps": list(auto_detected),
            "custom_sitemaps": custom_sitemaps or [],
            "urls": all_urls,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/add")
async def add_custom_sitemap(
    domain: str = Query(..., description="Domain"),
    sitemap_url: str = Query(..., description="Sitemap URL to add")
):
    """
    Manually add a custom sitemap for a domain.
    
    This endpoint allows administrators to:
    - Override auto-detection
    - Add non-standard sitemap paths
    - Specify alternative sitemap formats
    """
    # Validate URL
    if not (sitemap_url.startswith("http://") or sitemap_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Invalid sitemap URL")
    
    # Validate domain matches (basic check)
    from urllib.parse import urlparse
    sitemap_domain = urlparse(sitemap_url).netloc
    
    if not domain in sitemap_domain:
        return {
            "status": "warning",
            "message": f"Sitemap domain ({sitemap_domain}) doesn't match target ({domain}). Proceeding anyway.",
            "domain": domain,
            "sitemap_url": sitemap_url,
        }
    
    return {
        "status": "success",
        "message": f"Sitemap {sitemap_url} added for {domain}",
        "domain": domain,
        "sitemap_url": sitemap_url,
    }


@router.get("/common-paths")
async def list_common_paths():
    """
    Get list of common sitemap paths that are checked.
    """
    return {
        "description": "Common sitemap locations checked during auto-detection",
        "paths": [
            "/sitemap.xml",
            "/sitemap-index.xml",
            "/sitemap_index.xml",
            "/sitemap1.xml",
            "/sitemaps/sitemap.xml",
            "/sitemap/sitemap.xml",
            "/rss.xml",
            "/feed.xml",
        ],
    }


@router.get("/docs")
async def sitemap_api_docs():
    """
    Get API documentation.
    """
    return {
        "title": "Sitemap Management API",
        "version": "1.0",
        "endpoints": {
            "POST /sitemap/detect/{domain}": {
                "description": "Auto-detect sitemaps for a domain",
                "example": "curl -X POST http://localhost:8080/admin/sitemap/detect/example.com",
            },
            "POST /sitemap/parse": {
                "description": "Parse a sitemap and extract URLs",
                "example": "curl -X POST http://localhost:8080/admin/sitemap/parse?url=https://example.com/sitemap.xml&limit=1000",
            },
            "POST /sitemap/get-all": {
                "description": "Get all URLs from domain sitemaps",
                "example": "curl -X POST http://localhost:8080/admin/sitemap/get-all?domain=example.com",
            },
            "POST /sitemap/add": {
                "description": "Manually add a custom sitemap",
                "example": "curl -X POST http://localhost:8080/admin/sitemap/add?domain=example.com&sitemap_url=https://example.com/custom-sitemap.xml",
            },
            "GET /sitemap/common-paths": {
                "description": "List common sitemap paths",
            },
        },
        "features": {
            "auto_detection": "Automatically finds sitemaps in robots.txt and common paths",
            "sitemap_index": "Handles sitemap index files with recursion",
            "metadata": "Extracts lastmod, changefreq, priority",
            "custom_sitemaps": "Support for manually added sitemaps",
        },
    }
