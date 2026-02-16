"""Tests for Alembic migration configuration."""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_alembic_upgrade_head_creates_expected_tables(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
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
