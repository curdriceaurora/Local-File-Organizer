"""CLI tests for marketplace commands."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app
from file_organizer.plugins.marketplace import compute_sha256

pytestmark = pytest.mark.ci

runner = CliRunner()


def _prepare_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    archive = repo_dir / "cli-plugin-1.0.0.zip"
    with zipfile.ZipFile(archive, "w") as zipf:
        zipf.writestr(
            "plugin.py",
            "\n".join(
                [
                    "from file_organizer.plugins import Plugin, PluginMetadata",
                    "",
                    "class CliPlugin(Plugin):",
                    "    def get_metadata(self):",
                    "        return PluginMetadata(name='cli-plugin', version='1.0.0', author='tests', description='cli plugin')",
                    "    def on_load(self): pass",
                    "    def on_enable(self): pass",
                    "    def on_disable(self): pass",
                    "    def on_unload(self): pass",
                ]
            ),
        )
    payload = {
        "plugins": [
            {
                "name": "cli-plugin",
                "version": "1.0.0",
                "author": "tests",
                "description": "CLI plugin",
                "download_url": archive.name,
                "checksum_sha256": compute_sha256(archive),
                "size_bytes": archive.stat().st_size,
                "dependencies": [],
                "tags": ["cli"],
                "category": "utility",
                "license": "MIT",
                "min_organizer_version": "2.0.0",
                "max_organizer_version": None,
                "downloads": 1,
                "rating": 4.2,
                "reviews_count": 2,
            }
        ]
    }
    (repo_dir / "index.json").write_text(json.dumps(payload), encoding="utf-8")


def test_marketplace_help() -> None:
    result = runner.invoke(app, ["marketplace", "--help"])
    assert result.exit_code == 0
    assert "Browse and manage marketplace plugins" in result.output


def test_marketplace_list_and_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_dir = tmp_path / "repo"
    _prepare_repo(repo_dir)
    monkeypatch.setenv("FO_MARKETPLACE_HOME", str(tmp_path / "marketplace-home"))
    monkeypatch.setenv("FO_MARKETPLACE_REPO_URL", str(repo_dir))

    listed = runner.invoke(app, ["marketplace", "list"])
    assert listed.exit_code == 0
    assert "cli-plugin" in listed.output

    installed = runner.invoke(app, ["marketplace", "install", "cli-plugin"])
    assert installed.exit_code == 0
    assert "Installed" in installed.output

    installed_list = runner.invoke(app, ["marketplace", "installed"])
    assert installed_list.exit_code == 0
    assert "cli-plugin" in installed_list.output
