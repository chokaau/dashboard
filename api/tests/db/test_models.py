"""Tests for app/db/models.py — story 002-003.

TDD: these tests document the expected model structure without requiring a DB.
Migration/schema tests (AC1-AC4) are covered by the Alembic apply in CI
via docker-compose.test.yml (story 002-007).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import inspect as sa_inspect

from app.db.models import Base, BillingUsage, Call, TenantConfig


def test_base_has_three_tables():
    assert set(Base.metadata.tables.keys()) == {"calls", "tenant_config", "billing_usage"}


# ---------------------------------------------------------------------------
# Call model
# ---------------------------------------------------------------------------


def test_call_table_name():
    assert Call.__tablename__ == "calls"


def test_call_has_required_columns():
    mapper = sa_inspect(Call)
    col_names = {c.key for c in mapper.columns}
    required = {
        "id", "tenant_slug", "env", "start_time", "duration_s", "status",
        "intent", "caller_name", "phone_hash", "needs_callback", "summary",
        "has_recording", "created_at", "updated_at",
    }
    assert required.issubset(col_names)


def test_call_has_three_indexes():
    table = Base.metadata.tables["calls"]
    index_names = {idx.name for idx in table.indexes}
    assert "idx_calls_tenant_env_start" in index_names
    assert "idx_calls_tenant_status" in index_names
    assert "idx_calls_tenant_callback" in index_names


def test_call_has_check_constraints():
    table = Base.metadata.tables["calls"]
    constraint_names = {c.name for c in table.constraints}
    assert "ck_calls_status" in constraint_names
    assert "ck_calls_env" in constraint_names


def test_call_instantiation_required_fields():
    """ORM column defaults are insert-time, not __init__ defaults.
    Verify required fields are accepted and columns are not unexpectedly non-null.
    """
    now = datetime.now(timezone.utc)
    call = Call(
        id="test-id",
        tenant_slug="acme",
        env="dev",
        start_time=now,
        status="missed",
        needs_callback=False,
        has_recording=False,
    )
    assert call.id == "test-id"
    assert call.tenant_slug == "acme"
    assert call.status == "missed"


# ---------------------------------------------------------------------------
# TenantConfig model
# ---------------------------------------------------------------------------


def test_tenant_config_table_name():
    assert TenantConfig.__tablename__ == "tenant_config"


def test_tenant_config_has_required_columns():
    mapper = sa_inspect(TenantConfig)
    col_names = {c.key for c in mapper.columns}
    required = {"id", "tenant_slug", "env", "config", "version", "created_at", "updated_at"}
    assert required.issubset(col_names)


def test_tenant_config_has_unique_constraint():
    table = Base.metadata.tables["tenant_config"]
    unique_names = {c.name for c in table.constraints if hasattr(c, "columns")}
    assert "uq_tenant_config_slug_env" in unique_names


def test_tenant_config_column_defaults_are_defined():
    """Verify insert-default values are registered on the column metadata."""
    version_col = TenantConfig.__table__.c["version"]
    config_col = TenantConfig.__table__.c["config"]
    assert version_col.default.arg == 1
    # config default is `dict` (callable) — SQLAlchemy wraps it as CallableColumnDefault
    assert callable(config_col.default.arg)


# ---------------------------------------------------------------------------
# BillingUsage model
# ---------------------------------------------------------------------------


def test_billing_usage_table_name():
    assert BillingUsage.__tablename__ == "billing_usage"


def test_billing_usage_has_required_columns():
    mapper = sa_inspect(BillingUsage)
    col_names = {c.key for c in mapper.columns}
    required = {
        "id", "tenant_slug", "env", "plan", "trial_start",
        "trial_days", "activation_status", "product", "created_at", "updated_at",
    }
    assert required.issubset(col_names)


def test_billing_usage_has_unique_constraint():
    table = Base.metadata.tables["billing_usage"]
    unique_names = {c.name for c in table.constraints if hasattr(c, "columns")}
    assert "uq_billing_tenant_env" in unique_names


def test_billing_usage_has_activation_status_check():
    table = Base.metadata.tables["billing_usage"]
    constraint_names = {c.name for c in table.constraints}
    assert "ck_billing_activation_status" in constraint_names


def test_billing_usage_column_defaults_are_defined():
    """Verify insert-default values are registered on the column metadata."""
    plan_col = BillingUsage.__table__.c["plan"]
    trial_days_col = BillingUsage.__table__.c["trial_days"]
    activation_col = BillingUsage.__table__.c["activation_status"]
    assert plan_col.default.arg == "trial"
    assert trial_days_col.default.arg == 14
    assert activation_col.default.arg == "none"
