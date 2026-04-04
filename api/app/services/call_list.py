"""Call list service — PostgreSQL-only read path (Phase 4).

Story 003-003: dual-read (PG primary + Redis fallback).
Story 004-002: Redis fallback removed. PostgreSQL is the sole source of truth.

Read path resolution order (Phase 4):
  1. If repo is not None and returns calls → format and return PG data.
  2. If repo returns empty → return empty result.
  3. If repo is None → return empty result with degraded=True.

PII invariant: caller phone numbers never appear in any return value.
Port: service accepts CallRepositoryPort | None (not AsyncSession).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import structlog
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.db.repositories.calls import CallRepositoryPort

log = structlog.get_logger()

_MELB_TZ = ZoneInfo("Australia/Melbourne")


# ---------------------------------------------------------------------------
# Formatting helpers (pure functions — testable in isolation)
# ---------------------------------------------------------------------------


def _format_duration(duration_s: int) -> str:
    """Format seconds as human-readable duration.

    Returns: "Xs", "Xm Xs", or "Xh Xm".
    """
    if duration_s < 60:
        return f"{duration_s}s"
    hours, remainder = divmod(duration_s, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {seconds}s"


def _format_timestamp(call_time_utc: datetime, now_melb: datetime) -> str:
    """Format call timestamp relative to now in Australia/Melbourne timezone.

    Returns: "Today H:MM AM/PM", "Yesterday H:MM AM/PM", or "D Mon H:MM AM/PM".
    """
    call_melb = call_time_utc.astimezone(_MELB_TZ)
    now_date = now_melb.date()
    call_date = call_melb.date()

    time_str = call_melb.strftime("%-I:%M %p")

    delta = (now_date - call_date).days
    if delta == 0:
        return f"Today {time_str}"
    if delta == 1:
        return f"Yesterday {time_str}"
    return call_melb.strftime("%-d %b ") + time_str


def _derive_caller_name(caller_name: str | None) -> str:
    """Derive callerName from stored metadata (no raw phone numbers).

    Priority: caller_name from details > "Unknown caller".
    """
    if caller_name:
        return caller_name
    return "Unknown caller"


# ---------------------------------------------------------------------------
# Date range parsing
# ---------------------------------------------------------------------------


def _parse_date_range(date_range: str | None) -> tuple[str | None, str | None]:
    """Parse date_range string into (date_from, date_to) ISO strings.

    Supported formats:
      "Nd"       — relative N days back from now (e.g. "7d", "30d")
      "today"    — today midnight to now
      "yesterday"— yesterday midnight to yesterday 23:59:59
      "YYYY-MM-DD/YYYY-MM-DD" — absolute range
    Returns (date_from, date_to) as ISO-8601 strings or (None, None).
    """
    if not date_range:
        return None, None

    now = datetime.now(timezone.utc)

    if date_range.endswith("d") and date_range[:-1].isdigit():
        days = int(date_range[:-1])
        date_from = (now - timedelta(days=days)).isoformat()
        return date_from, None

    if date_range == "today":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return today_start.isoformat(), None

    if date_range == "yesterday":
        yesterday_start = (now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        yesterday_end = yesterday_start.replace(hour=23, minute=59, second=59)
        return yesterday_start.isoformat(), yesterday_end.isoformat()

    if "/" in date_range:
        parts = date_range.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]

    return None, None


# ---------------------------------------------------------------------------
# ORM → response dict mapper (PII-safe)
# ---------------------------------------------------------------------------


def _map_call_to_response(call: Any, now_melb: datetime) -> dict[str, Any]:
    """Map a Call ORM object to the API response dict.

    Explicitly excludes: phone_hash, caller_number (PII invariant).
    """
    start_time = call.start_time
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    duration_s = call.duration_s or 0
    return {
        "id": call.id,
        "callerName": _derive_caller_name(call.caller_name),
        "duration": _format_duration(duration_s),
        "timestamp": _format_timestamp(start_time, now_melb),
        "status": call.status,
        "needsCallback": bool(call.needs_callback),
        "intent": call.intent,
        "hasRecording": bool(call.has_recording),
        "summary": call.summary,
    }


# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------


def _compute_stats(
    calls: list[dict[str, Any]], now_melb: datetime, *, db_total: int
) -> dict[str, Any]:
    """Compute today/total/needs-callback stats from calls list.

    'Today' boundary is Australia/Melbourne midnight, not UTC.
    ``db_total`` is the full count from the database (not page-bounded).
    """
    total_today = 0
    needs_callback = 0

    for call in calls:
        if call.get("timestamp", "").startswith("Today"):
            total_today += 1
        if call.get("needsCallback"):
            needs_callback += 1

    return {
        "totalToday": total_today,
        "needsCallback": needs_callback,
        "total": db_total,
    }


# ---------------------------------------------------------------------------
# Public entry point — PostgreSQL only (Phase 4)
# ---------------------------------------------------------------------------


async def get_call_list(
    *,
    repo: "CallRepositoryPort | None",
    env_short: str,
    tenant_slug: str,
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    date_range: str | None = None,
) -> dict[str, Any]:
    """Fetch paginated call list for a tenant from PostgreSQL.

    Phase 4: Redis fallback removed. PostgreSQL is the sole source of truth.

    Returns:
        {
            "calls": [...],
            "pagination": {"page": int, "pageSize": int, "total": int},
            "stats": {"totalToday": int, "needsCallback": int, "total": int},
            "degraded": bool  (only present when True — no DB configured)
        }
    """
    date_from, date_to = _parse_date_range(date_range)
    now_melb = datetime.now(_MELB_TZ)

    if repo is not None:
        pg_result = await repo.list_calls(
            tenant_slug=tenant_slug,
            env=env_short,
            page=page,
            page_size=page_size,
            status=status_filter,
            date_from=date_from,
            date_to=date_to,
        )
        calls = [_map_call_to_response(c, now_melb) for c in pg_result.calls]
        stats = _compute_stats(calls, now_melb, db_total=pg_result.total)
        return {
            "calls": calls,
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "total": pg_result.total,
            },
            "stats": stats,
        }

    # No DB configured — degraded empty result
    return {
        "calls": [],
        "pagination": {"page": page, "pageSize": page_size, "total": 0},
        "stats": {"totalToday": 0, "needsCallback": 0, "total": 0},
        "degraded": True,
    }
