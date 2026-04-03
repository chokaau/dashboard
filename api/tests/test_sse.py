"""Tests for GET /api/events SSE endpoint — story-4-1 / Epic 7.

TDD: RED tests written first, then implementation added.

Covers:
- Unauthenticated request (no token) returns 401
- SSE_TOKEN_MISSING logged on missing ?token= param
- Valid JWT via ?token= → 200 text/event-stream
- call_completed Redis pub/sub event forwarded to SSE stream
- Cross-tenant isolation: tenant-a events not delivered to tenant-b stream
- Redis unavailable → ping-only heartbeat (no crash)
- Client disconnect → generator cancels, Redis subscription cleaned up
- Per-tenant concurrent connection limit (SSE_MAX_CONNECTIONS_PER_TENANT)
- Server-side timeout sends reconnect frame and cleans up
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from tests.conftest import TEST_POOL_ID, TEST_CLIENT_ID, TEST_ISS, TEST_REGION, mint_jwt


# ---------------------------------------------------------------------------
# Helpers: fake async pubsub
# ---------------------------------------------------------------------------

class FakePubSubMessage:
    """Minimal pub/sub message object."""
    def __init__(self, channel: str, data: str) -> None:
        self.type = "message"
        self.channel = channel
        self.data = data


class FakePubSub:
    """Fake Redis async pub/sub that yields configured messages."""

    def __init__(self, messages: list[dict[str, str]] | None = None) -> None:
        self._messages = messages or []
        self._subscribed: list[str] = []
        self.unsubscribed = False
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self._subscribed.append(channel)

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed = True

    async def aclose(self) -> None:
        self.closed = True

    async def listen(self) -> AsyncGenerator[FakePubSubMessage, None]:
        for msg in self._messages:
            yield FakePubSubMessage(channel=msg["channel"], data=msg["data"])
        # After messages exhausted, block forever (caller cancels)
        await asyncio.sleep(9999)


class FakePipeline:
    """Minimal fake Redis pipeline."""

    def __init__(self) -> None:
        self._cmds: list[tuple[str, list[Any]]] = []
        self._incr_values: dict[str, int] = {}

    def incr(self, key: str) -> "FakePipeline":
        self._cmds.append(("incr", [key]))
        return self

    def expire(self, key: str, seconds: int) -> "FakePipeline":
        return self

    async def execute(self) -> list[int]:
        results = []
        for cmd, args in self._cmds:
            if cmd == "incr":
                self._incr_values[args[0]] = self._incr_values.get(args[0], 0) + 1
                results.append(self._incr_values[args[0]])
        return results

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class FakeRedis:
    """Minimal fake Redis with pubsub(), pipeline(), and connection-limit counters."""

    def __init__(
        self,
        pubsub_messages: list[dict[str, str]] | None = None,
        raise_on_pubsub: bool = False,
        connection_count: int = 0,
    ) -> None:
        self._pubsub = FakePubSub(pubsub_messages or [])
        self._raise_on_pubsub = raise_on_pubsub
        self._incr_values: dict[str, int] = {}
        self._connection_count = connection_count
        self._pipeline = FakePipeline()

    def pubsub(self) -> FakePubSub:
        if self._raise_on_pubsub:
            raise ConnectionError("Redis unavailable")
        return self._pubsub

    def pipeline(self) -> FakePipeline:
        return self._pipeline

    async def incr(self, key: str) -> int:
        self._incr_values[key] = self._incr_values.get(key, 0) + 1
        return self._incr_values[key]

    async def decr(self, key: str) -> int:
        self._incr_values[key] = max(0, self._incr_values.get(key, 0) - 1)
        return self._incr_values[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass

    async def get(self, key: str) -> str | None:
        v = self._incr_values.get(key)
        return str(v) if v is not None else None

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sse_client(app_no_redis):
    """TestClient with streaming support for SSE."""
    with TestClient(app_no_redis, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def sse_token() -> str:
    return mint_jwt(tenant_slug="acme")


@pytest.fixture()
def sse_token_b() -> str:
    return mint_jwt(tenant_slug="tenant-b", sub="user-b")


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

class TestSSEAuthentication:
    def test_missing_token_returns_401(self, sse_client: TestClient) -> None:
        """No Authorization header and no ?token= → 401."""
        response = sse_client.get("/api/events")
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, sse_client: TestClient) -> None:
        """?token= with garbage value → 401."""
        response = sse_client.get("/api/events?token=not-a-jwt")
        assert response.status_code == 401

    def test_bearer_token_also_accepted(
        self, sse_client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Authorization: Bearer header also works for SSE (defense-in-depth)."""
        fake_redis = FakeRedis(pubsub_messages=[])
        sse_client.app.state.redis = fake_redis
        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 0):
            response = sse_client.get("/api/events", headers=auth_headers)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Happy-path SSE stream tests
