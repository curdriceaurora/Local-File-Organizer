"""Integration tests for Gap P3: Error Propagation.

Verifies that errors from file I/O, model failures, and permission issues
propagate correctly through the service stack without crashing the batch.

All tests use real service instances; only the Ollama/OpenAI HTTP clients
are stubbed at the ``model._do_generate()`` level.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.services.text_processor import TextProcessor

from .conftest import make_text_config, make_vision_config, patch_text_generate_error

pytestmark = [pytest.mark.integration]


class TestFileReadErrors:
    """File read errors surface in ProcessedFile results, not exceptions."""

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod does not restrict reads on Windows")
    def test_unreadable_file_returns_error_in_result(
        self,
        stub_text_model_init: None,
        stub_text_model_generate: MagicMock,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        """A file that can't be read returns ProcessedFile with error set."""
        bad_file = tmp_path / "secret.txt"
        bad_file.write_text("classified content")

        text_cfg = make_text_config()
        processor = TextProcessor(config=text_cfg)
        processor.initialize()

        try:
            # Make unreadable inside try so finally always restores
            bad_file.chmod(0o000)
            result = processor.process_file(bad_file)
            assert result.error is not None
            assert result.folder_name == "errors"
        finally:
            bad_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_nonexistent_file_returns_error(
        self,
        stub_text_model_init: None,
        stub_text_model_generate: MagicMock,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        """Processing a missing file returns error, does not raise."""
        text_cfg = make_text_config()
        processor = TextProcessor(config=text_cfg)
        processor.initialize()

        result = processor.process_file(tmp_path / "ghost.txt")

        assert result.error is not None


class TestModelErrors:
    """Model failures are captured per-file, not propagated as exceptions."""

    def test_model_exception_uses_fallback_values(
        self,
        stub_text_model_init: None,
        stub_nltk: None,
        integration_source_dir: Path,
    ) -> None:
        """When model.generate() raises, TextProcessor uses fallback values.

        The _generate_* methods catch exceptions internally and return
        hardcoded defaults (``"documents"``, ``"document"``).  The file is
        still processed — graceful degradation, not failure.
        """
        text_cfg = make_text_config()
        processor = TextProcessor(config=text_cfg)
        processor.initialize()

        with patch_text_generate_error(RuntimeError("GPU out of memory")):
            result = processor.process_file(integration_source_dir / "report.txt")

        # File still processes — error is handled gracefully with fallbacks
        assert result.error is None
        assert result.folder_name == "documents"
        assert result.filename == "document"


class TestOrganizerErrorHandling:
    """FileOrganizer handles errors gracefully across the full pipeline."""

    def test_missing_input_dir_raises_valueerror(
        self,
        tmp_path: Path,
    ) -> None:
        """organize() raises ValueError with clear message for bad input path."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        with pytest.raises(ValueError, match="does not exist"):
            org.organize(
                input_path=str(tmp_path / "nonexistent"),
                output_path=str(tmp_path / "output"),
            )

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod does not restrict reads on Windows")
    def test_mixed_good_and_bad_files_in_batch(
        self,
        stub_all_models: None,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        """Batch with one bad file still processes the good files."""
        src = tmp_path / "mixed"
        src.mkdir()

        # One good file
        (src / "good.txt").write_text("This is valid content for processing.")

        # One unreadable file
        bad_file = src / "bad.txt"
        bad_file.write_text("secret")

        out = tmp_path / "output"
        out.mkdir()

        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        try:
            bad_file.chmod(0o000)
            result = org.organize(
                input_path=str(src),
                output_path=str(out),
            )

            # Batch should complete (not crash)
            assert result.total_files == 2
            # Good file processed, bad file recorded as failed
            assert result.processed_files == 1
            assert result.failed_files == 1
        finally:
            bad_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_model_timeout_degrades_gracefully(
        self,
        stub_text_model_init: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """When model times out, files use fallback values instead of failing.

        TextProcessor._generate_* methods catch exceptions and return
        hardcoded defaults, so the files are still ``processed_files``.
        """
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        with patch_text_generate_error(TimeoutError("Model timed out after 60s")):
            result = org.organize(
                input_path=str(integration_source_dir),
                output_path=str(integration_output_dir),
            )

        # All files processed with fallback values (graceful degradation)
        assert result.total_files == 3
        assert result.processed_files == 3

    def test_deep_exception_in_parallel_does_not_crash(
        self,
        stub_text_model_init: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """An unexpected exception deep in a parallel worker doesn't crash the batch."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        with patch_text_generate_error(RuntimeError("Out of memory")):
            result = org.organize(
                input_path=str(integration_source_dir),
                output_path=str(integration_output_dir),
            )

        # Batch completes — errors degrade to fallback values, not failures
        assert result.total_files == 3
        assert result.processed_files == 3
