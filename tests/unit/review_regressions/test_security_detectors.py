from __future__ import annotations

import ast
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

    The second module uses bare ``Path(path)`` without any pathlib import.  If the seed
    were re-added, that call would be flagged, producing two findings instead of one.
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
    _write_module(
        tmp_path,
        "src/file_organizer/api/no_import_path.py",
        (
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/y')\n"
            "def view2(path: str) -> str:\n"
            "    return str(Path(path))\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    # Only P(path) in aliased_only.py should flag — bare Path() in no_import_path.py
    # has no pathlib import so _path_constructor_names returns {} for that file.
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
    """``helper.resolve_path(x)`` is not treated as a security-validator invocation (T10).

    The attribute branch of ``_is_resolve_path_call`` checks that the root receiver is
    a name in ``resolve_path_names``, not just that the method name is ``resolve_path``.
    When only an unrelated object's method is called, ``_find_validated_fields`` must
    return empty so the handler is skipped entirely.

    If ``_is_resolve_path_call`` were broken to accept any attribute call named
    ``resolve_path``, it would credit ``helper.resolve_path(request.input_dir, ...)`` as
    validation, which would then cause the raw ``request.input_dir`` passed to
    ``organize()`` to be flagged as a bypass (1 finding instead of 0).
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
            "class Organizer:\n"
            "    def organize(self, *, input_path): pass\n"
            "helper = PathHelper()\n"
            "organizer = Organizer()\n"
            "@router.post('/x')\n"
            "def handler(request: Req, settings: Settings) -> None:\n"
            "    _v = helper.resolve_path(request.input_dir, settings.allowed_paths)\n"
            "    organizer.organize(input_path=request.input_dir)\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    # helper.resolve_path() receiver "helper" is not in resolve_path_names →
    # _find_validated_fields returns {} → handler skipped → no findings.
    # A broken _is_resolve_path_call would credit helper.resolve_path as validation
    # and flag the raw request.input_dir at organize() (1 finding).
    assert findings == []


def test_validation_bypass_detector_flags_pre_validation_raw_alias(
    tmp_path: Path,
) -> None:
    """A raw alias assigned *before* ``resolve_path()`` is still flagged at the sink.

    Before the fix, ``_find_raw_field_aliases`` filtered out aliases whose assignment
    line was <= the validation line, so ``raw = request.input_dir`` appearing before
    ``resolve_path(request.input_dir, ...)`` was silently dropped.  The alias can then
    be passed to a sink that runs after validation — a genuine bypass that must be
    caught.
    """
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/pre_validation_alias.py",
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
            "    raw = request.input_dir\n"
            "    _ = resolve_path(request.input_dir, settings.allowed_paths)\n"
            "    organizer.organize(input_path=raw)\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "raw-field-after-validation"
    assert "alias raw sourced from raw request.input_dir" in finding.message


def test_validation_bypass_detector_recognizes_from_api_utils_alias(
    tmp_path: Path,
) -> None:
    """``from ...api import utils as utils`` must count as resolve_path provenance."""
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/from_api_utils_alias.py",
        (
            "from file_organizer.api import utils as utils\n"
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


def test_validation_bypass_detector_clears_stale_alias_after_non_validation_rebind(
    tmp_path: Path,
) -> None:
    """Non-validation rebind *before* the sink must clear the stale raw alias."""
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/non_validation_rebind.py",
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
            "    _ = resolve_path(request.input_dir, settings.allowed_paths)\n"
            "    raw = request.input_dir\n"
            "    raw = None\n"
            "    organizer.organize(input_path=raw)\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert findings == []


def test_validation_bypass_detector_flags_alias_when_rebind_is_after_sink(
    tmp_path: Path,
) -> None:
    """A rebind occurring *after* the sink must not suppress the finding (T10 negative)."""
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/post_sink_rebind.py",
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
            "    _ = resolve_path(request.input_dir, settings.allowed_paths)\n"
            "    raw = request.input_dir\n"
            "    organizer.organize(input_path=raw)\n"
            "    raw = None\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule_id == "raw-field-after-validation"


def test_validation_bypass_detector_uses_latest_raw_assignment_when_name_reused(
    tmp_path: Path,
) -> None:
    """When the same name is assigned a raw field twice, the *later* assignment is canonical.

    If ``_walk_function_body`` yields nodes out of source order, a naive overwrite
    can leave the earliest raw assignment as the alias.  The later raw assignment at a
    higher line number must be the one used, so that ``rebind_lines`` correctly reflects
    subsequent lines (T10 negative — ensures the ``candidate.line > existing.line``
    guard is exercised).
    """
    detector = ValidatedPathBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/api/double_raw_assignment.py",
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
            "    _ = resolve_path(request.input_dir, settings.allowed_paths)\n"
            "    raw = request.input_dir\n"
            "    raw = request.input_dir\n"
            "    organizer.organize(input_path=raw)\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule_id == "raw-field-after-validation"


# ── T10 predicate negative-case tests (issue #930) ───────────────────────────


def _parse_security_call(src: str) -> ast.Call:
    return ast.parse(src).body[0].value  # type: ignore[return-value]


def _parse_security_expr(src: str) -> ast.expr:
    return ast.parse(src).body[0].value  # type: ignore[return-value]


def test_is_path_call_returns_false_for_non_call_node() -> None:
    from file_organizer.review_regressions.security import _is_path_call

    node = ast.parse("x").body[0].value
    assert not _is_path_call(node, constructor_names={"Path"}, module_aliases={"pathlib"})


def test_is_path_call_returns_false_for_unrelated_name_call() -> None:
    from file_organizer.review_regressions.security import _is_path_call

    node = _parse_security_call("Other(x)")
    assert not _is_path_call(node, constructor_names={"Path"}, module_aliases={"pathlib"})


def test_is_resolve_path_call_returns_false_for_non_call() -> None:
    from file_organizer.review_regressions.security import _is_resolve_path_call

    node = ast.parse("x").body[0].value
    assert not _is_resolve_path_call(node, {"resolve_path"})


def test_is_resolve_path_call_returns_false_for_arbitrary_receiver_attr_call() -> None:
    from file_organizer.review_regressions.security import _is_resolve_path_call

    node = _parse_security_call("unrelated_service.resolve_path(x)")
    assert not _is_resolve_path_call(node, {"resolve_path"})


def test_is_allowed_paths_expr_returns_false_for_unrelated_name() -> None:
    from file_organizer.review_regressions.security import _is_allowed_paths_expr

    node = _parse_security_expr("other_paths")
    assert not _is_allowed_paths_expr(node)


def test_is_allowed_paths_expr_returns_false_for_non_name_non_attr() -> None:
    from file_organizer.review_regressions.security import _is_allowed_paths_expr

    node = _parse_security_expr("42")
    assert not _is_allowed_paths_expr(node)


def test_is_allowed_file_info_wrapper_returns_false_when_parent_is_not_call() -> None:
    from file_organizer.review_regressions.security import _is_allowed_file_info_wrapper

    src = "Path(x)"
    tree = ast.parse(src)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    assert not _is_allowed_file_info_wrapper(call, parents)


def test_is_route_handler_returns_false_for_non_decorated_function() -> None:
    from file_organizer.review_regressions.security import _is_route_handler

    src = "def plain(): pass"
    node = ast.parse(src).body[0]
    assert isinstance(node, ast.FunctionDef)
    assert not _is_route_handler(node)


def test_is_route_handler_returns_false_for_unrelated_decorator() -> None:
    from file_organizer.review_regressions.security import _is_route_handler

    src = "@staticmethod\ndef plain(): pass"
    node = ast.parse(src).body[0]
    assert isinstance(node, ast.FunctionDef)
    assert not _is_route_handler(node)


def test_is_safe_model_copy_call_returns_false_for_non_model_copy_attr() -> None:
    from file_organizer.review_regressions.security import _is_safe_model_copy_call

    node = _parse_security_call("obj.copy()")
    assert not _is_safe_model_copy_call(node)


def test_is_safe_model_copy_call_returns_false_for_name_call() -> None:
    from file_organizer.review_regressions.security import _is_safe_model_copy_call

    node = _parse_security_call("model_copy()")
    assert not _is_safe_model_copy_call(node)


def test_is_sensitive_validation_sink_returns_false_for_unrelated_call() -> None:
    from file_organizer.review_regressions.security import _is_sensitive_validation_sink

    node = _parse_security_call("do_something(x)")
    assert not _is_sensitive_validation_sink(node)


def test_is_request_model_construction_returns_false_for_lowercase_name_call() -> None:
    from file_organizer.review_regressions.security import _is_request_model_construction

    node = _parse_security_call("organizeRequest(x)")
    assert not _is_request_model_construction(node)


def test_is_request_model_construction_returns_false_for_non_request_suffix() -> None:
    from file_organizer.review_regressions.security import _is_request_model_construction

    node = _parse_security_call("OrganizeResponse(x)")
    assert not _is_request_model_construction(node)


def _build_security_parents(src: str) -> tuple[ast.AST, dict[ast.AST, ast.AST]]:
    tree = ast.parse(src)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return tree, parents


def test_is_basename_extraction_returns_false_for_path_call_not_followed_by_safe_attr() -> None:
    from file_organizer.review_regressions.security import _is_basename_extraction

    src = "Path(x)"
    tree, parents = _build_security_parents(src)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert not _is_basename_extraction(call, parents)


def test_is_allowed_config_root_path_returns_false_for_call_with_non_allowed_iter() -> None:
    from file_organizer.review_regressions.security import _is_allowed_config_root_path

    src = "[Path(p) for p in other_paths]"
    tree, parents = _build_security_parents(src)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert not _is_allowed_config_root_path(call, parents)


def test_is_in_route_handler_returns_false_for_node_inside_plain_function() -> None:
    from file_organizer.review_regressions.security import _is_in_route_handler

    src = "def plain():\n    x = 1\n"
    tree, parents = _build_security_parents(src)
    assign = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign))
    assert not _is_in_route_handler(assign, parents)


def test_is_allowed_direct_path_call_returns_false_for_unguarded_call_outside_resolve_path() -> (
    None
):
    from file_organizer.review_regressions.security import _is_allowed_direct_path_call

    src = "def handler():\n    p = Path(user_input)\n"
    tree = ast.parse(src)
    lines = src.splitlines()
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert not _is_allowed_direct_path_call(call, parents=parents, lines=lines)


def test_find_validated_fields_returns_empty_for_function_with_no_resolve_path_calls() -> None:
    from file_organizer.review_regressions.security import _find_validated_fields

    src = "def handler():\n    x = request.input_dir\n"
    tree = ast.parse(src)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    assert not _find_validated_fields(func, resolve_path_names={"resolve_path"})


def test_find_raw_field_aliases_returns_empty_when_no_validated_fields() -> None:
    from file_organizer.review_regressions.security import _find_raw_field_aliases

    src = "def handler():\n    x = request.input_dir\n"
    tree = ast.parse(src)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    assert not _find_raw_field_aliases(func, validated={})
