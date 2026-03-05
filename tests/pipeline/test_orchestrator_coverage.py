"""Coverage tests for pipeline.orchestrator module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.pipeline.config import PipelineConfig
from file_organizer.pipeline.orchestrator import (
    PipelineOrchestrator,
    PipelineStats,
    ProcessingResult,
)
from file_organizer.pipeline.router import ProcessorType

pytestmark = pytest.mark.unit


class TestProcessingResult:
    def test_defaults(self):
        r = ProcessingResult(file_path=Path("test.txt"), success=True)
        assert r.dry_run is True
        assert r.processor_type == ProcessorType.UNKNOWN
        assert r.error is None


class TestPipelineStats:
    def test_defaults(self):
        s = PipelineStats()
        assert s.total_processed == 0
        assert s.successful == 0
        assert s.failed == 0


class TestPipelineOrchestratorInit:
    def test_default_config(self):
        pipeline = PipelineOrchestrator()
        assert pipeline.config is not None
        assert pipeline.is_running is False

    def test_custom_config(self, tmp_path):
        config = PipelineConfig(output_directory=tmp_path)
        pipeline = PipelineOrchestrator(config)
        assert pipeline.config.output_directory == tmp_path


class TestPipelineOrchestratorStartStop:
    def test_start_sets_running(self):
        pipeline = PipelineOrchestrator()
        pipeline.start()
        assert pipeline.is_running is True
        pipeline.stop()

    def test_double_start_raises(self):
        pipeline = PipelineOrchestrator()
        pipeline.start()
        with pytest.raises(RuntimeError, match="already running"):
            pipeline.start()
        pipeline.stop()

    def test_stop_when_not_running(self):
        pipeline = PipelineOrchestrator()
        pipeline.stop()  # Should not raise

    def test_stop_cleans_up(self):
        pipeline = PipelineOrchestrator()
        pipeline.start()
        pipeline.stop()
        assert pipeline.is_running is False


class TestPipelineOrchestratorProcessFile:
    def test_nonexistent_file(self, tmp_path):
        pipeline = PipelineOrchestrator()
        result = pipeline.process_file(tmp_path / "missing.txt")
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_directory_not_file(self, tmp_path):
        pipeline = PipelineOrchestrator()
        result = pipeline.process_file(tmp_path)
        assert result.success is False
        assert "Not a file" in result.error

    def test_unsupported_extension(self, tmp_path):
        f = tmp_path / "test.xyz123"
        f.write_text("data")
        config = PipelineConfig(supported_extensions={".pdf"})
        pipeline = PipelineOrchestrator(config)
        result = pipeline.process_file(f)
        assert result.success is False
        assert "Unsupported" in result.error
        assert pipeline.stats.skipped == 1

    def test_unknown_processor_type(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        config = PipelineConfig(supported_extensions={".txt"})
        pipeline = PipelineOrchestrator(config)

        with patch.object(pipeline.router, "route", return_value=ProcessorType.UNKNOWN):
            result = pipeline.process_file(f)
        assert result.success is False
        assert "No processor" in result.error

    def test_processor_not_available(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        config = PipelineConfig(supported_extensions={".txt"})
        pipeline = PipelineOrchestrator(config)

        with patch.object(pipeline.router, "route", return_value=ProcessorType.TEXT):
            with patch.object(pipeline.processor_pool, "get_processor", return_value=None):
                result = pipeline.process_file(f)
        assert result.success is False
        assert "Failed to initialize" in result.error
        assert pipeline.stats.failed == 1

    def test_successful_processing(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        output_dir = tmp_path / "output"
        config = PipelineConfig(
            output_directory=output_dir,
            supported_extensions={".txt"},
            dry_run=True,
        )
        pipeline = PipelineOrchestrator(config)

        mock_processor = MagicMock()
        mock_result = MagicMock()
        mock_result.folder_name = "documents"
        mock_result.filename = "renamed"
        mock_result.error = None
        mock_processor.process_file.return_value = mock_result

        with patch.object(pipeline.router, "route", return_value=ProcessorType.TEXT):
            with patch.object(
                pipeline.processor_pool, "get_processor", return_value=mock_processor
            ):
                result = pipeline.process_file(f)

        assert result.success is True
        assert result.category == "documents"
        assert pipeline.stats.successful == 1

    def test_processing_with_notification_callback(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        callback = MagicMock()
        config = PipelineConfig(
            supported_extensions={".txt"},
            dry_run=True,
            notification_callback=callback,
        )
        pipeline = PipelineOrchestrator(config)

        mock_processor = MagicMock()
        mock_result = MagicMock()
        mock_result.folder_name = "docs"
        mock_result.filename = "test"
        mock_result.error = None
        mock_processor.process_file.return_value = mock_result

        with patch.object(pipeline.router, "route", return_value=ProcessorType.TEXT):
            with patch.object(
                pipeline.processor_pool, "get_processor", return_value=mock_processor
            ):
                pipeline.process_file(f)

        callback.assert_called_once_with(f, True)

    def test_processing_failure_notification(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        callback = MagicMock()
        config = PipelineConfig(
            supported_extensions={".txt"},
            dry_run=True,
            notification_callback=callback,
        )
        pipeline = PipelineOrchestrator(config)

        mock_processor = MagicMock()
        mock_processor.process_file.side_effect = RuntimeError("fail")

        with patch.object(pipeline.router, "route", return_value=ProcessorType.TEXT):
            with patch.object(
                pipeline.processor_pool, "get_processor", return_value=mock_processor
            ):
                result = pipeline.process_file(f)

        assert result.success is False
        callback.assert_called_once_with(f, False)
        assert pipeline.stats.failed == 1

    def test_notification_callback_error_swallowed(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        callback = MagicMock(side_effect=RuntimeError("callback fail"))
        config = PipelineConfig(
            supported_extensions={".txt"},
            dry_run=True,
            notification_callback=callback,
        )
        pipeline = PipelineOrchestrator(config)

        mock_processor = MagicMock()
        mock_result = MagicMock()
        mock_result.folder_name = "docs"
        mock_result.filename = "test"
        mock_result.error = None
        mock_processor.process_file.return_value = mock_result

        with patch.object(pipeline.router, "route", return_value=ProcessorType.TEXT):
            with patch.object(
                pipeline.processor_pool, "get_processor", return_value=mock_processor
            ):
                result = pipeline.process_file(f)

        assert result.success is True

    def test_processor_error_attribute(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        config = PipelineConfig(supported_extensions={".txt"}, dry_run=True)
        pipeline = PipelineOrchestrator(config)

        mock_processor = MagicMock()
        mock_result = MagicMock()
        mock_result.folder_name = "docs"
        mock_result.filename = "test"
        mock_result.error = "processor error msg"
        mock_processor.process_file.return_value = mock_result

        with patch.object(pipeline.router, "route", return_value=ProcessorType.TEXT):
            with patch.object(
                pipeline.processor_pool, "get_processor", return_value=mock_processor
            ):
                result = pipeline.process_file(f)

        assert result.success is False
        assert "processor error msg" in result.error


class TestPipelineOrchestratorProcessBatch:
    def test_process_batch(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("data")
        f2 = tmp_path / "b.txt"
        f2.write_text("data")

        pipeline = PipelineOrchestrator()
        results = pipeline.process_batch([f1, f2])
        assert len(results) == 2


class TestPipelineOrchestratorOrganize:
    def test_organize_file_creates_dirs(self, tmp_path):
        src = tmp_path / "source.txt"
        src.write_text("content")
        dest = tmp_path / "out" / "cat" / "source.txt"

        pipeline = PipelineOrchestrator()
        pipeline._organize_file(src, dest)

        assert dest.exists()
        assert dest.read_text() == "content"

    def test_organize_file_handles_duplicates(self, tmp_path):
        src = tmp_path / "source.txt"
        src.write_text("content")
        dest_dir = tmp_path / "out"
        dest_dir.mkdir()
        dest = dest_dir / "source.txt"
        dest.write_text("existing")

        pipeline = PipelineOrchestrator()
        pipeline._organize_file(src, dest)

        renamed = dest_dir / "source_1.txt"
        assert renamed.exists()
