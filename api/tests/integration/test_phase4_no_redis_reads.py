"""Phase 4 regression tests — story 004-001 (TDD red phase).

These tests verify that after Redis read removal, the call list and get_call
routes NEVER read from Redis. They are written before the code deletion so
the red-green cycle is maintained.

Test state before 004-002 (Redis read removal):
  - test_call_list_does_not_read_redis: FAIL (PG empty → fallback fires → 500)
  - test_get_call_does_not_read_redis: FAIL (PG no row → Redis read fires → raises)

Test state after 004-002 (Redis read removal):
  - test_call_list_does_not_read_redis: PASS (PG empty → empty 200 response)
  - test_get_call_does_not_read_redis: PASS (PG no row → 404, no Redis call)

Tests 3 and 4 must PASS now and continue to pass after Phase 4 cleanup
(rate limiting and SSE still use Redis write paths).

Gating conditions (require live deployed environment — operator must verify):
  AC1: Zero call_list_pg_fallback_to_redis events in last 48h (CloudWatch)
  AC2: PostgreSQL row count >= Redis row count for all tenants (psql query)
  AC5: Phase 3 ECS task definition revision recorded (rollback reference)
  These cannot be auto-verified here as Phase 3 infrastructure is BLOCKED on
  story 001-005 (operator must run tofu apply for RDS). When 001-005 is
  completed, operator must run the AWS CLI gating checks before Phase 4 proceed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(client, tenant_slug: str = "acme") -> dict[str, str]:
    token = client.mint_jwt(tenant_slug=tenant_slug, sub=f"user-{tenant_slug}")
    return {"Authorization": f"Bearer {token}"}


def _make_call(
    call_id: str | None = None,
    tenant_slug: str = "acme",
    env: str = "dev",
    status: str = "missed",
) -> "Call":
    from app.db.models import Call

    return Call(
        id=call_id or str(uuid.uuid4()),
        tenant_slug=tenant_slug,
        env=env,
        start_time=datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc),
        duration_s=60,
        status=status,
        intent="info",
        caller_name=None,
        phone_hash=None,
        needs_callback=False,
        summary=None,
        has_recording=False,
    )


def _make_raising_redis() -> MagicMock:
    """Return a mock Redis client whose read methods raise AssertionError.

    Write methods (pipeline, zadd, zremrangebyscore, expire, execute)
    are left functional (as AsyncMocks returning safe defaults) so rate
    limiting can pass through without error.
    """
    redis = MagicMock()

    # Read operations that must NOT be called in Phase 4
    _redis_read_error = AssertionError(
        "Redis read called — must not happen after Phase 4 Redis read removal"
    )
    redis.zcard = AsyncMock(side_effect=_redis_read_error)
    redis.zrange = AsyncMock(side_effect=_redis_read_error)
    redis.zrevrange = AsyncMock(side_effect=_redis_read_error)
    redis.zrevrangebyscore = AsyncMock(side_effect=_redis_read_error)
    redis.hgetall = AsyncMock(side_effect=_redis_read_error)
    redis.get = AsyncMock(side_effect=_redis_read_error)

    # Write/pipeline operations used by rate limiting — return safe values
    pipe = AsyncMock()
    pipe.zadd = AsyncMock(return_value=None)
    pipe.zremrangebyscore = AsyncMock(return_value=None)
    pipe.zcard = AsyncMock(return_value=None)
    pipe.expire = AsyncMock(return_value=None)
    # pipeline.execute returns [None, None, 1, None] — count=1, well under limit
    pipe.execute = AsyncMock(return_value=[None, None, 1, None])
    redis.pipeline = MagicMock(return_value=pipe)

    # SSE uses redis.incr, redis.expire, redis.decr, redis.pubsub
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.decr = AsyncMock(return_value=0)

    pubsub = AsyncMock()
    pubsub.subscribe = AsyncMock(return_value=None)
    pubsub.get_message = AsyncMock(return_value=None)
    pubsub.unsubscribe = AsyncMock(return_value=None)
    pubsub.aclose = AsyncMock(return_value=None)
    redis.pubsub = MagicMock(return_value=pubsub)

    return redis


# ---------------------------------------------------------------------------
# Test 1 — call list does NOT read Redis (RED before 004-002, GREEN after)
# ---------------------------------------------------------------------------


async def test_call_list_does_not_read_redis(integration_client, db_session):
    """Phase 4 regression: GET /api/calls must not read from Redis.

    Pre-004-002 state (RED): PG is empty → service falls through to Redis
    fallback branch → Redis.zcard is called → AssertionError → 500.

    Post-004-002 state (GREEN): Redis fallback branch removed → PG empty
    returns empty list → HTTP 200.
    """
    # Do NOT seed any Call rows — PG returns empty, triggering fallback if present
    redis = _make_raising_redis()
    integration_client.app.state.redis = redis  # type: ignore[attr-defined]

    try:
        headers = _auth(integration_client)
        resp = await integration_client.get("/api/calls", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["calls"] == []
        # Confirm no Redis read methods were called
        redis.zcard.assert_not_called()
        redis.hgetall.assert_not_called()
        redis.zrevrangebyscore.assert_not_called()
    finally:
        # Restore no-redis state for other tests
        integration_client.app.state.redis = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test 2 — get_call does NOT read Redis (RED before 004-002, GREEN after)
# ---------------------------------------------------------------------------


async def test_get_call_does_not_read_redis(integration_client, db_session):
    """Phase 4 regression: GET /api/calls/{id} must not read from Redis.

    Pre-004-002 state (RED): PG has no row → route falls through to Redis
    hgetall → AssertionError → 500 (not 404).

    Post-004-002 state (GREEN): Route only uses PG → no row → 404, no Redis.
    """
    nonexistent = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    redis = _make_raising_redis()
    integration_client.app.state.redis = redis  # type: ignore[attr-defined]

    try:
        headers = _auth(integration_client)
        resp = await integration_client.get(f"/api/calls/{nonexistent}", headers=headers)
        assert resp.status_code == 404
        redis.hgetall.assert_not_called()
    finally:
        integration_client.app.state.redis = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test 3 — rate limiting still uses Redis (must PASS now and after Phase 4)
# ---------------------------------------------------------------------------


async def test_rate_limit_still_uses_redis(integration_client, db_session):
    """Rate limiting must still work via Redis pipeline after Phase 4 cleanup.

    Injects a Redis mock with a pipeline whose execute returns count > limit
    to trigger a 429 response. This confirms the Redis WRITE path for rate
    limiting is intact and unchanged by Phase 4.
    """
    # Build a Redis mock where the pipeline returns a count over the read limit
    redis = MagicMock()
    pipe = AsyncMock()
    pipe.zadd = AsyncMock(return_value=None)
    pipe.zremrangebyscore = AsyncMock(return_value=None)
    pipe.zcard = AsyncMock(return_value=None)
    pipe.expire = AsyncMock(return_value=None)
    # Return count = 9999, well over the default 120 req/min limit
    pipe.execute = AsyncMock(return_value=[None, None, 9999, None])
    redis.pipeline = MagicMock(return_value=pipe)
    integration_client.app.state.redis = redis  # type: ignore[attr-defined]

    try:
        headers = _auth(integration_client)
        resp = await integration_client.get("/api/calls", headers=headers)
        assert resp.status_code == 429, (
            f"Expected 429 rate-limited response, got {resp.status_code}"
        )
        assert "Rate limit exceeded" in resp.json()["detail"]
        # Confirm pipeline was used (Redis write path active)
        redis.pipeline.assert_called()
        pipe.execute.assert_called()
    finally:
        integration_client.app.state.redis = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test 4 — SSE counter still uses Redis INCR (must PASS now and after Phase 4)
# ---------------------------------------------------------------------------


async def test_sse_counter_still_uses_redis(integration_client, db_session):
    """SSE connection counter must still use Redis INCR after Phase 4 cleanup.

    Calls _connection_counter directly (not via HTTP) to confirm the Redis
    WRITE path (INCR/EXPIRE/DECR) is intact and unchanged by Phase 4.
    This is a unit-level assertion on the SSE infrastructure component,
    not an end-to-end HTTP test — the HTTP streaming test would block
    indefinitely. The component under test (_connection_counter) is stable
    and exercised by the existing test_sse.py suite.
    """
    from app.routes.events import _connection_counter

    redis = MagicMock()
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.decr = AsyncMock(return_value=0)

    # Exercise _connection_counter — this is the SSE Redis WRITE path
    async with _connection_counter(
        redis,
        connection_key="sse_connections:dev:acme",
        max_connections=5,
        tenant_slug="acme",
    ) as allowed:
        assert allowed is True

    # INCR was called on entry (count the connection)
    redis.incr.assert_called_once_with("sse_connections:dev:acme")
    # EXPIRE was called to set TTL
    redis.expire.assert_called_once()
    # DECR was called on exit (connection closed)
    redis.decr.assert_called_once_with("sse_connections:dev:acme")
