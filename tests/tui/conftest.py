"""Shared fixtures for TUI tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def tui_completed_setup(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Keep TUI app tests out of first-run setup unless a test opts into it."""
    if request.node.name == "test_complete_wizard_persists_setup_completed":
        return

    mock_config = MagicMock()
    mock_config.setup_completed = True
    mock_config.default_input_dir = str(tmp_path)
    mock_config.default_output_dir = str(tmp_path / "organized")
    mock_config.default_methodology = "none"
    mock_config.parallel = {}
    mock_config.models.framework = "ollama"
    mock_config.models.text_model = None
    mock_config.models.vision_model = None
    mock_config_manager = MagicMock()
    mock_config_manager.load.return_value = mock_config

    monkeypatch.setattr(
        "file_organizer.tui.app.ConfigManager",
        MagicMock(return_value=mock_config_manager),
    )
    monkeypatch.setattr(
        "file_organizer.tui.app.FileOrganizerApp._check_for_updates", lambda _: None
    )

    # Re-route default '.' scan/input paths to the unique tmp_path for all tests
    # except those explicitly opting out with @pytest.mark.keep_default_paths.
    # Using a marker (rather than substring-matching request.node.name) ensures
    # only intentional tests bypass isolation, preventing accidental leakage.
    if request.node.get_closest_marker("keep_default_paths") is None:
        from file_organizer.tui.audio_view import AudioView
        from file_organizer.tui.file_preview import FilePreviewView
        from file_organizer.tui.methodology_view import MethodologyView
        from file_organizer.tui.organization_preview import OrganizationPreviewView

        # 1. FilePreviewView
        orig_file_preview_init = FilePreviewView.__init__

        def patched_file_preview_init(self, path=".", *args, **kwargs):
            if path == "." or path == Path("."):
                path = tmp_path
            orig_file_preview_init(self, path, *args, **kwargs)

        monkeypatch.setattr(FilePreviewView, "__init__", patched_file_preview_init)

        # 2. AudioView
        orig_audio_init = AudioView.__init__

        def patched_audio_init(self, scan_dir=".", *args, **kwargs):
            if scan_dir == "." or scan_dir == Path("."):
                scan_dir = tmp_path
            orig_audio_init(self, scan_dir, *args, **kwargs)

        monkeypatch.setattr(AudioView, "__init__", patched_audio_init)

        # 3. MethodologyView
        orig_meth_init = MethodologyView.__init__

        def patched_meth_init(self, scan_dir=".", *args, **kwargs):
            if scan_dir == "." or scan_dir == Path("."):
                scan_dir = tmp_path
            orig_meth_init(self, scan_dir, *args, **kwargs)

        monkeypatch.setattr(MethodologyView, "__init__", patched_meth_init)

        # 4. OrganizationPreviewView
        orig_org_init = OrganizationPreviewView.__init__

        def patched_org_init(self, input_dir=".", output_dir="organized_output", *args, **kwargs):
            if input_dir == "." or input_dir == Path("."):
                input_dir = tmp_path
            orig_org_init(self, input_dir, output_dir, *args, **kwargs)

        monkeypatch.setattr(OrganizationPreviewView, "__init__", patched_org_init)
