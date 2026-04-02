"""Tests for RateLimitMiddleware — story-3-1."""

import pytest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.main import create_app
from tests.conftest import mint_jwt, TEST_POOL_ID, TEST_CLIENT_ID, TEST_REGION, _PUBLIC_KEY_PEM

_RATE_CONFIG = AppConfig(
    cognito_user_pool_id=TEST_POOL_ID,
    cognito_client_id=TEST_CLIENT_ID,
    aws_region=TEST_REGION,
    redis_url="",  # Disable auto-connect in lifespan; we inject mock directly
    env_short="test",
    rate_limit_read_per_minute=5,
    rate_limit_write_per_minute=2,
)


def _redis_mock_with_count(count: int) -> MagicMock:
    """Return a mock Redis client whose pipeline returns a given request count."""
    pipe = MagicMock()
    pipe.zadd = MagicMock()
    pipe.zremrangebyscore = MagicMock()
    pipe.zcard = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[1, 0, count, True])

    redis = MagicMock()
    redis.pipeline = MagicMock(return_value=pipe)
    # aclose() is called in lifespan shutdown — must be awaitable
    redis.aclose = AsyncMock()
    return redis


async def _mock_get_keys(_self, *args, **kwargs):
    return [_PUBLIC_KEY_PEM]


@contextmanager
def _rate_client(redis_mock=None, route_path: str = "/api/ping"):
    """Context manager yielding a TestClient with config + JWKS patches active.

    redis_url="" in config prevents lifespan auto-connect. After lifespan runs,
    we inject the mock directly onto app.state so the middleware sees it.
    """
    app = create_app()

    router = APIRouter()

    @router.get(route_path)
    async def _handler(request: Request):  # noqa: ARG001
        return {"ok": True}

    app.include_router(router)

    with (
        patch("app.main.get_config", return_value=_RATE_CONFIG),
        patch("app.middleware.auth.JWKSCache.get_keys", _mock_get_keys),
        TestClient(app, raise_server_exceptions=False) as c,
    ):
        # Lifespan has run — now inject mock redis (overrides the None set by lifespan)
        if redis_mock is not None:
            c.app.state.redis = redis_mock
        yield c


def test_rate_limit_health_skipped() -> None:
    """Health endpoint always skips rate limiting."""
    redis = _redis_mock_with_count(999)
    with _rate_client(redis_mock=redis) as c:
        resp = c.get("/health")
    assert resp.status_code == 200


def test_rate_limit_fails_open_when_redis_none() -> None:
    """When Redis is None, rate limiter must not block the request."""
    with _rate_client(redis_mock=None) as c:
        token = mint_jwt()
        resp = c.get("/api/ping", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_rate_limit_passes_when_under_limit() -> None:
    redis = _redis_mock_with_count(3)  # limit is 5
    with _rate_client(redis_mock=redis) as c:
        token = mint_jwt()
        resp = c.get("/api/ping", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_rate_limit_returns_429_when_over_limit() -> None:
    redis = _redis_mock_with_count(10)  # limit is 5
    with _rate_client(redis_mock=redis, route_path="/api/over") as c:
        token = mint_jwt()
        resp = c.get("/api/over", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 429


def test_rate_limit_429_includes_retry_after() -> None:
    redis = _redis_mock_with_count(10)
    with _rate_client(redis_mock=redis, route_path="/api/retry") as c:
        token = mint_jwt()
        resp = c.get("/api/retry", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 429
    assert "retry-after" in resp.headers