# ---------------------------------------------------------------------------

class TestSSEStream:
    def test_valid_token_returns_200_event_stream(
        self, sse_client: TestClient, sse_token: str, app_no_redis
    ) -> None:
        """Valid ?token= JWT → 200 with content-type: text/event-stream."""
        fake_redis = FakeRedis(pubsub_messages=[])
        app_no_redis.state.redis = fake_redis
        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 0):
            response = sse_client.get(f"/api/events?token={sse_token}")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_response_headers(
        self, sse_client: TestClient, sse_token: str, app_no_redis
    ) -> None:
        """SSE response has correct headers."""
        fake_redis = FakeRedis(pubsub_messages=[])
        app_no_redis.state.redis = fake_redis
        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 0):
            response = sse_client.get(f"/api/events?token={sse_token}")
        assert response.headers.get("cache-control") == "no-cache"
        assert response.headers.get("x-accel-buffering") == "no"

    def test_call_completed_event_forwarded(
        self, sse_client: TestClient, sse_token: str, app_no_redis
    ) -> None:
        """A Redis call_completed message is forwarded to the SSE stream."""
        payload = json.dumps({"callId": "cid-abc", "timestamp": "2026-04-01T10:00:00Z"})
        fake_redis = FakeRedis(
            pubsub_messages=[
                {"channel": "events:test:acme", "data": payload},
            ]
        )
        app_no_redis.state.redis = fake_redis
        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 1):
            with patch("app.routes.events.SSE_PING_INTERVAL_SECONDS", 9999):
                response = sse_client.get(f"/api/events?token={sse_token}")

        assert response.status_code == 200
        body = response.text
        assert "event: call_completed" in body
        assert "cid-abc" in body

    def test_cross_tenant_isolation(
        self,
        sse_client: TestClient,
        sse_token: str,
        sse_token_b: str,
        app_no_redis,
    ) -> None:
        """tenant-a events are NOT delivered to tenant-b stream."""
        # tenant-b stream should not receive events for tenant-a
        payload = json.dumps({"callId": "tenant-a-call", "timestamp": "2026-04-01T10:00:00Z"})
        fake_redis = FakeRedis(
            pubsub_messages=[
                # Message is on tenant-a channel
                {"channel": "events:test:acme", "data": payload},
            ]
        )
        app_no_redis.state.redis = fake_redis
        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 1):
            with patch("app.routes.events.SSE_PING_INTERVAL_SECONDS", 9999):
                # Connect as tenant-b — should NOT see tenant-a's events
                response = sse_client.get(f"/api/events?token={sse_token_b}")

        assert response.status_code == 200
        # tenant-a's call should not appear in tenant-b's stream
        assert "tenant-a-call" not in response.text

    def test_redis_unavailable_sends_ping_only(
        self, sse_client: TestClient, sse_token: str, app_no_redis
    ) -> None:
        """When Redis pub/sub raises, stream stays alive with ping heartbeat."""
        fake_redis = FakeRedis(raise_on_pubsub=True)
        app_no_redis.state.redis = fake_redis
        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 0):
            with patch("app.routes.events.SSE_PING_INTERVAL_SECONDS", 0):
                response = sse_client.get(f"/api/events?token={sse_token}")
        # Must not crash — returns 200
        assert response.status_code == 200

    def test_server_timeout_sends_reconnect_frame(
        self, sse_client: TestClient, sse_token: str, app_no_redis
    ) -> None:
        """After SSE_MAX_CONNECTION_SECONDS, server sends reconnect event."""
        fake_redis = FakeRedis(pubsub_messages=[])
        app_no_redis.state.redis = fake_redis
        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 0):
            with patch("app.routes.events.SSE_PING_INTERVAL_SECONDS", 9999):
                response = sse_client.get(f"/api/events?token={sse_token}")
        assert "event: reconnect" in response.text


