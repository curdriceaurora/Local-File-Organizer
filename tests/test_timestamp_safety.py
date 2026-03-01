"""Timestamp safety tests.

Verify that all datetime usage in the codebase produces timezone-aware
datetimes and follows UTC-first conventions.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parent.parent / "src" / "file_organizer"


class TestNaiveDatetimeDetection:
    """Static analysis tests to catch naive datetime patterns."""

    def test_no_naive_datetime_now(self) -> None:
        """No datetime.now() without UTC in source code."""
        result = subprocess.run(
            ["ruff", "check", str(SRC_DIR), "--select", "DTZ005", "--output-format", "concise"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Found naive datetime.now() violations:\n{result.stdout}"
        )

    def test_no_naive_fromtimestamp(self) -> None:
        """No fromtimestamp() without tz= in source code."""
        result = subprocess.run(
            ["ruff", "check", str(SRC_DIR), "--select", "DTZ006", "--output-format", "concise"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Found naive fromtimestamp() violations:\n{result.stdout}"
        )

    def test_no_deprecated_utcnow(self) -> None:
        """No deprecated datetime.utcnow() in source code."""
        result = subprocess.run(
            ["ruff", "check", str(SRC_DIR), "--select", "DTZ003", "--output-format", "concise"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Found deprecated utcnow() violations:\n{result.stdout}"
        )

    def test_no_naive_datetime_constructor(self) -> None:
        """No datetime() without tzinfo in source code."""
        result = subprocess.run(
            ["ruff", "check", str(SRC_DIR), "--select", "DTZ001", "--output-format", "concise"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Found naive datetime() constructor violations:\n{result.stdout}"
        )

    def test_all_dtz_rules_clean(self) -> None:
        """Full DTZ rule suite passes clean."""
        result = subprocess.run(
            ["ruff", "check", str(SRC_DIR), "--select", "DTZ", "--output-format", "concise"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"DTZ violations found:\n{result.stdout}"
        )


class TestGrepPatternAbsence:
    """Grep-based tests for patterns ruff doesn't catch."""

    def _grep_source(self, pattern: str) -> list[str]:
        """Grep source directory for a pattern, return matching lines."""
        result = subprocess.run(
            ["grep", "-rn", "-E", pattern, str(SRC_DIR), "--include=*.py"],
            capture_output=True,
            text=True,
        )
        return [
            line for line in result.stdout.strip().split("\n")
            if line and not line.startswith("Binary")
        ]

    def test_no_isoformat_z_trap(self) -> None:
        """No isoformat()+'Z' without replace (produces invalid +00:00Z)."""
        # Match isoformat() + "Z" but exclude the safe .replace("+00:00", "Z") pattern
        matches = self._grep_source(r'\.isoformat\(\)\s*\+\s*"Z"')
        # Filter out the safe .replace("+00:00", "Z") pattern
        unsafe = [m for m in matches if '.replace("+00:00", "Z")' not in m]
        assert not unsafe, (
            "Found isoformat()+\"Z\" trap (use .replace(\"+00:00\", \"Z\") instead):\n"
            + "\n".join(unsafe)
        )

    def test_no_utcnow_usage(self) -> None:
        """No utcnow() usage anywhere (deprecated in 3.12)."""
        matches = self._grep_source(r"datetime\.utcnow\(\)")
        assert not matches, (
            f"Found deprecated utcnow():\n" + "\n".join(matches)
        )

    def test_no_utcfromtimestamp(self) -> None:
        """No utcfromtimestamp() usage (deprecated in 3.12)."""
        matches = self._grep_source(r"datetime\.utcfromtimestamp\(\)")
        assert not matches, (
            f"Found deprecated utcfromtimestamp():\n" + "\n".join(matches)
        )
