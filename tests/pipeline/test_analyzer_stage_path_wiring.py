"""Tests for path and tags wiring in AnalyzerStage and PipelineOrchestrator (#66, #64).

Marked ci so branch coverage counts toward the diff-coverage gate.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.interfaces import StageContext
from file_organizer.pipeline.config import PipelineConfig
from file_organizer.pipeline.orchestrator import PipelineOrchestrator, ProcessingResult
from file_organizer.pipeline.processor_pool import ProcessorPool
from file_organizer.pipeline.router import FileRouter, ProcessorType
from file_organizer.pipeline.stages.analyzer import AnalyzerStage

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class DummyPathAwareProcessor:
    """Processor that accepts scan_root, relative_path, and generate_tags."""

    def __init__(self) -> None:
        self.received_relative_path: str | None = None
        self.received_scan_root: str | None = None

    def process_file(
        self,
        file_path: Path,
        scan_root: Path | None = None,
        relative_path: Path | str | None = None,
        generate_tags: bool = False,
    ) -> dict[str, object]:
        self.received_relative_path = str(relative_path)
        self.received_scan_root = str(scan_root)
        tags = ["automated", "test"] if generate_tags else []
        return {
            "category": "documents",
            "filename": file_path.stem,
            "tags": tags,
        }


class DummyLegacyProcessor:
    """Processor with old signature accepting only file_path."""

    def process_file(self, file_path: Path) -> dict[str, object]:
        return {
            "category": "misc",
            "filename": file_path.stem,
        }


class TestAnalyzerStageWiring:
    """Test parameter inspection and forwarding in AnalyzerStage."""

    def test_passes_relative_path_anchored_at_scan_root(self, tmp_path: Path) -> None:
        scan_root = tmp_path / "incoming"
        file_path = scan_root / "nested" / "project" / "doc.txt"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("dummy")

        proc = DummyPathAwareProcessor()
        pool = MagicMock(spec=ProcessorPool)
        pool.get_processor.return_value = proc

        router = MagicMock(spec=FileRouter)
        router.route.return_value = ProcessorType.TEXT

        stage = AnalyzerStage(router=router, processor_pool=pool, generate_tags=True)
        ctx = StageContext(file_path=file_path, trusted_root=scan_root)

        res_ctx = stage.process(ctx)

        assert not res_ctx.failed
        assert res_ctx.category == "documents"
        assert res_ctx.extra.get("tags") == ["automated", "test"]
        assert res_ctx.analysis.get("tags") == ["automated", "test"]

    def test_falls_back_to_filename_when_trusted_root_is_none(self, tmp_path: Path) -> None:
        file_path = tmp_path / "standalone.txt"
        file_path.write_text("standalone")

        proc = DummyPathAwareProcessor()
        pool = MagicMock(spec=ProcessorPool)
        pool.get_processor.return_value = proc

        router = MagicMock(spec=FileRouter)
        router.route.return_value = ProcessorType.TEXT

        stage = AnalyzerStage(router=router, processor_pool=pool, generate_tags=False)
        ctx = StageContext(file_path=file_path, trusted_root=None)

        res_ctx = stage.process(ctx)

        assert not res_ctx.failed
        assert res_ctx.extra.get("tags", []) == []

    def test_compatible_with_legacy_processor_signature(self, tmp_path: Path) -> None:
        file_path = tmp_path / "legacy.txt"
        file_path.write_text("legacy")

        proc = DummyLegacyProcessor()
        pool = MagicMock(spec=ProcessorPool)
        pool.get_processor.return_value = proc

        router = MagicMock(spec=FileRouter)
        router.route.return_value = ProcessorType.TEXT

        stage = AnalyzerStage(router=router, processor_pool=pool)
        ctx = StageContext(file_path=file_path, trusted_root=tmp_path)

        res_ctx = stage.process(ctx)

        assert not res_ctx.failed
        assert res_ctx.category == "misc"

    def test_relative_path_fallback_when_path_outside_scan_root(self, tmp_path: Path) -> None:
        file_path = tmp_path / "outside.txt"
        file_path.write_text("outside")
        other_root = tmp_path / "somewhere_else"

        proc = DummyPathAwareProcessor()
        pool = MagicMock(spec=ProcessorPool)
        pool.get_processor.return_value = proc

        router = MagicMock(spec=FileRouter)
        router.route.return_value = ProcessorType.TEXT

        stage = AnalyzerStage(router=router, processor_pool=pool)
        ctx = StageContext(file_path=file_path, trusted_root=other_root)

        res_ctx = stage.process(ctx)
        assert not res_ctx.failed
        assert proc.received_relative_path == "outside.txt"

    def test_processor_accepts_scan_root_helper(self) -> None:
        assert AnalyzerStage._processor_accepts_scan_root(DummyPathAwareProcessor) is True
        assert AnalyzerStage._processor_accepts_scan_root(DummyLegacyProcessor) is False


class TestOrchestratorTagPropagation:
    """Test that PipelineOrchestrator respects generate_tags and surfaces tags in ProcessingResult."""

    def test_orchestrator_make_context_sets_generate_tags_flag(self, tmp_path: Path) -> None:
        config = PipelineConfig(
            output_directory=tmp_path / "out",
            generate_tags=True,
        )
        orchestrator = PipelineOrchestrator(config)
        ctx = orchestrator._make_context(tmp_path / "test.txt")

        assert ctx.extra.get("generate_tags") is True

    def test_orchestrator_populates_processing_result_tags(self, tmp_path: Path) -> None:
        import time

        config = PipelineConfig(
            output_directory=tmp_path / "out",
            generate_tags=True,
        )
        orchestrator = PipelineOrchestrator(config)
        ctx = StageContext(file_path=tmp_path / "report.pdf")
        ctx.category = "finance"
        ctx.analysis = {"tags": ["finance", "q1", "audit"]}

        result = orchestrator._finalize_result(ctx, time.monotonic() - 0.042)

        assert isinstance(result, ProcessingResult)
        assert result.tags == ("finance", "q1", "audit")
