"""Detect link farms, SEO spam, and blackhat techniques."""
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict
import re
from urllib.parse import urlparse
import socket
from ipaddress import ip_address, IPv4Address, IPv6Address


@dataclass
class SpamSignal:
    """Individual spam detection signal."""
    signal_type: str  # "link_farm", "cms_pattern", "ip_cluster", "reciprocal_links", etc.
    severity: str  # "low", "medium", "high", "critical"
    confidence: float  # 0-1
    description: str
    evidence: List[str]


@dataclass
class SpamReport:
    """Complete spam analysis report."""
    domain: str
    spam_score: float  # 0-100
    risk_level: str  # "clean", "suspicious", "spam"
    signals: List[SpamSignal]
    is_link_farm: bool
    is_pbn_candidate: bool  # Private Blog Network
    has_duplicated_content: bool
    cms_fingerprint: Optional[str]
    ip_risk_score: float  # 0-100, based on IP reputation
    recommendations: List[str]


class SpamDetector:
    """Detects spam, link farms, and blackhat SEO techniques."""
    
    # Common spam hosting patterns
    SPAM_IP_RANGES = {
        # Bulletproof hosting providers (examples)
        "208.89.0.0/16",
        "195.189.0.0/16",
        "185.220.100.0/24",
    }
    
    # CMS signatures (files/patterns unique to platforms)
    CMS_SIGNATURES = {
        "wordpress": [
            "/wp-content/",
            "/wp-admin/",
            "wp-json",
            "<meta name=\"generator\" content=\"WordPress\"",
        ],
        "drupal": [
            "/sites/default/",
            "drupal.settings",
            "<meta name=\"Generator\" content=\"Drupal\"",
        ],
        "joomla": [
            "/components/",
            "/modules/",
            "<meta name=\"generator\" content=\"Joomla\"",
        ],
        "wix": [
            "wixClient.js",
            "wixApi.js",
        ],
    }
    
    # Patterns indicating link farm behavior
    LINK_FARM_INDICATORS = {
        "excessive_internal_links": 200,  # More than 200 internal links
        "link_density_threshold": 0.4,  # 40% of page is links
        "irrelevant_link_anchors": 0.7,  # 70%+ generic anchor text
        "reciprocal_link_ratio": 0.8,  # 80%+ reciprocal links
    }
    
    @staticmethod
    def analyze_domain(
        domain: str,
        pages_crawled: List[Dict],
        link_graph: Dict[str, List[str]],
        cms_detected: Optional[str] = None,
        ip_address_str: Optional[str] = None,
    ) -> SpamReport:
        """
        Comprehensive spam analysis for a domain.
        
        Args:
            domain: Target domain
            pages_crawled: List of crawled page data with content
            link_graph: Domain link graph {url: [outbound_urls]}
            cms_detected: Detected CMS platform
            ip_address_str: IP address of the domain
        
        Returns:
            SpamReport with detailed findings
        """
        signals = []
        evidence = []
        
        # 1. LINK FARM DETECTION
        link_farm_signal = SpamDetector._detect_link_farm(
            pages_crawled, link_graph
        )
        if link_farm_signal:
            signals.append(link_farm_signal)
        
        # 2. CMS PATTERN ANALYSIS
        cms_signal, cms_fingerprint = SpamDetector._detect_cms_patterns(
            pages_crawled, cms_detected
        )
        if cms_signal:
            signals.append(cms_signal)
        
        # 3. CONTENT DUPLICATION
        duplication_signal = SpamDetector._detect_content_duplication(
            pages_crawled
        )
        if duplication_signal:
            signals.append(duplication_signal)
        
        # 4. RECIPROCAL LINKING
        reciprocal_signal = SpamDetector._detect_reciprocal_linking(
            domain, link_graph
        )
        if reciprocal_signal:
            signals.append(reciprocal_signal)
        
        # 5. ANCHOR TEXT ANALYSIS
        anchor_signal = SpamDetector._analyze_anchor_text(link_graph)
        if anchor_signal:
            signals.append(anchor_signal)
        
        # 6. IP REPUTATION
        ip_signal, ip_risk_score = SpamDetector._analyze_ip_reputation(
            ip_address_str
        )
        if ip_signal:
            signals.append(ip_signal)
        
        # Calculate overall spam score
        spam_score = SpamDetector._calculate_spam_score(signals)
        
        # Determine risk level
        if spam_score >= 75:
            risk_level = "spam"
        elif spam_score >= 45:
            risk_level = "suspicious"
        else:
            risk_level = "clean"
        
        # Generate recommendations
        recommendations = SpamDetector._generate_recommendations(signals, spam_score)
        
        return SpamReport(
            domain=domain,
            spam_score=spam_score,
            risk_level=risk_level,
            signals=signals,
            is_link_farm=any(s.signal_type == "link_farm" for s in signals),
            is_pbn_candidate=any(s.signal_type == "pbn_indicators" for s in signals),
            has_duplicated_content=any(s.signal_type == "content_duplication" for s in signals),
            cms_fingerprint=cms_fingerprint,
            ip_risk_score=ip_risk_score,
            recommendations=recommendations,
        )
    
    @staticmethod
    def _detect_link_farm(
        pages: List[Dict], link_graph: Dict[str, List[str]]
    ) -> Optional[SpamSignal]:
        """
        Detect if domain operates as a link farm.
        """
        indicators = []
        link_farm_score = 0.0
        
        # Check excessive internal linking
        total_links = sum(len(links) for links in link_graph.values())
        avg_links_per_page = total_links / len(link_graph) if link_graph else 0
        
        if avg_links_per_page > SpamDetector.LINK_FARM_INDICATORS["excessive_internal_links"]:
            link_farm_score += 0.4
            indicators.append(
                f"Excessive internal links: {avg_links_per_page:.0f} per page"
            )
        
        # Check link density
        for page in pages:
            if page.get("word_count", 0) > 0:
                link_density = page.get("link_count", 0) / page["word_count"]
                if link_density > SpamDetector.LINK_FARM_INDICATORS["link_density_threshold"]:
                    link_farm_score += 0.3
                    indicators.append(
                        f"High link density on {page.get('url', 'unknown')}: {link_density:.1%}"
                    )
                    break
        
        # Check outbound link ratio
        external_links = sum(
            1 for page in pages
            if page.get("external_links", 0) > page.get("internal_links", 1) * 2
        )
        if external_links > len(pages) * 0.5:  # More than 50% pages have more external than internal
            link_farm_score += 0.3
            indicators.append("Disproportionate external linking")
        
        if link_farm_score >= 0.5:
            return SpamSignal(
                signal_type="link_farm",
                severity="high" if link_farm_score >= 0.7 else "medium",
                confidence=min(1.0, link_farm_score),
                description="Domain shows characteristics of a link farm",
                evidence=indicators,
            )
        
        return None
    
    @staticmethod
    def _detect_cms_patterns(
        pages: List[Dict], detected_cms: Optional[str]
    ) -> Tuple[Optional[SpamSignal], Optional[str]]:
        """
        Detect CMS platform and flag if mismatched or suspicious.
        """
        cms_counts = defaultdict(int)
        
        # Analyze page content for CMS signatures
        for page in pages:
            content = page.get("content", "").lower()
            for cms, signatures in SpamDetector.CMS_SIGNATURES.items():
                for sig in signatures:
                    if sig.lower() in content:
                        cms_counts[cms] += 1
        
        detected = max(cms_counts, key=cms_counts.get) if cms_counts else None
        
        # Check for mixed CMS environments (suspicious)
        if len(cms_counts) >= 2:
            return SpamSignal(
                signal_type="cms_anomaly",
                severity="medium",
                confidence=0.7,
                description="Multiple CMS signatures detected (possible compromise or mixing)",
                evidence=list(cms_counts.keys()),
            ), detected
        
        return None, detected
    
    @staticmethod
    def _detect_content_duplication(pages: List[Dict]) -> Optional[SpamSignal]:
        """
        Detect excessive content duplication across pages.
        """
        if len(pages) < 2:
            return None
        
        # Simple hash-based duplication detection
        content_hashes = defaultdict(list)
        
        for page in pages:
            content = page.get("content", "")
            if content:
                # Normalize and hash content
                normalized = " ".join(content.lower().split())
                content_hash = hash(normalized)
                content_hashes[content_hash].append(page.get("url", ""))
        
        # Find duplicates
        duplicated_pages = [urls for urls in content_hashes.values() if len(urls) > 1]
        duplication_ratio = sum(len(urls) - 1 for urls in duplicated_pages) / len(pages)
        
        if duplication_ratio >= 0.2:  # 20% or more duplicated content
            return SpamSignal(
                signal_type="content_duplication",
                severity="high" if duplication_ratio >= 0.5 else "medium",
                confidence=min(1.0, duplication_ratio),
                description=f"Excessive content duplication detected ({duplication_ratio:.1%})",
                evidence=[str(len(duplicated_pages)), f"{duplication_ratio:.1%} of pages"],
            )
        
        return None
    
    @staticmethod
    def _detect_reciprocal_linking(
        domain: str, link_graph: Dict[str, List[str]]
    ) -> Optional[SpamSignal]:
        """
        Detect excessive reciprocal (mutual) linking patterns.
        """
        reciprocal_pairs = 0
        total_external_links = 0
        
        domain_netloc = urlparse(f"http://{domain}").netloc
        
        for source, targets in link_graph.items():
            for target in targets:
                target_netloc = urlparse(target).netloc
                
                # Check if it's external
                if target_netloc != domain_netloc:
                    total_external_links += 1
                    
                    # Check for reciprocal link (target links back to source)
                    for reverse_source, reverse_targets in link_graph.items():
                        if urlparse(reverse_source).netloc == target_netloc:
                            if source in reverse_targets:
                                reciprocal_pairs += 1
        
        if total_external_links > 0:
            reciprocal_ratio = reciprocal_pairs / total_external_links
            
            if reciprocal_ratio >= 0.6:  # 60% or more reciprocal
                return SpamSignal(
                    signal_type="reciprocal_linking",
                    severity="high" if reciprocal_ratio >= 0.8 else "medium",
                    confidence=min(1.0, reciprocal_ratio),
                    description="Suspicious reciprocal linking patterns detected",
                    evidence=[f"{reciprocal_ratio:.1%} of external links are reciprocal"],
                )
        
        return None
    
    @staticmethod
    def _analyze_anchor_text(link_graph: Dict[str, List[str]]) -> Optional[SpamSignal]:
        """
        Analyze anchor text patterns for keyword stuffing or generic text.
        """
        # Count generic anchor patterns
        generic_patterns = ["click here", "read more", "learn more", "visit", "link"]
        generic_count = 0
        total_links = 0
        
        # This is simplified - in real implementation, would need actual anchor text
        # For now, we'd extract from page HTML parsing
        
        return None  # Placeholder
    
    @staticmethod
    def _analyze_ip_reputation(ip_address_str: Optional[str]) -> Tuple[Optional[SpamSignal], float]:
        """
        Analyze IP address for spam hosting indicators.
        """
        if not ip_address_str:
            return None, 0.0
        
        ip_risk = 0.0
        indicators = []
        
        # Check against known spam IP ranges
        try:
            ip = ip_address(ip_address_str)
            
            # Check for suspicious patterns
            # (In production, would query reputation services like Spamhaus)
            
            # Check for shared hosting indicators
            if isinstance(ip, IPv4Address):
                last_octet = int(str(ip).split(".")[-1])
                # Suspiciously high IP numbers can indicate shared hosting pools
                if last_octet > 240:
                    ip_risk += 0.15
                    indicators.append("High IP octet (possible shared hosting pool)")
        
        except ValueError:
            return None, 0.0
        
        if ip_risk > 0.1:
            return SpamSignal(
                signal_type="ip_reputation",
                severity="medium",
                confidence=ip_risk,
                description="IP address shows potential reputation issues",
                evidence=indicators,
            ), ip_risk * 100
        
        return None, ip_risk * 100
    
    @staticmethod
    def _calculate_spam_score(signals: List[SpamSignal]) -> float:
        """
        Calculate overall spam score from individual signals.
        """
        if not signals:
            return 0.0
        
        # Weight signals by severity
        severity_weights = {
            "critical": 1.0,
            "high": 0.8,
            "medium": 0.5,
            "low": 0.2,
        }
        
        total_score = 0.0
        for signal in signals:
            weight = severity_weights.get(signal.severity, 0.5)
            signal_score = signal.confidence * weight * 100
            total_score += signal_score
        
        # Normalize to 0-100
        return min(100.0, total_score / len(signals))
    
    @staticmethod
    def _generate_recommendations(signals: List[SpamSignal], spam_score: float) -> List[str]:
        """
        Generate actionable recommendations based on findings.
        """
        recommendations = []
        
        for signal in signals:
            if signal.signal_type == "link_farm":
                recommendations.append(
                    "⚠️  Domain appears to be link farm - deprioritize in crawl queue"
                )
            elif signal.signal_type == "content_duplication":
                recommendations.append(
                    "📋 Significant content duplication - consider deduplication in indexing"
                )
            elif signal.signal_type == "reciprocal_linking":
                recommendations.append(
                    "🔗 Excessive reciprocal linking - likely part of link exchange scheme"
                )
            elif signal.signal_type == "cms_anomaly":
                recommendations.append(
                    "⚠️  Mixed CMS signatures - domain may be compromised"
                )
            elif signal.signal_type == "ip_reputation":
                recommendations.append(
                    "🌐 IP address has reputation concerns - monitor closely"
                )
        
        if spam_score >= 75:
            recommendations.append("🚫 RECOMMENDATION: Add to spam/PBN watchlist")
        elif spam_score >= 45:
            recommendations.append("⚠️  RECOMMENDATION: Monitor this domain closely")
        else:
            recommendations.append("✅ Domain appears legitimate")
        
        return recommendations


spam_detector = SpamDetector()
