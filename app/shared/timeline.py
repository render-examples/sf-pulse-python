"""Timeline builder — port of shared/timeline.ts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Generic, TypeVar

from app.shared.dates import is_today_or_potential_future, parse_date, today_utc

T = TypeVar("T")


@dataclass(frozen=True)
class TimelineDataRow(Generic[T]):
    item: T
    kind: str = "data"


@dataclass(frozen=True)
class TimelineTodayRow:
    kind: str = "today"


def build_timeline(
    items: list[T],
    get_date_str: Callable[[T], str],
    reference: date | None = None,
) -> list[TimelineDataRow[T] | TimelineTodayRow]:
    reference = reference or today_utc()
    past: list[tuple[float, T]] = []
    future: list[tuple[float, T]] = []

    for item in items:
        text = get_date_str(item)
        d = parse_date(text, reference)
        sort_key = float(d.toordinal()) if d else float("inf")

        if is_today_or_potential_future(text, reference):
            future.append((sort_key, item))
        else:
            past.append((sort_key, item))

    past.sort(key=lambda r: r[0])
    future.sort(key=lambda r: r[0])

    rows: list[TimelineDataRow[T] | TimelineTodayRow] = []
    rows.extend(TimelineDataRow(item=item) for _, item in past)
    rows.append(TimelineTodayRow())
    rows.extend(TimelineDataRow(item=item) for _, item in future)
    return rows
