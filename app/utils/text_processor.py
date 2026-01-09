import re
from typing import List

# Japanese stopwords (minimal set)
JAPANESE_STOPWORDS = set([
    "の", "に", "は", "を", "た", "が", "で", "て", "と", "し", "れ",
    "さ", "ある", "いる", "も", "する", "から", "な", "こと", "として",
    "い", "や", "など", "なっ", "など", "ない", "この", "ため"
])

def clean_html_text(text: str) -> str:
    """Remove HTML artifacts, normalize whitespace."""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def simple_tokenize(text: str) -> List[str]:
    """Simple tokenizer: split by whitespace and extract 2+ char tokens.
    For Japanese, this is very naive. For production, use MeCab.
    """
    # Remove symbols
    text = re.sub(r'[\r\n\t]+', ' ', text)
    # Keep alphanumeric and Japanese characters
    tokens = re.findall(r'[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+', text)
    # Filter by length
    tokens = [t for t in tokens if len(t) >= 2]
    # Remove stopwords
    tokens = [t for t in tokens if t.lower() not in JAPANESE_STOPWORDS]
    return tokens

def tokenize_with_mecab(text: str) -> List[str]:
    """Tokenize Japanese text using MeCab (optional)."""
    try:
        import MeCab
        tagger = MeCab.Tagger("-Owakati")
        result = tagger.parse(text).strip()
        tokens = result.split()
        # Remove stopwords
        tokens = [t for t in tokens if t not in JAPANESE_STOPWORDS and len(t) >= 2]
        return tokens
    except ImportError:
        # Fallback to simple tokenizer
        return simple_tokenize(text)

def normalize_query(query: str) -> str:
    """Normalize search query: lowercase, remove extra spaces."""
    query = query.lower().strip()
    query = re.sub(r'\s+', ' ', query)
    return query
