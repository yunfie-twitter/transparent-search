"""JavaScript rendering using Playwright for dynamic content."""
import asyncio
from typing import Optional, Dict, Tuple
import logging

try:
    from playwright.async_api import async_playwright, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️  Playwright not installed. Install with: pip install playwright && playwright install")

logger = logging.getLogger(__name__)

class JSRenderer:
    """Renders JavaScript-heavy pages using Playwright."""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.timeout = 30000  # 30 seconds
    
    async def initialize(self):
        """Initialize Playwright browser."""
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("⚠️  Playwright not available")
            return False
        
        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage"]  # Prevent OOM in containers
            )
            logger.info("✅ Playwright browser initialized")
            return True
        except Exception as e:
            logger.error(f"⚠️  Failed to initialize Playwright: {e}")
            return False
    
    async def render(
        self,
        url: str,
        wait_for_selector: Optional[str] = None,
        wait_for_timeout: int = 5000
    ) -> Optional[str]:
        """Render page with JavaScript and return HTML.
        
        Args:
            url: Page URL
            wait_for_selector: CSS selector to wait for (optional)
            wait_for_timeout: Timeout in milliseconds
        
        Returns:
            Rendered HTML content, or None if failed
        """
        if not self.browser:
            return None
        
        page = None
        try:
            context = await self.browser.new_context(
                user_agent="TransparentSearchBot/1.0 (+https://example.com/bot)"
            )
            page = await context.new_page()
            
            # Disable image/stylesheet loading for speed
            await page.route("**/*.{png,jpg,jpeg,gif,webp,svg}", lambda route: route.abort())
            
            # Navigate to page
            await page.goto(url, wait_until="networkidle", timeout=self.timeout)
            
            # Wait for specific selector if provided
            if wait_for_selector:
                try:
                    await page.wait_for_selector(wait_for_selector, timeout=wait_for_timeout)
                except Exception as e:
                    logger.warning(f"⚠️  Selector wait timeout for {url}: {e}")
            
            # Get rendered HTML
            html = await page.content()
            
            await context.close()
            logger.info(f"✅ Successfully rendered {url}")
            return html
        
        except Exception as e:
            logger.error(f"⚠️  Rendering error for {url}: {e}")
            return None
        
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
    
    async def render_with_screenshots(
        self,
        url: str,
        screenshot_path: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Render page and take screenshot.
        
        Args:
            url: Page URL
            screenshot_path: Path to save screenshot
        
        Returns:
            Tuple of (html_content, screenshot_path) or (None, None) if failed
        """
        if not self.browser:
            return None, None
        
        page = None
        try:
            context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="TransparentSearchBot/1.0 (+https://example.com/bot)"
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="networkidle", timeout=self.timeout)
            
            # Take screenshot
            await page.screenshot(path=screenshot_path, full_page=True)
            
            # Get HTML
            html = await page.content()
            
            await context.close()
            return html, screenshot_path
        
        except Exception as e:
            logger.error(f"⚠️  Rendering with screenshot failed for {url}: {e}")
            return None, None
        
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
    
    async def extract_data(
        self,
        url: str,
        script: str
    ) -> Optional[Dict]:
        """Execute JavaScript on page and extract data.
        
        Args:
            url: Page URL
            script: JavaScript to execute (should return JSON-serializable object)
        
        Returns:
            Extracted data or None if failed
        """
        if not self.browser:
            return None
        
        page = None
        try:
            context = await self.browser.new_context()
            page = await context.new_page()
            
            await page.goto(url, wait_until="networkidle", timeout=self.timeout)
            
            # Execute script
            data = await page.evaluate(script)
            
            await context.close()
            return data
        
        except Exception as e:
            logger.error(f"⚠️  Data extraction failed for {url}: {e}")
            return None
        
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
    
    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
            logger.info("✅ Playwright browser closed")

# Global instance
js_renderer = JSRenderer()
