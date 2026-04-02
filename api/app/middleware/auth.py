"""Cognito JWT validation middleware — story-3-2.

Validates RS256 JWTs from Cognito JWKS endpoint.
- Caches JWKS with 1-hour TTL using asyncio singleflight pattern
- Validates: algorithm (RS256 only), iss, aud, exp
- Stores decoded claims at request.state.jwt_claims
- Supports ?token= query param for SSE /events endpoint only
- Fails closed: JWKS unreachable with no cache → 503

Required IAM: none (public JWKS endpoint).
"""

import asyncio
import time
from typing import Any

import httpx
import structlog
from fastapi import Request, Response
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.logging_events import AUTH_REJECTED, SSE_TOKEN_INVALID, SSE_TOKEN_MISSING

log = structlog.get_logger()

_JWKS_TTL = 3600  # 1 hour
_SSE_PATH = "/api/events"


class JWKSCache:
    """Thread-safe JWKS cache with singleflight pattern via asyncio.Lock."""

    def __init__(self) -> None:
        self._keys: list[dict[str, Any]] = []
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_keys(self, jwks_url: str) -> list[dict[str, Any]]:
        """Return cached keys or fetch once (singleflight via lock)."""
        now = time.monotonic()
        if self._keys and (now - self._fetched_at) < _JWKS_TTL:
            return self._keys

        async with self._lock:
            # Re-check under lock (another coroutine may have refreshed)
            now = time.monotonic()
            if self._keys and (now - self._fetched_at) < _JWKS_TTL:
                return self._keys

            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(jwks_url)
                    resp.raise_for_status()
                    data = resp.json()
                    self._keys = data.get("keys", [])
                    self._fetched_at = time.monotonic()
            except Exception as exc:
                if self._keys:
                    # Stale keys: proceed with cached (fail open on refresh failure)
                    log.warning("jwks_refresh_failed_using_cache", error=str(exc))
                    return self._keys
                raise  # No cache: propagate to caller

        return self._keys


# Module-level cache shared across all requests
_jwks_cache = JWKSCache()


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Validates Cognito RS256 JWT on every request except /health."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path.rstrip("/")

        # Health endpoint — always pass through
        if path.endswith("/health"):
            return await call_next(request)

        config = request.app.state.config
        token = _extract_token(request, path)

        if token is None:
            log.warning(AUTH_REJECTED, reason=SSE_TOKEN_MISSING, path=path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization header"},
            )

        jwks_url = (
            f"https://cognito-idp.{config.aws_region}.amazonaws.com"
            f"/{config.cognito_user_pool_id}/.well-known/jwks.json"
        )
        expected_iss = (
            f"https://cognito-idp.{config.aws_region}.amazonaws.com"
            f"/{config.cognito_user_pool_id}"
        )

        try:
            keys = await _jwks_cache.get_keys(jwks_url)
        except Exception as exc:
            log.error("jwks_unavailable_no_cache", error=str(exc))
            return JSONResponse(
                status_code=503,
                content={"detail": "Authentication service temporarily unavailable"},
            )

        try:
            claims = jwt.decode(
                token,
                keys,
                algorithms=["RS256"],
                audience=config.cognito_client_id,
                issuer=expected_iss,
                options={"verify_exp": True},
            )
        except ExpiredSignatureError:
            log.warning(AUTH_REJECTED, reason="expired", path=path)
            return JSONResponse(status_code=401, content={"detail": "Token expired"})
        except JWTClaimsError as exc:
            log.warning(AUTH_REJECTED, reason=SSE_TOKEN_INVALID, detail=str(exc))
            return JSONResponse(status_code=401, content={"detail": "Invalid token claims"})
        except JWTError as exc:
            log.warning(AUTH_REJECTED, reason=SSE_TOKEN_INVALID, detail=str(exc))
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})

        request.state.jwt_claims = claims
        return await call_next(request)


def _extract_token(request: Request, path: str) -> str | None:
    """Extract Bearer token from Authorization header, or ?token= on SSE path only."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth.removeprefix("Bearer ").strip()

    # ?token= only accepted on the SSE events endpoint
    if path.endswith("/events"):
        token = request.query_params.get("token")
        return token or None

    return None
