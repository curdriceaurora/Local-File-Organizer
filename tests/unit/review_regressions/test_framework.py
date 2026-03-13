from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

import pytest

from file_organizer.review_regressions.framework import (
    DetectorDescriptor,
    Violation,
    fingerprint_ast_node,
    iter_python_files,
    parse_python_ast,
    render_report_json,
    run_audit,
)


@dataclass
class _Detector:
    detector_id: str
    rule_class: str
    description: str
    findings: list[Violation]

    def find_violations(self, root: Path) -> list[Violation]:
        return list(self.findings)


def test_violation_fingerprint_is_stable_for_unchanged_finding(tmp_path: Path) -> None:
    root = tmp_path
    path = root / "pkg" / "module.py"
    path.parent.mkdir(parents=True)
    path.write_text("x = 1\n", encoding="utf-8")

    first = Violation.from_path(
        detector_id="test.detector",
        rule_class="test-quality",
        rule_id="weak-assertion",
        root=root,
        path=path,
        message="Weak assertion",
        line=1,
        fingerprint_basis="assert mock.call_count >= 1",
    )
    second = Violation.from_path(
        detector_id="test.detector",
        rule_class="test-quality",
        rule_id="weak-assertion",
        root=root,
        path=path,
        message="Weak assertion",
        line=1,
        fingerprint_basis="assert mock.call_count >= 1",
    )

    assert first.fingerprint == second.fingerprint


def test_violation_fingerprint_distinguishes_none_from_zero_line_numbers(tmp_path: Path) -> None:
    root = tmp_path
    path = root / "pkg" / "module.py"
    path.parent.mkdir(parents=True)
    path.write_text("x = 1\n", encoding="utf-8")

    zero_line = Violation.from_path(
        detector_id="test.detector",
        rule_class="test-quality",
        rule_id="weak-assertion",
        root=root,
        path=path,
        message="Weak assertion",
        line=0,
    )
    none_line = Violation.from_path(
        detector_id="test.detector",
        rule_class="test-quality",
        rule_id="weak-assertion",
        root=root,
        path=path,
        message="Weak assertion",
        line=None,
    )

    assert zero_line.fingerprint != none_line.fingerprint


def test_run_audit_and_render_report_are_deterministic(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "audit-root"
    root.mkdir()
    monkeypatch.chdir(tmp_path)
    (root / "b.py").write_text("print('b')\n", encoding="utf-8")
    (root / "a.py").write_text("print('a')\n", encoding="utf-8")

    findings = [
        Violation.from_path(
            detector_id="detector.z",
            rule_class="correctness",
            rule_id="z-rule",
            root=root,
            path=root / "b.py",
            message="second",
            line=9,
        ),
        Violation.from_path(
            detector_id="detector.a",
            rule_class="correctness",
            rule_id="a-rule",
            root=root,
            path=root / "a.py",
            message="first",
            line=3,
        ),
    ]
    detector = _Detector(
        detector_id="detector.pack",
        rule_class="correctness",
        description="fixture detector",
        findings=list(reversed(findings)),
    )

    report_one = run_audit(root, [detector])
    report_two = run_audit(root, [detector])

    json_one = render_report_json(report_one)
    json_two = render_report_json(report_two)

    assert json_one == json_two
    payload = json.loads(json_one)
    assert payload["root"] == "audit-root"
    assert [finding["path"] for finding in payload["findings"]] == ["a.py", "b.py"]


def test_run_audit_uses_immutable_detector_descriptors(tmp_path: Path) -> None:
    report = run_audit(
        tmp_path,
        [
            _Detector(
                detector_id="detector.pack",
                rule_class="correctness",
                description="fixture detector",
                findings=[],
            )
        ],
    )

    descriptor = report.detectors[0]

    assert isinstance(descriptor, DetectorDescriptor)
    with pytest.raises(FrozenInstanceError):
        descriptor.description = "mutated"


def test_run_audit_falls_back_to_absolute_root_when_relpath_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "audit-root"
    root.mkdir()
    monkeypatch.setattr(
        "file_organizer.review_regressions.framework.os.path.relpath",
        lambda path, start: (_ for _ in ()).throw(ValueError("different drive")),
    )

    report = run_audit(
        root,
        [
            _Detector(
                detector_id="detector.pack",
                rule_class="correctness",
                description="fixture detector",
                findings=[],
            )
        ],
    )

    assert report.root == root.resolve().as_posix()


def test_iter_python_files_excludes_cache_and_orders_results(tmp_path: Path) -> None:
    root = tmp_path
    (root / "pkg").mkdir()
    (root / "pkg" / "z.py").write_text("", encoding="utf-8")
    (root / "pkg" / "a.py").write_text("", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "ignored.py").write_text("", encoding="utf-8")

    assert [path.relative_to(root).as_posix() for path in iter_python_files(root)] == [
        "pkg/a.py",
        "pkg/z.py",
    ]


def test_iter_python_files_allows_empty_exclusion_set(tmp_path: Path) -> None:
    root = tmp_path
    (root / "__pycache__").mkdir()
    cached_file = root / "__pycache__" / "included.py"
    cached_file.write_text("", encoding="utf-8")

    assert iter_python_files(root, exclude_dirs=set()) == [cached_file]


def test_iter_python_files_only_scopes_exclusions_under_root(tmp_path: Path) -> None:
    root = tmp_path / "build" / "project"
    root.mkdir(parents=True)
    target = root / "module.py"
    target.write_text("", encoding="utf-8")

    assert iter_python_files(root) == [target]


def test_violation_from_path_rejects_paths_outside_audit_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="outside audit root"):
        Violation.from_path(
            detector_id="test.detector",
            rule_class="correctness",
            rule_id="outside-root",
            root=root,
            path=outside,
            message="outside path",
        )


