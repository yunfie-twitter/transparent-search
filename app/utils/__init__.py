"""Utils module - Utility functions and analysis tools."""

from app.utils.metadata_analyzer import MetadataAnalyzer
from app.utils.page_value_scorer import PageValueScorer
from app.utils.spam_detector import SpamDetector
from app.utils.query_intent_analyzer import QueryIntentAnalyzer
from app.utils.intent_detector import IntentDetector

# Singleton instances
metadata_analyzer = MetadataAnalyzer()
page_value_scorer = PageValueScorer()
spam_detector = SpamDetector()
query_intent_analyzer = QueryIntentAnalyzer()

__all__ = [
    "MetadataAnalyzer",
    "PageValueScorer",
    "SpamDetector",
    "QueryIntentAnalyzer",
    "IntentDetector",
    # Singletons
    "metadata_analyzer",
    "page_value_scorer",
    "spam_detector",
    "query_intent_analyzer",
]