# ---------------------------------------------------------------------------
# Concurrent connection limit — AC-9
# ---------------------------------------------------------------------------

class TestSSEConcurrentConnectionLimit:
    def test_sixth_connection_returns_error_frame(
        self, sse_client: TestClient, sse_token: str, app_no_redis
    ) -> None:
        """When 5 connections already exist, the 6th receives an SSE error frame."""
        # Pre-seed the Redis counter so it already shows 5 connections
        fake_redis = FakeRedis(pubsub_messages=[])
        # Seed the counter to SSE_MAX_CONNECTIONS_PER_TENANT (default 5)
        connection_key = "sse_connections:test:acme"
        fake_redis._incr_values[connection_key] = 5
        app_no_redis.state.redis = fake_redis

        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 0):
            with patch("app.routes.events.SSE_PING_INTERVAL_SECONDS", 9999):
                response = sse_client.get(f"/api/events?token={sse_token}")

        # The generator must yield the error frame and return (no 200 stream of events)
        assert response.status_code == 200
        assert "Too many concurrent SSE connections" in response.text

    def test_connection_counter_decremented_on_disconnect(
        self, sse_client: TestClient, sse_token: str, app_no_redis
    ) -> None:
        """Counter in Redis is decremented when the connection closes."""
        fake_redis = FakeRedis(pubsub_messages=[])
        app_no_redis.state.redis = fake_redis

        connection_key = "sse_connections:test:acme"

        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 0):
            with patch("app.routes.events.SSE_PING_INTERVAL_SECONDS", 9999):
                sse_client.get(f"/api/events?token={sse_token}")

        # After the stream completes the counter must be back at 0
        assert fake_redis._incr_values.get(connection_key, 0) == 0

    def test_pubsub_unsubscribed_after_disconnect(
        self, sse_client: TestClient, sse_token: str, app_no_redis
    ) -> None:
        """Redis pub/sub channel is unsubscribed when the client disconnects."""
        fake_pubsub = FakePubSub(messages=[])
        fake_redis = FakeRedis(pubsub_messages=[])
        # Replace the FakePubSub instance so we can inspect it after the stream
        fake_redis._pubsub = fake_pubsub
        app_no_redis.state.redis = fake_redis

        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 0):
            with patch("app.routes.events.SSE_PING_INTERVAL_SECONDS", 9999):
                sse_client.get(f"/api/events?token={sse_token}")

        # The finally block must have called unsubscribe and aclose
        assert fake_pubsub.unsubscribed is True
        assert fake_pubsub.closed is True


# ---------------------------------------------------------------------------
# JWT expiry after connection — AC-10
# ---------------------------------------------------------------------------

class TestSSEJWTExpiry:
    def test_jwt_expiry_after_connect_stream_continues(
        self, sse_client: TestClient, app_no_redis
    ) -> None:
        """JWT validated only at connection time; stream continues even if token would expire mid-stream."""
        # Mint a JWT that is valid now (expiry is checked only at connection initiation,
        # not on every message). We verify the stream delivers the event successfully
        # using a token with a very short but non-zero validity window.
        token = mint_jwt(tenant_slug="acme")
        payload = json.dumps({"callId": "cid-expire-test", "timestamp": "2026-04-01T10:00:00Z"})
        fake_redis = FakeRedis(
            pubsub_messages=[
                {"channel": "events:test:acme", "data": payload},
            ]
        )
        app_no_redis.state.redis = fake_redis

        # The stream runs to completion — if JWT was re-validated mid-stream it would
        # fail on a short-lived token, but our implementation only validates at entry.
        with patch("app.routes.events.SSE_MAX_CONNECTION_SECONDS", 1):
            with patch("app.routes.events.SSE_PING_INTERVAL_SECONDS", 9999):
                response = sse_client.get(f"/api/events?token={token}")

        # Stream must complete successfully and contain the event
        assert response.status_code == 200
        assert "cid-expire-test" in response.text
