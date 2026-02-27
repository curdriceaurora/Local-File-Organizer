"""Test that code examples in documentation are syntactically valid and use real paths.

Validates:
- Python code blocks parse without syntax errors
- cURL examples reference real API endpoints (not phantom routes)
- Import paths in examples reference real modules
- No deprecated or wrong endpoint patterns in code blocks
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.docs.conftest import DOCS_DIR, SRC_DIR, extract_code_blocks

# Known-real endpoint paths (derived from code inspection of api/routers/)
REAL_API_ENDPOINTS = {
    "/api/v1/health",
    "/api/v1/auth/token",
    "/api/v1/files",
    "/api/v1/organize/scan",
    "/api/v1/organize/preview",
    "/api/v1/organize/execute",
    "/api/v1/organize/status",
    "/api/v1/dedupe/scan",
    "/api/v1/dedupe/preview",
    "/api/v1/dedupe/execute",
    "/api/v1/ws",  # WebSocket base
    "/api/v1/ws/{client_id}",
    "/api/v1/system",
    "/api/v1/marketplace",
    "/api/v1/integrations",
}

# Phantom endpoints that do NOT exist
PHANTOM_ENDPOINTS = [
    "/api/v1/files/upload",  # No upload route — files router handles differently
    "/api/v1/organize",  # No single POST /organize — uses sub-paths
    "/api/v1/analyze",  # No /analyze prefix
    "/api/v1/analyze/duplicates",  # Wrong — should be /dedupe/*
]

# Real importable modules under src/file_organizer/
REAL_MODULES_CHECK = [
    "file_organizer",
    "file_organizer.api",
    "file_organizer.web",
]


@pytest.mark.unit
class TestPythonCodeExamples:
    """Validate Python code blocks in documentation parse without syntax errors."""

    def test_python_examples_parse(self, all_doc_files: list[Path]) -> None:
        """All Python code blocks in docs must be valid Python syntax."""
        syntax_errors = []

        for md_file in all_doc_files:
            content = md_file.read_text(encoding="utf-8")
            python_blocks = extract_code_blocks(content, "python")

            for i, block in enumerate(python_blocks):
                # Skip blocks that are clearly fragments/comments only
                stripped = block.strip()
                if not stripped:
                    continue
                # Skip blocks that start with #! (shebang) or are just comments
                lines = [
                    line
                    for line in stripped.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                if not lines:
                    continue

                try:
                    ast.parse(stripped)
                except SyntaxError as e:
                    rel = md_file.relative_to(DOCS_DIR)
                    syntax_errors.append(
                        f"  {rel} (block {i + 1}): {e.msg} at line {e.lineno}\n"
                        f"    Snippet: {stripped[:100]!r}"
                    )

        assert not syntax_errors, (
            f"Found {len(syntax_errors)} Python syntax error(s) in docs:\n"
            + "\n".join(syntax_errors[:10])
            + ("\n  ... (truncated)" if len(syntax_errors) > 10 else "")
        )

    def test_no_phantom_upload_endpoint_in_examples(self, all_doc_files: list[Path]) -> None:
        """Python code blocks must not reference the non-existent /files/upload endpoint."""
        violations = []

        for md_file in all_doc_files:
            content = md_file.read_text(encoding="utf-8")
            python_blocks = extract_code_blocks(content, "python")

            for block in python_blocks:
                if "/files/upload" in block:
                    rel = md_file.relative_to(DOCS_DIR)
                    violations.append(
                        f"  {rel}: Python example references non-existent "
                        f"'/files/upload' endpoint. Use '/api/v1/files' (POST with multipart)."
                    )

        assert not violations, (
            "Python code examples reference phantom /files/upload endpoint:\n"
            + "\n".join(violations)
        )

    def test_no_wrong_organize_endpoint_in_examples(self, all_doc_files: list[Path]) -> None:
        """Python examples must use real organize sub-paths, not POST /organize."""
        violations = []

        for md_file in all_doc_files:
            content = md_file.read_text(encoding="utf-8")
            python_blocks = extract_code_blocks(content, "python")

            for block in python_blocks:
                # Flag POST to /api/v1/organize directly (without sub-path)
                if re.search(r"['\"]POST['\"].*['\"].*?/organize['\"](?!\s*/)", block):
                    rel = md_file.relative_to(DOCS_DIR)
                    violations.append(
                        f"  {rel}: Python example POSTs to '/organize' directly. "
                        f"Use '/organize/scan', '/organize/preview', or '/organize/execute'."
                    )

        assert not violations, "Python code examples use wrong organize endpoint:\n" + "\n".join(
            violations
        )


@pytest.mark.unit
class TestCurlExamples:
    """Validate cURL examples in documentation reference real API endpoints."""

    def _extract_curl_paths(self, block: str) -> list[str]:
        """Extract URL paths from cURL commands."""
        # Match curl http://host:port/path or curl -X METHOD http://host:port/path
        paths = re.findall(r"curl[^\n]*https?://[^/\s]+(/api/v\d+/[^\s'\"\\]+)", block)
        return paths

    def test_curl_examples_use_real_endpoints(self, all_doc_files: list[Path]) -> None:
        """cURL examples must not reference phantom endpoints."""
        violations = []

        for md_file in all_doc_files:
            content = md_file.read_text(encoding="utf-8")
            bash_blocks = extract_code_blocks(content, "bash")
            # Also check unlabeled blocks for curl commands
            all_blocks = extract_code_blocks(content, "")

            all_curl_blocks = [b for b in (bash_blocks + all_blocks) if "curl " in b]

            for block in all_curl_blocks:
                for phantom in PHANTOM_ENDPOINTS:
                    # Match phantom path followed by space, quote, newline, or end-of-string
                    # This avoids matching /api/v1/organize as a prefix of /api/v1/organize/scan
                    if re.search(re.escape(phantom) + r"(?:\s|['\"\?#]|$)", block):
                        rel = md_file.relative_to(DOCS_DIR)
                        violations.append(
                            f"  {rel}: cURL example uses phantom endpoint '{phantom}'"
                        )

        assert not violations, (
            "cURL examples reference non-existent endpoints:\n"
            + "\n".join(violations)
            + "\n\nCheck REAL_API_ENDPOINTS for valid paths."
        )

    def test_curl_auth_uses_x_api_key_header(self, all_doc_files: list[Path]) -> None:
        """cURL examples must use X-API-Key header, not Authorization: Bearer."""
        violations = []

        for md_file in all_doc_files:
            content = md_file.read_text(encoding="utf-8")
            bash_blocks = extract_code_blocks(content, "bash")
            all_blocks = extract_code_blocks(content, "")

            all_curl_blocks = [b for b in (bash_blocks + all_blocks) if "curl " in b]

            for block in all_curl_blocks:
                # cURL with API path should not use Authorization: Bearer
                if "/api/v" in block and "Authorization: Bearer" in block:
                    rel = md_file.relative_to(DOCS_DIR)
                    violations.append(
                        f"  {rel}: cURL example uses 'Authorization: Bearer' — "
                        f"should use 'X-API-Key: <key>'"
                    )

        assert not violations, "cURL examples use wrong auth header:\n" + "\n".join(violations)


@pytest.mark.unit
class TestImportPathsInExamples:
    """Validate that import statements in examples reference real modules."""

    def test_file_organizer_imports_use_real_packages(self, all_doc_files: list[Path]) -> None:
        """Python imports from file_organizer.* must reference existing top-level modules."""
        # Get real top-level subpackages under src/file_organizer/
        fo_src = SRC_DIR / "file_organizer"
        real_subpackages = set()
        if fo_src.exists():
            for p in fo_src.iterdir():
                if p.is_dir() and (p / "__init__.py").exists():
                    real_subpackages.add(p.name)
                elif p.is_file() and p.suffix == ".py" and p.name != "__init__.py":
                    real_subpackages.add(p.stem)

        if not real_subpackages:
            pytest.skip("Cannot find file_organizer source directory")

        violations = []

        for md_file in all_doc_files:
            content = md_file.read_text(encoding="utf-8")
            python_blocks = extract_code_blocks(content, "python")

            for block in python_blocks:
                # Find: from file_organizer.X import Y  or  import file_organizer.X
                imports = re.findall(r"(?:from|import)\s+file_organizer\.(\w+)", block)
                for subpkg in imports:
                    if subpkg not in real_subpackages:
                        rel = md_file.relative_to(DOCS_DIR)
                        violations.append(
                            f"  {rel}: imports from 'file_organizer.{subpkg}' "
                            f"but that subpackage doesn't exist. "
                            f"Real subpackages: {sorted(real_subpackages)}"
                        )

        assert not violations, (
            "Documentation examples import from non-existent modules:\n"
            + "\n".join(violations[:10])
            + ("\n  ... (truncated)" if len(violations) > 10 else "")
        )


@pytest.mark.unit
class TestApiKeyFormatInExamples:
    """Validate API key format used in examples matches real format."""

    def test_no_fk_live_api_key_format_in_examples(self, all_doc_files: list[Path]) -> None:
        """Code examples must not show 'fk_live_*' API key format (that's the wrong format)."""
        violations = []

        for md_file in all_doc_files:
            content = md_file.read_text(encoding="utf-8")
            # Check all code blocks (any language)
            all_blocks = extract_code_blocks(content, "")
            python_blocks = extract_code_blocks(content, "python")
            bash_blocks = extract_code_blocks(content, "bash")

            for block in all_blocks + python_blocks + bash_blocks:
                if "fk_live_" in block:
                    rel = md_file.relative_to(DOCS_DIR)
                    violations.append(
                        f"  {rel}: code example uses 'fk_live_*' API key format. "
                        f"Correct format is 'fo_<id>_<token>'."
                    )

        # Deduplicate
        violations = list(dict.fromkeys(violations))

        assert not violations, "Code examples use wrong API key format:\n" + "\n".join(violations)
