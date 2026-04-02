"""Call list service — story-4-1.

Reads call metadata from Redis sorted set + hash pipeline.
Falls back to S3 scan when Redis index is empty.
Enforces tenant isolation: all keys scoped to env_short + tenant_slug.
PII invariant: caller phone numbers never appear in any return value.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from zoneinfo import ZoneInfo

log = structlog.get_logger()

_MELB_TZ = ZoneInfo("Australia/Melbourne")

# Structured log event names
_CALL_LIST_DEGRADED = "call_list_degraded"
_CALL_LIST_S3_FALLBACK = "call_list_s3_fallback"


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


def _derive_caller_name(caller_name: str, phone_hash: str) -> str:
    """Derive callerName from stored metadata (no raw phone numbers).

    Priority: caller_name from details > "Unknown caller".
    phone_hash is a truncated sha256 — never a raw phone number.
    """
    if caller_name:
        return caller_name
    return "Unknown caller"


# ---------------------------------------------------------------------------
# Redis read path
# ---------------------------------------------------------------------------


async def _read_calls_from_redis(
    redis: Any,
    env_short: str,
    tenant_slug: str,
    page: int,
    page_size: int,
    status_filter: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Read paginated calls from Redis sorted set + hash.

    Returns (calls_list, degraded_flag).
    Sorted set: call_index:{env}:{tenant_slug}  (score = start_time timestamp)
    Hash:       call_meta:{env}:{tenant_slug}:{call_id}
    """
    index_key = f"call_index:{env_short}:{tenant_slug}"

    total = await redis.zcard(index_key)
    if total == 0:
        return [], False

    # ZREVRANGEBYSCORE for reverse-chron order with pagination
    offset = (page - 1) * page_size
    # Fetch extra items for status filtering if filter is active
    fetch_size = page_size * 3 if status_filter else page_size
    members_scores = await redis.zrevrangebyscore(
        index_key,
        max="+inf",
        min="-inf",
        withscores=True,
        start=offset,
        num=fetch_size,
    )

    calls: list[dict[str, Any]] = []
    degraded = False
    now_melb = datetime.now(_MELB_TZ)

    for call_id, score in members_scores:
        meta_key = f"call_meta:{env_short}:{tenant_slug}:{call_id}"
        meta = await redis.hgetall(meta_key)

        if not meta:
            degraded = True
            log.warning(_CALL_LIST_DEGRADED, call_id=call_id, reason="missing_hash")
            continue

        # Tenant isolation: skip if hash tenant_slug doesn't match
        hash_tenant = meta.get("tenant_slug", "")
        if hash_tenant and hash_tenant != tenant_slug:
            continue

        status = meta.get("status", "unknown")
        if status_filter and status != status_filter:
            continue

        start_ts = float(meta.get("start_time", score))
        call_time_utc = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        duration_s = int(meta.get("duration_s", 0))

        call_item = {
            "id": call_id,
            "callerName": _derive_caller_name(
                meta.get("caller_name", ""),
                meta.get("phone_hash", ""),
            ),
            "duration": _format_duration(duration_s),
            "timestamp": _format_timestamp(call_time_utc, now_melb),
            "status": status,
            "needsCallback": meta.get("needs_callback", "false") == "true",
            "intent": meta.get("intent", "info"),
        }
        calls.append(call_item)

        if len(calls) >= page_size:
            break

    return calls, degraded


# ---------------------------------------------------------------------------
# S3 fallback (stub — full impl in story-7-x backfill)
# ---------------------------------------------------------------------------


async def s3_scan_fallback(
    s3_client: Any,
    bucket: str,
    env_short: str,
    tenant_slug: str,
    max_objects: int = 500,
) -> list[dict[str, Any]]:
    """Scan S3 for call archives when Redis index is empty.

    Returns a list of minimal call records. Fires async Redis backfill.
    This is a thin stub — real pagination + backfill implemented in story-7-x.
    """
    log.info(_CALL_LIST_S3_FALLBACK, tenant_slug=tenant_slug)
    return []


# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------


def _compute_stats(calls: list[dict[str, Any]], now_melb: datetime) -> dict[str, Any]:
    """Compute today/total/needs-callback stats from calls list.

    'Today' boundary is Australia/Melbourne midnight, not UTC.
    """
    today_str = now_melb.strftime("%Y-%m-%d")
    total_today = 0
    needs_callback = 0

    for call in calls:
        # Reparse the formatted timestamp to check if it's today
        if call["timestamp"].startswith("Today"):
            total_today += 1
        if call.get("needsCallback"):
            needs_callback += 1

    return {
        "totalToday": total_today,
        "needsCallback": needs_callback,
        "total": len(calls),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def get_call_list(
    redis: Any,
    env_short: str,
    tenant_slug: str,
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    date_range: str | None = None,
) -> dict[str, Any]:
    """Fetch paginated call list for a tenant.

    Returns:
        {
            "calls": [...],
            "pagination": {"page": int, "pageSize": int, "total": int},
            "stats": {"totalToday": int, "needsCallback": int, "total": int},
            "degraded": bool  (omitted when False)
        }
    """
    calls: list[dict[str, Any]] = []
    degraded = False

    if redis is not None:
        index_key = f"call_index:{env_short}:{tenant_slug}"
        zcard = await redis.zcard(index_key)

        if zcard == 0:
            # Redis index empty — S3 fallback (stub returns [] for now)
            calls = await s3_scan_fallback(None, "", env_short, tenant_slug)
        else:
            calls, degraded = await _read_calls_from_redis(
                redis, env_short, tenant_slug, page, page_size, status_filter
            )

    now_melb = datetime.now(_MELB_TZ)
    stats = _compute_stats(calls, now_melb)

    result: dict[str, Any] = {
        "calls": calls,
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": len(calls),
        },
        "stats": stats,
    }

    if degraded:
        result["degraded"] = True

    return result
