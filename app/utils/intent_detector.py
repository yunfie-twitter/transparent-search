import re
from typing import Tuple, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class IntentDetector:
    """
    Detect search intent from query strings.
    Types: navigation, informational, transactional, question, research, debugging, product_research
    """

    # Rule-based patterns for intent detection
    INTENT_PATTERNS = {
        'question': [
            r'^(\w+\s)?(?:what|which|who|when|where|why|how)',
            r'(\?)$',
            r'\s(?:とは|ですか|ですか\?)',  # Japanese
        ],
        'navigation': [
            r'\b(?:login|sign in|signin|signup|register|facebook|twitter|github)',
            r'^(?:facebook|google|youtube|twitter)',
        ],
        'transactional': [
            r'\b(?:buy|purchase|price|shop|store|cart|checkout)',
            r'\b(?:最安値|激安|割引|セール)',  # Japanese for cheapest, discount
        ],
        'debugging': [
            r'\b(?:error|bug|fix|issue|problem|not working|crash)',
            r'\b(?:エラー|バグ|fix|動かない|クラッシュ)',  # Japanese
        ],
        'research': [
            r'\b(?:learn|tutorial|guide|how to|documentation)',
            r'\b(?:学習|チュートリアル|ガイド|ドキュメント)',
        ],
        'product_research': [
            r'\b(?:review|best|recommend|compare|vs|versus|difference)',
            r'\b(?:レビュー|おすすめ|比較|違い)',
        ],
    }

    # Expertise level indicators
    EXPERTISE_PATTERNS = {
        'beginner': [
            r'\b(?:for beginners|getting started|introduction|basics|fundamentals)',
            r'\b(?:初心者向け|入門|基礎|わかりやすい)',
        ],
        'intermediate': [
            r'\b(?:advanced|intermediate|tutorial|guide)',
        ],
        'expert': [
            r'\b(?:RFC|spec|whitepaper|implementation|architecture)',
            r'\b(?:仕様書|ホワイトペーパー|実装|アーキテクチャ)',
        ],
    }

    @staticmethod
    async def detect_intent(query: str, db: AsyncSession = None) -> Tuple[str, float]:
        """
        Detect search intent from query.
        Returns (primary_intent, confidence)
        """
        query_lower = query.lower()
        scores = {}
        
        # Pattern matching
        for intent, patterns in IntentDetector.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    score += 1
            scores[intent] = min(1.0, score * 0.3)  # Cap at 1.0
        
        # Default to informational if no strong signal
        if max(scores.values()) < 0.3:
            scores['informational'] = 0.6
        else:
            scores['informational'] = scores.get('informational', 0.2)
        
        # Determine primary intent
        primary_intent = max(scores, key=scores.get)
        confidence = scores[primary_intent]
        
        return primary_intent, confidence

    @staticmethod
    def detect_expertise_level(query: str) -> str:
        """
        Detect target expertise level from query.
        """
        query_lower = query.lower()
        
        for level, patterns in IntentDetector.EXPERTISE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    return level
        
        return 'intermediate'  # Default

    @staticmethod
    async def store_intent(db: AsyncSession, query_cluster_id: int, intent_type: str, confidence: float):
        """
        Store intent classification in database.
        """
        expertise = IntentDetector.detect_expertise_level(
            (await db.execute(text("""
                SELECT canonical_query FROM query_clusters WHERE id = :id
            """), {'id': query_cluster_id})).scalar() or ''
        )
        
        await db.execute(
            text("""
                INSERT INTO intent_classifications
                (query_cluster_id, primary_intent, intent_confidence, typical_user_expertise)
                VALUES (:cid, :intent, :conf, :expertise)
                ON CONFLICT (query_cluster_id) DO UPDATE SET
                    primary_intent = EXCLUDED.primary_intent,
                    intent_confidence = EXCLUDED.intent_confidence,
                    updated_at = NOW()
            """),
            {
                'cid': query_cluster_id,
                'intent': intent_type,
                'conf': confidence,
                'expertise': expertise
            }
        )
