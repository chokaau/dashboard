"""Tests for GET /health endpoint — story-3-1, extended story-4-5."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.config import AppConfig
from tests.conftest import TEST_POOL_ID, TEST_CLIENT_ID, TEST_REGION


def _make_ok_redis() -> MagicMock:
    r = MagicMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


@pytest.fixture()
def health_client(monkeypatch) -> TestClient:
    """TestClient for health checks — patches get_config and JWKS so no real AWS calls."""
    test_cfg = AppConfig(
        cognito_user_pool_id=TEST_POOL_ID,
        cognito_client_id=TEST_CLIENT_ID,
        aws_region=TEST_REGION,
        redis_url="",
        env_short="test",
    )
    monkeypatch.setattr("app.main.get_config", lambda: test_cfg)

    app = create_app()
    app.state.config = test_cfg
    app.state.redis = _make_ok_redis()

    with TestClient(app, raise_server_exceptions=True) as c:
        # Overwrite redis set by lifespan (lifespan sees redis_url="" so leaves None)
        c.app.state.redis = _make_ok_redis()
        yield c


def test_health_returns_200(health_client: TestClient) -> None:
    with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
        with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
            resp = health_client.get("/health")
    assert resp.status_code == 200


def test_health_returns_ok_status(health_client: TestClient) -> None:
    with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
        with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
            body = health_client.get("/health").json()
    assert body["status"] == "ok"


def test_health_returns_service_name(health_client: TestClient) -> None:
    with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
        with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
            body = health_client.get("/health").json()
    assert body["service"] == "choka-dashboard-api"


def test_health_returns_version_field(health_client: TestClient) -> None:
    with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
        with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
            body = health_client.get("/health").json()
    assert "version" in body


def test_health_no_auth_required(health_client: TestClient) -> None:
    """Health must be unauthenticated — no Authorization header."""
    with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
        with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
            resp = health_client.get("/health")
    assert resp.status_code == 200


def test_health_in_maintenance_mode(health_client: TestClient, monkeypatch) -> None:
    """Health endpoint passes through even when maintenance mode is on."""
    maintenance_cfg = AppConfig(
        cognito_user_pool_id=TEST_POOL_ID,
        cognito_client_id=TEST_CLIENT_ID,
        aws_region=TEST_REGION,
        redis_url="",
        env_short="test",
        maintenance_mode=True,
    )
    health_client.app.state.config = maintenance_cfg
    health_client.app.state.redis = _make_ok_redis()
    with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
        with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
            resp = health_client.get("/health")
    assert resp.status_code == 200


def test_health_returns_dependencies_block(health_client: TestClient) -> None:
    """Response includes dependencies.redis/s3/cognito_jwks fields."""
    with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
        with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
            body = health_client.get("/health").json()
    deps = body["dependencies"]
    assert deps["redis"] == "ok"
    assert deps["s3"] == "ok"
    assert deps["cognito_jwks"] == "ok"
