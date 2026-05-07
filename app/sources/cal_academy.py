"""California Academy of Sciences events scraper.

Port of bin/cron-refresh/events.ts (fetchCalAcademy / parseCalAcademyPage).
Reuses the museum-events parser from app.sources.famsf.
"""

from __future__ import annotations

import re

from app.sources.constants import LONG_FETCH_TIMEOUT_SECONDS
from app.sources.famsf import parse_museum_events
from app.sources.http import fetch_url
from app.storage import NewEvent

CAL_ACADEMY_URL = "https://www.calacademy.org/events"

_CAL_ACADEMY_IGNORED = re.compile(
    r"^(?:planetarium|aquarium|rainforest|nightlife|today at the academy|museum map)$",
    re.IGNORECASE,
)


async def fetch_cal_academy_events() -> list[NewEvent]:
    """Fetch and parse the California Academy of Sciences events calendar."""
    html = await fetch_url(CAL_ACADEMY_URL, timeout=LONG_FETCH_TIMEOUT_SECONDS)
    if not html:
        return []
    return parse_museum_events(
        html,
        location="California Academy of Sciences, Golden Gate Park",
        source_url=CAL_ACADEMY_URL,
        heading_levels="234",
        ignored_title_re=_CAL_ACADEMY_IGNORED,
    )
