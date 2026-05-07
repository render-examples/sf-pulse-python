"""CLI entrypoint: `uv run python -m bin.migrate`."""

from __future__ import annotations

import asyncio
import sys

from app.db import close_pool, get_pool
from app.migrate import migrate


async def main() -> None:
    pool = await get_pool()
    try:
        await migrate(pool)
        print("[migrate] done")
    finally:
        await close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as err:  # noqa: BLE001
        print(err, file=sys.stderr)
        sys.exit(1)
