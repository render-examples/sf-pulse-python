"""Web Push helpers — pywebpush wrapper.

Reads VAPID config from settings; throws RuntimeError if not configured.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pywebpush import WebPushException, webpush

from app.config import get_settings


@dataclass(frozen=True)
class VapidConfig:
    public_key: str
    private_key: str
    subject: str


def get_vapid_config() -> VapidConfig:
    settings = get_settings()
    if not settings.vapid_public_key or not settings.vapid_private_key:
        raise RuntimeError(
            "VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY must be configured"
        )
    return VapidConfig(
        public_key=settings.vapid_public_key,
        private_key=settings.vapid_private_key,
        subject=settings.vapid_subject,
    )


def get_vapid_public_key() -> str:
    return get_vapid_config().public_key


def send_push(
    *,
    endpoint: str,
    keys: dict,
    payload: dict,
    ttl: int = 60 * 60 * 24,
) -> bool:
    """Send a single push notification. Returns True on success.

    Raises WebPushException on failures the caller should handle (e.g. 410 Gone
    means the subscription should be removed).
    """
    config = get_vapid_config()
    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": keys},
            data=json.dumps(payload),
            vapid_private_key=config.private_key,
            vapid_claims={"sub": config.subject},
            ttl=ttl,
        )
        return True
    except WebPushException as err:
        raise err


def is_subscription_gone(err: WebPushException) -> bool:
    """Return True if the failure means the subscription should be deleted."""
    response = getattr(err, "response", None)
    status = getattr(response, "status_code", None) if response is not None else None
    return status in (404, 410)
