"""Tests for composable pipeline stages.

Validates that each stage implements PipelineStage protocol, processes
files correctly, handles errors gracefully, and can be composed into
custom pipelines.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.interfaces.pipeline import PipelineStage, StageContext
from file_organizer.pipeline.stages.analyzer import AnalyzerStage
from file_organizer.pipeline.stages.postprocessor import PostprocessorStage
from file_organizer.pipeline.stages.preprocessor import PreprocessorStage
from file_organizer.pipeline.stages.writer import WriterStage

# ---------------------------------------------------------------------------
# StageContext
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestStageContext:
    """Test StageContext dataclass behavior."""

    def test_failed_property_false_by_default(self) -> None:
        ctx = StageContext(file_path=Path("test.txt"))
        assert ctx.failed is False

    def test_failed_property_true_when_error_set(self) -> None:
        ctx = StageContext(file_path=Path("test.txt"), error="boom")
        assert ctx.failed is True

    def test_defaults(self) -> None:
        ctx = StageContext(file_path=Path("test.txt"))
        assert ctx.metadata == {}
        assert ctx.analysis == {}
        assert ctx.destination is None
        assert ctx.category == ""
        assert ctx.filename == ""
        assert ctx.dry_run is True
        assert ctx.extra == {}

    def test_rejects_path_traversal_in_category(self) -> None:
        with pytest.raises(ValueError, match="Invalid category"):
            StageContext(file_path=Path("input/file.txt"), category="../etc")

    def test_rejects_path_traversal_in_filename(self) -> None:
        with pytest.raises(ValueError, match="Invalid filename"):
            StageContext(file_path=Path("input/file.txt"), filename="../../etc/passwd")

    def test_rejects_windows_drive_in_category(self) -> None:
        # Regression for #760: "C:" has no slash but still escapes output_dir / category
        # on Windows via PureWindowsPath.drive being non-empty.
        with pytest.raises(ValueError, match="Invalid category"):
            StageContext(file_path=Path("input/file.txt"), category="C:")

    def test_rejects_windows_drive_with_path_in_category(self) -> None:
        # Drive-qualified path without a separator also escapes containment.
        with pytest.raises(ValueError, match="Invalid category"):
            StageContext(file_path=Path("input/file.txt"), category="C:docs")

    def test_rejects_windows_drive_in_filename(self) -> None:
        with pytest.raises(ValueError, match="Invalid filename"):
            StageContext(file_path=Path("input/file.txt"), filename="C:")

    def test_rejects_windows_drive_in_filename_via_setattr(self) -> None:
        ctx = StageContext(file_path=Path("input/file.txt"))
        with pytest.raises(ValueError, match="Invalid filename"):
            ctx.filename = "C:evil"

    def test_accepts_normal_category(self) -> None:
        ctx = StageContext(file_path=Path("input/file.txt"), category="Documents")
        assert ctx.category == "Documents"

    def test_accepts_normal_filename(self) -> None:
        ctx = StageContext(file_path=Path("input/file.txt"), filename="report_2026")
        assert ctx.filename == "report_2026"


# ---------------------------------------------------------------------------
# PreprocessorStage
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestPreprocessorStage:
    """Test PreprocessorStage validation and metadata extraction."""

    def test_satisfies_protocol(self) -> None:
        assert isinstance(PreprocessorStage(), PipelineStage)

    def test_name(self) -> None:
        assert PreprocessorStage().name == "preprocessor"

    def test_extracts_metadata(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world")

        ctx = StageContext(file_path=f)
        result = PreprocessorStage().process(ctx)

        assert result.error is None
        assert result.metadata["extension"] == ".txt"
        assert result.metadata["size_bytes"] == 11
        assert result.metadata["stem"] == "hello"
        assert result.filename == "hello"

    def test_file_not_found(self) -> None:
        ctx = StageContext(file_path=Path("nonexistent/file.txt"))
        result = PreprocessorStage().process(ctx)
        assert result.failed
        assert result.error is not None
        assert "not found" in result.error.lower()

    def test_directory_rejected(self, tmp_path: Path) -> None:
        ctx = StageContext(file_path=tmp_path)
        result = PreprocessorStage().process(ctx)
        assert result.failed
        assert result.error is not None
        assert "Not a file" in result.error

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xyz"
        f.write_text("data")

        stage = PreprocessorStage(supported_extensions=frozenset({".txt"}))
        ctx = StageContext(file_path=f)
        result = stage.process(ctx)
        assert result.failed
        assert result.error is not None
        assert "Unsupported" in result.error

    def test_no_extension_filter(self, tmp_path: Path) -> None:
        """When supported_extensions is None, all extensions pass."""
        f = tmp_path / "test.xyz"
        f.write_text("data")

        ctx = StageContext(file_path=f)
        result = PreprocessorStage().process(ctx)
        assert not result.failed

    def test_skips_when_already_failed(self) -> None:
        ctx = StageContext(file_path=Path("x.txt"), error="prior error")
        result = PreprocessorStage().process(ctx)
        assert result.error == "prior error"


# ---------------------------------------------------------------------------
# AnalyzerStage
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestAnalyzerStage:
    """Test AnalyzerStage routing and processor invocation."""

    def test_satisfies_protocol(self) -> None:
        assert isinstance(AnalyzerStage(), PipelineStage)

    def test_name(self) -> None:
        assert AnalyzerStage().name == "analyzer"

    def test_skips_when_no_router(self, tmp_path: Path) -> None:
        """Without a router, analyzer is a no-op."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        ctx = StageContext(file_path=f)
        result = AnalyzerStage().process(ctx)
        assert not result.failed

    def test_skips_when_context_already_failed(self, tmp_path: Path) -> None:
        ctx = StageContext(file_path=tmp_path / "x.txt", error="prior error")
        result = AnalyzerStage().process(ctx)
        assert result.error == "prior error"

    def test_processes_file_with_router_and_pool(self, tmp_path: Path) -> None:
        """When router and pool are configured, analyzer invokes processor."""
        from file_organizer.pipeline.processor_pool import ProcessorPool
        from file_organizer.pipeline.router import FileRouter

        f = tmp_path / "doc.txt"
        f.write_text("hello")

        mock_result = MagicMock()
        mock_result.folder_name = "Documents"
        mock_result.filename = "hello_doc"
        mock_result.error = None

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = mock_result

        router = FileRouter()
        pool = MagicMock(spec=ProcessorPool)
        pool.get_processor.return_value = mock_processor

        stage = AnalyzerStage(router=router, processor_pool=pool)
        ctx = StageContext(file_path=f)
        result = stage.process(ctx)

        assert not result.failed
        assert result.category == "Documents"
        assert result.filename == "hello_doc"
        mock_processor.process_file.assert_called_once_with(f)
        pool.get_processor.assert_called_once()


