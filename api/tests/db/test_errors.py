"""Tests for app/db/errors.py — story 002-001.

TDD: these tests document the expected class hierarchy.
All error types must be subclasses of DBError.
"""
from app.db.errors import (
    DBConnectionError,
    DBError,
    DBMigrationError,
    DBPoolExhaustedError,
    DBQueryError,
    DBStatementTimeoutError,
)


def test_dberror_is_exception():
    assert issubclass(DBError, Exception)


def test_db_connection_error_subclasses_dberror():
    assert issubclass(DBConnectionError, DBError)


def test_db_pool_exhausted_error_subclasses_dberror():
    assert issubclass(DBPoolExhaustedError, DBError)


def test_db_statement_timeout_error_subclasses_dberror():
    assert issubclass(DBStatementTimeoutError, DBError)


def test_db_query_error_subclasses_dberror():
    assert issubclass(DBQueryError, DBError)


def test_db_migration_error_subclasses_dberror():
    assert issubclass(DBMigrationError, DBError)


def test_all_errors_are_distinct_types():
    types = [
        DBConnectionError,
        DBPoolExhaustedError,
        DBStatementTimeoutError,
        DBQueryError,
        DBMigrationError,
    ]
    assert len(set(types)) == len(types)


def test_errors_can_be_raised_and_caught_as_dberror():
    for cls in [DBConnectionError, DBPoolExhaustedError, DBStatementTimeoutError,
                DBQueryError, DBMigrationError]:
        try:
            raise cls("test")
        except DBError:
            pass
        else:
            raise AssertionError(f"{cls} not caught as DBError")
