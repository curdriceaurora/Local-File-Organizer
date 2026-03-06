"""CI guardrails for package metadata in pyproject.toml."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

PLACEHOLDER_PATTERNS = [
    re.compile(r"yourusername", re.IGNORECASE),
    re.compile(r"your[_-]?name", re.IGNORECASE),
    re.compile(r"example\.com"),
    re.compile(r"placeholder", re.IGNORECASE),
    re.compile(r"TODO", re.IGNORECASE),
    re.compile(r"CHANGEME", re.IGNORECASE),
]


def _load_pyproject() -> dict[str, Any]:
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)


@pytest.mark.ci
class TestPackageMetadata:
    """Validate package metadata is production-ready."""

    def test_pyproject_exists(self) -> None:
        assert PYPROJECT.exists(), "pyproject.toml not found at project root"

    def test_project_name_set(self) -> None:
        data = _load_pyproject()
        name = data.get("project", {}).get("name", "")
        assert name, "project.name is missing"
        assert name != "my-project", "project.name is still a placeholder"

    def test_project_version_set(self) -> None:
        data = _load_pyproject()
        version = data.get("project", {}).get("version", "")
        assert version, "project.version is missing"

    def test_project_description_set(self) -> None:
        data = _load_pyproject()
        desc = data.get("project", {}).get("description", "")
        assert desc, "project.description is missing"
        assert len(desc) >= 10, "project.description is too short"

    def test_urls_no_placeholders(self) -> None:
        data = _load_pyproject()
        urls = data.get("project", {}).get("urls", {})
        assert urls, "project.urls section is missing"

        for label, url in urls.items():
            for pattern in PLACEHOLDER_PATTERNS:
                assert not pattern.search(url), (
                    f"project.urls.{label} contains placeholder pattern '{pattern.pattern}': {url}"
                )

    def test_urls_are_valid(self) -> None:
        data = _load_pyproject()
        urls = data.get("project", {}).get("urls", {})

        for label, url in urls.items():
            parsed = urlparse(url)
            assert parsed.scheme in ("http", "https"), (
                f"project.urls.{label} has invalid scheme: {url}"
            )
            assert parsed.netloc, f"project.urls.{label} has no host: {url}"

    def test_required_url_keys_present(self) -> None:
        data = _load_pyproject()
        urls = data.get("project", {}).get("urls", {})
        required = {"Homepage", "Repository", "Issues"}
        missing = required - set(urls.keys())
        assert not missing, f"Missing required URL keys: {missing}"

    def test_license_set(self) -> None:
        data = _load_pyproject()
        project = data.get("project", {})
        has_license = (
            "license" in project
            or "license-files" in project
            or any(
                (PROJECT_ROOT / name).exists()
                for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
            )
        )
        assert has_license, "No license information found"

    def test_python_requires_set(self) -> None:
        data = _load_pyproject()
        requires = data.get("project", {}).get("requires-python", "")
        assert requires, "project.requires-python is missing"

    def test_classifiers_present(self) -> None:
        data = _load_pyproject()
        classifiers = data.get("project", {}).get("classifiers", [])
        assert len(classifiers) >= 1, "project.classifiers should have at least one entry"
