"""choka-dashboard-api — FastAPI BFF application.

Story 3.1 — scaffold with CORS, structlog, rate limiting, maintenance mode.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_config
from app.middleware.maintenance import MaintenanceModeMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_log import RequestLogMiddleware
from app.middleware.auth import JWTAuthMiddleware
from app.routes import billing, calls, events, health, profile, recordings, setup

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load config, wire Redis. Shutdown: close connections."""
    config = get_config()
    app.state.config = config

    # Wire Redis (optional — rate limit and metadata index)
    try:
        import redis.asyncio as aioredis
        if config.redis_url:
            app.state.redis = aioredis.from_url(
                config.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            log.info("redis_connected", url=config.redis_url)
    except Exception as exc:
        log.warning("redis_connection_failed", error=str(exc))
        app.state.redis = None

    log.info("app_started", service=config.service_name, env=config.env_short)
    yield

    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()


def create_app() -> FastAPI:
    config = get_config()

    app = FastAPI(
        title="choka-dashboard-api",
        description="Choka Voice Dashboard BFF",
        version="0.1.0",
        root_path=config.root_path,
        lifespan=lifespan,
    )

    # CORS — no wildcard, credentials allowed
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Origin-Verify"],
    )

    # Middleware stack (applied in reverse order — last added = outermost).
    # Execution order: MaintenanceModeMiddleware → JWTAuthMiddleware → RateLimitMiddleware → RequestLogMiddleware
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(MaintenanceModeMiddleware)

    # Routes
    app.include_router(health.router)
    app.include_router(calls.router, prefix="/api")
    app.include_router(recordings.router, prefix="/api")
    app.include_router(profile.router, prefix="/api")
    app.include_router(billing.router, prefix="/api")
    app.include_router(setup.router, prefix="/api")
    app.include_router(events.router, prefix="/api")

    return app


app = create_app()
