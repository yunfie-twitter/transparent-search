"""Analyze search query intent and match with page content relevance."""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re
from enum import Enum


class QueryIntent(Enum):
    """Search query intent classification."""
    INFORMATIONAL = "informational"  # "How to", "What is", "Why"
    NAVIGATIONAL = "navigational"    # "[Brand] login", "[Site] homepage"
    TRANSACTIONAL = "transactional"  # "Buy", "Download", "Register"
    COMMERCIAL = "commercial"        # "Best [product]", "Reviews", "Pricing"
    LOCAL = "local"                  # "Near me", "[Location] + [service]"
    
    def __str__(self):
        return self.value


class ContentType(Enum):
    """Page content classification."""
    ARTICLE = "article"
    PRODUCT = "product"
    CATEGORY = "category"
    LANDING_PAGE = "landing_page"
    DOCUMENTATION = "documentation"
    FORUM = "forum"
    VIDEO = "video"
    NEWS = "news"
    LISTING = "listing"
    UNKNOWN = "unknown"


@dataclass
class IntentAnalysis:
    """Search query intent analysis."""
    query: str
    primary_intent: QueryIntent
    secondary_intents: List[QueryIntent]
    confidence: float  # 0-1
    keywords: List[str]  # Key indicator keywords found
    modifiers: List[str]  # "near me", "best", "free", etc.


@dataclass
class PageRelevanceScore:
    """Page relevance to query intent."""
    url: str
    content_type: ContentType
    relevance_score: float  # 0-100
    intent_match_score: float  # 0-100, how well page matches query intent
    content_match_score: float  # 0-100, keyword/topic relevance
    recommendations: List[str]
    is_relevant: bool  # Relevance >= 60
    reasoning: List[str]


