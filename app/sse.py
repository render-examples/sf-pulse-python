"""SSE realtime broadcaster — port of server/sse.ts.

When REDIS_URL is set, broadcasts happen via Redis pub/sub (channel
`sf-pulse:realtime`) so multiple instances see each other's events.
Otherwise, falls back to in-process fan-out to local SSE clients.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

from app.config import get_settings

REALTIME_CHANNEL = "sf-pulse:realtime"
HEARTBEAT_INTERVAL = 25.0  # seconds

log = logging.getLogger(__name__)


@dataclass
class SseEvent:
    event: str
    data: Any


class _Hub:
    def __init__(self) -> None:
        self._clients: set[asyncio.Queue[SseEvent | None]] = set()
        self._publisher: redis.Redis | None = None
        self._subscriber: redis.Redis | None = None
        self._subscriber_task: asyncio.Task | None = None

    def _redis_url(self) -> str | None:
        url = get_settings().redis_url
        return url.strip() or None if url else None

    async def initialize(self) -> None:
        url = self._redis_url()
        if not url or self._subscriber_task is not None:
            return
        self._subscriber = redis.from_url(url, decode_responses=True)
        pubsub = self._subscriber.pubsub()
        await pubsub.subscribe(REALTIME_CHANNEL)

        async def reader() -> None:
            try:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    raw = message.get("data")
                    if not isinstance(raw, str):
                        continue
                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    event = parsed.get("event")
                    if not isinstance(event, str) or not event:
                        continue
                    self._fanout_local(SseEvent(event=event, data=parsed.get("data")))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("[realtime] subscriber loop error")
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe(REALTIME_CHANNEL)
                    await pubsub.close()

        self._subscriber_task = asyncio.create_task(reader())

    async def shutdown(self) -> None:
        if self._subscriber_task is not None:
            self._subscriber_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._subscriber_task
            self._subscriber_task = None
        if self._subscriber is not None:
            with contextlib.suppress(Exception):
                await self._subscriber.aclose()
            self._subscriber = None
        if self._publisher is not None:
            with contextlib.suppress(Exception):
                await self._publisher.aclose()
            self._publisher = None
        for q in list(self._clients):
            with contextlib.suppress(Exception):
                q.put_nowait(None)
        self._clients.clear()

    def _fanout_local(self, evt: SseEvent) -> None:
        for q in self._clients:
            with contextlib.suppress(Exception):
                q.put_nowait(evt)

    async def _get_publisher(self) -> redis.Redis | None:
        url = self._redis_url()
        if not url:
            return None
        if self._publisher is None:
            self._publisher = redis.from_url(url, decode_responses=True)
        return self._publisher

    async def broadcast(self, event: str, data: Any) -> None:
        publisher = await self._get_publisher()
        if publisher is None:
            self._fanout_local(SseEvent(event=event, data=data))
            return
        try:
            await publisher.publish(REALTIME_CHANNEL, json.dumps({"event": event, "data": data}))
        except Exception as err:  # noqa: BLE001
            log.warning("[realtime] redis publish failed: %s", err)
            self._publisher = None

    async def stream(self) -> AsyncIterator[dict[str, str]]:
        """Yield SSE events for one client. Heartbeat every 25 seconds."""
        queue: asyncio.Queue[SseEvent | None] = asyncio.Queue()
        self._clients.add(queue)
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                except TimeoutError:
                    yield {"event": "ping", "data": ""}
                    continue
                if evt is None:
                    return
                yield {"event": evt.event, "data": json.dumps(evt.data, default=str)}
        finally:
            self._clients.discard(queue)


hub = _Hub()


async def broadcast(event: str, data: Any) -> None:
    await hub.broadcast(event, data)


async def initialize_realtime() -> None:
    await hub.initialize()


async def shutdown_realtime() -> None:
    await hub.shutdown()
