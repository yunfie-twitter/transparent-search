import asyncio
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from urllib.parse import urlparse, urljoin
import os
import sys

# DB Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/search_engine")
engine = create_async_engine(DATABASE_URL, echo=False)

async def get_favicon_url(base_url, soup, client):
    """Attempt to find favicon URL from HTML link tags or default location."""
    # 1. Check link tags
    icon_link = soup.find("link", rel=lambda x: x and 'icon' in x.lower().split())
    if icon_link and icon_link.get("href"):
        return urljoin(base_url, icon_link.get("href"))
    
    # 2. Check default location (HEAD request)
    default_favicon = urljoin(base_url, "/favicon.ico")
    try:
        resp = await client.head(default_favicon, timeout=2.0)
        if resp.status_code == 200:
            return default_favicon
    except:
        pass
    
    return None

async def register_site(session, domain, base_url, soup, client):
    """Register new site and fetch favicon if it doesn't exist."""
    # Check if exists
    result = await session.execute(
        text("SELECT id FROM sites WHERE domain = :domain"), 
        {"domain": domain}
    )
    site = result.fetchone()
    
    if site:
        return site.id
    
    # New Site: Fetch Favicon
    print(f"[*] New site detected: {domain}. Fetching favicon...")
    favicon_url = await get_favicon_url(base_url, soup, client)
    
    # Insert
    result = await session.execute(
        text("INSERT INTO sites (domain, favicon_url) VALUES (:domain, :url) RETURNING id"),
        {"domain": domain, "url": favicon_url}
    )
    new_site_id = result.scalar()
    print(f"[+] Site registered: {domain} (Favicon: {favicon_url})")
    return new_site_id

async def save_images(session, page_id, base_url, soup):
    """Extract and save images from the page."""
    images = soup.find_all('img')
    count = 0
    for img in images:
        src = img.get('src')
        if not src:
            continue
            
        abs_url = urljoin(base_url, src)
        alt = img.get('alt', '')[:255] # Limit alt text length
        
        await session.execute(
            text("INSERT INTO images (page_id, url, alt_text) VALUES (:pid, :url, :alt)"),
            {"pid": page_id, "url": abs_url, "alt": alt}
        )
        count += 1
    
    if count > 0:
        print(f"[+] Linked {count} images to page {page_id}")

async def crawl_page(url):
    print(f"[*] Crawling: {url}")
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
        except Exception as e:
            print(f"[!] Failed to fetch {url}: {e}")
            return

        soup = BeautifulSoup(resp.content, "lxml")
        title = soup.title.string if soup.title else url
        # Remove script/style elements for cleaner content
        for script in soup(["script", "style"]):
            script.decompose()
        content = soup.get_text(separator=' ', strip=True)

        async with AsyncSession(engine) as session:
            async with session.begin():
                # 1. Site Registration
                site_id = await register_site(session, domain, base_url, soup, client)

                # 2. Page Registration (Upsert)
                # Note: Using INSERT ... ON CONFLICT for simplicity
                result = await session.execute(
                    text("""
                        INSERT INTO pages (url, title, content, site_id, last_crawled_at) 
                        VALUES (:url, :title, :content, :site_id, NOW())
                        ON CONFLICT (url) DO UPDATE 
                        SET title = EXCLUDED.title, 
                            content = EXCLUDED.content,
                            site_id = EXCLUDED.site_id,
                            last_crawled_at = NOW()
                        RETURNING id
                    """),
                    {"url": url, "title": title, "content": content, "site_id": site_id}
                )
                page_id = result.scalar()
                
                # 3. Image Linking
                # Clear old images first (simple strategy for re-crawl)
                await session.execute(
                    text("DELETE FROM images WHERE page_id = :pid"),
                    {"pid": page_id}
                )
                await save_images(session, page_id, url, soup)
                
            print(f"[SUCCESS] Processed: {title}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python crawler.py <url>")
        sys.exit(1)
    
    target_url = sys.argv[1]
    asyncio.run(crawl_page(target_url))
