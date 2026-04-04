"""conftest for integration tests — re-exposes DB fixtures from tests/db/conftest.

pytest_plugins cannot be used in non-top-level conftest files (pytest restriction).
Instead, the DB fixtures are duplicated here. The fixtures themselves live in
tests/db/conftest.py (canonical location for DB tests); this file makes them
available to tests/integration/ tests.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/voicebff_test",
)


@pytest.fixture(scope="session")
def _run_migrations():
    """Run alembic upgrade head once per test session (sync, session-scoped)."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
    )


@pytest_asyncio.fixture
async def db_engine(_run_migrations):
    """Function-scoped async engine — each test gets its own engine."""
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Function-scoped session with table truncation after each test."""
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
        async with db_engine.connect() as conn:
            await conn.execute(
                sa_text(
                    "TRUNCATE TABLE calls, tenant_config, billing_usage "
                    "RESTART IDENTITY CASCADE"
                )
            )
            await conn.commit()


@pytest_asyncio.fixture
async def integration_client(db_session):
    """AsyncClient with JWT auth patched for integration tests.

    - Patches JWKSCache.get_keys to return the test public key.
    - Patches get_config to return a test AppConfig (env_short="dev").
    - Overrides get_db_session with the test db_session.

    Tests can mint JWTs via client.mint_jwt() for any tenant_slug.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    # Import test JWT helpers from the root conftest
    tests_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)

    from conftest import (
        _PUBLIC_KEY_PEM,
        TEST_POOL_ID,
        TEST_CLIENT_ID,
        TEST_REGION,
        mint_jwt,
    )
    from app.config import AppConfig
    from app.dependencies.database import get_db_session
    from app.main import create_app

    test_config = AppConfig(
        cognito_user_pool_id=TEST_POOL_ID,
        cognito_client_id=TEST_CLIENT_ID,
        aws_region=TEST_REGION,
        redis_url="",
        maintenance_mode=False,
        env_short="dev",
        cors_origins=["https://app.choka.dev"],
        cloudfront_origin_secret="",
    )

    async def _mock_get_keys(_self_or_url, *args, **kwargs):
        return [_PUBLIC_KEY_PEM]

    with (
        patch("app.middleware.auth.JWKSCache.get_keys", _mock_get_keys),
        patch("app.main.get_config", return_value=test_config),
    ):
        app = create_app()
        app.state.config = test_config
        app.state.redis = None

        async def override_get_db_session():
            yield db_session

        app.dependency_overrides[get_db_session] = override_get_db_session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            client.mint_jwt = mint_jwt  # type: ignore[attr-defined]
            client.app = app  # type: ignore[attr-defined]  # expose for state mutation in tests
            yield client
