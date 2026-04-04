"""SQLAlchemy 2.0 ORM models for voice-bff.

Tables:
  calls          — call metadata, partitioned logically by tenant_slug
  tenant_config  — per-tenant config as JSONB
  billing_usage  — billing state per tenant

Data model spec: plans/overview.md §Data Model
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_slug: Mapped[str] = mapped_column(Text, nullable=False, index=False)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_s: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(Text)
    caller_name: Mapped[str | None] = mapped_column(Text)
    phone_hash: Mapped[str | None] = mapped_column(Text)
    needs_callback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    summary: Mapped[str | None] = mapped_column(Text)
    has_recording: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_calls_tenant_env_start", "tenant_slug", "env", "start_time"),
        Index("idx_calls_tenant_status", "tenant_slug", "env", "status"),
        Index("idx_calls_tenant_callback", "tenant_slug", "env", "needs_callback"),
        CheckConstraint(
            "status IN ('missed', 'completed', 'needs-callback')",
            name="ck_calls_status",
        ),
        CheckConstraint(
            "env IN ('dev', 'demo', 'prod')",
            name="ck_calls_env",
        ),
    )


class TenantConfig(Base):
    __tablename__ = "tenant_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_slug: Mapped[str] = mapped_column(Text, nullable=False)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_tenant_config_slug_env", "tenant_slug", "env"),
        UniqueConstraint("tenant_slug", "env", name="uq_tenant_config_slug_env"),
        CheckConstraint(
            "env IN ('dev', 'demo', 'prod')",
            name="ck_tenant_config_env",
        ),
    )


class BillingUsage(Base):
    __tablename__ = "billing_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_slug: Mapped[str] = mapped_column(Text, nullable=False)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[str] = mapped_column(Text, nullable=False, default="trial")
    trial_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    activation_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="none"
    )
    product: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_billing_tenant_env", "tenant_slug", "env"),
        UniqueConstraint("tenant_slug", "env", name="uq_billing_tenant_env"),
        CheckConstraint(
            "activation_status IN ('none', 'pending', 'active')",
            name="ck_billing_activation_status",
        ),
        CheckConstraint(
            "env IN ('dev', 'demo', 'prod')",
            name="ck_billing_env",
        ),
        # plan column intentionally unconstrained — plan types expected to evolve
    )
