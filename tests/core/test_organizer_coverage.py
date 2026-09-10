"""Coverage tests for FileOrganizer — targets uncovered branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer

pytestmark = pytest.mark.unit


@pytest.fixture()
def organizer():
    mock_text_cfg = MagicMock()
    mock_vision_cfg = MagicMock()
    with patch(
        "file_organizer.config.provider_env.get_model_configs",
        return_value=(mock_text_cfg, mock_vision_cfg),
    ):
        org = FileOrganizer(dry_run=True)
    return org


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_init(self, organizer):
        assert organizer.dry_run is True
        assert organizer._undo_manager is None

    def test_tag_defaults_are_false_and_none(self, organizer):
        """generate_tags/tag_style/tag_prompt default to off when not supplied."""
        assert organizer.generate_tags is False
        assert organizer.tag_style is None
        assert organizer.tag_prompt is None

    def test_generate_tags_kwarg_stored(self):
        """Passing generate_tags=True directly is stored on the instance."""
        with patch(
            "file_organizer.config.provider_env.get_model_configs",
            return_value=(MagicMock(), MagicMock()),
        ):
            org = FileOrganizer(dry_run=True, generate_tags=True)
        assert org.generate_tags is True
        assert org.organize_options.generate_tags is True

    def test_tag_style_and_prompt_kwarg_stored(self):
        """tag_style and tag_prompt are stored when passed alongside generate_tags."""
        with patch(
            "file_organizer.config.provider_env.get_model_configs",
            return_value=(MagicMock(), MagicMock()),
        ):
            org = FileOrganizer(
                dry_run=True,
                generate_tags=True,
                tag_style="descriptive",
                tag_prompt="focus on content",
            )
        assert org.tag_style == "descriptive"
        assert org.tag_prompt == "focus on content"
        assert org.organize_options.tag_style == "descriptive"
        assert org.organize_options.tag_prompt == "focus on content"

    def test_tag_params_extracted_from_organize_options(self):
        """When organize_options is supplied, tag fields are read from it."""
        from file_organizer.core.organize_options import OrganizeOptions
        from file_organizer.models.base import ModelConfig, ModelType

        text_cfg = ModelConfig(name="text-model", model_type=ModelType.TEXT)
        vision_cfg = ModelConfig(name="vision-model", model_type=ModelType.VISION)
        opts = OrganizeOptions(generate_tags=True, tag_style="descriptive", tag_prompt="brief")
        org = FileOrganizer(
            dry_run=True,
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            organize_options=opts,
        )
        assert org.generate_tags is True
        assert org.tag_style == "descriptive"
        assert org.tag_prompt == "brief"


# ---------------------------------------------------------------------------
# _collect_files
# ---------------------------------------------------------------------------


class TestCollectFiles:
    def test_collect_single_file(self, organizer, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        files = organizer._collect_files(f)
        assert len(files) == 1
        assert f in files

    def test_collect_directory(self, organizer, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / ".hidden").write_text("skip")
        files = organizer._collect_files(tmp_path)
        assert len(files) == 2  # hidden skipped
        assert tmp_path / "a.txt" in files
        assert tmp_path / "b.txt" in files

    def test_collect_empty(self, organizer, tmp_path):
        files = organizer._collect_files(tmp_path)
        assert len(files) == 0


# ---------------------------------------------------------------------------
# _simulate_organization
# ---------------------------------------------------------------------------


class TestSimulateOrganization:
    def test_simulates_grouping(self, organizer, tmp_path):
        mock_processed = MagicMock()
        mock_processed.error = None
        mock_processed.folder_name = "Documents"
        mock_processed.filename = "test"
        mock_processed.file_path = tmp_path / "test.txt"

        result = organizer._simulate_organization([mock_processed], tmp_path / "out")
        assert "Documents" in result
        assert "test.txt" in result["Documents"]

    def test_skips_errors(self, organizer, tmp_path):
        mock_processed = MagicMock()
        mock_processed.error = "some error"
        result = organizer._simulate_organization([mock_processed], tmp_path / "out")
        assert result == {}


# ---------------------------------------------------------------------------
# _cleanup_empty_dirs
# ---------------------------------------------------------------------------


class TestCleanupEmptyDirs:
    def test_removes_empty_subdirs(self, organizer, tmp_path):
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        organizer._cleanup_empty_dirs(tmp_path)
        assert not sub.exists()
        assert tmp_path.exists()  # root preserved

    def test_keeps_non_empty(self, organizer, tmp_path):
        sub = tmp_path / "a"
        sub.mkdir()
        (sub / "f.txt").write_text("data")
        organizer._cleanup_empty_dirs(tmp_path)
        assert sub.exists()


# ---------------------------------------------------------------------------
# undo / redo
# ---------------------------------------------------------------------------


class TestUndoRedo:
    def test_undo_no_manager(self, organizer):
        assert organizer.undo() is False

    def test_redo_no_manager(self, organizer):
        assert organizer.redo() is False

    def test_undo_no_transaction(self, organizer):
        organizer._undo_manager = MagicMock()
        organizer._last_transaction_id = None
        assert organizer.undo() is False

    def test_redo_no_transaction(self, organizer):
        organizer._undo_manager = MagicMock()
        organizer._last_transaction_id = None
        assert organizer.redo() is False

    def test_undo_calls_manager(self, organizer, tmp_path):
        organizer._undo_manager = MagicMock()
        organizer._undo_manager.undo_transaction.return_value = True
        organizer._last_transaction_id = "txn-1"
        organizer._last_output_path = tmp_path
        assert organizer.undo() is True
        organizer._undo_manager.undo_transaction.assert_called_once_with("txn-1")

    def test_redo_calls_manager(self, organizer):
        organizer._undo_manager = MagicMock()
        organizer._undo_manager.redo_transaction.return_value = True
        organizer._last_transaction_id = "txn-1"
        assert organizer.redo() is True
        organizer._undo_manager.redo_transaction.assert_called_once_with("txn-1")


# ---------------------------------------------------------------------------
# organize — validation
# ---------------------------------------------------------------------------


# organize — validation
# ---------------------------------------------------------------------------


class TestOrganize:
    def test_nonexistent_input(self, organizer):
        with pytest.raises(ValueError, match="Input path does not exist"):
            organizer.organize(Path("nonexistent"), Path("output"))

    def test_empty_directory(self, organizer, tmp_path):
        result = organizer.organize(tmp_path, tmp_path / "output")
        assert result.total_files == 0


# ---------------------------------------------------------------------------
# _categorize_files
# ---------------------------------------------------------------------------


class TestCategorizeFiles:
    def test_categorize_all_file_types(self, organizer, tmp_path):
        in_dir = tmp_path / "input"
        in_dir.mkdir()
        (in_dir / "doc.txt").write_text("text")
        (in_dir / "photo.jpg").write_text("img")
        (in_dir / "movie.mp4").write_text("vid")
        (in_dir / "song.mp3").write_text("aud")
        (in_dir / "drawing.dwg").write_text("cad")
        (in_dir / "archive.unknown").write_text("other")

        with (
            patch("file_organizer.core.display.show_file_breakdown") as mock_show,
            patch.object(organizer, "_init_text_processor"),
            patch.object(organizer, "_fallback_by_extension", return_value=[]),
            patch.object(organizer, "_process_audio_files", return_value=[]),
            patch.object(organizer, "_process_video_files", return_value=[]),
        ):
            organizer.organize(in_dir, tmp_path / "output")

        mock_show.assert_called_once()
        kwargs = mock_show.call_args[1]
        assert [f.name for f in kwargs["text_files"]] == ["doc.txt"]
        assert [f.name for f in kwargs["image_files"]] == ["photo.jpg"]
        assert [f.name for f in kwargs["video_files"]] == ["movie.mp4"]
        assert [f.name for f in kwargs["audio_files"]] == ["song.mp3"]
        assert [f.name for f in kwargs["cad_files"]] == ["drawing.dwg"]
        assert [f.name for f in kwargs["other_files"]] == ["archive.unknown"]


# ---------------------------------------------------------------------------
# organize execution & media pipeline tests
# ---------------------------------------------------------------------------


class TestOrganizePipelinesAndExecution:
    def test_organize_vram_cleanup_and_vision_ready(self, organizer, tmp_path):
        txt = tmp_path / "input" / "doc.txt"
        img = tmp_path / "input" / "img.jpg"
        txt.parent.mkdir(parents=True)
        txt.write_text("text")
        img.write_text("image")

        mock_txt_proc = MagicMock()
        mock_txt_proc.text_model.is_initialized = True
        organizer.enable_vision = True

        mock_vis_proc = MagicMock()
        mock_vis_proc.vision_model.is_initialized = True

        proc_txt = MagicMock(error=None, folder_name="Documents", filename="doc", file_path=txt)
        proc_img = MagicMock(error=None, folder_name="Images", filename="img", file_path=img)

        with (
            patch.object(
                organizer,
                "_init_text_processor",
                side_effect=lambda: setattr(organizer, "text_processor", mock_txt_proc),
            ),
            patch.object(
                organizer,
                "_init_vision_processor",
                side_effect=lambda: setattr(organizer, "vision_processor", mock_vis_proc),
            ),
            patch.object(organizer, "_process_text_files", return_value=[proc_txt]),
            patch.object(
                organizer, "_process_image_files", return_value=[proc_img]
            ) as mock_proc_img,
        ):
            result = organizer.organize(tmp_path / "input", tmp_path / "output")

        mock_txt_proc.cleanup.assert_called()
        assert organizer.text_processor is None
        mock_proc_img.assert_called_once()
        assert result.total_files == 2

    def test_organize_vision_not_ready_falls_back(self, organizer, tmp_path):
        img = tmp_path / "input" / "img.jpg"
        img.parent.mkdir(parents=True)
        img.write_text("image")

        organizer.enable_vision = True
        mock_vis_proc = MagicMock()
        mock_vis_proc.vision_model.is_initialized = False

        with (
            patch.object(organizer, "_init_vision_processor") as mock_init_vis,
            patch.object(organizer, "_fallback_by_extension", return_value=[]) as mock_fb,
        ):

            def set_vis():
                organizer.vision_processor = mock_vis_proc

            mock_init_vis.side_effect = set_vis
            organizer.organize(tmp_path / "input", tmp_path / "output")

        mock_fb.assert_called_once_with([img])

    def test_organize_dispatches_audio_video_and_cad_with_text_ready(self, organizer, tmp_path):
        aud = tmp_path / "input" / "track.mp3"
        vid = tmp_path / "input" / "clip.mp4"
        cad = tmp_path / "input" / "cad.dwg"
        oth = tmp_path / "input" / "raw.bin"
        aud.parent.mkdir(parents=True)
        aud.write_text("audio")
        vid.write_text("video")
        cad.write_text("cad")
        oth.write_text("other")

        mock_txt_proc = MagicMock()
        mock_txt_proc.text_model.is_initialized = True

        proc_aud = MagicMock(error=None, folder_name="Audio", filename="track", file_path=aud)
        proc_vid = MagicMock(error=None, folder_name="Video", filename="clip", file_path=vid)
        proc_cad = MagicMock(error=None, folder_name="CAD", filename="cad", file_path=cad)

        with (
            patch.object(
                organizer,
                "_init_text_processor",
                side_effect=lambda: setattr(organizer, "text_processor", mock_txt_proc),
            ),
            patch.object(organizer, "_process_text_files", return_value=[proc_cad]) as mock_cad,
            patch.object(organizer, "_process_audio_files", return_value=[proc_aud]) as mock_aud,
            patch.object(organizer, "_process_video_files", return_value=[proc_vid]) as mock_vid,
        ):
            result = organizer.organize(tmp_path / "input", tmp_path / "output")

        mock_cad.assert_called_once()
        mock_aud.assert_called_once_with([aud])
        mock_vid.assert_called_once_with([vid])
        assert result.total_files == 4
        assert result.skipped_files == 1

    def test_organize_no_files_processed_returns_early(self, organizer, tmp_path):
        f = tmp_path / "input" / "f.txt"
        f.parent.mkdir(parents=True)
        f.write_text("text")

        with (
            patch.object(organizer, "_init_text_processor"),
            patch.object(organizer, "_process_text_files", return_value=[]),
            patch.object(organizer, "_fallback_by_extension", return_value=[]),
        ):
            result = organizer.organize(tmp_path / "input", tmp_path / "output")
        assert result.processed_files == 0
        assert result.organized_structure == {}

    def test_organize_real_run_execution(self, organizer, tmp_path):
        organizer.dry_run = False
        f = tmp_path / "input" / "doc.txt"
        f.parent.mkdir(parents=True)
        f.write_text("hello")

        proc = MagicMock(error=None, folder_name="Docs", filename="doc", file_path=f)
        mock_undo = MagicMock()

        with (
            patch.object(organizer, "_init_text_processor"),
            patch.object(organizer, "_process_text_files", return_value=[proc]),
            patch("file_organizer.core.organizer.UndoManager", return_value=mock_undo),
            patch(
                "file_organizer.core.organizer.execute_plan",
                return_value=(
                    {"Docs": [tmp_path / "output" / "Docs" / "doc.txt"]},
                    "txn-real-1",
                    [("doc.txt", "minor-error")],
                ),
            ),
        ):
            result = organizer.organize(tmp_path / "input", tmp_path / "output")

        assert result.processed_files == 1
        assert result.failed_files == 1
        assert ("doc.txt", "minor-error") in result.errors
        assert organizer._last_transaction_id == "txn-real-1"
        assert "Docs" in result.organized_structure

    def test_undo_when_output_path_is_none(self, organizer):
        organizer._undo_manager = MagicMock()
        organizer._undo_manager.undo_transaction.return_value = True
        organizer._last_transaction_id = "txn-2"
        organizer._last_output_path = None
        with patch("file_organizer.core.file_ops.cleanup_empty_dirs") as mock_cleanup:
            assert organizer.undo() is True
            mock_cleanup.assert_not_called()

    def test_execute_plan_when_undo_manager_already_set(self, organizer, tmp_path):
        organizer._undo_manager = MagicMock()
        mock_plan = MagicMock(
            output_path=str(tmp_path / "out"),
            total_files=1,
            skipped_files=0,
            failed_files=0,
            deduplicated_files=0,
            errors=[],
        )
        with patch(
            "file_organizer.core.organizer.execute_plan",
            return_value=({"Docs": [tmp_path / "out" / "Docs" / "f.txt"]}, "txn-3", []),
        ):
            res = organizer.execute_plan(mock_plan)
        assert res.transaction_id == "txn-3"
        assert res.processed_files == 1

    def test_hash_file_safedir_not_implemented_fallback(self, organizer, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("sample content")
        with patch(
            "file_organizer.core.organizer.SafeDir.open_root", side_effect=NotImplementedError
        ):
            h = organizer._sha256_via_safedir(f)
        assert h is not None

    def test_init_text_processor_calls_initializer(self, organizer):
        with patch("file_organizer.core.organizer.initializer.init_text_processor") as mock_init:
            organizer._init_text_processor()
            mock_init.assert_called_once()

    def test_process_audio_files_initializes_transcriber(self, organizer, tmp_path):
        organizer.transcribe_audio = True
        organizer.whisper_model = "base"
        f = tmp_path / "sample.mp3"

        mock_audio_model = MagicMock()
        mock_audio_model_cls = MagicMock(return_value=mock_audio_model)

        with (
            patch("file_organizer.services.audio.transcriber._FASTER_WHISPER_AVAILABLE", True),
            patch("file_organizer.models.audio_model.AudioModel", mock_audio_model_cls),
            patch(
                "file_organizer.core.dispatcher.process_audio_files", return_value=[]
            ) as mock_disp,
        ):
            res = organizer._process_audio_files([f])

            assert res == []
            mock_audio_model.initialize.assert_called_once()
            assert organizer._audio_model is mock_audio_model
            mock_disp.assert_called_once()
            assert mock_disp.call_args[1]["transcriber"] is mock_audio_model

            # Second call reuses already initialized _audio_model
            with patch(
                "file_organizer.core.dispatcher.process_audio_files", return_value=[]
            ) as mock_disp2:
                organizer._process_audio_files([f])
            assert mock_disp2.call_args[1]["transcriber"] is mock_audio_model

    def test_organize_content_deduplication(self, organizer, tmp_path):
        f1 = tmp_path / "input" / "doc1.txt"
        f2 = tmp_path / "input" / "doc2.txt"
        f1.parent.mkdir(parents=True)
        f1.write_text("duplicate content")
        f2.write_text("duplicate content")

        proc1 = MagicMock(error=None, folder_name="Docs", filename="doc1", file_path=f1)
        proc2 = MagicMock(error=None, folder_name="Docs", filename="doc2", file_path=f2)

        with (
            patch.object(organizer, "_init_text_processor"),
            patch.object(organizer, "_process_text_files", return_value=[proc1, proc2]),
            patch.object(organizer, "_sha256_via_safedir", return_value="hash-12345"),
        ):
            res = organizer.organize(tmp_path / "input", tmp_path / "output")

        assert res.deduplicated_files == 1
        assert res.total_files == 2
        assert res.processed_files == 1
