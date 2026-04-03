"""Tests for extended health endpoint with dependency status (story-4-5).

TDD: RED tests written first.

Covers:
- Returns 200 with all dependencies ok
- Returns 503 when Redis is unreachable
- Returns 503 when S3 is unreachable
- Returns 503 when Cognito JWKS is unreachable
- Response includes 'version' field (GIT_SHA env var)
- /health exempt from auth middleware
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestHealthExtended:
    def test_health_all_ok(self, client: TestClient, app_no_redis) -> None:
        """All dependencies reachable → 200 with all ok."""
        fake_redis = MagicMock()
        fake_redis.ping = AsyncMock(return_value=True)
        fake_redis.aclose = AsyncMock()
        app_no_redis.state.redis = fake_redis

        with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
            with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
                response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "choka-dashboard-api"
        assert data["dependencies"]["redis"] == "ok"
        assert data["dependencies"]["s3"] == "ok"
        assert data["dependencies"]["cognito_jwks"] == "ok"

    def test_health_redis_unavailable_returns_503(
        self, client: TestClient, app_no_redis
    ) -> None:
        """Redis ping fails → 503 with redis=unavailable."""
        fake_redis = MagicMock()
        fake_redis.ping = AsyncMock(side_effect=ConnectionError("Redis down"))
        fake_redis.aclose = AsyncMock()
        app_no_redis.state.redis = fake_redis

        with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
            with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
                response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["dependencies"]["redis"] == "unavailable"

    def test_health_no_redis_client_returns_unavailable(
        self, client: TestClient, app_no_redis
    ) -> None:
        """No Redis client configured → redis=unavailable."""
        app_no_redis.state.redis = None

        with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
            with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
                response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["dependencies"]["redis"] == "unavailable"

    def test_health_s3_unavailable_returns_503(
        self, client: TestClient, app_no_redis
    ) -> None:
        """S3 check fails → 503 with s3=unavailable."""
        fake_redis = MagicMock()
        fake_redis.ping = AsyncMock(return_value=True)
        fake_redis.aclose = AsyncMock()
        app_no_redis.state.redis = fake_redis

        with patch("app.routes.health._check_s3", AsyncMock(return_value="unavailable")):
            with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
                response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["dependencies"]["s3"] == "unavailable"

    def test_health_jwks_unavailable_returns_503(
        self, client: TestClient, app_no_redis
    ) -> None:
        """JWKS check fails → 503 with cognito_jwks=unavailable."""
        fake_redis = MagicMock()
        fake_redis.ping = AsyncMock(return_value=True)
        fake_redis.aclose = AsyncMock()
        app_no_redis.state.redis = fake_redis

        with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
            with patch("app.routes.health._check_jwks", AsyncMock(return_value="unavailable")):
                response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["dependencies"]["cognito_jwks"] == "unavailable"

    def test_health_returns_version_from_env(
        self, client: TestClient, app_no_redis
    ) -> None:
        """GIT_SHA env var appears in version field."""
        fake_redis = MagicMock()
        fake_redis.ping = AsyncMock(return_value=True)
        fake_redis.aclose = AsyncMock()
        app_no_redis.state.redis = fake_redis

        with patch.dict(os.environ, {"GIT_SHA": "abc123def456"}):
            with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
                with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
                    response = client.get("/health")

        data = response.json()
        assert data["version"] == "abc123def456"

    def test_health_no_auth_required(self, client: TestClient, app_no_redis) -> None:
        """Health endpoint returns 200 without Authorization header."""
        app_no_redis.state.redis = None
        with patch("app.routes.health._check_s3", AsyncMock(return_value="ok")):
            with patch("app.routes.health._check_jwks", AsyncMock(return_value="ok")):
                response = client.get("/health")
        # Should not return 401
        assert response.status_code != 401
