"""Advanced content type classification."""
import re
from typing import Dict, Tuple
from urllib.parse import urlparse

class ContentClassifier:
    """Classifies web content into specific types with confidence scores."""
    
    # Content type patterns
    PATTERNS = {
        "text_article": {
            "url_patterns": [
                r"/blog/", r"/article/", r"/post/", r"/news/",
                r"/story/", r"/press/", r"/publication/"
            ],
            "content_patterns": [
                r"<article", r"<main", r"<h1>.*?</h1>.*?<p>",
                r"byline|author|published|article"
            ],
            "schema_patterns": ["Article", "NewsArticle", "BlogPosting"]
        },
        "video": {
            "url_patterns": [
                r"/video/", r"/watch", r"youtube.com/watch", 
                r"vimeo.com", r"/video-", r"/v/"
            ],
            "content_patterns": [
                r"<iframe.*?src=.*?(youtube|vimeo)",
                r"<video", r"videojs", r"player"
            ],
            "schema_patterns": ["VideoObject"]
        },
        "image": {
            "url_patterns": [
                r"/gallery/", r"/images/", r"/photos/", r"/picture",
                r"imgur.com", r"flick.com"
            ],
            "content_patterns": [
                r"<img[^>]+src=.*?\.(jpg|png|gif|webp)",
                r"lightbox|photoswipe|gallery"
            ],
            "schema_patterns": ["ImageObject"]
        },
        "forum": {
            "url_patterns": [
                r"/forum/", r"/thread/", r"/discussion/", r"/topic/",
                r"reddit.com", r"stackoverflow.com", r"github.com/issues"
            ],
            "content_patterns": [
                r"comment|reply|post.*?user", r"upvote|downvote|vote",
                r"<ul.*?class.*?comment"
            ],
            "schema_patterns": ["DiscussionForumPosting"]
        },
        "tool": {
            "url_patterns": [
                r"/app/", r"/tool", r"/calculator", r"/generator",
                r"/converter", r"/api", r"/service"
            ],
            "content_patterns": [
                r"<input[^>]+type.*?(text|number|file)",
                r"<button[^>]+id=.*?submit|execute|generate",
                r"api.example"
            ],
            "schema_patterns": ["SoftwareApplication"]
        },
        "product": {
            "url_patterns": [
                r"/product/", r"/shop/", r"/store/", r"/item/",
                r"/listing/", r"amazon.com/", r"ebay.com"
            ],
            "content_patterns": [
                r"price|\$[0-9]+|¥", r"add.*?cart|buy.*?now",
                r"rating|star|review"
            ],
            "schema_patterns": ["Product", "Offer"]
        },
        "documentation": {
            "url_patterns": [
                r"/docs/", r"/documentation/", r"/manual/", r"/guide/",
                r"/tutorial/", r"/readme"
            ],
            "content_patterns": [
                r"<code", r"```", r"<pre>", r"example",
                r"installation|setup|configuration"
            ],
            "schema_patterns": ["TechArticle"]
        },
        "manga": {
            "url_patterns": [
                r"/manga/", r"/comic/", r"/chapter/", 
                r"mangadex|mangaplus|manganelo"
            ],
            "content_patterns": [
                r"<img[^>]+class=.*?manga|chapter",
                r"page.*?\d+", r"next.*?chapter"
            ],
            "schema_patterns": ["Manga", "Comic"]
        },
        "academic": {
            "url_patterns": [
                r"/paper/", r"/research/", r"/study/",
                r"arxiv.org", r"scholar.google", r"researchgate"
            ],
            "content_patterns": [
                r"abstract|introduction|conclusion",
                r"doi:|citation|reference"
            ],
            "schema_patterns": ["ScholarlyArticle"]
        },
    }
    
    @staticmethod
    def classify(
        url: str,
        html: str,
        jsonld_items: list = None
    ) -> Tuple[str, float]:
        """Classify content and return (type, confidence)."""
        if jsonld_items is None:
            jsonld_items = []
        
        scores = {}
        
        # Check each content type
        for content_type, patterns in ContentClassifier.PATTERNS.items():
            score = 0.0
            matches = 0
            total_checks = 0
            
            # URL pattern matching (0-30 points)
            for pattern in patterns["url_patterns"]:
                total_checks += 1
                if re.search(pattern, url, re.IGNORECASE):
                    score += 30 / len(patterns["url_patterns"])
                    matches += 1
            
            # Content pattern matching (0-40 points)
            for pattern in patterns["content_patterns"]:
                total_checks += 1
                if re.search(pattern, html, re.IGNORECASE):
                    score += 40 / len(patterns["content_patterns"])
                    matches += 1
            
            # Schema.org pattern matching (0-30 points)
            for schema in patterns["schema_patterns"]:
                total_checks += 1
                schema_found = False
                
                # Check in JSON-LD
                for item in jsonld_items:
                    if isinstance(item, dict):
                        item_type = item.get("@type", "")
                        if isinstance(item_type, str):
                            if schema in item_type:
                                schema_found = True
                        elif isinstance(item_type, list):
                            if schema in item_type:
                                schema_found = True
                    
                    if schema_found:
                        break
                
                if schema_found:
                    score += 30 / len(patterns["schema_patterns"])
                    matches += 1
            
            scores[content_type] = score
        
        # Find best match
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        
        # Normalize to 0-1 confidence
        confidence = min(best_score / 100.0, 1.0)
        
        # Default to 'unknown' if confidence is too low
        if confidence < 0.1:
            return "unknown", 0.0
        
        return best_type, confidence
    
    @staticmethod
    def classify_batch(
        pages: list
    ) -> Dict[int, Tuple[str, float]]:
        """Classify multiple pages efficiently.
        
        Args:
            pages: List of dicts with 'url', 'html', 'jsonld'
        
        Returns:
            Dict mapping page_id to (type, confidence)
        """
        results = {}
        
        for page in pages:
            content_type, confidence = ContentClassifier.classify(
                page.get("url", ""),
                page.get("html", ""),
                page.get("jsonld", [])
            )
            results[page.get("id")] = (content_type, confidence)
        
        return results


content_classifier = ContentClassifier()
