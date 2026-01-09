"""Content Type Classifier - Automatically categorize page content."""

import re
from typing import Dict, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from bs4 import BeautifulSoup


class ContentClassifier:
    """Classify content type of web pages."""
    
    CONTENT_TYPES = [
        'text_article',
        'manga',
        'video',
        'image',
        'forum',
        'tool',
        'unknown',
    ]
    
    @staticmethod
    async def classify(html: str, url: str, page_id: int, session: AsyncSession) -> Dict:
        """Classify page content type."""
        soup = BeautifulSoup(html, 'lxml')
        
        # Calculate metrics
        metrics = ContentClassifier._extract_metrics(soup, html)
        
        # Score each content type
        scores = {
            'text_article': ContentClassifier._score_article(metrics),
            'manga': ContentClassifier._score_manga(metrics),
            'video': ContentClassifier._score_video(metrics),
            'image': ContentClassifier._score_image(metrics),
            'forum': ContentClassifier._score_forum(metrics),
            'tool': ContentClassifier._score_tool(metrics),
        }
        
        # Find primary content type
        primary_type = max(scores, key=scores.get)
        confidence = scores[primary_type]
        
        # If confidence too low, mark as unknown
        if confidence < 0.3:
            primary_type = 'unknown'
        
        # Store in database
        await session.execute(
            text("""
                INSERT INTO content_classifications (
                    page_id, content_type, type_confidence,
                    text_length, image_count, has_video,
                    has_form, code_block_count, comment_indicators,
                    has_toc, is_series,
                    metrics_json
                )
                VALUES (
                    :page_id, :type, :confidence,
                    :text_len, :img_count, :has_video,
                    :has_form, :code_count, :comment_count,
                    :has_toc, :is_series,
                    :metrics
                )
                ON CONFLICT (page_id) DO UPDATE
                SET content_type = EXCLUDED.content_type,
                    type_confidence = EXCLUDED.type_confidence,
                    metrics_json = EXCLUDED.metrics_json
            """),
            {
                'page_id': page_id,
                'type': primary_type,
                'confidence': confidence,
                'text_len': metrics['text_length'],
                'img_count': metrics['image_count'],
                'has_video': metrics['has_video'],
                'has_form': metrics['has_form'],
                'code_count': metrics['code_block_count'],
                'comment_count': metrics['comment_indicators'],
                'has_toc': metrics['has_toc'],
                'is_series': metrics['is_series'],
                'metrics': str(metrics),
            },
        )
        
        return {
            'content_type': primary_type,
            'confidence': confidence,
            'metrics': metrics,
            'all_scores': scores,
        }
    
    @staticmethod
    def _extract_metrics(soup: BeautifulSoup, html: str) -> Dict:
        """Extract metrics from page."""
        # Text length
        body = soup.body or soup
        text_content = body.get_text()
        text_length = len(re.sub(r'\s+', ' ', text_content).strip())
        
        # Images
        images = soup.find_all('img')
        image_count = len(images)
        
        # Video
        has_video = bool(
            soup.find('video') or
            soup.find('iframe', src=re.compile(r'(youtube|vimeo|youtu\.be|nicovideo)')) or
            re.search(r'<video', html, re.IGNORECASE)
        )
        
        # Forms
        has_form = bool(soup.find('form'))
        
        # Code blocks
        code_blocks = soup.find_all('code')
        code_block_count = len(code_blocks)
        
        # Comment indicators (user-generated content patterns)
        comment_patterns = [
            soup.find_all('comment'),
            soup.find_all(class_=re.compile(r'comment|discussion|reply|feedback')),
            re.findall(r'\bcomment\b', html, re.IGNORECASE),
        ]
        comment_indicators = sum(len(list(p)) for p in comment_patterns if p)
        
        # Table of contents
        has_toc = bool(
            soup.find(class_=re.compile(r'toc|table.of.contents|contents')) or
            soup.find('nav') or
            re.search(r'<nav[^>]*>(.*?)</nav>', html, re.IGNORECASE)
        )
        
        # Series/continuation (prev/next links)
        is_series = bool(
            soup.find('a', rel=re.compile(r'prev|next')) or
            soup.find('a', text=re.compile(r'^(prev|next|\u524d|\u6b21)', re.IGNORECASE)) or
            re.search(r'(episode|chapter|part|\u8a71)', text_content, re.IGNORECASE)
        )
        
        # Heading structure
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        heading_count = len(headings)
        
        # Links
        links = soup.find_all('a')
        link_count = len(links)
        
        # Blockquotes
        blockquotes = soup.find_all('blockquote')
        blockquote_count = len(blockquotes)
        
        return {
            'text_length': text_length,
            'image_count': image_count,
            'has_video': has_video,
            'has_form': has_form,
            'code_block_count': code_block_count,
            'comment_indicators': comment_indicators,
            'has_toc': has_toc,
            'is_series': is_series,
            'heading_count': heading_count,
            'link_count': link_count,
            'blockquote_count': blockquote_count,
            'image_ratio': image_count / max(1, heading_count) if heading_count > 0 else 0,
        }
    
    @staticmethod
    def _score_article(metrics: Dict) -> float:
        """Score likelihood of being a text article."""
        score = 0.0
        
        if metrics['text_length'] > 1000:
            score += 0.3
        elif metrics['text_length'] > 500:
            score += 0.2
        
        if 0.1 <= metrics['image_ratio'] <= 0.4:
            score += 0.2
        
        if metrics['heading_count'] > 3:
            score += 0.2
        
        if metrics['has_toc']:
            score += 0.15
        
        if metrics['blockquote_count'] > 0:
            score += 0.1
        
        if not metrics['has_form'] and not metrics['has_video']:
            score += 0.05
        
        return min(1.0, score)
    
    @staticmethod
    def _score_manga(metrics: Dict) -> float:
        """Score likelihood of being manga/webtoon."""
        score = 0.0
        
        if metrics['image_ratio'] > 0.6:
            score += 0.3
        
        if metrics['image_count'] > 5 and metrics['text_length'] < 500:
            score += 0.3
        
        if metrics['is_series']:
            score += 0.4
        
        if metrics['has_toc'] and metrics['image_count'] > 3:
            score += 0.15
        
        return min(1.0, score)
    
    @staticmethod
    def _score_video(metrics: Dict) -> float:
        """Score likelihood of being video content."""
        score = 0.0
        
        if metrics['has_video']:
            score += 0.8
        
        if metrics['text_length'] < 500 and metrics['has_video']:
            score += 0.2
        
        return min(1.0, score)
    
    @staticmethod
    def _score_image(metrics: Dict) -> float:
        """Score likelihood of being image gallery."""
        score = 0.0
        
        if metrics['image_count'] > 20:
            score += 0.4
        elif metrics['image_count'] > 10:
            score += 0.3
        
        if metrics['text_length'] < 300 and metrics['image_count'] > 5:
            score += 0.3
        
        if metrics['image_ratio'] > 0.7:
            score += 0.2
        
        if not metrics['has_form']:
            score += 0.1
        
        return min(1.0, score)
    
    @staticmethod
    def _score_forum(metrics: Dict) -> float:
        """Score likelihood of being forum/discussion."""
        score = 0.0
        
        if metrics['comment_indicators'] > 5:
            score += 0.4
        elif metrics['comment_indicators'] > 0:
            score += 0.2
        
        if metrics['heading_count'] > 2:
            score += 0.2
        
        if metrics['link_count'] > metrics['image_count']:
            score += 0.15
        
        if metrics['blockquote_count'] > 0:
            score += 0.15
        
        return min(1.0, score)
    
    @staticmethod
    def _score_tool(metrics: Dict) -> float:
        """Score likelihood of being a web tool/application."""
        score = 0.0
        
        if metrics['has_form']:
            score += 0.4
        
        if metrics['code_block_count'] > 0:
            score += 0.25
        
        if metrics['text_length'] < 1000 and metrics['has_form']:
            score += 0.2
        
        if not metrics['has_toc'] and metrics['image_count'] < 3:
            score += 0.15
        
        return min(1.0, score)
