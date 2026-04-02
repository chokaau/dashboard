"""Tests for MaintenanceModeMiddleware — story-3-1."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.main import create_app
from tests.conftest import TEST_POOL_ID, TEST_CLIENT_ID, TEST_REGION


def _make_config(maintenance: bool) -> AppConfig:
    return AppConfig(
        cognito_user_pool_id=TEST_POOL_ID,
        cognito_client_id=TEST_CLIENT_ID,
        aws_region=TEST_REGION,
        redis_url="",
        env_short="test",
        maintenance_mode=maintenance,
    )


def _make_app_with_test_route(maintenance: bool):
    """Create app with a /api/test route and all health sub-checks stubbed."""
    config = _make_config(maintenance)
    app = create_app()

    router = APIRouter()

    @router.get("/api/test")
    async def _test_route():
        return {"ok": True}

    app.include_router(router)
    app.state.config = config

    # Inject a mock Redis so /health ping succeeds
    fake_redis = MagicMock()
    fake_redis.ping = AsyncMock(return_value=True)
    fake_redis.aclose = AsyncMock()
    app.state.redis = fake_redis

    return app, config


@pytest.fixture()
def maintenance_on_client():
    with (
        patch("app.main.get_config", return_value=_make_config(True)),
        patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")),
        patch("app.routes.health._check_s3", AsyncMock(return_value="ok")),
    ):
        app, config = _make_app_with_test_route(True)
        with TestClient(app, raise_server_exceptions=False) as c:
            c.app.state.redis = app.state.redis
            yield c


@pytest.fixture()
def maintenance_off_client():
    with (
        patch("app.main.get_config", return_value=_make_config(False)),
        patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")),
        patch("app.routes.health._check_s3", AsyncMock(return_value="ok")),
    ):
        app, config = _make_app_with_test_route(False)
        with TestClient(app, raise_server_exceptions=False) as c:
            c.app.state.redis = app.state.redis
            yield c


def test_maintenance_off_health_200(maintenance_off_client: TestClient) -> None:
    resp = maintenance_off_client.get("/health")
    assert resp.status_code == 200


def test_maintenance_on_returns_503_for_non_health(maintenance_on_client: TestClient) -> None:
    resp = maintenance_on_client.get("/api/test")
    assert resp.status_code == 503


def test_maintenance_on_detail_message(maintenance_on_client: TestClient) -> None:
    body = maintenance_on_client.get("/api/test").json()
    assert "maintenance" in body["detail"].lower()


def test_maintenance_on_health_still_200(maintenance_on_client: TestClient) -> None:
    resp = maintenance_on_client.get("/health")
    assert resp.status_code == 200


def test_maintenance_off_non_health_not_503(maintenance_off_client: TestClient) -> None:
    """When maintenance is off, non-health routes are not blocked by maintenance (may get 401 from JWT)."""
    resp = maintenance_off_client.get("/api/test")
    assert resp.status_code != 503
