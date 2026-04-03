"""Profile read/write endpoints — story-4-4.

GET /profile  — read business.yaml from S3, return as JSON + setupComplete flag
PUT /profile  — validate BusinessConfig, write business.yaml, publish config-change event

Security:
  - Only role = "owner" can PUT /profile.
  - S3 key is derived from JWT tenant_slug, never from user input.
"""

from __future__ import annotations

from typing import Annotated, Any

import aioboto3
import structlog
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from ruamel.yaml import YAML

from app.dependencies.tenant import TenantContext, extract_tenant_context
from app.models.business_config import BusinessConfig
from app.services.s3_keys import setup_complete_key as _setup_complete_key

log = structlog.get_logger()

router = APIRouter(tags=["profile"])

_yaml = YAML()
_yaml.default_flow_style = False


def _profile_s3_key(env_short: str, tenant_slug: str) -> str:
    return f"{env_short}/{tenant_slug}/business.yaml"


async def _check_setup_complete(s3, bucket: str, key: str) -> bool:
    """Return True if setup_complete.json exists in S3."""
    try:
        await s3.get_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            return False
        raise


def _config_to_response(config: BusinessConfig, setup_complete: bool) -> dict[str, Any]:
    """Convert BusinessConfig to camelCase API response."""
    return {
        "businessName": config.business_name,
        "ownerName": config.owner_name,
        "receptionistName": config.receptionist_name,
        "ownerPhone": config.owner_phone,
        "services": config.services,
        "servicesNotOffered": config.services_not_offered,
        "serviceAreas": config.service_areas,
        "hours": config.hours,
        "pricing": config.pricing,
        "faq": config.faq,
        "policies": config.policies,
        "aboutOwner": config.about_owner,
        "state": config.state,
        "setupComplete": setup_complete,
    }


@router.get("/profile")
async def get_profile(
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
) -> dict[str, Any]:
    """Read business profile from S3 for the authenticated tenant."""
    config = request.app.state.config
    bucket = config.s3_config_bucket
    yaml_key = _profile_s3_key(config.env_short, tenant.tenant_slug)
    setup_key = _setup_complete_key(config.env_short, tenant.tenant_slug)

    session = aioboto3.Session()
    async with session.client("s3", region_name=config.aws_region) as s3:
        # Read business.yaml
        try:
            resp = await s3.get_object(Bucket=bucket, Key=yaml_key)
            raw_bytes = await resp["Body"].read()
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                raise HTTPException(status_code=404, detail="Profile not configured")
            raise HTTPException(status_code=500, detail="Storage error")

        try:
            import io
            data = dict(_yaml.load(io.BytesIO(raw_bytes)) or {})
            business_config = BusinessConfig(**data)
        except Exception as exc:
            log.error("profile_parse_error", error=str(exc))
            raise HTTPException(status_code=500, detail="Profile data invalid")

        setup_complete = await _check_setup_complete(s3, bucket, setup_key)

    return _config_to_response(business_config, setup_complete)


@router.put("/profile")
async def update_profile(
    request: Request,
    tenant: Annotated[TenantContext, Depends(extract_tenant_context)],
    body: BusinessConfig,
) -> dict[str, str]:
    """Write business profile to S3 for the authenticated tenant.

    Only role = "owner" can write.
    Validates with BusinessConfig before any S3 write.
    """
    if tenant.role != "owner":
        raise HTTPException(status_code=403, detail="Insufficient role")

    config = request.app.state.config
    bucket = config.s3_config_bucket
    yaml_key = _profile_s3_key(config.env_short, tenant.tenant_slug)

    # Serialise validated config to YAML
    import io
    buf = io.StringIO()
    _yaml.dump(body.model_dump(), buf)
    yaml_bytes = buf.getvalue().encode("utf-8")

    session = aioboto3.Session()
    async with session.client("s3", region_name=config.aws_region) as s3:
        try:
            await s3.put_object(
                Bucket=bucket,
                Key=yaml_key,
                Body=yaml_bytes,
                ContentType="application/x-yaml",
            )
        except ClientError as exc:
            log.error("profile_write_error", error=str(exc))
            raise HTTPException(status_code=500, detail="Profile update failed")

    # Publish config-change event via Redis pub/sub (fire-and-forget)
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        import json
        channel = f"config:{config.env_short}:{tenant.tenant_slug}"
        try:
            await redis.publish(channel, json.dumps({"event": "config_updated"}))
        except Exception as exc:
            log.warning("config_event_publish_failed", error=str(exc))

    return {"status": "updated"}
