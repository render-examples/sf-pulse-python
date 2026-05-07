"""Constants for source extractors — port of bin/cron-refresh/constants.ts."""

from __future__ import annotations

CRON_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 sf-pulse-cron/1.0"
)

MONTH_NAME_PATTERN = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)

WEEKDAY_PATTERN = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"

THREE_MONTHS_DAYS = 90
FETCH_TIMEOUT_SECONDS = 10.0
LONG_FETCH_TIMEOUT_SECONDS = 15.0
MAX_REDIRECTS = 5
BODY_TEXT_LIMIT = 8_000
