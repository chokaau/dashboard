"""Alembic async migration environment.

URL resolution:
  - Reads DATABASE_URL from environment (never from alembic.ini).
  - In production, the ECS migration task sets DATABASE_URL by fetching
    from DATABASE_SECRET_ARN before invoking `alembic upgrade head`.
  - Locally and in CI, docker-compose sets DATABASE_URL directly.
"""
import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.db.models import Base  # noqa: E402 — must import after sys.path is set

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up loggers from alembic.ini config.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Wire our ORM metadata for autogenerate support.
target_metadata = Base.metadata

# Override sqlalchemy.url from DATABASE_URL environment variable.
# alembic.ini has sqlalchemy.url left blank intentionally — credentials
# must never appear in config files.
database_url = os.environ.get("DATABASE_URL", "")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script output, no DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations online."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
