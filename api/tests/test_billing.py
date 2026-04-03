"""Tests for story-4-5: GET /billing Endpoint.

TDD: RED tests written first. Tests cover:
  - Trial started 10 days ago → trialDaysRemaining = 4
  - Expired trial → trialDaysRemaining = 0 and isTrialExpired = true
  - Missing billing.json → synthetic response with trialDaysRemaining = 14
  - plan = "paid" → validation rejection
  - Unknown fields silently ignored
  - Valid JWT required
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_s3_billing(json_data: dict | None = None):
    """Return an aioboto3 S3 mock for billing reads."""
    import json

    s3 = MagicMock()
    s3.__aenter__ = AsyncMock(return_value=s3)
    s3.__aexit__ = AsyncMock(return_value=False)

    async def _get_object(**kwargs):
        if json_data is None:
            from botocore.exceptions import ClientError
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                "GetObject",
            )
        body = MagicMock()
        body.read = AsyncMock(return_value=json.dumps(json_data).encode())
        return {"Body": body}

    s3.get_object = AsyncMock(side_effect=_get_object)

    session = MagicMock()
    session.client = MagicMock(return_value=s3)
    return session


def _billing_json(days_since_start: int = 0, trial_days: int = 14) -> dict:
    """Build billing.json payload with trial_start relative to now."""
    trial_start = datetime.now(timezone.utc) - timedelta(days=days_since_start)
    return {
        "plan": "trial",
        "trial_start": trial_start.isoformat(),
        "trial_days": trial_days,
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_billing_401_without_token(client):
    resp = client.get("/api/billing")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Happy path — active trial
# ---------------------------------------------------------------------------


def test_billing_active_trial_days_remaining(client, auth_headers, app_no_redis):
    """Trial started 10 days ago, 14-day trial → trialDaysRemaining = 4."""
    session = _mock_s3_billing(_billing_json(days_since_start=10, trial_days=14))
    with patch("app.routes.billing.aioboto3.Session", return_value=session):
        resp = client.get("/api/billing", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "trial"
    assert body["trialDaysRemaining"] == 4
    assert body["isTrialExpired"] is False


def test_billing_trial_not_started(client, auth_headers, app_no_redis):
    """Trial started today → trialDaysRemaining = 14."""
    session = _mock_s3_billing(_billing_json(days_since_start=0, trial_days=14))
    with patch("app.routes.billing.aioboto3.Session", return_value=session):
        resp = client.get("/api/billing", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["trialDaysRemaining"] == 14
    assert body["isTrialExpired"] is False


# ---------------------------------------------------------------------------
# Expired trial
# ---------------------------------------------------------------------------


def test_billing_expired_trial(client, auth_headers, app_no_redis):
    """Trial started 20 days ago, 14-day trial → trialDaysRemaining = 0, expired."""
    session = _mock_s3_billing(_billing_json(days_since_start=20, trial_days=14))
    with patch("app.routes.billing.aioboto3.Session", return_value=session):
        resp = client.get("/api/billing", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["trialDaysRemaining"] == 0
    assert body["isTrialExpired"] is True


# ---------------------------------------------------------------------------
# Missing billing.json → synthetic 14-day response
# ---------------------------------------------------------------------------


def test_billing_missing_file_synthetic_response(client, auth_headers, app_no_redis):
    """No billing.json → synthetic trial with trialDaysRemaining = 14."""
    session = _mock_s3_billing(json_data=None)
    with patch("app.routes.billing.aioboto3.Session", return_value=session):
        resp = client.get("/api/billing", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "trial"
    assert body["trialDaysRemaining"] == 14
    assert body["isTrialExpired"] is False
    # trialEndDate should be ~14 days from today
    assert "trialEndDate" in body


def test_billing_synthetic_trial_end_date_format(client, auth_headers, app_no_redis):
    """Synthetic trialEndDate must be YYYY-MM-DD format."""
    import re
    session = _mock_s3_billing(json_data=None)
    with patch("app.routes.billing.aioboto3.Session", return_value=session):
        resp = client.get("/api/billing", headers=auth_headers)

    body = resp.json()
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", body["trialEndDate"])


# ---------------------------------------------------------------------------
# BillingConfig validation
# ---------------------------------------------------------------------------


def test_billing_unknown_fields_ignored(client, auth_headers, app_no_redis):
    """Unknown fields in billing.json are silently ignored."""
    data = {**_billing_json(), "unknown_field": "value", "extra": 42}
    session = _mock_s3_billing(data)
    with patch("app.routes.billing.aioboto3.Session", return_value=session):
        resp = client.get("/api/billing", headers=auth_headers)

    assert resp.status_code == 200


def test_billing_paid_plan_rejected(client, auth_headers, app_no_redis):
    """plan = 'paid' is not valid for Phase 1 — should cause error or be rejected."""
    data = {**_billing_json(), "plan": "paid"}
    session = _mock_s3_billing(data)
    with patch("app.routes.billing.aioboto3.Session", return_value=session):
        resp = client.get("/api/billing", headers=auth_headers)

    # Phase 1 only supports "trial" — paid plan should return error
    assert resp.status_code in (422, 500, 400)
