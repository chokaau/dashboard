"""FastAPI dependency — yields a scoped AsyncSession per request.

Usage in route handlers:
    from app.dependencies.database import get_db_session
    from sqlalchemy.ext.asyncio import AsyncSession

    @router.get("/example")
    async def example(session: AsyncSession | None = Depends(get_db_session)):
        ...

The session factory is stored on app.state.db_session_factory by the lifespan
wiring in app/main.py. If the DB engine was not initialised (DATABASE_SECRET_ARN
and DATABASE_URL both absent), db_session_factory is None on app.state and
get_db_session yields None so routes can degrade gracefully to the Redis path.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session(
    request: Request,
) -> AsyncGenerator[AsyncSession | None, None]:
    """Yield a scoped AsyncSession, or None when DB is not configured.

    Yields None when db_session_factory is None or absent — allows routes
    to fall back to Redis/degraded mode without raising an exception.
    Routes that require a DB session should raise DBConnectionError explicitly
    when session is None and no fallback is available.
    """
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        yield None
        return
    async with session_factory() as session:
        async with session.begin():
            yield session
