"""Tests for MaintenanceModeMiddleware — story-3-1."""

import pytest
from unittest.mock import patch
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


@pytest.fixture()
def maintenance_on_client():
    config = _make_config(True)
    with patch("app.main.get_config", return_value=config):
        app = create_app()

        router = APIRouter()

        @router.get("/api/test")
        async def _test_route():
            return {"ok": True}

        app.include_router(router)
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture()
def maintenance_off_client():
    config = _make_config(False)
    with patch("app.main.get_config", return_value=config):
        app = create_app()

        router = APIRouter()

        @router.get("/api/test")
        async def _test_route():
            return {"ok": True}

        app.include_router(router)
        with TestClient(app, raise_server_exceptions=False) as c:
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
