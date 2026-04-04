"""Tests for BillingRepository — story 002-005.

TDD: tests written before implementation.
AC1: all 3 tests pass after implementation.
AC3: upsert_billing is idempotent (ON CONFLICT DO UPDATE).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ
    and os.environ.get("CI") != "true",
    reason="Integration tests require DATABASE_URL env var or CI=true",
)


def _billing_kwargs(tenant_slug: str = "acme", env: str = "dev", plan: str = "trial") -> dict:
    return {
        "tenant_slug": tenant_slug,
        "env": env,
        "plan": plan,
        "trial_start": datetime.now(timezone.utc),
        "trial_days": 14,
        "activation_status": "none",
        "product": "voice",
    }


async def test_get_billing_returns_none_for_missing_tenant(db_session):
    """get_billing for non-existent tenant → None."""
    from app.db.repositories.billing import SQLAlchemyBillingRepository

    repo = SQLAlchemyBillingRepository(db_session)
    result = await repo.get_billing(tenant_slug="ghost", env="dev")

    assert result is None


async def test_upsert_billing_creates_and_returns(db_session):
    """upsert_billing new row → returned object has matching tenant_slug, env, plan."""
    from app.db.repositories.billing import SQLAlchemyBillingRepository
    from app.db.models import BillingUsage

    repo = SQLAlchemyBillingRepository(db_session)
    row = BillingUsage(**_billing_kwargs())
    result = await repo.upsert_billing(row)

    assert result is not None
    assert result.tenant_slug == "acme"
    assert result.env == "dev"
    assert result.plan == "trial"


async def test_upsert_billing_updates_existing(db_session):
    """upsert_billing twice with different plan → updated row, no UNIQUE violation, one row only."""
    from app.db.repositories.billing import SQLAlchemyBillingRepository
    from app.db.models import BillingUsage
    from sqlalchemy import text

    repo = SQLAlchemyBillingRepository(db_session)

    row1 = BillingUsage(**_billing_kwargs(plan="trial"))
    await repo.upsert_billing(row1)

    row2 = BillingUsage(**_billing_kwargs(plan="paid"))
    result = await repo.upsert_billing(row2)

    assert result.plan == "paid"

    # Only one row in table
    count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM billing_usage "
                "WHERE tenant_slug='acme' AND env='dev'"
            )
        )
    ).scalar_one()
    assert count == 1
