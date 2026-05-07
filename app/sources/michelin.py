"""Michelin California Selection scraper — port of bin/cron-refresh/restaurants.ts.

Pure regex extraction — parses the Michelin California publication page for
San Francisco-listed starred restaurants.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import unquote

from app.shared.dates import normalize_date_text
from app.shared.html import decode_html_entities, normalize_whitespace
from app.sources.http import ddg_search, fetch_url
from app.storage import NewRestaurant

MICHELIN_PUBLICATION_QUERY = (
    'site:michelin.com/en/publications/products-and-services '
    '"MICHELIN Guide California" selection'
)

_LINE_BREAK_RE = re.compile(
    r"</(?:p|span|div|li|h1|h2|h3|h4|h5|h6|br)>", re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]+>")
_ROW_RE = re.compile(r"^(.+?)\s+\((San Francisco)(?:;[^)]*)?\)$")
_DATE_LINE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_STOP_HEADING_RE = re.compile(r"^Green Star|^Bib Gourmand|^Special Awards?", re.IGNORECASE)
_DIRECT_URL_RE = re.compile(
    r"https://www\.michelin\.com/en/publications/products-and-services/"
    r"michelin-guide-california-[^\"'\s<]+",
    re.IGNORECASE,
)
_UDDG_RE = re.compile(r"uddg=([^\"&\s>]+)", re.IGNORECASE)


def _michelin_publication_url(year: int) -> str:
    return (
        f"https://www.michelin.com/en/publications/products-and-services/"
        f"michelin-guide-california-{year}-selection"
    )


def _michelin_star_count(heading: str) -> int | None:
    if re.match(r"^One MICHELIN Star$", heading, re.IGNORECASE):
        return 1
    if re.match(r"^Two MICHELIN Stars$", heading, re.IGNORECASE):
        return 2
    if re.match(r"^Three MICHELIN Stars$", heading, re.IGNORECASE):
        return 3
    return None


def _michelin_html_to_lines(html: str) -> list[str]:
    flattened = _LINE_BREAK_RE.sub("\n", html)
    flattened = _TAG_RE.sub(" ", flattened)
    return [
        normalize_whitespace(decode_html_entities(line))
        for line in flattened.split("\n")
        if normalize_whitespace(decode_html_entities(line))
    ]


def _parse_publication_date(lines: list[str]) -> str | None:
    raw = next((line for line in lines if _DATE_LINE_RE.match(line)), None)
    if not raw:
        return None
    parts = raw.split("-")
    try:
        month = int(parts[0])
        day = int(parts[1])
        year = int(parts[2])
    except (ValueError, IndexError):
        return None
    try:
        d = datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return None
    return d.strftime("%B %-d, %Y")


def _parse_michelin_selection_page(html: str, source_url: str) -> list[NewRestaurant]:
    lines = _michelin_html_to_lines(html)
    published_at = _parse_publication_date(lines)
    if not published_at:
        return []

    results: list[NewRestaurant] = []
    seen: set[str] = set()
    stars: int | None = None

    for line in lines:
        next_stars = _michelin_star_count(line)
        if next_stars is not None:
            stars = next_stars
            continue

        if stars is None:
            continue
        if _STOP_HEADING_RE.match(line):
            stars = None
            continue

        match = _ROW_RE.match(line)
        if not match:
            continue

        name = normalize_whitespace(match.group(1))
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        star_label = "star" if stars == 1 else "stars"
        results.append(
            NewRestaurant(
                name=name,
                neighborhood="San Francisco",
                cuisine=f"Michelin {stars}-star recognition",
                address=None,
                opened_date=f"{stars} {star_label} · {published_at}",
                highlight_kind="michelin",
                source_url=source_url,
            )
        )

    return results


def _extract_michelin_publication_urls(search_html: str) -> list[str]:
    urls: set[str] = set()
    for match in _DIRECT_URL_RE.finditer(search_html):
        urls.add(match.group(0))
    for match in _UDDG_RE.finditer(search_html):
        try:
            decoded = unquote(match.group(1))
        except Exception:
            continue
        if decoded.startswith(
            "https://www.michelin.com/en/publications/products-and-services/"
        ):
            urls.add(decoded)
    return list(urls)


async def fetch_michelin_restaurants() -> list[NewRestaurant]:
    """Fetch the current Michelin California selection (SF entries only).
    Tries the current and prior year by URL, then falls back to DDG search."""
    reference = datetime.now(UTC)
    candidate_urls = [
        _michelin_publication_url(reference.year),
        _michelin_publication_url(reference.year - 1),
    ]

    for url in candidate_urls:
        html = await fetch_url(url)
        if not html:
            continue
        parsed = _parse_michelin_selection_page(html, url)
        if parsed:
            return [
                NewRestaurant(
                    name=r.name,
                    neighborhood=r.neighborhood,
                    cuisine=r.cuisine,
                    address=r.address,
                    opened_date=normalize_date_text(r.opened_date),
                    highlight_kind=r.highlight_kind,
                    source_url=r.source_url,
                )
                for r in parsed
            ]

    try:
        search_html = await ddg_search(MICHELIN_PUBLICATION_QUERY)
        for url in _extract_michelin_publication_urls(search_html):
            html = await fetch_url(url)
            if not html:
                continue
            parsed = _parse_michelin_selection_page(html, url)
            if parsed:
                return [
                    NewRestaurant(
                        name=r.name,
                        neighborhood=r.neighborhood,
                        cuisine=r.cuisine,
                        address=r.address,
                        opened_date=normalize_date_text(r.opened_date),
                        highlight_kind=r.highlight_kind,
                        source_url=r.source_url,
                    )
                    for r in parsed
                ]
    except Exception:
        pass

    return []
