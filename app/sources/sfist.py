"""SFist restaurant openings — port of bin/cron-refresh/restaurants.ts (fetchSFist).

Pure regex extraction; the TS version also uses regex here (no LLM).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.shared.blocklist import is_blocked_restaurant_name
from app.sources.recency import is_recent
from app.sources.rss import fetch_rss
from app.storage import NewRestaurant

SFIST_RSS = "https://sfist.com/rss"

_OPENING_KEYWORDS = re.compile(
    r"\b(?:opens?|opened|openings?|debuts?|now open|coming soon|new restaurant|grand opening)\b",
    re.IGNORECASE,
)
_SF_HINT = re.compile(r"san francisco|sf\b", re.IGNORECASE)
_VENUE_HINT = re.compile(
    r"restaurant|bar|café|cafe|bakery|eatery|bistro|diner|pizzeria|ramen|sushi",
    re.IGNORECASE,
)
_TITLE_TRAILING_PUNCT = re.compile(r"\s*[-–|:,].*$")
_TITLE_OPENING_SUFFIX = re.compile(
    r"\s+(?:Opens?|Opening|Debuts?|Now Open).*", re.IGNORECASE
)


def _clean_sfist_title(title: str) -> str:
    cleaned = _TITLE_TRAILING_PUNCT.sub("", title)
    cleaned = _TITLE_OPENING_SUFFIX.sub("", cleaned)
    return cleaned.strip()


async def fetch_sfist_restaurants() -> list[NewRestaurant]:
    """Fetch new restaurant openings from SFist RSS.
    Pure regex extraction — no LLM."""
    items = await fetch_rss(SFIST_RSS)
    month = datetime.now(UTC).strftime("%B %Y")
    results: list[NewRestaurant] = []
    seen: set[str] = set()

    for item in items:
        if not is_recent(item.pub_date):
            continue
        combined = f"{item.title} {item.description}"
        if not _OPENING_KEYWORDS.search(combined):
            continue
        if not _SF_HINT.search(combined):
            continue
        if not _VENUE_HINT.search(combined):
            continue

        name = _clean_sfist_title(item.title)
        if len(name) < 3:
            continue
        if is_blocked_restaurant_name(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        results.append(
            NewRestaurant(
                name=name,
                neighborhood="San Francisco",
                cuisine="New opening",
                address=None,
                opened_date=month,
                source_url=item.link or None,
            )
        )

    return results
