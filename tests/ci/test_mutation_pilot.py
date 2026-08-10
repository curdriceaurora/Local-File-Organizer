"""Tests for the mutation-testing pilot driver (#1684, epic #1678).

The driver's job is to turn mutmut's output into a number people will trust,
so these tests concentrate on the ways that number could lie: a crashed run
scored as a result, coverage left on, or a floor enforced against a profile
that never produced a score.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "mutation_pilot.py"


def _load_module() -> ModuleType:
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

    def test_score_is_killed_over_decided_mutants(self) -> None:
        stats = {"killed": 129, "survived": 65}

        assert mutation_pilot.score_of(stats) == pytest.approx(66.49, abs=0.01)

    def test_uncovered_mutants_do_not_move_the_score(self) -> None:
        """`no_tests` is a coverage fact, gated elsewhere.

        Folding it into the denominator would let a coverage change shift the
        mutation score on its own, which makes the number unreadable as a
        statement about assertion strength.
        """
        without = mutation_pilot.score_of({"killed": 8, "survived": 2})
        with_uncovered = mutation_pilot.score_of({"killed": 8, "survived": 2, "no_tests": 500})

        assert without == with_uncovered == 80.0

    def test_no_decided_mutants_scores_none_not_zero(self) -> None:
        """Zero decided mutants is "unknown", and must not read as a failure."""
        assert mutation_pilot.score_of({"killed": 0, "survived": 0, "no_tests": 12}) is None

    def test_every_mutant_surviving_is_zero_not_none(self) -> None:
        assert mutation_pilot.score_of({"killed": 0, "survived": 40}) == 0.0


@pytest.mark.unit
class TestProfiles:
    """Profile definitions are the pilot's scope; keep them honest."""

    def test_profile_names_are_unique(self) -> None:
        names = [p.name for p in mutation_pilot.PROFILES]

        assert len(names) == len(set(names))

    def test_every_profile_names_its_own_tests(self) -> None:
        """A profile with no test selector silently falls back to the suite.

        That is the ~22.5k-test run this pilot exists to avoid, and it is
        also what makes mutmut's fork segfault.
        """
        for profile in mutation_pilot.PROFILES:
            assert profile.tests, f"{profile.name} has no test selection"
            assert profile.only_mutate, f"{profile.name} mutates nothing"

    def test_coverage_is_disabled_for_every_run(self) -> None:
        """`--no-cov` is what stops the coverage gate faking a 100% score.

        With coverage on, `--cov-fail-under=93` fails for nearly every
        mutant, pytest exits non-zero, and mutmut reads that as "killed".
        """
        assert "--no-cov" in mutation_pilot.BASE_PYTEST_ARGS

    def test_generated_config_carries_the_profile_selection(self, tmp_path, monkeypatch) -> None:
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

    def test_segfaults_fail_the_run_even_at_a_perfect_score(self, monkeypatch, capsys) -> None:
        stats = {"killed": 222, "survived": 0, "no_tests": 7, "segfault": 432}
        monkeypatch.setattr(
            mutation_pilot, "run_profile", lambda profile, max_children, timeout: stats
        )
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py", "organizer"])

        exit_code = mutation_pilot.main()

        assert exit_code == 1, "a segfaulting run must not pass"
        assert "segfault" in capsys.readouterr().err

    def test_clean_run_below_no_floor_still_passes(self, monkeypatch) -> None:
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

    def test_score_below_floor_fails_under_enforce(self, monkeypatch, capsys) -> None:
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

    def test_the_same_score_passes_without_enforce(self, monkeypatch) -> None:
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

    def test_blocked_profile_is_skipped_but_announced(self, monkeypatch, capsys) -> None:
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

    def test_blocked_profile_still_runs_when_named(self, monkeypatch) -> None:
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

    def test_gated_profile_with_no_score_fails_rather_than_passing(
        self, monkeypatch, capsys
    ) -> None:
        """ "No score" must never read as "floor cleared".

        Every mutant landing in `no_tests`, or mutmut emitting empty stats,
        leaves `score_of` returning None. Skipping the floor check there
        passes a gated profile in silence — exactly the shape of failure this
        pilot exists to detect.
        """
        stats = {"killed": 0, "survived": 0, "no_tests": 400, "segfault": 0}
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
        assert "no score" in capsys.readouterr().err

    def test_one_profile_failing_does_not_abort_the_others(self, monkeypatch, tmp_path) -> None:
        """A wedged profile must not cost the rest their results.

        Left to propagate, a hang in the first profile meant no report file
        was written at all, so the nightly's artifact upload had nothing to
        publish.
        """
        report = tmp_path / "report.json"

        def fake_run(profile, max_children, timeout):
            if profile.name == "wedged":
                raise RuntimeError("hung for >1800s")
            return {"killed": 9, "survived": 1, "no_tests": 0, "segfault": 0}

        monkeypatch.setattr(mutation_pilot, "run_profile", fake_run)
        monkeypatch.setattr(
            mutation_pilot,
            "PROFILES",
            (
                mutation_pilot.Profile(name="wedged", only_mutate=["*"], tests=["t"]),
                mutation_pilot.Profile(name="healthy", only_mutate=["*"], tests=["t"]),
            ),
        )
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py", "--report", str(report)])

        assert mutation_pilot.main() == 1, "the wedged profile must still fail the run"

        written = json.loads(report.read_text(encoding="utf-8"))
        assert "hung" in written["wedged"]["error"]
        assert written["healthy"]["score"] == 90.0, "the healthy profile still ran and reported"

    def test_unknown_profile_is_rejected(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py", "no-such-profile"])

        assert mutation_pilot.main() == 2


@pytest.mark.unit
class TestPlatformScopedBlocking:
    """A blocker with an OS-specific cause must not suppress a profile everywhere.

    The organizer/parallel profiles were blocked on the strength of local macOS
    runs, for a fault in Apple's libsqlite3 that cannot occur on the
    ubuntu-latest nightly (#1726). Two profiles were therefore hidden from CI
    for a reason that never applied there.
    """

    def test_unscoped_block_applies_to_every_platform(self) -> None:
        """Back-compat: `blocked` without a platform set still blocks anywhere."""
        p = mutation_pilot.Profile(
            name="everywhere", only_mutate=["*"], tests=["t"], blocked="broken"
        )
        for platform in ("darwin", "linux", "win32"):
            assert p.block_reason(platform) == "broken"

    def test_scoped_block_applies_only_to_named_platforms(self) -> None:
        p = mutation_pilot.Profile(
            name="mac-only",
            only_mutate=["*"],
            tests=["t"],
            blocked="libsqlite3 fork fault",
            blocked_platforms=frozenset({"darwin"}),
        )
        assert p.block_reason("darwin") == "libsqlite3 fork fault"
        assert p.block_reason("linux") is None
        assert p.block_reason("win32") is None

    def test_unblocked_profile_is_never_blocked(self) -> None:
        p = mutation_pilot.Profile(name="fine", only_mutate=["*"], tests=["t"])
        assert p.block_reason("darwin") is None
        assert p.block_reason("linux") is None

    def test_profile_blocked_on_darwin_runs_on_linux(self, monkeypatch) -> None:
        """The behaviour that actually unblocks CI, not just the predicate."""
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
                    name="mac-only",
                    only_mutate=["*"],
                    tests=["t"],
                    blocked="libsqlite3 fork fault",
                    blocked_platforms=frozenset({"darwin"}),
                ),
            ),
        )
        monkeypatch.setattr(sys, "argv", ["mutation_pilot.py"])

        monkeypatch.setattr(mutation_pilot, "current_platform", lambda: "linux")
        assert mutation_pilot.main() == 0
        assert called == ["mac-only"], "a darwin-scoped block must not skip the Linux run"

        called.clear()
        monkeypatch.setattr(mutation_pilot, "current_platform", lambda: "darwin")
        assert mutation_pilot.main() == 0
        assert called == [], "the same profile must still be skipped on darwin"

    def test_real_blocked_profiles_run_on_linux(self) -> None:
        """The #1726 profiles must be scoped, not globally blocked."""
        by_name = {p.name: p for p in mutation_pilot.PROFILES}
        for name in ("organizer", "parallel"):
            profile = by_name[name]
            assert profile.blocked, f"{name} is expected to carry a blocker note"
            assert profile.block_reason("darwin"), f"{name} must stay blocked on macOS"
            assert profile.block_reason("linux") is None, (
                f"{name} must run on Linux, where the libsqlite3 fork fault cannot occur"
            )

    def test_newly_unblocked_profiles_are_not_gated_yet(self) -> None:
        """No floor until there is a Linux baseline to set one from.

        Unblocking with a guessed floor would fail the very first nightly.
        """
        by_name = {p.name: p for p in mutation_pilot.PROFILES}
        for name in ("organizer", "parallel"):
            assert by_name[name].floor is None, (
                f"{name} has no measured Linux baseline; a floor here would gate on a guess"
            )
