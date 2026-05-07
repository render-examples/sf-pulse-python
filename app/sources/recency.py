"""Article recency filter — port of bin/cron-refresh/recency.ts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.sources.constants import THREE_MONTHS_DAYS


def is_recent(pub_date: str | None) -> bool:
    """True if pub_date parses to within the last 90 days, or cannot be parsed at all
    (mirrors TS: missing/invalid dates fall through as recent)."""
    if not pub_date:
        return True
    try:
        parsed = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        try:
            from email.utils import parsedate_to_datetime

            parsed = parsedate_to_datetime(pub_date)
        except (ValueError, TypeError):
            return True
        if parsed is None:
            return True

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return datetime.now(UTC) - parsed < timedelta(days=THREE_MONTHS_DAYS)
