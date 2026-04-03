"""Per-tenant Redis rate limiting middleware — story-3-1.

Read endpoints: 120 req/min per tenant.
Write endpoints: 20 req/min per tenant.
Fails open when Redis is unavailable.
"""

import time
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.logging_events import RATE_LIMITER_UNAVAILABLE, TENANT_RATE_LIMITED

log = structlog.get_logger()

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limit keyed on tenant_slug (from JWT claims)."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip health endpoint — unauthenticated, no tenant context
        if request.url.path.rstrip("/").endswith("/health"):
            return await call_next(request)

        # Rate limit only applies after JWT validation sets jwt_claims
        claims = getattr(request.state, "jwt_claims", None)
        if claims is None:
            return await call_next(request)

        tenant_slug = claims.get("custom:tenant_slug", "")
        if not tenant_slug:
            # No tenant yet (e.g. /auth/register) — rate-limit on user sub instead
            sub = claims.get("sub", "")
            if not sub:
                return await call_next(request)
            tenant_slug = f"__sub__{sub}"

        config = request.app.state.config
        is_write = request.method in _WRITE_METHODS
        limit = config.rate_limit_write_per_minute if is_write else config.rate_limit_read_per_minute
        window = 60

        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            log.warning(RATE_LIMITER_UNAVAILABLE, tenant_slug=tenant_slug)
            return await call_next(request)

        key = f"rate:{config.env_short}:{tenant_slug}:{'w' if is_write else 'r'}"
        try:
            now = int(time.time())
            pipe = redis.pipeline()
            pipe.zadd(key, {str(now): now})
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zcard(key)
            pipe.expire(key, window + 1)
            results = await pipe.execute()
            count = results[2]

            if count > limit:
                log.warning(
                    TENANT_RATE_LIMITED,
                    tenant_slug=tenant_slug,
                    count=count,
                    limit=limit,
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please slow down."},
                    headers={"Retry-After": str(window)},
                )
        except Exception as exc:
            log.warning(RATE_LIMITER_UNAVAILABLE, error=str(exc), tenant_slug=tenant_slug)

        return await call_next(request)
