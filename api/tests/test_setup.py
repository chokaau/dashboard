"""Tests for story-4-7: POST /setup/complete Endpoint.

TDD: RED tests written first. Tests cover:
  - Route returns 404 before implementation (canonical red step)
  - staff role → 403
  - owner role → 200 with S3 write
  - idempotent: second call overwrites completed_at
  - S3 write failure → 500
  - Valid JWT required
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import mint_jwt


def _mock_s3_setup(put_fails: bool = False):
    """Return an aioboto3 S3 mock for setup/complete writes."""
    s3 = MagicMock()
    s3.__aenter__ = AsyncMock(return_value=s3)
    s3.__aexit__ = AsyncMock(return_value=False)

    if put_fails:
        from botocore.exceptions import ClientError
        s3.put_object = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "InternalError", "Message": "Server Error"}},
                "PutObject",
            )
        )
    else:
        s3.put_object = AsyncMock(return_value={})

    session = MagicMock()
    session.client = MagicMock(return_value=s3)
    return session


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_setup_complete_401_without_token(client):
    resp = client.post("/api/setup/complete")
    assert resp.status_code == 401


def test_setup_complete_403_staff_role(client):
    token = mint_jwt(role="staff")
    session = _mock_s3_setup()
    with patch("app.routes.setup.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/setup/complete",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 403
    assert resp.json() == {"detail": "Insufficient role"}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_setup_complete_owner_returns_200(client, auth_headers, app_no_redis):
    session = _mock_s3_setup()
    with patch("app.routes.setup.aioboto3.Session", return_value=session):
        resp = client.post("/api/setup/complete", headers=auth_headers)

    assert resp.status_code == 200


def test_setup_complete_writes_setup_complete_json(client, auth_headers, app_no_redis):
    """setup_complete.json must be written to S3 with setup_complete=true."""
    import json

    s3 = MagicMock()
    s3.__aenter__ = AsyncMock(return_value=s3)
    s3.__aexit__ = AsyncMock(return_value=False)
    s3.put_object = AsyncMock(return_value={})

    session = MagicMock()
    session.client = MagicMock(return_value=s3)

    with patch("app.routes.setup.aioboto3.Session", return_value=session):
        resp = client.post("/api/setup/complete", headers=auth_headers)

    assert resp.status_code == 200

    # Verify S3 put_object was called with correct data
    s3.put_object.assert_called_once()
    call_kwargs = s3.put_object.call_args[1]

    assert "setup_complete.json" in call_kwargs.get("Key", "")
    body = json.loads(call_kwargs.get("Body", b"{}"))
    assert body["setup_complete"] is True
    assert "completed_at" in body


def test_setup_complete_idempotent(client, auth_headers, app_no_redis):
    """Second call is idempotent — returns 200 and overwrites completed_at."""
    session = _mock_s3_setup()
    with patch("app.routes.setup.aioboto3.Session", return_value=session):
        resp1 = client.post("/api/setup/complete", headers=auth_headers)
        resp2 = client.post("/api/setup/complete", headers=auth_headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# S3 write failure
# ---------------------------------------------------------------------------


def test_setup_complete_s3_failure_returns_500(client, auth_headers, app_no_redis):
    """S3 write failure → 500 with specific error message."""
    session = _mock_s3_setup(put_fails=True)
    with patch("app.routes.setup.aioboto3.Session", return_value=session):
        resp = client.post("/api/setup/complete", headers=auth_headers)

    assert resp.status_code == 500
    assert "Setup completion could not be recorded" in resp.json()["detail"]
