"""Tests for PipelineOrchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.pipeline.config import PipelineConfig
from file_organizer.pipeline.orchestrator import (
    PipelineOrchestrator,
    PipelineStats,
    ProcessingResult,
)
from file_organizer.pipeline.router import ProcessorType

# --- Test fixtures and helpers ---


@dataclass
class MockProcessedFile:
    """Mock result from a processor's process_file method."""

    file_path: Path
    folder_name: str = "test_category"
    filename: str = "test_file"
    error: str | None = None


class MockProcessor:
    """Mock processor that conforms to BaseProcessor protocol."""

    def __init__(self, folder_name: str = "test_category", filename: str = "test_file") -> None:
        self._folder_name = folder_name
        self._filename = filename
        self._initialized = False
        self._cleaned_up = False
        self.process_file_calls: list[Path] = []
        self._should_raise: Exception | None = None

    def initialize(self) -> None:
        self._initialized = True

    def cleanup(self) -> None:
        self._cleaned_up = True

    def process_file(self, file_path: Path) -> MockProcessedFile:
        self.process_file_calls.append(file_path)
        if self._should_raise is not None:
            raise self._should_raise
        return MockProcessedFile(
            file_path=file_path,
            folder_name=self._folder_name,
            filename=self._filename,
        )

    def set_error(self, error: Exception) -> None:
        self._should_raise = error


class MockProcessorWithError:
    """Mock processor that returns results with error field set."""

    def __init__(self) -> None:
        self._initialized = False
        self._cleaned_up = False

    def initialize(self) -> None:
        self._initialized = True

    def cleanup(self) -> None:
        self._cleaned_up = True

    def process_file(self, file_path: Path) -> MockProcessedFile:
        return MockProcessedFile(
            file_path=file_path,
            folder_name="errors",
            filename=file_path.stem,
            error="Processing failed: corrupt file",
        )


@pytest.fixture()
def tmp_files(tmp_path: Path) -> dict[str, Path]:
    """Create temporary test files of various types."""
    files = {}
    for name, content in [
        ("document.txt", "Hello world"),
        ("report.pdf", "%PDF-1.4 fake"),
        ("photo.jpg", "fake jpg"),
        ("video.mp4", "fake mp4"),
        ("song.mp3", "fake mp3"),
        ("data.csv", "a,b,c\n1,2,3"),
        ("archive.zip", "fake zip"),
    ]:
        f = tmp_path / name
        f.write_text(content)
        files[name] = f
    return files


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    """Provide a temporary output directory."""
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.fixture()
def mock_processor() -> MockProcessor:
    """Provide a mock processor."""
    return MockProcessor()


@pytest.fixture()
def pipeline_with_mock(
    output_dir: Path,
    mock_processor: MockProcessor,
) -> PipelineOrchestrator:
    """Provide a pipeline with mock text processor registered."""
    config = PipelineConfig(output_directory=output_dir, dry_run=True)
    pipeline = PipelineOrchestrator(config)
    pipeline.processor_pool.register_factory(
        ProcessorType.TEXT,
        lambda: mock_processor,
    )
    pipeline.processor_pool.register_factory(
        ProcessorType.IMAGE,
        lambda: mock_processor,
    )
    pipeline.processor_pool.register_factory(
        ProcessorType.VIDEO,
        lambda: mock_processor,
    )
    pipeline.processor_pool.register_factory(
        ProcessorType.AUDIO,
        lambda: mock_processor,
    )
    return pipeline


# --- ProcessingResult tests ---


class TestProcessingResult:
    """Test the ProcessingResult dataclass."""

    def test_successful_result(self) -> None:
        result = ProcessingResult(
            file_path=Path("test.txt"),
            success=True,
            category="documents",
            destination=Path("/tmp/organized/documents/test.txt"),
            duration_ms=150.5,
        )
        assert result.success is True
        assert result.category == "documents"
        assert result.error is None

    def test_failed_result(self) -> None:
        result = ProcessingResult(
            file_path=Path("test.txt"),
            success=False,
            error="File not found",
        )
        assert result.success is False
        assert result.error == "File not found"

    def test_default_dry_run_is_true(self) -> None:
        result = ProcessingResult(
            file_path=Path("test.txt"),
            success=True,
        )
        assert result.dry_run is True

    def test_result_is_frozen(self) -> None:
        """ProcessingResult should be immutable."""
        result = ProcessingResult(
            file_path=Path("test.txt"),
            success=True,
        )
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


# --- PipelineStats tests ---


