from bs4 import BeautifulSoup
from typing import Dict, Tuple
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class ContentClassifier:
    """
    Automatically classify web page content type.
    Types: text_article, manga, video, image, forum, tool, unknown
    """

    @staticmethod
    async def classify(html: str, url: str, page_id: int, db: AsyncSession = None) -> Dict:
        """
        Classify page content and store results.
        """
        soup = BeautifulSoup(html, 'lxml')
        
        metrics = ContentClassifier._extract_metrics(soup, html)
        content_type, confidence = ContentClassifier._determine_type(metrics)
        
        result = {
            'content_type': content_type,
            'confidence': confidence,
            'metrics': metrics
        }
        
        if db:
            await ContentClassifier._store_classification(db, page_id, result)
        
        return result

    @staticmethod
    def _extract_metrics(soup: BeautifulSoup, html: str) -> Dict:
        """
        Extract metrics for classification.
        """
        metrics = {}
        
        # Text metrics
        text_content = soup.get_text()
        metrics['text_length'] = len(text_content)
        metrics['paragraph_count'] = len(soup.find_all('p'))
        metrics['avg_paragraph_length'] = metrics['text_length'] / max(1, metrics['paragraph_count'])
        
        # Image metrics
        images = soup.find_all('img')
        metrics['image_count'] = len(images)
        metrics['image_ratio'] = len(images) / max(1, len(soup.find_all(['p', 'div', 'section'])))
        
        # Video detection
        metrics['has_video'] = bool(soup.find('video')) or bool(soup.find('iframe', src=re.compile(r'(youtube|vimeo|youtu\.be)')))
        metrics['video_count'] = len(soup.find_all('video')) + len(soup.find_all('iframe', src=re.compile(r'(youtube|vimeo|youtu\.be)')))
        
        # iframe detection
        metrics['iframe_count'] = len(soup.find_all('iframe'))
        metrics['has_iframe'] = metrics['iframe_count'] > 0
        
        # JavaScript metrics
        scripts = soup.find_all('script')
        metrics['script_count'] = len(scripts)
        metrics['external_js_count'] = len([s for s in scripts if s.get('src')])
        
        # Heuristics for specific types
        metrics['has_toc'] = bool(soup.find(['nav', '[role="navigation"]'])) or bool(soup.find('a', href=re.compile(r'#')))
        metrics['has_prev_next'] = bool(soup.find('a', rel='prev')) or bool(soup.find('a', rel='next'))
        metrics['is_series'] = metrics['has_prev_next'] or 'chapter' in html.lower()
        
        # Form detection (tool/interactive)
        metrics['has_form'] = bool(soup.find('form'))
        metrics['input_count'] = len(soup.find_all(['input', 'textarea', 'select']))
        
        # Table detection
        metrics['table_count'] = len(soup.find_all('table'))
        
        # Heading hierarchy
        metrics['h1_count'] = len(soup.find_all('h1'))
        metrics['h2_count'] = len(soup.find_all('h2'))
        metrics['h3_plus_count'] = len(soup.find_all(['h3', 'h4', 'h5', 'h6']))
        
        # Code detection (technical content)
        metrics['code_block_count'] = len(soup.find_all(['pre', 'code']))
        metrics['has_syntax_highlighting'] = bool(soup.find('code', class_=re.compile(r'hljs|lang-|language-')))
        
        # Forum/discussion indicators
        metrics['comment_indicators'] = len(soup.find_all(['comment', '[data-comment', '[role="article"]']))
        metrics['has_comments'] = metrics['comment_indicators'] > 0 or bool(soup.find('section', id=re.compile(r'comment|discussion')))
        
        return metrics

    @staticmethod
    def _determine_type(metrics: Dict) -> Tuple[str, float]:
        """
        Determine content type based on metrics.
        Returns (type, confidence_score)
        """
        scores = {}
        
        # Text article: high text, balanced images, headings, TOC common
        text_score = 0
        if metrics['text_length'] > 1000:
            text_score += 0.3
        if 0.1 < metrics['image_ratio'] < 0.4:
            text_score += 0.2
        if metrics['h1_count'] >= 1 and (metrics['h2_count'] + metrics['h3_plus_count']) >= 2:
            text_score += 0.2
        if metrics['has_toc']:
            text_score += 0.15
        if metrics['paragraph_count'] > 10:
            text_score += 0.15
        scores['text_article'] = text_score
        
        # Video: iframe with youtube/vimeo or video tag
        video_score = 0
        if metrics['has_video']:
            video_score += 0.5
        if metrics['video_count'] > 0:
            video_score += 0.3
        if metrics['video_count'] > 0 and metrics['text_length'] < 500:
            video_score += 0.2
        scores['video'] = video_score
        
        # Manga: images dominate, series structure, prev/next
        manga_score = 0
        if metrics['image_ratio'] > 0.6:
            manga_score += 0.3
        if metrics['image_count'] > 5 and metrics['text_length'] < 500:
            manga_score += 0.3
        if metrics['is_series']:
            manga_score += 0.4
        scores['manga'] = manga_score
        
        # Image/素材: mostly images, minimal text, galleries
        image_score = 0
        if metrics['image_count'] > 20 and metrics['text_length'] < 300:
            image_score += 0.5
        if metrics['image_ratio'] > 0.8:
            image_score += 0.3
        scores['image'] = image_score
        
        # Forum/discussion: comments, user-generated content
        forum_score = 0
        if metrics['has_comments']:
            forum_score += 0.4
        if metrics['comment_indicators'] > 3:
            forum_score += 0.3
        scores['forum'] = forum_score
        
        # Tool/Interactive: forms, inputs, code, dynamic elements
        tool_score = 0
        if metrics['has_form']:
            tool_score += 0.5
        if metrics['input_count'] > 0:
            tool_score += 0.3
        if metrics['code_block_count'] > 5:
            tool_score += 0.2
        scores['tool'] = tool_score
        
        # Determine primary type
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        
        # If confidence too low, mark as unknown
        if best_score < 0.3:
            best_type = 'unknown'
            best_score = 0.5
        
        return best_type, best_score

    @staticmethod
    async def _store_classification(db: AsyncSession, page_id: int, result: Dict):
        """
        Store content classification in database.
        """
        metrics = result['metrics']
        
        await db.execute(
            text("""
                INSERT INTO content_classifications (
                    page_id, content_type, type_confidence,
                    text_length, image_count, image_ratio,
                    has_video, has_iframe, avg_paragraph_length,
                    has_table_of_contents, has_interactive_elements,
                    external_js_count
                )
                VALUES (:pid, :ct, :conf, :tl, :ic, :ir, :hv, :hif, :apl, :htoc, :hie, :ejc)
                ON CONFLICT (page_id) DO UPDATE SET
                    content_type = EXCLUDED.content_type,
                    type_confidence = EXCLUDED.type_confidence,
                    classified_at = NOW()
            """),
            {
                'pid': page_id,
                'ct': result['content_type'],
                'conf': result['confidence'],
                'tl': metrics['text_length'],
                'ic': metrics['image_count'],
                'ir': metrics['image_ratio'],
                'hv': metrics['has_video'],
                'hif': metrics['has_iframe'],
                'apl': int(metrics['avg_paragraph_length']),
                'htoc': metrics['has_toc'],
                'hie': metrics['has_form'] or metrics['input_count'] > 0,
                'ejc': metrics['external_js_count']
            }
        )
