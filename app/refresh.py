"""Apply discovered items + push fan-out — port of server/refresh.ts."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

import asyncpg
from pywebpush import WebPushException

from app import storage
from app.push import is_subscription_gone, send_push
from app.security import is_trusted_push_endpoint
from app.shared.blocklist import is_blocked_restaurant_name
from app.shared.catalog import (
    derive_event_category,
    event_matches_push_preferences,
    format_event_category,
    restaurant_matches_push_preferences,
)
from app.shared.dates import DatePrecision, get_date_precision, normalize_date_text
from app.shared.html import (
    decode_html_entities_recursive,
    normalize_escaped_html_text,
    normalize_whitespace,
)
from app.shared.identity import build_event_identity_key, build_restaurant_identity_key
from app.shared.types import Restaurant, SFEvent
from app.sse import broadcast

log = logging.getLogger(__name__)


@dataclass
class ApplyDiscoveredItemsResult:
    added_restaurants: list[str] = field(default_factory=list)
    added_events: list[str] = field(default_factory=list)
    updated_restaurants: list[str] = field(default_factory=list)


DATE_PRECISION_SCORE: dict[DatePrecision, int] = {
    "unknown": 0,
    "year": 1,
    "season": 2,
    "month": 3,
    "day_range": 4,
    "day": 5,
}


def _restaurant_detail_href(id: int) -> str:
    return f"/restaurants/{id}"


def _event_detail_href(id: int) -> str:
    return f"/events/{id}"


def _describe_restaurant(r: storage.StoredRestaurant) -> str:
    return f"{r.name} ({r.neighborhood} · {r.cuisine})"


def _describe_event(e: storage.StoredEvent) -> str:
    return f"{e.title} ({format_event_category(derive_event_category(e))} · {e.date})"


def _build_push_payload(
    restaurants: list[storage.StoredRestaurant], events: list[storage.StoredEvent]
) -> dict:
    if len(restaurants) == 1 and not events:
        r = restaurants[0]
        return {
            "title": r.name,
            "body": f"{r.neighborhood} · {r.cuisine} · {r.opened_date}",
            "url": _restaurant_detail_href(r.id),
        }
    if not restaurants and len(events) == 1:
        e = events[0]
        return {
            "title": e.title,
            "body": f"{format_event_category(derive_event_category(e))} · {e.date} · {e.location}",
            "url": _event_detail_href(e.id),
        }
    lines = [_describe_restaurant(r) for r in restaurants] + [_describe_event(e) for e in events]
    return {"title": "SF Pulse update", "body": " · ".join(lines), "url": "/"}


def _summarize_restaurants(
    added: list[storage.StoredRestaurant], updated: list[storage.StoredRestaurant]
) -> str | None:
    parts: list[str] = []
    if added:
        suffix = "s" if len(added) > 1 else ""
        parts.append(
            f"{len(added)} new restaurant{suffix}: {', '.join(r.name for r in added)}"
        )
    if updated:
        suffix = "s" if len(updated) > 1 else ""
        parts.append(
            f"{len(updated)} updated restaurant{suffix}: {', '.join(r.name for r in updated)}"
        )
    return " · ".join(parts) if parts else None


def _summarize_events(
    added: list[storage.StoredEvent], updated: list[storage.StoredEvent]
) -> str | None:
    parts: list[str] = []
    if added:
        suffix = "s" if len(added) > 1 else ""
        parts.append(f"{len(added)} new event{suffix}: {', '.join(e.title for e in added)}")
    if updated:
        suffix = "s" if len(updated) > 1 else ""
        parts.append(f"{len(updated)} updated event{suffix}: {', '.join(e.title for e in updated)}")
    return " · ".join(parts) if parts else None


# ── Normalisers used during merge ─────────────────────────────────────────────


def _strip_qualifier(value: str) -> str:
    idx = value.find("·")
    return value if idx == -1 else value[idx + 1 :].strip()


_RE_UPCOMING_SUFFIX = re.compile(r"\s*\(upcoming\)\s*$", re.IGNORECASE)


def _normalize_restaurant_opened_date(value: str) -> str:
    cleaned = _RE_UPCOMING_SUFFIX.sub("", value).strip()
    idx = cleaned.find("·")
    if idx == -1:
        return normalize_date_text(cleaned)
    return f"{cleaned[:idx].strip()} · {normalize_date_text(cleaned[idx + 1 :].strip())}"


_RE_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize_restaurant_name_for_match(value: str) -> str:
    s = normalize_whitespace(decode_html_entities_recursive(value)).lower()
    return _RE_NON_ALNUM.sub(" ", s).strip()


_RE_SF_CA = re.compile(r"\b(?:san francisco|ca)\b")
_RE_ZIP = re.compile(r"\b\d{5}(?:-\d{4})?\b")
_RE_STREET = re.compile(r"\bstreet\b")
_RE_AVENUE = re.compile(r"\bavenue\b")
_RE_BLVD = re.compile(r"\bboulevard\b")
_RE_ROAD = re.compile(r"\broad\b")
_RE_DRIVE = re.compile(r"\bdrive\b")
_RE_PLACE = re.compile(r"\bplace\b")
_RE_TERRACE = re.compile(r"\bterrace\b")
_RE_SUITE = re.compile(r"\bsuite\b")


def _normalize_address_for_match(value: str | None) -> str:
    s = normalize_whitespace(value or "").lower()
    s = _RE_SF_CA.sub(" ", s)
    s = _RE_ZIP.sub(" ", s)
    s = _RE_STREET.sub("st", s)
    s = _RE_AVENUE.sub("ave", s)
    s = _RE_BLVD.sub("blvd", s)
    s = _RE_ROAD.sub("rd", s)
    s = _RE_DRIVE.sub("dr", s)
    s = _RE_PLACE.sub("pl", s)
    s = _RE_TERRACE.sub("ter", s)
    s = _RE_SUITE.sub("ste", s)
    return _RE_NON_ALNUM.sub(" ", s).strip()


def _normalize_event_title_for_match(value: str) -> str:
    return normalize_whitespace(decode_html_entities_recursive(value)).lower()


def _normalize_event_location_for_match(value: str) -> str:
    return normalize_whitespace(decode_html_entities_recursive(value)).lower()


def _precision_score(value: str) -> int:
    return DATE_PRECISION_SCORE[get_date_precision(_strip_qualifier(value))]


def _prefers_incoming_date(existing: str | None, incoming: str) -> bool:
    if not existing:
        return True
    inc = _precision_score(incoming)
    exi = _precision_score(existing)
    if inc != exi:
        return inc > exi
    return len(incoming) > len(existing)


def _is_generic_neighborhood(value: str | None) -> bool:
    return normalize_whitespace(value or "").lower() == "san francisco"


def _is_generic_cuisine(value: str | None) -> bool:
    return normalize_whitespace(value or "").lower() == "new opening"


def _is_generic_event_location(value: str | None) -> bool:
    return normalize_whitespace(value or "").lower() == "san francisco"


_RE_FUNCHEAP_FOOTER = re.compile(r"appeared first on funcheap")


def _event_description_score(value: str | None) -> int:
    if not value:
        return 0
    s = decode_html_entities_recursive(value).lower()
    if _RE_FUNCHEAP_FOOTER.search(s):
        return 1
    return len(s) + 10


def _merge_restaurant(
    incoming: storage.NewRestaurant, existing: storage.StoredRestaurant | None
) -> storage.NewRestaurant:
    next_kind = incoming.highlight_kind or (existing.highlight_kind if existing else "opening")
    inc_date = _normalize_restaurant_opened_date(incoming.opened_date)
    exi_date = _normalize_restaurant_opened_date(existing.opened_date) if existing else None
    inc_neighborhood = normalize_whitespace(incoming.neighborhood)
    exi_neighborhood = normalize_whitespace(existing.neighborhood) if existing else ""
    inc_cuisine = normalize_whitespace(incoming.cuisine)
    exi_cuisine = normalize_whitespace(existing.cuisine) if existing else ""

    chosen_neighborhood = (
        inc_neighborhood
        if inc_neighborhood
        and (not _is_generic_neighborhood(inc_neighborhood) or not exi_neighborhood)
        else (exi_neighborhood or inc_neighborhood)
    )
    chosen_cuisine = (
        inc_cuisine
        if inc_cuisine and (not _is_generic_cuisine(inc_cuisine) or not exi_cuisine)
        else (exi_cuisine or inc_cuisine)
    )
    chosen_address = (
        normalize_whitespace(incoming.address or "")
        or normalize_whitespace(existing.address or "" if existing else "")
        or None
    )
    chosen_opened = inc_date if _prefers_incoming_date(exi_date, inc_date) else (exi_date or inc_date)

    return storage.NewRestaurant(
        name=normalize_whitespace(decode_html_entities_recursive(incoming.name)),
        neighborhood=chosen_neighborhood,
        cuisine=chosen_cuisine,
        address=chosen_address,
        opened_date=chosen_opened,
        source_url=incoming.source_url or (existing.source_url if existing else None),
        highlight_kind=next_kind,
    )


def _merge_event(
    incoming: storage.NewEvent, existing: storage.StoredEvent | None
) -> storage.NewEvent:
    inc_date = normalize_date_text(incoming.date)
    exi_date = normalize_date_text(existing.date) if existing else None
    inc_title = normalize_escaped_html_text(incoming.title)
    exi_title = normalize_escaped_html_text(existing.title) if existing else None
    inc_loc = normalize_whitespace(decode_html_entities_recursive(incoming.location))
    exi_loc = normalize_whitespace(decode_html_entities_recursive(existing.location if existing else ""))
    inc_desc = normalize_escaped_html_text(incoming.description) if incoming.description else None
    exi_desc = (
        normalize_escaped_html_text(existing.description)
        if existing and existing.description
        else None
    )

    chosen_title = inc_title if (len(inc_title) >= len(exi_title or "")) else (exi_title or inc_title)
    chosen_location = (
        inc_loc
        if inc_loc and (not _is_generic_event_location(inc_loc) or not exi_loc)
        else (exi_loc or inc_loc)
    )
    chosen_date = inc_date if _prefers_incoming_date(exi_date, inc_date) else (exi_date or inc_date)
    chosen_description = (
        inc_desc
        if _event_description_score(inc_desc) >= _event_description_score(exi_desc)
        else exi_desc
    )

    return storage.NewEvent(
        title=chosen_title,
        location=chosen_location,
        date=chosen_date,
        time=incoming.time or (existing.time if existing else None),
        description=chosen_description,
        source_url=incoming.source_url or (existing.source_url if existing else None),
    )


# ── Matching strategies ───────────────────────────────────────────────────────


def _find_matching_restaurant(
    r: storage.NewRestaurant, existing: list[storage.StoredRestaurant]
) -> storage.StoredRestaurant | None:
    identity = build_restaurant_identity_key(name=r.name, address=r.address, neighborhood=r.neighborhood)
    for cand in existing:
        if (
            build_restaurant_identity_key(
                name=cand.name, address=cand.address, neighborhood=cand.neighborhood
            )
            == identity
        ):
            return cand
    if r.highlight_kind == "michelin":
        for cand in existing:
            if cand.name.lower() == r.name.lower():
                return cand

    inc_addr = _normalize_address_for_match(r.address)
    if not inc_addr:
        return None
    inc_name = _normalize_restaurant_name_for_match(r.name)
    for cand in existing:
        cand_addr = _normalize_address_for_match(cand.address)
        if not cand_addr or cand_addr != inc_addr:
            continue
        cand_name = _normalize_restaurant_name_for_match(cand.name)
        if inc_name in cand_name or cand_name in inc_name:
            return cand
    return None


def _build_event_source_match_key(
    *, title: str, date: str, source_url: str | None
) -> str | None:
    if not source_url:
        return None
    return "|".join(
        [source_url, _normalize_event_title_for_match(title), normalize_date_text(date).lower()]
    )


def _find_matching_event(
    e: storage.NewEvent, existing: list[storage.StoredEvent]
) -> storage.StoredEvent | None:
    dedupe = build_event_identity_key(
        title=e.title, location=e.location, date_text=normalize_date_text(e.date)
    )
    for cand in existing:
        if cand.dedupe_key == dedupe:
            return cand

    src_key = _build_event_source_match_key(title=e.title, date=e.date, source_url=e.source_url)
    if src_key:
        for cand in existing:
            cand_key = _build_event_source_match_key(
                title=cand.title, date=cand.date, source_url=cand.source_url
            )
            if cand_key == src_key:
                return cand

    norm_title = _normalize_event_title_for_match(e.title)
    norm_date = normalize_date_text(e.date).lower()
    norm_loc = _normalize_event_location_for_match(e.location)
    for cand in existing:
        if (
            _normalize_event_title_for_match(cand.title) == norm_title
            and normalize_date_text(cand.date).lower() == norm_date
            and (
                _normalize_event_location_for_match(cand.location) == norm_loc
                or _is_generic_event_location(cand.location)
                or _is_generic_event_location(e.location)
            )
        ):
            return cand
    return None


# ── Change detection ──────────────────────────────────────────────────────────


def _restaurant_changed(existing: storage.StoredRestaurant, n: storage.NewRestaurant) -> bool:
    return (
        existing.name != n.name
        or existing.neighborhood != n.neighborhood
        or existing.cuisine != n.cuisine
        or existing.address != n.address
        or existing.opened_date != n.opened_date
        or existing.source_url != n.source_url
        or existing.highlight_kind != (n.highlight_kind or "opening")
    )


def _event_changed(existing: storage.StoredEvent, n: storage.NewEvent) -> bool:
    return (
        existing.title != n.title
        or existing.location != n.location
        or existing.date != n.date
        or existing.time != n.time
        or existing.description != n.description
        or existing.source_url != n.source_url
    )


# ── Public types for upserted broadcast events ────────────────────────────────


def _stored_restaurant_to_public(r: storage.StoredRestaurant) -> Restaurant:
    return Restaurant.model_validate(r.model_dump())


def _stored_event_to_public(e: storage.StoredEvent) -> SFEvent:
    return SFEvent.model_validate(e.model_dump())


# ── Push fan-out ──────────────────────────────────────────────────────────────


async def _push_to_interested(
    restaurants: list[storage.StoredRestaurant],
    events: list[storage.StoredEvent],
    *,
    pool: asyncpg.Pool | None = None,
) -> None:
    try:
        from app.push import get_vapid_config

        get_vapid_config()
    except RuntimeError as err:
        log.warning("[push] notifications disabled: %s", err)
        return

    subs = await storage.get_subscriptions(pool=pool)

    async def send(sub: storage.StoredPushSubscription) -> None:
        if not is_trusted_push_endpoint(sub.endpoint):
            await storage.remove_subscription(sub.endpoint, pool=pool)
            return
        matching_r = [r for r in restaurants if restaurant_matches_push_preferences(_stored_restaurant_to_public(r), sub.preferences)]
        matching_e = [e for e in events if event_matches_push_preferences(_stored_event_to_public(e), sub.preferences)]
        if not matching_r and not matching_e:
            return
        payload = _build_push_payload(matching_r, matching_e)
        try:
            await asyncio.to_thread(
                send_push,
                endpoint=sub.endpoint,
                keys=dict(sub.keys),
                payload=payload,
            )
        except WebPushException as err:
            if is_subscription_gone(err):
                await storage.remove_subscription(sub.endpoint, pool=pool)
            else:
                log.warning("[push] send failed for %s: %s", sub.endpoint, err)

    await asyncio.gather(*(send(s) for s in subs), return_exceptions=True)


# ── Public entrypoint ─────────────────────────────────────────────────────────


async def apply_discovered_items(
    *,
    restaurants: Iterable[storage.NewRestaurant] = (),
    events: Iterable[storage.NewEvent] = (),
    pool: asyncpg.Pool | None = None,
) -> ApplyDiscoveredItemsResult:
    existing_r = await storage.get_restaurants(pool=pool)
    existing_e = await storage.get_events(pool=pool)
    result = ApplyDiscoveredItemsResult()
    added_r_rows: list[storage.StoredRestaurant] = []
    updated_r_rows: list[storage.StoredRestaurant] = []
    added_e_rows: list[storage.StoredEvent] = []
    updated_e_rows: list[storage.StoredEvent] = []
    versions: list[str] = []

    for r in restaurants:
        if is_blocked_restaurant_name(r.name):
            continue
        match = _find_matching_restaurant(r, existing_r)
        merged = _merge_restaurant(r, match)
        if match is None:
            persisted = await storage.add_restaurant(merged, pool=pool)
            update = await storage.record_update("restaurant", persisted.name, "added", pool=pool)
            versions.append(update.occurred_at.isoformat())
            result.added_restaurants.append(persisted.name)
            added_r_rows.append(persisted)
            existing_r.append(persisted)
            continue
        if not _restaurant_changed(match, merged):
            continue
        persisted = await storage.update_restaurant(match.id, merged, pool=pool)
        update = await storage.record_update("restaurant", persisted.name, "updated", pool=pool)
        versions.append(update.occurred_at.isoformat())
        result.updated_restaurants.append(persisted.name)
        updated_r_rows.append(persisted)
        for idx, item in enumerate(existing_r):
            if item.id == match.id:
                existing_r[idx] = persisted
                break

    for e in events:
        match = _find_matching_event(e, existing_e)
        merged = _merge_event(e, match)
        if match is None:
            persisted = await storage.add_event(merged, pool=pool)
            update = await storage.record_update("event", persisted.title, "added", pool=pool)
            versions.append(update.occurred_at.isoformat())
            result.added_events.append(persisted.title)
            added_e_rows.append(persisted)
            existing_e.append(persisted)
            continue
        if not _event_changed(match, merged):
            continue
        persisted = await storage.update_event(match.id, merged, pool=pool)
        update = await storage.record_update("event", persisted.title, "updated", pool=pool)
        versions.append(update.occurred_at.isoformat())
        updated_e_rows.append(persisted)
        for idx, item in enumerate(existing_e):
            if item.id == match.id:
                existing_e[idx] = persisted
                break

    if result.added_restaurants or result.updated_restaurants or result.added_events or updated_e_rows:
        version = sorted(versions)[-1] if versions else None
        if version is None:
            ts = await storage.get_latest_update_timestamp(pool=pool)
            version = ts.isoformat() if ts else None

        if added_r_rows or updated_r_rows:
            await broadcast(
                "restaurants",
                {
                    "version": version,
                    "upserted": [r.model_dump(mode="json") for r in [*added_r_rows, *updated_r_rows]],
                    "deleted": [],
                    "summary": _summarize_restaurants(added_r_rows, updated_r_rows),
                },
            )
        if added_e_rows or updated_e_rows:
            await broadcast(
                "events",
                {
                    "version": version,
                    "upserted": [e.model_dump(mode="json") for e in [*added_e_rows, *updated_e_rows]],
                    "deleted": [],
                    "summary": _summarize_events(added_e_rows, updated_e_rows),
                },
            )
        await _push_to_interested([*added_r_rows, *updated_r_rows], added_e_rows, pool=pool)

    return result
