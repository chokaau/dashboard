"""Tenant registration endpoint — dashboard-8.

POST /api/auth/register — creates a tenant for a newly signed-up user.

User must be authenticated (valid JWT) but does NOT need existing tenant
claims. This endpoint is called once per user, immediately after Cognito
sign-up, to provision the tenant's S3 config objects and set Cognito
custom attributes.

Flow:
  1. Extract UserIdentity (sub + email) from JWT
  2. Check Cognito: if custom:tenant_id already set → 409
  3. Generate slug from business_name; check S3 for collisions
  4. Generate tenant_id (uuid4)
  5. Write Cognito custom attributes (tenant_id, tenant_slug, role=owner)
  6. Write billing.json + business.yaml to S3
  7. Return 201 with tenant metadata
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

import aioboto3
import structlog
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from app.dependencies.tenant import UserIdentity, extract_user_identity
from app.services.slug import make_unique_slug, slugify

log = structlog.get_logger()

router = APIRouter(tags=["auth"])

_yaml = YAML()
_yaml.default_flow_style = False


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=100)
    owner_name: str = Field(min_length=2, max_length=100)
    state: str = Field(pattern=r"^(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)$")


class RegisterResponse(BaseModel):
    tenant_id: str
    tenant_slug: str
    plan: str
    trial_days: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _user_has_tenant(cognito, pool_id: str, username: str) -> bool:
    """Return True if the Cognito user already has custom:tenant_id set."""
    resp = await cognito.admin_get_user(UserPoolId=pool_id, Username=username)
    attrs = {a["Name"]: a["Value"] for a in resp.get("UserAttributes", [])}
    return bool(attrs.get("custom:tenant_id"))


async def _slug_exists(s3, bucket: str, key_prefix: str) -> bool:
    """Return True if any object exists under the given S3 prefix."""
    try:
        await s3.head_object(Bucket=bucket, Key=key_prefix)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


async def _resolve_slug(s3, bucket: str, env_short: str, base_slug: str) -> str | None:
    """Return a unique slug, appending a random suffix on collision.

    Retries up to 3 times to handle the (unlikely) case where a suffixed
    slug also collides.  Returns None if all attempts are exhausted.
    """
    slug = base_slug
    for attempt in range(3):
        prefix = f"{env_short}/{slug}/"
        if not await _slug_exists(s3, bucket, prefix):
            return slug
        slug = make_unique_slug(base_slug)
    return None


async def _write_billing(s3, bucket: str, env_short: str, slug: str) -> None:
    """Write billing.json to S3."""
    payload = json.dumps({
        "plan": "trial",
        "trial_start": datetime.now(timezone.utc).isoformat(),
        "trial_days": 14,
    }).encode("utf-8")
    await s3.put_object(
        Bucket=bucket,
        Key=f"{env_short}/{slug}/billing.json",
        Body=payload,
        ContentType="application/json",
    )


async def _write_business_yaml(
    s3, bucket: str, env_short: str, slug: str, body: RegisterRequest
) -> None:
    """Write business.yaml to S3."""
    buf = io.StringIO()
    _yaml.dump(
        {
            "business_name": body.business_name,
            "owner_name": body.owner_name,
            "state": body.state,
        },
        buf,
    )
    await s3.put_object(
        Bucket=bucket,
        Key=f"{env_short}/{slug}/business.yaml",
        Body=buf.getvalue().encode("utf-8"),
        ContentType="application/x-yaml",
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/auth/register", status_code=201)
async def register_tenant(
    request: Request,
    identity: Annotated[UserIdentity, Depends(extract_user_identity)],
    body: RegisterRequest,
) -> JSONResponse:
    """Create a tenant for a newly signed-up Cognito user.

    Returns 409 if the user already has a tenant.
    Returns 201 with tenant metadata on success.
    """
    config = request.app.state.config
    pool_id: str = config.cognito_user_pool_id
    bucket: str = config.s3_config_bucket
    env_short: str = config.env_short

    session = aioboto3.Session()
    async with session.client("cognito-idp", region_name=config.aws_region) as cognito:
        try:
            already_registered = await _user_has_tenant(cognito, pool_id, identity.user_id)
        except ClientError as exc:
            log.error("register_cognito_get_user_failed", error=str(exc), user_id=identity.user_id)
            raise HTTPException(status_code=500, detail="Registration check failed")

        if already_registered:
            raise HTTPException(status_code=409, detail="User is already registered with a tenant")

        base_slug = slugify(body.business_name)
        tenant_id = str(uuid.uuid4())

        async with session.client("s3", region_name=config.aws_region) as s3:
            try:
                tenant_slug = await _resolve_slug(s3, bucket, env_short, base_slug)
                if tenant_slug is None:
                    raise HTTPException(status_code=409, detail="Could not generate unique tenant slug")
                await _write_billing(s3, bucket, env_short, tenant_slug)
                await _write_business_yaml(s3, bucket, env_short, tenant_slug, body)
            except HTTPException:
                raise
            except ClientError as exc:
                log.error("register_s3_failed", error=str(exc), slug=base_slug)
                raise HTTPException(status_code=500, detail="Tenant storage initialisation failed")

        try:
            await cognito.admin_update_user_attributes(
                UserPoolId=pool_id,
                Username=identity.user_id,
                UserAttributes=[
                    {"Name": "custom:tenant_id", "Value": tenant_id},
                    {"Name": "custom:tenant_slug", "Value": tenant_slug},
                    {"Name": "custom:role", "Value": "owner"},
                ],
            )
        except ClientError as exc:
            log.error("register_cognito_update_failed", error=str(exc), user_id=identity.user_id)
            raise HTTPException(status_code=500, detail="Tenant attribute assignment failed")

    log.info(
        "tenant_registered",
        user_id=identity.user_id,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
    )

    return JSONResponse(
        status_code=201,
        content=RegisterResponse(
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            plan="trial",
            trial_days=14,
        ).model_dump(),
    )
