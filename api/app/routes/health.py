"""Health check endpoint — story-3-1, extended with dependency checks in story-4-5."""

import os

import httpx
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = structlog.get_logger()
router = APIRouter()


async def _check_s3(config: object) -> str:
    """Check S3 reachability by doing a lightweight HeadBucket call.

    Returns 'ok' or 'unavailable'.
    """
    import aioboto3
    from botocore.exceptions import ClientError, EndpointConnectionError

    bucket = getattr(config, "s3_config_bucket", "")
    if not bucket:
        # No bucket configured — S3 check skipped, treat as ok
        return "ok"

    region = getattr(config, "aws_region", "ap-southeast-2")
    try:
        session = aioboto3.Session()
        async with session.client("s3", region_name=region) as s3:
            await s3.head_bucket(Bucket=bucket)
        return "ok"
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        # 403/404 means S3 is reachable even if we don't have access
        if code in ("403", "404", "NoSuchBucket", "AccessDenied"):
            return "ok"
        log.warning("health_s3_check_failed", code=code)
        return "unavailable"
    except Exception as exc:
        log.warning("health_s3_check_failed", error=str(exc))
        return "unavailable"


async def _check_jwks(config: object) -> str:
    """Check Cognito JWKS endpoint reachability.

    Returns 'ok' or 'unavailable'.
    """
    region = getattr(config, "aws_region", "ap-southeast-2")
    pool_id = getattr(config, "cognito_user_pool_id", "")
    if not pool_id:
        return "ok"

    url = (
        f"https://cognito-idp.{region}.amazonaws.com"
        f"/{pool_id}/.well-known/jwks.json"
    )
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return "ok"
    except Exception as exc:
        log.warning("health_jwks_check_failed", error=str(exc))
        return "unavailable"


@router.get("/health", include_in_schema=True)
async def health(request: Request) -> JSONResponse:
    """Readiness health check — unauthenticated, no rate limiting.

    Checks:
    - Redis: PING
    - S3: HeadBucket on config bucket
    - Cognito JWKS: GET on .well-known/jwks.json

    Returns 200 when all dependencies are ok; 503 when any is unavailable.
    """
    git_sha = os.environ.get("GIT_SHA", "unknown")
    config = getattr(request.app.state, "config", None)

    # Redis check
    redis = getattr(request.app.state, "redis", None)
    redis_status = "unavailable"
    if redis is not None:
        try:
            await redis.ping()
            redis_status = "ok"
        except Exception as exc:
            log.warning("health_redis_check_failed", error=str(exc))

    # S3 + JWKS checks (run concurrently)
    import asyncio

    if config is not None:
        s3_status, jwks_status = await asyncio.gather(
            _check_s3(config),
            _check_jwks(config),
        )
    else:
        s3_status, jwks_status = "ok", "ok"

    dependencies = {
        "redis": redis_status,
        "s3": s3_status,
        "cognito_jwks": jwks_status,
    }

    all_ok = all(v == "ok" for v in dependencies.values())
    status_code = 200 if all_ok else 503
    overall = "ok" if all_ok else "degraded"

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "service": "choka-dashboard-api",
            "version": git_sha,
            "dependencies": dependencies,
        },
    )
