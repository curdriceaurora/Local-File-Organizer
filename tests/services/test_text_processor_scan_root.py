"""Tests for the SafeDir-anchored read path in TextProcessor (WP-2.1).

``TextProcessor.process_file`` gained an opt-in ``scan_root`` keyword: when the
caller supplies the trusted directory it walked to discover the file, content is
read through ``read_file_via_safedir_anchored`` so a symlink swapped in after the
scan is refused rather than dereferenced (#264/#286). ``scan_root=None`` (the
default) keeps the legacy path-based ``read_file``.

Marked ``ci`` so the new read-path branch coverage counts toward the
diff-coverage gate.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core import dispatcher
from file_organizer.models.base import ModelType
from file_organizer.services.text_processor import ProcessedFile, TextProcessor
from file_organizer.utils.safedir import SymlinkRejected

pytestmark = [pytest.mark.unit, pytest.mark.ci]

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")


@pytest.fixture
def mock_text_model() -> MagicMock:
    model = MagicMock()
    model.config.model_type = ModelType.TEXT
    model.is_initialized = True
    model.generate.return_value = "Mocked AI Response"
    return model


@pytest.fixture
def text_processor(mock_text_model: MagicMock) -> TextProcessor:
    with patch("file_organizer.services.text_processor.ensure_nltk_data"):
        return TextProcessor(text_model=mock_text_model)


class TestReadContentRouting:
    """``_read_content`` chooses the legacy vs SafeDir-anchored reader."""

    def test_no_scan_root_uses_legacy_reader(self) -> None:
        with (
            patch("file_organizer.services.text_processor.read_file") as legacy,
            patch(
                "file_organizer.services.text_processor.read_file_via_safedir_anchored"
            ) as anchored,
        ):
            legacy.return_value = "content"
            out = TextProcessor._read_content(Path("/x/doc.txt"), None)
        assert out == "content"
        legacy.assert_called_once_with(Path("/x/doc.txt"))
        anchored.assert_not_called()

    @posix_only
    def test_scan_root_uses_anchored_reader(self) -> None:
        with (
            patch("file_organizer.services.text_processor.read_file") as legacy,
            patch(
                "file_organizer.services.text_processor.read_file_via_safedir_anchored"
            ) as anchored,
        ):
            anchored.return_value = "safe content"
            out = TextProcessor._read_content(Path("/root/sub/doc.txt"), Path("/root"))
        assert out == "safe content"
        anchored.assert_called_once_with(Path("/root/sub/doc.txt"), trusted_root=Path("/root"))
        legacy.assert_not_called()

    @posix_only
    def test_not_implemented_falls_back_to_legacy(self) -> None:
        with (
            patch("file_organizer.services.text_processor.read_file") as legacy,
            patch(
                "file_organizer.services.text_processor.read_file_via_safedir_anchored",
                side_effect=NotImplementedError,
            ),
        ):
            legacy.return_value = "fallback"
            out = TextProcessor._read_content(Path("/root/doc.txt"), Path("/root"))
        assert out == "fallback"
        legacy.assert_called_once_with(Path("/root/doc.txt"))


class TestReadContentRealFilesystem:
    """End-to-end through real syscalls (POSIX)."""

    @posix_only
    def test_reads_real_file_under_scan_root(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        target = tmp_path / "sub" / "notes.txt"
        target.write_text("hello safedir")
        assert TextProcessor._read_content(target, tmp_path) == "hello safedir"

    @posix_only
    def test_symlinked_leaf_is_refused(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("attacker secret")
        inside = tmp_path / "inside"
        inside.mkdir()
        try:
            (inside / "doc.txt").symlink_to(outside / "secret.txt")
        except OSError:
            pytest.skip("symlink creation not supported")
        with pytest.raises(SymlinkRejected):
            TextProcessor._read_content(inside / "doc.txt", inside)


class TestProcessFileScanRoot:
    """``process_file(scan_root=...)`` wires the hardened read end-to-end."""

    @posix_only
    def test_process_file_reads_via_scan_root(
        self, tmp_path: Path, text_processor: TextProcessor, mock_text_model: MagicMock
    ) -> None:
        target = tmp_path / "report.txt"
        target.write_text("quarterly revenue figures")
        mock_text_model.generate.side_effect = ["desc", "finance", "report_q1"]

        result = text_processor.process_file(target, scan_root=tmp_path)

        assert isinstance(result, ProcessedFile)
        assert result.error is None
        assert "quarterly revenue" in result.original_content

    @posix_only
    def test_process_file_refused_symlink_is_errored(
        self, tmp_path: Path, text_processor: TextProcessor
    ) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("attacker secret")
        inside = tmp_path / "inside"
        inside.mkdir()
        try:
            (inside / "doc.txt").symlink_to(outside / "secret.txt")
        except OSError:
            pytest.skip("symlink creation not supported")

        result = text_processor.process_file(inside / "doc.txt", scan_root=inside)

        # SymlinkRejected (OSError subclass) → error result, file not organized.
        assert result.error is not None
        assert "attacker secret" not in (result.original_content or "")


class TestDispatcherForwardsScanRoot:
    def test_process_text_files_forwards_scan_root(self) -> None:
        processor = MagicMock()
        processor.process_file.return_value = ProcessedFile(
            file_path=Path("a.txt"), description="", folder_name="docs", filename="a"
        )
        parallel = MagicMock()
        # Run the per-item callable inline so we can assert the forwarded kwarg.
        parallel.process_batch_iter.side_effect = lambda files, fn: [
            MagicMock(success=True, result=fn(p), error=None, path=p) for p in files
        ]
        console = MagicMock()

        dispatcher.process_text_files(
            [Path("a.txt")], processor, parallel, console, scan_root=Path("/root")
        )

        processor.process_file.assert_called_once_with(Path("a.txt"), scan_root=Path("/root"))
