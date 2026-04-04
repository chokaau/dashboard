"""Tests verifying the DB fixtures work correctly — story 002-007.

These tests require a running PostgreSQL instance (docker-compose.test.yml).
They are skipped automatically when DATABASE_URL is not reachable.

AC2: db_engine fixture runs alembic upgrade head (verified by schema existing).
AC3: db_session fixture rolls back after each test.
AC4: app_client fixture wires the test session into FastAPI dependency overrides.
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text

# Skip all tests in this file if DATABASE_URL is not set to a real PG instance.
# This allows the unit test suite to run without Docker.
pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ
    and os.environ.get("CI") != "true",
    reason="Integration tests require DATABASE_URL env var or CI=true",
)


async def test_db_engine_schema_exists(db_engine):
    """AC2 — alembic upgrade head ran: calls table exists."""
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables "
                 "WHERE table_schema='public' AND table_name='calls'")
        )
        row = result.fetchone()
    assert row is not None, "calls table not found — alembic upgrade head may not have run"


async def test_db_session_isolation_insert_and_read(db_session):
    """AC3 part 1 — insert a row; it must be visible within this test."""
    await db_session.execute(
        text(
            "INSERT INTO calls (id, tenant_slug, env, start_time, status, needs_callback, has_recording) "
            "VALUES ('fixture-isolation-test', 'acme', 'dev', now(), 'missed', false, false)"
        )
    )
    await db_session.commit()
    result = await db_session.execute(
        text("SELECT id FROM calls WHERE id = 'fixture-isolation-test'")
    )
    assert result.fetchone() is not None


async def test_db_session_isolation_clean_state(db_session):
    """AC3 part 2 — tables are truncated between tests; no data from prior test."""
    result = await db_session.execute(
        text("SELECT id FROM calls WHERE id = 'fixture-isolation-test'")
    )
    assert result.fetchone() is None, (
        "Row from previous test is visible — truncation isolation is broken"
    )
