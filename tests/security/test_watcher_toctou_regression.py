"""Security regression tests for watcher TOCTOU and symlink swap protection.

Verifies that the orchestrator and PreprocessorStage reject files swapped
to symlinks during event processing when a trusted root is provided.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from file_organizer.pipeline.config import PipelineConfig
from file_organizer.pipeline.orchestrator import PipelineOrchestrator
from file_organizer.pipeline.stages.preprocessor import PreprocessorStage

pytestmark = [pytest.mark.unit, pytest.mark.integration, pytest.mark.ci]

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink hardening is POSIX-focused"
)


@posix_only
def test_watcher_toctou_symlink_swap_rejection(tmp_path: Path) -> None:
    """Verify that if a file is swapped to a symlink between detection and read,
    the pipeline (specifically PreprocessorStage) rejects it when trusted_root is set.
    """
    # 1. Setup watched root and a secret file outside the root
    root = tmp_path / "watched"
    root.mkdir()

    secret = tmp_path / "secret.txt"
    secret.write_text("sensitive attacker-controlled data")

    # 2. Create a target path that is originally a regular file (passes detection)
    target = root / "swapped.txt"
    target.write_text("original content")

    # 3. Swap it to a symlink pointing to the secret file (simulating the TOCTOU swap)
    target.unlink()
    target.symlink_to(secret)

    # 4. Initialize the orchestrator with just the PreprocessorStage
    config = PipelineConfig(dry_run=True, auto_organize=False)

    preprocessor = PreprocessorStage()
    orchestrator = PipelineOrchestrator(config=config, stages=[preprocessor])

    # 5. Process the file, supplying the watched root as the trusted root
    result = orchestrator.process_file(target, trusted_root=root)

    # 6. Verify that processing failed and rejected the symlink
    assert not result.success
    assert "Refused to read symlinked file" in result.error
