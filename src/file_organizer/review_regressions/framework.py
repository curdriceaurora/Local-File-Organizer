"""Shared framework for review-regression audit detectors."""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

_DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "site",
}


def _stable_hash(parts: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()[:16]


def _normalized_relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


@dataclass(frozen=True, slots=True)
class Violation:
    """Stable schema for a detector finding."""

    detector_id: str
    rule_class: str
    rule_id: str
    path: str
    message: str
    line: int | None = None
    end_line: int | None = None
    fingerprint_basis: str = ""
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        """Compute stable fingerprint once at construction time."""
        object.__setattr__(
            self,
            "fingerprint",
            _stable_hash(
                [
                    self.detector_id,
                    self.rule_class,
                    self.rule_id,
                    self.path,
                    "" if self.line is None else str(self.line),
                    "" if self.end_line is None else str(self.end_line),
                    self.fingerprint_basis or self.message,
                ]
            ),
        )

    @classmethod
    def from_path(
        cls,
        *,
        detector_id: str,
        rule_class: str,
        rule_id: str,
        root: Path,
        path: Path,
        message: str,
        line: int | None = None,
        end_line: int | None = None,
        fingerprint_basis: str = "",
    ) -> Violation:
        """Build a violation with a stable root-relative path."""
        return cls(
            detector_id=detector_id,
            rule_class=rule_class,
            rule_id=rule_id,
            path=_normalized_relative_path(path, root),
            message=message,
            line=line,
            end_line=end_line,
            fingerprint_basis=fingerprint_basis,
        )

    def sort_key(self) -> tuple[str, str, str, int, int, str, str, str]:
        """Return deterministic ordering key for serialized output."""
        return (
            self.rule_class,
            self.detector_id,
            self.path,
            self.line if self.line is not None else -1,
            self.end_line if self.end_line is not None else -1,
            self.message,
            self.rule_id,
            self.fingerprint,
        )

    def to_dict(self) -> dict[str, object]:
        """Convert to deterministic JSON-friendly structure."""
        data: dict[str, object] = {
            "detector_id": self.detector_id,
            "rule_class": self.rule_class,
            "rule_id": self.rule_id,
            "path": self.path,
            "message": self.message,
            "fingerprint": self.fingerprint,
        }
        if self.line is not None:
            data["line"] = self.line
        if self.end_line is not None:
            data["end_line"] = self.end_line
        return data


class ReviewRegressionDetector(Protocol):
    """Protocol that detector packs must satisfy."""

    detector_id: str
    rule_class: str
    description: str

    def find_violations(self, root: Path) -> Iterable[Violation]:
        """Return violations discovered under *root*."""


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Deterministic report emitted by the audit entrypoint."""

    root: str
    detectors: tuple[dict[str, str], ...]
    findings: tuple[Violation, ...]

    def to_dict(self) -> dict[str, object]:
        """Convert to stable JSON-friendly structure."""
        return {
            "format_version": 1,
            "root": self.root,
            "detector_count": len(self.detectors),
            "finding_count": len(self.findings),
            "detectors": list(self.detectors),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def render_report_json(report: AuditReport, *, pretty: bool = True) -> str:
    """Render *report* as deterministic JSON."""
    if pretty:
        return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    return json.dumps(report.to_dict(), separators=(",", ":"), sort_keys=True) + "\n"


def iter_python_files(
    root: Path,
    *,
    exclude_dirs: set[str] | None = None,
) -> list[Path]:
    """Return project Python files in deterministic order."""
    excluded = _DEFAULT_EXCLUDE_DIRS if exclude_dirs is None else exclude_dirs
    results: list[Path] = []
    for path in root.rglob("*.py"):
        relative_parts = path.relative_to(root).parts[:-1]
        if any(part in excluded for part in relative_parts):
            continue
        if path.is_file():
            results.append(path)
    return sorted(results, key=lambda item: item.as_posix())


def parse_python_ast(path: Path) -> ast.AST:
    """Parse a Python file into an AST."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def fingerprint_ast_node(node: ast.AST) -> str:
    """Return a formatting-resilient fingerprint for an AST node."""
    return _stable_hash([ast.dump(node, annotate_fields=True, include_attributes=False)])


def run_audit(root: Path, detectors: Iterable[ReviewRegressionDetector]) -> AuditReport:
    """Run detector audit and return a deterministic report."""
    normalized_root = root.resolve()
    ordered_detectors = sorted(
        detectors,
        key=lambda detector: (detector.rule_class, detector.detector_id),
    )

    findings: list[Violation] = []
    detector_descriptors: list[dict[str, str]] = []
    for detector in ordered_detectors:
        detector_descriptors.append(
            {
                "detector_id": detector.detector_id,
                "rule_class": detector.rule_class,
                "description": detector.description,
            }
        )
        findings.extend(detector.find_violations(normalized_root))

    return AuditReport(
        root=normalized_root.as_posix(),
        detectors=tuple(detector_descriptors),
        findings=tuple(sorted(findings, key=Violation.sort_key)),
    )
