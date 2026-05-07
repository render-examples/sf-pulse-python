"""Minimal async migration runner — port of server/migrate.ts.

Migrations live in /migrations as plain SQL files named NNNN_description.sql.
Applied migrations are tracked in the `schema_migrations` table. Idempotent.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"


async def _ensure_migrations_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version    TEXT        PRIMARY KEY,
          applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


async def _applied_versions(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
    return {r["version"] for r in rows}


async def migrate(pool: asyncpg.Pool, migrations_dir: Path | None = None) -> None:
    directory = migrations_dir or MIGRATIONS_DIR
    files = sorted(p for p in directory.iterdir() if p.suffix == ".sql")

    async with pool.acquire() as conn:
        await _ensure_migrations_table(conn)
        applied = await _applied_versions(conn)

    for file in files:
        version = file.stem
        if version in applied:
            continue

        sql = file.read_text(encoding="utf-8")
        async with pool.acquire() as conn:
            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)",
                        version,
                    )
                print(f"[migrate] applied {file.name}")
            except Exception as err:  # noqa: BLE001
                raise RuntimeError(f"[migrate] failed on {file.name}: {err}") from err