# ---------------------------------------------------------------------------
# PostprocessorStage
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestPostprocessorStage:
    """Test PostprocessorStage path computation."""

    def test_satisfies_protocol(self) -> None:
        assert isinstance(PostprocessorStage(output_directory=Path("out")), PipelineStage)

    def test_name(self) -> None:
        assert PostprocessorStage(output_directory=Path("out")).name == "postprocessor"

    def test_builds_destination(self, tmp_path: Path) -> None:
        stage = PostprocessorStage(output_directory=tmp_path / "out")
        ctx = StageContext(
            file_path=Path("input/report.pdf"),
            category="Documents",
            filename="quarterly_report",
        )
        result = stage.process(ctx)

        assert result.destination == tmp_path / "out" / "Documents" / "quarterly_report.pdf"

    def test_defaults_to_uncategorized(self, tmp_path: Path) -> None:
        stage = PostprocessorStage(output_directory=tmp_path / "out")
        ctx = StageContext(file_path=Path("input/file.txt"))
        result = stage.process(ctx)

        assert "uncategorized" in str(result.destination)

    def test_deduplicates_existing_files(self, tmp_path: Path) -> None:
        out = tmp_path / "out" / "Docs"
        out.mkdir(parents=True)
        (out / "file.txt").write_text("existing")

        stage = PostprocessorStage(output_directory=tmp_path / "out")
        ctx = StageContext(
            file_path=Path("input/file.txt"),
            category="Docs",
            filename="file",
        )
        result = stage.process(ctx)
        assert result.destination == out / "file_1.txt"

    def test_skips_when_failed(self) -> None:
        stage = PostprocessorStage(output_directory=Path("out"))
        ctx = StageContext(file_path=Path("x.txt"), error="prior")
        result = stage.process(ctx)
        assert result.destination is None


