"""Calls API routes — stories 4-1 and 4-2 (Redis primary).
Rewritten in stories 003-003 and 003-004 (PostgreSQL primary + Redis fallback).
Rewritten in story 004-003 (Redis fallback removed — PostgreSQL only).

GET /calls         — paginated call list (PostgreSQL only, Phase 4)
GET /calls/{id}    — call detail (PostgreSQL only, Phase 4)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

import aioboto3
import structlog
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.calls import SQLAlchemyCallRepository
from app.dependencies.database import get_db_session
from app.dependencies.tenant import TenantContext, extract_tenant_context
from app.services.call_list import get_call_list
from app.services.s3_keys import _CALL_ID_RE

log = structlog.get_logger()

router = APIRouter(prefix="/calls", tags=["calls"])


# ---------------------------------------------------------------------------
# GET /calls
# ---------------------------------------------------------------------------


@router.get("")
async def list_calls(
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Literal["missed", "completed", "needs-callback"] | None = None,
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

    Reads from PostgreSQL (Phase 4: sole source of truth).
    PII invariant: no phone numbers in any response field.
    """
    config = request.app.state.config

    # Composition root: wire concrete adapter to port interface.
    # If session is None (no DB configured), pass repo=None → degraded empty result.
    repo = SQLAlchemyCallRepository(session) if session is not None else None

    return await get_call_list(
        repo=repo,
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


def _derive_archive_key(tenant_slug: str, start_time: datetime, call_id: str) -> str:
    """Derive S3 archive key from tenant slug and call start_time.

    Key format: {tenant_slug}/{YYYY}/{MM}/{DD}/{call_id}.json
    Derived entirely from trusted metadata — never from user input.
    """
    call_dt = start_time.astimezone(timezone.utc)
    return (
        f"{tenant_slug}/"
        f"{call_dt.year:04d}/{call_dt.month:02d}/{call_dt.day:02d}/"
        f"{call_id}.json"
    )


def _derive_recording_key(
    tenant_slug: str, env_short: str, start_time: datetime, call_id: str
) -> str:
    """Derive S3 recording key to check hasRecording.

    Matches the key used in recordings.py:
    {env_short}/{tenant_slug}/{YYYY}/{MM}/{DD}/{call_id}.mp3
    """
    call_dt = start_time.astimezone(timezone.utc)
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
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Return call detail for the authenticated tenant.

    Validates call_id format before any AWS operation.
    Fetches metadata from PostgreSQL only (Phase 4: Redis fallback removed).
    S3 key is derived from trusted metadata — never from user input.
    Cross-tenant requests return 404 (identical to missing call — no info leakage).
    caller_number never appears in the response.
    """
    # Validate call_id format before any DB or AWS operation
    if not _CALL_ID_RE.match(call_id):
        raise HTTPException(status_code=400, detail="Invalid call_id format")

    config = request.app.state.config

    # Fetch from PostgreSQL — sole source of truth (Phase 4)
    if session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    repo = SQLAlchemyCallRepository(session)
    pg_call = await repo.get_call(
        call_id=call_id,
        tenant_slug=tenant.tenant_slug,
        env=config.env_short,
    )

    if pg_call is None:
        raise HTTPException(status_code=404, detail="Not found")

    start_time = pg_call.start_time
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    archive_key = _derive_archive_key(tenant.tenant_slug, start_time, call_id)
    recording_key = _derive_recording_key(
        tenant.tenant_slug, config.env_short, start_time, call_id
    )
    bucket = config.s3_recordings_bucket

    transcript: list[Any] = []
    agent_actions: list[Any] = []
    summary: str = pg_call.summary or ""
    has_recording = bool(pg_call.has_recording)

    session_s3 = aioboto3.Session()
    try:
        async with session_s3.client("s3", region_name=config.aws_region) as s3:
            try:
                archive_resp = await s3.get_object(Bucket=bucket, Key=archive_key)
                archive_body = await archive_resp["Body"].read()
                archive = json.loads(archive_body)
                transcript = archive.get("transcript", [])
                agent_actions = archive.get("agent_actions", [])
                summary = archive.get("summary", summary)
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code in ("NoSuchKey", "NoSuchBucket"):
                    raise HTTPException(status_code=404, detail="Not found") from exc
                log.warning("call_archive_s3_error", call_id=call_id, error=str(exc))
                raise HTTPException(status_code=500, detail="Storage error") from exc

            try:
                await s3.head_object(Bucket=bucket, Key=recording_key)
                has_recording = True
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code not in ("NoSuchKey", "NoSuchBucket", "404", "NotFound"):
                    log.warning("call_recording_head_error", call_id=call_id, error=str(exc))
                has_recording = False
    except HTTPException:
        raise
    except Exception as exc:
        log.error("call_detail_s3_error", call_id=call_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Storage error") from exc

    # PII invariant: phone_hash is a server-side field only — never exposed.
    return {
        "id": call_id,
        "callerName": pg_call.caller_name or "Unknown caller",
        "duration": str(pg_call.duration_s or 0),
        "status": pg_call.status,
        "intent": pg_call.intent or "info",
        "summary": summary,
        "timestamp": str(start_time.timestamp()),
        "needsCallback": bool(pg_call.needs_callback),
        "transcript": transcript,
        "agentActions": agent_actions,
        "hasRecording": has_recording,
    }
