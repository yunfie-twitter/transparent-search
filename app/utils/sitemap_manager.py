"""Sitemap management with manual and automatic detection."""
import asyncio
from typing import List, Optional, Set, Dict, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime
import httpx
import xml.etree.ElementTree as ET
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import re

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
    def _remove_namespace(tag: str) -> str:
        """Remove XML namespace from tag name."""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag
    
    @staticmethod
    async def parse_sitemap(
        sitemap_url: str,
        limit: int = 5000,
        depth: int = 0,
        max_depth: int = 10
    ) -> Tuple[List[str], List[Dict]]:
        """Parse sitemap and extract URLs.
        
        Returns:
            Tuple of (urls, metadata)
            - urls: List of page URLs
            - metadata: List of dicts with lastmod, changefreq, priority
        """
        if depth > max_depth:
            print(f"⚠️  Sitemap recursion depth exceeded for {sitemap_url}")
            return [], []
        
        try:
            async with httpx.AsyncClient(
                timeout=SitemapManager.REQUEST_TIMEOUT,
                follow_redirects=True
            ) as client:
                resp = await client.get(sitemap_url)
                if resp.status_code != 200:
                    print(f"⚠️  Failed to fetch sitemap: {sitemap_url} ({resp.status_code})")
                    return [], []
                
                content = resp.content
                
                # Try to parse XML
                try:
                    root = ET.fromstring(content)
                except ET.ParseError as e:
                    print(f"⚠️  XML parse error for {sitemap_url}: {e}")
                    # Try fallback text parsing
                    return SitemapManager._parse_sitemap_text(content.decode('utf-8', errors='ignore')), []
        
        except Exception as e:
            print(f"⚠️  Sitemap fetch error for {sitemap_url}: {e}")
            return [], []
        
        # Parse XML content
        return SitemapManager._parse_sitemap_xml(root, sitemap_url, limit, depth)
    
    @staticmethod
    def _parse_sitemap_xml(
        root: ET.Element,
        sitemap_url: str,
        limit: int,
        depth: int = 0
    ) -> Tuple[List[str], List[Dict]]:
        """Parse XML sitemap element."""
        try:
            # Detect namespace
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"
            
            root_tag = SitemapManager._remove_namespace(root.tag)
            urls = []
            metadata = []
            
            # Handle sitemap index
            if root_tag == "sitemapindex":
                sitemap_elements = root.findall(f"{ns}sitemap", root) if ns else root.findall("sitemap")
                if not sitemap_elements:
                    sitemap_elements = root.findall(".//sitemap")
                
                for sm in sitemap_elements:
                    loc_elem = sm.find(f"{ns}loc") if ns else sm.find("loc")
                    if loc_elem is None:
                        loc_elem = sm.find(".//loc")
                    
                    if loc_elem is not None and loc_elem.text:
                        child_url = loc_elem.text.strip()
                        print(f"🔗 Found child sitemap: {child_url}")
                        # Note: Recursive parsing would need to be async
                        # For now, return the child sitemap URLs to be processed separately
                        urls.append(child_url)
                    if len(urls) >= limit:
                        break
                
                return urls, metadata
            
            # Handle URL sitemap
            elif root_tag == "urlset":
                url_elements = root.findall(f"{ns}url", root) if ns else root.findall("url")
                if not url_elements:
                    url_elements = root.findall(".//url")
                
                for url_elem in url_elements:
                    # Find location element
                    loc_elem = url_elem.find(f"{ns}loc") if ns else url_elem.find("loc")
                    if loc_elem is None:
                        loc_elem = url_elem.find(".//loc")
                    
                    if loc_elem is not None and loc_elem.text:
                        url = loc_elem.text.strip()
                        if url:
                            urls.append(url)
                            
                            # Extract metadata
                            meta = {"url": url}
                            
                            # Last modified
                            lastmod_elem = url_elem.find(f"{ns}lastmod") if ns else url_elem.find("lastmod")
                            if lastmod_elem is None:
                                lastmod_elem = url_elem.find(".//lastmod")
                            if lastmod_elem is not None and lastmod_elem.text:
                                meta["lastmod"] = lastmod_elem.text
                            
                            # Change frequency
                            changefreq_elem = url_elem.find(f"{ns}changefreq") if ns else url_elem.find("changefreq")
                            if changefreq_elem is None:
                                changefreq_elem = url_elem.find(".//changefreq")
                            if changefreq_elem is not None and changefreq_elem.text:
                                meta["changefreq"] = changefreq_elem.text
                            
                            # Priority
                            priority_elem = url_elem.find(f"{ns}priority") if ns else url_elem.find("priority")
                            if priority_elem is None:
                                priority_elem = url_elem.find(".//priority")
                            if priority_elem is not None and priority_elem.text:
                                try:
                                    meta["priority"] = float(priority_elem.text)
                                except ValueError:
                                    pass
                            
                            metadata.append(meta)
                            
                            if len(urls) >= limit:
                                break
            
            return urls[:limit], metadata[:limit]
        
        except Exception as e:
            print(f"⚠️  Sitemap XML parsing error: {e}")
            return [], []
    
    @staticmethod
    def _parse_sitemap_text(content: str) -> List[str]:
        """Fallback: Extract URLs from sitemap using regex."""
        urls = []
        
        # Extract URLs from <loc> tags
        pattern = r'<loc[^>]*>([^<]+)</loc>'
        matches = re.findall(pattern, content, re.IGNORECASE)
        
        for url in matches:
            url = url.strip()
            if url and url.startswith(('http://', 'https://')):
                urls.append(url)
        
        return urls
    
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
        processed_sitemaps = set()
        
        # Custom sitemaps
        sitemaps_to_check = custom_sitemaps or []
        
        # Auto-detect sitemaps
        auto_sitemaps = await SitemapManager.detect_sitemaps(domain)
        sitemaps_to_check.extend(auto_sitemaps)
        detected_sitemaps.update(auto_sitemaps)
        
        # Parse each sitemap (handle indexes)
        for sitemap_url in set(sitemaps_to_check):
            if sitemap_url in processed_sitemaps:
                continue
            processed_sitemaps.add(sitemap_url)
            
            urls, _ = await SitemapManager.parse_sitemap(sitemap_url)
            
            # Check if we got sitemap index entries (child sitemaps)
            # If so, recursively parse them
            for url in urls:
                if 'sitemap' in url.lower() and url not in processed_sitemaps:
                    print(f"📁 Processing child sitemap: {url}")
                    child_urls, _ = await SitemapManager.parse_sitemap(url)
                    all_urls.extend(child_urls)
                    processed_sitemaps.add(url)
                elif url.startswith(('http://', 'https://')):
                    all_urls.append(url)
        
        return list(set(all_urls)), detected_sitemaps

sitemap_manager = SitemapManager()
