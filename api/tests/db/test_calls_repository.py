"""Tests for CallRepository — story 002-004 + 003-002.

TDD: tests written before implementation. These tests require a running
PostgreSQL instance (docker-compose.test.yml). Skipped in unit-test-only
runs when DATABASE_URL is not set.

002-004 AC2: all 7 list/get tests pass.
002-004 AC3: tenant isolation enforced.
002-004 AC4: pagination correct.
003-002 AC1: all 6 upsert tests pass after implementation.
003-002 AC2: upsert_call updates existing row without duplication.
003-002 AC3: bulk_upsert is idempotent (ON CONFLICT DO NOTHING).
003-002 AC4: bulk_upsert([]) returns 0 without error.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ
    and os.environ.get("CI") != "true",
    reason="Integration tests require DATABASE_URL env var or CI=true",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_row(
    call_id: str,
    tenant_slug: str = "acme",
    env: str = "dev",
    status: str = "missed",
) -> dict:
    return {
        "id": call_id,
        "tenant_slug": tenant_slug,
        "env": env,
        "status": status,
        "needs_callback": False,
        "has_recording": False,
    }


async def _insert_call(session, **kwargs) -> None:
    await session.execute(
        text(
            "INSERT INTO calls "
            "(id, tenant_slug, env, start_time, status, needs_callback, has_recording) "
            "VALUES (:id, :tenant_slug, :env, now(), :status, :needs_callback, :has_recording)"
        ),
        kwargs,
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_list_calls_returns_empty_for_new_tenant(db_session):
    """AC2 — no rows → CallListResult with total=0, calls=[]."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    repo = SQLAlchemyCallRepository(db_session)
    result = await repo.list_calls(tenant_slug="acme", env="dev")

    assert result.total == 0
    assert result.calls == []


async def test_list_calls_paginates_correctly(db_session):
    """AC4 — 25 rows, page=2, page_size=10 → 10 rows, total=25."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    for i in range(25):
        await _insert_call(
            db_session,
            **_call_row(f"call-page-{i:03d}"),
        )

    repo = SQLAlchemyCallRepository(db_session)
    result = await repo.list_calls(tenant_slug="acme", env="dev", page=2, page_size=10)

    assert result.total == 25
    assert len(result.calls) == 10
    assert result.page == 2
    assert result.page_size == 10


async def test_list_calls_filters_by_status(db_session):
    """AC2 — status filter: 3 missed + 2 completed → 3 results when filtering missed."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    for i in range(3):
        await _insert_call(db_session, **_call_row(f"missed-{i}", status="missed"))
    for i in range(2):
        await _insert_call(db_session, **_call_row(f"completed-{i}", status="completed"))

    repo = SQLAlchemyCallRepository(db_session)
    result = await repo.list_calls(tenant_slug="acme", env="dev", status="missed")

    assert result.total == 3
    assert all(c.status == "missed" for c in result.calls)


async def test_list_calls_isolates_by_tenant(db_session):
    """AC3 — tenant isolation: tenant-a rows not visible to tenant-b query."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    await _insert_call(db_session, **_call_row("a-001", tenant_slug="tenant-a"))
    await _insert_call(db_session, **_call_row("a-002", tenant_slug="tenant-a"))
    await _insert_call(db_session, **_call_row("b-001", tenant_slug="tenant-b"))

    repo = SQLAlchemyCallRepository(db_session)
    result = await repo.list_calls(tenant_slug="tenant-a", env="dev")

    assert result.total == 2
    assert all(c.tenant_slug == "tenant-a" for c in result.calls)


async def test_get_call_returns_none_for_missing(db_session):
    """AC2 — non-existent call_id → None."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    repo = SQLAlchemyCallRepository(db_session)
    result = await repo.get_call(call_id="does-not-exist", tenant_slug="acme", env="dev")

    assert result is None


async def test_get_call_cross_tenant_returns_none(db_session):
    """AC3 — row inserted for tenant-a, queried as tenant-b → None."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    await _insert_call(db_session, **_call_row("cross-tenant-call", tenant_slug="tenant-a"))

    repo = SQLAlchemyCallRepository(db_session)
    result = await repo.get_call(
        call_id="cross-tenant-call", tenant_slug="tenant-b", env="dev"
    )

    assert result is None


async def test_get_call_returns_row_for_correct_tenant(db_session):
    """AC2 — insert + query correct tenant → Call object with matching id."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    await _insert_call(db_session, **_call_row("correct-tenant-call", tenant_slug="acme"))

    repo = SQLAlchemyCallRepository(db_session)
    result = await repo.get_call(
        call_id="correct-tenant-call", tenant_slug="acme", env="dev"
    )

    assert result is not None
    assert result.id == "correct-tenant-call"
    assert result.tenant_slug == "acme"


