"""Unit tests for .claude/scripts/generate-integration-floors.py and
check-integration-floors.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "scripts"
GENERATE_SCRIPT = SCRIPTS_DIR / "generate-integration-floors.py"
CHECK_SCRIPT = SCRIPTS_DIR / "check-integration-floors.py"


def make_coverage_json(files: dict[str, dict]) -> dict:
    """Build a minimal coverage.json structure."""
    return {
        "files": {
            path: {
                "summary": {
                    "num_statements": info.get("stmts", 10),
                    "num_branches": info.get("branches", 4),
                    "covered_lines": info.get("hit_lines", 0),
                    "covered_branches": info.get("hit_branches", 0),
                }
            }
            for path, info in files.items()
        }
    }


def make_pyproject_toml(floors: dict[str, int] | None = None) -> str:
    lines = [
        "[tool.pytest.ini_options]",
        'addopts = "--cov-fail-under=95"',
        "",
        "[tool.coverage.run]",
        'source = ["src"]',
        "",
    ]
    if floors is not None:
        lines.append("[tool.coverage.floors.integration]")
        for path, floor in sorted(floors.items()):
            lines.append(f'"{path}" = {floor}')
    return "\n".join(lines) + "\n"


@pytest.mark.unit
class TestGenerateScript:
    def test_creates_floors_section_from_scratch(self, tmp_path: Path) -> None:
        """generate script creates [tool.coverage.floors.integration] when absent."""
        cov = make_coverage_json(
            {
                "src/file_organizer/api/auth.py": {
                    "stmts": 100,
                    "branches": 20,
                    "hit_lines": 84,
                    "hit_branches": 17,
                },
            }
        )
        (tmp_path / ".coverage-integration.json").write_text(json.dumps(cov))
        (tmp_path / "pyproject.toml").write_text(make_pyproject_toml())

        result = subprocess.run(
            [
                sys.executable,
                str(GENERATE_SCRIPT),
                "--json",
                ".coverage-integration.json",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        text = (tmp_path / "pyproject.toml").read_text()
        assert "[tool.coverage.floors.integration]" in text
        # pct = (84+17)/(100+20)*100 = 84.16% → floor = int(84.16//5)*5 = 80
        assert '"src/file_organizer/api/auth.py" = 80' in text

    def test_never_auto_downgrades_existing_floor(self, tmp_path: Path) -> None:
        """generate script keeps existing floor if higher than computed value."""
        cov = make_coverage_json(
            {
                "src/file_organizer/api/auth.py": {
                    "stmts": 10,
                    "branches": 0,
                    "hit_lines": 7,
                    "hit_branches": 0,
                },
            }
        )
        (tmp_path / ".coverage-integration.json").write_text(json.dumps(cov))
        # Existing floor = 90, computed = int(70//5)*5 = 70 — should keep 90
        (tmp_path / "pyproject.toml").write_text(
            make_pyproject_toml({"src/file_organizer/api/auth.py": 90})
        )

        result = subprocess.run(
            [
                sys.executable,
                str(GENERATE_SCRIPT),
                "--json",
                ".coverage-integration.json",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        text = (tmp_path / "pyproject.toml").read_text()
        assert '"src/file_organizer/api/auth.py" = 90' in text

    def test_keys_are_sorted_alphabetically(self, tmp_path: Path) -> None:
        """generate script writes keys in alphabetical order."""
        cov = make_coverage_json(
            {
                "src/file_organizer/zzz.py": {
                    "stmts": 10,
                    "branches": 0,
                    "hit_lines": 10,
                    "hit_branches": 0,
                },
                "src/file_organizer/aaa.py": {
                    "stmts": 10,
                    "branches": 0,
                    "hit_lines": 10,
                    "hit_branches": 0,
                },
            }
        )
        (tmp_path / ".coverage-integration.json").write_text(json.dumps(cov))
        (tmp_path / "pyproject.toml").write_text(make_pyproject_toml())

        subprocess.run(
            [
                sys.executable,
                str(GENERATE_SCRIPT),
                "--json",
                ".coverage-integration.json",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            check=True,
        )
        text = (tmp_path / "pyproject.toml").read_text()
        aaa_pos = text.index("aaa.py")
        zzz_pos = text.index("zzz.py")
        assert aaa_pos < zzz_pos, "Keys must be sorted alphabetically"

    def test_flags_stale_entries_to_stderr(self, tmp_path: Path) -> None:
        """generate script prints stale entry to stderr but keeps it in the table."""
        cov = make_coverage_json(
            {
                "src/file_organizer/api/auth.py": {
                    "stmts": 10,
                    "branches": 0,
                    "hit_lines": 8,
                    "hit_branches": 0,
                },
            }
        )
        (tmp_path / ".coverage-integration.json").write_text(json.dumps(cov))
        # deleted.py is in the table but not in coverage JSON
        (tmp_path / "pyproject.toml").write_text(
            make_pyproject_toml(
                {
                    "src/file_organizer/api/auth.py": 75,
                    "src/file_organizer/deleted.py": 50,
                }
            )
        )

        result = subprocess.run(
            [
                sys.executable,
                str(GENERATE_SCRIPT),
                "--json",
                ".coverage-integration.json",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "STALE" in result.stderr
        assert "deleted.py" in result.stderr
        # Stale entry preserved
        text = (tmp_path / "pyproject.toml").read_text()
        assert "deleted.py" in text


@pytest.mark.unit
class TestCheckScript:
    def test_passes_when_all_floors_met(self, tmp_path: Path) -> None:
        """check script exits 0 when all files meet their floors."""
        cov = make_coverage_json(
            {
                "src/file_organizer/api/auth.py": {
                    "stmts": 100,
                    "branches": 20,
                    "hit_lines": 90,
                    "hit_branches": 18,
                },
            }
        )
        # pct = (90+18)/(100+20)*100 = 90% → floor 90 should pass
        (tmp_path / ".coverage-integration.json").write_text(json.dumps(cov))
        (tmp_path / "pyproject.toml").write_text(
            make_pyproject_toml({"src/file_organizer/api/auth.py": 90})
        )
        result = subprocess.run(
            [
                sys.executable,
                str(CHECK_SCRIPT),
                "--json",
                ".coverage-integration.json",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_fails_when_file_below_floor(self, tmp_path: Path) -> None:
        """check script exits 1 when a file is below its floor."""
        cov = make_coverage_json(
            {
                "src/file_organizer/api/auth.py": {
                    "stmts": 10,
                    "branches": 0,
                    "hit_lines": 6,
                    "hit_branches": 0,
                },
            }
        )
        # pct = 60%, floor = 70 → violation
        (tmp_path / ".coverage-integration.json").write_text(json.dumps(cov))
        (tmp_path / "pyproject.toml").write_text(
            make_pyproject_toml({"src/file_organizer/api/auth.py": 70})
        )
        result = subprocess.run(
            [
                sys.executable,
                str(CHECK_SCRIPT),
                "--json",
                ".coverage-integration.json",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "BELOW FLOOR" in result.stderr
        assert "auth.py" in result.stderr

    def test_fails_when_covered_file_missing_entry(self, tmp_path: Path) -> None:
        """check script exits 1 when a covered file has no floor entry."""
        cov = make_coverage_json(
            {
                "src/file_organizer/api/new_module.py": {
                    "stmts": 10,
                    "branches": 0,
                    "hit_lines": 8,
                    "hit_branches": 0,
                },
            }
        )
        (tmp_path / ".coverage-integration.json").write_text(json.dumps(cov))
        (tmp_path / "pyproject.toml").write_text(make_pyproject_toml({}))
        result = subprocess.run(
            [
                sys.executable,
                str(CHECK_SCRIPT),
                "--json",
                ".coverage-integration.json",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "MISSING FLOOR" in result.stderr

    def test_fails_when_stale_entry_in_table(self, tmp_path: Path) -> None:
        """check script exits 1 when floors table has an entry absent from coverage."""
        cov = make_coverage_json(
            {
                "src/file_organizer/api/auth.py": {
                    "stmts": 10,
                    "branches": 0,
                    "hit_lines": 9,
                    "hit_branches": 0,
                },
            }
        )
        (tmp_path / ".coverage-integration.json").write_text(json.dumps(cov))
        (tmp_path / "pyproject.toml").write_text(
            make_pyproject_toml(
                {
                    "src/file_organizer/api/auth.py": 85,
                    "src/file_organizer/deleted.py": 50,
                }
            )
        )
        result = subprocess.run(
            [
                sys.executable,
                str(CHECK_SCRIPT),
                "--json",
                ".coverage-integration.json",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "STALE" in result.stderr

    def test_floor_zero_skips_threshold_check(self, tmp_path: Path) -> None:
        """check script does not fail a file whose floor is 0."""
        cov = make_coverage_json(
            {
                "src/file_organizer/tui/audio_view.py": {
                    "stmts": 50,
                    "branches": 10,
                    "hit_lines": 5,
                    "hit_branches": 1,
                },
            }
        )
        (tmp_path / ".coverage-integration.json").write_text(json.dumps(cov))
        (tmp_path / "pyproject.toml").write_text(
            make_pyproject_toml({"src/file_organizer/tui/audio_view.py": 0})
        )
        result = subprocess.run(
            [
                sys.executable,
                str(CHECK_SCRIPT),
                "--json",
                ".coverage-integration.json",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
