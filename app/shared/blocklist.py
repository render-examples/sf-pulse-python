"""Restaurant blocklist — port of shared/restaurant-blocklist.ts."""

from __future__ import annotations

import re

_BLOCKED = {"insider tip", "take note", "what to order"}
_WS = re.compile(r"\s+")


def is_blocked_restaurant_name(name: str) -> bool:
    return _WS.sub(" ", name.strip()).lower() in _BLOCKED
