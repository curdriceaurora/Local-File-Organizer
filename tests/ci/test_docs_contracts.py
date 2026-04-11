"""CI guardrails for documentation-to-code contracts.

These tests encode the canonical correct state of user-facing docs so that
regressions (stale env vars, wrong install extras, missing prerequisites)
are caught at commit time rather than in PR review.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
DESKTOP_README = REPO_ROOT / "desktop" / "README.md"
DESKTOP_DOC = REPO_ROOT / "docs" / "desktop-app.md"
GETTING_STARTED = REPO_ROOT / "docs" / "getting-started.md"
CLI_REFERENCE = REPO_ROOT / "docs" / "cli-reference.md"

pytestmark = pytest.mark.ci


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_readme_quickstart_uses_base_install() -> None:
    """The Ollama quickstart must not force the desktop extra on all users."""
    text = _text(README)
    # Extract just the quickstart section (between "### With Ollama" and next "###")
    start = text.find("### With Ollama (local, default)")
    assert start != -1, "README missing '### With Ollama (local, default)' section heading"
    end = text.find("\n### ", start + 1)
    quickstart_block = text[start:end] if end != -1 else text[start:]
    desktop_pattern = r'pip install -e\s+[\'"]?\.\[[^\]]*desktop[^\]]*\][\'"]?'
    assert not re.search(desktop_pattern, quickstart_block), (
        "README Ollama quickstart must use the base install `pip install -e .`\n"
        "Desktop users can opt in via the extras table below."
    )
    assert "pip install -e ." in quickstart_block, (
        "README Ollama quickstart must include `pip install -e .` (base install)"
    )


def test_provider_quickstarts_set_provider_env_var() -> None:
    """Cloud provider quickstarts must show the FO_PROVIDER env var."""
    text = _text(README)
    assert "FO_PROVIDER=openai" in text, "README missing FO_PROVIDER=openai example"
    assert "FO_PROVIDER=claude" in text, "README missing FO_PROVIDER=claude example"


def test_desktop_contributor_docs_use_canonical_dev_extras() -> None:
    """desktop/README.md (contributor guide) must document the full dev install."""
    text = _text(DESKTOP_README)
    # Accept ".[desktop,web]" or any superset (e.g. ".[desktop,web,dev]")
    has_desktop_web = (
        'pip install -e ".[desktop,web]"' in text or 'pip install -e ".[desktop,web,' in text
    )
    assert has_desktop_web, (
        'desktop/README.md must show `pip install -e ".[desktop,web]"` (or superset)'
    )


@pytest.mark.parametrize("doc", [DESKTOP_DOC, GETTING_STARTED, CLI_REFERENCE])
def test_docs_do_not_reference_removed_ollama_env_var(doc: Path) -> None:
    """FO_OLLAMA_BASE_URL was removed from source — docs must not reference it."""
    assert "FO_OLLAMA_BASE_URL" not in _text(doc), (
        f"{doc.name}: references removed env var FO_OLLAMA_BASE_URL.\n"
        "Remove the row — the Ollama URL is no longer user-configurable via env."
    )


@pytest.mark.parametrize("doc", [DESKTOP_DOC, GETTING_STARTED, CLI_REFERENCE])
def test_linux_desktop_prereqs_are_consistent(doc: Path) -> None:
    """Linux desktop prerequisites must match desktop/README.md (the reference)."""
    text = _text(doc)
    assert "gir1.2-webkit2" in text, (
        f"{doc.name}: missing gir1.2-webkit2 in Linux desktop prerequisites"
    )
    assert "libgirepository1.0-dev" in text, (
        f"{doc.name}: missing libgirepository1.0-dev in Linux desktop prerequisites.\n"
        "Reference: desktop/README.md line 67."
    )
