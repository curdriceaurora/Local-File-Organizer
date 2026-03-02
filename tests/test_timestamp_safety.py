"""Timestamp safety tests.

Verify that all datetime usage in the codebase produces timezone-aware
datetimes and follows UTC-first conventions.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parent.parent / "src" / "file_organizer"


@pytest.mark.unit
class TestDTZRuleCompliance:
    """Static analysis tests using ruff DTZ rules."""

    def test_all_dtz_rules_clean(self) -> None:
        """Full DTZ rule suite passes clean (DTZ001-DTZ007, DTZ011-DTZ012).

        This single test covers all datetime timezone rules:
        - DTZ001: naive datetime() constructor
        - DTZ003: deprecated utcnow()
        - DTZ005: naive datetime.now()
        - DTZ006: naive fromtimestamp()
        - DTZ007: naive strptime() without %z
        - DTZ011: naive datetime.today()
        - DTZ012: naive datetime.utcfromtimestamp()
        """
        result = subprocess.run(
            ["ruff", "check", str(SRC_DIR), "--select", "DTZ", "--output-format", "concise"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"DTZ violations found:\n{result.stdout}"
        )


@pytest.mark.unit
class TestPatternAbsence:
    """Pattern-based tests for issues ruff doesn't catch."""

    @staticmethod
    def _scan_python_files(pattern: re.Pattern[str]) -> list[str]:
        """Scan all Python files in source for a regex pattern.

        Uses pathlib for cross-platform portability (no subprocess grep).
        """
        matches: list[str] = []
        for py_file in SRC_DIR.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(content.splitlines(), start=1):
                    if pattern.search(line):
                        matches.append(f"{py_file}:{i}: {line.strip()}")
            except OSError:
                continue
        return matches

    def test_no_isoformat_z_trap(self) -> None:
        """No isoformat()+'Z' concatenation (produces invalid +00:00Z).

        Safe pattern: .isoformat().replace('+00:00', 'Z')
        Unsafe pattern: .isoformat() + 'Z'
        """
        # Match isoformat() + "Z" but NOT .replace("+00:00", "Z")
        trap_pattern = re.compile(r'\.isoformat\(\)\s*\+\s*["\']Z["\']')
        matches = self._scan_python_files(trap_pattern)
        # Filter out safe .replace() usage
        unsafe = [m for m in matches if ".replace(" not in m]
        assert not unsafe, (
            'Found isoformat()+"Z" trap (use .replace("+00:00", "Z") instead):\n'
            + "\n".join(unsafe)
        )

    def test_no_utcnow_usage(self) -> None:
        """No utcnow() usage anywhere (deprecated in 3.12)."""
        pattern = re.compile(r"datetime\.utcnow\(\)")
        matches = self._scan_python_files(pattern)
        assert not matches, (
            "Found deprecated utcnow():\n" + "\n".join(matches)
        )

    def test_no_utcfromtimestamp(self) -> None:
        """No utcfromtimestamp() usage (deprecated in 3.12)."""
        pattern = re.compile(r"datetime\.utcfromtimestamp\(\)")
        matches = self._scan_python_files(pattern)
        assert not matches, (
            "Found deprecated utcfromtimestamp():\n" + "\n".join(matches)
        )
