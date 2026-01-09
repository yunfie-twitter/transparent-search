from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db
from ..utils.text_processor import normalize_query, tokenize
import re
import time

router = APIRouter()


def _make_snippet(content: str | None, tokens: list[str], radius: int = 60) -> str | None:
    if not content:
        return None
    content = re.sub(r"\s+", " ", content).strip()
    if not content:
        return None

    lower = content.lower()
    hit_pos = None
    hit_token = None
    for t in tokens:
        p = lower.find(t.lower())
        if p != -1:
            hit_pos = p
            hit_token = t
            break

    if hit_pos is None:
        return content[: min(len(content), radius * 2)]

    start = max(0, hit_pos - radius)
    end = min(len(content), hit_pos + radius)
    snippet = content[start:end]

    # highlight all tokens
    for t in sorted(set(tokens), key=len, reverse=True):
        snippet = re.sub(
            re.escape(t),
            lambda m: f"<mark>{m.group(0)}</mark>",
            snippet,
            flags=re.IGNORECASE,
        )

    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet = snippet + "…"

    return snippet


@router.get("/search")
async def search(
    q: str,
    limit: int = 10,
    offset: int = 0,
    op: str = "or",  # "or" or "and"
    db: AsyncSession = Depends(get_db),
):
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    q_norm = normalize_query(q)
    tokens = tokenize(q_norm)

    # de-dup tokens but keep order
    seen = set()
    tokens = [t for t in tokens if not (t in seen or seen.add(t))]

    if not tokens:
        raise HTTPException(status_code=400, detail="No valid tokens extracted from query")

    start = time.time()

    mode_and = (op.lower() == "and")

    query_score = text(
        """
        WITH q AS (
            SELECT unnest(:tokens::text[]) AS t
        ),
        base AS (
            SELECT
                p.id,
                p.title,
                p.h1,
                p.url,
                p.content,
                p.og_title,
                p.og_description,
                p.og_image_url,
                p.last_crawled_at,

                SUM(
                    (CASE WHEN lower(COALESCE(p.title,'')) LIKE '%' || lower(t) || '%' THEN 10 ELSE 0 END)
                  + (CASE WHEN lower(COALESCE(p.url,''))   LIKE '%' || lower(t) || '%' THEN  6 ELSE 0 END)
                  + (CASE WHEN lower(COALESCE(p.h1,''))    LIKE '%' || lower(t) || '%' THEN  8 ELSE 0 END)
                  + (
                        (
                            length(lower(COALESCE(p.content,'')))
                          - length(replace(lower(COALESCE(p.content,'')), lower(t), ''))
                        ) / GREATEST(length(t), 1)
                    )
                ) AS term_score,

                BOOL_AND(
                    lower(COALESCE(p.title,'')) LIKE '%' || lower(t) || '%'
                    OR lower(COALESCE(p.h1,'')) LIKE '%' || lower(t) || '%'
                    OR lower(COALESCE(p.url,'')) LIKE '%' || lower(t) || '%'
                    OR lower(COALESCE(p.content,'')) LIKE '%' || lower(t) || '%'
                ) AS all_terms_match,

                BOOL_OR(
                    lower(COALESCE(p.title,'')) LIKE '%' || lower(t) || '%'
                    OR lower(COALESCE(p.h1,'')) LIKE '%' || lower(t) || '%'
                    OR lower(COALESCE(p.url,'')) LIKE '%' || lower(t) || '%'
                    OR lower(COALESCE(p.content,'')) LIKE '%' || lower(t) || '%'
                ) AS any_terms_match

            FROM pages p
            CROSS JOIN q
            GROUP BY p.id
        )
        SELECT
            *,
            (
                term_score
                + (CASE WHEN lower(COALESCE(title,'')) = lower(:q_norm) THEN 5 ELSE 0 END)
                + (CASE
                    WHEN last_crawled_at > now() - interval '7 days'  THEN 3
                    WHEN last_crawled_at > now() - interval '30 days' THEN 1
                    ELSE 0
                  END)
                + (CASE
                    WHEN length(COALESCE(content,'')) < 100  THEN -5
                    WHEN length(COALESCE(content,'')) > 1000 THEN  2
                    ELSE 0
                  END)
            ) AS total_score
        FROM base
        WHERE (
            CASE WHEN :mode_and THEN all_terms_match ELSE any_terms_match END
        )
        ORDER BY total_score DESC
        LIMIT :limit OFFSET :offset
        """
    )

    result = await db.execute(
        query_score,
        {
            "tokens": tokens,
            "q_norm": q_norm,
            "limit": limit,
            "offset": offset,
            "mode_and": mode_and,
        },
    )
    rows = result.fetchall()

    # Fuzzy fallback (typo) when no results
    used_fuzzy = False
    did_you_mean = None

    if len(rows) == 0:
        used_fuzzy = True
        query_fuzzy = text(
            """
            SELECT id, title, h1, url, content, og_title, og_description, og_image_url, last_crawled_at,
                   similarity(COALESCE(title,''), :q_norm) AS total_score
            FROM pages
            WHERE title IS NOT NULL AND similarity(title, :q_norm) > 0.2
            ORDER BY similarity(title, :q_norm) DESC
            LIMIT :limit OFFSET :offset
            """
        )
        result2 = await db.execute(
            query_fuzzy, {"q_norm": q_norm, "limit": limit, "offset": offset}
        )
        rows = result2.fetchall()
        if len(rows) > 0 and rows[0].title:
            did_you_mean = rows[0].title

    took_ms = int((time.time() - start) * 1000)

    data = []
    for row in rows:
        snippet = _make_snippet(row.content, tokens)
        data.append(
            {
                "id": row.id,
                "title": row.title,
                "url": row.url,
                "updated_at": row.last_crawled_at,
                "score": float(row.total_score) if row.total_score is not None else 0.0,
                "snippet": snippet,
                "og": {
                    "title": row.og_title,
                    "description": row.og_description,
                    "image": row.og_image_url,
                },
            }
        )

    # Log query (and return query_id for click learning)
    async with db.begin():
        qres = await db.execute(
            text(
                "INSERT INTO search_queries (query, took_ms, results_count) VALUES (:q, :t, :c) RETURNING id"
            ),
            {"q": q_norm, "t": took_ms, "c": len(data)},
        )
        query_id = qres.scalar()

    return {
        "meta": {
            "query_id": query_id,
            "took_ms": took_ms,
            "count": len(data),
            "used_fuzzy": used_fuzzy,
            "did_you_mean": did_you_mean,
            "op": "and" if mode_and else "or",
            "tokens": tokens,
        },
        "data": data,
    }
