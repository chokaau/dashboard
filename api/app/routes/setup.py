"""Setup wizard endpoint — story-4-7.

POST /setup/complete
  Writes setup_complete.json to S3. Idempotent.
  Only role = "owner" can call it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any

import aioboto3
import structlog
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies.tenant import TenantContext, extract_tenant_context
from app.services.s3_keys import setup_complete_key as _setup_complete_key

log = structlog.get_logger()

router = APIRouter(tags=["setup"])


@router.post("/setup/complete")
async def setup_complete(
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
) -> dict[str, Any]:
    """Mark the tenant as onboarding-complete by writing setup_complete.json.

    Idempotent: subsequent calls overwrite completed_at.
    Only role = "owner" can call this endpoint.
    """
    if tenant.role != "owner":
        raise HTTPException(status_code=403, detail="Insufficient role")

    config = request.app.state.config
    bucket = config.s3_config_bucket
    key = _setup_complete_key(config.env_short, tenant.tenant_slug)

    payload = json.dumps({
        "setup_complete": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).encode("utf-8")

    session = aioboto3.Session()
    async with session.client("s3", region_name=config.aws_region) as s3:
        try:
            await s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=payload,
                ContentType="application/json",
            )
        except ClientError as exc:
            log.error("setup_complete_write_error", error=str(exc))
            raise HTTPException(
                status_code=500,
                detail="Setup completion could not be recorded. Please try again.",
            )

    return {"status": "ok"}
