"""CI coverage tests for atomic-write rail remediations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from file_organizer.config.path_migration import PathMigrator
from file_organizer.daemon.pid import PidFileManager
from file_organizer.events.discovery import ServiceDiscovery
from file_organizer.plugins.sdk.testing import PluginTestCase
from file_organizer.services.copilot.rules.models import RuleSet
from file_organizer.services.copilot.rules.rule_manager import RuleManager

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def test_path_migrator_finalize_writes_audit_log(tmp_path: Path) -> None:
    migrator = PathMigrator(
        legacy_path=tmp_path / "legacy",
        canonical_path=tmp_path / "canonical",
    )

    migrator.finalize_migration()

    audit_path = tmp_path / "canonical" / ".migration-audit.json"
    assert audit_path.exists()
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"


def test_pid_manager_write_pid_writes_value(tmp_path: Path) -> None:
    pid_file = tmp_path / "daemon.pid"

    PidFileManager().write_pid(pid_file, pid=4242)

    assert pid_file.read_text(encoding="utf-8") == "4242"


def test_service_discovery_register_persists_registry(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry" / "services.json"
    discovery = ServiceDiscovery(registry_path=registry_path)

    discovery.register("indexer", "local://indexer:9000")

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert "indexer" in data


def test_plugin_test_case_create_test_file_writes_content() -> None:
    case = PluginTestCase()
    case.setUp()
    try:
        path = case.create_test_file("fixtures/hello.txt", "hello")
        assert path.read_text(encoding="utf-8") == "hello"
    finally:
        case.tearDown()


def test_rule_manager_save_rule_set_writes_yaml(tmp_path: Path) -> None:
    manager = RuleManager(rules_dir=tmp_path / "rules")

    manager.save_rule_set(RuleSet(name="default"))

    saved = tmp_path / "rules" / "default.yaml"
    assert saved.exists()
    assert "name: default" in saved.read_text(encoding="utf-8")
