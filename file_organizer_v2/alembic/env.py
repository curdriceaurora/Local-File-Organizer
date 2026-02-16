"""Alembic migration environment for File Organizer API models."""
from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# Ensure all model tables are registered on Base.metadata before migration runs.
import file_organizer.api.db_models  # noqa: F401
from alembic import context
from file_organizer.api.auth_models import Base
from file_organizer.api.database import resolve_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_database_url() -> str:
    env_database = os.getenv("FO_API_DATABASE_URL")
    if env_database:
        return resolve_database_url(env_database)

    configured = config.get_main_option("sqlalchemy.url")
    return resolve_database_url(configured)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _get_database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