class TestPipelineStats:
    """Test the PipelineStats dataclass."""

    def test_default_values(self) -> None:
        stats = PipelineStats()
        assert stats.total_processed == 0
        assert stats.successful == 0
        assert stats.failed == 0
        assert stats.skipped == 0
        assert stats.total_duration_ms == 0.0


# --- PipelineOrchestrator core tests ---


class TestPipelineOrchestratorInit:
    """Test pipeline initialization."""

    def test_default_config(self) -> None:
        pipeline = PipelineOrchestrator()
        assert pipeline.config.dry_run is True
        assert pipeline.is_running is False

    def test_custom_config(self, output_dir: Path) -> None:
        config = PipelineConfig(
            output_directory=output_dir,
            dry_run=False,
            auto_organize=True,
        )
        pipeline = PipelineOrchestrator(config)
        assert pipeline.config.dry_run is False
        assert pipeline.config.auto_organize is True


class TestPipelineOrchestratorStartStop:
    """Test pipeline start/stop lifecycle."""

    def test_start_sets_running(self, output_dir: Path) -> None:
        config = PipelineConfig(output_directory=output_dir)
        pipeline = PipelineOrchestrator(config)
        pipeline.start()
        assert pipeline.is_running is True
        pipeline.stop()

    def test_stop_clears_running(self, output_dir: Path) -> None:
        config = PipelineConfig(output_directory=output_dir)
        pipeline = PipelineOrchestrator(config)
        pipeline.start()
        pipeline.stop()
        assert pipeline.is_running is False

    def test_double_start_raises(self, output_dir: Path) -> None:
        config = PipelineConfig(output_directory=output_dir)
        pipeline = PipelineOrchestrator(config)
        pipeline.start()
        with pytest.raises(RuntimeError, match="already running"):
            pipeline.start()
        pipeline.stop()

    def test_stop_when_not_running_is_safe(self, output_dir: Path) -> None:
        config = PipelineConfig(output_directory=output_dir)
        pipeline = PipelineOrchestrator(config)
        pipeline.stop()  # Should not raise


class TestPipelineProcessFile:
    """Test single file processing."""

    def test_process_text_file(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Processing a text file returns successful result."""
        result = pipeline_with_mock.process_file(tmp_files["document.txt"])
        assert result.success is True
        assert result.category == "test_category"
        assert result.destination is not None
        assert result.processor_type == ProcessorType.TEXT
        assert result.duration_ms > 0

    def test_process_image_file(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Processing an image file routes to IMAGE processor."""
        result = pipeline_with_mock.process_file(tmp_files["photo.jpg"])
        assert result.success is True
        assert result.processor_type == ProcessorType.IMAGE

    def test_process_video_file(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Processing a video file routes to VIDEO processor."""
        result = pipeline_with_mock.process_file(tmp_files["video.mp4"])
        assert result.success is True
        assert result.processor_type == ProcessorType.VIDEO

    def test_process_audio_file(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Processing an audio file routes to AUDIO processor."""
        result = pipeline_with_mock.process_file(tmp_files["song.mp3"])
        assert result.success is True
        assert result.processor_type == ProcessorType.AUDIO

    def test_process_nonexistent_file(
        self,
        pipeline_with_mock: PipelineOrchestrator,
    ) -> None:
        """Processing a non-existent file returns failure."""
        result = pipeline_with_mock.process_file(Path("/nonexistent/file.txt"))
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_process_unsupported_extension(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Files with unsupported extensions are skipped."""
        result = pipeline_with_mock.process_file(tmp_files["archive.zip"])
        assert result.success is False
        assert "unsupported" in result.error.lower()

    def test_process_directory_fails(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_path: Path,
    ) -> None:
        """Processing a directory returns failure."""
        result = pipeline_with_mock.process_file(tmp_path)
        assert result.success is False
        assert "not a file" in result.error.lower()


class TestPipelineDryRun:
    """Test dry-run behavior."""

    def test_dry_run_does_not_move_files(
        self,
        output_dir: Path,
        mock_processor: MockProcessor,
        tmp_files: dict[str, Path],
    ) -> None:
        """In dry-run mode, no files are actually moved."""
        config = PipelineConfig(
            output_directory=output_dir,
            dry_run=True,
            auto_organize=True,
        )
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, lambda: mock_processor)

        result = pipeline.process_file(tmp_files["document.txt"])
        assert result.success is True
        assert result.dry_run is True
        # Output directory should be empty (no files moved)
        organized_files = list(output_dir.rglob("*"))
        assert len(organized_files) == 0

    def test_dry_run_result_has_destination(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Dry-run results still include the planned destination."""
        result = pipeline_with_mock.process_file(tmp_files["document.txt"])
        assert result.destination is not None
        assert "test_category" in str(result.destination)

    def test_auto_organize_requires_dry_run_false(
        self,
        output_dir: Path,
        mock_processor: MockProcessor,
        tmp_files: dict[str, Path],
    ) -> None:
        """Auto-organize only works when dry_run is False."""
        config = PipelineConfig(
            output_directory=output_dir,
            dry_run=False,
            auto_organize=True,
        )
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, lambda: mock_processor)

        result = pipeline.process_file(tmp_files["document.txt"])
        assert result.success is True
        assert result.dry_run is False
        # File should actually be copied
        assert result.destination.exists()


class TestPipelineErrorHandling:
    """Test error handling in the pipeline."""

    def test_processor_exception_returns_failure(
        self,
        output_dir: Path,
        tmp_files: dict[str, Path],
    ) -> None:
        """When processor raises exception, result indicates failure."""
        failing_processor = MockProcessor()
        failing_processor.set_error(RuntimeError("Processing crashed"))

        config = PipelineConfig(output_directory=output_dir)
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, lambda: failing_processor)

        result = pipeline.process_file(tmp_files["document.txt"])
        assert result.success is False
        assert "Processing crashed" in result.error

    def test_processor_result_with_error_field(
        self,
        output_dir: Path,
        tmp_files: dict[str, Path],
    ) -> None:
        """When processor returns result with error field, pipeline reports failure."""
        config = PipelineConfig(output_directory=output_dir)
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, MockProcessorWithError)

        result = pipeline.process_file(tmp_files["document.txt"])
        assert result.success is False
        assert "corrupt file" in result.error

    def test_no_processor_registered(
        self,
        output_dir: Path,
        tmp_files: dict[str, Path],
    ) -> None:
        """When no processor is registered, returns failure."""
        config = PipelineConfig(output_directory=output_dir)
        pipeline = PipelineOrchestrator(config)
        # No processors registered

        result = pipeline.process_file(tmp_files["document.txt"])
        assert result.success is False
        assert "failed to initialize" in result.error.lower()

    def test_failed_processing_updates_stats(
        self,
        output_dir: Path,
        tmp_files: dict[str, Path],
    ) -> None:
        """Failed processing updates the failed counter in stats."""
        failing_processor = MockProcessor()
        failing_processor.set_error(RuntimeError("Fail"))

        config = PipelineConfig(output_directory=output_dir)
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, lambda: failing_processor)

        pipeline.process_file(tmp_files["document.txt"])
        assert pipeline.stats.failed == 1
        assert pipeline.stats.total_processed == 1


