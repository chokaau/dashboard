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
from unittest.mock import AsyncMock, MagicMock, patch

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
    """Build app with /api/protected route.

    Note: create_app() already includes the real /api/events SSE route from
    events.router. We do NOT re-register /api/events here — it would be
    unreachable anyway (first match wins) and registering a streaming handler
    a second time does nothing useful.

    The SSE ?token= acceptance test calls the real /api/events route, which is
    the correct behavior. The real events route returns a StreamingResponse;
    TestClient consumes the first chunk (status line + headers) without blocking
    because we patch the generator to yield one frame then stop.
    """
    app = create_app()

    router = APIRouter()

    @router.get("/api/protected")
    async def _protected():
        return {"ok": True}

    app.include_router(router)
    return app


async def _stub_event_generator(request, tenant_slug, env_short, **kwargs):
    """One-shot SSE generator — yields a single ping and stops.

    Replaces the real infinite SSE generator in tests so that TestClient
    receives the full response immediately without hanging.
    """
    yield "event: ping\ndata: 1\n\n"


@contextmanager
def _client(jwks=_good_jwks):
    """Context manager: app + TestClient with given JWKS mock and config patch.

    Also patches:
    - app.routes.health._check_jwks / _check_s3 — prevents real outbound HTTP
      calls (test pool URL would return 503).
    - app.routes.events._event_generator — replaces the infinite SSE stream
      with a one-shot stub so TestClient is not blocked waiting for body end.
    """
    with (
        patch("app.main.get_config", return_value=_TEST_CONFIG),
        patch("app.middleware.auth.JWKSCache.get_keys", jwks),
        patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")),
        patch("app.routes.health._check_s3", AsyncMock(return_value="ok")),
        patch("app.routes.events._event_generator", _stub_event_generator),
        TestClient(_build_app(), raise_server_exceptions=False) as c,
    ):
        # Inject a minimal redis mock so /health redis ping succeeds
        r = MagicMock()
        r.ping = AsyncMock(return_value=True)
        r.aclose = AsyncMock()
        c.app.state.redis = r
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


# ---------------------------------------------------------------------------
# JWKSCache unit tests — exercise the real get_keys() implementation
# (lines 43-67 in auth.py) so auth.py reaches 100% line coverage.
# ---------------------------------------------------------------------------


_TEST_JWKS_URL = (
    f"https://cognito-idp.{TEST_REGION}.amazonaws.com"
    f"/{TEST_POOL_ID}/.well-known/jwks.json"
)
_FAKE_KEYS = [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": "k1"}]


@pytest.mark.asyncio
async def test_jwks_cache_fetches_keys_on_first_call() -> None:
    """get_keys() fetches from the URL when cache is empty."""
    import respx
    import httpx
    from app.middleware.auth import JWKSCache

    cache = JWKSCache()
    with respx.mock:
        respx.get(_TEST_JWKS_URL).mock(
            return_value=httpx.Response(200, json={"keys": _FAKE_KEYS})
        )
        keys = await cache.get_keys(_TEST_JWKS_URL)

    assert keys == _FAKE_KEYS


@pytest.mark.asyncio
async def test_jwks_cache_returns_cached_keys_without_refetch() -> None:
    """get_keys() returns cached result on the second call (no second HTTP request)."""
    import respx
    import httpx
    from app.middleware.auth import JWKSCache

    cache = JWKSCache()
    with respx.mock:
        route = respx.get(_TEST_JWKS_URL).mock(
            return_value=httpx.Response(200, json={"keys": _FAKE_KEYS})
        )
        await cache.get_keys(_TEST_JWKS_URL)
        keys = await cache.get_keys(_TEST_JWKS_URL)

    # Only one HTTP call should have been made
    assert route.call_count == 1
    assert keys == _FAKE_KEYS


@pytest.mark.asyncio
async def test_jwks_cache_raises_when_fetch_fails_and_no_cached_keys() -> None:
    """get_keys() propagates the exception when the fetch fails with no cache."""
    import respx
    import httpx
    from app.middleware.auth import JWKSCache

    cache = JWKSCache()
    with respx.mock:
        respx.get(_TEST_JWKS_URL).mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(Exception):
            await cache.get_keys(_TEST_JWKS_URL)


@pytest.mark.asyncio
async def test_jwks_cache_double_checked_lock_early_return() -> None:
    """get_keys() re-checks inside the lock and returns early when another
    coroutine already populated fresh keys (double-checked locking — line 51).

    We control time.monotonic in auth's module namespace so that:
      - Call 1 (outer fast-path, line 43): returns a large value so
        (now - _fetched_at=0) > TTL → outer check misses → acquires lock.
      - Call 2 (inner re-check, line 49): returns 0.0 so
        (0.0 - _fetched_at=0.0) = 0 < TTL → inner check passes → line 51.
    """
    import time as _time
    from app.middleware.auth import JWKSCache, _JWKS_TTL

    cache = JWKSCache()
    cache._keys = _FAKE_KEYS
    cache._fetched_at = 0.0  # stale epoch

    call_count = 0

    def _controlled_monotonic():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Outer fast-path: return a value far beyond TTL so check misses
            return float(_JWKS_TTL + 9999)
        # Inner re-check: return 0.0 so (0.0 - 0.0) = 0 < TTL → early return
        return 0.0

    with patch("app.middleware.auth.time.monotonic", _controlled_monotonic):
        keys = await cache.get_keys(_TEST_JWKS_URL)

    assert keys == _FAKE_KEYS


@pytest.mark.asyncio
async def test_jwks_cache_returns_stale_keys_when_refresh_fails() -> None:
    """get_keys() returns stale cached keys (fail-open) when refresh fails."""
    import time
    import respx
    import httpx
    from app.middleware.auth import JWKSCache, _JWKS_TTL

    cache = JWKSCache()
    # Pre-seed the cache with stale keys (fetched_at forced into the past)
    cache._keys = _FAKE_KEYS
    cache._fetched_at = time.monotonic() - (_JWKS_TTL + 1)

    with respx.mock:
        respx.get(_TEST_JWKS_URL).mock(return_value=httpx.Response(503))
        keys = await cache.get_keys(_TEST_JWKS_URL)

    # Should get the stale cached keys back, not raise
    assert keys == _FAKE_KEYS


# ---------------------------------------------------------------------------
# AC6 — singleflight: 10 concurrent requests with expired cache → 1 JWKS fetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwks_cache_singleflight_10_concurrent_one_fetch() -> None:
    """10 concurrent get_keys() calls with an expired cache trigger exactly 1
    HTTP fetch (singleflight via asyncio.Lock — AC6)."""
    import asyncio
    import respx
    import httpx
    from app.middleware.auth import JWKSCache, _JWKS_TTL
    import time

    cache = JWKSCache()
    # Force cache to appear expired
    cache._fetched_at = time.monotonic() - (_JWKS_TTL + 1)

    with respx.mock:
        route = respx.get(_TEST_JWKS_URL).mock(
            return_value=httpx.Response(200, json={"keys": _FAKE_KEYS})
        )
        results = await asyncio.gather(
            *[cache.get_keys(_TEST_JWKS_URL) for _ in range(10)]
        )

    # All 10 callers should receive the correct keys
    assert all(r == _FAKE_KEYS for r in results)
    # The HTTP endpoint was called exactly once (singleflight)
    assert route.call_count == 1
