"""Integration tests: billing endpoint against real PostgreSQL.

Story 003-008 — AC1 (billing tests), covering:
  - Empty billing_usage table + no S3 data → synthetic response
  - BillingUsage row exists → response matches row fields
  - S3 fallback when DB empty → auto-upserts row to DB
  - Correct trialDaysRemaining calculation from seeded row

Tests use the `integration_client` fixture (real DB, JWT auth patched).
Seed data inserted via `db_session`; tables truncated after each test.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _auth(client, tenant_slug: str = "acme") -> dict[str, str]:
    token = client.mint_jwt(tenant_slug=tenant_slug, sub=f"user-{tenant_slug}")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _make_billing_row(
    tenant_slug: str = "acme",
    env: str = "dev",
    plan: str = "trial",
    trial_start: datetime | None = None,
    trial_days: int = 14,
    activation_status: str = "none",
    product: str = "",
) -> "BillingUsage":
    from app.db.models import BillingUsage

    return BillingUsage(
        id=uuid.uuid4(),
        tenant_slug=tenant_slug,
        env=env,
        plan=plan,
        trial_start=trial_start or datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc),
        trial_days=trial_days,
        activation_status=activation_status,
        product=product,
    )


def _mock_s3_no_billing():
    """S3 mock that raises NoSuchKey for billing.json.

    session.client() is a regular sync call returning an async context manager.
    Use MagicMock (not AsyncMock) for the session/client to avoid coroutine errors.
    """
    from botocore.exceptions import ClientError

    s3 = MagicMock()
    s3.__aenter__ = AsyncMock(return_value=s3)
    s3.__aexit__ = AsyncMock(return_value=False)
    s3.get_object = AsyncMock(
        side_effect=ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "GetObject"
        )
    )
    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=s3)
    return mock_session


def _mock_s3_with_billing(data: dict) -> MagicMock:
    """S3 mock that returns a billing.json payload."""
    s3 = MagicMock()
    s3.__aenter__ = AsyncMock(return_value=s3)
    s3.__aexit__ = AsyncMock(return_value=False)

    body_mock = AsyncMock()
    body_mock.read = AsyncMock(return_value=json.dumps(data).encode())
    s3.get_object = AsyncMock(return_value={"Body": body_mock})

    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=s3)
    return mock_session


# ---------------------------------------------------------------------------
# Test 1 — empty DB + no S3 → synthetic response
# ---------------------------------------------------------------------------


async def test_billing_empty_db_returns_synthetic(integration_client, db_session):
    """Empty billing_usage + no S3 data → HTTP 200, synthetic 14-day trial shape."""
    headers = _auth(integration_client)

    with patch("app.routes.billing.aioboto3.Session", return_value=_mock_s3_no_billing()):
        resp = await integration_client.get("/api/billing", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "trial"
    assert body["trialDaysRemaining"] == 14
    assert body["isTrialExpired"] is False
    assert body["activationStatus"] == "none"
    assert body["product"] == ""
    assert "trialEndDate" in body


# ---------------------------------------------------------------------------
# Test 2 — BillingUsage row exists → response matches row fields
# ---------------------------------------------------------------------------


async def test_billing_returns_pg_row_when_exists(integration_client, db_session):
    """Seed BillingUsage row → response matches stored fields."""
    row = _make_billing_row(
        trial_start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        trial_days=30,
        activation_status="active",
        product="voice",
    )
    db_session.add(row)
    await db_session.flush()

    headers = _auth(integration_client)

    # S3 mock not reached because DB row exists — but provide one anyway
    with patch("app.routes.billing.aioboto3.Session", return_value=_mock_s3_no_billing()):
        resp = await integration_client.get("/api/billing", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "trial"
    assert body["activationStatus"] == "active"
    assert body["product"] == "voice"
    assert isinstance(body["trialDaysRemaining"], int)
    assert isinstance(body["isTrialExpired"], bool)
    assert isinstance(body["trialEndDate"], str)


# ---------------------------------------------------------------------------
# Test 3 — S3 fallback when DB empty → auto-upserts row to DB
# ---------------------------------------------------------------------------


async def test_billing_s3_fallback_upserts_to_db(integration_client, db_session):
    """Empty DB + S3 has billing.json → HTTP 200, row created in billing_usage."""
    from sqlalchemy import select
    from app.db.models import BillingUsage

    s3_data = {
        "plan": "trial",
        "trial_start": "2026-03-01T00:00:00+00:00",
        "trial_days": 14,
        "activation_status": "pending",
        "product": "voice",
    }
    headers = _auth(integration_client)

    with patch(
        "app.routes.billing.aioboto3.Session",
        return_value=_mock_s3_with_billing(s3_data),
    ):
        resp = await integration_client.get("/api/billing", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "trial"
    assert body["activationStatus"] == "pending"

    # Verify the row was upserted into billing_usage
    result = await db_session.execute(
        select(BillingUsage).where(
            BillingUsage.tenant_slug == "acme",
            BillingUsage.env == "dev",
        )
    )
    row = result.scalar_one_or_none()
    assert row is not None, "billing_usage row was not created by S3 fallback auto-upsert"
    assert row.plan == "trial"
    assert row.activation_status == "pending"


# ---------------------------------------------------------------------------
# Test 4 — correct trialDaysRemaining calculation
# ---------------------------------------------------------------------------


async def test_billing_correct_trial_days_calculation(integration_client, db_session):
    """Seed row with trial_start 5 days ago, trial_days=14 → trialDaysRemaining=9."""
    trial_start = datetime.now(timezone.utc) - timedelta(days=5)
    row = _make_billing_row(
        trial_start=trial_start,
        trial_days=14,
    )
    db_session.add(row)
    await db_session.flush()

    headers = _auth(integration_client)

    with patch("app.routes.billing.aioboto3.Session", return_value=_mock_s3_no_billing()):
        resp = await integration_client.get("/api/billing", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["trialDaysRemaining"] == 9
    assert body["isTrialExpired"] is False
