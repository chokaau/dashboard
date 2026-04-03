"""Activation request endpoint — dashboard-10.

POST /api/activation/request
  - Requires TenantContext (owner role only)
  - Reads billing.json from S3 (or creates a minimal record if absent)
  - Sets activation_status = "pending", product = "voice"
  - Writes updated billing.json back to S3
  - Sends SNS notification to operator (non-fatal on failure)

Response: {"activation_status": "pending"}
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
from app.models.billing_config import BillingConfig
from app.services.notification import notify_activation_request

log = structlog.get_logger()

router = APIRouter(tags=["activation"])


def _billing_s3_key(env_short: str, tenant_slug: str) -> str:
    return f"{env_short}/{tenant_slug}/billing.json"


def _default_billing_data() -> dict[str, Any]:
    """Minimal billing record when billing.json is absent."""
    return {
        "plan": "trial",
        "trial_start": datetime.now(timezone.utc).isoformat(),
        "trial_days": 14,
        "activation_status": "none",
        "product": "",
    }


@router.post("/activation/request")
async def request_activation(
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
) -> dict[str, str]:
    """Submit an activation request for the authenticated tenant.

    Sets activation_status to "pending" and notifies the operator via SNS.
    Only role = "owner" may call this endpoint.
    """
    if tenant.role != "owner":
        raise HTTPException(status_code=403, detail="Insufficient role")

    config = request.app.state.config
    bucket = config.s3_config_bucket
    key = _billing_s3_key(config.env_short, tenant.tenant_slug)

    session = aioboto3.Session()
    async with session.client("s3", region_name=config.aws_region) as s3:
        # Read existing billing.json (or start from defaults)
        existing_data = await _read_billing(s3, bucket, key)

        current_status = existing_data.get("activation_status", "none")

        # Idempotency: already active → 409; already pending → 200
        if current_status == "active":
            raise HTTPException(status_code=409, detail="Service already activated")
        if current_status == "pending":
            return {"activation_status": "pending"}

        # Update activation fields
        existing_data["activation_status"] = "pending"
        existing_data["product"] = "voice"

        # Write updated billing.json
        await _write_billing(s3, bucket, key, existing_data)

    # Parse for notification context (best-effort — profile not required)
    business_name = ""
    owner_name = ""
    state = ""
    try:
        BillingConfig(**existing_data)  # validate schema only
    except Exception:
        pass  # non-fatal — proceed with empty notification fields

    # Send SNS notification — non-fatal on failure
    try:
        await notify_activation_request(
            sns_topic_arn=config.sns_alarms_topic_arn,
            aws_region=config.aws_region,
            tenant_slug=tenant.tenant_slug,
            business_name=business_name,
            owner_name=owner_name,
            state=state,
        )
    except Exception as exc:
        log.warning("activation_notification_failed", error=str(exc), tenant_slug=tenant.tenant_slug)

    log.info("activation_requested", tenant_slug=tenant.tenant_slug)
    return {"activation_status": "pending"}


async def _read_billing(s3, bucket: str, key: str) -> dict[str, Any]:
    """Read billing.json from S3. Returns defaults if key does not exist."""
    try:
        resp = await s3.get_object(Bucket=bucket, Key=key)
        raw_bytes = await resp["Body"].read()
        return json.loads(raw_bytes)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            return _default_billing_data()
        log.error("activation_billing_read_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Storage error")


async def _write_billing(s3, bucket: str, key: str, data: dict[str, Any]) -> None:
    """Write billing.json to S3."""
    try:
        await s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data).encode("utf-8"),
            ContentType="application/json",
        )
    except ClientError as exc:
        log.error("activation_billing_write_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Activation update failed")
