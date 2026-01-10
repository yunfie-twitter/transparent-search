import asyncio
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Set, List, Dict
from urllib.parse import urljoin, urlparse

import chardet
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from .utils.url_normalizer import normalize_url, is_valid_url
from .utils.text_processor import clean_html_text, tokenize_with_mecab

# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/search_engine"
)
USER_AGENT = os.getenv("CRAWLER_UA", "TransparentSearchBot/1.0 (+https://example.com/bot)")
CRAWL_DELAY = float(os.getenv("CRAWL_DELAY", "1.5"))  # seconds between requests
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "15.0"))

engine = create_async_engine(DATABASE_URL, echo=False)

@dataclass
class RobotsRules:
    disallow: List[str]
    allow: List[str]
    crawl_delay: Optional[float] = None

    def is_allowed(self, path: str) -> bool:
        candidates = []
        for a in self.allow:
            if path.startswith(a):
                candidates.append((len(a), True))
        for d in self.disallow:
            if path.startswith(d):
                candidates.append((len(d), False))
        if not candidates:
            return True
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

@dataclass
class CrawlStats:
    total_attempted: int = 0
    total_success: int = 0
    total_failed: int = 0
    total_skipped: int = 0

def detect_trackers(html: str, url: str) -> Dict:
    """
    Safely detect trackers in HTML.
    Returns dict with tracker info and risk score.
    """
    try:
        # Common tracker patterns
        tracker_patterns = {
            'google_analytics': r'google-analytics|UA-\d+',
            'facebook_pixel': r'facebook\.com/tr|fbq\(',
            'google_ads': r'google.*?ads|googleadservices',
            'mixpanel': r'mixpanel\.com',
            'amplitude': r'amplitude\.com',
            'hotjar': r'hotjar\.com',
            'intercom': r'intercom\.com',
            'rollbar': r'rollbar\.com',
            'sentry': r'sentry\.io',
        }
        
        found_trackers = []
        for name, pattern in tracker_patterns.items():
            import re
            if re.search(pattern, html, re.IGNORECASE):
                found_trackers.append(name)
        
        # Calculate risk score (0.0 = clean, 1.0 = heavy trackers)
        tracker_count = len(found_trackers)
        if tracker_count == 0:
            tracker_risk_score = 0.0
            risk_profile = 'clean'
        elif tracker_count <= 2:
            tracker_risk_score = 0.3
            risk_profile = 'minimal'
        elif tracker_count <= 4:
            tracker_risk_score = 0.6
            risk_profile = 'moderate'
        elif tracker_count <= 6:
            tracker_risk_score = 0.8
            risk_profile = 'heavy'
        else:
            tracker_risk_score = 1.0
            risk_profile = 'severe'
        
        return {
            'trackers': found_trackers,
            'tracker_count': tracker_count,
            'tracker_risk_score': tracker_risk_score,
            'risk_profile': risk_profile,
        }
    except Exception as e:
        print(f"⚠️  Tracker detection error: {e}")
        return {
            'trackers': [],
            'tracker_count': 0,
            'tracker_risk_score': 0.5,  # Default: moderate risk
            'risk_profile': 'unknown',
        }

async def fetch_with_retry(
    client: httpx.AsyncClient, url: str, max_retries: int = MAX_RETRIES
) -> Optional[httpx.Response]:
    """Fetch URL with retry logic and redirect following."""
    for attempt in range(max_retries):
        try:
            resp = await client.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
            if resp.status_code == 200:
                return resp
            elif resp.status_code in (301, 302, 303, 307, 308):
                continue
            else:
                return None
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
            continue
        except Exception as e:
            print(f"⚠️  Fetch error for {url}: {e}")
            return None
    return None

def detect_charset(content: bytes, default: str = "utf-8") -> str:
    """Detect charset from content."""
    try:
        result = chardet.detect(content)
        encoding = result.get("encoding", default)
        return encoding or default
    except Exception:
        return default

