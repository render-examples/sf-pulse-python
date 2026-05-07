"""Health endpoint smoke test."""

from __future__ import annotations

from httpx import AsyncClient


async def test_healthz_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
