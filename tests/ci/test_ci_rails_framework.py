"""Tests for the WP-0.1 advisory CI-rail framework (#1222).

Exercises ``.claude/scripts/ci_rails.py``: registry parsing, advisory vs.
enforce semantics, the ``--enforce-all`` override, and the empty-registry
no-op. No real rails exist yet (WP-6.x adds them), so these tests register
synthetic rails whose commands deterministically pass/fail.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_RUNNER = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "ci_rails.py"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ci_rails_under_test", _RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve the module via sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ci_rails = _load_runner()

# Commands that deterministically pass / fail via the test interpreter.
_PASS = [sys.executable, "-c", "import sys; sys.exit(0)"]
_FAIL = [sys.executable, "-c", "import sys; sys.exit(3)"]


def _toml_command(command: list[str]) -> str:
    parts = ", ".join(repr(part) for part in command)
    return f"[{parts}]"


def _write_registry(tmp_path: Path, rails: list[tuple[str, list[str], str]]) -> Path:
    blocks = []
    for name, command, mode in rails:
        blocks.append(
            f'[[rail]]\nname = "{name}"\ncommand = {_toml_command(command)}\nmode = "{mode}"\n'
        )
    registry = tmp_path / "ci-rails.toml"
    registry.write_text("\n".join(blocks), encoding="utf-8")
    return registry


def test_missing_registry_is_noop() -> None:
    assert ci_rails.load_rails(Path("/nonexistent/ci-rails.toml")) == []
    assert ci_rails.main(["--registry", "/nonexistent/ci-rails.toml"]) == 0


def test_empty_registry_is_noop(tmp_path: Path) -> None:
    registry = tmp_path / "ci-rails.toml"
    registry.write_text("# no rails\n", encoding="utf-8")
    assert ci_rails.load_rails(registry) == []
    assert ci_rails.main(["--registry", str(registry)]) == 0


def test_load_defaults_mode_to_advisory(tmp_path: Path) -> None:
    registry = tmp_path / "ci-rails.toml"
    registry.write_text('[[rail]]\nname = "r"\ncommand = ["true"]\n', encoding="utf-8")
    (rail,) = ci_rails.load_rails(registry)
    assert rail.mode == ci_rails.ADVISORY


def test_invalid_mode_raises(tmp_path: Path) -> None:
    registry = tmp_path / "ci-rails.toml"
    registry.write_text(
        '[[rail]]\nname = "r"\ncommand = ["true"]\nmode = "block"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="invalid mode"):
        ci_rails.load_rails(registry)


def test_non_list_command_raises(tmp_path: Path) -> None:
    registry = tmp_path / "ci-rails.toml"
    registry.write_text('[[rail]]\nname = "r"\ncommand = "true"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="must be a list of strings"):
        ci_rails.load_rails(registry)


def test_advisory_failure_does_not_block(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path, [("flaky", _FAIL, "advisory")])
    assert ci_rails.main(["--registry", str(registry)]) == 0


def test_enforce_failure_blocks(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path, [("strict", _FAIL, "enforce")])
    assert ci_rails.main(["--registry", str(registry)]) == 1


def test_enforce_all_promotes_advisory_failure(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path, [("flaky", _FAIL, "advisory")])
    assert ci_rails.main(["--registry", str(registry)]) == 0
    assert ci_rails.main(["--registry", str(registry), "--enforce-all"]) == 1


def test_missing_command_binary_does_not_crash_advisory(tmp_path: Path) -> None:
    # A rail whose binary does not exist must be treated as a failure, not crash
    # the runner — advisory mode still must never fail the run.
    missing = ["this-binary-does-not-exist-xyz", "--nope"]
    registry = _write_registry(tmp_path, [("typo", missing, "advisory")])
    assert ci_rails.main(["--registry", str(registry)]) == 0


def test_missing_command_binary_blocks_under_enforce(tmp_path: Path) -> None:
    missing = ["this-binary-does-not-exist-xyz", "--nope"]
    registry = _write_registry(tmp_path, [("typo", missing, "enforce")])
    assert ci_rails.main(["--registry", str(registry)]) == 1


def test_passing_rail_returns_zero(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path, [("ok", _PASS, "enforce")])
    assert ci_rails.main(["--registry", str(registry)]) == 0


def test_mixed_advisory_pass_and_enforce_fail(tmp_path: Path) -> None:
    registry = _write_registry(
        tmp_path,
        [("advisory-fail", _FAIL, "advisory"), ("enforce-fail", _FAIL, "enforce")],
    )
    rails = ci_rails.load_rails(registry)
    summary = ci_rails.run_rails(rails)
    assert summary.exit_code == 1
    # Advisory failure recorded but not blocking; enforce failure blocks.
    by_name = {r.rail.name: r for r in summary.results}
    assert by_name["advisory-fail"].blocking is False
    assert by_name["enforce-fail"].blocking is True


def test_list_is_noop_exit_zero(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path, [("ok", _PASS, "advisory")])
    assert ci_rails.main(["--registry", str(registry), "--list"]) == 0


def test_repo_registry_loads_registered_rails() -> None:
    """The checked-in registry loads all registered rails, and they must be advisory in this phase."""
    rails = ci_rails.load_rails(ci_rails.DEFAULT_REGISTRY)
    assert {rail.name for rail in rails} == {
        "safedir-required",
        "atomic-write",
        "cli-path-validation",
        "defusedxml-fallback",
        "test-hardcoded-paths",
        "test-separator-paths",
        "pytest-raises-hygiene",
        "safedir-valueerror",
    }
    for rail in rails:
        assert rail.mode == "advisory"
