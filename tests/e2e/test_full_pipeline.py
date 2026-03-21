"""E2E tests for the full FileOrganizer pipeline against a complex nested folder tree.

Tests exercise ``FileOrganizer.organize()`` against the ~60-file tree produced by
the ``complex_file_tree`` session fixture.  All AI model calls are mocked via the
``mock_text_processor`` and ``mock_vision_processor`` fixtures from conftest.py.

Audio and video files are routed through metadata-only pipelines inside the
organizer (no AI model), so no additional mocking is needed for them.

Note on accounting semantics
-----------------------------
``result.processed_files`` counts files that completed the AI-processing pipeline,
not files that were successfully copied to the output directory.  ``result.skipped_files``
counts unsupported file types only (not skip_existing skips).
``result.organized_structure`` is a ``{folder_name: [filename, ...]}`` dict that is
**only populated for files that were newly copied** — it remains empty on a second run
when ``skip_existing=True``.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

try:
    import pytest_benchmark  # noqa: F401

    HAS_PYTEST_BENCHMARK = True
except ImportError:
    HAS_PYTEST_BENCHMARK = False

from file_organizer.core.organizer import FileOrganizer, OrganizationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_MIN_FILES = 55


def _count_tree(root: Path) -> int:
    """Count all non-hidden files under *root*."""
    return sum(1 for p in root.rglob("*") if p.is_file() and not p.name.startswith("."))


# ---------------------------------------------------------------------------
# TestComplexTreeOrganization
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestComplexTreeOrganization:
    """Full-pipeline tests against the complex ~60-file nested folder tree."""

    # ------------------------------------------------------------------
    # Core result tests
    # ------------------------------------------------------------------

    def test_discover_all_files(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """Organizer should discover at least 55 files from the complex tree."""
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        result = organizer.organize(complex_file_tree, tmp_path / "out", skip_existing=False)
        assert result.total_files >= _EXPECTED_MIN_FILES, (
            f"Expected >= {_EXPECTED_MIN_FILES} files, got {result.total_files}"
        )

    def test_no_file_loss(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """processed + skipped + failed must equal total_files (no silent losses).

        Note: ``processed_files`` counts AI-pipeline completions, not copy successes.
        This assertion validates the organizer's internal accounting is consistent —
        every discovered file ends up in exactly one bucket.
        """
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        result = organizer.organize(complex_file_tree, tmp_path / "out", skip_existing=False)
        accounted = (
            result.processed_files
            + result.skipped_files
            + result.failed_files
            + result.deduplicated_files
        )
        assert accounted == result.total_files, (
            f"File loss detected: total={result.total_files}, "
            f"processed={result.processed_files}, skipped={result.skipped_files}, "
            f"failed={result.failed_files}, deduplicated={result.deduplicated_files}"
        )

    def test_result_contains_processing_time(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """processing_time must be a positive float."""
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        result = organizer.organize(complex_file_tree, tmp_path / "out", skip_existing=False)
        assert isinstance(result.processing_time, float)
        assert result.processing_time > 0

    def test_output_structure_is_dict(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """organized_structure must be a non-empty dict after a live run."""
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        result = organizer.organize(complex_file_tree, tmp_path / "out", skip_existing=False)
        assert isinstance(result.organized_structure, dict)
        assert len(result.organized_structure) > 0

    # ------------------------------------------------------------------
    # Source preservation tests
    # ------------------------------------------------------------------

    def test_dry_run_preserves_source(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """dry_run=True must leave the source tree 100% intact.

        ``complex_file_tree`` is session-scoped (read-only by convention).
        Live-run tests write to separate ``tmp_path`` output directories and
        never touch the source tree.
        """
        source_file_count = _count_tree(complex_file_tree)
        organizer = FileOrganizer(dry_run=True, use_hardlinks=False)
        organizer.organize(complex_file_tree, tmp_path / "dry_out")
        assert _count_tree(complex_file_tree) == source_file_count, (
            "dry_run=True modified or removed source files"
        )

    # ------------------------------------------------------------------
    # Output structure tests
    # ------------------------------------------------------------------

    def test_live_run_creates_output(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """A live run must create at least one subdirectory in the output dir."""
        out_dir = tmp_path / "out"
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        organizer.organize(complex_file_tree, out_dir, skip_existing=False)
        sub_dirs = [p for p in out_dir.iterdir() if p.is_dir()] if out_dir.exists() else []
        assert len(sub_dirs) > 0, "No subdirectories created in output dir"

    def test_text_files_processed(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """At least some files should be processed (not all failed/skipped)."""
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        result = organizer.organize(complex_file_tree, tmp_path / "out", skip_existing=False)
        assert result.processed_files > 0, (
            f"No files were processed (total={result.total_files}, failed={result.failed_files})"
        )

    def test_media_files_categorized(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """organized_structure must contain an 'images' key from VisionProcessor mock."""
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        result = organizer.organize(complex_file_tree, tmp_path / "out", skip_existing=False)
        # The mock VisionProcessor maps .jpg/.png → folder_name="images"
        assert "images" in result.organized_structure, (
            f"Expected 'images' category from VisionProcessor mock; "
            f"got keys: {list(result.organized_structure.keys())[:10]}"
        )

    def test_deeply_nested_files_found(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """Files at depth 4 (Work/Projects/2024/*.docx) must appear in organized output."""
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        result = organizer.organize(complex_file_tree, tmp_path / "out", skip_existing=False)
        # The 4-level deep paths: complex_tree/Work/Projects/2024/spec_v1.docx
        deep_files = list((complex_file_tree / "Work" / "Projects" / "2024").glob("*.docx"))
        assert len(deep_files) > 0, "Test fixture is missing Work/Projects/2024 DOCX files"
        # Collect all filenames placed in any output folder
        all_placed = {
            fname for filelist in result.organized_structure.values() for fname in filelist
        }
        for f in deep_files:
            placed_name = f.name
            assert placed_name in all_placed, (
                f"Deeply nested file '{f.name}' not found in organized output; "
                f"placed files: {sorted(all_placed)[:10]}"
            )

    # ------------------------------------------------------------------
    # Idempotency test
    # ------------------------------------------------------------------

    def test_organize_is_idempotent(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """Second run with skip_existing=True must place 0 new files in the output dir.

        The organizer always AI-processes files to determine their destination, but
        ``skip_existing=True`` skips the *copy* step for files already present.
        ``organized_structure`` is only populated for files that were newly copied,
        so it must be empty on the second run.

        Contract relied upon: ``organized_structure`` tracks copy-level placement,
        not AI-processing.  This is an implementation detail of ``_organize_files``
        where ``new_path.exists() and skip_existing`` causes the file to be
        skipped (not copied), so it is omitted from ``organized_structure``.
        """
        out_dir = tmp_path / "out"
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        # First run — establishes output
        first = organizer.organize(complex_file_tree, out_dir, skip_existing=True)
        first_file_count = _count_tree(out_dir)
        # Second run — no new files should be placed
        second = organizer.organize(complex_file_tree, out_dir, skip_existing=True)
        second_file_count = _count_tree(out_dir)
        assert second.organized_structure == {}, (
            f"Idempotency failed: second run newly placed files in "
            f"{list(second.organized_structure.keys())} "
            f"(first run placed {first.processed_files} files)"
        )
        assert second_file_count == first_file_count, (
            f"Output directory gained files on second run: {first_file_count} → {second_file_count}"
        )


# ---------------------------------------------------------------------------
# TestPipelineTiming
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.e2e
class TestPipelineTiming:
    """Timing and performance tests for the full organize pipeline."""

    def test_timing_60_files_under_threshold(
        self,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """Organizing ~60 files with mocked AI must complete within 30 seconds."""
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        result = organizer.organize(complex_file_tree, tmp_path / "out", skip_existing=False)
        assert result.processing_time < 30.0, (
            f"Pipeline too slow: {result.processing_time:.2f}s for "
            f"{result.total_files} files (threshold=30s)"
        )

    def test_collect_files_timing(
        self,
        complex_file_tree: Path,
    ) -> None:
        """_collect_files on the ~60-file tree must complete in under 1 second.

        NOTE: This test is deliberately coupled to the private ``_collect_files``
        method because there is no public API that exposes collection timing
        independently of AI processing.  If ``_collect_files`` is renamed or
        removed, this test should be updated or deleted accordingly.
        """
        organizer = FileOrganizer(dry_run=True, use_hardlinks=False)
        t0 = time.perf_counter()
        files = organizer._collect_files(complex_file_tree)
        elapsed = time.perf_counter() - t0
        assert len(files) >= _EXPECTED_MIN_FILES
        assert elapsed < 1.0, f"_collect_files too slow: {elapsed:.3f}s"

    @pytest.mark.benchmark
    @pytest.mark.skipif(not HAS_PYTEST_BENCHMARK, reason="pytest-benchmark not installed")
    def test_benchmark_organize(
        self,
        benchmark: Any,
        tmp_path: Path,
        complex_file_tree: Path,
        mock_text_processor: MagicMock,
        mock_vision_processor: MagicMock,
    ) -> None:
        """Benchmark full organize() pipeline using pytest-benchmark.

        A fresh UUID-named output directory is created each round so that
        ``skip_existing`` never fires and every round is equivalent.  The
        ``organizer`` instance is reused deliberately (its in-memory undo history
        accumulates across rounds but does not affect timing materially).
        """
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        out_dir = tmp_path / "bench_out"

        def run_organize() -> OrganizationResult:
            # Rotate output dir each round so skip_existing never fires
            dest = out_dir / str(uuid.uuid4())
            return organizer.organize(complex_file_tree, dest)

        result = benchmark(run_organize)
        assert result.total_files >= _EXPECTED_MIN_FILES
        assert result.processed_files > 0
