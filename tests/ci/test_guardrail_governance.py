"""Guardrail ownership and workflow-governance checks."""

from __future__ import annotations

import re
import shlex
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRE_PR_SCRIPT = PROJECT_ROOT / "scripts" / "dev" / "pre-commit-validation.sh"
GUARDRAIL_DOC = PROJECT_ROOT / "docs" / "developer" / "guardrails.md"
CONTRIBUTING_DOC = PROJECT_ROOT / "CONTRIBUTING.md"
RAILS_REGISTRY = PROJECT_ROOT / "scripts" / "ci" / "rails.toml"
SECURITY_DOC = PROJECT_ROOT / "SECURITY.md"

pytestmark = pytest.mark.ci


def _canonical_commands_from_script(source: str) -> list[str]:
    commands: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped.startswith("run_step "):
            continue

        parts = shlex.split(stripped)
        command = " ".join(parts[2:])
        command = command.replace("${changed_files[@]}", "<changed-files>")
        command = command.replace("--override-ini=addopts=", '--override-ini="addopts="')
        commands.append(command)

    return commands


def _canonical_commands_from_docs(source: str) -> list[str]:
    section_match = re.search(
        r"## Canonical Pre-PR Flow\n(?P<section>.*?)(?:\n## |\Z)",
        source,
        flags=re.DOTALL,
    )
    assert section_match, "Guardrail doc must define a Canonical Pre-PR Flow section"

    commands = re.findall(r"(?m)^\d+\.\s+`([^`]+)`", section_match.group("section"))
    assert commands, "Canonical Pre-PR Flow section must enumerate the command list"
    return commands


def test_pre_pr_script_runs_canonical_enforced_layers() -> None:
    assert PRE_PR_SCRIPT.exists(), f"Pre-PR script not found: {PRE_PR_SCRIPT}"
    source = PRE_PR_SCRIPT.read_text(encoding="utf-8")
    commands = _canonical_commands_from_script(source)

    assert commands == [
        "pre-commit validate-config",
        "pre-commit run --all-files",
        'pytest tests/ci -q --no-cov --override-ini="addopts="',
    ]
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
    assert PRE_PR_SCRIPT.exists(), f"Pre-PR script not found: {PRE_PR_SCRIPT}"
    source = GUARDRAIL_DOC.read_text(encoding="utf-8")
    script_commands = _canonical_commands_from_script(PRE_PR_SCRIPT.read_text(encoding="utf-8"))
    doc_commands = _canonical_commands_from_docs(source)

    required_fragments = [
        ".pre-commit-config.yaml",
        "tests/ci/",
        ".github/workflows/ci.yml",
        "scripts/dev/pre-commit-validation.sh",
        "tests/ci/test_api_compat_guardrails.py",
        "tests/ci/test_daemon_pid_guardrails.py",
        "tests/ci/test_filesystem_link_copy_guardrails.py",
        "from file_organizer.review_regressions.api_compat import",
        "legacy-positional-prefix-changed",
        "new-optional-param-must-be-keyword-only",
        "allowlisted-callable-missing",
        "result.output",
        "GITHUB_*",
        "pull-requests: read",
    ]
    for fragment in required_fragments:
        assert fragment in source, f"Expected guardrail doc fragment missing: {fragment}"

    assert doc_commands == script_commands, (
        "Canonical Pre-PR Flow docs must match the orchestrator command list in order"
    )


def test_contributing_points_to_guardrail_workflow() -> None:
    assert CONTRIBUTING_DOC.exists(), f"Contributing doc not found: {CONTRIBUTING_DOC}"
    source = CONTRIBUTING_DOC.read_text(encoding="utf-8")

    assert "docs/developer/guardrails.md" in source
    assert "canonical pre-PR guardrail orchestrator" in source


def _parse_rail_status_table(source: str) -> dict[str, str]:
    section_match = re.search(
        r"## CI-Enforced Lint Rails\n(?P<section>.*?)(?:\n\n[A-Z#]|\Z)",
        source,
        flags=re.DOTALL,
    )
    assert section_match, "Doc must define a CI-Enforced Lint Rails section"

    rows = re.findall(
        r"^\| `([^`]+)` \| [^|]+ \| (advisory|enforced) \|$",
        section_match.group("section"),
        flags=re.MULTILINE,
    )
    names = [name for name, _ in rows]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"Rail status table has duplicate rows for: {duplicates}"

    return {name: ("enforce" if status == "enforced" else status) for name, status in rows}


