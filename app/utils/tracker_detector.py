"""Tracker Detection Module - Identify privacy-invasive scripts and services."""

import re
import json
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Comprehensive tracker database
TRACKER_DATABASE = {
    # Analytics (Risk Level 2-3)
    'google_analytics': {
        'risk': 2,
        'patterns': [r'google-analytics', r'ga\(', r'gtag\(', r'_gid', r'_ga'],
    },
    'gtag': {'risk': 2, 'patterns': [r'googletagmanager', r'gtag\(']},
    'amplitude': {'risk': 2, 'patterns': [r'amplitude\.com', r'amplitude\(']},
    'mixpanel': {'risk': 2, 'patterns': [r'mixpanel', r'mixpanel\.track']},
    
    # Advertising Networks (Risk Level 3-4)
    'facebook_pixel': {
        'risk': 4,
        'patterns': [r'facebook\.com/tr', r'fbq\(', r'pixel', r'_fbp'],
    },
    'google_ads': {
        'risk': 3,
        'patterns': [r'google\.com/ads', r'pagead', r'gstatic\.com/ads'],
    },
    'criteo': {'risk': 3, 'patterns': [r'criteo\.com', r'criteo\.net']},
    'twitter_pixel': {'risk': 3, 'patterns': [r'twitter\.com.*pixel', r'twq\(']},
    'tiktok_pixel': {'risk': 3, 'patterns': [r'tiktok\.com.*pixel']},
    
    # Session Recording (Risk Level 5)
    'hotjar': {
        'risk': 5,
        'patterns': [r'hotjar', r'hj\.']],
    },
    'fullstory': {
        'risk': 5,
        'patterns': [r'fullstory', r'_fs_', r'FS\.replaySession'],
    },
    'sessioncam': {
        'risk': 5,
        'patterns': [r'sessioncam', r'_scc'],
    },
    'smartlook': {
        'risk': 5,
        'patterns': [r'smartlook', r'smartlook\.com'],
    },
    
    # Heatmaps (Risk Level 4)
    'microsoft_clarity': {
        'risk': 4,
        'patterns': [r'clarity\.ms', r'clarity\('],
    },
    'contentsquare': {
        'risk': 4,
        'patterns': [r'contentsquare', r'contentsquarecdn'],
    },
    
    # A/B Testing (Risk Level 2)
    'optimizely': {'risk': 2, 'patterns': [r'optimizely', r'optimizely\.com']},
    'convert': {'risk': 2, 'patterns': [r'convertkit', r'convertexperiments']},
    
    # CDN / Third-party (Risk Level 1)
    'cloudflare': {'risk': 1, 'patterns': [r'cloudflare\.com']},
    'cdn': {'risk': 1, 'patterns': [r'cdn', r'jsdelivr', r'unpkg']},
}


