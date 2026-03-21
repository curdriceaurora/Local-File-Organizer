from __future__ import annotations

from pathlib import Path

from file_organizer.review_regressions.security import (
    SECURITY_DETECTORS,
    GuardedContextDirectPathDetector,
    ValidatedPathBypassDetector,
)


def _fixture_root() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "fixtures" / "review_regressions" / "security"
    ).resolve()


def _write_module(root: Path, rel_path: str, source: str) -> Path:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target


def test_direct_path_detector_flags_unreviewed_path_construction() -> None:
    detector = GuardedContextDirectPathDetector()

    findings = detector.find_violations(_fixture_root())

    assert [(finding.path, finding.line, finding.rule_id) for finding in findings] == [
        (
            "src/file_organizer/api/direct_path_allowed_roots_missing_codeql.py",
            15,
            "unguarded-direct-path",
        ),
        (
            "src/file_organizer/api/direct_path_positive.py",
            16,
            "unguarded-direct-path",
        ),
    ]


def test_direct_path_detector_skips_documented_safe_patterns() -> None:
    detector = GuardedContextDirectPathDetector()

    findings = [
        finding
        for finding in detector.find_violations(_fixture_root())
        if finding.path == "src/file_organizer/api/direct_path_safe.py"
    ]

    assert findings == []


def test_direct_path_detector_flags_path_alias_and_pathlib_attribute_calls(tmp_path: Path) -> None:
    detector = GuardedContextDirectPathDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/path_alias.py",
        (
            "from pathlib import Path as P\n"
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/x')\n"
            "def unsafe_alias(path: str) -> str:\n"
            "    return str(P(path))\n"
        ),
    )
    _write_module(
        tmp_path,
        "src/file_organizer/api/pathlib_attr.py",
        (
            "import pathlib\n"
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/x')\n"
            "def unsafe_attr(path: str) -> str:\n"
            "    return str(pathlib.Path(path))\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert {(finding.path, finding.rule_id) for finding in findings} == {
        ("src/file_organizer/api/path_alias.py", "unguarded-direct-path"),
        ("src/file_organizer/api/pathlib_attr.py", "unguarded-direct-path"),
    }


def test_direct_path_detector_does_not_allow_codeql_comment_bypass_in_route(
    tmp_path: Path,
) -> None:
    detector = GuardedContextDirectPathDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/comment_bypass.py",
        (
            "from pathlib import Path\n"
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/x')\n"
            "def unsafe(path: str) -> str:\n"
            "    # codeql[py/path-injection]\n"
            "    return str(Path(path))\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert [(finding.path, finding.rule_id) for finding in findings] == [
        ("src/file_organizer/api/comment_bypass.py", "unguarded-direct-path")
    ]


def test_validation_bypass_detector_flags_raw_request_reuse_after_validation() -> None:
    detector = ValidatedPathBypassDetector()

    findings = detector.find_violations(_fixture_root())

    assert [
        (finding.path, finding.line, finding.rule_id, finding.message) for finding in findings
    ] == [
        (
            "src/file_organizer/api/validation_bypass_positional_positive.py",
            26,
            "raw-field-after-validation",
            "Route validates request.destination with resolve_path() but later passes raw request.destination to move_files().",
        ),
        (
            "src/file_organizer/api/validation_bypass_positional_positive.py",
            26,
            "raw-field-after-validation",
            "Route validates request.source with resolve_path() but later passes raw request.source to move_files().",
        ),
        (
            "src/file_organizer/api/validation_bypass_positive.py",
            35,
            "raw-request-after-validation",
            "Route validates request path fields with resolve_path() but later passes the raw request object to add_task().",
        ),
        (
            "src/file_organizer/api/validation_bypass_positive.py",
            36,
            "raw-field-after-validation",
            "Route validates request.input_dir with resolve_path() but later passes raw request.input_dir to organize().",
        ),
        (
            "src/file_organizer/api/validation_bypass_positive.py",
            36,
            "raw-field-after-validation",
            "Route validates request.output_dir with resolve_path() but later passes raw request.output_dir to organize().",
        ),
    ]


def test_validation_bypass_detector_skips_sanitized_request_flow() -> None:
    detector = ValidatedPathBypassDetector()

    findings = [
        finding
        for finding in detector.find_violations(_fixture_root())
        if finding.path == "src/file_organizer/api/validation_bypass_safe.py"
    ]

    assert findings == []


def test_validation_bypass_detector_flags_inline_validation_and_raw_alias_reuse(
    tmp_path: Path,
) -> None:
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/raw_alias.py",
        (
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "def resolve_path(value: str, allowed: list[str]) -> str:\n"
            "    return value\n"
            "class Req:\n"
            "    input_dir: str\n"
            "class Settings:\n"
            "    allowed_paths: list[str] = []\n"
            "class Organizer:\n"
            "    def organize(self, *, input_path: str) -> None:\n"
            "        pass\n"
            "organizer = Organizer()\n"
            "@router.post('/x')\n"
            "def unsafe(request: Req, settings: Settings) -> None:\n"
            "    _ = str(resolve_path(request.input_dir, settings.allowed_paths))\n"
            "    raw_input = request.input_dir\n"
            "    organizer.organize(input_path=raw_input)\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.path == "src/file_organizer/api/raw_alias.py"
    assert finding.rule_id == "raw-field-after-validation"
    assert "alias raw_input sourced from raw request.input_dir" in finding.message


def test_validation_bypass_detector_flags_api_route_decorated_handlers(tmp_path: Path) -> None:
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/api_route_bypass.py",
        (
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "def resolve_path(value: str, allowed: list[str]) -> str:\n"
            "    return value\n"
            "class Req:\n"
            "    input_dir: str\n"
            "class Settings:\n"
            "    allowed_paths: list[str] = []\n"
            "class Organizer:\n"
            "    def organize(self, *, input_path: str) -> None:\n"
            "        pass\n"
            "organizer = Organizer()\n"
            "@router.api_route('/x', methods=['POST'])\n"
            "def unsafe(request: Req, settings: Settings) -> None:\n"
            "    validated = resolve_path(request.input_dir, settings.allowed_paths)\n"
            "    organizer.organize(input_path=request.input_dir)\n"
            "    _ = validated\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.path == "src/file_organizer/api/api_route_bypass.py"
    assert finding.rule_id == "raw-field-after-validation"


def test_security_detector_pack_exports_both_first_wave_security_detectors() -> None:
    assert [detector.detector_id for detector in SECURITY_DETECTORS] == [
        "security.guarded-context-direct-path",
        "security.validated-path-bypass",
    ]
