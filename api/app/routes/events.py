"""SSE endpoint — GET /events — story-4-1 / Epic 7.

Architecture:
- JWT extracted from ?token= query param (SSE-only path, no Authorization header
  support needed — EventSource cannot set headers).
- Subscribes to Redis pub/sub channel events:{env}:{tenant_slug}.
- Forwards call_completed events to the SSE stream.
- Sends ping heartbeat every sse_ping_interval_seconds from AppConfig.
- Server-side timeout: sends reconnect frame after sse_max_connection_seconds.
- Redis unavailable: falls back to ping-only heartbeat (no crash).
- Per-tenant concurrent connection limit via sse_max_connections_per_tenant.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.logging_events import AUTH_REJECTED, SSE_TOKEN_MISSING, TENANT_RATE_LIMITED

log = structlog.get_logger()

router = APIRouter()

# Module-level constants initialised from AppConfig at startup (see main.py).
# Tests patch these directly (e.g. patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 0)).
# Default values match AppConfig field defaults.
SSE_PING_INTERVAL_SECONDS: int = 30
SSE_MAX_CONNECTION_SECONDS: int = 600
SSE_MAX_CONNECTIONS_PER_TENANT: int = 5


def _sse_frame(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


@asynccontextmanager
async def _connection_counter(redis, connection_key: str, max_connections: int, tenant_slug: str):
    """Async context manager that increments/decrements the per-tenant SSE counter.

    Yields True when the connection is allowed, False when the limit is exceeded.
    Guarantees decrement in the finally block regardless of how the caller exits.
    """
    allowed = True
    if redis is not None:
        try:
            count = await redis.incr(connection_key)
            ttl = SSE_MAX_CONNECTION_SECONDS + 60
            await redis.expire(connection_key, ttl)
            if count > max_connections:
                await redis.decr(connection_key)
                log.warning(
                    TENANT_RATE_LIMITED,
                    tenant_slug=tenant_slug,
                    endpoint="/events",
                    reason="concurrent_connection_limit",
                )
                allowed = False
        except Exception as exc:
            log.warning("sse_connection_counter_failed", error=str(exc))

    try:
        yield allowed
    finally:
        if redis is not None and allowed:
            try:
                await redis.decr(connection_key)
            except Exception as exc:
                log.warning("sse_connection_decr_failed", error=str(exc))


async def _subscribe_pubsub(redis, channel: str):
    """Create and subscribe a Redis pubsub object.

    Returns the subscribed pubsub object, or None if subscription fails.
    """
    if redis is None:
        return None
    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        return pubsub
    except Exception as exc:
        log.warning("sse_redis_subscribe_failed", error=str(exc))
        return None


async def _cleanup_pubsub(pubsub, channel: str) -> None:
    """Unsubscribe and close a pubsub object, swallowing cleanup errors."""
    if pubsub is None:
        return
    try:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
    except Exception as exc:
        log.warning("sse_pubsub_cleanup_failed", error=str(exc))


async def _event_generator(
    request: Request,
    tenant_slug: str,
    env_short: str,
    ping_interval: int,
    max_connection_seconds: int,
    max_connections: int,
) -> AsyncGenerator[str, None]:
    """Core SSE generator: subscribe to Redis, yield events, handle timeout."""
    redis = getattr(request.app.state, "redis", None)

    channel = f"events:{env_short}:{tenant_slug}"
    deadline = asyncio.get_event_loop().time() + max_connection_seconds
    connection_key = f"sse_connections:{env_short}:{tenant_slug}"

    async with _connection_counter(redis, connection_key, max_connections, tenant_slug) as allowed:
        if not allowed:
            yield _sse_frame("error", '{"detail":"Too many concurrent SSE connections for this tenant."}')
            return

        pubsub = await _subscribe_pubsub(redis, channel)
        listen_task = None
        try:
            if pubsub is not None:
                listen_task = asyncio.create_task(_drain_pubsub(pubsub, channel))

            ping_counter = 0
            while True:
                now = asyncio.get_event_loop().time()
                remaining = deadline - now
                if remaining <= 0:
                    yield _sse_frame("reconnect", "{}")
                    break

                sleep_secs = min(ping_interval, max(0.0, remaining))

                if listen_task is not None and not listen_task.done():
                    done, _ = await asyncio.wait({listen_task}, timeout=sleep_secs)
                    if done:
                        try:
                            msg_data = listen_task.result()
                            if msg_data is not None:
                                yield _sse_frame("call_completed", msg_data)
                        except Exception as exc:
                            log.warning("sse_message_decode_error", error=str(exc))
                        listen_task = (
                            asyncio.create_task(_drain_pubsub(pubsub, channel))
                            if pubsub is not None
                            else None
                        )
                    else:
                        ping_counter += 1
                        yield _sse_frame("ping", str(ping_counter))
                else:
                    await asyncio.sleep(sleep_secs)
                    ping_counter += 1
                    yield _sse_frame("ping", str(ping_counter))

        finally:
            if listen_task is not None and not listen_task.done():
                listen_task.cancel()
                try:
                    await listen_task
                except (asyncio.CancelledError, Exception):
                    pass
            await _cleanup_pubsub(pubsub, channel)
            log.info("sse_connection_closed", tenant_slug=tenant_slug)


async def _drain_pubsub(pubsub: object, expected_channel: str) -> str | None:
    """Read the next message from the pub/sub stream that matches expected_channel."""
    async for msg in pubsub.listen():  # type: ignore[attr-defined]
        if msg.type == "message" and msg.channel == expected_channel:
            return msg.data  # type: ignore[return-value]
    return None


@router.get("/events")
async def sse_events(request: Request) -> StreamingResponse:
    """Server-Sent Events endpoint.

    Authentication: JWT from ?token= query param (SSE-only path).
    The JWT validation middleware handles auth before this handler runs.
    Claims are available at request.state.jwt_claims.
    """
    claims = getattr(request.state, "jwt_claims", None)
    if claims is None:
        log.warning(AUTH_REJECTED, reason=SSE_TOKEN_MISSING)
        from fastapi.responses import JSONResponse
        return JSONResponse(  # type: ignore[return-value]
            status_code=401,
            content={"detail": "Missing authorization"},
        )

    tenant_slug: str = claims.get("custom:tenant_slug", "")
    config = request.app.state.config
    env_short: str = getattr(config, "env_short", "dev")

    return StreamingResponse(
        _event_generator(
            request,
            tenant_slug,
            env_short,
            ping_interval=SSE_PING_INTERVAL_SECONDS,
            max_connection_seconds=SSE_MAX_CONNECTION_SECONDS,
            max_connections=SSE_MAX_CONNECTIONS_PER_TENANT,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
