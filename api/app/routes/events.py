"""SSE endpoint — GET /events — story-4-1 / Epic 7.

Architecture:
- JWT extracted from ?token= query param (SSE-only path, no Authorization header
  support needed — EventSource cannot set headers).
- Subscribes to Redis pub/sub channel events:{env}:{tenant_slug}.
- Forwards call_completed events to the SSE stream.
- Sends ping heartbeat every SSE_PING_INTERVAL_SECONDS.
- Server-side timeout: sends reconnect frame after SSE_MAX_CONNECTION_SECONDS.
- Redis unavailable: falls back to ping-only heartbeat (no crash).
- Per-tenant concurrent connection limit via SSE_MAX_CONNECTIONS_PER_TENANT.
"""

import asyncio
import json
import os
from collections.abc import AsyncGenerator

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.logging_events import AUTH_REJECTED, SSE_TOKEN_MISSING, TENANT_RATE_LIMITED

log = structlog.get_logger()

router = APIRouter()

# Configurable via environment variables
SSE_PING_INTERVAL_SECONDS: int = int(os.environ.get("SSE_PING_INTERVAL_SECONDS", "30"))
SSE_MAX_CONNECTION_SECONDS: int = int(os.environ.get("SSE_MAX_CONNECTION_SECONDS", "600"))
SSE_MAX_CONNECTIONS_PER_TENANT: int = int(
    os.environ.get("SSE_MAX_CONNECTIONS_PER_TENANT", "5")
)


def _sse_frame(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


async def _event_generator(
    request: Request,
    tenant_slug: str,
    env_short: str,
) -> AsyncGenerator[str, None]:
    """Core SSE generator: subscribe to Redis, yield events, handle timeout."""
    config = request.app.state.config
    redis = getattr(request.app.state, "redis", None)

    channel = f"events:{env_short}:{tenant_slug}"
    deadline = asyncio.get_event_loop().time() + SSE_MAX_CONNECTION_SECONDS
    connection_key = f"sse_connections:{env_short}:{tenant_slug}"

    # Increment concurrent connection counter
    if redis is not None:
        try:
            count = await redis.incr(connection_key)
            ttl = SSE_MAX_CONNECTION_SECONDS + 60
            await redis.expire(connection_key, ttl)
            if count > SSE_MAX_CONNECTIONS_PER_TENANT:
                await redis.decr(connection_key)
                log.warning(
                    TENANT_RATE_LIMITED,
                    tenant_slug=tenant_slug,
                    endpoint="/events",
                    reason="concurrent_connection_limit",
                )
                yield _sse_frame("error", '{"detail":"Too many concurrent SSE connections for this tenant."}')
                return
        except Exception as exc:
            log.warning("sse_connection_counter_failed", error=str(exc))

    pubsub = None
    try:
        # Attempt to subscribe to Redis pub/sub
        if redis is not None:
            try:
                pubsub = redis.pubsub()
                await pubsub.subscribe(channel)
            except Exception as exc:
                log.warning("sse_redis_subscribe_failed", error=str(exc))
                pubsub = None

        # Main event loop
        listen_task = None
        if pubsub is not None:
            listen_task = asyncio.create_task(_drain_pubsub(pubsub, channel))

        ping_counter = 0
        while True:
            now = asyncio.get_event_loop().time()
            remaining = deadline - now
            if remaining <= 0:
                # Server-side timeout — send reconnect frame and close cleanly
                yield _sse_frame("reconnect", "{}")
                break

            # Wait for next ping interval or a message from Redis
            sleep_secs = min(SSE_PING_INTERVAL_SECONDS, max(0.0, remaining))

            if listen_task is not None and not listen_task.done():
                done, _ = await asyncio.wait(
                    {listen_task},
                    timeout=sleep_secs,
                )
                if done:
                    # listen_task returned a message
                    try:
                        msg_data = listen_task.result()
                        if msg_data is not None:
                            yield _sse_frame("call_completed", msg_data)
                    except Exception as exc:
                        log.warning("sse_message_decode_error", error=str(exc))
                    # Re-arm listener for next message
                    if pubsub is not None:
                        listen_task = asyncio.create_task(
                            _drain_pubsub(pubsub, channel)
                        )
                    else:
                        listen_task = None
                else:
                    # Timeout: send ping
                    ping_counter += 1
                    yield _sse_frame("ping", str(ping_counter))
            else:
                await asyncio.sleep(sleep_secs)
                ping_counter += 1
                yield _sse_frame("ping", str(ping_counter))

    finally:
        # Clean up listener task
        if listen_task is not None and not listen_task.done():
            listen_task.cancel()
            try:
                await listen_task
            except (asyncio.CancelledError, Exception):
                pass

        # Unsubscribe and close pubsub
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception as exc:
                log.warning("sse_pubsub_cleanup_failed", error=str(exc))

        # Decrement connection counter
        if redis is not None:
            try:
                await redis.decr(connection_key)
            except Exception as exc:
                log.warning("sse_connection_decr_failed", error=str(exc))

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
        # Should not reach here — middleware handles 401 — but be defensive
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
        _event_generator(request, tenant_slug, env_short),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
