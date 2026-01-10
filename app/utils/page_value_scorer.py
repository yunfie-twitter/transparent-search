"""Page value scoring with multi-factor analysis for smart crawling."""
import math
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass
from urllib.parse import urlparse
from collections import defaultdict


@dataclass
class LinkMetrics:
    """Link graph metrics for a page."""
    depth_from_root: int  # Number of hops from domain root
    internal_link_count: int  # Incoming internal links
    external_backlink_estimate: int  # Estimated external backlinks (0-100)
    outgoing_internal_links: int  # Links pointing to other pages
    outgoing_external_links: int  # Links pointing outside


@dataclass
class ContentMetrics:
    """Content quality and relevance metrics."""
    has_structured_data: bool  # Schema.org markup
    is_article: bool  # Blog, news article, etc.
    has_publish_date: bool
    has_author: bool
    has_og_tags: bool  # Open Graph metadata
    word_count: int  # Estimated or actual
    headings_count: int  # H1, H2, H3 total
    has_meta_description: bool


@dataclass
class PageValueScore:
    """Complete page value scoring."""
    total_score: float  # 0-100
    link_score: float  # Depth + internal links + backlinks
    content_score: float  # Structure + quality
    relevance_score: float  # Query intent matching
    crawl_priority: int  # 1 (highest) to 10 (lowest)
    recommendation: str  # "CRAWL_NOW", "CRAWL_LATER", "LOW_VALUE"
    factors: Dict[str, float]  # Individual factor scores
    reasoning: List[str]  # Why this priority


