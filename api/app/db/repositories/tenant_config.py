"""TenantConfig repository — ports-and-adapters pattern.

TenantConfigRepositoryPort   — Protocol (port).
SQLAlchemyTenantConfigRepository — Adapter: SQLAlchemy 2.0 async + PostgreSQL
                                   INSERT ... ON CONFLICT DO UPDATE.

No raw SQL text() calls — all queries use SQLAlchemy ORM/core constructs.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Protocol, runtime_checkable

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError, TimeoutError as SATimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.errors import DBPoolExhaustedError, DBQueryError, DBStatementTimeoutError
from app.db.models import TenantConfig

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Port (Protocol)
# ---------------------------------------------------------------------------


@runtime_checkable
class TenantConfigRepositoryPort(Protocol):
    async def get_config(
        self, *, tenant_slug: str, env: str
    ) -> TenantConfig | None: ...

    async def upsert_config(
        self, *, tenant_slug: str, env: str, config: dict[str, Any]
    ) -> TenantConfig: ...


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class SQLAlchemyTenantConfigRepository:
    """SQLAlchemy 2.0 async implementation of TenantConfigRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_config(
        self, *, tenant_slug: str, env: str
    ) -> TenantConfig | None:
        try:
            stmt = select(TenantConfig).where(
                TenantConfig.tenant_slug == tenant_slug,
                TenantConfig.env == env,
            )
            return (await self._session.execute(stmt)).scalar_one_or_none()
        except SATimeoutError as exc:
            raise DBPoolExhaustedError("DB pool exhausted") from exc
        except asyncio.TimeoutError as exc:
            raise DBStatementTimeoutError("Statement timeout") from exc
        except SQLAlchemyError as exc:
            raise DBQueryError("Query failed") from exc

    async def upsert_config(
        self, *, tenant_slug: str, env: str, config: dict[str, Any]
    ) -> TenantConfig:
        try:
            stmt = (
                pg_insert(TenantConfig)
                .values(
                    id=uuid.uuid4(),
                    tenant_slug=tenant_slug,
                    env=env,
                    config=config,
                    version=1,
                )
                .on_conflict_do_update(
                    constraint="uq_tenant_config_slug_env",
                    set_={
                        "config": config,
                        "version": TenantConfig.version + 1,
                        "updated_at": TenantConfig.updated_at,
                    },
                )
                .returning(TenantConfig)
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one()
            await self._session.commit()
            return row
        except SATimeoutError as exc:
            raise DBPoolExhaustedError("DB pool exhausted") from exc
        except asyncio.TimeoutError as exc:
            raise DBStatementTimeoutError("Statement timeout") from exc
        except SQLAlchemyError as exc:
            raise DBQueryError("Query failed") from exc
