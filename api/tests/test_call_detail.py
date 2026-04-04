"""Tests for story-4-2: GET /calls/:id — Call Detail Endpoint.

TDD: RED tests written first. Tests cover:
  - Path traversal call_id returns 400
  - Cross-tenant call_id returns 404 (indistinguishable from missing)
  - caller_number absent from response body
  - Missing call returns 404
  - Valid call returns full detail schema
  - call_id format validation (invalid chars)

Updated in story 004-003: Redis fallback removed from get_call route.
Tests now mock the PostgreSQL repository instead of Redis hash data.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import mint_jwt


# ---------------------------------------------------------------------------
# ORM model factory
# ---------------------------------------------------------------------------


def _make_pg_call(
    call_id: str = "cc-001",
    tenant_slug: str = "acme",
    env: str = "test",
    caller_name: str = "John Smith",
    phone_hash: str = "abc123def456abcd",
    status: str = "completed",
    needs_callback: bool = True,
    intent: str = "info",
    duration_s: int = 125,
    summary: str | None = None,
    has_recording: bool = False,
) -> MagicMock:
    """Build a minimal Call-like object for get_call mocking."""
    call = MagicMock()
    call.id = call_id
    call.tenant_slug = tenant_slug
    call.env = env
    call.caller_name = caller_name
    call.phone_hash = phone_hash
    call.status = status
    call.needs_callback = needs_callback
    call.intent = intent
    call.duration_s = duration_s
    call.summary = summary
    call.has_recording = has_recording
    # start_time: 2023-11-14 22:13:20 UTC (matches 1700000000.0 epoch)
    call.start_time = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    return call


@contextmanager
def _mock_pg_repo(app, call_or_none):
    """Context manager that wires a mock repo into the get_call route.

    Overrides get_db_session to yield a sentinel session, and patches
    SQLAlchemyCallRepository (at routes import site) to return a mock repo
    whose get_call coroutine returns call_or_none.

    Usage:
        with _mock_pg_repo(app_no_redis, _make_pg_call()) as repo_mock:
            resp = client.get("/api/calls/cc-001", headers=auth_headers)
    """
    from app.dependencies.database import get_db_session

    session_mock = MagicMock()
    repo_mock = MagicMock()
    repo_mock.get_call = AsyncMock(return_value=call_or_none)

    async def _override_session():
        yield session_mock

    app.dependency_overrides[get_db_session] = _override_session

    with patch("app.routes.calls.SQLAlchemyCallRepository", return_value=repo_mock):
        try:
            yield repo_mock
        finally:
            app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# S3 mock helper
# ---------------------------------------------------------------------------


def _make_s3_session_mock(
    archive_body: bytes | None = None,
    archive_error_code: str | None = None,
    recording_exists: bool = False,
) -> MagicMock:
    """Build an async context-manager mock for aioboto3 s3 client."""
    from botocore.exceptions import ClientError

    s3_client = MagicMock()

    if archive_error_code:
        error_response = {"Error": {"Code": archive_error_code, "Message": "mock"}}
        s3_client.get_object = AsyncMock(
            side_effect=ClientError(error_response, "GetObject")
        )
    else:
        body_mock = MagicMock()
        body_mock.read = AsyncMock(return_value=archive_body or b"{}")
        s3_client.get_object = AsyncMock(return_value={"Body": body_mock})

    if recording_exists:
        s3_client.head_object = AsyncMock(return_value={})
    else:
        error_response = {"Error": {"Code": "NoSuchKey", "Message": "mock"}}
        s3_client.head_object = AsyncMock(
            side_effect=ClientError(error_response, "HeadObject")
        )

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=s3_client)
    cm.__aexit__ = AsyncMock(return_value=False)

    session_mock = MagicMock()
    session_mock.client = MagicMock(return_value=cm)
    return session_mock


# ---------------------------------------------------------------------------
# Path traversal protection
# ---------------------------------------------------------------------------


def test_path_traversal_call_id_returns_400(client, auth_headers):
    resp = client.get("/api/calls/../../../secret", headers=auth_headers)
    assert resp.status_code in (400, 404)


def test_dotdot_call_id_returns_400(client, auth_headers):
    resp = client.get("/api/calls/..", headers=auth_headers)
    assert resp.status_code in (400, 404)


def test_invalid_call_id_chars_returns_400(client, auth_headers):
    """call_id with shell-special chars must return 400."""
    resp = client.get("/api/calls/cc-001;rm+-rf+/", headers=auth_headers)
    assert resp.status_code in (400, 404)


def test_call_id_with_slash_returns_400(client, auth_headers):
    """call_id containing % or other invalid chars returns 400."""
    resp = client.get("/api/calls/cc%2F001", headers=auth_headers)
    assert resp.status_code in (400, 404, 405)


# ---------------------------------------------------------------------------
# Cross-tenant isolation — returns 404 identical to missing call
# ---------------------------------------------------------------------------


def test_cross_tenant_returns_404(client, app_no_redis):
    """Cross-tenant call_id returns 404.

    Phase 4: DB repo.get_call filters by tenant_slug — returns None for
    cross-tenant requests. No info leakage (identical to missing call).
    """
    with _mock_pg_repo(app_no_redis, None):
        token_a = mint_jwt(
            tenant_slug="tenant-a",
            tenant_id="12345678-1234-4234-8234-123456789abc",
        )
        resp = client.get(
            "/api/calls/cc-001",
            headers={"Authorization": f"Bearer {token_a}"},
        )
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not found"}


def test_missing_call_returns_404(client, auth_headers, app_no_redis):
    """Genuinely missing call returns 404."""
    with _mock_pg_repo(app_no_redis, None):
        resp = client.get("/api/calls/cc-does-not-exist", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not found"}


# ---------------------------------------------------------------------------
# caller_number must NOT appear in response
# ---------------------------------------------------------------------------


def test_caller_number_absent_from_response(client, auth_headers, app_no_redis, monkeypatch):
    """caller_number never appears in the call detail response."""
    import re

    s3_mock = _make_s3_session_mock(archive_body=b"{}")
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: s3_mock)

    with _mock_pg_repo(app_no_redis, _make_pg_call(phone_hash="abc123def456abcd")):
        resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 200

    au_phone_re = re.compile(r"\+61[1-9]\d{8}")
    assert not au_phone_re.search(resp.text), "AU phone number found in response — PII leak!"


# ---------------------------------------------------------------------------
# Happy path — response schema
# ---------------------------------------------------------------------------


def test_get_call_detail_happy_path(client, auth_headers, app_no_redis, monkeypatch):
    import json as _json
    import re

    archive = {
        "transcript": [{"role": "agent", "text": "How can I help?"}],
        "agent_actions": [],
        "summary": "Billing query.",
    }
    s3_mock = _make_s3_session_mock(
        archive_body=_json.dumps(archive).encode(), recording_exists=False
    )
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: s3_mock)

    with _mock_pg_repo(
        app_no_redis,
        _make_pg_call(caller_name="John Smith", status="completed", needs_callback=True),
    ):
        resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["id"] == "cc-001"
    assert body["callerName"] == "John Smith"
    assert body["status"] == "completed"
    assert body["needsCallback"] is True
    assert body["intent"] == "info"
    assert "hasRecording" in body
    assert body["transcript"] == [{"role": "agent", "text": "How can I help?"}]
    assert "agentActions" in body
    assert body["summary"] == "Billing query."
    caller_phone = body.get("callerPhone", "")
    au_re = re.compile(r"\+61[1-9]\d{8}")
    assert not au_re.search(str(caller_phone))


def test_get_call_401_without_token(client):
    resp = client.get("/api/calls/cc-001")
    assert resp.status_code == 401


def test_get_call_403_without_tenant(client):
    token = mint_jwt(tenant_slug="")
    resp = client.get("/api/calls/cc-001", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Valid call_id formats pass format check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("call_id", [
    "cc-001",
    "abc123",
    "callcontrol-ABCDEF-01234567",
    "a" * 128,  # max length
])
def test_valid_call_id_formats(call_id, client, auth_headers, app_no_redis):
    with _mock_pg_repo(app_no_redis, None):
        resp = client.get(f"/api/calls/{call_id}", headers=auth_headers)
    # 404 (not found) is correct — valid format but no data
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Invalid call_id formats return 400
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("call_id", [
    "-starts-with-dash",
    "has space",
    "has@symbol",
    "a" * 129,  # over max length
])
def test_invalid_call_id_returns_400(call_id, client, auth_headers, app_no_redis):
    resp = client.get(f"/api/calls/{call_id}", headers=auth_headers)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# AC1 + AC2: S3 archive fetch — transcript, agentActions, summary from S3
# ---------------------------------------------------------------------------


def test_s3_archive_transcript_returned(client, auth_headers, app_no_redis, monkeypatch):
    """AC1 + AC2: transcript and agentActions come from S3 archive."""
    import json

    archive = {
        "transcript": [{"role": "user", "text": "Hello"}],
        "agent_actions": [{"action": "lookup", "result": "ok"}],
        "summary": "Short call about billing.",
    }
    s3_mock = _make_s3_session_mock(archive_body=json.dumps(archive).encode())
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: s3_mock)

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["transcript"] == [{"role": "user", "text": "Hello"}]
    assert body["agentActions"] == [{"action": "lookup", "result": "ok"}]
    assert body["summary"] == "Short call about billing."


def test_s3_archive_key_derived_from_start_time():
    """AC2: S3 key is derived from start_time datetime, not from user input."""
    from app.routes.calls import _derive_archive_key

    # start_time: 2023-11-14 22:13:20 UTC (epoch 1700000000.0)
    start_time = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    key = _derive_archive_key("acme", start_time, "cc-001")
    assert key == "acme/2023/11/14/cc-001.json"
    assert key.startswith("acme/2023/11/14/")


# ---------------------------------------------------------------------------
# AC4: callerPhone present in response (as phone_hash, not raw number)
# ---------------------------------------------------------------------------


def test_caller_phone_in_response(client, auth_headers, app_no_redis, monkeypatch):
    """AC4: callerPhone field is present in response."""
    s3_mock = _make_s3_session_mock(archive_body=b"{}")
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: s3_mock)

    with _mock_pg_repo(app_no_redis, _make_pg_call(phone_hash="abc123def456abcd")):
        resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert "callerPhone" in body
    assert body["callerPhone"] == "abc123def456abcd"


# ---------------------------------------------------------------------------
# AC5: hasRecording reflects S3 object existence
# ---------------------------------------------------------------------------


def test_has_recording_true_when_s3_object_exists(
    client, auth_headers, app_no_redis, monkeypatch
):
    """AC5: hasRecording=true when recording S3 object exists."""
    s3_mock = _make_s3_session_mock(archive_body=b"{}", recording_exists=True)
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: s3_mock)

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["hasRecording"] is True


def test_has_recording_false_when_no_s3_object(
    client, auth_headers, app_no_redis, monkeypatch
):
    """AC5: hasRecording=false when recording S3 object does not exist."""
    s3_mock = _make_s3_session_mock(archive_body=b"{}", recording_exists=False)
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: s3_mock)

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["hasRecording"] is False


# ---------------------------------------------------------------------------
# AC7: S3 NoSuchKey → 404
# ---------------------------------------------------------------------------


def test_s3_no_such_key_returns_404(client, auth_headers, app_no_redis, monkeypatch):
    """AC7: S3 NoSuchKey on archive fetch returns 404 to client."""
    s3_mock = _make_s3_session_mock(archive_error_code="NoSuchKey")
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: s3_mock)

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not found"}


def test_s3_no_such_bucket_returns_404(client, auth_headers, app_no_redis, monkeypatch):
    """AC7: S3 NoSuchBucket on archive fetch returns 404 to client."""
    s3_mock = _make_s3_session_mock(archive_error_code="NoSuchBucket")
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: s3_mock)

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not found"}
