"""Refresh pipeline integration tests — apply_discovered_items end-to-end."""

from __future__ import annotations

from unittest.mock import AsyncMock

import asyncpg

from app import refresh, storage


async def test_apply_discovered_items_adds_new_records(
    clean_db: asyncpg.Pool, monkeypatch
) -> None:
    broadcast_mock = AsyncMock()
    monkeypatch.setattr("app.refresh.broadcast", broadcast_mock)

    result = await refresh.apply_discovered_items(
        restaurants=[
            storage.NewRestaurant(
                name="Joe's", neighborhood="Mission", cuisine="Pizza", opened_date="April 15, 2026"
            )
        ],
        events=[
            storage.NewEvent(
                title="Outside Lands",
                location="Golden Gate Park",
                date="August 8-10, 2026",
            )
        ],
        pool=clean_db,
    )

    assert result.added_restaurants == ["Joe's"]
    assert result.added_events == ["Outside Lands"]
    assert result.updated_restaurants == []
    # Two broadcasts: one for restaurants, one for events.
    assert broadcast_mock.await_count == 2
    channels = {call.args[0] for call in broadcast_mock.await_args_list}
    assert channels == {"restaurants", "events"}


async def test_apply_discovered_items_blocks_named_filter(
    clean_db: asyncpg.Pool, monkeypatch
) -> None:
    monkeypatch.setattr("app.refresh.broadcast", AsyncMock())

    result = await refresh.apply_discovered_items(
        restaurants=[
            storage.NewRestaurant(
                name="Insider Tip",  # blocked phrase
                neighborhood="Mission",
                cuisine="Pizza",
                opened_date="April 15, 2026",
            )
        ],
        pool=clean_db,
    )
    assert result.added_restaurants == []
    rows = await clean_db.fetch("SELECT COUNT(*) AS c FROM restaurants")
    assert rows[0]["c"] == 0


async def test_apply_discovered_items_updates_on_changed_field(
    clean_db: asyncpg.Pool, monkeypatch
) -> None:
    monkeypatch.setattr("app.refresh.broadcast", AsyncMock())

    initial = storage.NewRestaurant(
        name="Joe's",
        neighborhood="Mission",
        cuisine="Pizza",
        opened_date="April 2026",
        address="123 Mission St",
    )
    await refresh.apply_discovered_items(restaurants=[initial], pool=clean_db)

    # Same identity (name+address), more precise opened_date → triggers update.
    refined = storage.NewRestaurant(
        name="Joe's",
        neighborhood="Mission",
        cuisine="Pizza",
        opened_date="April 15, 2026",
        address="123 Mission St",
    )
    result = await refresh.apply_discovered_items(restaurants=[refined], pool=clean_db)
    assert result.added_restaurants == []
    assert result.updated_restaurants == ["Joe's"]


async def test_push_skipped_when_vapid_not_configured(
    clean_db: asyncpg.Pool, monkeypatch, caplog
) -> None:
    """With no VAPID keys (default in test env), push fan-out short-circuits."""
    monkeypatch.setattr("app.refresh.broadcast", AsyncMock())

    # Pre-seed a subscription so that if push WERE enabled, it would try to send.
    await storage.add_subscription(
        endpoint="https://fcm.googleapis.com/fcm/send/abc",
        keys={"p256dh": "x" * 10, "auth": "y" * 10},
        pool=clean_db,
    )

    # Use a sentinel by spying on send_push — it must NOT be invoked.
    send_mock = AsyncMock()
    monkeypatch.setattr("app.refresh.send_push", send_mock)

    await refresh.apply_discovered_items(
        restaurants=[
            storage.NewRestaurant(
                name="Joe's",
                neighborhood="Mission",
                cuisine="Pizza",
                opened_date="April 15, 2026",
            )
        ],
        pool=clean_db,
    )
    assert send_mock.await_count == 0
