"""Event API endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient

from app import storage


async def test_list_events(client: AsyncClient, clean_db) -> None:
    await storage.add_event(
        storage.NewEvent(
            title="Outside Lands",
            location="Golden Gate Park",
            date="August 8, 2026",
        ),
        pool=clean_db,
    )
    resp = await client.get("/api/events")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "Outside Lands"


async def test_get_event_by_id_404(client: AsyncClient, clean_db) -> None:
    resp = await client.get("/api/events/99999")
    assert resp.status_code == 404


async def test_delete_event_with_cron_secret(
    client: AsyncClient, clean_db, cron_headers
) -> None:
    e = await storage.add_event(
        storage.NewEvent(
            title="Concert",
            location="SoMa",
            date="August 1, 2026",
        ),
        pool=clean_db,
    )
    miss = await client.delete(f"/api/events/{e.id}")
    assert miss.status_code == 401

    ok = await client.delete(f"/api/events/{e.id}", headers=cron_headers)
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}
    assert await storage.get_event_by_id(e.id, pool=clean_db) is None
