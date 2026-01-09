"""Search Intent Detector - Classify user search intent."""

import re
from typing import Dict, Tuple, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class IntentDetector:
    """Detect and classify search intent from queries."""
    
    INTENT_TYPES = [
        'question',
        'navigation',
        'transactional',
        'debugging',
        'research',
        'product_research',
        'informational',  # default
    ]
    
    # Intent patterns (English)
    INTENT_PATTERNS = {
        'question': [
            r'^\s*(?:what|which|who|when|where|why|how|do|does|is|are|can|could)',
            r'\?\s*$',
            r'\b(?:tell me|explain|show me|give me|list)\b',
        ],
        'debugging': [
            r'\b(?:error|bug|fix|issue|crash|exception|failed|not working|broke|broken)\b',
            r'\b(?:TypeError|SyntaxError|RuntimeError|ValueError|KeyError)\b',
            r'\b(?:stderr|traceback|stack trace|debug)\b',
        ],
        'transactional': [
            r'\b(?:buy|purchase|price|cost|shop|order|checkout|cart|payment)\b',
            r'\b(?:deal|discount|sale|coupon|promo)\b',
        ],
        'product_research': [
            r'\b(?:review|best|top|recommend|compare|vs|versus)\b',
            r'\b(?:rating|rated|opinion|alternative|competitor)\b',
        ],
        'navigation': [
            r'^(?:facebook|twitter|github|youtube|google|amazon|reddit|stackoverflow)',
            r'\b(?:login|sign in|signin|sign-in)\b',
        ],
        'research': [
            r'\b(?:tutorial|guide|how to|learn|course|class)\b',
            r'\b(?:documentation|doc|reference|manual|handbook)\b',
            r'\b(?:example|sample|code|snippet)\b',
        ],
    }
    
    # Japanese patterns
    INTENT_PATTERNS_JA = {
        'question': [
            r'\s(?:\u3068\u306f|\u3067\u3059\u304b|\u3092\u3069\u3046)',
            r'\?\s*$',
        ],
        'debugging': [
            r'\b(?:\u30a8\u30e9\u30fc|\u30d0\u30b0|\u52d5\u304b\u306a\u3044|\u30af\u30e9\u30c3\u30b7\u30e5)\b',
        ],
        'transactional': [
            r'\b(?:\u8cfc\u5165|\u5c02\u96f6|\u5024\u6bb5|\u8cb7\u3046)\b',
        ],
        'product_research': [
            r'\b(?:\u30ec\u30d3\u30e5\u30fc|\u304a\u3059\u3059\u3081|\u6bd4\u8f03|\u9055\u3044)\b',
        ],
        'research': [
            r'\b(?:\u30c1\u30e5\u30fc\u30c8\u30ea\u30a2\u30eb|\u30ac\u30a4\u30c9|\u53c2\u8003\u3088\u308a|\u8aad\u307f\u3082\u306e)\b',
        ],
    }
    
    # Expertise level patterns
    EXPERTISE_PATTERNS = {
        'beginner': [
            r'\b(?:for beginners|introduction|basics|101|start|getting started)\b',
            r'\b(?:\u521d\u5fc3\u8005\u5411\u3051|\u5165\u9580|\u308f\u304b\u308a\u3084\u3059\u3044)\b',
        ],
        'intermediate': [
            r'\b(?:advanced|intermediate|tutorial|guide|best practices)\b',
            r'\b(?:\u767a\u8cac\u6cd5|\u5b9f\u8df5|\u30c6\u30af\u30cb\u30c3\u30af)\b',
        ],
        'expert': [
            r'\b(?:RFC|whitepaper|architecture|research paper|academic)\b',
            r'\b(?:\u4ed5\u69d8\u66f8|\u30db\u30ef\u30a4\u30c8\u30da\u30fc\u30d1\u30fc|\u7814\u7a76\u8da3\u65e8)\b',
        ],
    }
    
    @staticmethod
    def detect_intent(query: str) -> Dict:
        """Detect search intent from query."""
        query_lower = query.lower().strip()
        
        # Combine English and Japanese patterns
        all_patterns = IntentDetector.INTENT_PATTERNS.copy()
        for intent_type, patterns in IntentDetector.INTENT_PATTERNS_JA.items():
            if intent_type in all_patterns:
                all_patterns[intent_type].extend(patterns)
            else:
                all_patterns[intent_type] = patterns
        
        # Score each intent type
        scores = {}
        for intent_type, patterns in all_patterns.items():
            score = 0.0
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    score += 0.3
            scores[intent_type] = min(1.0, score)
        
        # Find primary intent
        primary_intent = max(scores, key=scores.get)
        confidence = scores[primary_intent]
        
        # If no strong match, default to informational
        if confidence < 0.3:
            primary_intent = 'informational'
            confidence = 0.2
        
        # Detect expertise level
        expertise = IntentDetector._detect_expertise_level(query)
        
        return {
            'primary_intent': primary_intent,
            'intent_confidence': confidence,
            'all_intent_scores': scores,
            'typical_user_expertise': expertise,
        }
    
    @staticmethod
    def _detect_expertise_level(query: str) -> str:
        """Detect typical user expertise level for this query."""
        query_lower = query.lower()
        
        for level, patterns in IntentDetector.EXPERTISE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    return level
        
        return 'intermediate'  # default
    
    @staticmethod
    async def store_intent(
        session: AsyncSession,
        query_cluster_id: int,
        intent_data: Dict,
    ) -> None:
        """Store intent classification in database."""
        await session.execute(
            text("""
                INSERT INTO intent_classifications (
                    query_cluster_id,
                    primary_intent,
                    intent_confidence,
                    typical_user_expertise,
                    best_performing_content_type
                )
                VALUES (
                    :cluster_id,
                    :intent,
                    :confidence,
                    :expertise,
                    NULL
                )
                ON CONFLICT (query_cluster_id) DO UPDATE
                SET primary_intent = EXCLUDED.primary_intent,
                    intent_confidence = EXCLUDED.intent_confidence,
                    typical_user_expertise = EXCLUDED.typical_user_expertise
            """),
            {
                'cluster_id': query_cluster_id,
                'intent': intent_data.get('primary_intent', 'informational'),
                'confidence': intent_data.get('intent_confidence', 0.0),
                'expertise': intent_data.get('typical_user_expertise', 'intermediate'),
            },
        )
    
    @staticmethod
    def get_best_content_type_for_intent(intent: str) -> str:
        """Recommend best content type for given intent."""
        recommendations = {
            'question': 'text_article',  # Detailed explanations
            'debugging': 'text_article',  # Code examples, tutorials
            'transactional': 'tool',  # Shopping interfaces
            'product_research': 'forum',  # Reviews, user opinions
            'navigation': 'tool',  # Direct access to service
            'research': 'text_article',  # In-depth guides
            'informational': 'text_article',  # General information
        }
        return recommendations.get(intent, 'text_article')
    
    @staticmethod
    def calculate_intent_match_score(intent: str, content_type: str) -> float:
        """Calculate how well content type matches the intent."""
        matches = {
            ('question', 'text_article'): 1.0,
            ('question', 'forum'): 0.8,
            ('question', 'video'): 0.7,
            
            ('debugging', 'text_article'): 1.0,
            ('debugging', 'forum'): 0.9,
            ('debugging', 'video'): 0.7,
            
            ('transactional', 'tool'): 1.0,
            ('transactional', 'image'): 0.6,
            
            ('product_research', 'forum'): 1.0,
            ('product_research', 'text_article'): 0.9,
            ('product_research', 'video'): 0.8,
            
            ('navigation', 'tool'): 1.0,
            
            ('research', 'text_article'): 1.0,
            ('research', 'video'): 0.8,
            ('research', 'forum'): 0.7,
        }
        
        return matches.get((intent, content_type), 0.5)  # default neutral score


if __name__ == '__main__':
    # Test examples
    test_queries = [
        'How to install Docker?',
        'python list index out of range error',
        'buy MacBook Pro',
        'best VPN review',
        'facebook login',
        'React tutorial',
        'what is machine learning',
        'Dockerの使い方は?',
        'Python エラー修正',
    ]
    
    for query in test_queries:
        result = IntentDetector.detect_intent(query)
        print(f"Query: {query}")
        print(f"  Intent: {result['primary_intent']} ({result['intent_confidence']:.2f})")
        print(f"  Expertise: {result['typical_user_expertise']}")
        print()
