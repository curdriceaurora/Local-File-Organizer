"""Integration tests for Gap P4+P5: Concurrency + Cleanup.

Verifies that ParallelProcessor, FileOrganizer, and model lifecycle
work together under concurrent load without deadlocks, leaks, or
incomplete cleanup.

All tests use real ``FileOrganizer`` and ``ParallelProcessor`` instances
with stubbed models.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.parallel.config import ParallelConfig

from .conftest import (
    make_text_config,
    make_vision_config,
    patch_text_generate,
    patch_text_generate_error,
)

pytestmark = [pytest.mark.integration]


class TestConcurrentTextProcessing:
    """Concurrent text processing with real ParallelProcessor."""

    def test_parallel_processes_multiple_files(
        self,
        stub_all_models: None,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        """ParallelProcessor handles multiple files concurrently."""
        src = tmp_path / "source"
        src.mkdir()

        # Create 10 text files
        for i in range(10):
            (src / f"file_{i}.txt").write_text(
                f"Document {i}: This is a test document about topic {i}."
            )

        out = tmp_path / "output"
        out.mkdir()

        org = FileOrganizer(
            text_model_config=make_text_config(),
            vision_model_config=make_vision_config(),
            dry_run=True,
            parallel_workers=2,
        )

        result = org.organize(input_path=str(src), output_path=str(out))

        assert result.total_files == 10
        assert result.processed_files == 10
        assert result.failed_files == 0

    def test_pool_exhaustion_many_files_few_workers(
        self,
        stub_all_models: None,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        """50 files with 2 workers completes without deadlock or resource exhaustion."""
        src = tmp_path / "source"
        src.mkdir()

        for i in range(50):
            (src / f"doc_{i:03d}.txt").write_text(f"Content for document number {i}.")

        out = tmp_path / "output"
        out.mkdir()

        org = FileOrganizer(
            text_model_config=make_text_config(),
            vision_model_config=make_vision_config(),
            dry_run=True,
            parallel_workers=2,
        )

        result = org.organize(input_path=str(src), output_path=str(out))

        assert result.total_files == 50
        assert result.processed_files == 50
        assert result.failed_files == 0


class TestTimeoutHandling:
    """Timeout cancellation works without deadlock."""

    def test_slow_model_does_not_deadlock(
        self,
        stub_text_model_init: None,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        """A model that takes too long is handled gracefully.

        Uses a real ParallelProcessor with a short timeout. The slow
        model triggers timeout handling, which must not deadlock.
        """
        src = tmp_path / "source"
        src.mkdir()
        (src / "slow.txt").write_text("This file will take forever to process.")

        out = tmp_path / "output"
        out.mkdir()

        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
            parallel_workers=1,
        )
        # Override the parallel processor config with a short timeout
        org.parallel_config = ParallelConfig(max_workers=1, timeout_per_file=0.5)

        def _slow_generate(prompt: str, **kwargs: object) -> str:
            time.sleep(1.0)  # Slightly longer than 0.5s timeout
            return "should not reach here"

        with patch_text_generate(_slow_generate):
            # This must complete within a reasonable time (not hang)
            result = org.organize(input_path=str(src), output_path=str(out))

        # The file should appear in results (processed or failed, not dropped)
        assert result.total_files == 1
        assert result.processed_files + result.failed_files == 1


class TestProcessorCleanup:
    """Processors are cleaned up properly after organize()."""

    def test_processors_cleaned_up_after_organize(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """TextProcessor.cleanup() and VisionProcessor.cleanup() are called."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        org.organize(
            input_path=str(integration_source_dir),
            output_path=str(integration_output_dir),
        )

        # After organize(), the text_processor should have been cleaned up.
        # Verify the model was cleaned up by checking client state.
        assert org.text_processor is not None
        assert org.text_processor.text_model.client is None

    def test_cleanup_after_partial_failure(
        self,
        stub_text_model_init: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """Processors are cleaned up even when some files fail."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        with patch_text_generate_error(RuntimeError("GPU crash")):
            result = org.organize(
                input_path=str(integration_source_dir),
                output_path=str(integration_output_dir),
            )

        # Verify error injection took effect (files processed with fallbacks)
        assert result.total_files == 3
        assert result.processed_files == 3

        # Even after failures, cleanup happened
        assert org.text_processor is not None
        assert org.text_processor.text_model.client is None


class TestMidOperationFailure:
    """Partial output is handled correctly when failures occur mid-batch."""

    def test_intermittent_errors_use_fallback_values(
        self,
        stub_text_model_init: None,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        """Intermittent model errors degrade to fallback values, not batch failure.

        When some generate() calls raise, the affected files get fallback
        values (``"documents"``/``"document"``). All files are still counted
        as ``processed_files`` — not ``failed_files``.
        """
        src = tmp_path / "source"
        src.mkdir()

        # Create 4 files
        for i in range(4):
            (src / f"file_{i}.txt").write_text(f"Content {i} for processing.")

        out = tmp_path / "output"
        out.mkdir()

        call_count = 0

        def _intermittent_generate(prompt: str, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            # Fail every 4th call (which hits some files, not others)
            if call_count % 4 == 0:
                raise RuntimeError("Intermittent GPU error")
            return "Deterministic response for integration test."

        org = FileOrganizer(
            text_model_config=make_text_config(),
            vision_model_config=make_vision_config(),
            dry_run=True,
        )

        with patch_text_generate(_intermittent_generate):
            result = org.organize(input_path=str(src), output_path=str(out))

        # All 4 files processed (failures use fallback values, not failed_files)
        assert result.total_files == 4
        assert result.processed_files == 4
        assert result.failed_files == 0


class TestRepeatedOrganize:
    """FileOrganizer can be called multiple times safely."""

    def test_organize_twice_no_resource_leak(
        self,
        stub_all_models: None,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        """Calling organize() twice on the same organizer works cleanly."""
        src1 = tmp_path / "source1"
        src1.mkdir()
        (src1 / "doc1.txt").write_text("First batch document.")

        src2 = tmp_path / "source2"
        src2.mkdir()
        (src2 / "doc2.txt").write_text("Second batch document.")

        out = tmp_path / "output"
        out.mkdir()

        org = FileOrganizer(
            text_model_config=make_text_config(),
            vision_model_config=make_vision_config(),
            dry_run=True,
        )

        result1 = org.organize(input_path=str(src1), output_path=str(out))
        result2 = org.organize(input_path=str(src2), output_path=str(out))

        assert result1.total_files == 1
        assert result1.processed_files == 1
        assert result2.total_files == 1
        assert result2.processed_files == 1
