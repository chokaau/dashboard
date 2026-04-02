"""Billing endpoint — story-4-5.

GET /billing
  Reads billing.json from S3, computes trial_days_remaining.
  Returns synthetic 14-day trial response when billing.json absent.
  Phase 1 only supports "trial" plan.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import aioboto3
import structlog
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.dependencies.tenant import TenantContext, extract_tenant_context
from app.models.billing_config import BillingConfig

log = structlog.get_logger()

router = APIRouter(tags=["billing"])


def _billing_s3_key(env_short: str, tenant_slug: str) -> str:
    return f"{env_short}/{tenant_slug}/billing.json"


def _compute_response(config: BillingConfig) -> dict[str, Any]:
    """Compute billing response from BillingConfig."""
    now_utc = datetime.now(timezone.utc)
    # Ensure trial_start is timezone-aware
    trial_start = config.trial_start
    if trial_start.tzinfo is None:
        trial_start = trial_start.replace(tzinfo=timezone.utc)

    days_elapsed = (now_utc - trial_start).days
    remaining = max(0, config.trial_days - days_elapsed)
    trial_end = trial_start + timedelta(days=config.trial_days)

    return {
        "plan": config.plan,
        "trialDaysRemaining": remaining,
        "trialEndDate": trial_end.date().isoformat(),
        "isTrialExpired": remaining == 0,
    }


def _synthetic_response() -> dict[str, Any]:
    """Return a synthetic 14-day trial response when billing.json is missing."""
    now_utc = datetime.now(timezone.utc)
    end_date = (now_utc + timedelta(days=14)).date().isoformat()
    return {
        "plan": "trial",
        "trialDaysRemaining": 14,
        "trialEndDate": end_date,
        "isTrialExpired": False,
    }


@router.get("/billing")
async def get_billing(
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
) -> dict[str, Any]:
    """Return billing / trial status for the authenticated tenant."""
    config = request.app.state.config
    bucket = config.s3_config_bucket
    key = _billing_s3_key(config.env_short, tenant.tenant_slug)

    session = aioboto3.Session()
    async with session.client("s3", region_name=config.aws_region) as s3:
        try:
            resp = await s3.get_object(Bucket=bucket, Key=key)
            raw_bytes = await resp["Body"].read()
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                return _synthetic_response()
            raise HTTPException(status_code=500, detail="Storage error")

    try:
        data = json.loads(raw_bytes)
        billing = BillingConfig(**data)
    except (ValidationError, ValueError, Exception) as exc:
        log.error("billing_parse_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Billing data invalid")

    return _compute_response(billing)
