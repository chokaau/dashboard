"""Recording streaming proxy — story-4-3.

GET /calls/{call_id}/recording
  Streams S3 audio via StreamingResponse.
  S3 bucket name never appears in any response header or body.
  Supports Range requests for audio seeking.
  Cross-tenant requests → 404 (indistinguishable from missing recording).
"""

from __future__ import annotations

import re
from typing import Annotated, AsyncIterator

import aioboto3
import structlog
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.dependencies.tenant import TenantContext, extract_tenant_context
from app.services.s3_keys import _CALL_ID_RE

log = structlog.get_logger()

router = APIRouter(tags=["recordings"])

# Range header validation: bytes=START-END or bytes=START-
_RANGE_RE = re.compile(r"^bytes=\d+(-\d+)?$")

# Structured log event names
_RECORDING_STREAM_INTERRUPTED = "recording_stream_interrupted"


async def _stream_s3_body(body) -> AsyncIterator[bytes]:
    """Async generator that yields chunks from an S3 streaming body."""
    try:
        async for chunk in body:
            yield chunk
    except Exception as exc:
        log.error(_RECORDING_STREAM_INTERRUPTED, error=str(exc))
        raise


@router.get("/calls/{call_id}/recording")
async def get_recording(
    call_id: str,
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
) -> StreamingResponse:
    """Stream audio recording from S3 without exposing presigned URLs.

    Security invariants:
    - S3 bucket name never appears in any response header or body.
    - Cross-tenant call_id → 404 (same as missing recording).
    - Range header forwarded to S3 for audio seeking.
    - Malformed Range header → 400 before any S3 call.
    """
    if not _CALL_ID_RE.match(call_id):
        raise HTTPException(status_code=400, detail="Invalid call_id format")

    # Validate Range header BEFORE any AWS call
    range_header = request.headers.get("Range")
    if range_header is not None:
        if not _RANGE_RE.match(range_header):
            raise HTTPException(status_code=400, detail="Invalid Range header")

    config = request.app.state.config
    redis = getattr(request.app.state, "redis", None)

    # Verify call ownership via Redis metadata
    meta: dict = {}
    if redis is not None:
        meta_key = f"call_meta:{config.env_short}:{tenant.tenant_slug}:{call_id}"
        meta = await redis.hgetall(meta_key) or {}

    if not meta:
        raise HTTPException(status_code=404, detail="Not found")

    hash_tenant = meta.get("tenant_slug", "")
    if hash_tenant and hash_tenant != tenant.tenant_slug:
        raise HTTPException(status_code=404, detail="Not found")

    # Derive S3 key from metadata (never from user input)
    start_ts = float(meta.get("start_time", 0))
    from datetime import datetime, timezone
    call_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    recording_key = (
        f"{config.env_short}/{tenant.tenant_slug}/"
        f"{call_dt.year:04d}/{call_dt.month:02d}/{call_dt.day:02d}/"
        f"{call_id}.mp3"
    )

    bucket = config.s3_recordings_bucket

    # Build get_object kwargs
    get_kwargs: dict = {
        "Bucket": bucket,
        "Key": recording_key,
    }
    if range_header:
        get_kwargs["Range"] = range_header

    # Stream from S3
    session = aioboto3.Session()
    try:
        async with session.client("s3", region_name=config.aws_region) as s3:
            try:
                response = await s3.get_object(**get_kwargs)
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code in ("NoSuchKey", "NoSuchBucket"):
                    raise HTTPException(status_code=404, detail="Not found") from exc
                if code == "InvalidRange":
                    # Proxy Content-Range header from S3 error response if present
                    content_range = (
                        exc.response.get("ResponseMetadata", {})
                        .get("HTTPHeaders", {})
                        .get("content-range", "")
                    )
                    raise HTTPException(
                        status_code=416,
                        detail="Range Not Satisfiable",
                        headers={"Content-Range": content_range} if content_range else None,
                    ) from exc
                raise HTTPException(status_code=500, detail="Storage error") from exc

            status_code = 206 if range_header else 200
            headers = {
                "Content-Disposition": "inline",
                "Cache-Control": "private, max-age=3600",
                # Intentionally omit any header that would expose bucket name
            }

            return StreamingResponse(
                _stream_s3_body(response["Body"]),
                status_code=status_code,
                media_type="audio/mpeg",
                headers=headers,
            )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("recording_s3_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Storage error") from exc
