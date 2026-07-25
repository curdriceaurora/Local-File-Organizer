"""Tests for the #1685 triage worklist generator."""

from __future__ import annotations

import pytest

from scripts.ci.triage_mock_findings import FIXTURE_SPREAD, build_worklist

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _dead(file: str, test: str, target: str, line: int = 10) -> dict:
    return {
        "file": file,
        "line": line,
        "nodeid": f"{file}::{test}",
        "target": target,
        "status": "dead",
        "access_count": 0,
    }


def _unused(file: str, test: str, param: str, line: int = 10) -> dict:
    return {"file": file, "line": line, "test": test, "param": param}


def test_unused_but_live_is_add_assertion() -> None:
    """Static-only finding: the mock was reached at runtime, just unasserted."""
    rows = build_worklist([], [_unused("t.py", "test_a", "mock_x")], [])
    assert len(rows) == 1
    assert rows[0]["action"] == "add-assertion"
    assert rows[0]["sources"] == ["static"]


def test_dead_and_referenced_is_retarget_or_overreach() -> None:
    """Liveness-only finding: configured in the body but never reached."""
    rows = build_worklist([_dead("t.py", "test_a", "mod.helper")], [], [])
    assert len(rows) == 1
    assert rows[0]["action"] == "retarget-or-overreach"
    assert rows[0]["sources"] == ["liveness"]


def test_dead_and_unused_is_delete_or_retarget() -> None:
    """Both detectors: a pure ghost patch."""
    rows = build_worklist(
        [_dead("t.py", "test_a", "mod.helper")],
        [_unused("t.py", "test_a", "mock_helper")],
        [],
    )
    assert len(rows) == 1
    assert rows[0]["action"] == "delete-or-retarget"
    assert rows[0]["sources"] == ["liveness", "static"]


def test_fixture_spread_forces_narrow_fixture() -> None:
    """A target dead across >= FIXTURE_SPREAD tests in one file is fixture noise,
    and wins over the pairwise classification for every affected test."""
    dead = [_dead("t.py", f"test_{i}", "mod.suppressor") for i in range(FIXTURE_SPREAD)]
    unused = [_unused("t.py", "test_0", "mock_suppressor")]
    rows = build_worklist(dead, unused, [])
    assert {r["action"] for r in rows} == {"narrow-fixture"}
    assert len(rows) == FIXTURE_SPREAD


def test_below_spread_threshold_stays_pairwise() -> None:
    dead = [_dead("t.py", f"test_{i}", "mod.helper") for i in range(FIXTURE_SPREAD - 1)]
    rows = build_worklist(dead, [], [])
    assert {r["action"] for r in rows} == {"retarget-or-overreach"}


def test_parametrized_nodeids_collapse_to_one_test() -> None:
    """test_a[case1] / test_a[case2] are the same repair site."""
    dead = [
        _dead("t.py", "test_a[one]", "mod.helper"),
        _dead("t.py", "test_a[two]", "mod.helper"),
    ]
    rows = build_worklist(dead, [], [])
    assert len(rows) == 1
    assert rows[0]["test"] == "test_a"


def test_untracked_rows_are_deferred() -> None:
    rows = build_worklist([], [], [_dead("t.py", "test_a", "mod.CONST")])
    assert len(rows) == 1
    assert rows[0]["action"] == "untracked-review"
    assert rows[0]["status"] == "deferred"


def test_open_rows_carry_line_and_evidence() -> None:
    rows = build_worklist(
        [_dead("t.py", "test_a", "mod.helper", line=42)],
        [_unused("t.py", "test_a", "mock_helper", line=41)],
        [],
    )
    assert rows[0]["line"] == 41
    assert rows[0]["dead_targets"] == ["mod.helper"]
    assert rows[0]["unused_params"] == ["mock_helper"]
    assert rows[0]["status"] == "open"
