import re
from typing import List, Dict, Tuple
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class TrackerDetector:
    """
    Detects tracking scripts and services on web pages.
    Maintains a database of known trackers with risk levels.
    """

    # Known tracker domains with risk levels (1-5)
    KNOWN_TRACKERS = {
        # Analytics
        'google-analytics.com': {'name': 'Google Analytics', 'category': 'analytics', 'risk': 2},
        'googletagmanager.com': {'name': 'Google Tag Manager', 'category': 'analytics', 'risk': 2},
        'segment.com': {'name': 'Segment', 'category': 'analytics', 'risk': 3},
        'amplitude.com': {'name': 'Amplitude', 'category': 'analytics', 'risk': 2},
        'mixpanel.com': {'name': 'Mixpanel', 'category': 'analytics', 'risk': 3},
        
        # Advertising
        'doubleclick.net': {'name': 'Google Ads', 'category': 'advertising', 'risk': 4},
        'facebook.com': {'name': 'Facebook Pixel', 'category': 'advertising', 'risk': 4},
        'criteo.com': {'name': 'Criteo', 'category': 'advertising', 'risk': 4},
        'amazon-adsystem.com': {'name': 'Amazon Ads', 'category': 'advertising', 'risk': 3},
        
        # Heatmap/Session Recording (highest privacy risk)
        'hotjar.com': {'name': 'Hotjar', 'category': 'heatmap', 'risk': 5},
        'fullstory.com': {'name': 'FullStory', 'category': 'heatmap', 'risk': 5},
        'mouseflow.com': {'name': 'Mouseflow', 'category': 'heatmap', 'risk': 5},
        'sessioncam.com': {'name': 'SessionCam', 'category': 'heatmap', 'risk': 5},
        
        # Social
        'facebook.net': {'name': 'Facebook', 'category': 'social', 'risk': 4},
        'twitter.com': {'name': 'Twitter', 'category': 'social', 'risk': 3},
        'linkedin.com': {'name': 'LinkedIn', 'category': 'social', 'risk': 3},
    }

    @staticmethod
    async def detect_trackers(html: str, page_url: str) -> Dict:
        """
        Detect all tracking scripts in HTML.
        Returns dict with tracker list and risk score.
        """
        soup = BeautifulSoup(html, 'lxml')
        detected_trackers = []
        risk_sum = 0
        risk_count = 0

        # 1. Detect script tags
        for script in soup.find_all('script'):
            src = script.get('src', '')
            if src:
                tracker = TrackerDetector._check_tracker_url(src)
                if tracker:
                    detected_trackers.append({
                        'domain': tracker['domain'],
                        'name': tracker['name'],
                        'category': tracker['category'],
                        'risk': tracker['risk'],
                        'method': 'script_src'
                    })
                    risk_sum += tracker['risk']
                    risk_count += 1

        # 2. Detect image pixels (tracking pixels)
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if 'pixel' in src.lower() or 'beacon' in src.lower():
                tracker = TrackerDetector._check_tracker_url(src)
                if tracker:
                    detected_trackers.append({
                        'domain': tracker['domain'],
                        'name': tracker['name'],
                        'category': tracker['category'],
                        'risk': tracker['risk'],
                        'method': 'img_pixel'
                    })
                    risk_sum += tracker['risk']
                    risk_count += 1

        # 3. Detect iframe embeds
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src', '')
            if src:
                tracker = TrackerDetector._check_tracker_url(src)
                if tracker:
                    detected_trackers.append({
                        'domain': tracker['domain'],
                        'name': tracker['name'],
                        'category': tracker['category'],
                        'risk': tracker['risk'],
                        'method': 'iframe'
                    })
                    risk_sum += tracker['risk']
                    risk_count += 1

        # 4. Detect inline script patterns
        for script in soup.find_all('script'):
            if script.string:
                # Look for common tracker patterns
                content = script.string
                
                # Google Analytics pattern
                if 'ga(' in content or 'gtag(' in content:
                    detected_trackers.append({
                        'domain': 'google-analytics.com',
                        'name': 'Google Analytics',
                        'category': 'analytics',
                        'risk': 2,
                        'method': 'script_inline'
                    })
                    risk_sum += 2
                    risk_count += 1
                
                # Facebook Pixel pattern
                if 'fbq(' in content:
                    detected_trackers.append({
                        'domain': 'facebook.com',
                        'name': 'Facebook Pixel',
                        'category': 'advertising',
                        'risk': 4,
                        'method': 'script_inline'
                    })
                    risk_sum += 4
                    risk_count += 1

        # Calculate tracker risk score (0.5 = very risky, 1.0 = clean)
        if risk_count == 0:
            tracker_risk_score = 1.0
        else:
            avg_risk = risk_sum / risk_count
            # Formula: 1.0 - (avg_risk / 5) with penalty for count
            tracker_risk_score = max(0.1, 1.0 - (avg_risk / 5.0) - (min(0.2, risk_count * 0.05)))

        # Deduplicate trackers
        unique_trackers = {}
        for t in detected_trackers:
            key = t['domain']
            if key not in unique_trackers:
                unique_trackers[key] = t

        return {
            'trackers': list(unique_trackers.values()),
            'tracker_count': len(unique_trackers),
            'tracker_risk_score': tracker_risk_score,
            'risk_profile': TrackerDetector._get_risk_profile(tracker_risk_score)
        }

    @staticmethod
    def _check_tracker_url(url: str) -> Dict or None:
        """
        Check if a URL matches known tracker domains.
        """
        from urllib.parse import urlparse
        
        try:
            domain = urlparse(url).netloc
            domain_lower = domain.lower()
            
            # Direct match
            if domain_lower in TrackerDetector.KNOWN_TRACKERS:
                info = TrackerDetector.KNOWN_TRACKERS[domain_lower].copy()
                info['domain'] = domain_lower
                return info
            
            # Subdomain match
            for tracker_domain, tracker_info in TrackerDetector.KNOWN_TRACKERS.items():
                if domain_lower.endswith('.' + tracker_domain) or domain_lower == tracker_domain:
                    info = tracker_info.copy()
                    info['domain'] = tracker_domain
                    return info
        except:
            pass
        
        return None

    @staticmethod
    def _get_risk_profile(score: float) -> str:
        """
        Categorize tracker risk score.
        """
        if score >= 0.9:
            return 'clean'
        elif score >= 0.7:
            return 'minimal_trackers'
        elif score >= 0.5:
            return 'moderate_trackers'
        elif score >= 0.3:
            return 'heavy_trackers'
        else:
            return 'severe_tracking_risk'

    @staticmethod
    async def store_trackers(db: AsyncSession, page_id: int, trackers: List[Dict]):
        """
        Store detected trackers in database.
        """
        for tracker_info in trackers:
            # Get or create tracker
            result = await db.execute(
                text("""
                    SELECT id FROM trackers WHERE domain = :domain
                """),
                {'domain': tracker_info['domain']}
            )
            tracker_id = result.scalar()
            
            if not tracker_id:
                result = await db.execute(
                    text("""
                        INSERT INTO trackers (domain, name, category, risk_level)
                        VALUES (:domain, :name, :category, :risk)
                        RETURNING id
                    """),
                    {
                        'domain': tracker_info['domain'],
                        'name': tracker_info['name'],
                        'category': tracker_info['category'],
                        'risk': tracker_info['risk']
                    }
                )
                tracker_id = result.scalar()
            
            # Link tracker to page
            await db.execute(
                text("""
                    INSERT INTO page_trackers (page_id, tracker_id, detection_method)
                    VALUES (:page_id, :tracker_id, :method)
                    ON CONFLICT DO NOTHING
                """),
                {
                    'page_id': page_id,
                    'tracker_id': tracker_id,
                    'method': tracker_info.get('method', 'unknown')
                }
            )
