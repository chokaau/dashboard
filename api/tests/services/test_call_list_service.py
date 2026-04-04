"""Unit tests for call_list service (PostgreSQL-only, Phase 4) — story 004-002.

Redis fallback tests removed in story 004-002 (Redis read path deleted).
Remaining tests cover the PostgreSQL path and the no-DB degraded path.

AC1: repo returns data → service returns formatted calls.
AC4: PII invariant — no raw phone numbers in response.
AC5: repo=None → empty result with degraded=True.
AC6: service accepts CallRepositoryPort | None (not AsyncSession).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Sequence
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models import Call
from app.db.repositories.calls import CallListResult


# ---------------------------------------------------------------------------
# NullCallRepository — in-memory fake conforming to CallRepositoryPort
# ---------------------------------------------------------------------------


class NullCallRepository:
    """In-memory fake for unit-testing the call_list service.

    Configurable via constructor kwargs so each test can set its own data.
    """

    def __init__(self, calls: list[Call] | None = None, total: int | None = None):
        self._calls = calls or []
        self._total = total if total is not None else len(self._calls)
        self.list_calls_kwargs: dict | None = None

    async def list_calls(
        self,
        *,
        tenant_slug: str,
        env: str,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> CallListResult:
        self.list_calls_kwargs = dict(
            tenant_slug=tenant_slug,
            env=env,
            page=page,
            page_size=page_size,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
        return CallListResult(
            calls=self._calls,
            total=self._total,
            page=page,
            page_size=page_size,
        )

    async def get_call(self, *, call_id: str, tenant_slug: str, env: str) -> Call | None:
        return next((c for c in self._calls if c.id == call_id), None)

    async def upsert_call(self, call: Call) -> Call:
        return call

    async def bulk_upsert(self, calls: Sequence[Call]) -> int:
        return len(calls)


def _make_call(
    call_id: str = "c1",
    tenant_slug: str = "acme",
    env: str = "dev",
    status: str = "missed",
    caller_name: str | None = None,
    phone_hash: str | None = None,
) -> Call:
    return Call(
        id=call_id,
        tenant_slug=tenant_slug,
        env=env,
        start_time=datetime(2026, 4, 4, 9, 0, 0, tzinfo=timezone.utc),
        status=status,
        needs_callback=False,
        has_recording=False,
        caller_name=caller_name,
        phone_hash=phone_hash,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_returns_pg_result_when_available():
    """AC1 — repo returns 2 calls → service returns those 2 calls."""
    from app.services.call_list import get_call_list

    calls = [_make_call("c1"), _make_call("c2")]
    repo = NullCallRepository(calls=calls)

    result = await get_call_list(
        repo=repo,
        env_short="dev",
        tenant_slug="acme",
        page=1,
        page_size=20,
        status_filter=None,
        date_range=None,
    )

    assert len(result["calls"]) == 2
    assert result["pagination"]["total"] == 2


async def test_returns_empty_when_db_empty():
    """AC5 replacement — repo returns 0 rows → empty result (no degraded flag)."""
    from app.services.call_list import get_call_list

    repo = NullCallRepository(calls=[], total=0)

    result = await get_call_list(
        repo=repo,
        env_short="dev",
        tenant_slug="acme",
        page=1,
        page_size=20,
        status_filter=None,
        date_range=None,
    )

    assert result["calls"] == []
    assert result["pagination"]["total"] == 0
    # No degraded flag when DB is available but empty
    assert result.get("degraded") is not True


async def test_returns_degraded_when_no_db():
    """AC5 — repo=None → empty result with degraded=True."""
    from app.services.call_list import get_call_list

    result = await get_call_list(
        repo=None,
        env_short="dev",
        tenant_slug="acme",
        page=1,
        page_size=20,
        status_filter=None,
        date_range=None,
    )

    assert result["calls"] == []
    assert result["pagination"]["total"] == 0
    assert result.get("degraded") is True


async def test_pii_invariant_no_phone_in_response():
    """AC4 — no E.164 phone number pattern in any response field."""
    from app.services.call_list import get_call_list

    # Call with phone_hash set (not raw number) and caller_name (no phone)
    calls = [_make_call("c1", phone_hash="sha256:abc123", caller_name="Alice")]
    repo = NullCallRepository(calls=calls)

    result = await get_call_list(
        repo=repo,
        env_short="dev",
        tenant_slug="acme",
        page=1,
        page_size=20,
        status_filter=None,
        date_range=None,
    )

    phone_pattern = re.compile(r"\+?[0-9]{7,15}")
    response_str = str(result)
    assert not phone_pattern.search(response_str), (
        f"Potential phone number found in response: {response_str}"
    )
    # Verify phone_hash is NOT in response (it's a server-side field only)
    for call_item in result["calls"]:
        assert "phone_hash" not in call_item
        assert "caller_number" not in call_item


async def test_date_range_filter_parsed_correctly():
    """AC1 — date_range='7d' → date_from passed to repo is ~7 days ago."""
    from datetime import timedelta
    from app.services.call_list import get_call_list

    repo = NullCallRepository(calls=[])

    await get_call_list(
        repo=repo,
        env_short="dev",
        tenant_slug="acme",
        page=1,
        page_size=20,
        status_filter=None,
        date_range="7d",
    )

    assert repo.list_calls_kwargs is not None
    date_from = repo.list_calls_kwargs.get("date_from")
    assert date_from is not None
    # date_from should be approximately 7 days ago (within 1 day tolerance)
    date_from_dt = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
    expected = datetime.now(timezone.utc) - timedelta(days=7)
    delta = abs((date_from_dt - expected).total_seconds())
    assert delta < 86400, f"date_from {date_from} is not ~7 days ago (delta={delta}s)"


async def test_status_filter_passed_to_repository():
    """AC1 — status_filter='missed' → repo.list_calls called with status='missed'."""
    from app.services.call_list import get_call_list

    repo = NullCallRepository(calls=[])

    await get_call_list(
        repo=repo,
        env_short="dev",
        tenant_slug="acme",
        page=1,
        page_size=20,
        status_filter="missed",
        date_range=None,
    )

    assert repo.list_calls_kwargs is not None
    assert repo.list_calls_kwargs["status"] == "missed"