def _parse_known_limitations_advisory_rails(source: str) -> set[str]:
    section_match = re.search(
        r"## Known Limitations\n(?P<section>.*?)(?:\n## |\Z)",
        source,
        flags=re.DOTALL,
    )
    assert section_match, "Doc must define a Known Limitations section"

    # "remains?" tolerates both "remain advisory" (2+ rails) and "remains advisory"
    # (exactly 1 rail) — the count-dependent verb shouldn't need a prose rewrite.
    remain_advisory_match = re.search(
        r"remains? advisory \((?P<names>.*?)\)",
        section_match.group("section"),
        flags=re.DOTALL,
    )
    assert remain_advisory_match, "Known Limitations must name the rails that remain advisory"

    return set(re.findall(r"`([^`]+)`", remain_advisory_match.group("names")))


def test_security_rail_status_table_matches_registry() -> None:
    assert RAILS_REGISTRY.exists(), f"Rail registry not found: {RAILS_REGISTRY}"
    assert SECURITY_DOC.exists(), f"Security doc not found: {SECURITY_DOC}"

    registry = tomllib.loads(RAILS_REGISTRY.read_text(encoding="utf-8"))
    expected_modes = {rail["name"]: rail["mode"] for rail in registry["rail"]}

    source = SECURITY_DOC.read_text(encoding="utf-8")
    table_modes = _parse_rail_status_table(source)
    assert table_modes == expected_modes


def test_api_compat_rules_are_not_duplicated_in_shell_orchestrator() -> None:
    assert PRE_PR_SCRIPT.exists(), f"Pre-PR script not found: {PRE_PR_SCRIPT}"
    source = PRE_PR_SCRIPT.read_text(encoding="utf-8")

    for rule_id in (
        "legacy-positional-prefix-changed",
        "new-optional-param-must-be-keyword-only",
        "allowlisted-callable-missing",
    ):
        assert rule_id not in source, (
            "API-compat semantic policy must stay in tests/ci, not in the shell orchestrator. "
            f"Found rule id in script: {rule_id}"
        )


def test_rail_status_table_rejects_duplicate_rows_for_same_rail() -> None:
    source = (
        "## CI-Enforced Lint Rails\n\n"
        "| Rail | What it flags | Status |\n"
        "|---|---|---|\n"
        "| `rail-a` | thing | enforced |\n"
        "| `rail-a` | thing again | advisory |\n"
    )
    with pytest.raises(AssertionError, match="duplicate"):
        _parse_rail_status_table(source)


def test_rail_status_table_ignores_prose_mentions_outside_table_rows() -> None:
    source = (
        "## CI-Enforced Lint Rails\n\n"
        "| Rail | What it flags | Status |\n"
        "|---|---|---|\n"
        "| `rail-a` | thing | enforced |\n"
        "see also `rail-b`, which has no table row yet.\n"
    )
    assert _parse_rail_status_table(source) == {"rail-a": "enforce"}


def test_rail_status_table_detects_missing_row() -> None:
    source = (
        "## CI-Enforced Lint Rails\n\n"
        "| Rail | What it flags | Status |\n"
        "|---|---|---|\n"
        "| `rail-a` | thing | enforced |\n"
    )
    table_modes = _parse_rail_status_table(source)
    assert "rail-b" not in table_modes
    registry_modes = {"rail-a": "enforce", "rail-b": "advisory"}
    assert table_modes != registry_modes


def test_known_limitations_advisory_rails_match_registry() -> None:
    assert RAILS_REGISTRY.exists(), f"Rail registry not found: {RAILS_REGISTRY}"
    assert SECURITY_DOC.exists(), f"Security doc not found: {SECURITY_DOC}"

    registry = tomllib.loads(RAILS_REGISTRY.read_text(encoding="utf-8"))
    expected_advisory = {rail["name"] for rail in registry["rail"] if rail["mode"] == "advisory"}

    source = SECURITY_DOC.read_text(encoding="utf-8")
    assert _parse_known_limitations_advisory_rails(source) == expected_advisory


def test_known_limitations_detects_newly_added_advisory_rail() -> None:
    source = (
        "## Known Limitations\n\n- Two lint rails above remain advisory (`rail-a` and `rail-b`).\n"
    )
    doc_advisory = _parse_known_limitations_advisory_rails(source)
    assert doc_advisory == {"rail-a", "rail-b"}
    registry_advisory = {"rail-a", "rail-b", "rail-c"}
    assert doc_advisory != registry_advisory


def test_known_limitations_detects_newly_promoted_enforced_rail() -> None:
    source = "## Known Limitations\n\n- One lint rail above remains advisory (`rail-a`).\n"
    doc_advisory = _parse_known_limitations_advisory_rails(source)
    assert doc_advisory == {"rail-a"}
    registry_advisory: set[str] = set()
    assert doc_advisory != registry_advisory
