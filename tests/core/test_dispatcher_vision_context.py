"""Tests for context_root forwarding through dispatcher and organizer."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from file_organizer.core import dispatcher
from file_organizer.core.organizer import FileOrganizer
from file_organizer.services.vision_processor import ProcessedImage

pytestmark = pytest.mark.unit


def test_dispatcher_process_image_files_threads_context_root(tmp_path: Path) -> None:
    vision_proc = MagicMock()
    vision_proc.process_file.return_value = ProcessedImage(
        file_path=tmp_path / "img.jpg",
        description="desc",
        folder_name="folder",
        filename="img",
    )
    parallel_proc = MagicMock()

    # Mock parallel processing to call the worker directly
    def mock_process_batch_iter(files: list[Path], worker_fn: Any) -> Any:
        for f in files:
            res = MagicMock()
            res.success = True
            res.result = worker_fn(f)
            yield res

    parallel_proc.process_batch_iter.side_effect = mock_process_batch_iter

    context_root = tmp_path / "scan_input"
    files = [context_root / "a.jpg", context_root / "b.jpg"]

    results = dispatcher.process_image_files(
        files,
        vision_proc,
        parallel_proc,
        Console(quiet=True),
        context_root=context_root,
    )

    assert len(results) == 2
    for call in vision_proc.process_file.call_args_list:
        assert call.kwargs["context_root"] == context_root


@patch("file_organizer.core.organizer.dispatcher.process_image_files")
def test_organizer_process_image_files_forwards_context_root(
    mock_dispatcher_process: MagicMock, tmp_path: Path
) -> None:
    organizer = FileOrganizer()
    organizer.vision_processor = MagicMock()

    context_root = tmp_path / "custom_root"
    files = [context_root / "1.jpg"]

    organizer._process_image_files(files, context_root=context_root)

    mock_dispatcher_process.assert_called_once()
    assert mock_dispatcher_process.call_args.kwargs["context_root"] == context_root
