"""Tests for JWTAuthMiddleware — story-3-2.

Covers:
  - Valid token → 200
  - Missing Authorization → 401
  - Expired token → 401
  - Wrong issuer → 401
  - Wrong audience → 401
  - Malformed token → 401
  - JWKS unreachable with no cache → 503
  - SSE ?token= accepted on /events path
  - SSE ?token= rejected on non-events path
  - /health bypasses JWT entirely
  - Valid claims stored on request.state.jwt_claims
"""

import time
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.main import create_app
from tests.conftest import (
    TEST_CLIENT_ID,
    TEST_ISS,
    TEST_POOL_ID,
    TEST_REGION,
    _PUBLIC_KEY_PEM,
    mint_jwt,
)

_TEST_CONFIG = AppConfig(
    cognito_user_pool_id=TEST_POOL_ID,
    cognito_client_id=TEST_CLIENT_ID,
    aws_region=TEST_REGION,
    redis_url="",
    env_short="test",
)


# ---------------------------------------------------------------------------
# JWKS mock helpers
# ---------------------------------------------------------------------------


async def _good_jwks(_self, *args, **kwargs):
    return [_PUBLIC_KEY_PEM]


async def _bad_jwks(_self, *args, **kwargs):
    raise RuntimeError("JWKS unreachable")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _build_app() -> object:
    """Build app with /api/protected and /api/events routes."""
    app = create_app()

    router = APIRouter()

    @router.get("/api/protected")
    async def _protected():
        return {"ok": True}

    @router.get("/api/events")
    async def _events():
        return {"stream": True}

    app.include_router(router)
    return app


@contextmanager
def _client(jwks=_good_jwks):
    """Context manager: app + TestClient with given JWKS mock and config patch."""
    with (
        patch("app.main.get_config", return_value=_TEST_CONFIG),
        patch("app.middleware.auth.JWKSCache.get_keys", jwks),
        TestClient(_build_app(), raise_server_exceptions=False) as c,
    ):
        yield c


# ---------------------------------------------------------------------------
# Parameterized JWT matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token_factory, expected_status",
    [
        (lambda: mint_jwt(), 200),
        (lambda: mint_jwt(exp_offset=-10), 401),
        (lambda: mint_jwt(iss="https://wrong-idp.example.com/bad-pool"), 401),
        (lambda: mint_jwt(aud="wrong-client-id"), 401),
        (lambda: "not.a.valid.jwt.token", 401),
    ],
    ids=["valid", "expired", "wrong_iss", "wrong_aud", "malformed"],
)
def test_jwt_matrix(token_factory, expected_status) -> None:
    token = token_factory()
    with _client() as c:
        resp = c.get("/api/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == expected_status


def test_missing_authorization_header() -> None:
    with _client() as c:
        resp = c.get("/api/protected")
    assert resp.status_code == 401


def test_missing_auth_detail_message() -> None:
    with _client() as c:
        body = c.get("/api/protected").json()
    assert "authorization" in body["detail"].lower() or "missing" in body["detail"].lower()


# ---------------------------------------------------------------------------
# JWKS unavailable
# ---------------------------------------------------------------------------


def test_jwks_unreachable_no_cache_returns_503() -> None:
    token = mint_jwt()
    with _client(jwks=_bad_jwks) as c:
        resp = c.get("/api/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# SSE ?token= path
# ---------------------------------------------------------------------------


def test_sse_token_param_accepted_on_events_path() -> None:
    token = mint_jwt()
    with _client() as c:
        resp = c.get(f"/api/events?token={token}")
    assert resp.status_code == 200


def test_sse_token_param_rejected_on_non_events_path() -> None:
    token = mint_jwt()
    with _client() as c:
        resp = c.get(f"/api/protected?token={token}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Health bypass
# ---------------------------------------------------------------------------


def test_health_bypasses_jwt_entirely() -> None:
    call_count = 0

    async def _counting_jwks(_self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return [_PUBLIC_KEY_PEM]

    with _client(jwks=_counting_jwks) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
    assert call_count == 0


# ---------------------------------------------------------------------------
# Claims stored on request.state
# ---------------------------------------------------------------------------


def test_valid_jwt_claims_stored_on_request_state() -> None:
    captured: dict = {}

    with (
        patch("app.main.get_config", return_value=_TEST_CONFIG),
        patch("app.middleware.auth.JWKSCache.get_keys", _good_jwks),
    ):
        app = _build_app()

        @app.get("/api/claims-check")
        async def _claims_check(request: Request):
            captured["claims"] = getattr(request.state, "jwt_claims", None)
            return {"ok": True}

        token = mint_jwt(sub="uid-abc", tenant_slug="testco")
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/api/claims-check", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert captured["claims"] is not None
    assert captured["claims"]["sub"] == "uid-abc"
    assert captured["claims"]["custom:tenant_slug"] == "testco"
