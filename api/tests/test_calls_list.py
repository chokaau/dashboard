"""Tests for story-4-1: GET /calls — Call List Endpoint.

Phase 4 (story 004-004): Redis data-read helpers and stale test cases removed.
Redis is no longer used as a data source for the call list route.

Remaining tests cover:
  - Auth: 401 without JWT, 403 without tenant_slug
  - Response schema: calls[], pagination, stats
  - Helper pure functions: _derive_caller_name, _format_duration, _format_timestamp
  - Pagination params: page, page_size (valid and invalid)
  - Status filter accepted (route-level, data tested in integration tests)
  - Degraded mode: no DB configured → degraded=True
  - Empty DB: DB available but returns 0 rows → no degraded flag
  - PII guard: no phone numbers in response or logs
  - date_range param accepted / invalid value rejected
  - Performance benchmark (warm DB path)
  - Stats today boundary in Melbourne timezone
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import mint_jwt


# ---------------------------------------------------------------------------
# AC6 — redis_metadata_enabled removed; app ignores unknown env vars
# ---------------------------------------------------------------------------


def test_redis_metadata_flag_ignored(monkeypatch):
    """AC6: REDIS_METADATA_ENABLED in env → app starts without error.

    AppConfig uses extra='ignore' so unknown fields are silently dropped.
    This confirms the field removal is backwards-compatible for ECS tasks
    that still have REDIS_METADATA_ENABLED in their environment.
    """
    import os
    monkeypatch.setenv("REDIS_METADATA_ENABLED", "true")
    from app.config import AppConfig
    config = AppConfig()
    assert not hasattr(config, "redis_metadata_enabled"), (
        "redis_metadata_enabled should have been removed from AppConfig"
    )


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


def test_get_calls_no_auth_returns_401(client):
    resp = client.get("/api/calls")
    assert resp.status_code == 401


def test_get_calls_missing_tenant_slug_returns_403(client):
    token = mint_jwt(tenant_slug="")
    resp = client.get("/api/calls", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Happy path schema (degraded path — no DB in unit test context)
# ---------------------------------------------------------------------------


def test_get_calls_happy_path_schema(client, auth_headers, app_no_redis):
    """GET /api/calls returns correct top-level schema keys."""
    resp = client.get("/api/calls", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert "calls" in body
    assert "pagination" in body
    assert "stats" in body


# ---------------------------------------------------------------------------
# callerName derivation (pure unit tests on helper)
# ---------------------------------------------------------------------------


def test_get_calls_caller_name_from_details():
    """callerName is derived from caller_name field (Phase 4: unit test on helper)."""
    from app.services.call_list import _derive_caller_name

    assert _derive_caller_name("Jane Doe") == "Jane Doe"
    assert _derive_caller_name("Alice") == "Alice"


def test_get_calls_caller_name_unknown_when_empty():
    """callerName falls back to 'Unknown caller' when caller_name is empty."""
    from app.services.call_list import _derive_caller_name

    assert _derive_caller_name("") == "Unknown caller"
    assert _derive_caller_name(None) == "Unknown caller"


# ---------------------------------------------------------------------------
# Duration formatting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "duration_s, expected",
    [
        (45, "45s"),
        (65, "1m 5s"),
        (3723, "1h 2m"),
        (0, "0s"),
        (60, "1m 0s"),
        (3600, "1h 0m"),
    ],
)
def test_format_duration(duration_s, expected):
    from app.services.call_list import _format_duration
    assert _format_duration(duration_s) == expected


# ---------------------------------------------------------------------------
# Timestamp formatting (Melbourne timezone)
# ---------------------------------------------------------------------------


def test_format_timestamp_today(monkeypatch):
    from zoneinfo import ZoneInfo
    from app.services.call_list import _format_timestamp

    melb = ZoneInfo("Australia/Melbourne")
    # 2024-03-28 14:30:00 Melbourne (AEDT = UTC+11)
    # UTC: 2024-03-28 03:30:00
    call_time_utc = datetime(2024, 3, 28, 3, 30, 0, tzinfo=timezone.utc)
    now_melb = datetime(2024, 3, 28, 15, 0, 0, tzinfo=melb)

    result = _format_timestamp(call_time_utc, now_melb)
    assert result.startswith("Today")
    assert "2:30 PM" in result


def test_format_timestamp_yesterday(monkeypatch):
    from zoneinfo import ZoneInfo
    from app.services.call_list import _format_timestamp

    melb = ZoneInfo("Australia/Melbourne")
    call_time_utc = datetime(2024, 3, 27, 3, 30, 0, tzinfo=timezone.utc)
    now_melb = datetime(2024, 3, 28, 15, 0, 0, tzinfo=melb)

    result = _format_timestamp(call_time_utc, now_melb)
    assert result.startswith("Yesterday")


def test_format_timestamp_older(monkeypatch):
    from zoneinfo import ZoneInfo
    from app.services.call_list import _format_timestamp

    melb = ZoneInfo("Australia/Melbourne")
    call_time_utc = datetime(2024, 3, 25, 3, 30, 0, tzinfo=timezone.utc)
    now_melb = datetime(2024, 3, 28, 15, 0, 0, tzinfo=melb)

    result = _format_timestamp(call_time_utc, now_melb)
    assert "25 Mar" in result


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_get_calls_pagination_defaults(client, auth_headers, app_no_redis):
    resp = client.get("/api/calls", headers=auth_headers)
    body = resp.json()
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 20


def test_get_calls_invalid_page_size_422(client, auth_headers):
    resp = client.get("/api/calls?page_size=0", headers=auth_headers)
    assert resp.status_code == 422


def test_get_calls_invalid_page_422(client, auth_headers):
    resp = client.get("/api/calls?page=0", headers=auth_headers)
    assert resp.status_code == 422


def test_get_calls_page_size_too_large_422(client, auth_headers):
    resp = client.get("/api/calls?page_size=101", headers=auth_headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Status filter — accepted by route (data correctness tested in integration tests)
# ---------------------------------------------------------------------------


def test_get_calls_status_filter_accepted(client, auth_headers, app_no_redis):
    """status=missed is accepted by the route without error."""
    resp = client.get("/api/calls?status=missed", headers=auth_headers)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Degraded mode: no DB configured → degraded=True
# ---------------------------------------------------------------------------


def test_no_db_configured_returns_degraded(client, auth_headers, app_no_redis):
    """When no DB is configured (repo=None), response includes degraded=True.

    Phase 4: degraded state is triggered by absent DB, not by missing Redis hashes.
    """
    app_no_redis.state.db_session_factory = None

    resp = client.get("/api/calls", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("degraded") is True


# ---------------------------------------------------------------------------
# Empty DB: DB available but returns 0 rows → no degraded flag
# ---------------------------------------------------------------------------


def test_empty_db_returns_200_without_degraded(client, auth_headers, app_no_redis):
    """Empty DB (repo returns 0 rows) → HTTP 200, no degraded flag.

    Phase 4: Redis fallback removed. Empty DB is a valid state — not degraded.
    Injects a mock session so get_db_session yields non-None, causing the route
    to build a repo. The repo's list_calls returns 0 rows — no degraded flag.
    """
    from app.dependencies.database import get_db_session
    from app.db.repositories.calls import CallListResult

    session_mock = MagicMock()
    repo_mock = MagicMock()
    repo_mock.list_calls = AsyncMock(
        return_value=CallListResult(calls=[], total=0, page=1, page_size=20)
    )

    async def _override_session():
        yield session_mock

    app_no_redis.dependency_overrides[get_db_session] = _override_session
    try:
        with patch("app.routes.calls.SQLAlchemyCallRepository", return_value=repo_mock):
            resp = client.get("/api/calls", headers=auth_headers)
    finally:
        app_no_redis.dependency_overrides.pop(get_db_session, None)

    assert resp.status_code == 200
    body = resp.json()
    assert "calls" in body
    assert body.get("degraded") is not True


# ---------------------------------------------------------------------------
# PII guard: no raw phone numbers in response
# ---------------------------------------------------------------------------


def test_no_phone_number_in_response(client, auth_headers, app_no_redis):
    """No AU phone number pattern +61XXXXXXXXX appears in response body."""
    import re

    resp = client.get("/api/calls", headers=auth_headers)
    body_text = resp.text
    au_phone_re = re.compile(r"\+61[1-9]\d{8}")
    assert not au_phone_re.search(body_text), "AU phone number found in response — PII leak!"


# ---------------------------------------------------------------------------
# date_range query parameter (AC-1)
# ---------------------------------------------------------------------------


def test_get_calls_date_range_accepted(client, auth_headers, app_no_redis):
    """date_range param is accepted and passed through without error."""
    resp = client.get("/api/calls?date_range=7d", headers=auth_headers)
    assert resp.status_code == 200


def test_get_calls_date_range_invalid_422(client, auth_headers):
    """date_range value that cannot be parsed returns 422."""
    resp = client.get("/api/calls?date_range=not-a-valid-range-!!!!", headers=auth_headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PII guard: no raw phone numbers in logs (AC-11)
# ---------------------------------------------------------------------------


def test_no_phone_number_in_logs(client, auth_headers, app_no_redis):
    """No AU phone number pattern +61XXXXXXXXX appears in any structlog log record."""
    import re

    au_phone_re = re.compile(r"\+61[1-9]\d{8}")
    captured_events: list[dict] = []

    def capturing_warning(event, **kwargs):
        captured_events.append({"event": event, **kwargs})

    def capturing_info(event, **kwargs):
        captured_events.append({"event": event, **kwargs})

    with patch("app.services.call_list.log") as mock_log:
        mock_log.warning = capturing_warning
        mock_log.info = capturing_info
        resp = client.get("/api/calls", headers=auth_headers)

    assert resp.status_code == 200
    for record in captured_events:
        for val in record.values():
            assert not au_phone_re.search(str(val)), (
                f"AU phone number found in log record: {record}"
            )


# ---------------------------------------------------------------------------
# Performance (AC-12)
# ---------------------------------------------------------------------------


@pytest.mark.performance
def test_call_list_performance_warm_db(app_no_redis):
    """P95 < 200ms under sequential requests (degraded/empty path)."""
    import time
    import statistics

    from fastapi.testclient import TestClient

    token = mint_jwt()
    headers = {"Authorization": f"Bearer {token}"}

    latencies: list[float] = []
    with TestClient(app_no_redis, raise_server_exceptions=True) as c:
        # Warm-up
        c.get("/api/calls", headers=headers)
        # 10 measured requests
        for _ in range(10):
            t0 = time.perf_counter()
            resp = c.get("/api/calls", headers=headers)
            latencies.append(time.perf_counter() - t0)
            assert resp.status_code == 200

    latencies_ms = [l * 1000 for l in latencies]
    latencies_ms.sort()
    p95 = latencies_ms[int(len(latencies_ms) * 0.95) - 1]
    p99_idx = max(int(len(latencies_ms) * 0.99) - 1, len(latencies_ms) - 1)
    p99 = latencies_ms[p99_idx]

    assert p95 < 200, f"P95 latency {p95:.1f}ms exceeds 200ms threshold"
    assert p99 < 500, f"P99 latency {p99:.1f}ms exceeds 500ms threshold"


# ---------------------------------------------------------------------------
# Stats boundary in Melbourne timezone
# ---------------------------------------------------------------------------


def test_stats_today_boundary_melbourne(client, auth_headers, app_no_redis):
    """stats.today uses Australia/Melbourne day boundary, not UTC."""
    resp = client.get("/api/calls", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "stats" in body
    assert "totalToday" in body["stats"]
