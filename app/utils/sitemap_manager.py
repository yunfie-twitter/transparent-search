"""Sitemap management with manual and automatic detection."""
import asyncio
from typing import List, Optional, Set, Dict, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime
import httpx
import xml.etree.ElementTree as ET
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

class SitemapManager:
    """Manages sitemaps for crawling."""
    
    REQUEST_TIMEOUT = 15.0
    USER_AGENT = "TransparentSearchBot/1.0 (+https://example.com/bot)"
    
    # Common sitemap locations
    COMMON_SITEMAP_PATHS = [
        "/sitemap.xml",
        "/sitemap-index.xml",
        "/sitemap_index.xml",
        "/sitemap1.xml",
        "/sitemaps/sitemap.xml",
        "/sitemap/sitemap.xml",
        "/rss.xml",
        "/feed.xml",
    ]
    
    @staticmethod
    async def detect_sitemaps(domain: str) -> List[str]:
        """Auto-detect sitemaps for a domain.
        
        Strategy:
        1. robots.txt
        2. Common sitemap locations
        3. Well-known locations
        """
        base_url = f"https://{domain}"
        detected_sitemaps = []
        
        # Strategy 1: robots.txt
        robots_sitemaps = await SitemapManager._from_robots(base_url)
        detected_sitemaps.extend(robots_sitemaps)
        
        # Strategy 2: Common paths
        common_sitemaps = await SitemapManager._from_common_paths(base_url)
        detected_sitemaps.extend(common_sitemaps)
        
        # Remove duplicates
        return list(set(detected_sitemaps))
    
    @staticmethod
    async def _from_robots(base_url: str) -> List[str]:
        """Extract sitemaps from robots.txt."""
        try:
            robots_url = urljoin(base_url, "/robots.txt")
            async with httpx.AsyncClient(timeout=SitemapManager.REQUEST_TIMEOUT) as client:
                resp = await client.get(robots_url, follow_redirects=True)
                if resp.status_code != 200:
                    return []
                
                sitemaps = []
                for line in resp.text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("sitemap:"):
                        url = line.split(":", 1)[1].strip()
                        if url:
                            sitemaps.append(url)
                
                return sitemaps
        except Exception as e:
            print(f"⚠️  Robots.txt parsing error: {e}")
            return []
    
    @staticmethod
    async def _from_common_paths(base_url: str) -> List[str]:
        """Check common sitemap paths."""
        sitemaps = []
        
        try:
            async with httpx.AsyncClient(timeout=SitemapManager.REQUEST_TIMEOUT) as client:
                for path in SitemapManager.COMMON_SITEMAP_PATHS:
                    sitemap_url = urljoin(base_url, path)
                    try:
                        resp = await client.head(sitemap_url, follow_redirects=True)
                        if resp.status_code == 200:
                            sitemaps.append(sitemap_url)
                    except Exception:
                        continue
        except Exception as e:
            print(f"⚠️  Common paths check error: {e}")
        
        return sitemaps
    
    @staticmethod
    async def parse_sitemap(
        sitemap_url: str,
        limit: int = 5000
    ) -> Tuple[List[str], List[Dict]]:
        """Parse sitemap and extract URLs.
        
        Returns:
            Tuple of (urls, metadata)
            - urls: List of page URLs
            - metadata: List of dicts with lastmod, changefreq, priority
        """
        try:
            async with httpx.AsyncClient(timeout=SitemapManager.REQUEST_TIMEOUT) as client:
                resp = await client.get(sitemap_url, follow_redirects=True)
                if resp.status_code != 200:
                    return [], []
                
                root = ET.fromstring(resp.content)
        except Exception as e:
            print(f"⚠️  Sitemap fetch error for {sitemap_url}: {e}")
            return [], []
        
        try:
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"
            
            urls = []
            metadata = []
            
            # Handle sitemap index
            if root.tag.endswith("sitemapindex"):
                for sm in root.findall(f"{ns}sitemap"):
                    loc = sm.find(f"{ns}loc")
                    if loc is not None and loc.text:
                        # Recursively parse child sitemap
                        child_urls, child_meta = await SitemapManager.parse_sitemap(
                            loc.text.strip(),
                            limit=limit
                        )
                        urls.extend(child_urls)
                        metadata.extend(child_meta)
                        if len(urls) >= limit:
                            return urls[:limit], metadata[:limit]
                
                return urls[:limit], metadata[:limit]
            
            # Handle URL sitemap
            for url_elem in root.findall(f"{ns}url"):
                loc = url_elem.find(f"{ns}loc")
                if loc is not None and loc.text:
                    url = loc.text.strip()
                    urls.append(url)
                    
                    # Extract metadata
                    meta = {"url": url}
                    
                    lastmod = url_elem.find(f"{ns}lastmod")
                    if lastmod is not None and lastmod.text:
                        meta["lastmod"] = lastmod.text
                    
                    changefreq = url_elem.find(f"{ns}changefreq")
                    if changefreq is not None and changefreq.text:
                        meta["changefreq"] = changefreq.text
                    
                    priority = url_elem.find(f"{ns}priority")
                    if priority is not None and priority.text:
                        try:
                            meta["priority"] = float(priority.text)
                        except ValueError:
                            pass
                    
                    metadata.append(meta)
                    
                    if len(urls) >= limit:
                        break
            
            return urls[:limit], metadata[:limit]
        
        except Exception as e:
            print(f"⚠️  Sitemap parsing error: {e}")
            return [], []
    
    @staticmethod
    async def get_all_urls(
        domain: str,
        custom_sitemaps: Optional[List[str]] = None
    ) -> Tuple[List[str], Set[str]]:
        """Get all URLs from sitemaps.
        
        Returns:
            Tuple of (urls, auto_detected_sitemaps)
        """
        base_url = f"https://{domain}"
        all_urls = []
        detected_sitemaps = set()
        
        # Custom sitemaps
        sitemaps_to_check = custom_sitemaps or []
        
        # Auto-detect sitemaps
        auto_sitemaps = await SitemapManager.detect_sitemaps(domain)
        sitemaps_to_check.extend(auto_sitemaps)
        detected_sitemaps.update(auto_sitemaps)
        
        # Parse each sitemap
        for sitemap_url in set(sitemaps_to_check):
            urls, _ = await SitemapManager.parse_sitemap(sitemap_url)
            all_urls.extend(urls)
        
        return list(set(all_urls)), detected_sitemaps

sitemap_manager = SitemapManager()
