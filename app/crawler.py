import asyncio
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# DB Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/search_engine"
)
engine = create_async_engine(DATABASE_URL, echo=False)

USER_AGENT = os.getenv("CRAWLER_UA", "TransparentSearchBot/0.1")

@dataclass
class RobotsRules:
    disallow: list[str]
    allow: list[str]

    def is_allowed(self, path: str) -> bool:
        # Minimal robots.txt evaluator: longest-match wins (simple approximation)
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

async def fetch_text(client: httpx.AsyncClient, url: str, timeout: float = 10.0) -> Optional[str]:
    try:
        r = await client.get(url, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception:
        return None

def extract_domain(url: str) -> str:
    return urlparse(url).netloc

def base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"

async def get_favicon_url(base: str, soup: BeautifulSoup, client: httpx.AsyncClient) -> Optional[str]:
    icon_link = soup.find("link", rel=lambda x: x and "icon" in x.lower())
    if icon_link and icon_link.get("href"):
        return urljoin(base, icon_link.get("href"))

    default_favicon = urljoin(base, "/favicon.ico")
    try:
        resp = await client.head(default_favicon, timeout=2.0)
        if resp.status_code == 200:
            return default_favicon
    except Exception:
        pass

    return None

def extract_ogp(soup: BeautifulSoup) -> dict:
    def m(prop: str) -> Optional[str]:
        tag = soup.find("meta", property=prop)
        return tag.get("content") if tag and tag.get("content") else None

    return {
        "og_title": m("og:title"),
        "og_description": m("og:description"),
        "og_image_url": m("og:image"),
    }

def extract_jsonld(soup: BeautifulSoup) -> Optional[list]:
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    items = []
    for s in scripts:
        if not s.string:
            continue
        try:
            items.append(json.loads(s.string))
        except Exception:
            continue
    return items or None

async def parse_robots(client: httpx.AsyncClient, site_base: str) -> tuple[RobotsRules, list[str]]:
    # returns (rules, sitemaps)
    robots_url = urljoin(site_base, "/robots.txt")
    text_body = await fetch_text(client, robots_url, timeout=5.0)
    disallow: list[str] = []
    allow: list[str] = []
    sitemaps: list[str] = []

    if not text_body:
        return RobotsRules(disallow=disallow, allow=allow), sitemaps

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

        # only respect UA="*" (minimal)
        if current_ua not in ("*", None):
            continue

        if k == "disallow":
            disallow.append(v or "/")
        elif k == "allow":
            allow.append(v)
        elif k == "sitemap":
            sitemaps.append(v)

    return RobotsRules(disallow=disallow, allow=allow), sitemaps

async def parse_sitemap_urls(client: httpx.AsyncClient, sitemap_url: str, limit: int = 2000) -> list[str]:
    body = await fetch_text(client, sitemap_url, timeout=10.0)
    if not body:
        return []

    try:
        root = ET.fromstring(body.encode("utf-8"))
    except Exception:
        return []

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    urls: list[str] = []

    # sitemapindex
    if root.tag.endswith("sitemapindex"):
        for sm in root.findall(f"{ns}sitemap"):
            loc = sm.find(f"{ns}loc")
            if loc is not None and loc.text:
                urls.extend(await parse_sitemap_urls(client, loc.text.strip(), limit=limit))
                if len(urls) >= limit:
                    return urls[:limit]
        return urls[:limit]

    # urlset
    for u in root.findall(f"{ns}url"):
        loc = u.find(f"{ns}loc")
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
        if len(urls) >= limit:
            break

    return urls

async def register_site(session: AsyncSession, domain: str, site_base: str, soup: BeautifulSoup, client: httpx.AsyncClient) -> int:
    result = await session.execute(text("SELECT id, favicon_url, robots_txt_url, sitemap_url FROM sites WHERE domain = :d"), {"d": domain})
    row = result.fetchone()
    if row:
        return row.id

    favicon_url = await get_favicon_url(site_base, soup, client)
    robots_url = urljoin(site_base, "/robots.txt")

    # try robots->sitemap, else /sitemap.xml
    rules, sitemaps = await parse_robots(client, site_base)
    sitemap = sitemaps[0] if sitemaps else urljoin(site_base, "/sitemap.xml")

    result = await session.execute(
        text(
            "INSERT INTO sites (domain, favicon_url, robots_txt_url, sitemap_url) VALUES (:d, :f, :r, :s) RETURNING id"
        ),
        {"d": domain, "f": favicon_url, "r": robots_url, "s": sitemap},
    )
    return result.scalar()

async def save_images(session: AsyncSession, page_id: int, page_url: str, soup: BeautifulSoup) -> int:
    images = soup.find_all("img")
    count = 0
    for img in images:
        src = img.get("src")
        if not src:
            continue
        abs_url = urljoin(page_url, src)
        alt = (img.get("alt") or "")[:255]
        await session.execute(
            text("INSERT INTO images (page_id, url, alt_text) VALUES (:pid, :u, :a)"),
            {"pid": page_id, "u": abs_url, "a": alt},
        )
        count += 1
    return count

def extract_links(page_url: str, soup: BeautifulSoup, same_domain: str) -> list[str]:
    urls: list[str] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        u = urljoin(page_url, href)
        pu = urlparse(u)
        if pu.scheme not in ("http", "https"):
            continue
        if pu.netloc != same_domain:
            continue
        # strip fragment
        u = u.split("#", 1)[0]
        urls.append(u)
    return urls

async def crawl_one(url: str, client: httpx.AsyncClient, rules: RobotsRules, domain: str) -> tuple[str, Optional[dict], list[str]]:
    p = urlparse(url)
    if not rules.is_allowed(p.path or "/"):
        return url, None, []

    try:
        resp = await client.get(url, timeout=15.0)
        resp.raise_for_status()
    except Exception:
        return url, None, []

    soup = BeautifulSoup(resp.content, "lxml")

    title = soup.title.string.strip() if soup.title and soup.title.string else url
    for script in soup(["script", "style"]):
        script.decompose()
    content = soup.get_text(separator=" ", strip=True)

    og = extract_ogp(soup)
    jsonld = extract_jsonld(soup)

    out_links = extract_links(url, soup, domain)

    return url, {
        "title": title,
        "content": content,
        **og,
        "jsonld": jsonld,
        "soup": soup,
    }, out_links

async def upsert_page(session: AsyncSession, site_id: int, url: str, payload: dict) -> int:
    result = await session.execute(
        text(
            """
            INSERT INTO pages (url, title, content, site_id, og_title, og_description, og_image_url, jsonld, last_crawled_at)
            VALUES (:url, :title, :content, :site_id, :og_title, :og_description, :og_image_url, :jsonld, NOW())
            ON CONFLICT (url) DO UPDATE
            SET title = EXCLUDED.title,
                content = EXCLUDED.content,
                site_id = EXCLUDED.site_id,
                og_title = EXCLUDED.og_title,
                og_description = EXCLUDED.og_description,
                og_image_url = EXCLUDED.og_image_url,
                jsonld = EXCLUDED.jsonld,
                last_crawled_at = NOW()
            RETURNING id
            """
        ),
        {
            "url": url,
            "title": payload.get("title"),
            "content": payload.get("content"),
            "site_id": site_id,
            "og_title": payload.get("og_title"),
            "og_description": payload.get("og_description"),
            "og_image_url": payload.get("og_image_url"),
            "jsonld": json.dumps(payload.get("jsonld")) if payload.get("jsonld") is not None else None,
        },
    )
    return result.scalar()

async def crawl_site(start_url: str, max_pages: int = 100, concurrency: int = 10):
    dom = extract_domain(start_url)
    base = base_url(start_url)

    headers = {"User-Agent": USER_AGENT}
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
        rules, sitemaps = await parse_robots(client, base)

        # sitemap seed
        seeds = [start_url]
        sitemap_url = sitemaps[0] if sitemaps else urljoin(base, "/sitemap.xml")
        sitemap_urls = await parse_sitemap_urls(client, sitemap_url)
        if sitemap_urls:
            seeds = list(dict.fromkeys(sitemap_urls + seeds))

        queue: list[str] = []
        seen: set[str] = set()
        for u in seeds:
            if extract_domain(u) != dom:
                continue
            if u not in seen:
                queue.append(u)
                seen.add(u)

        processed = 0

        while queue and processed < max_pages:
            batch = []
            while queue and len(batch) < concurrency and processed + len(batch) < max_pages:
                batch.append(queue.pop(0))

            async def runner(u: str):
                async with semaphore:
                    return await crawl_one(u, client, rules, dom)

            results = await asyncio.gather(*[runner(u) for u in batch])

            async with AsyncSession(engine) as session:
                async with session.begin():
                    # register site on first success
                    site_id: Optional[int] = None

                    for url, payload, out_links in results:
                        if payload is None:
                            continue

                        if site_id is None:
                            site_id = await register_site(session, dom, base, payload["soup"], client)

                        page_id = await upsert_page(session, site_id, url, payload)

                        # refresh images
                        await session.execute(text("DELETE FROM images WHERE page_id = :pid"), {"pid": page_id})
                        img_count = await save_images(session, page_id, url, payload["soup"])

                        # enqueue discovered links
                        for link in out_links:
                            if link not in seen:
                                queue.append(link)
                                seen.add(link)

                        processed += 1
                        print(f"[OK] {processed}/{max_pages} {url} (images={img_count})")

        print(f"[DONE] crawled={processed}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python crawler.py <start_url> [max_pages] [concurrency]")
        sys.exit(1)

    start = sys.argv[1]
    max_pages = int(sys.argv[2]) if len(sys.argv) >= 3 else 100
    concurrency = int(sys.argv[3]) if len(sys.argv) >= 4 else 10

    asyncio.run(crawl_site(start, max_pages=max_pages, concurrency=concurrency))
