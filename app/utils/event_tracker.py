import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

class EventTracker:
    """
    Handles session management and event tracking for collective intelligence.
    
    Key design principles:
    - IP-based tracking using secure hashing (not storing raw IPs)
    - Time-aware session management
    - Anomaly detection for bot/spam
    """

    SESSION_TIMEOUT = timedelta(hours=24)  # Expire sessions after 24h
    SUSPICIOUS_CLICK_THRESHOLD = 10  # Clicks in < 1 minute = suspicious

    @staticmethod
    def hash_ip(ip_address: str) -> str:
        """Hash IP address for privacy."""
        return hashlib.sha256(f"ip_{ip_address}".encode()).hexdigest()[:16]

    @staticmethod
    def hash_ua(user_agent: str) -> str:
        """Hash User-Agent for privacy."""
        return hashlib.sha256(f"ua_{user_agent}".encode()).hexdigest()[:16]

    @staticmethod
    def hash_session_id(ip_hash: str, ua_hash: str) -> str:
        """Create session hash from IP + UA."""
        return hashlib.sha256(f"{ip_hash}_{ua_hash}".encode()).hexdigest()

    @staticmethod
    async def get_or_create_session(
        db: AsyncSession,
        ip_address: str,
        user_agent: str
    ) -> int:
        """
        Get or create a session for tracking.
        Returns session_id.
        """
        ip_hash = EventTracker.hash_ip(ip_address)
        ua_hash = EventTracker.hash_ua(user_agent)
        session_hash = EventTracker.hash_session_id(ip_hash, ua_hash)

        # Check if session exists and is still active
        result = await db.execute(
            text("""
                SELECT id FROM sessions
                WHERE session_hash = :hash
                AND last_activity_at > NOW() - INTERVAL '24 hours'
                LIMIT 1
            """),
            {"hash": session_hash}
        )
        row = result.fetchone()
        if row:
            # Update last activity
            await db.execute(
                text("UPDATE sessions SET last_activity_at = NOW() WHERE id = :id"),
                {"id": row.id}
            )
            return row.id

        # Create new session
        result = await db.execute(
            text("""
                INSERT INTO sessions (session_hash, ip_hash, user_agent_hash, trust_score)
                VALUES (:hash, :ip, :ua, :trust)
                RETURNING id
            """),
            {"hash": session_hash, "ip": ip_hash, "ua": ua_hash, "trust": 0.5}
        )
        return result.scalar()

    @staticmethod
    async def record_search_event(
        db: AsyncSession,
        session_id: int,
        query: str,
        results_count: int,
        took_ms: int,
        intent_type: Optional[str] = None,
        intent_confidence: Optional[float] = None
    ) -> int:
        """
        Record a search event.
        Returns search_event_id.
        """
        # Get query cluster (simplified: use query itself for now)
        # TODO: Implement proper query clustering with aliases
        result = await db.execute(
            text("""
                SELECT id FROM query_clusters
                WHERE canonical_query = :query
                LIMIT 1
            """),
            {"query": query}
        )
        cluster_id = result.scalar()

        # If no cluster exists, create one
        if not cluster_id:
            result = await db.execute(
                text("""
                    INSERT INTO query_clusters (canonical_query, intent_type)
                    VALUES (:query, :intent)
                    RETURNING id
                """),
                {"query": query, "intent": intent_type or "unknown"}
            )
            cluster_id = result.scalar()

        # Record search event
        result = await db.execute(
            text("""
                INSERT INTO search_events (
                    session_id, query, normalized_query, query_cluster_id,
                    intent_type, intent_confidence, results_count, took_ms
                )
                VALUES (:sid, :q, :nq, :cid, :it, :ic, :rc, :t)
                RETURNING id
            """),
            {
                "sid": session_id,
                "q": query,
                "nq": query,  # TODO: Implement normalization
                "cid": cluster_id,
                "it": intent_type,
                "ic": intent_confidence,
                "rc": results_count,
                "t": took_ms
            }
        )
        return result.scalar()

    @staticmethod
    async def record_click_event(
        db: AsyncSession,
        search_event_id: int,
        page_id: int,
        rank_position: int,
        time_to_click_ms: int,
        time_on_page_ms: int,
        scroll_depth: float = 0.0,
        interaction_signals: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Record a click event with interaction metrics.
        Automatically determines success signal based on heuristics.
        
        Success signals:
        - time_on_page > 30 seconds
        - scroll_depth > 0.5
        - interaction (copy, expand, etc.)
        """
        # Determine success
        is_success = (
            time_on_page_ms > 30000 or  # 30+ seconds
            scroll_depth > 0.5 or  # scrolled >50%
            (interaction_signals and any(v for k, v in interaction_signals.items()))
        )

        success_reason = None
        if is_success:
            if time_on_page_ms > 30000:
                success_reason = "long_stay"
            elif scroll_depth > 0.5:
                success_reason = "thorough_read"
            else:
                success_reason = "interaction"

        result = await db.execute(
            text("""
                INSERT INTO click_events (
                    search_event_id, page_id, rank_position,
                    time_to_click_ms, time_on_page_ms, scroll_depth,
                    interaction_signals, is_success_signal, success_reason
                )
                VALUES (:se, :p, :r, :ttc, :top, :sd, :sig, :suc, :sr)
                RETURNING id
            """),
            {
                "se": search_event_id,
                "p": page_id,
                "r": rank_position,
                "ttc": time_to_click_ms,
                "top": time_on_page_ms,
                "sd": scroll_depth,
                "sig": json.dumps(interaction_signals) if interaction_signals else None,
                "suc": is_success,
                "sr": success_reason
            }
        )
        return result.scalar()

    @staticmethod
    async def record_re_search(
        db: AsyncSession,
        previous_search_event_id: int,
        time_to_next_search_ms: int
    ):
        """
        Record that user re-searched after a click.
        This helps determine if previous click was a 'success' or not.
        """
        # Update click events to mark they weren't terminal
        await db.execute(
            text("""
                UPDATE click_events
                SET next_search_time_ms = :time,
                    is_terminal_click = FALSE
                WHERE search_event_id = :se
            """),
            {"se": previous_search_event_id, "time": time_to_next_search_ms}
        )

    @staticmethod
    async def update_success_matrix(db: AsyncSession):
        """
        Batch update page_success_matrix from click_events.
        Should be called periodically (e.g., every hour).
        """
        # Extract success patterns
        await db.execute(text("""
            INSERT INTO page_success_matrix
            (
                query_cluster_id, page_id,
                impressions, success_events, click_count,
                first_seen_at, last_updated_at
            )
            SELECT
                se.query_cluster_id,
                ce.page_id,
                COUNT(DISTINCT se.id)::INT as impressions,
                COUNT(CASE WHEN ce.is_success_signal THEN 1 END)::INT as success_events,
                COUNT(ce.id)::INT as click_count,
                MIN(ce.clicked_at),
                NOW()
            FROM search_events se
            LEFT JOIN click_events ce ON se.id = ce.search_event_id
            WHERE se.created_at > NOW() - INTERVAL '7 days'
            GROUP BY se.query_cluster_id, ce.page_id
            ON CONFLICT (query_cluster_id, page_id)
            DO UPDATE SET
                impressions = page_success_matrix.impressions + EXCLUDED.impressions,
                success_events = page_success_matrix.success_events + EXCLUDED.success_events,
                click_count = page_success_matrix.click_count + EXCLUDED.click_count,
                last_updated_at = NOW()
        """))

    @staticmethod
    async def detect_anomalies(db: AsyncSession):
        """
        Detect suspicious patterns and mark sessions.
        Patterns:
        - Rapid clicks (>10 clicks in 1 minute)
        - Identical clicks (same page, immediately)
        - Unusual patterns (all top results clicked)
        """
        # Pattern 1: Rapid clicks
        result = await db.execute(text("""
            SELECT se.session_id, COUNT(ce.id) as click_count
            FROM search_events se
            LEFT JOIN click_events ce ON se.id = ce.search_event_id
            WHERE se.created_at > NOW() - INTERVAL '1 minute'
            GROUP BY se.session_id
            HAVING COUNT(ce.id) > :threshold
        """), {"threshold": EventTracker.SUSPICIOUS_CLICK_THRESHOLD})

        for row in result.fetchall():
            session_id = row[0]
            await db.execute(text("""
                INSERT INTO anomaly_detections (session_id, anomaly_type, severity, action_taken)
                VALUES (:sid, 'rapid_click_pattern', 3, 'weight_reduced')
            """), {"sid": session_id})
            
            await db.execute(text("""
                UPDATE sessions SET is_anomalous = TRUE, trust_score = trust_score * 0.5
                WHERE id = :id
            """), {"id": session_id})

    @staticmethod
    async def calculate_session_trust(
        db: AsyncSession,
        session_id: int
    ) -> float:
        """
        Calculate trust score for a session based on:
        - Days of activity
        - Consistency of behavior
        - Success rate of clicks
        - Anomaly history
        """
        result = await db.execute(text("""
            SELECT
                EXTRACT(DAY FROM NOW() - first_search_at) as days_old,
                COUNT(se.id) as total_searches,
                COUNT(CASE WHEN ce.is_success_signal THEN 1 END)::FLOAT /
                    NULLIF(COUNT(ce.id), 0) as success_rate,
                COUNT(DISTINCT a.id) as anomaly_count
            FROM sessions s
            LEFT JOIN search_events se ON s.id = se.session_id
            LEFT JOIN click_events ce ON se.id = ce.search_event_id
            LEFT JOIN anomaly_detections a ON s.id = a.session_id
            WHERE s.id = :sid
            GROUP BY s.id
        """), {"sid": session_id})

        row = result.fetchone()
        if not row:
            return 0.5

        days_old, total_searches, success_rate, anomaly_count = row
        
        # Trust formula
        trust = 0.5  # Base
        trust += min(0.3, days_old / 30) if days_old else 0  # Long-term usage
        trust += min(0.2, total_searches / 50) if total_searches else 0  # Activity
        trust += (success_rate * 0.2) if success_rate else 0  # Successful clicks
        trust -= min(0.5, anomaly_count * 0.1)  # Anomaly penalty
        
        return max(0.1, min(1.5, trust))  # Clamp [0.1, 1.5]

    @staticmethod
    async def apply_time_decay(
        db: AsyncSession,
        lambda_decay: float = 0.1
    ):
        """
        Apply exponential time decay to old success records.
        λ = 0.1 means 30-day-old data has weight 0.05x
        """
        await db.execute(text("""
            UPDATE page_success_matrix
            SET time_decay_factor = EXP(-:lambda * EXTRACT(DAY FROM NOW() - last_updated_at))
            WHERE last_updated_at < NOW() - INTERVAL '1 day'
        """), {"lambda": lambda_decay})
