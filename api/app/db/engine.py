"""Async SQLAlchemy engine and session factory.

Engine configuration matches overview.md §Connection Pooling:
  pool_size=5, max_overflow=2, pool_timeout=10, pool_recycle=1800
  connect_args={"command_timeout": 5}  -- client-side hard limit per query
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_db_engine(
    database_url: str,
    pool_size: int,
    max_overflow: int,
    pool_timeout: int,
    pool_recycle: int,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine with connection pooling.

    Args:
        database_url: asyncpg-compatible connection URL.
        pool_size: Number of persistent connections in the pool.
        max_overflow: Extra connections allowed above pool_size on burst.
        pool_timeout: Seconds to wait for a connection before raising DBPoolExhaustedError.
        pool_recycle: Seconds after which a connection is recycled to avoid stale connections.

    Returns:
        Configured AsyncEngine instance.
    """
    return create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=True,
        echo=False,
        connect_args={"command_timeout": 5},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine.

    expire_on_commit=False prevents attribute access errors after commit
    when ORM objects are used outside the session scope.
    """
    return async_sessionmaker(engine, expire_on_commit=False)