class TestPipelineBatchProcessing:
    """Test batch processing of multiple files."""

    def test_process_batch_returns_all_results(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Batch processing returns one result per file."""
        files = [tmp_files["document.txt"], tmp_files["report.pdf"]]
        results = pipeline_with_mock.process_batch(files)
        assert len(results) == 2

    def test_batch_processes_sequentially(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
        mock_processor: MockProcessor,
    ) -> None:
        """Files in a batch are processed in order."""
        files = [tmp_files["document.txt"], tmp_files["data.csv"]]
        pipeline_with_mock.process_batch(files)
        assert len(mock_processor.process_file_calls) == 2
        assert mock_processor.process_file_calls[0] == tmp_files["document.txt"]
        assert mock_processor.process_file_calls[1] == tmp_files["data.csv"]

    def test_batch_mixed_success_and_failure(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Batch handles a mix of successful and failed files."""
        files = [
            tmp_files["document.txt"],  # Supported
            tmp_files["archive.zip"],  # Unsupported
            tmp_files["photo.jpg"],  # Supported
        ]
        results = pipeline_with_mock.process_batch(files)
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    def test_empty_batch(
        self,
        pipeline_with_mock: PipelineOrchestrator,
    ) -> None:
        """Processing an empty batch returns an empty list."""
        results = pipeline_with_mock.process_batch([])
        assert results == []

    def test_batch_updates_stats(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Batch processing updates cumulative stats."""
        files = [tmp_files["document.txt"], tmp_files["report.pdf"]]
        pipeline_with_mock.process_batch(files)
        assert pipeline_with_mock.stats.total_processed == 2
        assert pipeline_with_mock.stats.successful == 2


class TestPipelineNotificationCallback:
    """Test notification callback integration."""

    def test_callback_called_on_success(
        self,
        output_dir: Path,
        mock_processor: MockProcessor,
        tmp_files: dict[str, Path],
    ) -> None:
        """Notification callback is invoked on successful processing."""
        callback = MagicMock()
        config = PipelineConfig(
            output_directory=output_dir,
            notification_callback=callback,
        )
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, lambda: mock_processor)

        pipeline.process_file(tmp_files["document.txt"])
        callback.assert_called_once_with(tmp_files["document.txt"], True)

    def test_callback_called_on_failure(
        self,
        output_dir: Path,
        tmp_files: dict[str, Path],
    ) -> None:
        """Notification callback is invoked on failed processing."""
        failing_processor = MockProcessor()
        failing_processor.set_error(RuntimeError("Fail"))
        callback = MagicMock()

        config = PipelineConfig(
            output_directory=output_dir,
            notification_callback=callback,
        )
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, lambda: failing_processor)

        pipeline.process_file(tmp_files["document.txt"])
        callback.assert_called_once_with(tmp_files["document.txt"], False)

    def test_callback_error_does_not_break_pipeline(
        self,
        output_dir: Path,
        mock_processor: MockProcessor,
        tmp_files: dict[str, Path],
    ) -> None:
        """Pipeline continues even if callback raises an exception."""

        def bad_callback(path: Path, success: bool) -> None:
            raise ValueError("Callback error")

        config = PipelineConfig(
            output_directory=output_dir,
            notification_callback=bad_callback,
        )
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, lambda: mock_processor)

        # Should not raise despite callback error
        result = pipeline.process_file(tmp_files["document.txt"])
        assert result.success is True


class TestPipelineFileOrganization:
    """Test actual file organization (non-dry-run)."""

    def test_file_copied_to_destination(
        self,
        output_dir: Path,
        mock_processor: MockProcessor,
        tmp_files: dict[str, Path],
    ) -> None:
        """Files are copied to the organized destination."""
        config = PipelineConfig(
            output_directory=output_dir,
            dry_run=False,
            auto_organize=True,
        )
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, lambda: mock_processor)

        result = pipeline.process_file(tmp_files["document.txt"])
        assert result.success is True
        assert result.destination.exists()
        # Verify content matches
        assert result.destination.read_text() == "Hello world"

    def test_category_directory_created(
        self,
        output_dir: Path,
        tmp_files: dict[str, Path],
    ) -> None:
        """Category subdirectory is created automatically."""
        processor = MockProcessor(folder_name="my_category")
        config = PipelineConfig(
            output_directory=output_dir,
            dry_run=False,
            auto_organize=True,
        )
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, lambda: processor)

        pipeline.process_file(tmp_files["document.txt"])
        assert (output_dir / "my_category").is_dir()

    def test_duplicate_filename_handling(
        self,
        output_dir: Path,
        tmp_files: dict[str, Path],
    ) -> None:
        """Duplicate filenames get incremented suffixes."""
        processor = MockProcessor(folder_name="docs", filename="report")
        config = PipelineConfig(
            output_directory=output_dir,
            dry_run=False,
            auto_organize=True,
        )
        pipeline = PipelineOrchestrator(config)
        pipeline.processor_pool.register_factory(ProcessorType.TEXT, lambda: processor)

        # Process two files that would get the same name
        result1 = pipeline.process_file(tmp_files["document.txt"])
        result2 = pipeline.process_file(tmp_files["data.csv"])

        assert result1.success is True
        assert result2.success is True
        # Both should exist but with different names
        assert result1.destination != result2.destination


class TestPipelineStatsAccumulation:
    """Test cumulative statistics tracking."""

    def test_stats_initialized_to_zero(self) -> None:
        pipeline = PipelineOrchestrator()
        assert pipeline.stats.total_processed == 0
        assert pipeline.stats.successful == 0
        assert pipeline.stats.failed == 0
        assert pipeline.stats.skipped == 0

    def test_stats_accumulate_across_calls(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Stats accumulate across multiple process_file calls."""
        pipeline_with_mock.process_file(tmp_files["document.txt"])
        pipeline_with_mock.process_file(tmp_files["report.pdf"])
        assert pipeline_with_mock.stats.total_processed == 2
        assert pipeline_with_mock.stats.successful == 2

    def test_skipped_files_counted(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Unsupported files increment the skipped counter."""
        pipeline_with_mock.process_file(tmp_files["archive.zip"])
        assert pipeline_with_mock.stats.skipped == 1

    def test_duration_accumulated(
        self,
        pipeline_with_mock: PipelineOrchestrator,
        tmp_files: dict[str, Path],
    ) -> None:
        """Total duration accumulates across calls."""
        pipeline_with_mock.process_file(tmp_files["document.txt"])
        pipeline_with_mock.process_file(tmp_files["report.pdf"])
        assert pipeline_with_mock.stats.total_duration_ms > 0
