"""Billing repository — ports-and-adapters pattern.

BillingRepositoryPort          — Protocol (port).
SQLAlchemyBillingRepository    — Adapter: SQLAlchemy 2.0 async + PostgreSQL
                                  INSERT ... ON CONFLICT DO UPDATE.

No raw SQL text() calls — all queries use SQLAlchemy ORM/core constructs.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Protocol, runtime_checkable

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError, TimeoutError as SATimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.errors import DBPoolExhaustedError, DBQueryError, DBStatementTimeoutError
from app.db.models import BillingUsage

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Port (Protocol)
# ---------------------------------------------------------------------------


@runtime_checkable
class BillingRepositoryPort(Protocol):
    async def get_billing(
        self, *, tenant_slug: str, env: str
    ) -> BillingUsage | None: ...

    async def upsert_billing(self, row: BillingUsage) -> BillingUsage: ...


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class SQLAlchemyBillingRepository:
    """SQLAlchemy 2.0 async implementation of BillingRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_billing(
        self, *, tenant_slug: str, env: str
    ) -> BillingUsage | None:
        try:
            stmt = select(BillingUsage).where(
                BillingUsage.tenant_slug == tenant_slug,
                BillingUsage.env == env,
            )
            return (await self._session.execute(stmt)).scalar_one_or_none()
        except SATimeoutError as exc:
            raise DBPoolExhaustedError("DB pool exhausted") from exc
        except asyncio.TimeoutError as exc:
            raise DBStatementTimeoutError("Statement timeout") from exc
        except SQLAlchemyError as exc:
            raise DBQueryError("Query failed") from exc

    async def upsert_billing(self, row: BillingUsage) -> BillingUsage:
        try:
            stmt = (
                pg_insert(BillingUsage)
                .values(
                    id=row.id if row.id is not None else uuid.uuid4(),
                    tenant_slug=row.tenant_slug,
                    env=row.env,
                    plan=row.plan,
                    trial_start=row.trial_start,
                    trial_days=row.trial_days,
                    activation_status=row.activation_status,
                    product=row.product,
                )
                .on_conflict_do_update(
                    constraint="uq_billing_tenant_env",
                    set_={
                        "plan": row.plan,
                        "trial_start": row.trial_start,
                        "trial_days": row.trial_days,
                        "activation_status": row.activation_status,
                        "product": row.product,
                        "updated_at": func.now(),
                    },
                )
                .returning(BillingUsage)
            )
            result = await self._session.execute(stmt)
            upserted = result.scalar_one()
            return upserted
        except SATimeoutError as exc:
            raise DBPoolExhaustedError("DB pool exhausted") from exc
        except asyncio.TimeoutError as exc:
            raise DBStatementTimeoutError("Statement timeout") from exc
        except SQLAlchemyError as exc:
            raise DBQueryError("Query failed") from exc
