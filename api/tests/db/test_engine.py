"""Tests for app/db/engine.py — story 002-002.

TDD: these tests document the expected engine and session factory configuration.
"""
from unittest.mock import MagicMock

import pytest

from app.db.engine import create_db_engine, create_session_factory


# Use a dummy URL — engine creation is lazy, no actual connection is made.
_DUMMY_URL = "postgresql+asyncpg://u:p@localhost:5432/testdb"


def test_create_db_engine_returns_engine():
    engine = create_db_engine(_DUMMY_URL, pool_size=5, max_overflow=2,
                               pool_timeout=10, pool_recycle=1800)
    assert engine is not None


def test_create_db_engine_sets_command_timeout():
    """command_timeout=5 must appear in the connect args baked into the pool creator closure."""
    engine = create_db_engine(_DUMMY_URL, pool_size=5, max_overflow=2,
                               pool_timeout=10, pool_recycle=1800)
    # The connect_args dict is captured in the pool creator closure.
    closure_contents = [
        cell.cell_contents
        for cell in (engine.sync_engine.pool._creator.__closure__ or [])
        if not isinstance(cell.cell_contents, type)  # skip class references
    ] if engine.sync_engine.pool._creator.__closure__ else []
    found = any(
        isinstance(c, dict) and c.get("command_timeout") == 5
        for c in closure_contents
    )
    assert found, f"command_timeout=5 not found in pool creator closure: {closure_contents}"


def test_create_db_engine_sets_pool_pre_ping():
    engine = create_db_engine(_DUMMY_URL, pool_size=5, max_overflow=2,
                               pool_timeout=10, pool_recycle=1800)
    # pool_pre_ping is stored on the engine's sync_engine
    assert engine.sync_engine.pool._pre_ping is True


def test_create_db_engine_pool_size():
    engine = create_db_engine(_DUMMY_URL, pool_size=3, max_overflow=1,
                               pool_timeout=5, pool_recycle=900)
    assert engine.sync_engine.pool.size() == 3


def test_create_session_factory_expire_on_commit_false():
    engine = create_db_engine(_DUMMY_URL, pool_size=5, max_overflow=2,
                               pool_timeout=10, pool_recycle=1800)
    factory = create_session_factory(engine)
    assert factory.kw.get("expire_on_commit") is False
