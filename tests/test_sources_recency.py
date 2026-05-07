"""Recency filter tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.sources.recency import is_recent


def test_is_recent_none_returns_true() -> None:
    """No pub_date → treat as recent (mirrors TS behavior)."""
    assert is_recent(None) is True
    assert is_recent("") is True


def test_is_recent_unparseable_returns_true() -> None:
    assert is_recent("garbage-not-a-date") is True


def test_is_recent_today_iso() -> None:
    today = datetime.now(UTC).isoformat()
    assert is_recent(today) is True


def test_is_recent_old_returns_false() -> None:
    old = (datetime.now(UTC) - timedelta(days=200)).isoformat()
    assert is_recent(old) is False


def test_is_recent_rfc822_parses() -> None:
    rfc = (datetime.now(UTC) - timedelta(days=5)).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
    assert is_recent(rfc) is True


def test_is_recent_naive_iso_assumed_utc() -> None:
    recent_naive = (datetime.now(UTC) - timedelta(days=1)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    assert is_recent(recent_naive) is True
