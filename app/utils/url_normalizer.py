from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
import re

def normalize_url(url: str) -> str:
    """Normalize URL for deduplication.
    - Convert to lowercase (except path for case-sensitive servers)
    - Remove fragment (#...)
    - Sort query parameters
    - Remove trailing slash (except for root)
    - Unify http/https (prefer https if available, but here we keep original)
    """
    parsed = urlparse(url)
    
    # Lowercase scheme and netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    
    # Keep path as-is (case sensitive)
    path = parsed.path
    
    # Remove trailing slash except for root
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    
    # Sort query params
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        sorted_params = sorted(params.items())
        query = urlencode(sorted_params, doseq=True)
    else:
        query = ""
    
    # No fragment
    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    return normalized

def is_valid_url(url: str) -> bool:
    """Check if URL is valid for crawling."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    # Exclude common binary/media extensions
    exclude_exts = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".mp4", ".avi", ".mp3")
    if any(parsed.path.lower().endswith(ext) for ext in exclude_exts):
        return False
    return True
