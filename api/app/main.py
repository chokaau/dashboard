"""choka-dashboard-api — FastAPI BFF application.

Story 3.1 — scaffold with CORS, structlog, rate limiting, maintenance mode.
Story 002-006 — DB engine wiring in lifespan, exception handlers.
"""

from contextlib import asynccontextmanager
from urllib.parse import urlparse

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_config
from app.db.engine import create_db_engine, create_session_factory
from app.db.errors import (
    DBConnectionError,
    DBPoolExhaustedError,
    DBQueryError,
    DBStatementTimeoutError,
)
from app.db.secrets import fetch_database_url
from app.middleware.maintenance import MaintenanceModeMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_log import RequestLogMiddleware
from app.middleware.auth import JWTAuthMiddleware
from app.routes import activation, billing, calls, events, health, profile, recordings, register, setup
import app.routes.events as _events_module

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load config, wire Redis, wire DB. Shutdown: close connections."""
    config = get_config()
    app.state.config = config

    # Populate SSE module-level constants from AppConfig so they are config-driven,
    # not read from os.environ directly. Tests may still patch these constants.
    _events_module.SSE_PING_INTERVAL_SECONDS = config.sse_ping_interval_seconds
    _events_module.SSE_MAX_CONNECTION_SECONDS = config.sse_max_connection_seconds
    _events_module.SSE_MAX_CONNECTIONS_PER_TENANT = config.sse_max_connections_per_tenant

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

    # Wire DB engine — resolution order: secret_arn → database_url → disabled
    database_url: str | None = None
    if config.database_secret_arn:
        try:
            database_url = await fetch_database_url(config.database_secret_arn)
        except Exception as exc:
            log.warning("db_secret_fetch_failed", error=str(exc))
    elif config.database_url:
        database_url = config.database_url

    if database_url:
        pool_config = {
            "pool_size": config.db_pool_size,
            "max_overflow": config.db_max_overflow,
            "pool_timeout": config.db_pool_timeout,
            "pool_recycle": config.db_pool_recycle,
        }
        engine = create_db_engine(database_url, **pool_config)
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        except Exception:
            pass  # OTEL not configured in all environments
        app.state.db_engine = engine
        app.state.db_session_factory = create_session_factory(engine)
        app.state.db_secret_arn = config.database_secret_arn
        app.state.db_pool_config = pool_config
        parsed = urlparse(database_url)
        log.info("db_connected", host=parsed.hostname)
    else:
        app.state.db_engine = None
        app.state.db_session_factory = None
        app.state.db_secret_arn = None
        app.state.db_pool_config = {}
        log.warning("db_disabled", reason="no database_secret_arn or database_url configured")

    log.info("app_started", service=config.service_name, env=config.env_short)
    yield

    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()

    db_engine = getattr(app.state, "db_engine", None)
    if db_engine is not None:
        await db_engine.dispose()


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


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

    # DB exception handlers
    @app.exception_handler(DBPoolExhaustedError)
    async def db_pool_exhausted_handler(
        request: Request, exc: DBPoolExhaustedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=_error_body("DB_POOL_EXHAUSTED", "Database connection pool exhausted"),
            headers={"Retry-After": "5"},
        )

    @app.exception_handler(DBStatementTimeoutError)
    async def db_statement_timeout_handler(
        request: Request, exc: DBStatementTimeoutError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=_error_body("DB_STATEMENT_TIMEOUT", "Database statement timed out"),
        )

    @app.exception_handler(DBConnectionError)
    async def db_connection_handler(
        request: Request, exc: DBConnectionError
    ) -> JSONResponse:
        secret_arn = getattr(request.app.state, "db_secret_arn", None)
        if secret_arn:
            try:
                pool_config = getattr(request.app.state, "db_pool_config", {})
                new_url = await fetch_database_url(secret_arn)
                old_engine = getattr(request.app.state, "db_engine", None)
                new_engine = create_db_engine(new_url, **pool_config)
                request.app.state.db_engine = new_engine
                request.app.state.db_session_factory = create_session_factory(new_engine)
                if old_engine is not None:
                    await old_engine.dispose()
                log.info("db_pool_rebuilt_after_rotation")
            except Exception as rebuild_exc:
                log.warning("db_pool_rebuild_failed", error=str(rebuild_exc))
        return JSONResponse(
            status_code=503,
            content=_error_body("DB_UNAVAILABLE", "Database connection not available"),
        )

    @app.exception_handler(DBQueryError)
    async def db_query_error_handler(
        request: Request, exc: DBQueryError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=_error_body("DB_QUERY_ERROR", "Database query failed"),
        )

    # Routes
    app.include_router(health.router)
    app.include_router(calls.router, prefix="/api")
    app.include_router(recordings.router, prefix="/api")
    app.include_router(profile.router, prefix="/api")
    app.include_router(billing.router, prefix="/api")
    app.include_router(setup.router, prefix="/api")
    app.include_router(activation.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(register.router, prefix="/api")

    return app


app = create_app()
