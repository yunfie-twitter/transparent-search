import re
import unicodedata
from typing import List

# Japanese stopwords (minimal set)
JAPANESE_STOPWORDS = set([
    "の", "に", "は", "を", "た", "が", "で", "て", "と", "し", "れ",
    "さ", "ある", "いる", "も", "する", "から", "な", "こと", "として",
    "い", "や", "など", "なっ", "ない", "この", "ため",
])

_WORD_RE = re.compile(r"[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+")


def clean_html_text(text: str) -> str:
    """Remove HTML artifacts, normalize whitespace."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_query(query: str) -> str:
    """Normalize query:
    - NFKC (fullwidth/halfwidth normalization)
    - lowercase
    - normalize whitespace
    """
    query = unicodedata.normalize("NFKC", query)
    query = query.lower().strip()
    query = re.sub(r"\s+", " ", query)
    return query


def _filter_tokens(tokens: List[str]) -> List[str]:
    out = []
    for t in tokens:
        t = t.strip()
        if len(t) < 2:
            continue
        if t in JAPANESE_STOPWORDS:
            continue
        out.append(t)
    return out


def simple_tokenize(text: str) -> List[str]:
    """Fallback tokenizer: extract word-ish sequences and keep 2+ chars."""
    text = normalize_query(text)
    tokens = _WORD_RE.findall(text)
    return _filter_tokens(tokens)


def tokenize_with_mecab(text: str) -> List[str]:
    """Tokenize Japanese text using MeCab + unidic-lite (default enabled).

    If MeCab fails for any reason, fallback to simple_tokenize.
    """
    text = normalize_query(text)

    try:
        import MeCab
        try:
            import unidic_lite
            dicdir = unidic_lite.DICDIR
            tagger = MeCab.Tagger(f"-d {dicdir} -Owakati")
        except Exception:
            tagger = MeCab.Tagger("-Owakati")

        parsed = tagger.parse(text)
        if not parsed:
            return simple_tokenize(text)
        tokens = parsed.strip().split()
        return _filter_tokens(tokens)

    except Exception:
        return simple_tokenize(text)


def tokenize(text: str) -> List[str]:
    """Default tokenizer (MeCab enabled)."""
    return tokenize_with_mecab(text)
