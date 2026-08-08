"""Tests for the mutation-testing pilot driver (#1684, epic #1678).

The driver's job is to turn mutmut's output into a number people will trust,
so these tests concentrate on the ways that number could lie: a crashed run
scored as a result, coverage left on, or a floor enforced against a profile
that never produced a score.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "mutation_pilot.py"


def _load_module():
    """Import the driver by path; scripts/ is not an importable package."""
    spec = importlib.util.spec_from_file_location("mutation_pilot", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["mutation_pilot"] = module
    spec.loader.exec_module(module)
    return module


mutation_pilot = _load_module()


@pytest.mark.unit
class TestScoreOf:
    """The score's denominator is the whole argument."""

    def test_score_is_killed_over_decided_mutants(self):
        stats = {"killed": 129, "survived": 65}

        assert mutation_pilot.score_of(stats) == pytest.approx(66.49, abs=0.01)

    def test_uncovered_mutants_do_not_move_the_score(self):
        """`no_tests` is a coverage fact, gated elsewhere.

        Folding it into the denominator would let a coverage change shift the
        mutation score on its own, which makes the number unreadable as a
        statement about assertion strength.
        """
        without = mutation_pilot.score_of({"killed": 8, "survived": 2})
        with_uncovered = mutation_pilot.score_of({"killed": 8, "survived": 2, "no_tests": 500})

        assert without == with_uncovered == 80.0

    def test_no_decided_mutants_scores_none_not_zero(self):
        """Zero decided mutants is "unknown", and must not read as a failure."""
        assert mutation_pilot.score_of({"killed": 0, "survived": 0, "no_tests": 12}) is None

    def test_every_mutant_surviving_is_zero_not_none(self):
        assert mutation_pilot.score_of({"killed": 0, "survived": 40}) == 0.0


@pytest.mark.unit
class TestProfiles:
    """Profile definitions are the pilot's scope; keep them honest."""

    def test_profile_names_are_unique(self):
        names = [p.name for p in mutation_pilot.PROFILES]

        assert len(names) == len(set(names))

    def test_every_profile_names_its_own_tests(self):
        """A profile with no test selector silently falls back to the suite.

        That is the ~22.5k-test run this pilot exists to avoid, and it is
        also what makes mutmut's fork segfault.
        """
        for profile in mutation_pilot.PROFILES:
            assert profile.tests, f"{profile.name} has no test selection"
            assert profile.only_mutate, f"{profile.name} mutates nothing"

    def test_coverage_is_disabled_for_every_run(self):
        """`--no-cov` is what stops the coverage gate faking a 100% score.

        With coverage on, `--cov-fail-under=93` fails for nearly every
        mutant, pytest exits non-zero, and mutmut reads that as "killed".
        """
        assert "--no-cov" in mutation_pilot.BASE_PYTEST_ARGS

    def test_generated_config_carries_the_profile_selection(self, tmp_path, monkeypatch):
        """The written config must actually contain what the profile declared."""
        cfg = tmp_path / "setup.cfg"
        monkeypatch.setattr(mutation_pilot, "SETUP_CFG", cfg)
        profile = mutation_pilot.Profile(
            name="probe",
            only_mutate=["*/some/module.py"],
            tests=["tests/some/test_module.py"],
        )

        mutation_pilot.write_config(profile)
        written = cfg.read_text(encoding="utf-8")

        assert "[mutmut]" in written
        assert "*/some/module.py" in written
        assert "tests/some/test_module.py" in written
        assert "--no-cov" in written


@pytest.mark.unit
class TestSegfaultHandling:
    """A crashed run is not a result.

    This is the guard that caught the pilot's own first numbers: two profiles
    reported 100% while 268 and 432 mutants had segfaulted.
    """

    def test_segfaults_fail_the_run_even_at_a_perfect_score(self, monkeypatch, capsys):
        stats = {"killed": 222, "survived": 0, "no_tests": 7, "segfault": 432}
        monkeypatch.setattr(
            mutation_pilot, "run_profile", lambda profile, max_children, timeout: stats
        )
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py", "organizer"])

        exit_code = mutation_pilot.main()

        assert exit_code == 1, "a segfaulting run must not pass"
        assert "segfault" in capsys.readouterr().err

    def test_clean_run_below_no_floor_still_passes(self, monkeypatch):
        """Ungated profiles are measured, not enforced."""
        stats = {"killed": 1, "survived": 99, "no_tests": 0, "segfault": 0}
        monkeypatch.setattr(
            mutation_pilot, "run_profile", lambda profile, max_children, timeout: stats
        )
        monkeypatch.setattr(
            mutation_pilot,
            "PROFILES",
            (mutation_pilot.Profile(name="ungated", only_mutate=["*"], tests=["t"], floor=None),),
        )
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py", "--enforce"])

        assert mutation_pilot.main() == 0

    def test_score_below_floor_fails_under_enforce(self, monkeypatch, capsys):
        stats = {"killed": 50, "survived": 50, "no_tests": 0, "segfault": 0}
        monkeypatch.setattr(
            mutation_pilot, "run_profile", lambda profile, max_children, timeout: stats
        )
        monkeypatch.setattr(
            mutation_pilot,
            "PROFILES",
            (mutation_pilot.Profile(name="gated", only_mutate=["*"], tests=["t"], floor=75.0),),
        )
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py", "--enforce"])

        assert mutation_pilot.main() == 1
        assert "below floor" in capsys.readouterr().err

    def test_the_same_score_passes_without_enforce(self, monkeypatch):
        """Reporting mode never fails, so a nightly can still publish a report."""
        stats = {"killed": 50, "survived": 50, "no_tests": 0, "segfault": 0}
        monkeypatch.setattr(
            mutation_pilot, "run_profile", lambda profile, max_children, timeout: stats
        )
        monkeypatch.setattr(
            mutation_pilot,
            "PROFILES",
            (mutation_pilot.Profile(name="gated", only_mutate=["*"], tests=["t"], floor=75.0),),
        )
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py"])

        assert mutation_pilot.main() == 0

    def test_blocked_profile_is_skipped_but_announced(self, monkeypatch, capsys):
        """A dropped target must never read as a clean sweep."""
        called: list[str] = []
        monkeypatch.setattr(
            mutation_pilot,
            "run_profile",
            lambda profile, max_children, timeout: called.append(profile.name) or {},
        )
        monkeypatch.setattr(
            mutation_pilot,
            "PROFILES",
            (
                mutation_pilot.Profile(
                    name="wedged", only_mutate=["*"], tests=["t"], blocked="segfaults"
                ),
            ),
        )
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py", "--enforce"])

        assert mutation_pilot.main() == 0
        assert called == [], "a blocked profile must not be run by default"
        assert "SKIPPED" in capsys.readouterr().out

    def test_blocked_profile_still_runs_when_named(self, monkeypatch):
        """So whoever is fixing the blocker can measure their progress."""
        called: list[str] = []
        stats = {"killed": 1, "survived": 0, "no_tests": 0, "segfault": 0}
        monkeypatch.setattr(
            mutation_pilot,
            "run_profile",
            lambda profile, max_children, timeout: (called.append(profile.name), stats)[1],
        )
        monkeypatch.setattr(
            mutation_pilot,
            "PROFILES",
            (
                mutation_pilot.Profile(
                    name="wedged", only_mutate=["*"], tests=["t"], blocked="segfaults"
                ),
            ),
        )
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py", "wedged"])

        assert mutation_pilot.main() == 0
        assert called == ["wedged"]

    def test_unknown_profile_is_rejected(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py", "no-such-profile"])

        assert mutation_pilot.main() == 2
