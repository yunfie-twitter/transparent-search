# Router modules
"""All router modules for the application."""

from app.routers import search
from app.routers import advanced_search
from app.routers import admin
from app.routers import admin_crawl
from app.routers import admin_index
from app.routers import analytics
from app.routers import click
from app.routers import images
from app.routers import sitemap_admin
from app.routers import suggest

__all__ = [
    "search",
    "advanced_search",
    "admin",
    "admin_crawl",
    "admin_index",
    "analytics",
    "click",
    "images",
    "sitemap_admin",
    "suggest",
]
