"""Request logging middleware — scrubs ?token= from access logs (story-3-1)."""

import re
import time

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger()
_TOKEN_RE = re.compile(r"(token=)[^&\s]+")


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Logs each request with method, path (token redacted), status, and duration."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        raw_url = str(request.url)
        safe_url = _TOKEN_RE.sub(r"\1<redacted>", raw_url)

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        log.info(
            "http_request",
            method=request.method,
            url=safe_url,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response
