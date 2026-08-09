"""Tests for Alembic migration configuration."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_alembic_upgrade_head_creates_expected_tables(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    db_path = tmp_path / "migrated.db"
    database_url = f"sqlite+pysqlite:///{db_path}"

    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "users",
        "workspaces",
        "organization_jobs",
        "settings_store",
        "plugin_installations",
        "user_sessions",
        "file_metadata",
    }
    assert expected.issubset(tables)


@pytest.mark.unit
def test_running_migrations_does_not_disable_application_loggers(tmp_path: Path) -> None:
    """Migrations must not switch off the rest of the process's logging.

    Regression for #1677. ``alembic/env.py`` calls ``fileConfig()``, whose
    ``disable_existing_loggers`` default is True — that disables every logger
    not named in ``alembic.ini``, which is all of ``file_organizer.*``, for
    the remaining life of the process. Alembic ships that default assuming a
    short-lived CLI process; these migrations also run in-process.

    The visible symptom was two unrelated tests failing only in full-suite
    runs, because their ``caplog`` assertions saw nothing once this module had
    run: ``test_cli_daemon.py::test_log_helper_emits_on_delta`` and
    ``test_cli_main_commands.py::test_durable_move_sweep_failure_is_logged_not_raised``.

    Asserted on ``logger.disabled`` rather than through ``caplog``, because
    ``fileConfig`` also replaces the root handlers — which detaches caplog's
    own handler for the rest of *this* test. That is harmless across tests,
    since the fixture re-attaches per test, and it is not what broke them.
    """
    logger = logging.getLogger("file_organizer.probe_after_migration")
    assert not logger.disabled, "premise: the probe logger starts enabled"
    project_root = Path(__file__).resolve().parents[2]

    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'probe.db'}")
    command.upgrade(config, "head")

    assert not logger.disabled, "migrations disabled an application logger"
