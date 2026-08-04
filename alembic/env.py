from __future__ import annotations

import asyncio
from logging.config import fileConfig

# Registers the Vector column type with SQLAlchemy so autogenerate (and
# this env) recognize it - required even though nothing else here calls it.
from pgvector.sqlalchemy import Vector  # noqa: F401
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from src.database.engine import _build_database_url

# Import your models module so Base.metadata is populated with all
# tables before Alembic compares it against the live database schema.
from src.database.models.base import (
    Base,  # <-- adjust import path to match your project
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# If your DB URL comes from settings/env vars rather than alembic.ini,
# set it here instead of hardcoding it in the ini file:
# config.set_main_option("sqlalchemy.url", settings.database_url)
config.set_main_option("sqlalchemy.url", _build_database_url())


def run_migrations_offline() -> None:
    """Generate SQL script without a live DB connection (`alembic upgrade --sql`)."""
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


async def run_migrations_online() -> None:
    """Run migrations using an async engine (asyncpg)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
