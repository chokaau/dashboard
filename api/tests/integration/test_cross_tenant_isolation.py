"""Integration tests: cross-tenant isolation — story 003-009, AC1–AC3.

Security tests: verifies that tenant-a cannot see tenant-b's data.
Uses `integration_client` fixture (real DB, JWT auth patched).
Tests mint JWTs for different tenants to simulate cross-tenant access.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


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


def _make_billing_row(
    tenant_slug: str = "acme",
    env: str = "dev",
    activation_status: str = "none",
    plan: str = "trial",
) -> "BillingUsage":
    from app.db.models import BillingUsage

    return BillingUsage(
        id=uuid.uuid4(),
        tenant_slug=tenant_slug,
        env=env,
        plan=plan,
        trial_start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        trial_days=14,
        activation_status=activation_status,
        product="voice",
    )


def _auth(client, tenant_slug: str) -> dict[str, str]:
    token = client.mint_jwt(tenant_slug=tenant_slug, sub=f"user-{tenant_slug}")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# AC1 — list_calls returns only tenant-a's calls
# ---------------------------------------------------------------------------


async def test_list_calls_tenant_isolation(integration_client, db_session):
    """AC1 — calls seeded for tenant-a and tenant-b; authenticated as tenant-a
    → response contains only tenant-a calls, zero tenant-b calls.
    """
    # Seed 3 calls for tenant-a, 2 for tenant-b
    for i in range(3):
        db_session.add(_make_call(call_id=f"tenant-a-call-{i}", tenant_slug="acme"))
    for i in range(2):
        db_session.add(_make_call(call_id=f"tenant-b-call-{i}", tenant_slug="beta"))
    await db_session.flush()

    headers = _auth(integration_client, tenant_slug="acme")
    resp = await integration_client.get("/api/calls", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    calls = body["calls"]
    assert len(calls) == 3
    assert body["pagination"]["total"] == 3

    call_ids = {c["id"] for c in calls}
    assert "tenant-a-call-0" in call_ids
    assert "tenant-a-call-1" in call_ids
    assert "tenant-a-call-2" in call_ids
    # No tenant-b calls
    assert "tenant-b-call-0" not in call_ids
    assert "tenant-b-call-1" not in call_ids


# ---------------------------------------------------------------------------
# AC2 — get_call for tenant-b's call as tenant-a → 404 (not 403)
# ---------------------------------------------------------------------------


async def test_get_call_cross_tenant_returns_404(integration_client, db_session):
    """AC2 — Call owned by tenant-b; GET by tenant-a → HTTP 404 (not 403 or 200).

    Cross-tenant requests must not reveal the existence of the call (no 403).
    """
    tenant_b_call_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    call = _make_call(call_id=tenant_b_call_id, tenant_slug="beta")
    db_session.add(call)
    await db_session.flush()

    headers = _auth(integration_client, tenant_slug="acme")
    resp = await integration_client.get(f"/api/calls/{tenant_b_call_id}", headers=headers)

    # Must be 404 — not 403 (no info leakage about existence)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC3 — billing isolation: tenant-a gets own billing row, not tenant-b's
# ---------------------------------------------------------------------------


async def test_billing_tenant_isolation(integration_client, db_session):
    """AC3 — BillingUsage rows for tenant-a and tenant-b; GET /api/billing as
    tenant-a → response matches tenant-a's row (activation_status), not tenant-b's.
    """
    from botocore.exceptions import ClientError

    # Tenant-a: activation_status=active
    row_a = _make_billing_row(
        tenant_slug="acme",
        activation_status="active",
        plan="trial",
    )
    # Tenant-b: activation_status=pending (must not appear in tenant-a response)
    row_b = _make_billing_row(
        tenant_slug="beta",
        activation_status="pending",
        plan="trial",
    )
    db_session.add(row_a)
    db_session.add(row_b)
    await db_session.flush()

    headers = _auth(integration_client, tenant_slug="acme")

    # S3 not needed — DB row exists, but provide a mock to avoid network calls
    s3 = MagicMock()
    s3.__aenter__ = AsyncMock(return_value=s3)
    s3.__aexit__ = AsyncMock(return_value=False)
    s3.get_object = AsyncMock(
        side_effect=ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": ""}}, "GetObject"
        )
    )
    mock_session_s3 = MagicMock()
    mock_session_s3.client = MagicMock(return_value=s3)

    with patch("app.routes.billing.aioboto3.Session", return_value=mock_session_s3):
        resp = await integration_client.get("/api/billing", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    # Must match tenant-a's row
    assert body["activationStatus"] == "active"
    # Must NOT match tenant-b's activation_status
    assert body["activationStatus"] != "pending"
