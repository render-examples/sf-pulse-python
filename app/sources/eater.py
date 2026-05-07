"""Eater SF article fetcher — port of bin/cron-refresh/restaurants.ts (fetchEaterSFRaw).

Returns raw articles for the LLM pipeline; structured restaurant extraction lives in
app.llm.pipeline.
"""

from __future__ import annotations

import re

from app.sources.http import extract_body_text, fetch_url
from app.sources.recency import is_recent
from app.sources.rss import fetch_rss
from app.sources.types import RawArticle

EATER_SF_RSS = "https://sf.eater.com/rss/index.xml"

OPENING_KEYWORDS = re.compile(
    r"\b(?:opens?|opened|openings?|debuts?|now open|coming soon|new restaurant|grand opening)\b",
    re.IGNORECASE,
)


async def fetch_eater_sf_articles() -> list[RawArticle]:
    """Fetch recent Eater SF articles whose title/description hint at openings.
    Returns RawArticle objects ready for LLM extraction."""
    items = await fetch_rss(EATER_SF_RSS)
    results: list[RawArticle] = []

    for item in items:
        if not is_recent(item.pub_date):
            continue
        combined = f"{item.title} {item.description}"
        if not OPENING_KEYWORDS.search(combined):
            continue

        article_html = await fetch_url(item.link) if item.link else ""
        body_text = extract_body_text(article_html) if article_html else item.description

        results.append(
            RawArticle(
                source="eater",
                url=item.link or "",
                title=item.title,
                pubDate=item.pub_date or None,
                bodyText=body_text,
            )
        )

    return results
