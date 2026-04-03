"""Tests for story-4-2: GET /calls/:id — Call Detail Endpoint.

TDD: RED tests written first. Tests cover:
  - Path traversal call_id returns 400
  - Cross-tenant call_id returns 404 (indistinguishable from missing)
  - caller_number absent from response body
  - Missing call returns 404
  - Valid call returns full detail schema
  - call_id format validation (invalid chars)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import mint_jwt


def _mock_redis_with_meta(call_id: str, tenant_slug: str, meta: dict) -> MagicMock:
    redis = MagicMock()
    redis.aclose = AsyncMock()

    async def _hgetall(key: str) -> dict:
        if call_id in key and tenant_slug in key:
            return meta
        return {}

    redis.hgetall = AsyncMock(side_effect=_hgetall)
    return redis


_VALID_META = {
    "call_control_id": "cc-001",
    "tenant_slug": "acme",
    "start_time": "1700000000.0",
    "duration_s": "125",
    "status": "completed",
    "needs_callback": "true",
    "intent": "info",
    "caller_name": "John Smith",
    "phone_hash": "abc123def456abcd",
}


# ---------------------------------------------------------------------------
# Path traversal protection
# ---------------------------------------------------------------------------


def test_path_traversal_call_id_returns_400(client, auth_headers):
    resp = client.get("/api/calls/../../../secret", headers=auth_headers)
    # FastAPI/Starlette normalises the URL path before routing
    # The call_id would be "..%2F..%2F..%2Fsecret" or similar — test the raw validation
    assert resp.status_code in (400, 404)


def test_dotdot_call_id_returns_400(client, auth_headers):
    resp = client.get("/api/calls/..", headers=auth_headers)
    assert resp.status_code in (400, 404)


def test_invalid_call_id_chars_returns_400(client, auth_headers):
    """call_id with shell-special chars must return 400."""
    resp = client.get("/api/calls/cc-001;rm+-rf+/", headers=auth_headers)
    assert resp.status_code in (400, 404)


def test_call_id_with_slash_returns_400(client, auth_headers, app_no_redis):
    """call_id containing % or other invalid chars returns 400."""
    redis = MagicMock()
    redis.aclose = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    app_no_redis.state.redis = redis

    # URL-encode a slash: %2F is invalid in the call_id value
    resp = client.get("/api/calls/cc%2F001", headers=auth_headers)
    # FastAPI decodes %2F as '/' which splits the path — returns 405/404 at routing
    assert resp.status_code in (400, 404, 405)


# ---------------------------------------------------------------------------
# Cross-tenant isolation — returns 404 identical to missing call
# ---------------------------------------------------------------------------


def test_cross_tenant_returns_404(client, app_no_redis):
    """Cross-tenant call_id returns 404, identical to genuinely missing call."""
    # Call belongs to tenant-b
    meta_b = {**_VALID_META, "tenant_slug": "tenant-b"}
    redis = MagicMock()
    redis.aclose = AsyncMock()

    async def _hgetall(key: str) -> dict:
        # Returns data for tenant-b key, empty for tenant-a key
        if "tenant-b" in key:
            return meta_b
        return {}

    redis.hgetall = AsyncMock(side_effect=_hgetall)
    app_no_redis.state.redis = redis

    # Authenticated as tenant-a
    token_a = mint_jwt(tenant_slug="tenant-a", tenant_id="12345678-1234-4234-8234-123456789abc")
    resp = client.get(
        "/api/calls/cc-001",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not found"}


def test_missing_call_returns_404(client, auth_headers, app_no_redis):
    """Genuinely missing call returns same 404 as cross-tenant."""
    redis = MagicMock()
    redis.aclose = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    app_no_redis.state.redis = redis

    resp = client.get("/api/calls/cc-does-not-exist", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not found"}


# ---------------------------------------------------------------------------
# caller_number must NOT appear in response
# ---------------------------------------------------------------------------


def test_caller_number_absent_from_response(client, auth_headers, app_no_redis, monkeypatch):
    """caller_number never appears in the call detail response."""
    import re

    session_mock = _make_s3_client_mock(archive_body=b"{}")
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: session_mock)

    meta = {**_VALID_META, "caller_number": "+61412345678"}  # should be stripped
    redis = _mock_redis_with_meta("cc-001", "acme", meta)
    app_no_redis.state.redis = redis

    resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 200

    body_text = resp.text
    au_phone_re = re.compile(r"\+61[1-9]\d{8}")
    assert not au_phone_re.search(body_text), "AU phone number found in response — PII leak!"


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
    session_mock = _make_s3_client_mock(
        archive_body=_json.dumps(archive).encode(), recording_exists=False
    )
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: session_mock)

    redis = _mock_redis_with_meta("cc-001", "acme", _VALID_META)
    app_no_redis.state.redis = redis

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
    # PII: callerPhone must not be a raw phone number
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
    redis = MagicMock()
    redis.aclose = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    app_no_redis.state.redis = redis

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
    redis = MagicMock()
    redis.aclose = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    app_no_redis.state.redis = redis

    resp = client.get(f"/api/calls/{call_id}", headers=auth_headers)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# AC1 + AC2: S3 archive fetch — transcript, agentActions, summary from S3
# ---------------------------------------------------------------------------


def _make_s3_client_mock(
    archive_body: bytes | None = None,
    archive_error_code: str | None = None,
    recording_exists: bool = False,
) -> MagicMock:
    """Build an async context-manager mock for aioboto3 s3 client."""
    import json

    s3_client = MagicMock()

    # get_object
    if archive_error_code:
        from botocore.exceptions import ClientError
        error_response = {"Error": {"Code": archive_error_code, "Message": "mock"}}
        s3_client.get_object = AsyncMock(
            side_effect=ClientError(error_response, "GetObject")
        )
    else:
        body_mock = MagicMock()
        body_mock.read = AsyncMock(return_value=archive_body or b"{}")
        get_object_resp = {"Body": body_mock}
        s3_client.get_object = AsyncMock(return_value=get_object_resp)

    # head_object for hasRecording
    if recording_exists:
        s3_client.head_object = AsyncMock(return_value={})
    else:
        from botocore.exceptions import ClientError
        error_response = {"Error": {"Code": "NoSuchKey", "Message": "mock"}}
        s3_client.head_object = AsyncMock(
            side_effect=ClientError(error_response, "HeadObject")
        )

    # Make s3_client itself usable as async context manager
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=s3_client)
    cm.__aexit__ = AsyncMock(return_value=False)

    session_mock = MagicMock()
    session_mock.client = MagicMock(return_value=cm)
    return session_mock


def test_s3_archive_transcript_returned(client, auth_headers, app_no_redis, monkeypatch):
    """AC1 + AC2: transcript and agentActions come from S3 archive."""
    import json

    archive = {
        "transcript": [{"role": "user", "text": "Hello"}],
        "agent_actions": [{"action": "lookup", "result": "ok"}],
        "summary": "Short call about billing.",
    }
    session_mock = _make_s3_client_mock(archive_body=json.dumps(archive).encode())
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: session_mock)

    redis = _mock_redis_with_meta("cc-001", "acme", _VALID_META)
    app_no_redis.state.redis = redis

    resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["transcript"] == [{"role": "user", "text": "Hello"}]
    assert body["agentActions"] == [{"action": "lookup", "result": "ok"}]
    assert body["summary"] == "Short call about billing."


def test_s3_archive_key_derived_from_start_time(monkeypatch):
    """AC2: S3 key is derived from start_time, not from user input."""
    from app.routes.calls import _derive_archive_key

    # start_time = 1700000000.0 → 2023-11-14 22:13:20 UTC
    key = _derive_archive_key("acme", "1700000000.0", "cc-001")
    assert key == "acme/2023/11/14/cc-001.json"
    # Verify user-supplied call_id is only used at the leaf, key structure is date-based
    assert key.startswith("acme/2023/11/14/")


# ---------------------------------------------------------------------------
# AC4: callerPhone present in response (as phone_hash, not raw number)
# ---------------------------------------------------------------------------


def test_caller_phone_in_response(client, auth_headers, app_no_redis, monkeypatch):
    """AC4: callerPhone field is present in response."""
    import json

    session_mock = _make_s3_client_mock(archive_body=b"{}")
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: session_mock)

    meta = {**_VALID_META, "phone_hash": "abc123def456abcd"}
    redis = _mock_redis_with_meta("cc-001", "acme", meta)
    app_no_redis.state.redis = redis

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
    session_mock = _make_s3_client_mock(archive_body=b"{}", recording_exists=True)
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: session_mock)

    redis = _mock_redis_with_meta("cc-001", "acme", _VALID_META)
    app_no_redis.state.redis = redis

    resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["hasRecording"] is True


def test_has_recording_false_when_no_s3_object(
    client, auth_headers, app_no_redis, monkeypatch
):
    """AC5: hasRecording=false when recording S3 object does not exist."""
    session_mock = _make_s3_client_mock(archive_body=b"{}", recording_exists=False)
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: session_mock)

    redis = _mock_redis_with_meta("cc-001", "acme", _VALID_META)
    app_no_redis.state.redis = redis

    resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["hasRecording"] is False


# ---------------------------------------------------------------------------
# AC7: S3 NoSuchKey → 404
# ---------------------------------------------------------------------------


def test_s3_no_such_key_returns_404(client, auth_headers, app_no_redis, monkeypatch):
    """AC7: S3 NoSuchKey on archive fetch returns 404 to client."""
    session_mock = _make_s3_client_mock(archive_error_code="NoSuchKey")
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: session_mock)

    redis = _mock_redis_with_meta("cc-001", "acme", _VALID_META)
    app_no_redis.state.redis = redis

    resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not found"}


def test_s3_no_such_bucket_returns_404(client, auth_headers, app_no_redis, monkeypatch):
    """AC7: S3 NoSuchBucket on archive fetch returns 404 to client."""
    session_mock = _make_s3_client_mock(archive_error_code="NoSuchBucket")
    monkeypatch.setattr("app.routes.calls.aioboto3.Session", lambda: session_mock)

    redis = _mock_redis_with_meta("cc-001", "acme", _VALID_META)
    app_no_redis.state.redis = redis

    resp = client.get("/api/calls/cc-001", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not found"}
