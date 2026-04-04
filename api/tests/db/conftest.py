"""Shared async DB fixtures for integration tests — story 002-007.

Isolation pattern: each test runs against a fresh function-scoped engine.
After the test, all three tables are truncated so no data persists between
tests. Tables never need schema-level resetting because alembic upgrade head
runs once per session before any tests execute.

Requires a running PostgreSQL 16 instance. Set DATABASE_URL env var or use
the default (matches docker-compose.test.yml):
  postgresql+asyncpg://test:test@localhost:5432/voicebff_test

Start services locally:
  docker compose -f dashboard/api/docker-compose.test.yml up -d
"""
from __future__ import annotations

import os
import subprocess

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/voicebff_test",
)


@pytest.fixture(scope="session")
def _run_migrations():
    """Session-scoped sync fixture. Runs alembic upgrade head once per test
    session. Sync (not async) so it has no event-loop dependency — it simply
    shells out to the alembic CLI.

    This ensures the schema is up to date before any DB test runs. Idempotent —
    safe to run on an already-migrated database.
    """
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
    )


@pytest_asyncio.fixture
async def db_engine(_run_migrations):
    """Function-scoped async engine. Each test gets its own engine so there is
    no cross-loop Future sharing between tests.
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Function-scoped session. Tables are truncated after each test for
    isolation.

    SQLAlchemy 2.0 + asyncpg pattern: yield a session per test, close it
    completely, then truncate tables via a fresh engine connection.
    This avoids asyncpg's "another operation in progress" error that occurs
    when attempting savepoint-based isolation within the same connection.

    Truncation is fast on the small test datasets used here (< 100 rows).
    """
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        # Close and return the session's connection to the pool before truncating
        await session.close()
        # Truncate via a separate connection on the same function-scoped engine
        async with db_engine.connect() as conn:
            await conn.execute(
                sa_text(
                    "TRUNCATE TABLE calls, tenant_config, billing_usage "
                    "RESTART IDENTITY CASCADE"
                )
            )
            await conn.commit()


@pytest_asyncio.fixture
async def app_client(db_session):
    """AsyncClient with FastAPI app wired to the test DB session.

    Overrides the get_db_session dependency so all route handlers in tests
    use the same transactional session that is rolled back at test end.
    """
    from httpx import ASGITransport, AsyncClient

    from app.dependencies.database import get_db_session
    from app.main import create_app

    app = create_app()

    async def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


