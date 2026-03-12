"""Contract checks for prefetch-related public surfaces.

These tests intentionally cover the public contract from multiple angles:
- Typer-rendered CLI help for ``file-organizer organize``
- Runtime docstrings on ``FileOrganizer`` and ``PipelineOrchestrator``
- User/admin/architecture docs that describe prefetch behavior
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

FO_ROOT = Path(__file__).resolve().parents[2]
CLI_REFERENCE_DOC = FO_ROOT / "docs" / "cli-reference.md"
PERFORMANCE_TUNING_DOC = FO_ROOT / "docs" / "admin" / "performance-tuning.md"
ARCHITECTURE_OVERVIEW_DOC = FO_ROOT / "docs" / "architecture" / "architecture-overview.md"

pytestmark = pytest.mark.ci

_RUNNER = CliRunner()
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _rendered_text(text: str) -> str:
    """Remove terminal styling so contract checks assert on CLI semantics."""
    return _ANSI_ESCAPE.sub("", text)


def test_no_prefetch_contract_matches_cli_runtime_and_docs() -> None:
    """Covered surfaces: CLI help, FileOrganizer runtime docs, CLI/admin docs."""
    from file_organizer.core.organizer import FileOrganizer

    result = _RUNNER.invoke(app, ["organize", "--help"], terminal_width=120)
    rendered_help = _rendered_text(result.output)
    cli_help = _normalized(rendered_help)
    organizer_init_doc = _normalized(inspect.getdoc(FileOrganizer.__init__) or "")
    organizer_init_source = inspect.getsource(FileOrganizer.__init__)
    cli_reference = CLI_REFERENCE_DOC.read_text(encoding="utf-8")
    performance_doc = PERFORMANCE_TUNING_DOC.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "--no-prefetch" in rendered_help
    assert "Currently has no effect for this command" in cli_help
    assert "ParallelProcessor, not PipelineOrchestrator" in cli_help
    assert "Has no effect on the legacy processor path." in organizer_init_doc
    assert "no_prefetch=True has no effect" in organizer_init_source
    assert "Currently has no effect for `file-organizer organize`" in cli_reference
    assert "only emits a warning" in cli_reference
    assert "`--no-prefetch` on the `file-organizer organize` CLI is currently a no-op" in (
        performance_doc
    )
    assert "set `prefetch_depth=0`" in performance_doc


def test_prefetch_depth_contract_matches_runtime_and_docs() -> None:
    """Covered surfaces: PipelineOrchestrator docstrings and admin tuning docs."""
    from file_organizer.pipeline.orchestrator import PipelineOrchestrator

    init_doc = _normalized(inspect.getdoc(PipelineOrchestrator.__init__) or "")
    batch_doc = _normalized(inspect.getdoc(PipelineOrchestrator.process_batch) or "")
    performance_doc = PERFORMANCE_TUNING_DOC.read_text(encoding="utf-8")
    normalized_performance_doc = _normalized(performance_doc)

    assert "Set to 0 to disable prefetch (sequential fallback)." in init_doc
    assert "Defaults to 2." in init_doc
    assert "prefetch_depth > 0" in batch_doc
    assert "`prefetch_depth`" in normalized_performance_doc
    assert "Files to pre-process ahead of current file." in normalized_performance_doc
    assert "`0` disables prefetch." in normalized_performance_doc
    assert "Set `prefetch_depth=0` to disable overlap and process files sequentially" in (
        performance_doc
    )


def test_prefetch_stages_contract_matches_runtime_and_docs() -> None:
    """Covered surfaces: PipelineOrchestrator docs plus admin/architecture docs."""
    from file_organizer.pipeline.orchestrator import PipelineOrchestrator

    init_doc = _normalized(inspect.getdoc(PipelineOrchestrator.__init__) or "")
    batch_doc = _normalized(inspect.getdoc(PipelineOrchestrator.process_batch) or "")
    performance_doc = PERFORMANCE_TUNING_DOC.read_text(encoding="utf-8")
    architecture_doc = ARCHITECTURE_OVERVIEW_DOC.read_text(encoding="utf-8")

    assert "caps the effective prefetched stage count at 1" in init_doc
    assert "Values greater than 1 currently log a warning and are treated as 1." in init_doc
    assert (
        "Values of ``prefetch_stages`` greater than 1 currently log a warning and are effectively capped to 1"
        in batch_doc
    )
    assert "only supports the first stage" in performance_doc
    assert "Keep `prefetch_stages=1`" in performance_doc
    assert "default prefetch_stages=1" in architecture_doc
    assert "AnalyzerStage" in architecture_doc
    assert "runs on calling thread by default" in architecture_doc
