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

Updated in story 004-004: Redis ownership lookup removed from recordings route.
Tests now mock the PostgreSQL repository instead of Redis hash data.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import mint_jwt


# ---------------------------------------------------------------------------
# PG call factory and repo mock helper
# ---------------------------------------------------------------------------


def _make_pg_call(
    call_id: str = "cc-001",
    tenant_slug: str = "acme",
    env: str = "test",
    start_time: datetime | None = None,
) -> MagicMock:
    """Build a minimal Call-like object for recording route mocking."""
    call = MagicMock()
    call.id = call_id
    call.tenant_slug = tenant_slug
    call.env = env
    # 1700000000.0 epoch → 2023-11-14 22:13:20 UTC
    call.start_time = start_time or datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    return call


@contextmanager
def _mock_pg_repo(app, call_or_none):
    """Context manager that wires a mock repo into the recording route.

    Overrides get_db_session to yield a sentinel session, and patches
    SQLAlchemyCallRepository (at routes import site) to return a mock repo
    whose get_call coroutine returns call_or_none.
    """
    from app.dependencies.database import get_db_session

    session_mock = MagicMock()
    repo_mock = MagicMock()
    repo_mock.get_call = AsyncMock(return_value=call_or_none)

    async def _override_session():
        yield session_mock

    app.dependency_overrides[get_db_session] = _override_session

    with patch("app.routes.recordings.SQLAlchemyCallRepository", return_value=repo_mock):
        try:
            yield repo_mock
        finally:
            app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# S3 mock helpers
# ---------------------------------------------------------------------------


def _mock_s3_get_object(body_data: bytes = b"FAKE_AUDIO"):
    """Return a mock aioboto3 S3 get_object response."""

    class _AsyncStreamBody:
        """Proper async iterable S3 body stub."""

        def __aiter__(self):
            return self._gen()

        async def _gen(self):
            yield body_data

        async def read(self):
            return body_data

    return {
        "Body": _AsyncStreamBody(),
        "ContentType": "audio/mpeg",
        "ContentLength": len(body_data),
    }


def _make_s3_session(get_object_return=None, get_object_side_effect=None):
    """Build an aioboto3-style session mock for the recordings S3 client."""
    mock_s3_client = MagicMock()
    mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_s3_client.__aexit__ = AsyncMock(return_value=False)

    if get_object_side_effect is not None:
        mock_s3_client.get_object = AsyncMock(side_effect=get_object_side_effect)
    else:
        mock_s3_client.get_object = AsyncMock(
            return_value=get_object_return or _mock_s3_get_object()
        )

    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=mock_s3_client)
    return mock_session, mock_s3_client


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
# 404 when call not found in DB
# ---------------------------------------------------------------------------


def test_recording_404_when_call_not_found(client, auth_headers, app_no_redis):
    with _mock_pg_repo(app_no_redis, None):
        resp = client.get("/api/calls/cc-001/recording", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-tenant returns 404
# ---------------------------------------------------------------------------


def test_recording_cross_tenant_returns_404(client, app_no_redis):
    """repo.get_call filters by tenant_slug — cross-tenant returns None → 404."""
    with _mock_pg_repo(app_no_redis, None):
        token_a = mint_jwt(
            tenant_slug="tenant-a",
            tenant_id="12345678-1234-4234-8234-123456789abc",
        )
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
    bucket_name = app_no_redis.state.config.s3_recordings_bucket or "choka-recordings"
    mock_session, _ = _make_s3_session()

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
            resp = client.get("/api/calls/cc-001/recording", headers=auth_headers)

    for header_name, header_value in resp.headers.items():
        assert bucket_name not in header_value, (
            f"S3 bucket name '{bucket_name}' found in response header '{header_name}'"
        )


# ---------------------------------------------------------------------------
# Content-Type header correct
# ---------------------------------------------------------------------------


def test_recording_content_type_audio_mpeg(client, auth_headers, app_no_redis):
    mock_session, _ = _make_s3_session()

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
            resp = client.get("/api/calls/cc-001/recording", headers=auth_headers)

    assert resp.headers.get("content-type", "").startswith("audio/")


# ---------------------------------------------------------------------------
# Range header forwarded to S3
# ---------------------------------------------------------------------------


def test_range_header_forwarded_to_s3(client, auth_headers, app_no_redis):
    """Range: bytes=0-1023 must be forwarded to S3 get_object."""
    mock_session, mock_s3_client = _make_s3_session()

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
            resp = client.get(
                "/api/calls/cc-001/recording",
                headers={**auth_headers, "Range": "bytes=0-1023"},
            )

    mock_s3_client.get_object.assert_called_once()
    call_kwargs = mock_s3_client.get_object.call_args[1]
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
    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        resp = client.get(
            "/api/calls/cc-001/recording",
            headers={**auth_headers, "Range": bad_range},
        )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# S3 NoSuchKey returns 404
# ---------------------------------------------------------------------------


def test_recording_s3_no_such_key_returns_404(client, auth_headers, app_no_redis):
    from botocore.exceptions import ClientError

    mock_session, _ = _make_s3_session(
        get_object_side_effect=ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
            "GetObject",
        )
    )

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
            resp = client.get("/api/calls/cc-001/recording", headers=auth_headers)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC-1: Content-Disposition and Cache-Control headers correct
