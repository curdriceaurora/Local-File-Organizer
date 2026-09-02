"""Unit coverage for ``fo analyze`` helper paths.

The broader CLI test module is marked integration and is intentionally
excluded from the diff-cover pre-commit gate. These tests exercise the
same helper behavior under the unit marker so changed-line coverage stays
honest for the lightweight gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import typer

from file_organizer.cli import utilities

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _processed_image(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "description": "A receipt with payment details.",
        "folder_name": "receipts",
        "filename": "payment_receipt",
        "confidence": 0.91,
        "has_text": False,
        "extracted_text": None,
        "source": "vision",
        "error": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_analyze_dispatches_images_and_text(tmp_path: Path) -> None:
    image = tmp_path / "receipt.jpg"
    image.write_bytes(b"jpeg")
    text = tmp_path / "notes.txt"
    text.write_text("notes")

    with (
        patch("file_organizer.cli.utilities._analyze_image_file") as image_analyze,
        patch("file_organizer.cli.utilities._analyze_text_file") as text_analyze,
    ):
        with pytest.raises(typer.Exit) as image_exit:
            utilities.analyze(image)
        with pytest.raises(typer.Exit) as text_exit:
            utilities.analyze(text)

    assert image_exit.value.exit_code == 0
    assert text_exit.value.exit_code == 0
    image_analyze.assert_called_once_with(image, verbose=False, json_output=False)
    text_analyze.assert_called_once_with(text, verbose=False, json_output=False)


def test_analyze_image_file_emits_verbose_text(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    image = tmp_path / "receipt.jpg"
    image.write_bytes(b"jpeg")
    processor = MagicMock()
    processor.process_file.return_value = _processed_image(
        has_text=True,
        extracted_text="Payment process",
    )
    vision_config = SimpleNamespace(name="vision-model")

    with (
        patch(
            "file_organizer.config.provider_env.get_model_configs",
            return_value=(MagicMock(), vision_config),
        ),
        patch("file_organizer.services.vision_processor.VisionProcessor", return_value=processor),
    ):
        utilities._analyze_image_file(image, verbose=True, json_output=False)

    output = capsys.readouterr().out
    assert "Category:" in output
    assert "Model:" in output
    assert "Extracted text:" in output
    processor.initialize.assert_called_once_with()
    processor.process_file.assert_called_once_with(image)
    processor.cleanup.assert_called_once_with()


def test_analyze_image_file_emits_degraded_json(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    image = tmp_path / "receipt.jpg"
    image.write_bytes(b"jpeg")
    processor = MagicMock()
    processor.process_file.return_value = _processed_image(
        source="fallback_filename",
        error="vision backend unavailable",
        confidence=0.3,
    )

    with (
        patch(
            "file_organizer.config.provider_env.get_model_configs",
            return_value=(MagicMock(), SimpleNamespace(name="vision-model")),
        ),
        patch("file_organizer.services.vision_processor.VisionProcessor", return_value=processor),
    ):
        utilities._analyze_image_file(image, verbose=False, json_output=True)

    data = json.loads(capsys.readouterr().out)
    assert data["source"] == "fallback_filename"
    assert data["error"] == "vision backend unavailable"


def test_analyze_image_file_cleans_up_after_init_failure(tmp_path: Path) -> None:
    image = tmp_path / "receipt.jpg"
    image.write_bytes(b"jpeg")
    processor = MagicMock()
    processor.initialize.side_effect = RuntimeError("backend down")

    with (
        patch(
            "file_organizer.config.provider_env.get_model_configs",
            return_value=(MagicMock(), SimpleNamespace(name="vision-model")),
        ),
        patch("file_organizer.services.vision_processor.VisionProcessor", return_value=processor),
        pytest.raises(typer.Exit) as exc_info,
    ):
        utilities._analyze_image_file(image, verbose=False, json_output=False)

    assert exc_info.value.exit_code == 1
    processor.cleanup.assert_called_once_with()


def test_analyze_image_file_cleans_up_after_import_error_init_failure(tmp_path: Path) -> None:
    image = tmp_path / "receipt.jpg"
    image.write_bytes(b"jpeg")
    processor = MagicMock()
    processor.initialize.side_effect = ImportError("vision dependency missing")

    with (
        patch(
            "file_organizer.config.provider_env.get_model_configs",
            return_value=(MagicMock(), SimpleNamespace(name="vision-model")),
        ),
        patch("file_organizer.services.vision_processor.VisionProcessor", return_value=processor),
        pytest.raises(typer.Exit) as exc_info,
    ):
        utilities._analyze_image_file(image, verbose=False, json_output=False)

    assert exc_info.value.exit_code == 1
    processor.cleanup.assert_called_once_with()


def test_analyze_image_file_cleans_up_after_process_failure(tmp_path: Path) -> None:
    image = tmp_path / "receipt.jpg"
    image.write_bytes(b"jpeg")
    processor = MagicMock()
    processor.process_file.side_effect = ValueError("bad image")

    with (
        patch(
            "file_organizer.config.provider_env.get_model_configs",
            return_value=(MagicMock(), SimpleNamespace(name="vision-model")),
        ),
        patch("file_organizer.services.vision_processor.VisionProcessor", return_value=processor),
        pytest.raises(typer.Exit) as exc_info,
    ):
        utilities._analyze_image_file(image, verbose=False, json_output=False)

    assert exc_info.value.exit_code == 1
    processor.cleanup.assert_called_once_with()


def test_cleanup_vision_processor_handles_none_and_json_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    utilities._cleanup_vision_processor(None, json_output=False)

    processor = MagicMock()
    processor.cleanup.side_effect = RuntimeError("cleanup failed")

    utilities._cleanup_vision_processor(processor, json_output=True)

    captured = capsys.readouterr()
    assert "Vision cleanup failed" in captured.err
    assert "Vision cleanup failed" not in captured.out


def test_analyze_text_file_uses_shared_renderer(tmp_path: Path) -> None:
    text = tmp_path / "notes.txt"
    text.write_text("some useful notes")
    model = MagicMock()
    model_config = SimpleNamespace(name="text-model")
    model_cls = MagicMock(return_value=model)
    model_cls.get_default_config.return_value = model_config

    with (
        patch("file_organizer.models.text_model.TextModel", model_cls),
        patch("file_organizer.services.analyzer.truncate_content", return_value="short"),
        patch("file_organizer.services.analyzer.generate_category", return_value="notes"),
        patch(
            "file_organizer.services.analyzer.generate_description", return_value="Useful notes."
        ),
        patch("file_organizer.services.analyzer.calculate_confidence", return_value=0.8),
        patch("file_organizer.cli.utilities._emit_analysis_result") as emit_result,
    ):
        utilities._analyze_text_file(text, verbose=True, json_output=False)

    model.initialize.assert_called_once_with()
    emit_result.assert_called_once()
    assert emit_result.call_args.kwargs["category"] == "notes"


def test_emit_analysis_result_json_and_warning_text(capsys: pytest.CaptureFixture[str]) -> None:
    utilities._emit_analysis_result(
        description="desc",
        category="cat",
        confidence=0.5,
        json_output=True,
        verbose=False,
        json_extra={"source": "vision"},
    )
    assert json.loads(capsys.readouterr().out)["source"] == "vision"

    utilities._emit_analysis_result(
        description="desc",
        category="cat",
        confidence=0.5,
        json_output=False,
        verbose=False,
        warning="degraded",
    )
    assert "Warning:" in capsys.readouterr().out
