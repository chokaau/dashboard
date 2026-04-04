"""Integration tests: call list and call detail endpoints against real PostgreSQL.

Story 003-008 — AC1–AC5.

Tests use the `integration_client` fixture (real DB, JWT auth patched).
Seed data inserted via `db_session` within each test; tables truncated after
each test by the `db_session` fixture in tests/db/conftest.py.

Authentication: JWT minted via client.mint_jwt() (tenant_slug="acme", env="dev").
env_short from test AppConfig is "dev" — matches DB check constraint.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _make_call(
    call_id: str | None = None,
    tenant_slug: str = "acme",
    env: str = "dev",
    status: str = "missed",
    start_time: datetime | None = None,
    caller_name: str | None = None,
) -> "Call":
    from app.db.models import Call

    return Call(
        id=call_id or str(uuid.uuid4()),
        tenant_slug=tenant_slug,
        env=env,
        start_time=start_time or datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc),
        duration_s=120,
        status=status,
        intent="info",
        caller_name=caller_name,
        phone_hash=None,
        needs_callback=False,
        summary=None,
        has_recording=False,
    )


def _auth(client, tenant_slug: str = "acme") -> dict[str, str]:
    token = client.mint_jwt(tenant_slug=tenant_slug, sub=f"user-{tenant_slug}")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# AC1 — empty DB returns empty calls list
# ---------------------------------------------------------------------------


async def test_list_calls_empty_db(integration_client, db_session):
    """AC1 — empty calls table → HTTP 200, calls=[], total=0."""
    headers = _auth(integration_client)
    resp = await integration_client.get("/api/calls", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["calls"] == []
    assert body["pagination"]["total"] == 0
    assert body["pagination"]["page"] == 1


# ---------------------------------------------------------------------------
# AC2 — pagination: 25 rows, page 2, pageSize 10 → 10 items, total 25
# ---------------------------------------------------------------------------


async def test_list_calls_pagination(integration_client, db_session):
    """AC2 — seed 25 calls, GET page=2&pageSize=10 → 10 items, total=25."""
    for i in range(25):
        call = _make_call(
            call_id=f"call-pg-{i:03d}",
            start_time=datetime(2026, 3, 1, 9, i % 60, 0, tzinfo=timezone.utc),
        )
        db_session.add(call)
    await db_session.flush()

    headers = _auth(integration_client)
    resp = await integration_client.get(
        "/api/calls", params={"page": 2, "page_size": 10}, headers=headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["calls"]) == 10
    assert body["pagination"]["total"] == 25
    assert body["pagination"]["page"] == 2
    assert body["pagination"]["pageSize"] == 10


# ---------------------------------------------------------------------------
# AC3 — status filter: 3 missed + 2 completed → filter returns only missed
# ---------------------------------------------------------------------------


async def test_list_calls_status_filter(integration_client, db_session):
    """AC3 — seed mixed status rows, filter status=missed → 3 calls, all missed."""
    for i in range(3):
        db_session.add(_make_call(call_id=f"missed-{i}", status="missed"))
    for i in range(2):
        db_session.add(_make_call(call_id=f"completed-{i}", status="completed"))
    await db_session.flush()

    headers = _auth(integration_client)
    resp = await integration_client.get(
        "/api/calls", params={"status": "missed"}, headers=headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["calls"]) == 3
    for call in body["calls"]:
        assert call["status"] == "missed"


# ---------------------------------------------------------------------------
# AC4 — get_call nonexistent ID → 404
# ---------------------------------------------------------------------------


async def test_get_call_not_found(integration_client, db_session):
    """AC4 — GET /api/calls/<nonexistent> with no Redis fallback → 404."""
    headers = _auth(integration_client)
    # Use a valid call_id format (uuid-like) but one that doesn't exist in DB
    nonexistent = "00000000-0000-0000-0000-000000000404"
    resp = await integration_client.get(f"/api/calls/{nonexistent}", headers=headers)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC5 — get_call found: seed 1 row, fetch by ID → 200, correct fields, no callerNumber
# ---------------------------------------------------------------------------


async def test_get_call_found(integration_client, db_session):
    """AC5 — seed 1 Call, GET /api/calls/{id} → 200, correct id, no callerNumber.

    The route fetches S3 archive after finding the PG row. S3 is mocked to
    return a NoSuchKey error so the route raises 404 (archive not found) —
    this tests the PG lookup path itself. To test the full happy path we mock
    S3 to return a valid archive body.
    """
    call_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    call = _make_call(
        call_id=call_id,
        caller_name="Alice Smith",
        status="completed",
    )
    db_session.add(call)
    await db_session.flush()

    headers = _auth(integration_client)

    # Mock S3: archive exists, recording does not
    import json

    archive_body = json.dumps({
        "transcript": [],
        "agent_actions": [],
        "summary": "Test summary",
    }).encode()

    from unittest.mock import MagicMock
    from botocore.exceptions import ClientError

    mock_s3 = MagicMock()
    mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
    mock_s3.__aexit__ = AsyncMock(return_value=False)

    body_mock = AsyncMock()
    body_mock.read = AsyncMock(return_value=archive_body)
    mock_s3.get_object = AsyncMock(return_value={"Body": body_mock})
    mock_s3.head_object = AsyncMock(
        side_effect=ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "HeadObject"
        )
    )

    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=mock_s3)

    with patch("app.routes.calls.aioboto3.Session", return_value=mock_session):
        resp = await integration_client.get(f"/api/calls/{call_id}", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == call_id
    assert body["callerName"] == "Alice Smith"
    assert body["status"] == "completed"
    # PII invariant: callerNumber must not appear
    assert "callerNumber" not in body
    # caller_number must not appear either
    assert "caller_number" not in body
