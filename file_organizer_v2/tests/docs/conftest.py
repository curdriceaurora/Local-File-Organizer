"""Shared fixtures for documentation accuracy tests.

These tests verify that the documentation matches the actual implementation
by comparing documented paths, auth formats, and examples against the code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Project path fixtures
# ---------------------------------------------------------------------------

DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
SRC_DIR = Path(__file__).parent.parent.parent / "src"
MKDOCS_FILE = Path(__file__).parent.parent.parent / "mkdocs.yml"


@pytest.fixture(scope="session")
def docs_dir() -> Path:
    """Return the docs directory."""
    return DOCS_DIR


@pytest.fixture(scope="session")
def mkdocs_config() -> dict:
    """Load and return the mkdocs.yml configuration.

    mkdocs.yml may contain Python-tagged YAML nodes (e.g. !!python/name:...)
    that yaml.safe_load cannot parse. We strip those tags before loading so
    that nav validation still works without requiring the full MkDocs install.
    """
    assert MKDOCS_FILE.exists(), f"mkdocs.yml not found at {MKDOCS_FILE}"
    raw = MKDOCS_FILE.read_text(encoding="utf-8")
    # Strip !!python/name:* tags that are valid MkDocs YAML but break safe_load
    sanitized = re.sub(r"!!python/\S+", "", raw)
    return yaml.safe_load(sanitized)


@pytest.fixture(scope="session")
def all_doc_files(docs_dir: Path) -> list[Path]:
    """Return all markdown files under the docs directory."""
    return list(docs_dir.rglob("*.md"))


# ---------------------------------------------------------------------------
# Route extraction helpers
# ---------------------------------------------------------------------------


def get_router_paths(router) -> set[str]:
    """Extract all route paths from a FastAPI APIRouter."""
    paths = set()
    for route in router.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
    return paths


def extract_paths_from_markdown(content: str) -> list[str]:
    """Extract API paths (e.g. /api/v1/...) from markdown code blocks."""
    # Match paths in code blocks — look for /api/v1/ patterns
    pattern = r"(/api/v\d+/[^\s\'\"\)]+)"
    return re.findall(pattern, content)


def extract_code_blocks(content: str, lang: str = "") -> list[str]:
    """Extract fenced code blocks from markdown, optionally filtered by language."""
    if lang:
        pattern = rf"```{lang}\n(.*?)```"
    else:
        pattern = r"```(?:\w+)?\n(.*?)```"
    return re.findall(pattern, content, re.DOTALL)


def extract_all_links(content: str) -> list[str]:
    """Extract all markdown links [text](path) from content."""
    # Matches [text](path) — exclude http(s) external links
    pattern = r"\[(?:[^\]]+)\]\(([^)]+)\)"
    all_links = re.findall(pattern, content)
    # Filter to only relative/internal links
    return [
        link
        for link in all_links
        if not link.startswith("http://") and not link.startswith("https://")
    ]
