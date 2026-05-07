"""Fine Arts Museums of San Francisco events scraper.

Port of bin/cron-refresh/events.ts (fetchFAMSF / parseFAMSFPage). Uses selectolax to
walk heading elements and find an exact event date in their nearby text.
"""

from __future__ import annotations

import re
from typing import Any

from selectolax.parser import HTMLParser

from app.shared.dates import normalize_date_text
from app.shared.html import normalize_escaped_html_text, normalize_whitespace
from app.shared.identity import build_event_identity_key
from app.sources.constants import LONG_FETCH_TIMEOUT_SECONDS, MONTH_NAME_PATTERN, WEEKDAY_PATTERN
from app.sources.http import fetch_url
from app.storage import NewEvent

FAMSF_URL = "https://www.famsf.org/calendar"

_EXACT_EVENT_DATE_PATTERN = (
    rf"(?:({WEEKDAY_PATTERN}),?\s+)?"
    rf"(?:{MONTH_NAME_PATTERN})\s+\d{{1,2}}(?:\s*[–-]\s*\d{{1,2}})?(?:,\s*\d{{4}})?"
)
_DATE_RE = re.compile(_EXACT_EVENT_DATE_PATTERN, re.IGNORECASE)
_DATE_ONLY_TITLE_RE = re.compile(
    rf"^(?:{_EXACT_EVENT_DATE_PATTERN}|(?:{MONTH_NAME_PATTERN})\s+\d{{4}})$",
    re.IGNORECASE,
)
_GENERIC_EVENT_TITLE_RE = re.compile(
    r"^(?:highlights?|today|upcoming|calendar|events?|exhibitions?|exhibits?|tours?|talks?|"
    r"performances?|parties|access days?|featured(?: events?)?|programs?|planetarium|visit|"
    r"hours|tickets?|membership|donate|shop|search|menu|about|learn|support|collections?|"
    r"plan your visit|what'?s on|see all|view all|read more|new & featured|iconic exhibits|"
    r"ongoing exhibits|hands-on exhibits)\s*$",
    re.IGNORECASE,
)


def _is_likely_museum_title(title: str, ignored: re.Pattern[str]) -> bool:
    n = normalize_whitespace(title)
    if not n or len(n) < 4 or len(n) > 120:
        return False
    if not re.search(r"\w", n, re.UNICODE):
        return False
    if len(n.split()) > 12:
        return False
    if _GENERIC_EVENT_TITLE_RE.match(n):
        return False
    if _DATE_ONLY_TITLE_RE.match(n):
        return False
    return not ignored.match(n)


async def _fetch_html() -> str:
    return await fetch_url(FAMSF_URL, timeout=LONG_FETCH_TIMEOUT_SECONDS)


def parse_museum_events(
    html: str,
    *,
    location: str,
    source_url: str,
    heading_levels: str,
    ignored_title_re: re.Pattern[str],
) -> list[NewEvent]:
    """Walk h-tags whose level is in heading_levels (e.g. "34"), and pair each
    plausible heading with a nearby exact date. Returns deduped NewEvents."""
    tree = HTMLParser(html)
    body = tree.body or tree.root
    if body is None:
        return []

    selectors = ",".join(f"h{level}" for level in heading_levels)
    headings = body.css(selectors)
    if not headings:
        return []

    seen_keys: set[str] = set()
    results: list[NewEvent] = []

    candidates: list[tuple[Any, str, bool]] = []
    for h in headings:
        title = normalize_whitespace(h.text(separator=" "))
        candidates.append((h, title, _is_likely_museum_title(title, ignored_title_re)))

    for index, (heading, title, is_candidate) in enumerate(candidates):
        if not is_candidate:
            continue

        # Collect text from the heading's siblings until the next heading, capped
        window_parts: list[str] = [title]
        next_heading_node = candidates[index + 1][0] if index + 1 < len(candidates) else None
        cursor = heading.next
        char_budget = 1200
        while cursor is not None and char_budget > 0:
            if cursor is next_heading_node:
                break
            text = cursor.text(separator=" ") if hasattr(cursor, "text") else ""
            if text:
                snippet = normalize_whitespace(text)
                if snippet:
                    window_parts.append(snippet)
                    char_budget -= len(snippet)
            cursor = cursor.next

        window_text = " ".join(window_parts)
        date = _find_nearby_exact_date(window_text, title)
        if not date:
            continue

        event = NewEvent(
            title=normalize_escaped_html_text(title),
            location=location,
            date=date,
            time=None,
            description=None,
            source_url=source_url,
        )
        key = build_event_identity_key(
            title=event.title,
            location=event.location,
            date_text=normalize_date_text(event.date),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        results.append(event)

    return results


def _find_nearby_exact_date(window_text: str, title: str) -> str | None:
    n_window = normalize_whitespace(window_text)
    n_title = normalize_whitespace(title)
    title_index = n_window.find(n_title)
    if title_index == -1:
        return None

    best: tuple[str, int] | None = None
    for match in _DATE_RE.finditer(n_window):
        distance = min(
            abs(match.start() - title_index),
            abs(match.end() - (title_index + len(n_title))),
        )
        if distance > 240:
            continue
        date_text = normalize_whitespace(match.group(0))
        date_text = re.sub(r"\s*([–-])\s*", r" \1 ", date_text)
        if best is None or distance < best[1]:
            best = (date_text, distance)
    return best[0] if best else None


_FAMSF_IGNORED = re.compile(
    r"^(?:de young|legion of honor|tickets?|hours|museum map|visitor information)$",
    re.IGNORECASE,
)


async def fetch_famsf_events() -> list[NewEvent]:
    """Fetch and parse the FAMSF calendar page."""
    html = await _fetch_html()
    if not html:
        return []
    return parse_museum_events(
        html,
        location="Fine Arts Museums of San Francisco",
        source_url=FAMSF_URL,
        heading_levels="34",
        ignored_title_re=_FAMSF_IGNORED,
    )
