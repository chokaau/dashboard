"""Billing endpoint — story-4-5 (S3 primary) rewritten in story 003-005
(DB primary + S3 fallback + auto-upsert).

GET /billing
  1. Try BillingRepository (PostgreSQL primary)
  2. If no DB row: read S3 billing.json, upsert to DB, return response
  3. If S3 NoSuchKey or both unavailable: return synthetic 14-day trial response

Response shape matches tests/fixtures/billing_baseline.json.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import aioboto3
import structlog
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BillingUsage
from app.db.repositories.billing import SQLAlchemyBillingRepository
from app.dependencies.database import get_db_session
from app.dependencies.tenant import TenantContext, extract_tenant_context
from app.models.billing_config import BillingConfig

log = structlog.get_logger()

router = APIRouter(tags=["billing"])


def _billing_s3_key(env_short: str, tenant_slug: str) -> str:
    return f"{env_short}/{tenant_slug}/billing.json"


def _compute_response_from_row(row: BillingUsage) -> dict[str, Any]:
    """Map BillingUsage ORM row to API response shape.

    Matches billing_baseline.json fields exactly.
    """
    now_utc = datetime.now(timezone.utc)
    trial_start = row.trial_start
    if trial_start.tzinfo is None:
        trial_start = trial_start.replace(tzinfo=timezone.utc)

    days_elapsed = (now_utc - trial_start).days
    remaining = max(0, row.trial_days - days_elapsed)
    trial_end = trial_start + timedelta(days=row.trial_days)

    return {
        "plan": row.plan,
        "trialDaysRemaining": remaining,
        "trialEndDate": trial_end.date().isoformat(),
        "isTrialExpired": remaining == 0,
        "activationStatus": row.activation_status,
        "product": row.product,
    }


def _compute_response(config: BillingConfig) -> dict[str, Any]:
    """Compute billing response from BillingConfig (S3 model — legacy path)."""
    now_utc = datetime.now(timezone.utc)
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
        "activationStatus": config.activation_status,
        "product": config.product,
    }


def _synthetic_response() -> dict[str, Any]:
    """Return a synthetic 14-day trial response when billing data is missing."""
    now_utc = datetime.now(timezone.utc)
    end_date = (now_utc + timedelta(days=14)).date().isoformat()
    return {
        "plan": "trial",
        "trialDaysRemaining": 14,
        "trialEndDate": end_date,
        "isTrialExpired": False,
        "activationStatus": "none",
        "product": "",
    }


async def _handle_billing_request(
    *,
    repo: Any,
    s3: Any,
    bucket: str,
    s3_key: str,
    tenant_slug: str,
    env: str,
) -> dict[str, Any]:
    """Core billing logic extracted for testability.

    Resolution order:
      1. DB row exists → return _compute_response_from_row(row)
      2. DB empty, S3 has billing.json → upsert to DB → return response
      3. S3 NoSuchKey → return _synthetic_response()
    """
    row = await repo.get_billing(tenant_slug=tenant_slug, env=env)
    if row is not None:
        return _compute_response_from_row(row)

    # DB empty — attempt S3 fallback
    try:
        resp = await s3.get_object(Bucket=bucket, Key=s3_key)
        raw_bytes = await resp["Body"].read()
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            return _synthetic_response()
        log.error("billing_s3_error", error=str(exc))
        return _synthetic_response()

    try:
        data = json.loads(raw_bytes)
        config = BillingConfig(**data)
    except (ValidationError, ValueError, Exception) as exc:
        log.error("billing_parse_error", error=str(exc))
        return _synthetic_response()

    # Parse trial_start from S3 data
    trial_start = config.trial_start
    if trial_start.tzinfo is None:
        trial_start = trial_start.replace(tzinfo=timezone.utc)

    # Auto-upsert to DB so next request is served from PostgreSQL
    new_row = BillingUsage(
        id=uuid.uuid4(),
        tenant_slug=tenant_slug,
        env=env,
        plan=config.plan,
        trial_start=trial_start,
        trial_days=config.trial_days,
        activation_status=config.activation_status,
        product=config.product,
    )
    try:
        upserted = await repo.upsert_billing(new_row)
        return _compute_response_from_row(upserted)
    except Exception as exc:
        log.warning("billing_upsert_failed", error=str(exc))
        return _compute_response(config)


@router.get("/billing")
async def get_billing(
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> dict[str, Any]:
    """Return billing / trial status for the authenticated tenant.

    PostgreSQL primary, S3 billing.json fallback with auto-upsert.
    """
    config = request.app.state.config
    bucket = config.s3_config_bucket
    s3_key = _billing_s3_key(config.env_short, tenant.tenant_slug)

    if session is None:
        # No DB configured — fall back directly to S3/synthetic
        session_s3 = aioboto3.Session()
        async with session_s3.client("s3", region_name=config.aws_region) as s3:
            try:
                resp = await s3.get_object(Bucket=bucket, Key=s3_key)
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
                return _synthetic_response()
            return _compute_response(billing)

    repo = SQLAlchemyBillingRepository(session)
    session_s3 = aioboto3.Session()
    async with session_s3.client("s3", region_name=config.aws_region) as s3:
        return await _handle_billing_request(
            repo=repo,
            s3=s3,
            bucket=bucket,
            s3_key=s3_key,
            tenant_slug=tenant.tenant_slug,
            env=config.env_short,
        )
