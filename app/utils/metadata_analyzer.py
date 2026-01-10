"""Advanced metadata and structured data analysis."""
import json
from typing import Dict, List, Any, Tuple, Optional
from urllib.parse import urljoin, urlparse
import re
from bs4 import BeautifulSoup
from datetime import datetime

class MetadataAnalyzer:
    """Analyzes page metadata, structured data, and link graphs."""
    
    # Schema.org structured data types
    SCHEMA_TYPES = {
        "Article", "BlogPosting", "NewsArticle",
        "Product", "Offer",
        "Event",
        "Organization", "LocalBusiness",
        "Person",
        "BreadcrumbList",
        "FAQPage",
        "HowTo",
        "VideoObject",
    }
    
    # Open Graph properties
    OG_PROPERTIES = {
        "title", "description", "image", "url",
        "type", "site_name", "published_time", "modified_time",
        "author", "section", "tag",
    }
    
    @staticmethod
    def extract_metadata(html: str, url: str) -> Dict[str, Any]:
        """
        Extract comprehensive metadata from HTML.
        
        Returns:
            Dict with metadata, structured data, and link information
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            metadata = {
                "url": url,
                "title": MetadataAnalyzer._extract_title(soup),
                "description": MetadataAnalyzer._extract_meta_description(soup),
                "og_data": MetadataAnalyzer._extract_open_graph(soup),
                "twitter_data": MetadataAnalyzer._extract_twitter_card(soup),
                "canonical_url": MetadataAnalyzer._extract_canonical(soup, url),
                "robots": MetadataAnalyzer._extract_robots(soup),
                "language": MetadataAnalyzer._extract_language(soup),
                "structured_data": MetadataAnalyzer._extract_structured_data(soup),
                "headings": MetadataAnalyzer._extract_headings(soup),
                "publish_date": MetadataAnalyzer._extract_publish_date(soup),
                "modified_date": MetadataAnalyzer._extract_modified_date(soup),
                "author": MetadataAnalyzer._extract_author(soup),
                "keywords": MetadataAnalyzer._extract_keywords(soup),
                "links": MetadataAnalyzer._extract_links(soup, url),
                "images": MetadataAnalyzer._extract_images(soup, url),
            }
            
            return metadata
        
        except Exception as e:
            print(f"⚠️ Metadata extraction error: {e}")
            return {"url": url, "error": str(e)}
    
    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> Optional[str]:
        """Extract page title."""
        # Try og:title first
        og_title = soup.find("meta", {"property": "og:title"})
        if og_title and og_title.get("content"):
            return og_title["content"]
        
        # Fall back to <title> tag
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)
        
        return None
    
    @staticmethod
    def _extract_meta_description(soup: BeautifulSoup) -> Optional[str]:
        """Extract meta description."""
        # Try og:description
        og_desc = soup.find("meta", {"property": "og:description"})
        if og_desc and og_desc.get("content"):
            return og_desc["content"]
        
        # Fall back to description meta tag
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return meta_desc["content"]
        
        return None
    
    @staticmethod
    def _extract_open_graph(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Open Graph metadata."""
        og_data = {}
        
        for og_meta in soup.find_all("meta", {"property": re.compile("^og:")}):
            prop = og_meta.get("property", "").replace("og:", "")
            content = og_meta.get("content")
            if prop and content:
                og_data[prop] = content
        
        return og_data
    
    @staticmethod
    def _extract_twitter_card(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Twitter Card metadata."""
        twitter_data = {}
        
        for twitter_meta in soup.find_all("meta", {"name": re.compile("^twitter:")}):
            name = twitter_meta.get("name", "").replace("twitter:", "")
            content = twitter_meta.get("content")
            if name and content:
                twitter_data[name] = content
        
        return twitter_data
    
    @staticmethod
    def _extract_canonical(soup: BeautifulSoup, url: str) -> Optional[str]:
        """Extract canonical URL."""
        canonical = soup.find("link", {"rel": "canonical"})
        if canonical and canonical.get("href"):
            return canonical["href"]
        return None
    
    @staticmethod
    def _extract_robots(soup: BeautifulSoup) -> Dict[str, bool]:
        """Extract robots directives."""
        robots_meta = soup.find("meta", {"name": "robots"})
        directives = {
            "index": True,
            "follow": True,
            "archive": True,
            "snippet": True,
        }
        
        if robots_meta and robots_meta.get("content"):
            content = robots_meta["content"].lower()
            directives["index"] = "noindex" not in content
            directives["follow"] = "nofollow" not in content
            directives["archive"] = "noarchive" not in content
            directives["snippet"] = "nosnippet" not in content
        
        return directives
    
    @staticmethod
    def _extract_language(soup: BeautifulSoup) -> Optional[str]:
        """Extract language."""
        # Try html lang attribute
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            return html_tag["lang"]
        
        # Try meta lang
        meta_lang = soup.find("meta", {"http-equiv": "Content-Language"})
        if meta_lang and meta_lang.get("content"):
            return meta_lang["content"]
        
        return None
    
    @staticmethod
    def _extract_structured_data(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract JSON-LD structured data."""
        structured_data = []
        
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(script.string)
                # Flatten @context if array
                if isinstance(data, dict):
                    structured_data.append(data)
                elif isinstance(data, list):
                    structured_data.extend(data)
            except json.JSONDecodeError:
                continue
        
        return structured_data
    
    @staticmethod
    def _extract_headings(soup: BeautifulSoup) -> Dict[str, List[str]]:
        """Extract heading hierarchy."""
        headings = {
            "h1": [],
            "h2": [],
            "h3": [],
        }
        
        for h1 in soup.find_all("h1"):
            text = h1.get_text(strip=True)
            if text:
                headings["h1"].append(text)
        
        for h2 in soup.find_all("h2"):
            text = h2.get_text(strip=True)
            if text:
                headings["h2"].append(text)
        
        for h3 in soup.find_all("h3"):
            text = h3.get_text(strip=True)
            if text:
                headings["h3"].append(text)
        
        return headings
    
    @staticmethod
    def _extract_publish_date(soup: BeautifulSoup) -> Optional[str]:
        """Extract publish date."""
        # Try og:published_time
        og_date = soup.find("meta", {"property": "og:published_time"})
        if og_date and og_date.get("content"):
            return og_date["content"]
        
        # Try article:published_time
        article_date = soup.find("meta", {"property": "article:published_time"})
        if article_date and article_date.get("content"):
            return article_date["content"]
        
        # Try datePublished in structured data
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and "datePublished" in data:
                    return data["datePublished"]
            except:
                continue
        
        return None
    
    @staticmethod
    def _extract_modified_date(soup: BeautifulSoup) -> Optional[str]:
        """Extract last modified date."""
        # Try og:modified_time
        og_date = soup.find("meta", {"property": "og:modified_time"})
        if og_date and og_date.get("content"):
            return og_date["content"]
        
        # Try dateModified in structured data
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and "dateModified" in data:
                    return data["dateModified"]
            except:
                continue
        
        return None
    
    @staticmethod
    def _extract_author(soup: BeautifulSoup) -> Optional[str]:
        """Extract author information."""
        # Try article:author
        article_author = soup.find("meta", {"property": "article:author"})
        if article_author and article_author.get("content"):
            return article_author["content"]
        
        # Try author meta tag
        author_meta = soup.find("meta", {"name": "author"})
        if author_meta and author_meta.get("content"):
            return author_meta["content"]
        
        # Try author in structured data
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and "author" in data:
                    author = data["author"]
                    if isinstance(author, dict) and "name" in author:
                        return author["name"]
                    elif isinstance(author, str):
                        return author
            except:
                continue
        
        return None
    
    @staticmethod
    def _extract_keywords(soup: BeautifulSoup) -> List[str]:
        """Extract keywords."""
        keywords = []
        
        # Try keywords meta tag
        keywords_meta = soup.find("meta", {"name": "keywords"})
        if keywords_meta and keywords_meta.get("content"):
            keywords = [k.strip() for k in keywords_meta["content"].split(",")]
        
        # Try article:tag
        for tag_meta in soup.find_all("meta", {"property": "article:tag"}):
            if tag_meta.get("content"):
                keywords.append(tag_meta["content"])
        
        return list(set(keywords))  # Remove duplicates
    
    @staticmethod
    def _extract_links(soup: BeautifulSoup, base_url: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract internal and external links with context.
        
        Returns:
            Dict with "internal" and "external" link lists
        """
        internal_links = []
        external_links = []
        
        base_domain = urlparse(base_url).netloc
        
        for link in soup.find_all("a", {"href": True}):
            href = link["href"]
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            
            # Normalize URL
            if href.startswith(("/", "http")):
                full_url = urljoin(base_url, href) if not href.startswith("http") else href
            else:
                full_url = urljoin(base_url, href)
            
            link_domain = urlparse(full_url).netloc
            anchor_text = link.get_text(strip=True)[:100]  # Limit to 100 chars
            
            link_data = {
                "url": full_url,
                "text": anchor_text,
                "title": link.get("title", ""),
                "rel": link.get("rel", []) if link.get("rel") else [],
            }
            
            if link_domain == base_domain:
                internal_links.append(link_data)
            else:
                external_links.append(link_data)
        
        return {
            "internal": internal_links,
            "external": external_links,
        }
    
    @staticmethod
    def _extract_images(soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        """Extract image information."""
        images = []
        
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src:
                continue
            
            full_url = urljoin(base_url, src)
            
            images.append({
                "src": full_url,
                "alt": img.get("alt", ""),
                "title": img.get("title", ""),
                "width": img.get("width", ""),
                "height": img.get("height", ""),
            })
        
        return images

metadata_analyzer = MetadataAnalyzer()
