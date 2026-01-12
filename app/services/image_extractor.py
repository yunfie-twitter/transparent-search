"""Extract images and favicons from HTML content."""
import logging
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser
import re

logger = logging.getLogger(__name__)


class ImageExtractor(HTMLParser):
    """Extract image tags and metadata from HTML."""
    
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.images: List[Dict[str, any]] = []
        self.position_index = 0
    
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]):
        if tag == "img":
            attrs_dict = dict(attrs)
            
            # Extract required fields
            src = attrs_dict.get("src", "")
            alt = attrs_dict.get("alt", "").strip()
            title = attrs_dict.get("title", "").strip()
            
            # Skip data URIs and empty sources
            if not src or src.startswith("data:"):
                return
            
            # Convert relative URLs to absolute
            try:
                image_url = urljoin(self.base_url, src)
            except Exception as e:
                logger.warning(f"Failed to resolve image URL: {src} - {e}")
                return
            
            # Extract dimensions if available
            width = None
            height = None
            try:
                if "width" in attrs_dict:
                    width = int(attrs_dict["width"])
                if "height" in attrs_dict:
                    height = int(attrs_dict["height"])
            except (ValueError, TypeError):
                pass
            
            # Check for responsive image indicators
            is_responsive = bool(
                attrs_dict.get("srcset") or 
                attrs_dict.get("sizes") or
                "responsive" in attrs_dict.get("class", "").lower()
            )
            
            image_data = {
                "url": image_url,
                "alt_text": alt,
                "title": title,
                "width": width,
                "height": height,
                "is_responsive": is_responsive,
                "position_index": self.position_index,
                "has_alt": bool(alt),  # For ALT-based search filtering
            }
            
            self.images.append(image_data)
            self.position_index += 1
    
    def get_images(self) -> List[Dict[str, any]]:
        """Get extracted images."""
        return self.images
    
    def get_images_with_alt(self) -> List[Dict[str, any]]:
        """Get only images with ALT text (searchable images)."""
        return [img for img in self.images if img["has_alt"]]


class FaviconExtractor(HTMLParser):
    """Extract favicon URL from HTML head."""
    
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.favicons: List[Dict[str, str]] = []
        self.in_head = False
    
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]):
        if tag == "head":
            self.in_head = True
        elif tag == "link" and self.in_head:
            attrs_dict = dict(attrs)
            rel = attrs_dict.get("rel", "").lower()
            
            # Look for favicon links
            if any(x in rel for x in ["icon", "shortcut", "apple-touch"]):
                href = attrs_dict.get("href", "")
                if href and not href.startswith("data:"):
                    try:
                        favicon_url = urljoin(self.base_url, href)
                        
                        # Extract format
                        favicon_format = None
                        if favicon_url.lower().endswith(".ico"):
                            favicon_format = "ico"
                        elif favicon_url.lower().endswith(".png"):
                            favicon_format = "png"
                        elif favicon_url.lower().endswith(".jpg"):
                            favicon_format = "jpg"
                        elif favicon_url.lower().endswith(".svg"):
                            favicon_format = "svg"
                        
                        # Extract size from sizes attribute
                        sizes = attrs_dict.get("sizes", "")
                        
                        favicon_data = {
                            "url": favicon_url,
                            "format": favicon_format,
                            "size": sizes if sizes else None,
                            "rel": rel,
                        }
                        
                        self.favicons.append(favicon_data)
                    except Exception as e:
                        logger.warning(f"Failed to resolve favicon URL: {href} - {e}")
    
    def handle_endtag(self, tag: str):
        if tag == "head":
            self.in_head = False
    
    def get_favicons(self) -> List[Dict[str, str]]:
        """Get extracted favicons."""
        return self.favicons
    
    def get_best_favicon(self) -> Optional[Dict[str, str]]:
        """Get the best favicon (priority: png > svg > ico > jpg)."""
        if not self.favicons:
            # Fallback: check common favicon paths
            return self._try_common_favicon_paths()
        
        # Priority order
        priority = {"png": 1, "svg": 2, "ico": 3, "jpg": 4}
        
        return sorted(
            self.favicons,
            key=lambda x: priority.get(x.get("format"), 99)
        )[0]
    
    def _try_common_favicon_paths(self) -> Optional[Dict[str, str]]:
        """Try to construct favicon URL from domain root."""
        try:
            parsed = urlparse(self.base_url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            
            # Common favicon locations (in priority order)
            common_paths = [
                "/favicon.ico",
                "/favicon.png",
                "/favicon.svg",
            ]
            
            for path in common_paths:
                favicon_url = domain + path
                # Return the first one (assume exists, validation happens later)
                return {
                    "url": favicon_url,
                    "format": path.split(".")[-1],
                    "size": None,
                    "rel": "icon",
                }
        except Exception as e:
            logger.warning(f"Failed to construct favicon URL: {e}")
        
        return None


class AssetExtractor:
    """Combined image and favicon extraction."""
    
    @staticmethod
    def extract_images(
        html_content: str,
        base_url: str,
        min_alt_length: int = 3,
    ) -> Tuple[List[Dict], int]:
        """Extract images from HTML.
        
        Args:
            html_content: HTML content string
            base_url: Base URL for relative URL resolution
            min_alt_length: Minimum ALT text length to consider
        
        Returns:
            Tuple of (images list, images_with_alt count)
        """
        try:
            extractor = ImageExtractor(base_url)
            extractor.feed(html_content)
            
            images = extractor.get_images()
            
            # Filter out images with very short ALT text
            images_with_meaningful_alt = [
                img for img in images
                if img["has_alt"] and len(img["alt_text"]) >= min_alt_length
            ]
            
            logger.debug(f"Extracted {len(images)} images, "
                        f"{len(images_with_meaningful_alt)} with meaningful ALT")
            
            return images, len(images_with_meaningful_alt)
        
        except Exception as e:
            logger.error(f"Image extraction failed: {e}")
            return [], 0
    
    @staticmethod
    def extract_favicon(
        html_content: str,
        base_url: str,
    ) -> Optional[Dict[str, str]]:
        """Extract favicon from HTML.
        
        Args:
            html_content: HTML content string
            base_url: Base URL for relative URL resolution
        
        Returns:
            Favicon data dict or None
        """
        try:
            extractor = FaviconExtractor(base_url)
            extractor.feed(html_content)
            
            favicon = extractor.get_best_favicon()
            
            if favicon:
                logger.debug(f"Extracted favicon: {favicon['url']}")
            else:
                logger.debug("No favicon found")
            
            return favicon
        
        except Exception as e:
            logger.error(f"Favicon extraction failed: {e}")
            return None
