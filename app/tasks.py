import asyncio
from .advanced_crawler import crawl_recursive

async def crawl_domain_task(ctx, url: str, max_pages: int = 100, max_depth: int = 3):
    """
    Arq task wrapper for the crawler.
    In a real distributed system, this would break down into smaller page-level tasks.
    For now, it runs the async recursive crawler within the worker process.
    """
    print(f"[Worker] Starting crawl for {url}")
    await crawl_recursive(url, max_pages=max_pages, max_depth=max_depth, concurrency=5)
    print(f"[Worker] Finished crawl for {url}")
