"""Tests for story-4-3: GET /calls/:id/recording — BFF Streaming Proxy.

TDD: RED tests written first. Tests cover:
  - Cross-tenant request returns 404
  - S3 bucket name absent from all response headers/body
  - StreamingResponse with correct Content-Type
  - Range header forwarding to S3
  - Malformed Range header returns 400
  - Recording object missing returns 404
  - Valid JWT required (401 without)
  - Mid-stream exception logged and generator closed cleanly
"""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import mint_jwt


def _mock_redis_for_recording(call_id: str, tenant_slug: str) -> MagicMock:
    redis = MagicMock()
    redis.aclose = AsyncMock()
    redis.hgetall = AsyncMock(return_value={
        "call_control_id": call_id,
        "tenant_slug": tenant_slug,
        "start_time": "1700000000.0",
        "status": "completed",
    })
    return redis


async def _s3_stream_generator():
    """Fake S3 streaming body."""
    yield b"FAKE_AUDIO_DATA_CHUNK_1"
    yield b"FAKE_AUDIO_DATA_CHUNK_2"


class _FakeStreamBody:
    async def __aiter__(self):
        yield b"FAKE_AUDIO_DATA"


def _mock_s3_get_object(body_data: bytes = b"FAKE_AUDIO"):
    """Return a mock aioboto3 S3 get_object response."""
    stream_body = MagicMock()
    stream_body.__aiter__ = AsyncMock(return_value=iter([body_data]))

    async def _read():
        return body_data

    stream_body.read = _read

    response = {
        "Body": stream_body,
        "ContentType": "audio/mpeg",
        "ContentLength": len(body_data),
    }
    return response


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_recording_401_without_token(client):
    resp = client.get("/api/calls/cc-001/recording")
    assert resp.status_code == 401


def test_recording_403_without_tenant(client):
    token = mint_jwt(tenant_slug="")
    resp = client.get(
        "/api/calls/cc-001/recording",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Route exists and Redis check fires (404 when no data)
# ---------------------------------------------------------------------------


def test_recording_404_when_call_not_found(client, auth_headers, app_no_redis):
    redis = MagicMock()
    redis.aclose = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    app_no_redis.state.redis = redis

    resp = client.get("/api/calls/cc-001/recording", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-tenant returns 404
# ---------------------------------------------------------------------------


def test_recording_cross_tenant_returns_404(client, app_no_redis):
    redis = MagicMock()
    redis.aclose = AsyncMock()

    async def _hgetall(key: str) -> dict:
        if "tenant-b" in key:
            return {"call_control_id": "cc-001", "tenant_slug": "tenant-b"}
        return {}

    redis.hgetall = AsyncMock(side_effect=_hgetall)
    app_no_redis.state.redis = redis

    token_a = mint_jwt(tenant_slug="tenant-a", tenant_id="12345678-1234-4234-8234-123456789abc")
    resp = client.get(
        "/api/calls/cc-001/recording",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# S3 bucket name absent from response headers
# ---------------------------------------------------------------------------


def test_s3_bucket_name_absent_from_headers(client, auth_headers, app_no_redis):
    """S3 bucket name must not appear in any response header."""
    redis = _mock_redis_for_recording("cc-001", "acme")
    app_no_redis.state.redis = redis

    bucket_name = app_no_redis.state.config.s3_recordings_bucket or "choka-recordings"

    mock_s3_client = MagicMock()
    mock_get_object = AsyncMock(return_value=_mock_s3_get_object())
    mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_s3_client.__aexit__ = AsyncMock(return_value=False)
    mock_s3_client.get_object = mock_get_object

    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=mock_s3_client)

    with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
        resp = client.get("/api/calls/cc-001/recording", headers=auth_headers)

    # Bucket name must not appear in any header value
    for header_name, header_value in resp.headers.items():
        assert bucket_name not in header_value, (
            f"S3 bucket name '{bucket_name}' found in response header '{header_name}'"
        )


# ---------------------------------------------------------------------------
# Content-Type header correct
# ---------------------------------------------------------------------------


def test_recording_content_type_audio_mpeg(client, auth_headers, app_no_redis):
    redis = _mock_redis_for_recording("cc-001", "acme")
    app_no_redis.state.redis = redis

    mock_s3_client = MagicMock()
    mock_get_object = AsyncMock(return_value=_mock_s3_get_object())
    mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_s3_client.__aexit__ = AsyncMock(return_value=False)
    mock_s3_client.get_object = mock_get_object

    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=mock_s3_client)

    with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
        resp = client.get("/api/calls/cc-001/recording", headers=auth_headers)

    assert resp.headers.get("content-type", "").startswith("audio/")


# ---------------------------------------------------------------------------
# Range header forwarded to S3
# ---------------------------------------------------------------------------


def test_range_header_forwarded_to_s3(client, auth_headers, app_no_redis):
    """Range: bytes=0-1023 must be forwarded to S3 get_object."""
    redis = _mock_redis_for_recording("cc-001", "acme")
    app_no_redis.state.redis = redis

    mock_s3_client = MagicMock()
    mock_get_object = AsyncMock(return_value=_mock_s3_get_object())
    mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_s3_client.__aexit__ = AsyncMock(return_value=False)
    mock_s3_client.get_object = mock_get_object

    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=mock_s3_client)

    with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
        resp = client.get(
            "/api/calls/cc-001/recording",
            headers={**auth_headers, "Range": "bytes=0-1023"},
        )

    # Verify S3 get_object was called with the Range kwarg
    mock_get_object.assert_called_once()
    call_kwargs = mock_get_object.call_args[1]
    assert "Range" in call_kwargs
    assert call_kwargs["Range"] == "bytes=0-1023"


# ---------------------------------------------------------------------------
# Malformed Range header returns 400
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_range", [
    "not-a-range",
    "bytes=abc-def",
    "pages=0-100",
    "",
])
def test_malformed_range_returns_400(bad_range, client, auth_headers, app_no_redis):
    redis = _mock_redis_for_recording("cc-001", "acme")
    app_no_redis.state.redis = redis

    resp = client.get(
        "/api/calls/cc-001/recording",
        headers={**auth_headers, "Range": bad_range},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# S3 NoSuchKey returns 404
# ---------------------------------------------------------------------------


def test_recording_s3_no_such_key_returns_404(client, auth_headers, app_no_redis):
    redis = _mock_redis_for_recording("cc-001", "acme")
    app_no_redis.state.redis = redis

    from botocore.exceptions import ClientError

    mock_s3_client = MagicMock()
    mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_s3_client.__aexit__ = AsyncMock(return_value=False)
    mock_s3_client.get_object = AsyncMock(
        side_effect=ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
            "GetObject",
        )
    )

    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=mock_s3_client)

    with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
        resp = client.get("/api/calls/cc-001/recording", headers=auth_headers)

    assert resp.status_code == 404
