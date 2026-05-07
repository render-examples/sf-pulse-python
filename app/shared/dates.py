"""Date parsing/precision utilities — port of shared/dates.ts.

All comparisons use UTC midnight as the reference; matches the TS behaviour.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from app.shared.html import decode_html_entities

DatePrecision = Literal["day", "day_range", "month", "season", "year", "unknown"]

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_MONTH_INDEX = {name.lower(): idx for idx, name in enumerate(MONTH_NAMES)}

_SEASON_START_MONTH = {
    "spring": 3,
    "summer": 6,
    "fall": 9,
    "autumn": 9,
    "winter": 0,
}

_MONTH_PATTERN = "|".join(MONTH_NAMES)
_SEASON_PATTERN = "spring|summer|fall|autumn|winter"

_RE_WS = re.compile(r"\s+")
_RE_DASH_SPACE = re.compile(r"\s*([–-])\s*")
_RE_COMMA_SPACE = re.compile(r"\s+,")
_RE_YEAR = re.compile(r"\b20\d{2}\b")
_RE_SEASON = re.compile(rf"\b({_SEASON_PATTERN})\b", re.IGNORECASE)
_RE_DAY_OR_RANGE = re.compile(
    rf"(?:{_MONTH_PATTERN})\s+(\d{{1,2}})(?!\d)(?:[–-](\d{{1,2}})(?!\d))?",
    re.IGNORECASE,
)
_RE_UPCOMING = re.compile(r"upcoming|tbd|tba|coming soon", re.IGNORECASE)


@dataclass(frozen=True)
class StructuredDate:
    start_date: str | None
    end_date: str | None
    date_precision: DatePrecision
    is_upcoming: bool


@dataclass(frozen=True)
class _DateRange:
    start: date
    end: date


def today_utc() -> date:
    now = datetime.now(UTC)
    return date(now.year, now.month, now.day)


def _end_of_month(year: int, month_zero_based: int) -> date:
    last = calendar.monthrange(year, month_zero_based + 1)[1]
    return date(year, month_zero_based + 1, last)


def _infer_year(month_zero_based: int, reference: date) -> int:
    return reference.year + 1 if month_zero_based < (reference.month - 1) else reference.year


def _normalize_raw(value: str) -> str:
    s = decode_html_entities(value)
    s = _RE_WS.sub(" ", s)
    s = _RE_DASH_SPACE.sub(r"\1", s)
    s = _RE_COMMA_SPACE.sub(",", s)
    return s.strip()


def _find_month(raw: str) -> int | None:
    lower = raw.lower()
    for name, idx in _MONTH_INDEX.items():
        if name in lower:
            return idx
    return None


def has_explicit_year(raw: str) -> bool:
    return bool(_RE_YEAR.search(raw))


def normalize_date_text(raw: str, reference: date | None = None) -> str:
    reference = reference or today_utc()
    normalized = _normalize_raw(raw)
    if not normalized:
        return normalized
    if has_explicit_year(normalized):
        return normalized

    month = _find_month(normalized)
    if month is not None:
        inferred = _infer_year(month, reference)
        match = _RE_DAY_OR_RANGE.search(normalized)
        if match:
            return f"{MONTH_NAMES[month]} {match.group(1)}{f'–{match.group(2)}' if match.group(2) else ''}, {inferred}"
        return f"{MONTH_NAMES[month]} {inferred}"

    season_match = _RE_SEASON.search(normalized)
    if season_match:
        season = season_match.group(1)
        month_idx = _SEASON_START_MONTH[season.lower()]
        return f"{season[0].upper()}{season[1:].lower()} {_infer_year(month_idx, reference)}"

    return normalized


def get_date_precision(raw: str) -> DatePrecision:
    normalized = _normalize_raw(raw)
    if not normalized:
        return "unknown"

    if _RE_SEASON.search(normalized):
        return "season"

    match = _RE_DAY_OR_RANGE.search(normalized)
    if match:
        return "day_range" if match.group(2) else "day"

    if _find_month(normalized) is not None:
        return "month"

    if has_explicit_year(normalized):
        return "year"

    return "unknown"


def _parse_date_range(raw: str, reference: date | None = None) -> _DateRange | None:
    reference = reference or today_utc()
    normalized = normalize_date_text(raw, reference)
    lower = normalized.lower()
    year_match = re.search(r"\b(20\d{2})\b", lower)
    if not year_match:
        return None
    year = int(year_match.group(1))

    if "spring" in lower:
        return _DateRange(date(year, 4, 1), _end_of_month(year, 5))
    if "summer" in lower:
        return _DateRange(date(year, 7, 1), _end_of_month(year, 8))
    if "fall" in lower or "autumn" in lower:
        return _DateRange(date(year, 10, 1), _end_of_month(year, 11))
    if "winter" in lower:
        return _DateRange(date(year, 1, 1), _end_of_month(year, 1))

    month = _find_month(lower)
    if month is None:
        return _DateRange(date(year, 1, 1), date(year, 12, 31))

    match = _RE_DAY_OR_RANGE.search(lower)
    if match:
        start_day = int(match.group(1))
        end_day = int(match.group(2)) if match.group(2) else start_day
        return _DateRange(date(year, month + 1, start_day), date(year, month + 1, end_day))

    return _DateRange(date(year, month + 1, 1), _end_of_month(year, month))


def parse_date(raw: str, reference: date | None = None) -> date | None:
    rng = _parse_date_range(raw, reference)
    return rng.start if rng else None


def derive_structured_date(raw: str, reference: date | None = None) -> StructuredDate:
    reference = reference or today_utc()
    rng = _parse_date_range(raw, reference)
    return StructuredDate(
        start_date=rng.start.isoformat() if rng else None,
        end_date=rng.end.isoformat() if rng else None,
        date_precision=get_date_precision(raw),
        is_upcoming=is_today_or_potential_future(raw, reference),
    )


def is_upcoming_text(raw: str) -> bool:
    return bool(_RE_UPCOMING.search(raw))


def is_today_or_potential_future(raw: str, reference: date | None = None) -> bool:
    reference = reference or today_utc()
    if is_upcoming_text(raw):
        return True

    rng = _parse_date_range(raw, reference)
    if rng is None:
        return True

    return rng.end >= reference


def compare_date_text(a: str, b: str, reference: date | None = None) -> int:
    reference = reference or today_utc()
    a_date = parse_date(a, reference)
    b_date = parse_date(b, reference)
    a_ord = a_date.toordinal() if a_date else float("inf")
    b_ord = b_date.toordinal() if b_date else float("inf")

    if a_ord != b_ord:
        return -1 if a_ord < b_ord else 1

    a_norm = normalize_date_text(a, reference)
    b_norm = normalize_date_text(b, reference)
    if a_norm < b_norm:
        return -1
    if a_norm > b_norm:
        return 1
    return 0


def format_month_year(d: date) -> str:
    return d.strftime("%B %Y")