async def parse_robots(client: httpx.AsyncClient, site_base: str) -> tuple[RobotsRules, List[str]]:
    """Parse robots.txt."""
    robots_url = urljoin(site_base, "/robots.txt")
    resp = await fetch_with_retry(client, robots_url)
    
    disallow: List[str] = []
    allow: List[str] = []
    sitemaps: List[str] = []
    crawl_delay: Optional[float] = None
    
    if not resp:
        return RobotsRules(disallow=disallow, allow=allow, crawl_delay=crawl_delay), sitemaps
    
    try:
        text_body = resp.text
        current_ua = None
        
        for line in text_body.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            
            if k == "user-agent":
                current_ua = v
                continue
            
            if current_ua not in ("*", None):
                continue
            
            if k == "disallow":
                disallow.append(v or "/")
            elif k == "allow":
                allow.append(v)
            elif k == "sitemap":
                sitemaps.append(v)
            elif k == "crawl-delay":
                try:
                    crawl_delay = float(v)
                except ValueError:
                    pass
    except Exception as e:
        print(f"⚠️  Robots.txt parse error: {e}")
    
    return RobotsRules(disallow=disallow, allow=allow, crawl_delay=crawl_delay), sitemaps

async def parse_sitemap_urls(client: httpx.AsyncClient, sitemap_url: str, limit: int = 2000) -> List[str]:
    """Parse sitemap.xml recursively."""
    resp = await fetch_with_retry(client, sitemap_url)
    if not resp:
        return []
    
    try:
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"⚠️  Sitemap parse error: {e}")
        return []
    
    try:
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"
        
        urls: List[str] = []
        
        if root.tag.endswith("sitemapindex"):
            for sm in root.findall(f"{ns}sitemap"):
                loc = sm.find(f"{ns}loc")
                if loc is not None and loc.text:
                    urls.extend(await parse_sitemap_urls(client, loc.text.strip(), limit=limit))
                    if len(urls) >= limit:
                        return urls[:limit]
            return urls[:limit]
        
        for u in root.findall(f"{ns}url"):
            loc = u.find(f"{ns}loc")
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
            if len(urls) >= limit:
                break
        
        return urls
    except Exception as e:
        print(f"⚠️  Sitemap processing error: {e}")
        return []

def extract_metadata(soup: BeautifulSoup, url: str) -> Dict:
    """Extract metadata from HTML."""
    try:
        title = soup.title.string.strip() if soup.title and soup.title.string else url
        
        # OGP
        def meta(prop: str) -> Optional[str]:
            tag = soup.find("meta", property=prop)
            return tag.get("content") if tag and tag.get("content") else None
        
        og_title = meta("og:title")
        og_description = meta("og:description")
        og_image = meta("og:image")
        
        # JSON-LD
        jsonld_items = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if script.string:
                try:
                    jsonld_items.append(json.loads(script.string))
                except Exception:
                    pass
        
        # H1 Extraction with Fallback
        h1_tags = soup.find_all("h1")
        if h1_tags:
            h1_text = " ".join([h.get_text(strip=True) for h in h1_tags])
        else:
            h1_text = title
        
        # Remove script/style
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        
        body_text = soup.get_text(separator=" ", strip=True)
        body_text = clean_html_text(body_text)
        
        # Images
        images = []
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                images.append({
                    "url": urljoin(url, src),
                    "alt": img.get("alt", "")[:255]
                })
        
        # Links
        links = []
        domain = urlparse(url).netloc
        for a in soup.find_all("a"):
            href = a.get("href")
            if not href:
                continue
            abs_url = urljoin(url, href)
            if is_valid_url(abs_url):
                norm_url = normalize_url(abs_url)
                is_same_domain = urlparse(norm_url).netloc == domain
                links.append((norm_url, is_same_domain))
        
        return {
            "title": title,
            "h1": h1_text,
            "og_title": og_title,
            "og_description": og_description,
            "og_image": og_image,
            "jsonld": jsonld_items or None,
            "body_text": body_text,
            "images": images,
            "links": links,
        }
    except Exception as e:
        print(f"⚠️  Metadata extraction error: {e}")
        return {
            "title": url,
            "h1": url,
            "og_title": None,
            "og_description": None,
            "og_image": None,
            "jsonld": None,
            "body_text": "",
            "images": [],
            "links": [],
        }

