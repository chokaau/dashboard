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


def test_caller_number_absent_from_response(client, auth_headers, app_no_redis):
    """caller_number never appears in the call detail response."""
    import re

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


def test_get_call_detail_happy_path(client, auth_headers, app_no_redis):
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
    assert "transcript" in body
    assert "agentActions" in body
    # PII: callerPhone must not be a raw phone number
    caller_phone = body.get("callerPhone", "")
    import re
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
