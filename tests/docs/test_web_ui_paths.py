"""Test that web UI documentation uses the correct access paths.

Validates:
- Web UI is documented as being at /ui/ prefix, not just /
- API docs are at /docs and /redoc
- Documented URLs in web-ui guides match actual FastAPI mount paths
"""

from __future__ import annotations

import re

import pytest

from tests.docs.conftest import DOCS_DIR

WEB_UI_DOCS_DIR = DOCS_DIR / "web-ui"

# Real mount paths from file_organizer/api/main.py:
# app.include_router(web_router, prefix="/ui")   → web UI at /ui/
# FastAPI auto-generates /docs and /redoc
REAL_WEB_UI_PREFIX = "/ui"
WRONG_WEB_UI_ROOT = "localhost:8000/"  # accessing root directly without /ui/


@pytest.mark.unit
class TestWebUIPaths:
    """Validate web UI access path documentation."""

    def test_web_ui_docs_dir_exists(self) -> None:
        """docs/web-ui/ directory must exist."""
        assert WEB_UI_DOCS_DIR.exists(), f"docs/web-ui/ directory not found at {WEB_UI_DOCS_DIR}"

    def test_web_ui_documented_at_ui_path(self) -> None:
        """Web UI must be documented as accessible at /ui/ not root /."""
        web_ui_docs = list(WEB_UI_DOCS_DIR.glob("*.md"))
        if not web_ui_docs:
            pytest.skip("No web-ui docs found")

        wrong_url_files = []
        for doc in web_ui_docs:
            content = doc.read_text()

            # Look for localhost:8000 or 127.0.0.1:8000 without /ui/ path
            wrong_access = re.findall(
                r"https?://(?:localhost|127\.0\.0\.1):\d+(?:/(?!ui/))?(?:\s|\"|\)|$)", content
            )
            # Filter to only clearly wrong ones (root access without /ui/)
            truly_wrong = [url for url in wrong_access if re.search(r":\d+/?(?:\s|\"|\))", url)]

            if truly_wrong:
                wrong_url_files.append(f"  {doc.relative_to(DOCS_DIR)}: {truly_wrong[:2]}")

        assert not wrong_url_files, (
            "These web-ui docs reference the root URL without /ui/ prefix:\n"
            + "\n".join(wrong_url_files)
            + "\n\nFix: Change 'http://localhost:8000/' to 'http://localhost:8000/ui/'"
        )

    def test_web_ui_getting_started_uses_ui_path(self) -> None:
        """Getting started guide must show /ui/ access path."""
        getting_started = WEB_UI_DOCS_DIR / "getting-started.md"
        if not getting_started.exists():
            pytest.skip("getting-started.md not found in web-ui/")

        content = getting_started.read_text()

        # Must mention /ui/ path somewhere
        has_ui_path = "/ui/" in content or "/ui" in content
        has_wrong_root = bool(re.search(r"localhost:\d+(?:/\s|/\"|\))", content))

        if has_wrong_root and not has_ui_path:
            pytest.fail(
                "docs/web-ui/getting-started.md shows root URL access without /ui/ prefix. "
                "The web UI is mounted at /ui/, not at root /. "
                "Fix: Change 'http://localhost:8000/' to 'http://localhost:8000/ui/'"
            )

    def test_api_docs_path_documented(self) -> None:
        """API docs should be documented as accessible at /docs (FastAPI auto-generates this)."""
        # Check across web-ui and admin docs
        docs_to_check = list(WEB_UI_DOCS_DIR.glob("*.md")) + list((DOCS_DIR / "admin").glob("*.md"))

        for doc in docs_to_check:
            content = doc.read_text()
            # If they mention /redoc or Swagger, check the path is correct
            if "redoc" in content.lower() or "swagger" in content.lower():
                # /docs and /redoc are the standard FastAPI paths
                if "/api-docs" in content or "/swagger" in content:
                    pytest.fail(
                        f"{doc.relative_to(DOCS_DIR)}: Documents '/api-docs' or '/swagger' paths "
                        "but FastAPI uses '/docs' and '/redoc'. "
                        "Fix: Replace with standard FastAPI doc paths: /docs and /redoc"
                    )


@pytest.mark.unit
class TestHomePageRedirect:
    """Validate root URL behavior documentation."""

    def test_getting_started_clarifies_root_vs_ui(self) -> None:
        """Docs should clarify that / redirects or explain /ui/ is the entry point."""
        getting_started_global = DOCS_DIR / "getting-started.md"
        if not getting_started_global.exists():
            pytest.skip("docs/getting-started.md not found")

        content = getting_started_global.read_text()

        # The global getting started should mention /ui/ as the web interface URL
        if (
            "web" in content.lower()
            or "browser" in content.lower()
            or "interface" in content.lower()
        ):
            has_ui_mention = "/ui" in content or "ui/" in content
            if not has_ui_mention:
                pytest.fail(
                    "docs/getting-started.md mentions web/browser/interface but doesn't "
                    "show the correct /ui/ path. "
                    "Fix: Add 'Access the web interface at http://localhost:8000/ui/'"
                )