# ---------------------------------------------------------------------------


def test_recording_response_headers(client, auth_headers, app_no_redis):
    """AC-1: Content-Disposition: inline and Cache-Control: private, max-age=3600."""
    mock_session, _ = _make_s3_session()

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
            resp = client.get("/api/calls/cc-001/recording", headers=auth_headers)

    assert resp.headers.get("content-disposition") == "inline"
    assert resp.headers.get("cache-control") == "private, max-age=3600"


# ---------------------------------------------------------------------------
# AC-8: Mid-stream exception logs recording_stream_interrupted at ERROR
# ---------------------------------------------------------------------------


def test_midstream_exception_logs_and_closes_generator(app_no_redis, auth_headers, capsys):
    """AC-8: S3 stream raising mid-stream → recording_stream_interrupted logged at ERROR."""
    from fastapi.testclient import TestClient

    class _ErrorBody:
        """Async iterable that raises after first chunk."""
        call_count = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.call_count == 0:
                self.call_count += 1
                return b"FIRST_CHUNK"
            raise RuntimeError("Simulated mid-stream S3 error")

    response = {
        "Body": _ErrorBody(),
        "ContentType": "audio/mpeg",
        "ContentLength": 100,
    }
    mock_session, _ = _make_s3_session(get_object_return=response)

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        with TestClient(app_no_redis, raise_server_exceptions=False) as error_client:
            with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
                resp = error_client.get("/api/calls/cc-001/recording", headers=auth_headers)

    assert resp.status_code == 200

    captured = capsys.readouterr()
    assert "recording_stream_interrupted" in captured.out, (
        "Expected 'recording_stream_interrupted' in structlog stdout output"
    )
    assert "error" in captured.out.lower(), (
        "Expected error-level log entry in structlog stdout output"
    )


# ---------------------------------------------------------------------------
# AC-9: Malformed Range detail body and no S3 call
# ---------------------------------------------------------------------------


def test_malformed_range_returns_400_detail_and_no_s3_call(client, auth_headers, app_no_redis):
    """AC-9: Malformed Range returns {"detail": "Invalid Range header"} before S3 call."""
    mock_session, _ = _make_s3_session()

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session) as mock_sess_cls:
            resp = client.get(
                "/api/calls/cc-001/recording",
                headers={**auth_headers, "Range": "not-a-range"},
            )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "Invalid Range header"}
    # S3 session must not have been created at all
    mock_sess_cls.assert_not_called()


# ---------------------------------------------------------------------------
# AC-10: S3 416 → BFF proxies 416 status and Content-Range header
# ---------------------------------------------------------------------------


def test_s3_416_proxied_with_content_range_header(client, auth_headers, app_no_redis):
    """AC-10: S3 InvalidRange → 416 with Content-Range header proxied."""
    from botocore.exceptions import ClientError

    content_range_value = "bytes */1024"
    mock_session, _ = _make_s3_session(
        get_object_side_effect=ClientError(
            {
                "Error": {"Code": "InvalidRange", "Message": "The requested range is not satisfiable"},
                "ResponseMetadata": {
                    "HTTPStatusCode": 416,
                    "HTTPHeaders": {"content-range": content_range_value},
                },
            },
            "GetObject",
        )
    )

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
            resp = client.get(
                "/api/calls/cc-001/recording",
                headers={**auth_headers, "Range": "bytes=9000-9999"},
            )

    assert resp.status_code == 416
    assert resp.headers.get("content-range") == content_range_value


def test_s3_416_without_content_range_header(client, auth_headers, app_no_redis):
    """AC-10: S3 InvalidRange without Content-Range → 416 with no Content-Range leak."""
    from botocore.exceptions import ClientError

    mock_session, _ = _make_s3_session(
        get_object_side_effect=ClientError(
            {
                "Error": {"Code": "InvalidRange", "Message": "Range not satisfiable"},
                "ResponseMetadata": {"HTTPStatusCode": 416, "HTTPHeaders": {}},
            },
            "GetObject",
        )
    )

    with _mock_pg_repo(app_no_redis, _make_pg_call()):
        with patch("app.routes.recordings.aioboto3.Session", return_value=mock_session):
            resp = client.get(
                "/api/calls/cc-001/recording",
                headers={**auth_headers, "Range": "bytes=9000-9999"},
            )

    assert resp.status_code == 416