class QueryIntentAnalyzer:
    """Analyzes search query intent and page content relevance."""
    
    # Intent indicators
    INFORMATIONAL_KEYWORDS = {
        "how", "what", "why", "when", "where",
        "explain", "describe", "define", "understand",
        "tutorial", "guide", "help", "learn",
        "question", "answer", "tips", "best practices",
    }
    
    NAVIGATIONAL_KEYWORDS = {
        "login", "signin", "register", "sign up",
        "home", "homepage", "official", "website",
        "app", "download", "connect",
    }
    
    TRANSACTIONAL_KEYWORDS = {
        "buy", "purchase", "order", "checkout",
        "download", "install", "register", "subscribe",
        "sign up", "book", "reserve", "rent",
    }
    
    COMMERCIAL_KEYWORDS = {
        "best", "top", "review", "reviews",
        "pricing", "price", "cost", "free",
        "vs", "comparison", "pros cons", "worth",
        "alternative", "alternative to",
    }
    
    LOCAL_KEYWORDS = {
        "near me", "nearby", "local", "location",
        "address", "hours", "phone", "directions",
    }
    
    # Content type indicators
    ARTICLE_INDICATORS = {
        "published_date", "author", "tags",
        "h1_count", "long_content", "structured_data",
    }
    
    PRODUCT_INDICATORS = {
        "price", "add to cart", "product title",
        "specifications", "reviews", "rating",
    }
    
    @staticmethod
    def analyze_query(query: str) -> IntentAnalysis:
        """
        Analyze search query intent.
        
        Args:
            query: Search query string
        
        Returns:
            IntentAnalysis with primary/secondary intents
        """
        query_lower = query.lower()
        confidence = 0.0
        primary_intent = QueryIntent.INFORMATIONAL  # Default
        secondary_intents = []
        keywords = []
        modifiers = []
        
        # Score each intent type
        intent_scores = {
            QueryIntent.INFORMATIONAL: 0.0,
            QueryIntent.NAVIGATIONAL: 0.0,
            QueryIntent.TRANSACTIONAL: 0.0,
            QueryIntent.COMMERCIAL: 0.0,
            QueryIntent.LOCAL: 0.0,
        }
        
        # Check for informational intent
        informational_count = sum(
            1 for kw in QueryIntentAnalyzer.INFORMATIONAL_KEYWORDS
            if kw in query_lower
        )
        intent_scores[QueryIntent.INFORMATIONAL] = informational_count * 0.25
        if informational_count > 0:
            keywords.extend([kw for kw in QueryIntentAnalyzer.INFORMATIONAL_KEYWORDS if kw in query_lower])
        
        # Check for navigational intent
        navigational_count = sum(
            1 for kw in QueryIntentAnalyzer.NAVIGATIONAL_KEYWORDS
            if kw in query_lower
        )
        intent_scores[QueryIntent.NAVIGATIONAL] = navigational_count * 0.25
        if navigational_count > 0:
            keywords.extend([kw for kw in QueryIntentAnalyzer.NAVIGATIONAL_KEYWORDS if kw in query_lower])
        
        # Check for transactional intent
        transactional_count = sum(
            1 for kw in QueryIntentAnalyzer.TRANSACTIONAL_KEYWORDS
            if kw in query_lower
        )
        intent_scores[QueryIntent.TRANSACTIONAL] = transactional_count * 0.25
        if transactional_count > 0:
            keywords.extend([kw for kw in QueryIntentAnalyzer.TRANSACTIONAL_KEYWORDS if kw in query_lower])
        
        # Check for commercial intent
        commercial_count = sum(
            1 for kw in QueryIntentAnalyzer.COMMERCIAL_KEYWORDS
            if kw in query_lower
        )
        intent_scores[QueryIntent.COMMERCIAL] = commercial_count * 0.25
        if commercial_count > 0:
            keywords.extend([kw for kw in QueryIntentAnalyzer.COMMERCIAL_KEYWORDS if kw in query_lower])
            modifiers.append("comparison")
        
        # Check for local intent
        local_count = sum(
            1 for kw in QueryIntentAnalyzer.LOCAL_KEYWORDS
            if kw in query_lower
        )
        intent_scores[QueryIntent.LOCAL] = local_count * 0.25
        if local_count > 0:
            keywords.extend([kw for kw in QueryIntentAnalyzer.LOCAL_KEYWORDS if kw in query_lower])
            modifiers.append("location-based")
        
        # Determine primary intent
        max_intent = max(intent_scores, key=intent_scores.get)
        confidence = intent_scores[max_intent]
        primary_intent = max_intent
        
        # Find secondary intents (scores >= 20% of max)
        threshold = max(intent_scores.values()) * 0.2 if max(intent_scores.values()) > 0 else 0
        secondary_intents = [
            intent for intent, score in intent_scores.items()
            if intent != primary_intent and score >= threshold and score > 0
        ]
        
        # Extract additional modifiers
        if "free" in query_lower:
            modifiers.append("free")
        if "cheapest" in query_lower or "cheapest" in query_lower:
            modifiers.append("budget")
        if "2024" in query_lower or "2025" in query_lower:
            modifiers.append("recent")
        
        # Remove duplicates
        keywords = list(set(keywords))
        modifiers = list(set(modifiers))
        
        return IntentAnalysis(
            query=query,
            primary_intent=primary_intent,
            secondary_intents=secondary_intents,
            confidence=min(1.0, confidence),
            keywords=keywords,
            modifiers=modifiers,
        )
    
    @staticmethod
    def classify_content(page_data: Dict) -> ContentType:
        """
        Classify page content type based on metadata and structure.
        
        Args:
            page_data: Page metadata and content info
        
        Returns:
            ContentType classification
        """
        url = page_data.get("url", "").lower()
        metadata = page_data.get("metadata", {})
        structured_data = metadata.get("structured_data", [])
        content = page_data.get("content", "").lower()
        
        # Check URL patterns
        if any(x in url for x in ["product", "/p/", "shop", "store"]):
            return ContentType.PRODUCT
        elif any(x in url for x in ["category", "tag", "archive", "category"]):
            return ContentType.CATEGORY
        elif any(x in url for x in ["docs", "documentation", "api", "guide", "reference"]):
            return ContentType.DOCUMENTATION
        elif any(x in url for x in ["forum", "discussion", "thread", "comment"]):
            return ContentType.FORUM
        elif any(x in url for x in ["news", "article", "blog", "post"]):
            return ContentType.ARTICLE
        
        # Check structured data
        for schema in structured_data:
            if isinstance(schema, dict):
                schema_type = schema.get("@type", "").lower()
                
                if "product" in schema_type:
                    return ContentType.PRODUCT
                elif "article" in schema_type or "news" in schema_type:
                    return ContentType.ARTICLE
                elif "video" in schema_type:
                    return ContentType.VIDEO
        
        # Check content patterns
        if any(x in content for x in ["add to cart", "buy", "price:", "$", "purchase"]):
            return ContentType.PRODUCT
        elif any(x in content for x in ["published", "author:", "updated"]):
            return ContentType.ARTICLE
        elif any(x in content for x in ["watch", "video", "youtube"]):
            return ContentType.VIDEO
        
        # Check if landing page (main domain root)
        if url.rstrip("/") == page_data.get("domain", "").rstrip("/"):
            return ContentType.LANDING_PAGE
        
        return ContentType.UNKNOWN
    
    @staticmethod
    def score_page_relevance(
        page_data: Dict,
        query_intent: IntentAnalysis,
    ) -> PageRelevanceScore:
        """
        Score page relevance to query intent.
        
        Args:
            page_data: Page metadata, content, structure
            query_intent: Analyzed search query intent
        
        Returns:
            PageRelevanceScore with intent matching
        """
        url = page_data.get("url", "")
        content = page_data.get("content", "").lower()
        metadata = page_data.get("metadata", {})
        
        # Classify page content
        content_type = QueryIntentAnalyzer.classify_content(page_data)
        
        # Calculate intent match score
        intent_match_score = QueryIntentAnalyzer._calculate_intent_match(
            content_type, query_intent
        )
        
        # Calculate content match score
        content_match_score = QueryIntentAnalyzer._calculate_content_match(
            page_data, query_intent
        )
        
        # Overall relevance score
        relevance_score = (intent_match_score + content_match_score) / 2
        
        # Generate reasoning
        reasoning = QueryIntentAnalyzer._generate_reasoning(
            content_type, intent_match_score, content_match_score, query_intent
        )
        
        # Generate recommendations
        recommendations = []
        if intent_match_score < 50:
            recommendations.append(
                "Page content type doesn't match query intent well - may not rank well"
            )
        if content_match_score < 50:
            recommendations.append(
                "Limited keyword/topic relevance to query - consider improving content"
            )
        if not metadata.get("structured_data"):
            recommendations.append(
                "Add structured data markup to improve SERP appearance"
            )
        
        return PageRelevanceScore(
            url=url,
            content_type=content_type,
            relevance_score=relevance_score,
            intent_match_score=intent_match_score,
            content_match_score=content_match_score,
            recommendations=recommendations,
            is_relevant=relevance_score >= 60,
            reasoning=reasoning,
        )
    
    @staticmethod
    def _calculate_intent_match(
        content_type: ContentType,
        query_intent: IntentAnalysis,
    ) -> float:
        """
        Calculate how well page type matches query intent.
        
        Returns: 0-100 score
        """
        intent = query_intent.primary_intent
        score = 0.0
        
        # Perfect matches
        if intent == QueryIntent.INFORMATIONAL:
            if content_type in [ContentType.ARTICLE, ContentType.DOCUMENTATION, ContentType.NEWS]:
                score = 95.0
            elif content_type == ContentType.FORUM:
                score = 70.0
            elif content_type in [ContentType.PRODUCT, ContentType.LISTING]:
                score = 40.0
        
        elif intent == QueryIntent.NAVIGATIONAL:
            if content_type == ContentType.LANDING_PAGE:
                score = 95.0
            elif content_type == ContentType.PRODUCT:
                score = 70.0
            else:
                score = 50.0
        
        elif intent == QueryIntent.TRANSACTIONAL:
            if content_type in [ContentType.PRODUCT, ContentType.LISTING]:
                score = 95.0
            elif content_type == ContentType.LANDING_PAGE:
                score = 70.0
            else:
                score = 30.0
        
        elif intent == QueryIntent.COMMERCIAL:
            if content_type == ContentType.PRODUCT:
                score = 90.0
            elif content_type == ContentType.ARTICLE:
                score = 70.0  # Review/comparison articles
            elif content_type == ContentType.LISTING:
                score = 75.0
            else:
                score = 40.0
        
        elif intent == QueryIntent.LOCAL:
            if content_type == ContentType.LISTING:
                score = 95.0
            elif content_type == ContentType.LANDING_PAGE:
                score = 60.0
            else:
                score = 30.0
        
        return score
    
    @staticmethod
    def _calculate_content_match(
        page_data: Dict,
        query_intent: IntentAnalysis,
    ) -> float:
        """
        Calculate content keyword/topic relevance.
        
        Returns: 0-100 score
        """
        content = page_data.get("content", "").lower()
        metadata = page_data.get("metadata", {})
        
        score = 50.0  # Base score
        
        # Check keyword matches
        matched_keywords = sum(
            1 for keyword in query_intent.keywords
            if keyword in content
        )
        keyword_match_ratio = matched_keywords / len(query_intent.keywords) if query_intent.keywords else 0
        score += keyword_match_ratio * 30  # 0-30 points
        
        # Check title and description
        title = metadata.get("title", "").lower()
        description = metadata.get("description", "").lower()
        
        if matched_keywords > 0:
            if matched_keywords >= 1 and matched_keywords in title:
                score += 10  # Main keyword in title
            if matched_keywords >= 1 and matched_keywords in description:
                score += 5  # Keyword in meta description
        
        # Check for relevant modifiers
        if "free" in query_intent.modifiers and "free" in content:
            score += 5
        if "recent" in query_intent.modifiers:
            if metadata.get("publish_date") or metadata.get("modified_date"):
                score += 5
        
        return min(100.0, score)
    
    @staticmethod
    def _generate_reasoning(
        content_type: ContentType,
        intent_match: float,
        content_match: float,
        query_intent: IntentAnalysis,
    ) -> List[str]:
        """
        Generate human-readable reasoning for relevance score.
        """
        reasons = []
        
        reasons.append(
            f"Page type: {content_type.value} | Query intent: {query_intent.primary_intent}"
        )
        
        if intent_match >= 80:
            reasons.append("✅ Strong content-intent alignment")
        elif intent_match >= 60:
            reasons.append("⚠️  Moderate content-intent alignment")
        else:
            reasons.append("❌ Poor content-intent alignment")
        
        if content_match >= 80:
            reasons.append("✅ Good keyword/topic coverage")
        elif content_match >= 60:
            reasons.append("⚠️  Moderate keyword coverage")
        else:
            reasons.append("❌ Limited keyword coverage")
        
        if query_intent.secondary_intents:
            reasons.append(
                f"Secondary intents detected: {[str(i) for i in query_intent.secondary_intents]}"
            )
        
        return reasons


query_intent_analyzer = QueryIntentAnalyzer()
