"""Async PostgreSQL pool — port of server/db.ts.

Lazy initialization so tests can run without DATABASE_URL set (they inject their
own pool via testcontainers).
"""

from __future__ import annotations

from typing import Any

import asyncpg

from app.config import get_settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is required")
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=1,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def set_pool_for_tests(pool: asyncpg.Pool | None) -> None:
    """Inject a pool for tests (or reset to None)."""
    global _pool
    _pool = pool


async def fetch(sql: str, *params: Any) -> list[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch(sql, *params)


async def fetchrow(sql: str, *params: Any) -> asyncpg.Record | None:
    pool = await get_pool()
    return await pool.fetchrow(sql, *params)


async def execute(sql: str, *params: Any) -> str:
    pool = await get_pool()
    return await pool.execute(sql, *params)