# ---------------------------------------------------------------------------
# WriterStage
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestWriterStage:
    """Test WriterStage file copy operations."""

    def test_satisfies_protocol(self) -> None:
        assert isinstance(WriterStage(), PipelineStage)

    def test_name(self) -> None:
        assert WriterStage().name == "writer"

    def test_copies_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "file.txt"
        src.parent.mkdir()
        src.write_text("content")

        dest = tmp_path / "dest" / "Docs" / "file.txt"
        ctx = StageContext(
            file_path=src,
            destination=dest,
            dry_run=False,
        )
        result = WriterStage().process(ctx)
        assert not result.failed
        assert dest.exists()
        assert dest.read_text() == "content"

    def test_dry_run_no_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "file.txt"
        src.write_text("content")
        dest = tmp_path / "out" / "file.txt"

        ctx = StageContext(file_path=src, destination=dest, dry_run=True)
        result = WriterStage().process(ctx)
        assert not result.failed
        assert not dest.exists()

    def test_error_when_no_destination(self) -> None:
        ctx = StageContext(file_path=Path("x.txt"), dry_run=False)
        result = WriterStage().process(ctx)
        assert result.failed
        assert result.error is not None
        assert "destination" in result.error.lower()

    def test_skips_when_already_failed(self) -> None:
        ctx = StageContext(
            file_path=Path("x.txt"),
            destination=Path("out/x.txt"),
            error="prior",
            dry_run=False,
        )
        result = WriterStage().process(ctx)
        assert result.error == "prior"


# ---------------------------------------------------------------------------
# Composition tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestPipelineComposition:
    """Test composing stages into custom pipelines."""

    def test_preprocessor_plus_writer_skipping_analyzer(self, tmp_path: Path) -> None:
        """Custom pipeline with only preprocessor + postprocessor + writer."""
        src = tmp_path / "input" / "file.txt"
        src.parent.mkdir()
        src.write_text("hello")

        out = tmp_path / "output"
        stages: list[PipelineStage] = [
            PreprocessorStage(),
            PostprocessorStage(output_directory=out),
            WriterStage(),
        ]

        ctx = StageContext(file_path=src, dry_run=False, category="Quick")
        for stage in stages:
            ctx = stage.process(ctx)

        assert not ctx.failed
        assert ctx.destination is not None
        assert ctx.destination.exists()
        assert ctx.destination.read_text() == "hello"

    def test_custom_stage_without_orchestrator_changes(self, tmp_path: Path) -> None:
        """Adding a custom stage doesn't require orchestrator changes."""

        class UppercaseStage:
            @property
            def name(self) -> str:
                return "uppercase"

            def process(self, context: StageContext) -> StageContext:
                context.filename = context.filename.upper()
                return context

        assert isinstance(UppercaseStage(), PipelineStage)

        src = tmp_path / "report.txt"
        src.write_text("data")

        stages: list[PipelineStage] = [
            PreprocessorStage(),
            UppercaseStage(),
            PostprocessorStage(output_directory=tmp_path / "out"),
        ]

        ctx = StageContext(file_path=src, category="Docs")
        for stage in stages:
            ctx = stage.process(ctx)

        assert ctx.filename == "REPORT"
        assert "REPORT" in str(ctx.destination)

    def test_orchestrator_with_stages(self, tmp_path: Path) -> None:
        """PipelineOrchestrator delegates to stages when configured."""
        from file_organizer.pipeline.config import PipelineConfig
        from file_organizer.pipeline.orchestrator import PipelineOrchestrator

        src = tmp_path / "file.txt"
        src.write_text("hello")

        config = PipelineConfig(
            output_directory=tmp_path / "out",
            dry_run=True,
        )

        pipeline = PipelineOrchestrator(
            config,
            stages=[
                PreprocessorStage(),
                PostprocessorStage(output_directory=config.output_directory),
                WriterStage(),
            ],
        )

        result = pipeline.process_file(src)
        assert result.success
        assert result.destination is not None
        assert result.dry_run is True

    def test_error_propagation_through_stages(self) -> None:
        """Error in early stage propagates; later stages skip."""
        stages: list[PipelineStage] = [
            PreprocessorStage(),
            AnalyzerStage(),
            PostprocessorStage(output_directory=Path("out")),
            WriterStage(),
        ]

        ctx = StageContext(file_path=Path("nonexistent.txt"))
        for stage in stages:
            ctx = stage.process(ctx)

        assert ctx.failed
        assert ctx.destination is None  # postprocessor skipped
