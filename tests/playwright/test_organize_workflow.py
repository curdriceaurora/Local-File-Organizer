"""Browser E2E tests for the organize workflow.

Covers:
- Happy path: scan → preview → execute → running → completed + filesystem output
- Failure path: scan nonexistent dir → error banner, page does not 500
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    from playwright.sync_api import Page, expect
except ImportError as _exc:
    raise ImportError(
        "playwright not installed — run: pip install -e '.[dev]' && playwright install chromium"
    ) from _exc

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.playwright,
    pytest.mark.timeout(60),  # browser ops + ~1.6 s job slowdown
]


def test_organize_happy_path_runs_to_completion(
    page: Page,
    organize_file_tree: Path,
    organize_output_dir: Path,
    slow_ai_processors: None,
) -> None:
    """Scan → preview → execute; observe running frame then completion; verify output files."""
    page.goto("/ui/organize")

    # 1) Fill the scan form with the fixture-provided paths
    page.locator("#organize-input-dir").fill(str(organize_file_tree))
    page.locator("#organize-output-dir").fill(str(organize_output_dir))
    page.get_by_role("button", name="Generate plan").click()

    # 2) Wait for the plan partial to render with at least one movement
    expect(page.locator("[data-plan-id]")).to_be_visible(timeout=10000)
    expect(page.locator(".plan-movements")).to_be_visible()

    # 3) Approve and execute
    page.get_by_role("button", name="Approve and execute").click()

    # 4) Atomically assert status=="running" AND 0 < progress < 100 in one
    #    browser-side JS evaluation to avoid the TOCTOU race where the panel
    #    advances to "completed" between two separate DOM reads.
    page.wait_for_function(
        """() => {
            const panel = document.querySelector('[data-organize-job]');
            if (!panel) return false;
            const status = panel.getAttribute('data-job-status');
            const bar = panel.querySelector('[role="progressbar"]');
            const pct = parseInt(bar?.getAttribute('aria-valuenow') || '0', 10);
            return status === 'running' && pct > 0 && pct < 100;
        }""",
        timeout=5000,
    )

    # 5) Wait for completion: status=="completed", progress bar at 100%
    job_panel = page.locator("[data-organize-job]")
    progress_bar = page.locator("[data-organize-job] [role='progressbar']")
    expect(job_panel).to_have_attribute("data-job-status", "completed", timeout=10000)
    expect(progress_bar).to_have_attribute("aria-valuenow", "100")

    # 6) Verify execute actually wrote files — catches a no-op execute that
    #    only updates job status without performing file operations.
    output_files = [p for p in organize_output_dir.rglob("*") if p.is_file()]
    assert output_files, (
        f"Happy path must write at least one file to {organize_output_dir}; output dir is empty"
    )


def test_organize_scan_with_nonexistent_path_surfaces_error(
    page: Page,
    playwright_allowed_root: Path,
    organize_output_dir: Path,
) -> None:
    """Scan a nonexistent-but-allowed path → error banner; page does not 500."""
    page.goto("/ui/organize")

    # The bogus path MUST be under playwright_allowed_root so resolve_path()
    # succeeds (it raises ValueError for paths outside allowed_paths, which the
    # scan handler catches as the generic "Failed to generate plan." rather than
    # the specific "Input directory not found." we need).
    bogus = playwright_allowed_root / "does-not-exist-xyz123"
    page.locator("#organize-input-dir").fill(str(bogus))
    page.locator("#organize-output-dir").fill(str(organize_output_dir))
    page.get_by_role("button", name="Generate plan").click()

    error_banner = page.locator("#organize-plan .banner-error")
    expect(error_banner).to_be_visible()
    expect(error_banner).to_contain_text("Input directory not found.")

    # Sanity: the page itself did not 500 — the header still renders
    expect(page.locator("h1.page-title")).to_contain_text("Organization dashboard")
