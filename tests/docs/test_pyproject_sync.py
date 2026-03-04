"""Tests verifying pyproject.toml extras and markers are documented.

Ensures that optional dependency groups and pytest markers defined in
pyproject.toml appear in the corresponding documentation files. Catches
omissions when new extras or markers are added without updating docs.
"""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
DEPS_DOC = REPO_ROOT / "docs" / "setup" / "dependencies.md"
TESTING_DOC = REPO_ROOT / "docs" / "testing" / "testing-strategy.md"


def load_pyproject():
    """Load and parse pyproject.toml using stdlib tomllib."""
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)


def get_extras():
    """Return list of optional-dependency group names from pyproject.toml."""
    data = load_pyproject()
    return list(data.get("project", {}).get("optional-dependencies", {}).keys())


def get_markers():
    """Return list of pytest marker names from pyproject.toml."""
    data = load_pyproject()
    raw_markers = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    # Markers are formatted as "name: description" — extract just the name
    return [m.split(":")[0].strip() for m in raw_markers]


@pytest.mark.parametrize("extra", get_extras())
def test_extra_documented(extra):
    """Each pyproject.toml optional-dependency group must appear in dependencies.md."""
    content = DEPS_DOC.read_text()
    assert extra in content, (
        f"Optional extra '{extra}' not found in {DEPS_DOC.relative_to(REPO_ROOT)}"
    )


@pytest.mark.parametrize("marker", get_markers())
def test_marker_documented(marker):
    """Each pytest marker must appear in testing-strategy.md."""
    content = TESTING_DOC.read_text()
    assert marker in content, (
        f"Pytest marker '{marker}' not found in {TESTING_DOC.relative_to(REPO_ROOT)}"
    )
