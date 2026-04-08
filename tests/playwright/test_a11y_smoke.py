"""Browser E2E accessibility smoke tests (B5).

Runs axe-core against the five core rendered pages and enforces this policy:

Violation policy
----------------
* critical     → hard fail via ``pytest.fail()`` (CI fails on any critical violation)
* serious /
  moderate     → ``warnings.warn()`` — logged for triage, build does not fail
* minor        → ignored

The policy is centralised in ``_assert_no_critical_a11y()``; future
tightening (e.g. promoting serious to failing) requires changing one
function only.

Critical-violation procedure
-----------------------------
If ``_assert_no_critical_a11y`` reaches the ``pytest.fail()`` branch:

1. Run the failing test with ``-s`` to capture ``generate_report()`` output.
2. File a GitHub issue labelled ``accessibility`` and ``bug`` with the axe
   violation ID, impact, and affected selector.
3. Fix the violation in the template/CSS/JS and re-run the tests to confirm
   CI is green again.  Reference the issue number in the fix commit.

Running
-------
    pytest tests/playwright/test_a11y_smoke.py \\
        --browser chromium --override-ini='addopts='
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

try:
    from axe_playwright_python.sync_playwright import Axe
except ImportError as exc:
    raise ImportError(
        "axe-playwright-python is required: pip install axe-playwright-python"
    ) from exc

try:
    from playwright.sync_api import Page
except ImportError as exc:
    raise ImportError(
        "Playwright is required: pip install playwright && playwright install chromium"
    ) from exc

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.playwright,
    pytest.mark.timeout(60),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _assert_no_critical_a11y(page: Page, path: str) -> None:
    """Navigate to *path*, assert the page loaded, run axe, apply violation policy.

    Policy (documented in module docstring):
    - critical        → ``pytest.fail()`` with full ``generate_report()`` output (CI fails)
    - serious/moderate → ``warnings.warn()`` (logged, not failing)
    - minor           → ignored

    Args:
        page: Playwright Page already positioned on the live server.
        path: Absolute UI path, e.g. ``"/ui/files"``.

    Raises:
        AssertionError: If ``page.goto()`` returns a non-2xx response.
    """
    response = page.goto(path)
    assert response is not None and response.ok, (
        f"Expected 2xx loading {path}, got {getattr(response, 'status', 'None')}"
    )
    results = Axe().run(page)
    critical = [v for v in results.response["violations"] if v["impact"] == "critical"]
    non_critical = [
        v for v in results.response["violations"] if v["impact"] in ("serious", "moderate")
    ]
    if non_critical:
        warnings.warn(
            f"{path}: {len(non_critical)} serious/moderate a11y violation(s) "
            f"(triage only — not failing the build):\n{results.generate_report()}",
            stacklevel=2,
        )
    if critical:
        pytest.fail(
            f"{path}: {len(critical)} critical a11y violation(s):\n{results.generate_report()}"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_a11y_setup_page(page: Page, playwright_config_dir: Path) -> None:
    """Setup wizard page has zero critical a11y violations.

    Deletes ``config.yaml`` before navigating so the setup wizard always
    renders with ``setup_completed=False``, regardless of test-execution order.
    Matches the isolation pattern in ``test_smoke.py::test_home_redirect``.
    """
    config_file = playwright_config_dir / "file-organizer" / "config.yaml"
    if config_file.exists():
        config_file.unlink()
    _assert_no_critical_a11y(page, "/ui/setup")


def test_a11y_files_page(page: Page) -> None:
    """File browser page has zero critical a11y violations."""
    _assert_no_critical_a11y(page, "/ui/files")


def test_a11y_organize_page(page: Page) -> None:
    """Organize dashboard page has zero critical a11y violations."""
    _assert_no_critical_a11y(page, "/ui/organize")


def test_a11y_settings_page(page: Page) -> None:
    """Settings page has zero critical a11y violations."""
    _assert_no_critical_a11y(page, "/ui/settings")


def test_a11y_marketplace_page(page: Page, _marketplace_service: str) -> None:
    """Marketplace page has zero critical a11y violations (plugin table populated).

    Uses ``_marketplace_service`` (from conftest.py) to ensure the plugin table
    renders with at least one row, so axe evaluates the table markup rather than
    the empty-state message.  The fixture argument is not used directly — its
    side effect (patching ``_service()``) is what populates the table.
    """
    _assert_no_critical_a11y(page, "/ui/marketplace")
