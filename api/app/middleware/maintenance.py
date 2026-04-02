"""MaintenanceModeMiddleware — story-3-1."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    """Returns 503 for all non-health endpoints when MAINTENANCE_MODE=true."""

    async def dispatch(self, request: Request, call_next) -> Response:
        config = getattr(request.app.state, "config", None)
        if config and config.maintenance_mode:
            path = request.url.path.rstrip("/")
            if not path.endswith("/health"):
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Service temporarily unavailable for maintenance."},
                )
        return await call_next(request)
