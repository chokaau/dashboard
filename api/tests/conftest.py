"""Shared test fixtures for dashboard_api tests — story-3-1/3-2/3-3."""

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwt

from app.config import AppConfig
from app.main import create_app


# ---------------------------------------------------------------------------
# RSA key pair for signing test JWTs
# ---------------------------------------------------------------------------

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_PUBLIC_KEY_PEM = _PUBLIC_KEY.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

TEST_POOL_ID = "ap-southeast-2_TESTPOOL"
TEST_CLIENT_ID = "test-client-id"
TEST_REGION = "ap-southeast-2"
TEST_ISS = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_POOL_ID}"

# Minimal JWKS stub (jose accepts raw PEM for test decoding)
_MOCK_JWKS = [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": "test-key-1"}]


def mint_jwt(
    sub: str = "user-123",
    tenant_slug: str = "acme",
    tenant_id: str = "12345678-1234-4234-8234-123456789abc",
    role: str = "owner",
    email: str = "user@acme.com",
    exp_offset: int = 3600,
    iss: str | None = None,
    aud: str | None = None,
) -> str:
    """Mint a signed RS256 JWT with Cognito-style claims."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "iss": iss if iss is not None else TEST_ISS,
        "aud": aud if aud is not None else TEST_CLIENT_ID,
        "exp": now + exp_offset,
        "iat": now,
        "token_use": "id",
        "custom:tenant_slug": tenant_slug,
        "custom:tenant_id": tenant_id,
        "custom:role": role,
        "email": email,
    }
    private_pem = _PRIVATE_KEY.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(payload, private_pem, algorithm="RS256")


# ---------------------------------------------------------------------------
# App + client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_config() -> AppConfig:
    """Minimal config for unit tests — no real AWS/Redis."""
    return AppConfig(
        cognito_user_pool_id=TEST_POOL_ID,
        cognito_client_id=TEST_CLIENT_ID,
        aws_region=TEST_REGION,
        redis_url="",
        maintenance_mode=False,
        env_short="test",
        cors_origins=["https://app.choka.dev"],
        cloudfront_origin_secret="",
    )


@pytest.fixture()
def app_no_redis(test_config: AppConfig, monkeypatch):
    """Shared app instance — config injected, Redis set to None.

    Both this fixture and the `client` fixture share the SAME app object so
    that tests can inject a mock Redis onto app.state.redis and the client
    will see it during the request.

    get_config() is patched so the lifespan + create_app use test_config
    for JWT aud/iss validation (not the real env-var config).
    """

    async def _mock_get_keys(_self_or_url, *args, **kwargs):
        return [_PUBLIC_KEY_PEM]

    monkeypatch.setattr(
        "app.middleware.auth.JWKSCache.get_keys",
        _mock_get_keys,
    )
    monkeypatch.setattr("app.main.get_config", lambda: test_config)

    application = create_app()
    application.state.config = test_config
    application.state.redis = None
    return application


@pytest.fixture()
def client(app_no_redis) -> TestClient:
    """TestClient wrapping the shared app_no_redis instance.

    Uses app_no_redis (same object) so tests can mutate app.state.redis
    before requests and the client will pick up the change.
    """
    with TestClient(app_no_redis, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def valid_token() -> str:
    return mint_jwt()


@pytest.fixture()
def auth_headers(valid_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {valid_token}"}
