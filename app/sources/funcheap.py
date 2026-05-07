"""Funcheap event fetcher — port of bin/cron-refresh/events.ts (fetchFuncheap).

Strategy mirrors the TS source:
1. Pull the RSS feed for recent items.
2. For each item, fetch the article HTML and try to parse a JSON-LD Event node.
3. Fall back to RSS title/description if JSON-LD is absent.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.shared.dates import normalize_date_text
from app.shared.html import (
    decode_html_entities_recursive,
    normalize_escaped_html_text,
    normalize_whitespace,
)
from app.shared.identity import build_event_identity_key
from app.sources.constants import MONTH_NAME_PATTERN
from app.sources.http import fetch_url
from app.sources.recency import is_recent
from app.sources.rss import fetch_rss
from app.storage import NewEvent

FUNCHEAP_RSS = "https://sf.funcheap.com/feed/"
PT = ZoneInfo("America/Los_Angeles")

_PREFIX_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4}):\s*")
_FREE_SUFFIX_RE = re.compile(r"\s*-\s*FREE\s*$", re.IGNORECASE)
_JSONLD_SCRIPT_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>([\s\S]*?)</script>',
    re.IGNORECASE,
)
_TITLE_DATE_RE = re.compile(
    rf"^(.*?)\s*\(((?:{MONTH_NAME_PATTERN})\s+\d{{1,2}}(?:\s*[–-]\s*\d{{1,2}})?(?:,\s*\d{{4}})?)\)\s*$",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _strip_funcheap_attribution(value: str) -> str:
    cleaned = re.sub(
        r"\s*The post .*? appeared first on Funcheap\s*\.\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^Original Event Description:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*Read more\.\.\.\s*$", "", cleaned, flags=re.IGNORECASE)
    return normalize_whitespace(cleaned)


def _normalize_title_and_date(title: str, date: str) -> tuple[str, str]:
    normalized_title = normalize_whitespace(decode_html_entities_recursive(title))
    match = _TITLE_DATE_RE.match(normalized_title)
    if not match:
        return normalized_title, date

    next_title = normalize_whitespace(match.group(1))
    embedded_year = _YEAR_RE.search(match.group(2))
    title_year = _YEAR_RE.search(normalized_title)
    year = (
        embedded_year.group(1)
        if embedded_year
        else (title_year.group(1) if title_year else None)
    )

    candidate = match.group(2)
    if year and not _YEAR_RE.search(candidate):
        candidate = f"{candidate}, {year}"
    next_date = normalize_date_text(candidate).replace(" - ", " – ").replace("-", "–")

    if year:
        next_title = normalize_whitespace(re.sub(rf"\s+{year}$", "", next_title))

    return next_title, next_date


def _extract_jsonld_scripts(html: str) -> list[Any]:
    results: list[Any] = []
    for match in _JSONLD_SCRIPT_RE.finditer(html):
        raw = (match.group(1) or "").strip()
        if not raw:
            continue
        try:
            results.append(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            continue
    return results


def _flatten_jsonld(value: Any) -> list[dict]:
    if not isinstance(value, (dict, list)):
        return []
    if isinstance(value, list):
        out: list[dict] = []
        for entry in value:
            out.extend(_flatten_jsonld(entry))
        return out
    graph = value.get("@graph")
    if isinstance(graph, list):
        out = []
        for entry in graph:
            out.extend(_flatten_jsonld(entry))
        return out
    return [value]


def _is_event_node(node: dict) -> bool:
    type_value = node.get("@type")
    if isinstance(type_value, list):
        return "Event" in type_value
    return type_value == "Event"


def _node_string(value: Any) -> str | None:
    if isinstance(value, str):
        return decode_html_entities_recursive(value)
    return None


def _node_location(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    name = _node_string(value.get("name"))
    address_value = value.get("address")
    if isinstance(address_value, str):
        address = decode_html_entities_recursive(address_value)
    elif isinstance(address_value, dict):
        parts = [
            _node_string(address_value.get("streetAddress")),
            _node_string(address_value.get("addressLocality")),
            _node_string(address_value.get("addressRegion")),
        ]
        address = ", ".join(p for p in parts if p) or None
    else:
        address = None
    pieces = [name, address]
    seen: list[str] = []
    for piece in pieces:
        if piece and piece not in seen:
            seen.append(piece)
    joined = ", ".join(seen)
    return normalize_whitespace(joined) or None


def _format_funcheap_date(start_date: str, end_date: str | None) -> str:
    try:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return normalize_date_text(start_date)
    end = None
    if end_date:
        try:
            end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            end = None

    start_pt = start.astimezone(PT)
    if end:
        end_pt = end.astimezone(PT)
        same_day = start_pt.date() == end_pt.date()
    else:
        same_day = True

    if not end or same_day:
        return start_pt.strftime("%B %-d, %Y")
    return f"{start_pt.strftime('%B %-d, %Y')} – {end.astimezone(PT).strftime('%B %-d, %Y')}"


def _format_funcheap_time(start_date: str, end_date: str | None) -> str | None:
    try:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    start_text = start.astimezone(PT).strftime("%-I:%M %p").lstrip("0")
    if not end_date:
        return start_text
    try:
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return start_text
    end_text = end.astimezone(PT).strftime("%-I:%M %p").lstrip("0")
    return f"{start_text} – {end_text}"


_NON_SF_PLACE_RE = re.compile(
    r"\b(?:alameda|albany|berkeley|dublin|marin|oakland|petaluma|san bruno|"
    r"san jose|walnut creek|woodside)\b",
    re.IGNORECASE,
)
_SF_RE = re.compile(r"\bsan francisco\b|(?:^|\W)sf\b", re.IGNORECASE)


def _is_non_sf_event(title: str, address: str | None) -> bool:
    title_l = title.lower()
    address_l = (address or "").lower()
    if "san francisco bay area" in address_l:
        return True
    if re.search(r"\|\s*bay area\b", title_l):
        return True
    if "bay area" in address_l and not _SF_RE.search(address_l):
        return True
    if _NON_SF_PLACE_RE.search(address_l) and not _SF_RE.search(address_l):
        return True
    return bool(not address_l and _NON_SF_PLACE_RE.search(title_l))


def _parse_jsonld_event(html: str, source_url: str) -> NewEvent | None:
    nodes: list[dict] = []
    for blob in _extract_jsonld_scripts(html):
        nodes.extend(_flatten_jsonld(blob))
    event_node = next((n for n in nodes if _is_event_node(n)), None)
    if not event_node:
        return None

    title = _node_string(event_node.get("name"))
    start_date = _node_string(event_node.get("startDate"))
    end_date = _node_string(event_node.get("endDate"))
    location = _node_location(event_node.get("location")) or "San Francisco"
    if not title or not start_date:
        return None

    if _is_non_sf_event(title, location):
        return None

    next_title, next_date = _normalize_title_and_date(
        title, _format_funcheap_date(start_date, end_date)
    )
    description = _node_string(event_node.get("description"))
    return NewEvent(
        title=normalize_escaped_html_text(next_title),
        location=normalize_whitespace(location),
        date=next_date,
        time=_format_funcheap_time(start_date, end_date),
        description=normalize_escaped_html_text(description) if description else None,
        source_url=source_url,
    )


async def fetch_funcheap_events() -> list[NewEvent]:
    """Fetch Funcheap RSS, dedupe, prefer JSON-LD on the article page when available."""
    items = await fetch_rss(FUNCHEAP_RSS)
    results: list[NewEvent] = []
    seen_keys: set[str] = set()

    for item in items:
        if not is_recent(item.pub_date):
            continue

        title = item.title
        date = item.pub_date
        prefix = _PREFIX_DATE_RE.match(title)
        if prefix:
            month, day, year = prefix.group(1), prefix.group(2), prefix.group(3)
            full_year = f"20{year}" if len(year) == 2 else year
            try:
                parsed = datetime(int(full_year), int(month), int(day))
                date = parsed.strftime("%B %-d, %Y")
            except ValueError:
                pass
            title = title[prefix.end() :]

        event: NewEvent | None = None
        if item.link:
            page_html = await fetch_url(item.link)
            if "<h1" in page_html:
                event = _parse_jsonld_event(page_html, item.link)

        fallback_title = normalize_escaped_html_text(_FREE_SUFFIX_RE.sub("", title).strip())
        fallback_description_raw = _strip_funcheap_attribution(item.description or "")
        fallback_event = NewEvent(
            title=fallback_title,
            location="San Francisco",
            date=normalize_date_text(date or ""),
            time=None,
            description=normalize_escaped_html_text(fallback_description_raw)
            if fallback_description_raw
            else None,
            source_url=item.link or None,
        )

        candidate = event or fallback_event
        if len(candidate.title) < 3:
            continue
        key = build_event_identity_key(
            title=candidate.title,
            location=candidate.location,
            date_text=normalize_date_text(candidate.date),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        results.append(candidate)

    return results


_ = UTC  # reserved import; avoid unused warning
