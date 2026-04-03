"""Tests for dashboard-10: POST /api/activation/request endpoint.

TDD: RED tests written first. Tests cover:
  - 401 without token
  - 403 for non-owner role
  - Happy path: sets activation_status to "pending", returns 200
  - Idempotent: already-pending returns 200 again
  - S3 read error returns 500
  - S3 write error returns 500
  - SNS publish failure is non-fatal (returns 200)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import mint_jwt


# ---------------------------------------------------------------------------
# S3 mock helpers
# ---------------------------------------------------------------------------


def _billing_json(activation_status: str = "none", product: str = "") -> dict:
    return {
        "plan": "trial",
        "trial_start": datetime.now(timezone.utc).isoformat(),
        "trial_days": 14,
        "activation_status": activation_status,
        "product": product,
    }


def _mock_s3_activation(
    existing_billing: dict | None = None,
    get_error_code: str | None = None,
    put_error: bool = False,
):
    """Return an aioboto3 S3 context manager mock for activation reads/writes."""
    s3 = MagicMock()
    s3.__aenter__ = AsyncMock(return_value=s3)
    s3.__aexit__ = AsyncMock(return_value=False)

    async def _get_object(**kwargs):
        if get_error_code:
            from botocore.exceptions import ClientError
            raise ClientError(
                {"Error": {"Code": get_error_code, "Message": "Error"}},
                "GetObject",
            )
        body = MagicMock()
        data = existing_billing if existing_billing is not None else _billing_json()
        body.read = AsyncMock(return_value=json.dumps(data).encode())
        return {"Body": body}

    async def _put_object(**kwargs):
        if put_error:
            from botocore.exceptions import ClientError
            raise ClientError(
                {"Error": {"Code": "InternalError", "Message": "S3 error"}},
                "PutObject",
            )

    s3.get_object = AsyncMock(side_effect=_get_object)
    s3.put_object = AsyncMock(side_effect=_put_object)

    session = MagicMock()
    session.client = MagicMock(return_value=s3)
    return session


def _staff_token() -> str:
    return mint_jwt(role="staff")


def _owner_token() -> str:
    return mint_jwt(role="owner")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_activation_401_without_token(client):
    resp = client.post("/api/activation/request")
    assert resp.status_code == 401


def test_activation_403_non_owner(client):
    headers = {"Authorization": f"Bearer {_staff_token()}"}
    session = _mock_s3_activation()
    with patch("app.routes.activation.aioboto3.Session", return_value=session):
        resp = client.post("/api/activation/request", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_activation_request_happy_path(client, auth_headers, app_no_redis):
    """Owner submits activation request → billing.json updated to pending."""
    session = _mock_s3_activation(_billing_json(activation_status="none"))
    with patch("app.routes.activation.aioboto3.Session", return_value=session):
        with patch("app.routes.activation.notify_activation_request", new_callable=AsyncMock):
            resp = client.post("/api/activation/request", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["activation_status"] == "pending"


def test_activation_request_writes_billing_json(client, auth_headers, app_no_redis):
    """Activation request writes updated billing.json with activation_status=pending."""
    session = _mock_s3_activation(_billing_json(activation_status="none"))
    with patch("app.routes.activation.aioboto3.Session", return_value=session):
        with patch("app.routes.activation.notify_activation_request", new_callable=AsyncMock):
            resp = client.post("/api/activation/request", headers=auth_headers)

    assert resp.status_code == 200
    # Verify put_object was called
    s3_mock = session.client.return_value.__aenter__.return_value
    assert s3_mock.put_object.called
    call_kwargs = s3_mock.put_object.call_args.kwargs
    written = json.loads(call_kwargs["Body"])
    assert written["activation_status"] == "pending"
    assert written["product"] == "voice"


# ---------------------------------------------------------------------------
# Idempotent — already pending
# ---------------------------------------------------------------------------


def test_activation_already_pending_returns_200(client, auth_headers, app_no_redis):
    """If already pending, re-submitting returns 200 with activation_status=pending."""
    session = _mock_s3_activation(_billing_json(activation_status="pending", product="voice"))
    with patch("app.routes.activation.aioboto3.Session", return_value=session):
        with patch("app.routes.activation.notify_activation_request", new_callable=AsyncMock):
            resp = client.post("/api/activation/request", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["activation_status"] == "pending"


# ---------------------------------------------------------------------------
# Missing billing.json → treated as fresh (none)
# ---------------------------------------------------------------------------


def test_activation_missing_billing_creates_record(client, auth_headers, app_no_redis):
    """Missing billing.json → activation request still succeeds."""
    session = _mock_s3_activation(get_error_code="NoSuchKey")
    with patch("app.routes.activation.aioboto3.Session", return_value=session):
        with patch("app.routes.activation.notify_activation_request", new_callable=AsyncMock):
            resp = client.post("/api/activation/request", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["activation_status"] == "pending"


# ---------------------------------------------------------------------------
# S3 read error (not NoSuchKey)
# ---------------------------------------------------------------------------


def test_activation_s3_read_error_returns_500(client, auth_headers, app_no_redis):
    """Non-NoSuchKey S3 read error → 500."""
    session = _mock_s3_activation(get_error_code="InternalError")
    with patch("app.routes.activation.aioboto3.Session", return_value=session):
        resp = client.post("/api/activation/request", headers=auth_headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# S3 write error
# ---------------------------------------------------------------------------


def test_activation_s3_write_error_returns_500(client, auth_headers, app_no_redis):
    """S3 put_object failure → 500."""
    session = _mock_s3_activation(_billing_json(), put_error=True)
    with patch("app.routes.activation.aioboto3.Session", return_value=session):
        with patch("app.routes.activation.notify_activation_request", new_callable=AsyncMock):
            resp = client.post("/api/activation/request", headers=auth_headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# SNS notify failure is non-fatal
# ---------------------------------------------------------------------------


def test_activation_sns_failure_nonfatal(client, auth_headers, app_no_redis):
    """If notify_activation_request raises, the endpoint still returns 200."""
    session = _mock_s3_activation(_billing_json())
    with patch("app.routes.activation.aioboto3.Session", return_value=session):
        with patch(
            "app.routes.activation.notify_activation_request",
            new_callable=AsyncMock,
            side_effect=Exception("SNS failure"),
        ):
            resp = client.post("/api/activation/request", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["activation_status"] == "pending"
