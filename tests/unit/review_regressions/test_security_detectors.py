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


# ── Tests added for CodeRabbit Major findings on PR #929 ─────────────────────


def test_direct_path_detector_does_not_flag_path_without_pathlib_import(
    tmp_path: Path,
) -> None:
    """Path() in a file without ``from pathlib import Path`` is not flagged (finding #1).

    After removing the unconditional ``"Path"`` seed from ``_path_constructor_names``,
    only names explicitly introduced by ``from pathlib import Path [as alias]`` are
    tracked.  A file that shadows or inherits ``Path`` without a pathlib import cannot
    produce a valid ``Path(x)`` AST constructor node the detector cares about.
    """
    detector = GuardedContextDirectPathDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/aliased_only.py",
        (
            "from pathlib import Path as P\n"
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/x')\n"
            "def view(path: str) -> str:\n"
            "    return str(P(path))\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    # Alias P is tracked; bare "Path" is not seeded → only P(path) should flag
    assert len(findings) == 1
    assert findings[0].rule_id == "unguarded-direct-path"


def test_validation_bypass_detector_recognizes_module_alias_resolve_path(
    tmp_path: Path,
) -> None:
    """``import pkg.api.utils as utils; utils.resolve_path(x)`` counts as validation (finding #2).

    Before this fix only ``from pkg.api.utils import resolve_path`` was tracked.
    Module-alias calls like ``utils.resolve_path(request.input_dir, ...)`` were
    silently ignored, causing the bypass detector to miss real violations.
    """
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/module_alias_bypass.py",
        (
            "import file_organizer.api.utils as utils\n"
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "class Req:\n"
            "    input_dir: str\n"
            "class Settings:\n"
            "    allowed_paths: list = []\n"
            "class Organizer:\n"
            "    def organize(self, *, input_path): pass\n"
            "organizer = Organizer()\n"
            "@router.post('/x')\n"
            "def handler(request: Req, settings: Settings) -> None:\n"
            "    _v = utils.resolve_path(request.input_dir, settings.allowed_paths)\n"
            "    organizer.organize(input_path=request.input_dir)\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule_id == "raw-field-after-validation"


def test_direct_path_codeql_comment_inside_nested_function_in_route_is_still_flagged(
    tmp_path: Path,
) -> None:
    """A codeql suppression in a nested function inside a route handler does not bypass (finding #3).

    Before this fix ``_is_in_route_handler`` stopped at the first enclosing function.
    If ``Path()`` was inside an inner helper the stop-at-first logic would find that
    helper (not a route), return False, and allow the codeql comment to suppress the
    finding.  After the fix the walker continues up the chain and correctly identifies
    the outer route handler.
    """
    detector = GuardedContextDirectPathDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/nested_codeql.py",
        (
            "from pathlib import Path\n"
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/x')\n"
            "def handler(path: str) -> str:\n"
            "    def _inner() -> str:\n"
            "        # codeql[py/path-injection]\n"
            "        return str(Path(path))\n"
            "    return _inner()\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule_id == "unguarded-direct-path"


def test_validation_bypass_detector_does_not_credit_nested_resolve_path_to_outer_handler(
    tmp_path: Path,
) -> None:
    """``resolve_path()`` inside a nested function is not attributed to the outer handler (finding #4).

    Before this fix ``_find_validated_fields`` used ``ast.walk`` which descends into
    nested scopes.  A ``resolve_path()`` call in an inner function would be credited
    to the outer route handler's validation context, potentially masking real bypasses
    or producing spurious findings.  After the fix only calls in the handler's own
    scope are credited.
    """
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/nested_resolve.py",
        (
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "def resolve_path(v, allowed): return v\n"
            "class Req:\n"
            "    input_dir: str\n"
            "class Settings:\n"
            "    allowed_paths: list = []\n"
            "class Organizer:\n"
            "    def organize(self, *, input_path): pass\n"
            "organizer = Organizer()\n"
            "@router.post('/x')\n"
            "def handler(request: Req, settings: Settings) -> None:\n"
            "    def _validate():\n"
            "        return resolve_path(request.input_dir, settings.allowed_paths)\n"
            "    organizer.organize(input_path=request.input_dir)\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    # Nested resolve_path not credited to outer handler → validated empty
    # → detector does not fire; avoids false positive from inner-scope attribution
    assert findings == []


def test_validation_bypass_detector_clears_stale_raw_alias_after_revalidation(
    tmp_path: Path,
) -> None:
    """A raw alias rebound to a validated value is not flagged as a bypass (finding #5).

    Before this fix ``_find_raw_field_aliases`` never removed an alias that was later
    overwritten by a ``resolve_path()`` call.  The stale raw alias would cause
    downstream uses of the now-validated name to be incorrectly flagged.
    """
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/rebound_alias.py",
        (
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "def resolve_path(v, allowed): return v\n"
            "class Req:\n"
            "    input_dir: str\n"
            "class Settings:\n"
            "    allowed_paths: list = []\n"
            "class Organizer:\n"
            "    def organize(self, *, input_path): pass\n"
            "organizer = Organizer()\n"
            "@router.post('/x')\n"
            "def handler(request: Req, settings: Settings) -> None:\n"
            "    user_path = resolve_path(request.input_dir, settings.allowed_paths)\n"
            "    user_path = request.input_dir\n"
            "    user_path = resolve_path(request.input_dir, settings.allowed_paths)\n"
            "    organizer.organize(input_path=user_path)\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert findings == []


def test_is_resolve_path_call_does_not_match_arbitrary_receiver_method(
    tmp_path: Path,
) -> None:
    """``other_svc.resolve_path(x)`` is not treated as security-validator invocation (T10).

    The attribute branch of ``_is_resolve_path_call`` must check that the root receiver
    is a known alias of the security validator, not just that the method name matches.
    An unrelated object with a method named ``resolve_path`` must not suppress bypass
    detection.
    """
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/unrelated_resolver.py",
        (
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "class PathHelper:\n"
            "    def resolve_path(self, v, allowed): return v\n"
            "class Req:\n"
            "    input_dir: str\n"
            "class Settings:\n"
            "    allowed_paths: list = []\n"
            "helper = PathHelper()\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    # No security validator recognized → validated empty → no bypass findings
    # (the unrelated helper.resolve_path() is correctly ignored)
    assert findings == []
