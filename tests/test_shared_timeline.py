"""Tests for app.shared.timeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.shared.timeline import TimelineDataRow, TimelineTodayRow, build_timeline


@dataclass
class Item:
    id: int
    date: str


REF = date(2026, 5, 1)


def test_build_timeline_groups_past_today_future() -> None:
    items = [
        Item(1, "January 1, 2026"),  # past
        Item(2, "April 1, 2026"),  # past
        Item(3, "September 1, 2026"),  # future
        Item(4, "June 1, 2026"),  # future
    ]
    rows = build_timeline(items, lambda i: i.date, reference=REF)

    today_idx = next(i for i, r in enumerate(rows) if isinstance(r, TimelineTodayRow))
    past_rows = [r for r in rows[:today_idx] if isinstance(r, TimelineDataRow)]
    future_rows = [r for r in rows[today_idx + 1 :] if isinstance(r, TimelineDataRow)]

    assert [r.item.id for r in past_rows] == [1, 2]
    assert [r.item.id for r in future_rows] == [4, 3]


def test_build_timeline_always_includes_today_marker() -> None:
    rows = build_timeline([], lambda i: "", reference=REF)
    assert len(rows) == 1
    assert isinstance(rows[0], TimelineTodayRow)


def test_build_timeline_unparseable_date_treated_as_future() -> None:
    rows = build_timeline(
        [Item(1, "TBD"), Item(2, "January 1, 2020")],
        lambda i: i.date,
        reference=REF,
    )
    today_idx = next(i for i, r in enumerate(rows) if isinstance(r, TimelineTodayRow))
    past_ids = [r.item.id for r in rows[:today_idx] if isinstance(r, TimelineDataRow)]
    future_ids = [r.item.id for r in rows[today_idx + 1 :] if isinstance(r, TimelineDataRow)]
    assert past_ids == [2]
    assert future_ids == [1]