class TrackerDetector:
    """Detect privacy-invasive trackers on web pages."""

    @staticmethod
    async def detect_trackers(html: str, url: str) -> Dict:
        """Detect all trackers in HTML."""
        trackers_found = []
        
        # Pattern 1: Script tags
        script_pattern = r'<script[^>]*src=["\']?([^"\'>\s]+)'
        for match in re.finditer(script_pattern, html, re.IGNORECASE):
            src = match.group(1)
            tracker = TrackerDetector._identify_tracker(src)
            if tracker:
                trackers_found.append({
                    'name': tracker['name'],
                    'risk': tracker['risk'],
                    'type': 'script',
                    'url': src,
                })
        
        # Pattern 2: Inline scripts
        inline_pattern = r'<script[^>]*>([^<]+)</script>'
        for match in re.finditer(inline_pattern, html, re.IGNORECASE | re.DOTALL):
            content = match.group(1)
            tracker = TrackerDetector._identify_tracker_in_code(content)
            if tracker:
                trackers_found.append({
                    'name': tracker['name'],
                    'risk': tracker['risk'],
                    'type': 'inline_script',
                    'snippet': content[:100],
                })
        
        # Pattern 3: Tracking pixels (1x1 images)
        pixel_pattern = r'<img[^>]*src=["\']?([^"\'>\s]+)'
        for match in re.finditer(pixel_pattern, html, re.IGNORECASE):
            src = match.group(1)
            if 'pixel' in src.lower() or 'beacon' in src.lower():
                tracker = TrackerDetector._identify_tracker(src)
                if tracker or 'pixel' in src.lower():
                    trackers_found.append({
                        'name': tracker['name'] if tracker else 'unknown_pixel',
                        'risk': tracker['risk'] if tracker else 3,
                        'type': 'pixel',
                        'url': src,
                    })
        
        # Pattern 4: iframes
        iframe_pattern = r'<iframe[^>]*src=["\']?([^"\'>\s]+)'
        for match in re.finditer(iframe_pattern, html, re.IGNORECASE):
            src = match.group(1)
            tracker = TrackerDetector._identify_tracker(src)
            if tracker:
                trackers_found.append({
                    'name': tracker['name'],
                    'risk': tracker['risk'],
                    'type': 'iframe',
                    'url': src,
                })
        
        # Remove duplicates
        unique_trackers = {}
        for t in trackers_found:
            key = (t['name'], t['type'])
            if key not in unique_trackers:
                unique_trackers[key] = t
        
        trackers_found = list(unique_trackers.values())
        
        # Calculate risk profile
        if not trackers_found:
            risk_profile = 'clean'
            avg_risk = 1.0
        else:
            risks = [t['risk'] for t in trackers_found]
            avg_risk = sum(risks) / len(risks)
            
            if avg_risk >= 4.5:
                risk_profile = 'severe_tracking_risk'
            elif avg_risk >= 3.5:
                risk_profile = 'heavy_trackers'
            elif avg_risk >= 2.5:
                risk_profile = 'moderate_trackers'
            elif avg_risk >= 1.5:
                risk_profile = 'minimal_trackers'
            else:
                risk_profile = 'clean'
        
        # Calculate tracker risk score (0-1)
        # Formula: score = 1.0 - (avg_risk / 5) - (tracker_count * 0.05)
        risk_score = 1.0 - (avg_risk / 5) - (len(trackers_found) * 0.05)
        risk_score = max(0.1, min(1.0, risk_score))  # Clamp to [0.1, 1.0]
        
        return {
            'trackers': trackers_found,
            'tracker_count': len(trackers_found),
            'tracker_risk_score': risk_score,
            'risk_profile': risk_profile,
            'average_risk_level': avg_risk,
        }
    
    @staticmethod
    def _identify_tracker(url_or_code: str) -> Optional[Dict]:
        """Identify tracker from URL or code snippet."""
        for tracker_name, tracker_info in TRACKER_DATABASE.items():
            for pattern in tracker_info.get('patterns', []):
                if re.search(pattern, url_or_code, re.IGNORECASE):
                    return {
                        'name': tracker_name,
                        'risk': tracker_info['risk'],
                    }
        return None
    
    @staticmethod
    def _identify_tracker_in_code(code: str) -> Optional[Dict]:
        """Identify tracker from inline JavaScript code."""
        # Look for specific patterns like ga(, fbq(, gtag(, etc
        patterns_to_check = [
            (r'ga\(', 'google_analytics', 2),
            (r'gtag\(', 'gtag', 2),
            (r'fbq\(', 'facebook_pixel', 4),
            (r'twq\(', 'twitter_pixel', 3),
            (r'hj\(', 'hotjar', 5),
            (r'_fs_\(', 'fullstory', 5),
            (r'amplitude\.track', 'amplitude', 2),
            (r'mixpanel\.track', 'mixpanel', 2),
        ]
        
        for pattern, name, risk in patterns_to_check:
            if re.search(pattern, code, re.IGNORECASE):
                return {'name': name, 'risk': risk}
        
        return None
    
    @staticmethod
    async def store_trackers(
        session: AsyncSession, page_id: int, trackers: List[Dict]
    ) -> None:
        """Store detected trackers in database."""
        # First, create/update tracker entries
        for tracker in trackers:
            # Insert or get tracker
            result = await session.execute(
                text("""
                    INSERT INTO trackers (name, risk_level)
                    VALUES (:name, :risk)
                    ON CONFLICT (name) DO UPDATE
                    SET risk_level = EXCLUDED.risk_level
                    RETURNING id
                """),
                {'name': tracker['name'], 'risk': tracker['risk']},
            )
            tracker_id = result.scalar()
            
            # Link to page
            await session.execute(
                text("""
                    INSERT INTO page_trackers (page_id, tracker_id, type, url, snippet)
                    VALUES (:page_id, :tracker_id, :type, :url, :snippet)
                    ON CONFLICT (page_id, tracker_id, type) DO NOTHING
                """),
                {
                    'page_id': page_id,
                    'tracker_id': tracker_id,
                    'type': tracker.get('type', 'unknown'),
                    'url': tracker.get('url', None),
                    'snippet': tracker.get('snippet', None),
                },
            )


if __name__ == '__main__':
    import asyncio
    
    test_html = """
    <html>
    <head>
    <script async src="https://www.googletagmanager.com/gtag/js?id=GA_ID"></script>
    <script>
    gtag('config', 'GA_ID');
    </script>
    <script src="https://cdn.hotjar.com/hotjar.js"></script>
    </head>
    <body>
    <img src="https://facebook.com/tr?id=...&pixel..." />
    </body>
    </html>
    """
    
    result = asyncio.run(TrackerDetector.detect_trackers(test_html, 'https://example.com'))
    print(json.dumps(result, indent=2))
