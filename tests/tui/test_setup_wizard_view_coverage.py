# ruff: noqa: E402
"""Unit and integration coverage tests for file_organizer.tui.setup_wizard_view.

Targets 100% statement and branch coverage for SetupWizardView.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# 1. Mock textual.work decorator BEFORE importing SetupWizardView
def mock_work_decorator(*args, **kwargs):
    if len(args) == 1 and callable(args[0]):
        return args[0]
    return lambda f: f


import textual

textual.work = mock_work_decorator

from textual.widgets import Static

from file_organizer.tui.setup_wizard_view import SetupWizardView, WizardScreen

pytestmark = pytest.mark.unit


def _create_view_with_mocks() -> tuple[SetupWizardView, MagicMock, MagicMock]:
    """Helper to create a SetupWizardView with query_one and app mocked."""
    view = SetupWizardView()

    # Mock query_one to return a mock body widget
    mock_body = MagicMock(spec=Static)
    view.query_one = MagicMock(return_value=mock_body)

    # Mock app property
    mock_app = MagicMock()
    app_prop = PropertyMock(return_value=mock_app)
    type(view).app = app_prop

    # Force call_from_thread to execute synchronously in tests
    mock_app.call_from_thread = lambda func, *args, **kwargs: func(*args, **kwargs)

    return view, mock_body, mock_app


def test_setup_wizard_view_initialization() -> None:
    """Verify default view state on instantiation."""
    view = SetupWizardView()
    assert view._current_screen == WizardScreen.WELCOME
    assert view._selected_mode is None
    assert view._capabilities is None
    assert view._detection_status == "pending"
    assert view._detection_message == ""
    assert view._detection_step == ""
    assert view._detection_progress == 0
    assert view._selected_model is None
    assert view._download_status == "not_started"
    assert view._download_progress == 0
    assert view._download_message == ""


def test_setup_wizard_view_on_mount() -> None:
    """Verify on_mount updates the status message."""
    view, _, _ = _create_view_with_mocks()
    with patch.object(view, "_set_status") as mock_set_status:
        view.on_mount()
        mock_set_status.assert_called_once()
        assert "Welcome to File Organizer" in mock_set_status.call_args[0][0]


def test_setup_wizard_view_compose() -> None:
    """Verify compose yields a Static body widget with the rendered welcome screen."""
    view, _, _ = _create_view_with_mocks()
    with patch.object(view, "_render_screen", return_value="welcome_markup") as mock_render:
        widgets = list(view.compose())
        assert len(widgets) == 1
        static_widget = widgets[0]
        assert isinstance(static_widget, Static)
        assert static_widget.id == "wizard-body"
        assert static_widget.renderable == "welcome_markup"
        mock_render.assert_called_once()


def test_setup_wizard_view_action_select_option_1() -> None:
    """Verify Option 1 selection behaviour across different screens."""
    view, _, _ = _create_view_with_mocks()

    # 1. On WELCOME screen -> Select Quick Start, trigger detection
    view._current_screen = WizardScreen.WELCOME
    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_run_hardware_detection") as mock_detect,
    ):
        view.action_select_option_1()
        assert view._selected_mode == "quick_start"
        assert view._current_screen == WizardScreen.HARDWARE_DETECT
        mock_status.assert_called_once()
        mock_refresh.assert_called_once()
        mock_detect.assert_called_once()

    # 2. On MODE_SELECT screen -> Select Quick Start, trigger detection
    view._current_screen = WizardScreen.MODE_SELECT
    view._selected_mode = None
    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_run_hardware_detection") as mock_detect,
    ):
        view.action_select_option_1()
        assert view._selected_mode == "quick_start"
        assert view._current_screen == WizardScreen.HARDWARE_DETECT
        mock_status.assert_called_once()
        mock_refresh.assert_called_once()
        mock_detect.assert_called_once()

    # 3. On MODEL_SELECT screen -> Select recommended model from hardware capabilities
    view._current_screen = WizardScreen.MODEL_SELECT
    view._selected_model = None

    # Setup mock capabilities
    mock_hw = MagicMock()
    mock_hw.recommended_text_model.return_value = "recommended_model"
    mock_caps = MagicMock()
    mock_caps.hardware = mock_hw
    view._capabilities = mock_caps

    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
    ):
        view.action_select_option_1()
        assert view._selected_model == "recommended_model"
        mock_status.assert_called_once_with("Selected model: recommended_model")
        mock_refresh.assert_called_once()


def test_setup_wizard_view_action_select_option_2() -> None:
    """Verify Option 2 selection behaviour across different screens."""
    view, _, _ = _create_view_with_mocks()

    # 1. On WELCOME screen -> Select Power User, trigger detection
    view._current_screen = WizardScreen.WELCOME
    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_run_hardware_detection") as mock_detect,
    ):
        view.action_select_option_2()
        assert view._selected_mode == "power_user"
        assert view._current_screen == WizardScreen.HARDWARE_DETECT
        mock_status.assert_called_once()
        mock_refresh.assert_called_once()
        mock_detect.assert_called_once()

    # 2. On MODE_SELECT screen -> Select Power User, trigger detection
    view._current_screen = WizardScreen.MODE_SELECT
    view._selected_mode = None
    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_run_hardware_detection") as mock_detect,
    ):
        view.action_select_option_2()
        assert view._selected_mode == "power_user"
        assert view._current_screen == WizardScreen.HARDWARE_DETECT
        mock_status.assert_called_once()
        mock_refresh.assert_called_once()
        mock_detect.assert_called_once()

    # 3. On MODEL_SELECT screen -> Select alternative model (Qwen 3b if 7b is recommended)
    view._current_screen = WizardScreen.MODEL_SELECT
    view._selected_model = None

    mock_hw = MagicMock()
    mock_hw.recommended_text_model.return_value = "qwen2.5:7b-instruct-q4_K_M"
    mock_caps = MagicMock()
    mock_caps.hardware = mock_hw
    view._capabilities = mock_caps

    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
    ):
        view.action_select_option_2()
        assert view._selected_model == "qwen2.5:3b-instruct-q4_K_M"
        mock_status.assert_called_once_with("Selected model: qwen2.5:3b-instruct-q4_K_M")
        mock_refresh.assert_called_once()

    # 4. On MODEL_SELECT screen -> Select alternative model (Qwen 7b if 3b is recommended)
    mock_hw.recommended_text_model.return_value = "qwen2.5:3b-instruct-q4_K_M"
    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
    ):
        view.action_select_option_2()
        assert view._selected_model == "qwen2.5:7b-instruct-q4_K_M"


def test_setup_wizard_view_action_select_option_3() -> None:
    """Verify Option 3 selection behaviour on MODEL_SELECT screen."""
    view, _, _ = _create_view_with_mocks()

    # 1. On MODEL_SELECT screen -> Select first installed model if available
    view._current_screen = WizardScreen.MODEL_SELECT
    view._selected_model = None

    mock_model = MagicMock()
    mock_model.name = "installed_model_1"
    mock_model.size = 3 * 1024**3

    mock_caps = MagicMock()
    mock_caps.installed_models = [mock_model]
    view._capabilities = mock_caps

    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
    ):
        view.action_select_option_3()
        assert view._selected_model == "installed_model_1"
        mock_status.assert_called_once_with("Selected installed model: installed_model_1")
        mock_refresh.assert_called_once()


def test_setup_wizard_view_action_download_model() -> None:
    """Verify model download action boundaries and validations."""
    view, _, _ = _create_view_with_mocks()

    # 1. Wrong screen -> Ignore
    view._current_screen = WizardScreen.WELCOME
    with patch.object(view, "_run_model_download") as mock_download:
        view.action_download_model()
        mock_download.assert_not_called()

    # 2. Model Select screen, but no model selected
    view._current_screen = WizardScreen.MODEL_SELECT
    view._selected_model = None
    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_run_model_download") as mock_download,
    ):
        view.action_download_model()
        mock_status.assert_called_once_with("Please select a model first (press 1, 2, or 3).")
        mock_download.assert_not_called()

    # 3. Model is already installed
    view._selected_model = "my_model"
    mock_model = MagicMock()
    mock_model.name = "my_model"
    mock_caps = MagicMock()
    mock_caps.installed_models = [mock_model]
    view._capabilities = mock_caps

    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_run_model_download") as mock_download,
    ):
        view.action_download_model()
        mock_status.assert_called_once_with("Model my_model is already installed.")
        mock_download.assert_not_called()

    # 4. Model is not installed -> Trigger download
    view._selected_model = "new_model"
    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_run_model_download") as mock_download,
    ):
        view.action_download_model()
        mock_status.assert_called_once_with("Starting download of new_model...")
        mock_download.assert_called_once()


def test_setup_wizard_view_action_skip_setup() -> None:
    """Verify skip setup action simply sets status and logs."""
    view, _, _ = _create_view_with_mocks()
    with patch.object(view, "_set_status") as mock_status:
        view.action_skip_setup()
        mock_status.assert_called_once()
        assert "skipped" in mock_status.call_args[0][0]


def test_setup_wizard_view_action_continue_wizard() -> None:
    """Verify Continue action flows correctly between screens."""
    view, _, _ = _create_view_with_mocks()

    # 1. On WELCOME screen -> Transition to MODE_SELECT
    view._current_screen = WizardScreen.WELCOME
    with patch.object(view, "_set_status") as mock_status:
        view.action_continue_wizard()
        assert view._current_screen == WizardScreen.MODE_SELECT
        mock_status.assert_called_once_with("Select your setup mode: Quick Start or Power User.")

    # 2. On MODE_SELECT screen with no mode selected -> Warn user
    view._current_screen = WizardScreen.MODE_SELECT
    view._selected_mode = None
    with patch.object(view, "_set_status") as mock_status:
        view.action_continue_wizard()
        assert view._current_screen == WizardScreen.MODE_SELECT
        mock_status.assert_called_once_with("Please select a mode first (press 1 or 2).")

    # 3. On MODE_SELECT screen with mode selected -> Transition to HARDWARE_DETECT & trigger detection
    view._selected_mode = "quick_start"
    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_run_hardware_detection") as mock_detect,
    ):
        view.action_continue_wizard()
        assert view._current_screen == WizardScreen.HARDWARE_DETECT
        mock_status.assert_called_once_with("Detecting hardware capabilities...")
        mock_refresh.assert_called_once()
        mock_detect.assert_called_once()

    # 4. On HARDWARE_DETECT screen when detection is not complete -> Warn user
    view._current_screen = WizardScreen.HARDWARE_DETECT
    view._detection_status = "detecting"
    with patch.object(view, "_set_status") as mock_status:
        view.action_continue_wizard()
        assert view._current_screen == WizardScreen.HARDWARE_DETECT
        mock_status.assert_called_once_with("Please wait for hardware detection to complete.")

    # 5. On HARDWARE_DETECT screen when complete -> Transition to MODEL_SELECT
    view._detection_status = "complete"
    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
    ):
        view.action_continue_wizard()
        assert view._current_screen == WizardScreen.MODEL_SELECT
        mock_status.assert_called_once_with("Select and download AI model...")
        mock_refresh.assert_called_once()

    # 6. On MODEL_SELECT screen with no model selected -> Warn user
    view._current_screen = WizardScreen.MODEL_SELECT
    view._selected_model = None
    with patch.object(view, "_set_status") as mock_status:
        view.action_continue_wizard()
        assert view._current_screen == WizardScreen.MODEL_SELECT
        mock_status.assert_called_once_with("Please select a model first (press 1, 2, or 3).")

    # 7. On MODEL_SELECT screen with model selected but not downloaded -> Warn user
    view._selected_model = "target_model"
    view._capabilities = MagicMock(installed_models=[])
    view._download_status = "not_started"
    with patch.object(view, "_set_status") as mock_status:
        view.action_continue_wizard()
        assert view._current_screen == WizardScreen.MODEL_SELECT
        mock_status.assert_called_once_with("Please download the model first (press d).")

    # 8. On MODEL_SELECT screen with model selected and downloaded/complete -> Transition to COMPLETE
    view._download_status = "complete"
    with (
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "_refresh_screen") as mock_refresh,
    ):
        view.action_continue_wizard()
        assert view._current_screen == WizardScreen.COMPLETE
        mock_status.assert_called_once_with("Setup complete!")
        mock_refresh.assert_called_once()


def test_setup_wizard_view_action_go_back() -> None:
    """Verify Back action flows correctly backwards between screens."""
    view, _, _ = _create_view_with_mocks()
    with (
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_set_status") as mock_status,
    ):
        # 1. MODE_SELECT -> WELCOME
        view._current_screen = WizardScreen.MODE_SELECT
        view.action_go_back()
        assert view._current_screen == WizardScreen.WELCOME
        mock_status.assert_any_call("Welcome screen. Press Enter to continue.")

        # 2. HARDWARE_DETECT -> MODE_SELECT
        view._current_screen = WizardScreen.HARDWARE_DETECT
        view.action_go_back()
        assert view._current_screen == WizardScreen.MODE_SELECT
        assert view._selected_mode is None
        mock_status.assert_any_call("Mode selection. Press 1 or 2 to choose.")

        # 3. MODEL_SELECT -> HARDWARE_DETECT
        view._current_screen = WizardScreen.MODEL_SELECT
        view.action_go_back()
        assert view._current_screen == WizardScreen.HARDWARE_DETECT
        assert view._selected_model is None
        assert view._download_status == "not_started"
        assert view._download_progress == 0
        mock_status.assert_any_call("Hardware detection. Press Enter to continue.")

        # 4. COMPLETE -> MODEL_SELECT
        view._current_screen = WizardScreen.COMPLETE
        view.action_go_back()
        assert view._current_screen == WizardScreen.MODEL_SELECT
        mock_status.assert_any_call("Model selection. Press 1, 2, or 3 to choose.")

        assert mock_refresh.call_count == 4


def test_setup_wizard_view_screen_rendering() -> None:
    """Verify all screen rendering functions produce non-empty strings and handle capability bounds."""
    view = SetupWizardView()

    # 1. Welcome screen
    view._current_screen = WizardScreen.WELCOME
    markup = view._render_screen()
    assert "Welcome" in markup

    # 2. Mode Select screen
    view._current_screen = WizardScreen.MODE_SELECT
    view._selected_mode = "quick_start"
    markup = view._render_screen()
    assert "Select Setup Mode" in markup
    assert "✓" in markup

    # 3. Hardware Detect screen - Pending
    view._current_screen = WizardScreen.HARDWARE_DETECT
    view._detection_status = "pending"
    markup = view._render_screen()
    assert "Hardware Detection" in markup
    assert "Preparing" in markup

    # 4. Hardware Detect screen - Detecting
    view._detection_status = "detecting"
    view._detection_progress = 45
    view._detection_step = "Reading memory..."
    markup = view._render_screen()
    assert "Detecting system" in markup
    assert "Reading memory..." in markup

    # 5. Hardware Detect screen - Error
    view._detection_status = "error"
    view._detection_message = "No controller found"
    markup = view._render_screen()
    assert "Detection failed" in markup
    assert "No controller found" in markup

    # 6. Hardware Detect screen - Complete with Nvidia GPU
    mock_hw = MagicMock()
    mock_hw.gpu_type = MagicMock(value="nvidia")
    mock_hw.gpu_name = "RTX 4090"
    mock_hw.vram_gb = 24
    mock_hw.ram_gb = 64
    mock_hw.cpu_cores = 16
    mock_hw.arch = "x86_64"
    mock_hw.recommended_text_model.return_value = "qwen2.5:7b-instruct-q4_K_M"
    mock_hw.recommended_workers.return_value = 4

    mock_ollama = MagicMock()
    mock_ollama.running = True
    mock_ollama.installed = True
    mock_ollama.version = "0.1.15"
    mock_ollama.models_count = 3

    mock_model = MagicMock()
    mock_model.name = "qwen2.5:7b-instruct-q4_K_M"
    mock_model.size = int(4.5 * 1024**3)

    # Model double lacking .size attribute for regression testing
    mock_model_no_size = MagicMock()
    mock_model_no_size.name = "custom-local-model"
    del mock_model_no_size.size

    mock_caps = MagicMock()
    mock_caps.hardware = mock_hw
    mock_caps.ollama_status = mock_ollama
    mock_caps.installed_models = [mock_model_no_size, mock_model]

    view._capabilities = mock_caps
    view._detection_status = "complete"
    markup = view._render_screen()
    assert "Detection complete!" in markup
    assert "RTX 4090" in markup
    assert "64GB" in markup
    assert "Ollama: Running" in markup

    # Test Apple Silicon GPU path in hardware render
    mock_hw.gpu_type = MagicMock(value="apple_mps")
    mock_hw.gpu_name = "Apple M2 Max"
    markup = view._render_screen()
    assert "Apple M2 Max" in markup
    assert "Unified Memory" in markup

    # Test CPU-only GPU path in hardware render
    mock_hw.gpu_type = MagicMock(value="none")
    markup = view._render_screen()
    assert "No GPU detected" in markup

    # Test other GPU path in hardware render
    mock_hw.gpu_type = MagicMock(value="amd")
    markup = view._render_screen()
    assert "amd" in markup

    # Test Ollama installed but not running in hardware render
    mock_ollama.running = False
    mock_ollama.installed = True
    markup = view._render_screen()
    assert "Installed but not running" in markup

    # Test Ollama not installed in hardware render
    mock_ollama.installed = False
    markup = view._render_screen()
    assert "Not installed" in markup

    # 7. Model Select screen - Capabilities loading
    view._current_screen = WizardScreen.MODEL_SELECT
    view._capabilities = None
    markup = view._render_screen()
    assert "Loading model information" in markup

    # 8. Model Select screen - Capabilities loaded, showing recommended/alternative/installed
    view._capabilities = mock_caps
    view._selected_model = "qwen2.5:7b-instruct-q4_K_M"
    markup = view._render_screen()
    assert "Model Selection" in markup
    assert "qwen2.5:7b-instruct-q4_K_M" in markup
    assert "Unknown size" in markup

    # Test 3b recommended alternative sizing descriptions
    mock_hw.recommended_text_model.return_value = "qwen2.5:3b-instruct-q4_K_M"
    markup = view._render_screen()
    assert "qwen2.5:3b-instruct-q4_K_M" in markup

    # 9. Complete screen
    view._current_screen = WizardScreen.COMPLETE
    markup = view._render_screen()
    assert "Setup Complete!" in markup

    # 10. Unknown screen state fallback
    view._current_screen = "invalid_state"
    markup = view._render_screen()
    assert "Unknown screen state" in markup


def test_setup_wizard_view_status_bar_update() -> None:
    """Verify _set_status safely handles absence of StatusBar or application mount."""
    view = SetupWizardView()

    # Should not raise exception when not mounted in an app
    view._set_status("test message")

    # Mock mounted app and query_one
    mock_status_bar = MagicMock()
    mock_app = MagicMock()
    mock_app.query_one.return_value = mock_status_bar

    with patch.object(SetupWizardView, "app", new_callable=PropertyMock, return_value=mock_app):
        view._set_status("success message")
        mock_status_bar.set_status.assert_called_once_with("success message")


def test_setup_wizard_view_run_hardware_detection_success() -> None:
    """Verify background hardware detection updates status progress and stores capabilities."""
    view, _, mock_app = _create_view_with_mocks()
    view._selected_mode = "quick_start"

    # Setup mock capabilities return from core
    mock_hw = MagicMock()
    mock_hw.gpu_type = MagicMock(value="nvidia")
    mock_hw.ram_gb = 16
    mock_caps = MagicMock()
    mock_caps.hardware = mock_hw

    mock_wizard = MagicMock()
    mock_wizard.detect_capabilities.return_value = mock_caps

    with (
        patch("file_organizer.core.setup_wizard.SetupWizard", return_value=mock_wizard),
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_set_status") as mock_status,
    ):
        view._run_hardware_detection()

        assert view._detection_status == "complete"
        assert view._capabilities == mock_caps
        assert view._detection_progress == 100
        mock_refresh.assert_called()
        mock_status.assert_called()


def test_setup_wizard_view_run_hardware_detection_failure() -> None:
    """Verify background hardware detection failure is gracefully caught and surfaces error."""
    view, _, mock_app = _create_view_with_mocks()
    view._selected_mode = "power_user"

    with (
        patch(
            "file_organizer.core.setup_wizard.SetupWizard", side_effect=ValueError("Hardware error")
        ),
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_set_status") as mock_status,
    ):
        view._run_hardware_detection()

        assert view._detection_status == "error"
        assert view._detection_message == "Hardware error"
        assert view._detection_progress == 0
        mock_refresh.assert_called()
        mock_status.assert_called_with("Detection failed: Hardware error")


def test_setup_wizard_view_run_model_download_no_model() -> None:
    """Verify model download background task returns immediately if no model is selected."""
    view, _, _ = _create_view_with_mocks()
    view._selected_model = None
    with patch("sys.modules") as mock_modules:
        view._run_model_download()
        # Should not attempt to import or query packages
        assert "ollama" not in mock_modules


def test_setup_wizard_view_run_model_download_missing_ollama_package() -> None:
    """Verify model download gracefully fails if the ollama python library is missing."""
    view, _, mock_app = _create_view_with_mocks()
    view._selected_model = "some_model"

    with (
        patch.dict("sys.modules", {"ollama": None}),
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_set_status") as mock_status,
    ):
        view._run_model_download()

        assert view._download_status == "error"
        assert "Ollama Python package not installed" in view._download_message
        mock_refresh.assert_called()
        mock_status.assert_called_with("Ollama Python package not installed")


def test_setup_wizard_view_run_model_download_success() -> None:
    """Verify model download pull executes and updates progress to complete."""
    view, _, mock_app = _create_view_with_mocks()
    view._selected_model = "my_selected_model"

    # Mock ollama module client
    mock_ollama_client = MagicMock()
    mock_ollama = MagicMock()
    mock_ollama.Client.return_value = mock_ollama_client

    # Setup capabilities to refresh list
    mock_caps = MagicMock()
    mock_caps.installed_models = []
    view._capabilities = mock_caps

    # Mock a model to return in installed models list
    mock_installed_model = MagicMock()
    mock_installed_model.name = "my_selected_model"
    mock_installed_model.size = int(5 * 1024**3)

    with (
        patch.dict("sys.modules", {"ollama": mock_ollama}),
        patch(
            "file_organizer.core.backend_detector.list_installed_models",
            return_value=[mock_installed_model],
        ),
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_set_status") as mock_status,
    ):
        view._run_model_download()

        assert view._download_status == "complete"
        assert view._download_progress == 100
        mock_ollama_client.pull.assert_called_once_with("my_selected_model")
        mock_refresh.assert_called()
        mock_status.assert_called()


def test_setup_wizard_view_run_model_download_failure() -> None:
    """Verify model download pull exception is caught and surfaces error."""
    view, _, mock_app = _create_view_with_mocks()
    view._selected_model = "failing_model"

    mock_ollama_client = MagicMock()
    mock_ollama_client.pull.side_effect = RuntimeError("network timeout")
    mock_ollama = MagicMock()
    mock_ollama.Client.return_value = mock_ollama_client

    with (
        patch.dict("sys.modules", {"ollama": mock_ollama}),
        patch.object(view, "_refresh_screen") as mock_refresh,
        patch.object(view, "_set_status") as mock_status,
    ):
        view._run_model_download()

        assert view._download_status == "error"
        assert view._download_message == "network timeout"
        assert view._download_progress == 0
        mock_refresh.assert_called()
        mock_status.assert_called_with("Download failed: network timeout")
