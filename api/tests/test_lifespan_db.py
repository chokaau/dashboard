"""Tests for FastAPI lifespan DB wiring and exception handlers — story 002-006.

AC1: degraded mode when no DB env vars.
AC2: engine and session_factory set on app.state when DATABASE_URL provided.
AC3: engine disposed on shutdown.
AC4: DBPoolExhaustedError → 503 + Retry-After: 5.
AC5: DBConnectionError → lazy secret re-fetch + pool rebuild + 503.
AC6: no stack traces in error response bodies.
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter
from fastapi.testclient import TestClient
from jose import jwt

from app.config import AppConfig
from app.db.errors import (
    DBConnectionError,
    DBPoolExhaustedError,
    DBQueryError,
    DBStatementTimeoutError,
)
from app.main import create_app

# ---------------------------------------------------------------------------
# RSA key pair for signing test JWTs (same pattern as tests/conftest.py)
# ---------------------------------------------------------------------------

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY_PEM = _PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

TEST_POOL_ID = "ap-southeast-2_TESTPOOL"
TEST_CLIENT_ID = "test-client-id"
TEST_REGION = "ap-southeast-2"
TEST_ISS = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_POOL_ID}"


def _mint_jwt() -> str:
    now = int(time.time())
    private_pem = _PRIVATE_KEY.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(
        {
            "sub": "u1",
            "iss": TEST_ISS,
            "aud": TEST_CLIENT_ID,
            "exp": now + 3600,
            "iat": now,
            "token_use": "id",
            "custom:tenant_slug": "acme",
            "custom:tenant_id": "00000000-0000-4000-8000-000000000001",
            "custom:role": "owner",
            "email": "u@acme.com",
        },
        private_pem,
        algorithm="RS256",
    )


def _make_config(**overrides) -> AppConfig:
    base: dict[str, Any] = dict(
        cognito_user_pool_id=TEST_POOL_ID,
        cognito_client_id=TEST_CLIENT_ID,
        aws_region=TEST_REGION,
        redis_url="",
        maintenance_mode=False,
        env_short="test",
        cors_origins=["https://app.choka.dev"],
        cloudfront_origin_secret="",
        database_secret_arn="",
        database_url="",
    )
    base.update(overrides)
    return AppConfig(**base)


async def _mock_get_keys(_self, *args, **kwargs):
    return [_PUBLIC_KEY_PEM]


# ---------------------------------------------------------------------------
# AC1 — Degraded mode: no DB env vars → db_engine is None
# ---------------------------------------------------------------------------


def test_lifespan_degraded_mode_no_db_vars(monkeypatch):
    """AC1 — when no DB config, app.state.db_engine and db_session_factory are None."""
    config = _make_config()
    monkeypatch.setattr("app.main.get_config", lambda: config)
    monkeypatch.setattr("app.middleware.auth.JWKSCache.get_keys", _mock_get_keys)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False):
        assert app.state.db_engine is None
        assert app.state.db_session_factory is None


# ---------------------------------------------------------------------------
# AC2 — DB engine wired when database_url set
# ---------------------------------------------------------------------------


def test_lifespan_wires_db_engine_from_url(monkeypatch):
    """AC2 — database_url set → db_engine and db_session_factory on app.state."""
    config = _make_config(
        database_url="postgresql+asyncpg://test:test@localhost:5432/voicebff_test"
    )
    monkeypatch.setattr("app.main.get_config", lambda: config)
    monkeypatch.setattr("app.middleware.auth.JWKSCache.get_keys", _mock_get_keys)

    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    mock_engine.sync_engine = MagicMock()
    mock_session_factory = MagicMock()

    with (
        patch("app.main.create_db_engine", return_value=mock_engine) as mock_create,
        patch("app.main.create_session_factory", return_value=mock_session_factory),
    ):
        app = create_app()
        with TestClient(app, raise_server_exceptions=False):
            assert app.state.db_engine is mock_engine
            assert app.state.db_session_factory is mock_session_factory
        mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# AC3 — Engine disposed on shutdown
# ---------------------------------------------------------------------------


def test_lifespan_disposes_engine_on_shutdown(monkeypatch):
    """AC3 — lifespan exit calls engine.dispose()."""
    config = _make_config(
        database_url="postgresql+asyncpg://test:test@localhost:5432/voicebff_test"
    )
    monkeypatch.setattr("app.main.get_config", lambda: config)
    monkeypatch.setattr("app.middleware.auth.JWKSCache.get_keys", _mock_get_keys)

    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    mock_engine.sync_engine = MagicMock()

    with (
        patch("app.main.create_db_engine", return_value=mock_engine),
        patch("app.main.create_session_factory"),
    ):
        app = create_app()
        with TestClient(app, raise_server_exceptions=False):
            pass  # lifespan exits when TestClient context manager exits

    mock_engine.dispose.assert_awaited_once()


# ---------------------------------------------------------------------------
# AC4 — DBPoolExhaustedError → 503 + Retry-After: 5
# ---------------------------------------------------------------------------


def test_db_pool_exhausted_returns_503_with_retry_after(monkeypatch):
    """AC4 — DBPoolExhaustedError → 503 with Retry-After: 5 header."""
    config = _make_config()
    monkeypatch.setattr("app.main.get_config", lambda: config)
    monkeypatch.setattr("app.middleware.auth.JWKSCache.get_keys", _mock_get_keys)

    app = create_app()

    router = APIRouter()

    @router.get("/api/test/db-pool-error")
    async def _raise():
        raise DBPoolExhaustedError("pool full")

    app.include_router(router)

    token = _mint_jwt()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(
            "/api/test/db-pool-error",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 503
    assert resp.headers.get("retry-after") == "5"
    body = resp.json()
    assert body["error"]["code"] == "DB_POOL_EXHAUSTED"
    # AC6 — no stack trace in response body
    assert "traceback" not in str(body).lower()
    assert 'file "' not in str(body).lower()


# ---------------------------------------------------------------------------
# DBStatementTimeoutError → 503
# ---------------------------------------------------------------------------


def test_db_statement_timeout_returns_503(monkeypatch):
    """DBStatementTimeoutError → 503 with DB_STATEMENT_TIMEOUT code."""
    config = _make_config()
    monkeypatch.setattr("app.main.get_config", lambda: config)
    monkeypatch.setattr("app.middleware.auth.JWKSCache.get_keys", _mock_get_keys)

    app = create_app()
    router = APIRouter()

    @router.get("/api/test/db-timeout-error")
    async def _raise():
        raise DBStatementTimeoutError("timed out")

    app.include_router(router)

    token = _mint_jwt()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(
            "/api/test/db-timeout-error",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "DB_STATEMENT_TIMEOUT"
    assert "traceback" not in str(body).lower()


# ---------------------------------------------------------------------------
# DBQueryError → 503
# ---------------------------------------------------------------------------


def test_db_query_error_returns_503(monkeypatch):
    """DBQueryError → 503 with DB_QUERY_ERROR code."""
    config = _make_config()
    monkeypatch.setattr("app.main.get_config", lambda: config)
    monkeypatch.setattr("app.middleware.auth.JWKSCache.get_keys", _mock_get_keys)

    app = create_app()
    router = APIRouter()

    @router.get("/api/test/db-query-error")
    async def _raise():
        raise DBQueryError("bad query")

    app.include_router(router)

    token = _mint_jwt()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(
            "/api/test/db-query-error",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "DB_QUERY_ERROR"
    assert "traceback" not in str(body).lower()


# ---------------------------------------------------------------------------
# AC5 — DBConnectionError → lazy secret re-fetch + pool rebuild
# ---------------------------------------------------------------------------


def test_db_connection_error_triggers_pool_rebuild(monkeypatch):
    """AC5 — DBConnectionError with secret ARN → fetch_database_url called,
    new engine built, old engine disposed.
    """
    config = _make_config(
        database_url="postgresql+asyncpg://test:test@localhost:5432/voicebff_test"
    )
    monkeypatch.setattr("app.main.get_config", lambda: config)
    monkeypatch.setattr("app.middleware.auth.JWKSCache.get_keys", _mock_get_keys)

    original_engine = MagicMock()
    original_engine.dispose = AsyncMock()
    original_engine.sync_engine = MagicMock()
    new_engine = MagicMock()
    new_engine.dispose = AsyncMock()
    new_engine.sync_engine = MagicMock()

    call_count = {"n": 0}

    def _create_engine(url, **kwargs):
        call_count["n"] += 1
        return original_engine if call_count["n"] == 1 else new_engine

    mock_fetch = AsyncMock(
        return_value="postgresql+asyncpg://test:test@localhost:5432/voicebff_test"
    )

    router = APIRouter()

    @router.get("/api/test/db-conn-error")
    async def _raise():
        raise DBConnectionError("connection refused")

    token = _mint_jwt()

    with (
        patch("app.main.create_db_engine", side_effect=_create_engine),
        patch("app.main.create_session_factory"),
        patch("app.main.fetch_database_url", mock_fetch),
    ):
        app = create_app()
        app.include_router(router)

        with TestClient(app, raise_server_exceptions=False) as client:
            # Plant a secret ARN on app.state to trigger the re-fetch path
            app.state.db_secret_arn = (
                "arn:aws:secretsmanager:ap-southeast-2:123:secret:test"
            )
            resp = client.get(
                "/api/test/db-conn-error",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "DB_UNAVAILABLE"
    mock_fetch.assert_awaited_once_with(
        "arn:aws:secretsmanager:ap-southeast-2:123:secret:test"
    )
    original_engine.dispose.assert_awaited_once()
    assert "traceback" not in str(body).lower()
