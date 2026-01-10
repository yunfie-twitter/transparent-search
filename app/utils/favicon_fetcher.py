"""Favicon fetcher with multiple fallback strategies."""
import asyncio
from typing import Optional
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup

class FaviconFetcher:
    """Fetches favicons using multiple strategies."""
    
    REQUEST_TIMEOUT = 10.0
    USER_AGENT = "TransparentSearchBot/1.0 (+https://example.com/bot)"
    
    @staticmethod
    async def fetch_favicon(domain: str) -> Optional[str]:
        """Fetch favicon URL for domain using multiple strategies."""
        base_url = f"https://{domain}"
        
        # Strategy 1: HTML head tags
        favicon = await FaviconFetcher._from_html(base_url)
        if favicon:
            return favicon
        
        # Strategy 2: /favicon.ico
        favicon = await FaviconFetcher._from_root(base_url)
        if favicon:
            return favicon
        
        # Strategy 3: /apple-touch-icon.png
        favicon = await FaviconFetcher._from_apple_touch(base_url)
        if favicon:
            return favicon
        
        # Strategy 4: Common alternative locations
        favicon = await FaviconFetcher._from_common_paths(base_url)
        if favicon:
            return favicon
        
        return None
    
    @staticmethod
    async def _from_html(url: str) -> Optional[str]:
        """Extract favicon from HTML head."""
        try:
            async with httpx.AsyncClient(timeout=FaviconFetcher.REQUEST_TIMEOUT) as client:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code != 200:
                    return None
                
                soup = BeautifulSoup(resp.text, "html.parser")
                
                # Check multiple favicon link types
                favicon_selectors = [
                    {"rel": "icon"},
                    {"rel": "shortcut icon"},
                    {"rel": "apple-touch-icon"},
                    {"rel": "apple-touch-icon-precomposed"},
                ]
                
                for selector in favicon_selectors:
                    link = soup.find("link", selector)
                    if link and link.get("href"):
                        return urljoin(url, link.get("href"))
                
                return None
        except Exception as e:
            print(f"⚠️  Favicon HTML extraction error: {e}")
            return None
    
    @staticmethod
    async def _from_root(url: str) -> Optional[str]:
        """Check /favicon.ico at domain root."""
        try:
            favicon_url = urljoin(url, "/favicon.ico")
            async with httpx.AsyncClient(timeout=FaviconFetcher.REQUEST_TIMEOUT) as client:
                resp = await client.head(favicon_url, follow_redirects=True)
                if resp.status_code == 200:
                    return favicon_url
            return None
        except Exception:
            return None
    
    @staticmethod
    async def _from_apple_touch(url: str) -> Optional[str]:
        """Check /apple-touch-icon.png."""
        try:
            apple_url = urljoin(url, "/apple-touch-icon.png")
            async with httpx.AsyncClient(timeout=FaviconFetcher.REQUEST_TIMEOUT) as client:
                resp = await client.head(apple_url, follow_redirects=True)
                if resp.status_code == 200:
                    return apple_url
            return None
        except Exception:
            return None
    
    @staticmethod
    async def _from_common_paths(url: str) -> Optional[str]:
        """Check common alternative favicon paths."""
        common_paths = [
            "/favicon.png",
            "/favicon.jpg",
            "/favicon.jpeg",
            "/assets/favicon.ico",
            "/images/favicon.ico",
            "/.well-known/apple-touch-icon",
        ]
        
        try:
            async with httpx.AsyncClient(timeout=FaviconFetcher.REQUEST_TIMEOUT) as client:
                for path in common_paths:
                    favicon_url = urljoin(url, path)
                    try:
                        resp = await client.head(favicon_url, follow_redirects=True)
                        if resp.status_code == 200:
                            return favicon_url
                    except Exception:
                        continue
            return None
        except Exception:
            return None

favicon_fetcher = FaviconFetcher()
