"""Tests for TenantConfigRepository — story 002-005.

TDD: tests written before implementation.
AC1: all 3 tests pass after implementation.
AC2: upsert_config is idempotent (ON CONFLICT DO UPDATE).
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ
    and os.environ.get("CI") != "true",
    reason="Integration tests require DATABASE_URL env var or CI=true",
)


async def test_get_config_returns_none_for_missing_tenant(db_session):
    """get_config for non-existent tenant → None."""
    from app.db.repositories.tenant_config import SQLAlchemyTenantConfigRepository

    repo = SQLAlchemyTenantConfigRepository(db_session)
    result = await repo.get_config(tenant_slug="ghost", env="dev")

    assert result is None


async def test_upsert_config_creates_and_returns(db_session):
    """upsert_config new row → returned object has matching fields."""
    from app.db.repositories.tenant_config import SQLAlchemyTenantConfigRepository

    repo = SQLAlchemyTenantConfigRepository(db_session)
    result = await repo.upsert_config(
        tenant_slug="acme",
        env="dev",
        config={"greeting": "hello"},
    )

    assert result is not None
    assert result.tenant_slug == "acme"
    assert result.env == "dev"
    assert result.config == {"greeting": "hello"}
    assert result.version == 1


async def test_upsert_config_updates_existing(db_session):
    """upsert_config twice → second call updates config, increments version, one row only."""
    from app.db.repositories.tenant_config import SQLAlchemyTenantConfigRepository
    from sqlalchemy import text

    repo = SQLAlchemyTenantConfigRepository(db_session)

    await repo.upsert_config(tenant_slug="acme", env="dev", config={"v": 1})
    result = await repo.upsert_config(tenant_slug="acme", env="dev", config={"v": 2})

    # Version incremented
    assert result.config == {"v": 2}
    assert result.version == 2

    # Only one row in table
    count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM tenant_config "
                "WHERE tenant_slug='acme' AND env='dev'"
            )
        )
    ).scalar_one()
    assert count == 1
