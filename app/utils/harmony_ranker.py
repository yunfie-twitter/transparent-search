"""Harmony Ranker for improved search result quality."""
from typing import List, Dict, Tuple
import math

class HarmonyRanker:
    """Ranks search results using multi-signal harmony scoring."""
    
    # Signal weights (must sum to 1.0)
    WEIGHTS = {
        "relevance": 0.40,      # BM25/FTS matching
        "recency": 0.15,        # Content freshness
        "domain_trust": 0.15,   # Domain authority
        "quality": 0.15,        # Content depth/quality
        "engagement": 0.05,     # Click-through rate
        "tracker_safety": 0.10, # Privacy/tracker risk (inverse)
    }
    
    @staticmethod
    def rank(
        results: List[Dict],
        base_scores: List[float],
        query_intent: str = "general"
    ) -> List[Tuple[Dict, float]]:
        """Rank results using harmony scoring.
        
        Args:
            results: List of search results
            base_scores: Base relevance scores (normalized 0-1)
            query_intent: Query intent for weighting adjustment
        
        Returns:
            List of (result, final_score) tuples, sorted by score
        """
        if not results or not base_scores:
            return [(r, 0.0) for r in results]
        
        # Adjust weights based on intent
        weights = HarmonyRanker._adjust_weights_for_intent(query_intent)
        
        ranked = []
        
        for i, result in enumerate(results):
            # Extract signals
            relevance_score = base_scores[i]
            recency_score = HarmonyRanker._calculate_recency(
                result.get("last_crawled_at")
            )
            domain_score = HarmonyRanker._calculate_domain_trust(
                result.get("domain", ""),
                result.get("trust_score", 0.5)
            )
            quality_score = HarmonyRanker._calculate_content_quality(
                result.get("content", ""),
                result.get("h1", "")
            )
            engagement_score = HarmonyRanker._calculate_engagement(
                result.get("click_score", 0),
                result.get("pagerank_score", 0)
            )
            safety_score = HarmonyRanker._calculate_tracker_safety(
                result.get("tracker_risk_score", 0.5)
            )
            
            # Calculate final harmony score
            final_score = (
                relevance_score * weights["relevance"] +
                recency_score * weights["recency"] +
                domain_score * weights["domain_trust"] +
                quality_score * weights["quality"] +
                engagement_score * weights["engagement"] +
                safety_score * weights["tracker_safety"]
            )
            
            ranked.append((result, final_score))
        
        # Sort by score descending
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked
    
    @staticmethod
    def _adjust_weights_for_intent(intent: str) -> Dict[str, float]:
        """Adjust weights based on query intent.
        
        Different intents prioritize different signals.
        """
        base_weights = HarmonyRanker.WEIGHTS.copy()
        
        if intent == "question":
            # For questions: prioritize relevance and domain trust (authoritative sources)
            base_weights["relevance"] = 0.50
            base_weights["domain_trust"] = 0.20
            base_weights["recency"] = 0.10
        
        elif intent == "navigation":
            # For navigation: prioritize domain trust and engagement
            base_weights["domain_trust"] = 0.35
            base_weights["engagement"] = 0.15
            base_weights["relevance"] = 0.30
        
        elif intent == "product_research":
            # For products: balance relevance and trust
            base_weights["relevance"] = 0.40
            base_weights["domain_trust"] = 0.25
            base_weights["engagement"] = 0.10
            base_weights["tracker_safety"] = 0.15  # Users care about privacy
        
        elif intent == "research":
            # For research: prioritize quality and recency
            base_weights["quality"] = 0.25
            base_weights["recency"] = 0.20
            base_weights["domain_trust"] = 0.25
            base_weights["relevance"] = 0.25
        
        # Normalize weights to sum to 1.0
        total = sum(base_weights.values())
        return {k: v / total for k, v in base_weights.items()}
    
    @staticmethod
    def _calculate_recency(last_crawled_at: str) -> float:
        """Calculate freshness score based on crawl date.
        
        Returns: 0-1 score, where 1.0 = very recent
        """
        if not last_crawled_at:
            return 0.5  # Default for unknown
        
        try:
            from datetime import datetime, timezone
            
            # Parse ISO format datetime
            if isinstance(last_crawled_at, str):
                crawl_time = datetime.fromisoformat(last_crawled_at.replace('Z', '+00:00'))
            else:
                crawl_time = last_crawled_at
            
            now = datetime.now(timezone.utc)
            days_old = (now - crawl_time).days
            
            # Decay function: fresh content (0 days) = 1.0, old (365 days) = 0.1
            if days_old <= 0:
                return 1.0
            elif days_old >= 365:
                return 0.1
            else:
                # Exponential decay
                return max(0.1, math.exp(-days_old / 180.0))
        
        except Exception:
            return 0.5
    
    @staticmethod
    def _calculate_domain_trust(domain: str, trust_score: float) -> float:
        """Calculate domain trustworthiness.
        
        Considers domain score and reputation patterns.
        """
        if not domain:
            return 0.5
        
        # Base score from database
        score = trust_score if trust_score else 0.5
        
        # Boost well-known domains
        quality_tlds = {".edu": 0.95, ".gov": 0.95, ".ac": 0.90}
        for tld, boost in quality_tlds.items():
            if domain.endswith(tld):
                return boost
        
        # Boost known quality domains
        quality_domains = {
            "github.com": 0.90,
            "stackoverflow.com": 0.90,
            "wikipedia.org": 0.95,
            "arxiv.org": 0.92,
            "scholar.google.com": 0.90,
        }
        
        for quality_domain, boost in quality_domains.items():
            if quality_domain in domain:
                return boost
        
        # Penalize suspicious patterns
        suspicious_patterns = [
            "bit.ly", "tinyurl", "short.link",
            "spam", "scam", "malware"
        ]
        
        for pattern in suspicious_patterns:
            if pattern in domain.lower():
                return 0.2
        
        return score
    
    @staticmethod
    def _calculate_content_quality(content: str, h1: str) -> float:
        """Calculate content quality score.
        
        Considers length, structure, and depth.
        """
        if not content:
            return 0.3
        
        content_len = len(content)
        
        # Length heuristics
        if content_len < 100:
            length_score = 0.3
        elif content_len < 500:
            length_score = 0.6
        elif content_len < 2000:
            length_score = 0.8
        else:
            length_score = 0.95
        
        # Structure heuristic (h1 presence)
        structure_score = 0.8 if h1 and len(h1) > 10 else 0.5
        
        # Combine scores
        quality = (length_score * 0.6 + structure_score * 0.4)
        return min(quality, 1.0)
    
    @staticmethod
    def _calculate_engagement(click_score: float, pagerank_score: float) -> float:
        """Calculate user engagement score.
        
        Considers clicks and pagerank.
        """
        # Normalize both scores to 0-1
        click_norm = min(click_score / 100.0, 1.0) if click_score else 0.0
        pagerank_norm = min(pagerank_score / 10.0, 1.0) if pagerank_score else 0.0
        
        # Combine with pagerank weighted more
        return click_norm * 0.3 + pagerank_norm * 0.7
    
    @staticmethod
    def _calculate_tracker_safety(tracker_risk_score: float) -> float:
        """Calculate privacy/safety score.
        
        Higher tracker risk = lower safety score.
        """
        if not tracker_risk_score:
            return 0.5
        
        # Invert: risk 0.0 (clean) = safety 1.0
        # risk 1.0 (severe) = safety 0.0
        return 1.0 - tracker_risk_score
    
    @staticmethod
    def explain_scoring(
        result: Dict,
        base_score: float,
        query_intent: str = "general"
    ) -> Dict[str, float]:
        """Explain scoring breakdown for a result.
        """
        weights = HarmonyRanker._adjust_weights_for_intent(query_intent)
        
        return {
            "relevance": base_score * weights["relevance"],
            "recency": HarmonyRanker._calculate_recency(
                result.get("last_crawled_at")
            ) * weights["recency"],
            "domain_trust": HarmonyRanker._calculate_domain_trust(
                result.get("domain", ""),
                result.get("trust_score", 0.5)
            ) * weights["domain_trust"],
            "quality": HarmonyRanker._calculate_content_quality(
                result.get("content", ""),
                result.get("h1", "")
            ) * weights["quality"],
            "engagement": HarmonyRanker._calculate_engagement(
                result.get("click_score", 0),
                result.get("pagerank_score", 0)
            ) * weights["engagement"],
            "tracker_safety": HarmonyRanker._calculate_tracker_safety(
                result.get("tracker_risk_score", 0.5)
            ) * weights["tracker_safety"],
        }

harmony_ranker = HarmonyRanker()