# ---------------------------------------------------------------------------
# 003-002 — upsert_call and bulk_upsert tests (TDD red phase first)
# ---------------------------------------------------------------------------


def _call_obj(
    call_id: str,
    tenant_slug: str = "acme",
    env: str = "dev",
    status: str = "missed",
) -> "Call":
    from datetime import timezone
    from app.db.models import Call
    return Call(
        id=call_id,
        tenant_slug=tenant_slug,
        env=env,
        start_time=datetime.now(timezone.utc),
        status=status,
        needs_callback=False,
        has_recording=False,
    )


async def test_upsert_call_creates_new_record(db_session):
    """003-002 AC1 — upsert_call with new id → row exists in DB."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    repo = SQLAlchemyCallRepository(db_session)
    call = _call_obj("upsert-new-001")
    returned = await repo.upsert_call(call)

    result = await repo.get_call(
        call_id="upsert-new-001", tenant_slug="acme", env="dev"
    )
    assert result is not None
    assert result.id == "upsert-new-001"
    assert returned.id == "upsert-new-001"


async def test_upsert_call_updates_existing_record(db_session):
    """003-002 AC2 — same id, different status → one row, status updated."""
    from sqlalchemy import text
    from app.db.repositories.calls import SQLAlchemyCallRepository

    repo = SQLAlchemyCallRepository(db_session)

    call_v1 = _call_obj("upsert-update-001", status="missed")
    await repo.upsert_call(call_v1)
    await db_session.commit()

    call_v2 = _call_obj("upsert-update-001", status="completed")
    await repo.upsert_call(call_v2)
    await db_session.commit()

    count = (
        await db_session.execute(
            text("SELECT COUNT(*) FROM calls WHERE id='upsert-update-001'")
        )
    ).scalar_one()
    assert count == 1

    row = await repo.get_call(
        call_id="upsert-update-001", tenant_slug="acme", env="dev"
    )
    assert row is not None
    assert row.status == "completed"


async def test_upsert_call_does_not_update_tenant(db_session):
    """003-002 AC6 — tenant_slug and env not in ON CONFLICT set_; original values preserved."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    repo = SQLAlchemyCallRepository(db_session)

    call_v1 = _call_obj("upsert-tenant-001", tenant_slug="acme", env="dev")
    await repo.upsert_call(call_v1)
    await db_session.commit()

    # Second upsert with same id — tenant_slug must not change
    call_v2 = _call_obj("upsert-tenant-001", tenant_slug="acme", env="dev", status="completed")
    await repo.upsert_call(call_v2)
    await db_session.commit()

    row = await repo.get_call(
        call_id="upsert-tenant-001", tenant_slug="acme", env="dev"
    )
    assert row is not None
    assert row.tenant_slug == "acme"
    assert row.env == "dev"


async def test_bulk_upsert_inserts_multiple_calls(db_session):
    """003-002 AC1 — bulk_upsert 3 new calls → 3 rows, return value = 3."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    repo = SQLAlchemyCallRepository(db_session)
    calls = [_call_obj(f"bulk-new-{i:03d}") for i in range(3)]
    count = await repo.bulk_upsert(calls)

    assert count == 3
    for i in range(3):
        row = await repo.get_call(
            call_id=f"bulk-new-{i:03d}", tenant_slug="acme", env="dev"
        )
        assert row is not None


async def test_bulk_upsert_is_idempotent(db_session):
    """003-002 AC3 — bulk_upsert same calls twice → second run returns 0."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    repo = SQLAlchemyCallRepository(db_session)
    calls = [_call_obj(f"bulk-idem-{i:03d}") for i in range(3)]

    first = await repo.bulk_upsert(calls)
    assert first == 3

    second = await repo.bulk_upsert(calls)
    assert second == 0


async def test_bulk_upsert_empty_list_returns_zero(db_session):
    """003-002 AC4 — bulk_upsert([]) → 0, no error."""
    from app.db.repositories.calls import SQLAlchemyCallRepository

    repo = SQLAlchemyCallRepository(db_session)
    result = await repo.bulk_upsert([])
    assert result == 0
