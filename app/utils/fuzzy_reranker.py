"""Fuzzy reranking for ambiguous query handling."""
from typing import List, Dict, Tuple
from difflib import SequenceMatcher
import re

class FuzzyReranker:
    """Reranks search results based on fuzzy matching and ambiguity control."""
    
    @staticmethod
    def calculate_fuzzy_match(
        query: str,
        text: str,
        threshold: float = 0.6
    ) -> float:
        """Calculate fuzzy match ratio between query and text.
        
        Args:
            query: Search query
            text: Text to match against
            threshold: Minimum match ratio
        
        Returns:
            Match ratio (0-1)
        """
        # Normalize inputs
        query_norm = query.lower().strip()
        text_norm = text.lower().strip()
        
        # Exact match
        if query_norm == text_norm:
            return 1.0
        
        # Subsequence matching
        if query_norm in text_norm:
            # Score based on overlap percentage
            return min(len(query_norm) / len(text_norm) * 1.2, 1.0)
        
        # Token-based matching
        query_tokens = set(query_norm.split())
        text_tokens = set(text_norm.split())
        
        if query_tokens & text_tokens:  # Has overlap
            overlap = len(query_tokens & text_tokens)
            union = len(query_tokens | text_tokens)
            jaccard = overlap / union if union > 0 else 0
            return jaccard
        
        # Sequence matching
        ratio = SequenceMatcher(None, query_norm, text_norm).ratio()
        return ratio if ratio >= threshold else 0.0
    
    @staticmethod
    def calculate_ambiguity_score(
        results: List[Dict],
        query: str
    ) -> List[Tuple[Dict, float]]:
        """Calculate ambiguity score for each result.
        
        Lower score = less ambiguous, clearer match
        Higher score = more ambiguous, uncertain match
        
        Args:
            results: List of search results
            query: Original query
        
        Returns:
            List of (result, ambiguity_score) tuples
        """
        scored_results = []
        
        for result in results:
            # Get text fields
            title = result.get("title", "")
            content = result.get("content", "")[:500]  # First 500 chars
            url = result.get("url", "")
            
            # Calculate individual scores
            title_match = FuzzyReranker.calculate_fuzzy_match(query, title)
            content_match = FuzzyReranker.calculate_fuzzy_match(query, content, threshold=0.4)
            url_match = FuzzyReranker.calculate_fuzzy_match(query, url)
            
            # Weighted combination (higher is better match)
            match_score = (title_match * 0.5 + content_match * 0.3 + url_match * 0.2)
            
            # Ambiguity is inverse of match certainty
            # High match = low ambiguity
            # Spread of scores indicates ambiguity
            scores = [title_match, content_match, url_match]
            variance = sum((s - match_score) ** 2 for s in scores) / len(scores)
            
            # Normalize variance to 0-1
            ambiguity = min(variance, 1.0)
            
            scored_results.append((result, ambiguity))
        
        return scored_results
    
    @staticmethod
    def rerank(
        results: List[Dict],
        query: str,
        base_scores: List[float],
        ambiguity_control: float = 0.5
    ) -> List[Tuple[Dict, float]]:
        """Rerank results based on fuzzy matching and ambiguity.
        
        Args:
            results: Original search results
            query: Search query
            base_scores: Base ranking scores (e.g., from BM25)
            ambiguity_control: How much to penalize ambiguous results (0-1)
                0 = ignore ambiguity, 1 = heavily penalize ambiguous
        
        Returns:
            Reranked results with new scores
        """
        if not results or not base_scores:
            return [(r, 0.0) for r in results]
        
        # Calculate fuzzy matches
        fuzzy_scores = []
        for result in results:
            title = result.get("title", "")
            content = result.get("content", "")[:500]
            
            title_match = FuzzyReranker.calculate_fuzzy_match(query, title)
            content_match = FuzzyReranker.calculate_fuzzy_match(query, content, threshold=0.3)
            
            fuzzy_score = max(title_match, content_match)  # Use best match
            fuzzy_scores.append(fuzzy_score)
        
        # Calculate ambiguity scores
        ambiguity_results = FuzzyReranker.calculate_ambiguity_score(results, query)
        ambiguity_scores = [amb for _, amb in ambiguity_results]
        
        # Combine scores
        reranked = []
        max_base_score = max(base_scores) if base_scores else 1.0
        max_fuzzy_score = max(fuzzy_scores) if fuzzy_scores else 1.0
        
        for i, result in enumerate(results):
            # Normalize scores
            norm_base = base_scores[i] / max_base_score if max_base_score > 0 else 0
            norm_fuzzy = fuzzy_scores[i] / max_fuzzy_score if max_fuzzy_score > 0 else 0
            norm_ambiguity = ambiguity_scores[i]
            
            # Calculate final score
            # Base score (ranking): 40%
            # Fuzzy match (relevance): 50%
            # Ambiguity penalty (clarity): 10%
            final_score = (
                norm_base * 0.4 +
                norm_fuzzy * 0.5 -
                (norm_ambiguity * ambiguity_control * 0.1)
            )
            
            reranked.append((result, final_score))
        
        # Sort by final score
        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked
    
    @staticmethod
    def explain_relevance(result: Dict, query: str) -> Dict[str, float]:
        """Explain why a result is relevant.
        
        Args:
            result: Search result
            query: Search query
        
        Returns:
            Dict with relevance explanation scores
        """
        title = result.get("title", "")
        content = result.get("content", "")[:500]
        url = result.get("url", "")
        
        return {
            "title_match": FuzzyReranker.calculate_fuzzy_match(query, title),
            "content_match": FuzzyReranker.calculate_fuzzy_match(query, content, threshold=0.3),
            "url_match": FuzzyReranker.calculate_fuzzy_match(query, url),
            "domain_relevance": FuzzyReranker._score_domain_quality(url),
        }
    
    @staticmethod
    def _score_domain_quality(url: str) -> float:
        """Score domain quality based on URL patterns."""
        # Penalize certain low-quality domains
        low_quality_patterns = [
            r"spam", r"scam", r"adult", r"malware",
            r"bit.ly", r"tinyurl", r"short.link"
        ]
        
        for pattern in low_quality_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return 0.3
        
        # Boost certain quality domains
        quality_patterns = [
            r"(github|stackoverflow|wikipedia|arxiv|scholar)\.com",
            r"(edu|gov)",
        ]
        
        for pattern in quality_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return 0.9
        
        return 0.7  # Default neutral score

fuzzy_reranker = FuzzyReranker()
