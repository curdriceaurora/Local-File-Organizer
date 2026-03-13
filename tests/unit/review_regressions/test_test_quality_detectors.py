from __future__ import annotations

from pathlib import Path

import file_organizer.review_regressions.test_quality as MODULE
from file_organizer.review_regressions.test_quality import (
    TEST_QUALITY_DETECTORS,
    WeakMockCallCountAssertionDetector,
    changed_test_quality_detectors,
    discover_changed_test_files,
)


def _fixture_root() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "fixtures" / "review_regressions" / "test_quality"
    ).resolve()


def test_full_repo_mode_flags_weak_mock_call_count_patterns() -> None:
    detector = WeakMockCallCountAssertionDetector(scan_mode="full_repo")

    findings = detector.find_violations(_fixture_root())

    assert [(finding.path, finding.line, finding.rule_id) for finding in findings] == [
        (
            "tests/weak_assertions_positive.py",
            6,
            "weak-mock-call-count-lower-bound",
        ),
        (
            "tests/weak_assertions_positive.py",
            7,
            "weak-mock-call-count-lower-bound",
        ),
        (
            "tests/weak_assertions_positive.py",
            8,
            "weak-mock-call-count-lower-bound",
        ),
        (
            "tests/weak_assertions_positive.py",
            9,
            "weak-mock-call-count-lower-bound",
        ),
    ]


def test_full_repo_mode_does_not_flag_safe_assertions_or_non_test_files() -> None:
    detector = WeakMockCallCountAssertionDetector(scan_mode="full_repo")

    findings = detector.find_violations(_fixture_root())

    assert not any(finding.path == "tests/weak_assertions_safe.py" for finding in findings)
    assert not any(finding.path.startswith("src/") for finding in findings)


def test_changed_test_file_mode_scans_only_provided_changed_tests() -> None:
    fixture_root = _fixture_root()
    changed_test = fixture_root / "tests" / "weak_assertions_positive.py"
    non_test_file = fixture_root / "src" / "not_a_test_file.py"
    detector = WeakMockCallCountAssertionDetector(
        scan_mode="changed_test_files",
        changed_files_provider=lambda root: [changed_test, non_test_file],
    )

    findings = detector.find_violations(fixture_root)

    assert len(findings) == 4
    assert all(finding.path == "tests/weak_assertions_positive.py" for finding in findings)


def test_changed_test_file_mode_handles_empty_changed_set() -> None:
    detector = WeakMockCallCountAssertionDetector(
        scan_mode="changed_test_files",
        changed_files_provider=lambda root: [],
    )

    assert detector.find_violations(_fixture_root()) == []


def test_test_quality_detector_pack_exports_first_wave_detector() -> None:
    assert [detector.detector_id for detector in TEST_QUALITY_DETECTORS] == [
        "test-quality.weak-mock-call-count-lower-bound",
    ]
    assert [detector.detector_id for detector in changed_test_quality_detectors()] == [
        "test-quality.weak-mock-call-count-lower-bound",
    ]


def test_discover_changed_test_files_prefers_merge_base_for_multi_commit_branch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "alpha_test.py").write_text(
        "def test_alpha():\n    assert True\n", encoding="utf-8"
    )
    (tests_dir / "beta_test.py").write_text("def test_beta():\n    assert True\n", encoding="utf-8")

    def fake_git_stdout(root: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return "head-sha"
        if args == ("rev-parse", "--verify", "--quiet", "origin/main^{commit}"):
            return "origin-main-sha"
        if args == ("merge-base", "HEAD", "origin/main"):
            return "base-sha"
        if args == (
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            "base-sha...HEAD",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        ):
            return "tests/alpha_test.py\ntests/beta_test.py"
        return ""

    monkeypatch.setattr(MODULE, "_git_stdout", fake_git_stdout)

    assert discover_changed_test_files(tmp_path) == [
        tmp_path / "tests" / "alpha_test.py",
        tmp_path / "tests" / "beta_test.py",
    ]


def test_discover_changed_test_files_falls_back_to_head_parent_when_no_main_ref(
    monkeypatch,
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "changed_test.py").write_text(
        "def test_changed():\n    assert True\n", encoding="utf-8"
    )

    def fake_git_stdout(root: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return "head-sha"
        if args == ("rev-parse", "--verify", "--quiet", "HEAD^1"):
            return "parent-sha"
        if args == (
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            "parent-sha...HEAD",
            "--",
            "tests/**/*.py",
            "tests/*.py",
        ):
            return "tests/changed_test.py"
        return ""

    monkeypatch.setattr(MODULE, "_git_stdout", fake_git_stdout)

    assert discover_changed_test_files(tmp_path) == [tmp_path / "tests" / "changed_test.py"]
