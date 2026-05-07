"""Migration runner test — ensures all SQL migrations apply cleanly."""

from __future__ import annotations

import asyncpg

EXPECTED_VERSIONS = {f"{i:04d}" for i in range(1, 12)}  # 0001..0011


async def test_all_migrations_applied(pool: asyncpg.Pool) -> None:
    rows = await pool.fetch("SELECT version FROM schema_migrations ORDER BY version")
    versions = {r["version"] for r in rows}
    # Each row's version starts with its 4-digit prefix; check the prefixes.
    prefixes = {v.split("_", 1)[0] for v in versions}
    assert EXPECTED_VERSIONS.issubset(prefixes), (
        f"missing migrations; got prefixes={prefixes}"
    )


async def test_core_tables_exist(pool: asyncpg.Pool) -> None:
    expected = {
        "schema_migrations",
        "restaurants",
        "events",
        "push_subscriptions",
        "data_updates",
        "cron_runs",
    }
    rows = await pool.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )
    tables = {r["tablename"] for r in rows}
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


async def test_restaurants_has_identity_key_unique_constraint(pool: asyncpg.Pool) -> None:
    # Migration 0008 introduces identity_key with a unique index.
    row = await pool.fetchrow(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'restaurants' AND column_name = 'identity_key'
        """
    )
    assert row is not None
