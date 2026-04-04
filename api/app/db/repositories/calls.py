"""Call repository — ports-and-adapters pattern.

CallRepositoryPort   — Protocol (port): defines the interface.
SQLAlchemyCallRepository — Adapter: SQLAlchemy 2.0 async implementation.

list_calls and get_call are fully implemented.
upsert_call and bulk_upsert are stubbed (NotImplementedError) — completed in
story 003-002.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError, TimeoutError as SATimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.errors import DBPoolExhaustedError, DBQueryError, DBStatementTimeoutError
from app.db.models import Call

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class CallListResult:
    calls: list[Call]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Port (Protocol)
# ---------------------------------------------------------------------------


@runtime_checkable
class CallRepositoryPort(Protocol):
    async def list_calls(
        self,
        *,
        tenant_slug: str,
        env: str,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> CallListResult: ...

    async def get_call(
        self,
        *,
        call_id: str,
        tenant_slug: str,
        env: str,
    ) -> Call | None: ...

    async def upsert_call(self, call: Call) -> Call: ...

    async def bulk_upsert(self, calls: Sequence[Call]) -> int: ...


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class SQLAlchemyCallRepository:
    """SQLAlchemy 2.0 async implementation of CallRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_calls(
        self,
        *,
        tenant_slug: str,
        env: str,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> CallListResult:
        try:
            # Base filter — always applied
            base_filter = [
                Call.tenant_slug == tenant_slug,
                Call.env == env,
            ]
            if status is not None:
                base_filter.append(Call.status == status)

            # COUNT subquery
            count_stmt = select(func.count()).select_from(Call).where(*base_filter)
            total: int = (await self._session.execute(count_stmt)).scalar_one()

            # Data query with pagination
            offset = (page - 1) * page_size
            data_stmt = (
                select(Call)
                .where(*base_filter)
                .order_by(Call.start_time.desc())
                .offset(offset)
                .limit(page_size)
            )
            rows: list[Call] = list(
                (await self._session.execute(data_stmt)).scalars().all()
            )

            return CallListResult(
                calls=rows,
                total=total,
                page=page,
                page_size=page_size,
            )
        except SATimeoutError as exc:
            raise DBPoolExhaustedError("DB pool exhausted") from exc
        except asyncio.TimeoutError as exc:
            raise DBStatementTimeoutError("Statement timeout") from exc
        except SQLAlchemyError as exc:
            raise DBQueryError("Query failed") from exc

    async def get_call(
        self,
        *,
        call_id: str,
        tenant_slug: str,
        env: str,
    ) -> Call | None:
        try:
            stmt = select(Call).where(
                Call.id == call_id,
                Call.tenant_slug == tenant_slug,
                Call.env == env,
            )
            return (await self._session.execute(stmt)).scalar_one_or_none()
        except SATimeoutError as exc:
            raise DBPoolExhaustedError("DB pool exhausted") from exc
        except asyncio.TimeoutError as exc:
            raise DBStatementTimeoutError("Statement timeout") from exc
        except SQLAlchemyError as exc:
            raise DBQueryError("Query failed") from exc

    async def upsert_call(self, call: Call) -> Call:
        try:
            stmt = (
                pg_insert(Call)
                .values(
                    id=call.id,
                    tenant_slug=call.tenant_slug,
                    env=call.env,
                    start_time=call.start_time,
                    duration_s=call.duration_s,
                    status=call.status,
                    intent=call.intent,
                    caller_name=call.caller_name,
                    phone_hash=call.phone_hash,
                    needs_callback=call.needs_callback,
                    summary=call.summary,
                    has_recording=call.has_recording,
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_=dict(
                        status=call.status,
                        duration_s=call.duration_s,
                        caller_name=call.caller_name,
                        needs_callback=call.needs_callback,
                        summary=call.summary,
                        has_recording=call.has_recording,
                        updated_at=func.now(),
                    ),
                )
            )
            await self._session.execute(stmt)
            return call
        except SATimeoutError as exc:
            raise DBPoolExhaustedError("DB pool exhausted") from exc
        except asyncio.TimeoutError as exc:
            raise DBStatementTimeoutError("Statement timeout") from exc
        except SQLAlchemyError as exc:
            raise DBQueryError("Query failed") from exc

    async def bulk_upsert(self, calls: Sequence[Call]) -> int:
        if not calls:
            return 0
        try:
            stmt = (
                pg_insert(Call)
                .values(
                    [
                        dict(
                            id=c.id,
                            tenant_slug=c.tenant_slug,
                            env=c.env,
                            start_time=c.start_time,
                            duration_s=c.duration_s,
                            status=c.status,
                            intent=c.intent,
                            caller_name=c.caller_name,
                            phone_hash=c.phone_hash,
                            needs_callback=c.needs_callback,
                            summary=c.summary,
                            has_recording=c.has_recording,
                        )
                        for c in calls
                    ]
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            result = await self._session.execute(stmt)
            return result.rowcount
        except SATimeoutError as exc:
            raise DBPoolExhaustedError("DB pool exhausted") from exc
        except asyncio.TimeoutError as exc:
            raise DBStatementTimeoutError("Statement timeout") from exc
        except SQLAlchemyError as exc:
            raise DBQueryError("Query failed") from exc