class PageValueScorer:
    """Intelligent page value scoring for crawl prioritization."""
    
    # Weights for different factors (sum to 1.0)
    WEIGHTS = {
        "depth": 0.15,
        "internal_links": 0.15,
        "external_backlinks": 0.15,
        "content_quality": 0.20,
        "metadata": 0.15,
        "freshness": 0.10,
        "uniqueness": 0.10,
    }
    
    # Crawl priority thresholds
    PRIORITY_THRESHOLDS = {
        "CRAWL_NOW": 75,       # High value, crawl immediately
        "CRAWL_SOON": 55,      # Medium value, queue for crawling
        "CRAWL_LATER": 35,     # Lower value, batch with others
        "LOW_VALUE": 0,        # Skip or low priority
    }
    
    @staticmethod
    def score_page(
        url: str,
        link_metrics: LinkMetrics,
        content_metrics: ContentMetrics,
        domain_stats: Optional[Dict] = None,
        recent_crawl: bool = False,
    ) -> PageValueScore:
        """
        Calculate comprehensive page value score.
        
        Args:
            url: Page URL
            link_metrics: Link graph metrics
            content_metrics: Content quality metrics
            domain_stats: Domain-wide statistics for context
            recent_crawl: Whether page was crawled recently
        
        Returns:
            PageValueScore with detailed breakdown
        """
        factors = {}
        
        # 1. DEPTH SCORE (0-100)
        # Pages closer to root are more valuable (home > section > article)
        depth_score = PageValueScorer._calculate_depth_score(
            link_metrics.depth_from_root
        )
        factors["depth"] = depth_score
        
        # 2. LINK POPULARITY SCORE (0-100)
        # Internal links indicate importance within site
        link_popularity_score = PageValueScorer._calculate_link_popularity_score(
            link_metrics.internal_link_count,
            domain_stats,
        )
        factors["internal_links"] = link_popularity_score
        
        # 3. BACKLINK AUTHORITY SCORE (0-100)
        # External backlinks indicate authority
        backlink_score = PageValueScorer._calculate_backlink_score(
            link_metrics.external_backlink_estimate
        )
        factors["external_backlinks"] = backlink_score
        
        # 4. CONTENT QUALITY SCORE (0-100)
        content_quality_score = PageValueScorer._calculate_content_quality_score(
            content_metrics
        )
        factors["content_quality"] = content_quality_score
        
        # 5. METADATA COMPLETENESS SCORE (0-100)
        metadata_score = PageValueScorer._calculate_metadata_score(
            content_metrics
        )
        factors["metadata"] = metadata_score
        
        # 6. FRESHNESS SCORE (0-100)
        # Recently updated content is more valuable
        freshness_score = 50.0  # Default, would use publish/modify dates
        if recent_crawl:
            freshness_score = 25.0  # Lower priority for recently crawled pages
        factors["freshness"] = freshness_score
        
        # 7. UNIQUENESS SCORE (0-100)
        # Article vs homepage vs product page
        uniqueness_score = PageValueScorer._calculate_uniqueness_score(
            url, content_metrics
        )
        factors["uniqueness"] = uniqueness_score
        
        # Calculate weighted total
        total_score = sum(
            factors[key] * PageValueScorer.WEIGHTS[key]
            for key in PageValueScorer.WEIGHTS
        )
        
        # Determine crawl priority
        priority, recommendation = PageValueScorer._get_priority(
            total_score, content_metrics
        )
        
        # Generate reasoning
        reasoning = PageValueScorer._generate_reasoning(
            factors, link_metrics, content_metrics, total_score
        )
        
        return PageValueScore(
            total_score=total_score,
            link_score=(depth_score + link_popularity_score + backlink_score) / 3,
            content_score=content_quality_score,
            relevance_score=metadata_score,
            crawl_priority=priority,
            recommendation=recommendation,
            factors=factors,
            reasoning=reasoning,
        )
    
    @staticmethod
    def _calculate_depth_score(depth: int) -> float:
        """
        Score based on distance from domain root.
        
        Depth 0-2: High value (home, main sections)
        Depth 3-5: Medium value
        Depth 6+: Lower value (deep pages)
        """
        if depth <= 1:
            return 100.0
        elif depth == 2:
            return 85.0
        elif depth == 3:
            return 70.0
        elif depth == 4:
            return 55.0
        elif depth == 5:
            return 40.0
        else:
            # Exponential decay for very deep pages
            return max(10.0, 40.0 * math.exp(-0.2 * (depth - 5)))
    
    @staticmethod
    def _calculate_link_popularity_score(
        internal_links: int,
        domain_stats: Optional[Dict] = None,
    ) -> float:
        """
        Score based on internal link popularity.
        
        Pages linked to many times are more important.
        """
        if internal_links == 0:
            return 20.0
        elif internal_links == 1:
            return 40.0
        elif internal_links <= 3:
            return 60.0
        elif internal_links <= 10:
            return 75.0
        elif internal_links <= 50:
            return 85.0
        else:
            # Logarithmic scaling for very popular pages
            return min(100.0, 85.0 + math.log(internal_links) / math.log(100))
    
    @staticmethod
    def _calculate_backlink_score(estimated_backlinks: int) -> float:
        """
        Score based on estimated external backlinks.
        
        Scale 0-100 based on backlink count estimate.
        """
        if estimated_backlinks == 0:
            return 30.0
        elif estimated_backlinks <= 5:
            return 50.0
        elif estimated_backlinks <= 20:
            return 70.0
        elif estimated_backlinks <= 100:
            return 85.0
        else:
            # Logarithmic scaling
            return min(100.0, 85.0 + math.log(estimated_backlinks) / math.log(1000))
    
    @staticmethod
    def _calculate_content_quality_score(metrics: ContentMetrics) -> float:
        """
        Score content quality based on structure and completeness.
        """
        score = 50.0  # Base score
        
        # Content type matters
        if metrics.is_article:
            score += 15.0
        
        # Metadata completeness
        metadata_points = 0
        if metrics.has_structured_data:
            metadata_points += 5
        if metrics.has_publish_date:
            metadata_points += 5
        if metrics.has_author:
            metadata_points += 5
        if metrics.has_og_tags:
            metadata_points += 5
        if metrics.has_meta_description:
            metadata_points += 5
        
        score += metadata_points
        
        # Word count (more is better, up to a point)
        if metrics.word_count >= 500:
            score += 10.0
        elif metrics.word_count >= 300:
            score += 7.0
        elif metrics.word_count >= 100:
            score += 3.0
        
        # Structure (headings indicate organization)
        if metrics.headings_count >= 5:
            score += 5.0
        elif metrics.headings_count >= 3:
            score += 3.0
        
        return min(100.0, score)
    
    @staticmethod
    def _calculate_metadata_score(metrics: ContentMetrics) -> float:
        """
        Score based on SEO metadata completeness.
        """
        score = 0.0
        total_possible = 5
        
        if metrics.has_meta_description:
            score += 1
        if metrics.has_og_tags:
            score += 1
        if metrics.has_structured_data:
            score += 1
        if metrics.has_publish_date:
            score += 1
        if metrics.has_author:
            score += 1
        
        return (score / total_possible) * 100.0
    
    @staticmethod
    def _calculate_uniqueness_score(url: str, metrics: ContentMetrics) -> float:
        """
        Score based on page type and uniqueness.
        """
        score = 50.0
        
        # Original content gets premium
        if metrics.is_article:
            score = 80.0
        
        # Check URL patterns for common low-value pages
        path = urlparse(url).path.lower()
        
        # Archive/tag pages are less valuable
        if any(x in path for x in ["archive", "category", "tag", "author"]):
            score -= 15.0
        
        # Dynamic/parameter-heavy pages may be duplicate content
        if "?" in url and url.count("?") > 1:
            score -= 10.0
        
        return max(10.0, score)
    
    @staticmethod
    def _get_priority(score: float, metrics: ContentMetrics) -> Tuple[int, str]:
        """
        Determine crawl priority (1-10, 1 = highest) and recommendation.
        """
        if score >= PageValueScorer.PRIORITY_THRESHOLDS["CRAWL_NOW"]:
            return 1, "CRAWL_NOW"
        elif score >= PageValueScorer.PRIORITY_THRESHOLDS["CRAWL_SOON"]:
            return 3, "CRAWL_SOON"
        elif score >= PageValueScorer.PRIORITY_THRESHOLDS["CRAWL_LATER"]:
            return 6, "CRAWL_LATER"
        else:
            return 10, "LOW_VALUE"
    
    @staticmethod
    def _generate_reasoning(
        factors: Dict[str, float],
        link_metrics: LinkMetrics,
        content_metrics: ContentMetrics,
        total_score: float,
    ) -> List[str]:
        """
        Generate human-readable reasoning for the score.
        """
        reasons = []
        
        # Positive factors
        if factors["depth"] >= 80:
            reasons.append("Located near domain root (high priority)")
        
        if factors["internal_links"] >= 75:
            reasons.append(f"Heavily linked internally ({link_metrics.internal_link_count} incoming links)")
        
        if factors["external_backlinks"] >= 75:
            reasons.append(f"Significant external authority ({link_metrics.external_backlink_estimate} est. backlinks)")
        
        if factors["content_quality"] >= 80:
            reasons.append("High content quality and structure")
        
        if content_metrics.is_article:
            reasons.append("Identified as article/blog post (original content)")
        
        # Negative factors
        if factors["depth"] <= 40:
            reasons.append(f"Deep page ({link_metrics.depth_from_root} hops from root)")
        
        if factors["internal_links"] <= 40:
            reasons.append("Limited internal linking")
        
        if factors["content_quality"] <= 50:
            reasons.append("Minimal content or metadata")
        
        if not content_metrics.has_structured_data:
            reasons.append("No structured data markup")
        
        return reasons if reasons else [f"Overall score: {total_score:.1f}"]


page_value_scorer = PageValueScorer()
