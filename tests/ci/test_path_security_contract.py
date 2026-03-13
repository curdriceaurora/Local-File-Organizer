"""Guardrails for filesystem path handling in API/web modules."""

from __future__ import annotations

from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = FO_ROOT / "src" / "file_organizer"
CODEQL_CONFIG = FO_ROOT / ".github" / "codeql" / "codeql-config.yml"

pytestmark = pytest.mark.ci


# Keep direct Path(...) usage intentionally constrained so new path-handling
# code is reviewed for allow-root enforcement and CodeQL compatibility.
_ALLOWED_PATH_SNIPPETS: dict[str, set[str]] = {
    "api/api_keys.py": {
        'output_path = Path(argv[argv.index("--output") + 1]).expanduser()',
        # Multi-line variants (formatter may break long lines)
        'argv[argv.index("--output") + 1]',
    },
    "api/config.py": {
        "path = Path(config_path).expanduser()",
    },
    "api/utils.py": {
        "resolved = Path(path_value).expanduser()",
        "roots = [os.path.realpath(Path(root).expanduser()) for root in allowed_paths]",
        "return Path(resolved_str)",
        # Multi-line variants (formatter may break long lines)
        "os.path.realpath(Path(root).expanduser())",
    },
    "api/routers/system.py": {
        "file_info_from_path(Path(info.path))",
    },
    # Mock endpoints that treat file_id as a path for simple ID lookup;
    # these are intentionally not resolve_path()-guarded as they are
    # placeholder implementations for future database-backed ID lookup.
    "api/routers/files.py": {
        "target = Path(file_id)",
    },
    # Search endpoint uses allowed_paths from trusted config for search roots.
    # Explicit path filter uses resolve_path() for request-driven paths.
    "api/routers/search.py": {
        "search_roots = [Path(p) for p in settings.allowed_paths]",
        "search_roots = [Path(p).resolve() for p in settings.allowed_paths]",
        # Multi-line variants (formatter may break long lines)
        "Path(p).resolve() for p in settings.allowed_paths",
        # Variant when comment is inline and line wraps
        "]  # codeql[py/path-injection]",
    },
    "web/_helpers.py": {
        "BASE_DIR = Path(__file__).resolve().parent",
        "safe_name = Path(name).name.strip()",
    },
    "web/files_routes.py": {
        "raw_name = Path(upload.filename).name.strip()",
    },
    # service_facade wraps business-logic calls where the paths originate
    # from request bodies already validated by the router layer.
    "api/service_facade.py": {
        "target = Path(path)",
        "detector.scan_directory(Path(scan_dir))",
    },
}


_CODEQL_SUPPRESSED_SNIPPETS: dict[str, set[str]] = {
    "api/api_keys.py": {
        'output_path = Path(argv[argv.index("--output") + 1]).expanduser()',
    },
    "api/config.py": {
        "path = Path(config_path).expanduser()",
    },
    "api/utils.py": {
        "resolved = Path(path_value).expanduser()",
        "roots = [os.path.realpath(Path(root).expanduser()) for root in allowed_paths]",
    },
}


def _iter_python_files() -> list[Path]:
    api_dir = SRC_ROOT / "api"
    web_dir = SRC_ROOT / "web"
    return sorted([*api_dir.rglob("*.py"), *web_dir.rglob("*.py")])


def test_direct_path_usage_is_allowlisted() -> None:
    violations: list[str] = []

    for path in _iter_python_files():
        rel = path.relative_to(SRC_ROOT).as_posix()
        allowed = _ALLOWED_PATH_SNIPPETS.get(rel, set())
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if "Path(" not in line or stripped.startswith("#"):
                continue
            if not any(snippet in line for snippet in allowed):
                violations.append(f"{rel}:{line_no}: {stripped}")

    assert not violations, (
        "Found non-allowlisted direct Path(...) usage.\n"
        "Use resolve_path for request-driven paths or add explicit review notes.\n"
        + "\n".join(violations)
    )


def test_tainted_path_usage_has_codeql_suppression_comment() -> None:
    violations: list[str] = []

    for rel, snippets in _CODEQL_SUPPRESSED_SNIPPETS.items():
        lines = (SRC_ROOT / rel).read_text(encoding="utf-8").splitlines()
        for snippet in snippets:
            try:
                index = next(i for i, line in enumerate(lines) if snippet in line)
            except StopIteration:
                violations.append(f"{rel}: missing snippet '{snippet}'")
                continue
            # Allow comment on same line or one of the two lines above.
            window = "\n".join(lines[max(0, index - 2) : index + 1])
            if "codeql[py/path-injection]" not in window:
                violations.append(f"{rel}:{index + 1}: missing codeql suppression for '{snippet}'")

    assert not violations, "Missing CodeQL suppression comments:\n" + "\n".join(violations)


def test_intentional_security_detector_fixtures_are_ignored_by_codeql() -> None:
    config_text = CODEQL_CONFIG.read_text(encoding="utf-8")

    assert "tests/fixtures/review_regressions/security/**" in config_text, (
        "Intentional unsafe security-detector fixtures must stay out of CodeQL analysis.\n"
        "Update .github/codeql/codeql-config.yml paths-ignore when adding or moving them."
    )
