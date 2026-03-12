"""Guardrail ownership and workflow-governance checks."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRE_PR_SCRIPT = PROJECT_ROOT / ".claude" / "scripts" / "pre-commit-validation.sh"
GUARDRAIL_DOC = PROJECT_ROOT / "docs" / "developer" / "guardrails.md"
CONTRIBUTING_DOC = PROJECT_ROOT / "CONTRIBUTING.md"

pytestmark = pytest.mark.ci


def test_pre_pr_script_runs_canonical_enforced_layers() -> None:
    assert PRE_PR_SCRIPT.exists(), f"Pre-PR script not found: {PRE_PR_SCRIPT}"
    source = PRE_PR_SCRIPT.read_text(encoding="utf-8")

    assert "pre-commit validate-config" in source
    assert "pre-commit run --files" in source, (
        "Pre-PR script must run pre-commit on changed files when a diff exists"
    )
    assert "pre-commit run --all-files" in source, (
        "Pre-PR script must fall back to --all-files when no changed files are detected"
    )
    assert 'pytest tests/ci -q --no-cov --override-ini="addopts="' in source
    assert "git ls-files --others --exclude-standard" in source


def test_pre_pr_script_is_not_a_second_policy_engine() -> None:
    assert PRE_PR_SCRIPT.exists(), f"Pre-PR script not found: {PRE_PR_SCRIPT}"
    source = PRE_PR_SCRIPT.read_text(encoding="utf-8")

    banned_fragments = [
        "DICT_ACCESS=",
        "WEAK_CALL_COUNT=",
        "PATCHED_MOCKS=",
        "NARROW_EXCEPT=",
        "LOGURU_NO_TRACEBACK=",
        "ruff check .",
    ]
    for fragment in banned_fragments:
        assert fragment not in source, (
            "The pre-PR script should orchestrate enforced guardrails, not duplicate "
            f"blocking policy. Found banned fragment: {fragment}"
        )
    assert not re.search(r"(?m)^\s*(?:if\s+!\s+)?(?:python(?:3)?\s+-m\s+)?mypy(?:\s|$)", source), (
        "The pre-PR script should orchestrate enforced guardrails, not run mypy directly"
    )


def test_guardrail_docs_define_canonical_homes_and_conventions() -> None:
    assert GUARDRAIL_DOC.exists(), f"Guardrail doc not found: {GUARDRAIL_DOC}"
    source = GUARDRAIL_DOC.read_text(encoding="utf-8")

    required_fragments = [
        ".pre-commit-config.yaml",
        "tests/ci/",
        ".github/workflows/ci.yml",
        ".claude/scripts/pre-commit-validation.sh",
        "result.output",
        "GITHUB_*",
        "pull-requests: read",
    ]
    for fragment in required_fragments:
        assert fragment in source, f"Expected guardrail doc fragment missing: {fragment}"


def test_contributing_points_to_guardrail_workflow() -> None:
    assert CONTRIBUTING_DOC.exists(), f"Contributing doc not found: {CONTRIBUTING_DOC}"
    source = CONTRIBUTING_DOC.read_text(encoding="utf-8")

    assert "docs/developer/guardrails.md" in source
    assert "canonical pre-PR guardrail orchestrator" in source
