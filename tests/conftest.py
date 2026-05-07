"""Shared pytest fixtures.

Boots a Postgres testcontainer once per session, runs migrations once, and
provides per-test isolation by truncating data tables (schema_migrations is
preserved so we don't pay for re-running migrations every test).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

# Set env vars BEFORE importing the app — pydantic-settings caches them.
os.environ.setdefault("CRON_SECRET", "test-secret")
os.environ.setdefault("VAPID_PUBLIC_KEY", "")
os.environ.setdefault("VAPID_PRIVATE_KEY", "")
os.environ.setdefault("LLM_API_KEY", "")

import asyncpg  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402


@pytest.fixture(scope="session")
def postgres_container() -> "PostgresContainer":
    container = PostgresContainer("postgres:16-alpine")
    container.start()
    try:
        # asyncpg expects postgresql:// — testcontainers gives postgresql+psycopg2://
        raw_url = container.get_connection_url()
        async_url = raw_url.replace("postgresql+psycopg2://", "postgresql://")
        os.environ["DATABASE_URL"] = async_url

        # Reset cached settings now that DATABASE_URL is set.
        from app.config import get_settings

        get_settings.cache_clear()

        yield container
    finally:
        container.stop()


@pytest_asyncio.fixture(scope="session")
async def pool(postgres_container: "PostgresContainer") -> AsyncIterator[asyncpg.Pool]:
    from app.config import get_settings
    from app.db import set_pool_for_tests
    from app.migrate import migrate

    db_url = get_settings().database_url
    p = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
    set_pool_for_tests(p)
    await migrate(p)
    try:
        yield p
    finally:
        set_pool_for_tests(None)
        await p.close()


@pytest_asyncio.fixture
async def clean_db(pool: asyncpg.Pool) -> AsyncIterator[asyncpg.Pool]:
    """Truncate data tables between tests; keep schema_migrations intact."""
    yield pool
    # Run after the test so the next test starts clean.
    async with pool.acquire() as conn:
        await conn.execute(
            """
            TRUNCATE TABLE
                push_subscriptions,
                data_updates,
                cron_runs,
                events,
                restaurants
            RESTART IDENTITY CASCADE
            """
        )


@pytest_asyncio.fixture
async def client(pool: asyncpg.Pool) -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def cron_headers() -> dict[str, str]:
    return {"x-cron-secret": "test-secret"}


class FakeLLMClient:
    """Records all calls and returns whatever the test queues up."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.responses: list[object] = []

    def queue(self, response: object) -> None:
        self.responses.append(response)

    async def extract_structured(
        self,
        *,
        schema,
        prompt: str,
        text: str,
        model: str | None = None,
    ):
        self.calls.append(
            {"schema": schema, "prompt": prompt, "text": text, "model": model}
        )
        if not self.responses:
            return schema()
        head = self.responses.pop(0)
        if isinstance(head, BaseException):
            raise head
        return head


@pytest.fixture
def mock_llm() -> FakeLLMClient:
    from app.llm import set_llm_client_for_tests

    fake = FakeLLMClient()
    set_llm_client_for_tests(fake)
    try:
        yield fake
    finally:
        set_llm_client_for_tests(None)
