"""Calls API routes — stories 4-1 and 4-2.

GET /calls         — paginated call list (Redis + S3 fallback)
GET /calls/{id}    — call detail (Redis metadata + S3 archive)
"""

from __future__ import annotations

import re
from typing import Annotated, Any

import structlog
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


@router.get("/{call_id}")
async def get_call(
    call_id: str,
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
) -> dict[str, Any]:
    """Return call detail for the authenticated tenant.

    Validates call_id format before any AWS operation.
    Cross-tenant requests return 404 (identical to missing call — no info leakage).
    caller_number never appears in the response.
    """
    # Validate call_id format before any AWS operation
    if not _CALL_ID_RE.match(call_id):
        raise HTTPException(status_code=400, detail="Invalid call_id format")

    config = request.app.state.config
    redis = getattr(request.app.state, "redis", None)

    # Fetch from Redis metadata hash
    meta_key = f"call_meta:{config.env_short}:{tenant.tenant_slug}:{call_id}"
    meta: dict[str, str] = {}
    if redis is not None:
        meta = await redis.hgetall(meta_key) or {}

    if not meta:
        raise HTTPException(status_code=404, detail="Not found")

    # Verify tenant ownership (hash tenant_slug must match JWT tenant)
    hash_tenant = meta.get("tenant_slug", "")
    if hash_tenant and hash_tenant != tenant.tenant_slug:
        raise HTTPException(status_code=404, detail="Not found")

    # Build response — caller_number NEVER included
    return {
        "id": call_id,
        "callerName": meta.get("caller_name") or "Unknown caller",
        "duration": meta.get("duration_s", "0"),
        "status": meta.get("status", "unknown"),
        "intent": meta.get("intent", "info"),
        "needsCallback": meta.get("needs_callback", "false") == "true",
        "timestamp": meta.get("start_time", ""),
        "hasRecording": False,  # Extended in story-4-3
        "transcript": [],       # Extended from S3 in story-4-2 full impl
        "agentActions": [],
        "summary": "",
    }
