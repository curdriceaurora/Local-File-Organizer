from __future__ import annotations

import ast
from pathlib import Path

from file_organizer.review_regressions.api_compat import (
    API_COMPAT_DETECTORS,
    PublicApiCompatibilityDetector,
    PublicCallableContract,
    _find_allowlisted_callable,
    _find_class_method_callable,
    _find_named_classes,
    _find_named_methods,
    _find_toplevel_callable,
)


def _fixture_root() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "fixtures" / "review_regressions" / "api_compat"
    ).resolve()


def test_api_compat_detector_flags_legacy_positional_prefix_changes() -> None:
    detector = PublicApiCompatibilityDetector(
        contracts=(
            PublicCallableContract(
                path=Path("src/file_organizer/public/constructor_prefix_positive.py"),
                qualname="PipelineOrchestrator.__init__",
                legacy_positional_params=("config", "stages", "prefetch_depth"),
            ),
        )
    )

    findings = detector.find_violations(_fixture_root())

    assert [(finding.path, finding.line, finding.rule_id) for finding in findings] == [
        (
            "src/file_organizer/public/constructor_prefix_positive.py",
            2,
            "legacy-positional-prefix-changed",
        ),
    ]


def test_api_compat_detector_flags_new_optional_positional_params() -> None:
    detector = PublicApiCompatibilityDetector(
        contracts=(
            PublicCallableContract(
                path=Path("src/file_organizer/public/optional_positional_positive.py"),
                qualname="FileOrganizer.__init__",
                legacy_positional_params=("dry_run", "prefetch_depth"),
            ),
        )
    )

    findings = detector.find_violations(_fixture_root())

    assert [(finding.path, finding.line, finding.rule_id) for finding in findings] == [
        (
            "src/file_organizer/public/optional_positional_positive.py",
            6,
            "new-optional-param-must-be-keyword-only",
        ),
    ]


def test_api_compat_detector_allows_keyword_only_optional_extension() -> None:
    detector = PublicApiCompatibilityDetector(
        contracts=(
            PublicCallableContract(
                path=Path("src/file_organizer/public/keyword_only_safe.py"),
                qualname="FileOrganizer.__init__",
                legacy_positional_params=("dry_run", "prefetch_depth"),
            ),
            PublicCallableContract(
                path=Path("src/file_organizer/public/process_batch_safe.py"),
                qualname="PipelineOrchestrator.process_batch",
                legacy_positional_params=("files",),
            ),
        )
    )

    findings = detector.find_violations(_fixture_root())

    assert findings == []


def test_api_compat_detector_pack_exports_detector() -> None:
    assert [detector.detector_id for detector in API_COMPAT_DETECTORS] == [
        "api-compat.public-callable-signature-contracts",
    ]


def test_api_compat_detector_flags_missing_allowlisted_targets() -> None:
    detector = PublicApiCompatibilityDetector(
        contracts=(
            PublicCallableContract(
                path=Path("src/file_organizer/public/does_not_exist.py"),
                qualname="PipelineOrchestrator.__init__",
                legacy_positional_params=("config",),
            ),
            PublicCallableContract(
                path=Path("src/file_organizer/public/process_batch_safe.py"),
                qualname="PipelineOrchestrator.missing_method",
                legacy_positional_params=("files",),
            ),
        )
    )

    findings = detector.find_violations(_fixture_root())

    assert [(finding.path, finding.rule_id) for finding in findings] == [
        (
            "src/file_organizer/public/does_not_exist.py",
            "allowlisted-callable-missing",
        ),
        (
            "src/file_organizer/public/process_batch_safe.py",
            "allowlisted-callable-missing",
        ),
    ]


# ── T10 predicate negative-case tests (issue #930) ───────────────────────────


def test_find_toplevel_callable_returns_none_when_name_not_in_module() -> None:
    tree = ast.parse("def other_func(): pass")
    assert not _find_toplevel_callable(tree, "missing_func")


def test_find_toplevel_callable_returns_none_for_class_not_function() -> None:
    tree = ast.parse("class MyClass: pass")
    assert not _find_toplevel_callable(tree, "MyClass")


def test_find_named_classes_returns_empty_when_class_absent() -> None:
    body = ast.parse("def my_func(): pass").body
    assert not _find_named_classes(body, "MissingClass")


def test_find_named_classes_returns_empty_when_name_matches_function() -> None:
    body = ast.parse("def MyClass(): pass").body
    assert not _find_named_classes(body, "MyClass")


def test_find_named_methods_returns_empty_when_method_absent() -> None:
    body = ast.parse("class Foo:\n    def real_method(self): pass").body[0].body
    assert not _find_named_methods(body, "missing_method")


def test_find_class_method_callable_returns_none_when_class_absent() -> None:
    tree = ast.parse("class OtherClass:\n    def my_method(self): pass")
    assert not _find_class_method_callable(tree, ["MissingClass", "my_method"])[0]


def test_find_class_method_callable_returns_none_when_method_absent() -> None:
    tree = ast.parse("class MyClass:\n    def other_method(self): pass")
    assert not _find_class_method_callable(tree, ["MyClass", "missing_method"])[0]


def test_find_allowlisted_callable_returns_none_for_missing_toplevel_function() -> None:
    tree = ast.parse("def other_func(): pass")
    assert not _find_allowlisted_callable(tree, "missing_func")[0]


def test_find_allowlisted_callable_returns_none_for_missing_class_method() -> None:
    tree = ast.parse("class MyClass:\n    def other_method(self): pass")
    assert not _find_allowlisted_callable(tree, "MyClass.missing_method")[0]
