"""Calls API routes — stories 4-1 and 4-2.

GET /calls         — paginated call list (Redis + S3 fallback)
GET /calls/{id}    — call detail (Redis metadata + S3 archive)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Annotated, Any

import aioboto3
import structlog
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.dependencies.tenant import TenantContext, extract_tenant_context
from app.services.call_list import get_call_list

log = structlog.get_logger()

router = APIRouter(prefix="/calls", tags=["calls"])

# call_id validation pattern: alphanumeric + hyphen + underscore, 1-128 chars
_CALL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-\_]{0,127}$")

# date_range validation: relative shortcut (e.g. "7d", "30d", "today") or
# ISO date range "YYYY-MM-DD/YYYY-MM-DD"
_DATE_RANGE_RE = re.compile(
    r"^(\d+d|today|yesterday|\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2})$"
)


# ---------------------------------------------------------------------------
# GET /calls
# ---------------------------------------------------------------------------


@router.get("")
async def list_calls(
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: str | None = None,
    date_range: Annotated[
        str | None,
        Query(
            pattern=r"^(\d+d|today|yesterday|\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2})$",
            description=(
                "Optional date range filter. "
                "Relative: '7d', '30d', '90d', 'today', 'yesterday'. "
                "Absolute: 'YYYY-MM-DD/YYYY-MM-DD'."
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    """Return paginated call list for the authenticated tenant.

    Reads from Redis sorted set + hash pipeline.
    Falls back to S3 scan when Redis index is empty.
    PII invariant: no phone numbers in any response field.
    """
    config = request.app.state.config
    redis = getattr(request.app.state, "redis", None)

    return await get_call_list(
        redis=redis,
        env_short=config.env_short,
        tenant_slug=tenant.tenant_slug,
        page=page,
        page_size=page_size,
        status_filter=status,
        date_range=date_range,
    )


# ---------------------------------------------------------------------------
# GET /calls/{call_id}
# ---------------------------------------------------------------------------


def _derive_archive_key(tenant_slug: str, start_time_str: str, call_id: str) -> str:
    """Derive S3 archive key from tenant slug and call start_time.

    Key format: {tenant_slug}/{YYYY}/{MM}/{DD}/{call_id}.json
    Derived entirely from trusted Redis metadata — never from user input.
    """
    try:
        start_ts = float(start_time_str)
    except (ValueError, TypeError):
        start_ts = 0.0
    call_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    return (
        f"{tenant_slug}/"
        f"{call_dt.year:04d}/{call_dt.month:02d}/{call_dt.day:02d}/"
        f"{call_id}.json"
    )


def _derive_recording_key(tenant_slug: str, env_short: str, start_time_str: str, call_id: str) -> str:
    """Derive S3 recording key to check hasRecording.

    Matches the key used in recordings.py:
    {env_short}/{tenant_slug}/{YYYY}/{MM}/{DD}/{call_id}.mp3
    """
    try:
        start_ts = float(start_time_str)
    except (ValueError, TypeError):
        start_ts = 0.0
    call_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    return (
        f"{env_short}/{tenant_slug}/"
        f"{call_dt.year:04d}/{call_dt.month:02d}/{call_dt.day:02d}/"
        f"{call_id}.mp3"
    )


@router.get("/{call_id}")
async def get_call(
    call_id: str,
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
) -> dict[str, Any]:
    """Return call detail for the authenticated tenant.

    Validates call_id format before any AWS operation.
    Fetches metadata from Redis, then full archive from S3.
    S3 key is derived from Redis start_time — never from user input.
    Cross-tenant requests return 404 (identical to missing call — no info leakage).
    caller_number never appears in the response.
    """
    # AC8: Validate call_id format before any AWS operation
    if not _CALL_ID_RE.match(call_id):
        raise HTTPException(status_code=400, detail="Invalid call_id format")

    config = request.app.state.config
    redis = getattr(request.app.state, "redis", None)

    # AC1: Fetch from Redis metadata hash
    meta_key = f"call_meta:{config.env_short}:{tenant.tenant_slug}:{call_id}"
    meta: dict[str, str] = {}
    if redis is not None:
        meta = await redis.hgetall(meta_key) or {}

    if not meta:
        raise HTTPException(status_code=404, detail="Not found")

    # AC3: Verify tenant ownership — cross-tenant → 404 identical to missing
    hash_tenant = meta.get("tenant_slug", "")
    if hash_tenant and hash_tenant != tenant.tenant_slug:
        raise HTTPException(status_code=404, detail="Not found")

    # AC2: Derive S3 archive key from Redis start_time — never from user input
    start_time_str = meta.get("start_time", "0")
    archive_key = _derive_archive_key(tenant.tenant_slug, start_time_str, call_id)
    recording_key = _derive_recording_key(
        tenant.tenant_slug, config.env_short, start_time_str, call_id
    )
    bucket = config.s3_recordings_bucket

    transcript: list[Any] = []
    agent_actions: list[Any] = []
    summary: str = ""
    has_recording = False

    session = aioboto3.Session()
    try:
        async with session.client("s3", region_name=config.aws_region) as s3:
            # AC1 + AC7: Fetch full archive JSON for transcript, agentActions, summary
            try:
                archive_resp = await s3.get_object(Bucket=bucket, Key=archive_key)
                archive_body = await archive_resp["Body"].read()
                archive = json.loads(archive_body)
                transcript = archive.get("transcript", [])
                agent_actions = archive.get("agent_actions", [])
                summary = archive.get("summary", "")
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code in ("NoSuchKey", "NoSuchBucket"):
                    # AC7: S3 NoSuchKey → 404
                    raise HTTPException(status_code=404, detail="Not found") from exc
                log.warning("call_archive_s3_error", call_id=call_id, error=str(exc))
                raise HTTPException(status_code=500, detail="Storage error") from exc

            # AC5: hasRecording = True only if recording object exists at expected path
            try:
                await s3.head_object(Bucket=bucket, Key=recording_key)
                has_recording = True
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code in ("NoSuchKey", "NoSuchBucket", "404", "NotFound"):
                    has_recording = False
                else:
                    log.warning(
                        "call_recording_head_error", call_id=call_id, error=str(exc)
                    )
                    has_recording = False
    except HTTPException:
        raise
    except Exception as exc:
        log.error("call_detail_s3_error", call_id=call_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Storage error") from exc

    # AC4 + AC6: Build response — caller_number NEVER included
    # callerPhone is the phone_hash (truncated sha256) — never a raw phone number
    return {
        "id": call_id,
        "callerName": meta.get("caller_name") or "Unknown caller",
        "callerPhone": meta.get("phone_hash", ""),
        "duration": meta.get("duration_s", "0"),
        "status": meta.get("status", "unknown"),
        "intent": meta.get("intent", "info"),
        "summary": summary,
        "timestamp": meta.get("start_time", ""),
        "needsCallback": meta.get("needs_callback", "false") == "true",
        "transcript": transcript,
        "agentActions": agent_actions,
        "hasRecording": has_recording,
    }
