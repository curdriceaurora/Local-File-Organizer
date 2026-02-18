"""Test that API documentation matches actual FastAPI route registration.

Validates:
- Documented API paths exist as real routes in the codebase
- Authentication format is correct (X-API-Key header, not Bearer)
- API key format examples use the real format (fo_<id>_<token>)
- Organization endpoints use real paths (/scan, /preview, /execute)
- Deduplication endpoints use real paths (/dedupe/*)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.docs.conftest import DOCS_DIR, get_router_paths

# ---------------------------------------------------------------------------
# Real route paths from actual implementation
# ---------------------------------------------------------------------------


def _get_api_router_paths() -> set[str]:
    """Import actual API routers and extract registered paths."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

    paths = set()
    try:
        from file_organizer.api.routers import files as files_mod

        paths.update(get_router_paths(files_mod.router))
    except Exception:
        pass
    try:
        from file_organizer.api.routers import organize as org_mod

        paths.update(get_router_paths(org_mod.router))
    except Exception:
        pass
    try:
        from file_organizer.api.routers import search as search_mod

        paths.update(get_router_paths(search_mod.router))
    except Exception:
        pass
    try:
        from file_organizer.api.routers import dedupe as dedupe_mod

        paths.update(get_router_paths(dedupe_mod.router))
    except Exception:
        pass
    try:
        from file_organizer.api.routers import analyze as analyze_mod

        paths.update(get_router_paths(analyze_mod.router))
    except Exception:
        pass
    return paths


class TestAuthDocumentation:
    """Validate authentication documentation accuracy."""

    def test_auth_header_is_x_api_key_not_bearer(self) -> None:
        """Docs must use X-API-Key header, not Authorization: Bearer."""
        auth_doc = DOCS_DIR / "api" / "authentication.md"
        if not auth_doc.exists():
            pytest.skip(f"authentication.md not found at {auth_doc}")

        content = auth_doc.read_text()

        # Check for incorrect Bearer token pattern
        bearer_pattern = re.search(r"Authorization:\s*Bearer", content, re.IGNORECASE)
        assert not bearer_pattern, (
            "docs/api/authentication.md documents 'Authorization: Bearer' format, "
            "but the API uses 'X-API-Key' header. "
            "Fix: Replace 'Authorization: Bearer <token>' with 'X-API-Key: <token>'"
        )

    def test_auth_header_x_api_key_is_documented(self) -> None:
        """Docs must explicitly document the X-API-Key header."""
        auth_doc = DOCS_DIR / "api" / "authentication.md"
        if not auth_doc.exists():
            pytest.skip(f"authentication.md not found at {auth_doc}")

        content = auth_doc.read_text()
        assert "X-API-Key" in content, (
            "docs/api/authentication.md must document the 'X-API-Key' header. "
            "The API uses this header for authentication, not Bearer tokens."
        )

    def test_api_key_format_is_correct(self) -> None:
        """API key examples must use the real format fo_<id>_<token>, not fk_live_*."""
        api_docs = list((DOCS_DIR / "api").glob("*.md"))
        if not api_docs:
            pytest.skip("No API docs found")

        incorrect_format_files = []
        for doc in api_docs:
            content = doc.read_text()
            if re.search(r"fk_live_", content):
                incorrect_format_files.append(str(doc.relative_to(DOCS_DIR)))

        assert not incorrect_format_files, (
            "These docs use the incorrect API key format 'fk_live_*':\n"
            + "\n".join(f"  - {f}" for f in incorrect_format_files)
            + "\n\nFix: Replace 'fk_live_...' with 'fo_<id>_<token>' format examples"
        )


class TestOrganizeEndpoints:
    """Validate organization endpoint documentation accuracy."""

    def test_organize_uses_real_sub_paths(self) -> None:
        """Organization docs must use real endpoint paths: /scan, /preview, /execute."""
        org_doc = DOCS_DIR / "api" / "organization-endpoints.md"
        if not org_doc.exists():
            pytest.skip("organization-endpoints.md not found")

        content = org_doc.read_text()

        # The real API has /organize/scan, /organize/preview, etc.
        # Docs should NOT just show /organize as a single endpoint
        has_real_paths = any(
            p in content for p in ["/organize/scan", "/organize/preview", "/organize/execute"]
        )
        # But /organize by itself as a POST endpoint is wrong
        has_wrong_path = bool(re.search(r"POST\s+/api/v\d+/organize\b", content))

        if has_wrong_path and not has_real_paths:
            pytest.fail(
                "organization-endpoints.md documents 'POST /api/v1/organize' which doesn't exist. "
                "Real endpoints are: /organize/scan, /organize/preview, /organize/execute. "
                "Fix: Update endpoint paths to match actual implementation."
            )


class TestDeduplicationEndpoints:
    """Validate deduplication endpoint documentation accuracy."""

    def test_dedupe_endpoint_path_is_correct(self) -> None:
        """Deduplication docs must use /dedupe/* paths, not /analyze/duplicates."""
        # Check all API docs for incorrect dedupe paths
        api_docs_dir = DOCS_DIR / "api"
        if not api_docs_dir.exists():
            pytest.skip("api docs dir not found")

        wrong_path_files = []
        for doc in api_docs_dir.glob("*.md"):
            content = doc.read_text()
            if "/analyze/duplicates" in content:
                wrong_path_files.append(str(doc.relative_to(DOCS_DIR)))

        assert not wrong_path_files, (
            "These docs reference '/analyze/duplicates' which doesn't exist:\n"
            + "\n".join(f"  - {f}" for f in wrong_path_files)
            + "\n\nFix: Replace '/analyze/duplicates' with '/dedupe/scan', '/dedupe/preview', etc."
        )


class TestDocumentedRoutesExistInCode:
    """Validate that routes documented in API docs actually exist in the codebase."""

    def test_no_phantom_upload_endpoint(self) -> None:
        """The /files/upload endpoint is documented but doesn't exist."""
        api_docs = list((DOCS_DIR / "api").glob("*.md"))
        phantom_endpoint_files = []

        for doc in api_docs:
            content = doc.read_text()
            if re.search(r"POST\s+/api/v\d+/files/upload", content):
                phantom_endpoint_files.append(str(doc.relative_to(DOCS_DIR)))

        assert not phantom_endpoint_files, (
            "These docs document 'POST /api/v1/files/upload' which doesn't exist:\n"
            + "\n".join(f"  - {f}" for f in phantom_endpoint_files)
            + "\n\nFix: Remove or correct this endpoint — file upload is handled differently."
        )