async def upsert_page(session: AsyncSession, site_id: int, url: str, metadata: Dict, tracker_risk: float = 0.5) -> int:
    """Insert or update page with tracker risk score."""
    try:
        result = await session.execute(
            text("""
                INSERT INTO pages (
                    url, site_id, title, h1, content,
                    og_title, og_description, og_image_url, jsonld,
                    tracker_risk_score,
                    last_crawled_at
                )
                VALUES (:url, :site_id, :title, :h1, :content, :og_title, :og_desc, :og_img, :jsonld, :tracker_risk, NOW())
                ON CONFLICT (url) DO UPDATE
                SET site_id = EXCLUDED.site_id,
                    title = EXCLUDED.title,
                    h1 = EXCLUDED.h1,
                    content = EXCLUDED.content,
                    og_title = EXCLUDED.og_title,
                    og_description = EXCLUDED.og_description,
                    og_image_url = EXCLUDED.og_image_url,
                    jsonld = EXCLUDED.jsonld,
                    tracker_risk_score = EXCLUDED.tracker_risk_score,
                    last_crawled_at = NOW()
                RETURNING id
            """),
            {
                "url": url,
                "site_id": site_id,
                "title": metadata["title"][:500],
                "h1": metadata["h1"][:500],
                "content": metadata["body_text"][:10000],
                "og_title": metadata["og_title"],
                "og_desc": metadata["og_description"],
                "og_img": metadata["og_image"],
                "jsonld": json.dumps(metadata["jsonld"]) if metadata["jsonld"] else None,
                "tracker_risk": tracker_risk,
            },
        )
        return result.scalar()
    except Exception as e:
        print(f"⚠️  Page upsert error for {url}: {e}")
        raise

async def save_images(session: AsyncSession, page_id: int, images: List[Dict]):
    """Save images."""
    try:
        await session.execute(text("DELETE FROM images WHERE page_id = :pid"), {"pid": page_id})
        for img in images:
            await session.execute(
                text("INSERT INTO images (page_id, url, alt_text) VALUES (:pid, :url, :alt)"),
                {"pid": page_id, "url": img["url"], "alt": img["alt"]},
            )
    except Exception as e:
        print(f"⚠️  Image save error: {e}")

async def register_site(session: AsyncSession, domain: str, site_base: str) -> int:
    """Register site if not exists."""
    try:
        result = await session.execute(
            text("SELECT id FROM sites WHERE domain = :d"), {"d": domain}
        )
        row = result.fetchone()
        if row:
            return row.id
        
        result = await session.execute(
            text("INSERT INTO sites (domain) VALUES (:d) RETURNING id"), {"d": domain}
        )
        return result.scalar()
    except Exception as e:
        print(f"⚠️  Site registration error: {e}")
        raise

