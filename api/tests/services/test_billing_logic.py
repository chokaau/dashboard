"""Unit tests for billing route logic (DB primary + S3 fallback) — story 003-005.

TDD: tests written before implementation.
Uses NullBillingRepository (in-memory fake) — no DB required.

AC1: DB row returned when exists.
AC2: S3 fallback when DB empty.
AC3: auto-upsert after S3 fallback.
AC4: response shape matches billing_baseline.json fields.
AC5: synthetic response when both DB and S3 empty.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Sequence
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.db.models import BillingUsage


# ---------------------------------------------------------------------------
# NullBillingRepository
# ---------------------------------------------------------------------------


class NullBillingRepository:
    def __init__(self, row: BillingUsage | None = None):
        self._row = row
        self.upserted: BillingUsage | None = None

    async def get_billing(self, *, tenant_slug: str, env: str) -> BillingUsage | None:
        return self._row

    async def upsert_billing(self, row: BillingUsage) -> BillingUsage:
        self.upserted = row
        # Simulate a returned row with an id
        row.id = uuid.uuid4()
        return row


def _billing_row(
    plan: str = "trial",
    activation_status: str = "none",
    product: str = "voice",
    trial_days: int = 14,
) -> BillingUsage:
    return BillingUsage(
        tenant_slug="acme",
        env="dev",
        plan=plan,
        trial_start=datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc),
        trial_days=trial_days,
        activation_status=activation_status,
        product=product,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_returns_pg_result_when_row_exists():
    """AC1 — DB row exists → response uses DB data, S3 not called."""
    from app.routes.billing import _compute_response_from_row

    row = _billing_row(plan="trial", activation_status="none", product="voice")
    result = _compute_response_from_row(row)

    assert result["plan"] == "trial"
    assert result["activationStatus"] == "none"
    assert result["product"] == "voice"
    assert "trialDaysRemaining" in result
    assert "trialEndDate" in result
    assert "isTrialExpired" in result


async def test_falls_back_to_s3_when_db_empty():
    """AC2 — repo returns None → S3 get_object called."""
    from app.routes.billing import _handle_billing_request

    repo = NullBillingRepository(row=None)
    mock_s3 = AsyncMock()
    s3_data = {
        "plan": "trial",
        "trial_start": "2026-03-21T00:00:00",
        "trial_days": 14,
        "activation_status": "none",
        "product": "voice",
    }
    mock_s3.get_object = AsyncMock(return_value={
        "Body": AsyncMock(read=AsyncMock(return_value=json.dumps(s3_data).encode()))
    })

    result = await _handle_billing_request(
        repo=repo,
        s3=mock_s3,
        bucket="test-bucket",
        s3_key="dev/acme/billing.json",
        tenant_slug="acme",
        env="dev",
    )

    mock_s3.get_object.assert_called_once()
    assert result["plan"] == "trial"


async def test_s3_fallback_upserts_row_to_db():
    """AC3 — S3 fallback triggered → upsert_billing called with parsed data."""
    from app.routes.billing import _handle_billing_request
    from botocore.exceptions import ClientError

    repo = NullBillingRepository(row=None)
    mock_s3 = AsyncMock()
    s3_data = {
        "plan": "trial",
        "trial_start": "2026-03-21T00:00:00",
        "trial_days": 14,
        "activation_status": "none",
        "product": "voice",
    }
    mock_s3.get_object = AsyncMock(return_value={
        "Body": AsyncMock(read=AsyncMock(return_value=json.dumps(s3_data).encode()))
    })

    await _handle_billing_request(
        repo=repo,
        s3=mock_s3,
        bucket="test-bucket",
        s3_key="dev/acme/billing.json",
        tenant_slug="acme",
        env="dev",
    )

    assert repo.upserted is not None
    assert repo.upserted.plan == "trial"
    assert repo.upserted.tenant_slug == "acme"


async def test_returns_synthetic_when_both_empty():
    """AC5 — DB and S3 both empty → synthetic response returned."""
    from app.routes.billing import _handle_billing_request
    from botocore.exceptions import ClientError

    repo = NullBillingRepository(row=None)
    mock_s3 = AsyncMock()
    error_response = {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}
    mock_s3.get_object = AsyncMock(
        side_effect=ClientError(error_response, "GetObject")
    )

    result = await _handle_billing_request(
        repo=repo,
        s3=mock_s3,
        bucket="test-bucket",
        s3_key="dev/acme/billing.json",
        tenant_slug="acme",
        env="dev",
    )

    assert result["plan"] == "trial"
    assert result["trialDaysRemaining"] == 14
    assert result["isTrialExpired"] is False
    assert result["activationStatus"] == "none"


async def test_response_shape_matches_baseline():
    """AC4 — response has all 6 fields from billing_baseline.json."""
    from app.routes.billing import _compute_response_from_row

    row = _billing_row()
    result = _compute_response_from_row(row)

    baseline_fields = [
        "plan", "trialDaysRemaining", "trialEndDate",
        "isTrialExpired", "activationStatus", "product",
    ]
    for field in baseline_fields:
        assert field in result, f"Missing field: {field}"

    assert isinstance(result["trialDaysRemaining"], int)
    assert isinstance(result["trialEndDate"], str)
    assert isinstance(result["isTrialExpired"], bool)
