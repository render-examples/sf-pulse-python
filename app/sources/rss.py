"""RSS feed fetcher — port of bin/cron-refresh/rss.ts.

Uses feedparser for robust parsing (handles RSS 2.0, Atom, and various oddities).
"""

from __future__ import annotations

import feedparser
import httpx

from app.sources.constants import CRON_USER_AGENT, LONG_FETCH_TIMEOUT_SECONDS
from app.sources.http import _lookup_override, strip_html
from app.sources.types import RssItem


async def fetch_rss(url: str) -> list[RssItem]:
    """Fetch and parse an RSS/Atom feed. Returns [] on failure."""
    if _lookup_override is not None:
        try:
            xml = await _lookup_override(url)
        except Exception:
            return []
    else:
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": CRON_USER_AGENT},
                timeout=LONG_FETCH_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                if response.status_code >= 400:
                    return []
                xml = response.text
        except Exception:
            return []

    if not xml:
        return []

    parsed = feedparser.parse(xml)
    items: list[RssItem] = []
    for entry in parsed.entries:
        title = strip_html(entry.get("title") or "")
        link = entry.get("link") or ""
        pub_date = entry.get("published") or entry.get("updated") or ""
        description = strip_html(
            entry.get("summary") or entry.get("description") or ""
        )
        if title:
            items.append(
                RssItem(title=title, link=link, pub_date=pub_date, description=description)
            )
    return items
