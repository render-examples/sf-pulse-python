"""Tests for app.shared.dates."""

from __future__ import annotations

from datetime import date

from app.shared.dates import (
    compare_date_text,
    derive_structured_date,
    get_date_precision,
    is_today_or_potential_future,
    normalize_date_text,
)

REF = date(2026, 5, 1)


def test_get_date_precision_day() -> None:
    assert get_date_precision("April 15, 2026") == "day"


def test_get_date_precision_day_range() -> None:
    assert get_date_precision("April 15-17, 2026") == "day_range"


def test_get_date_precision_month() -> None:
    assert get_date_precision("April 2026") == "month"


def test_get_date_precision_season() -> None:
    assert get_date_precision("Spring 2026") == "season"


def test_get_date_precision_year_only() -> None:
    assert get_date_precision("2026") == "year"


def test_get_date_precision_unknown() -> None:
    assert get_date_precision("TBD") == "unknown"


def test_normalize_infers_year_when_missing() -> None:
    # April is before May (the reference month) → next year inferred.
    out = normalize_date_text("April 15", reference=REF)
    assert out == "April 15, 2027"


def test_normalize_keeps_explicit_year() -> None:
    assert normalize_date_text("April 15, 2026", reference=REF) == "April 15, 2026"


def test_normalize_season_infers_year() -> None:
    # September (idx 8) is after current month-1 (4), so same year.
    out = normalize_date_text("Fall", reference=REF)
    assert out == "Fall 2026"


def test_derive_structured_date_day_range() -> None:
    s = derive_structured_date("April 15-17, 2026", reference=REF)
    assert s.start_date == "2026-04-15"
    assert s.end_date == "2026-04-17"
    assert s.date_precision == "day_range"


def test_derive_structured_date_month_only() -> None:
    s = derive_structured_date("June 2026", reference=REF)
    assert s.start_date == "2026-06-01"
    assert s.end_date == "2026-06-30"
    assert s.date_precision == "month"


def test_derive_structured_date_unknown_string() -> None:
    s = derive_structured_date("coming soon", reference=REF)
    assert s.start_date is None
    assert s.end_date is None
    assert s.date_precision == "unknown"
    assert s.is_upcoming is True  # "coming soon" matches upcoming regex


def test_is_today_or_potential_future_past() -> None:
    # Way in the past → False.
    assert is_today_or_potential_future("January 1, 2020", reference=REF) is False


def test_is_today_or_potential_future_future() -> None:
    assert is_today_or_potential_future("December 1, 2030", reference=REF) is True


def test_compare_date_text_orders_chronologically() -> None:
    assert compare_date_text("April 15, 2026", "May 15, 2026", reference=REF) < 0
    assert compare_date_text("May 15, 2026", "April 15, 2026", reference=REF) > 0
    assert compare_date_text("April 15, 2026", "April 15, 2026", reference=REF) == 0
