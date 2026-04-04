"""Domain-level database error types.

All sqlalchemy/asyncpg exceptions are translated to these types at the
repository boundary — never leak driver errors into the service or route
layers (ARCHITECTURE.md §Boundary Handling Rules).
"""
from __future__ import annotations


class DBError(Exception):
    """Base class for all database errors."""


class DBConnectionError(DBError):
    """Raised on startup failure or runtime connection loss."""


class DBPoolExhaustedError(DBError):
    """Raised when pool_timeout is exceeded (sqlalchemy.exc.TimeoutError)."""


class DBStatementTimeoutError(DBError):
    """Raised when a query exceeds command_timeout (asyncio.TimeoutError) or
    the server-side statement_timeout (asyncpg.exceptions.QueryCanceledError).
    """


class DBQueryError(DBError):
    """Raised on generic SQLAlchemy query failure."""


class DBMigrationError(DBError):
    """Raised on Alembic migration failure (for programmatic invocation)."""