async def crawl_recursive(
    start_url: str,
    max_pages: int = 100,
    max_depth: int = 3,
    concurrency: int = 5,
    recrawl_days: int = 7,
):
    """Advanced recursive crawler with tracker detection."""
    domain = urlparse(start_url).netloc
    base = f"{urlparse(start_url).scheme}://{domain}"
    
    stats = CrawlStats()
    semaphore = asyncio.Semaphore(concurrency)
    
    headers = {"User-Agent": USER_AGENT}
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        # Parse robots
        rules, sitemaps = await parse_robots(client, base)
        effective_delay = rules.crawl_delay or CRAWL_DELAY
        
        print(f"[*] Crawl delay: {effective_delay}s")
        print(f"[*] Features: Tracker Detection")
        
        # Seed from sitemap
        seeds = [normalize_url(start_url)]
        if sitemaps:
            sitemap_urls = await parse_sitemap_urls(client, sitemaps[0])
            for u in sitemap_urls:
                if urlparse(u).netloc == domain:
                    seeds.append(normalize_url(u))
        
        # Queue: (url, depth)
        queue: List[tuple[str, int]] = [(u, 0) for u in seeds]
        seen: Set[str] = set(seeds)
        
        # Check last crawl times (recrawl control)
        async with AsyncSession(engine) as session:
            try:
                cutoff = datetime.now() - timedelta(days=recrawl_days)
                result = await session.execute(
                    text("SELECT url FROM pages WHERE last_crawled_at > :cutoff"),
                    {"cutoff": cutoff},
                )
                recent_urls = {normalize_url(r[0]) for r in result.fetchall()}
            except Exception as e:
                print(f"⚠️  Recrawl check error: {e}")
                recent_urls = set()
        
        async def crawl_one(url: str, depth: int):
            async with semaphore:
                stats.total_attempted += 1
                
                try:
                    # Rate limiting
                    await asyncio.sleep(effective_delay)
                    
                    # Robots check
                    path = urlparse(url).path or "/"
                    if not rules.is_allowed(path):
                        stats.total_skipped += 1
                        print(f"[SKIP] Robots.txt: {url}")
                        return []
                    
                    # Recrawl check
                    if normalize_url(url) in recent_urls:
                        stats.total_skipped += 1
                        return []
                    
                    resp = await fetch_with_retry(client, url)
                    if not resp:
                        stats.total_failed += 1
                        print(f"[FAIL] {url}")
                        return []
                    
                    # Content-Type check
                    content_type = resp.headers.get("content-type", "")
                    if "text/html" not in content_type:
                        stats.total_skipped += 1
                        return []
                    
                    # Charset detection
                    charset = detect_charset(resp.content)
                    try:
                        html = resp.content.decode(charset, errors="ignore")
                    except Exception:
                        html = resp.text
                    
                    soup = BeautifulSoup(html, "lxml")
                    metadata = extract_metadata(soup, url)
                    
                    # Detect trackers
                    tracker_result = detect_trackers(html, url)
                    tracker_risk_score = tracker_result.get('tracker_risk_score', 0.5)
                    
                    # Save to DB
                    async with AsyncSession(engine) as session:
                        async with session.begin():
                            site_id = await register_site(session, domain, base)
                            page_id = await upsert_page(session, site_id, url, metadata, tracker_risk_score)
                            await save_images(session, page_id, metadata["images"])
                    
                    stats.total_success += 1
                    print(f"[OK] {stats.total_success}/{max_pages} (depth={depth}) {url} | Trackers: {tracker_result.get('tracker_count', 0)} | Risk: {tracker_result.get('risk_profile', 'unknown')}")
                    
                    # Extract links for next level
                    new_links = []
                    if depth < max_depth:
                        for link, is_same in metadata["links"]:
                            norm = normalize_url(link)
                            if norm not in seen and is_valid_url(norm):
                                if is_same:
                                    new_links.append((norm, depth + 1))
                                seen.add(norm)
                    
                    return new_links
                except Exception as e:
                    stats.total_failed += 1
                    print(f"[ERROR] {url}: {e}")
                    return []
        
        while queue and stats.total_success < max_pages:
            batch = []
            while queue and len(batch) < concurrency and stats.total_success + len(batch) < max_pages:
                batch.append(queue.pop(0))
            
            tasks = [crawl_one(url, depth) for url, depth in batch]
            results = await asyncio.gather(*tasks)
            
            # Enqueue new links
            for links in results:
                queue.extend(links)
        
        print(f"\n[DONE] Attempted={stats.total_attempted}, Success={stats.total_success}, Failed={stats.total_failed}, Skipped={stats.total_skipped}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python advanced_crawler.py <start_url> [max_pages] [max_depth] [concurrency]")
        sys.exit(1)
    
    start = sys.argv[1]
    max_pages = int(sys.argv[2]) if len(sys.argv) >= 3 else 100
    max_depth = int(sys.argv[3]) if len(sys.argv) >= 4 else 3
    concurrency = int(sys.argv[4]) if len(sys.argv) >= 5 else 5
    
    asyncio.run(crawl_recursive(start, max_pages=max_pages, max_depth=max_depth, concurrency=concurrency))