def test_violation_from_path_accepts_root_relative_paths(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    nested = root / "pkg" / "module.py"
    nested.parent.mkdir()
    nested.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    violation = Violation.from_path(
        detector_id="test.detector",
        rule_class="correctness",
        rule_id="relative-path",
        root=root,
        path=Path("pkg/module.py"),
        message="relative path",
    )

    assert violation.path == "pkg/module.py"


def test_violation_from_path_accepts_relative_paths_that_include_root(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    nested = root / "pkg" / "module.py"
    nested.parent.mkdir()
    nested.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    violation = Violation.from_path(
        detector_id="test.detector",
        rule_class="correctness",
        rule_id="relative-with-root",
        root=Path("repo"),
        path=Path("repo/pkg/module.py"),
        message="root-prefixed relative path",
    )

    assert violation.path == "pkg/module.py"


def test_violation_from_path_accepts_root_prefixed_relative_paths_with_absolute_root(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    root = workspace / "repo"
    root.mkdir(parents=True)
    nested = root / "pkg" / "module.py"
    nested.parent.mkdir()
    nested.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(workspace)

    violation = Violation.from_path(
        detector_id="test.detector",
        rule_class="correctness",
        rule_id="absolute-root-prefixed",
        root=root,
        path=Path("repo/pkg/module.py"),
        message="root-prefixed relative path with absolute root",
    )

    assert violation.path == "pkg/module.py"


def test_parse_python_ast_supports_pep_263_source_encoding(tmp_path: Path) -> None:
    source = "# -*- coding: latin-1 -*-\nvalue = 'caf\xe9'\n".encode("latin-1")
    path = tmp_path / "encoded.py"
    path.write_bytes(source)

    tree = parse_python_ast(path)

    assign = tree.body[0]
    assert isinstance(assign, ast.Assign)
    assert isinstance(assign.value, ast.Constant)
    assert assign.value.value == "café"


def test_ast_fingerprint_is_resilient_to_harmless_formatting_changes() -> None:
    compact_node = ast.parse("value = foo(1, 2)\n").body[0]
    expanded_node = ast.parse("value = foo(\n    1,\n    2,\n)\n").body[0]

    assert fingerprint_ast_node(compact_node) == fingerprint_ast_node(expanded_node)
