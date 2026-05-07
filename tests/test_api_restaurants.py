"""Restaurant API endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient

from app import storage


async def test_list_restaurants_returns_visible(
    client: AsyncClient, clean_db
) -> None:
    await storage.add_restaurant(
        storage.NewRestaurant(
            name="Joe's",
            neighborhood="Mission",
            cuisine="Pizza",
            opened_date="April 15, 2026",
        ),
        pool=clean_db,
    )
    resp = await client.get("/api/restaurants")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Joe's"


async def test_get_restaurant_by_id(client: AsyncClient, clean_db) -> None:
    r = await storage.add_restaurant(
        storage.NewRestaurant(
            name="Sushi Place",
            neighborhood="Mission",
            cuisine="Sushi",
            opened_date="May 1, 2026",
        ),
        pool=clean_db,
    )
    resp = await client.get(f"/api/restaurants/{r.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == r.id

    miss = await client.get("/api/restaurants/99999")
    assert miss.status_code == 404


async def test_delete_restaurant_requires_cron_secret(
    client: AsyncClient, clean_db, cron_headers
) -> None:
    r = await storage.add_restaurant(
        storage.NewRestaurant(
            name="Joe's",
            neighborhood="Mission",
            cuisine="Pizza",
            opened_date="April 15, 2026",
        ),
        pool=clean_db,
    )
    no_secret = await client.delete(f"/api/restaurants/{r.id}")
    assert no_secret.status_code == 401

    with_secret = await client.delete(
        f"/api/restaurants/{r.id}", headers=cron_headers
    )
    assert with_secret.status_code == 200
    assert with_secret.json() == {"ok": True}
    assert await storage.get_restaurant_by_id(r.id, pool=clean_db) is None
