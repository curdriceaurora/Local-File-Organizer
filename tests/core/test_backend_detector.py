"""Unit tests for backend_detector module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, Mock, patch

# Mock the ollama module before importing backend_detector
# This is required because backend_detector conditionally imports ollama
_mock_ollama = MagicMock()
_original_ollama = sys.modules.get("ollama")
sys.modules["ollama"] = _mock_ollama

import file_organizer.core.backend_detector as backend_detector  # noqa: E402
from file_organizer.core.backend_detector import (  # noqa: E402
    InstalledModel,
    OllamaStatus,
    detect_ollama,
    list_installed_models,
)

# Ensure ollama is available in the backend_detector module namespace
backend_detector.ollama = _mock_ollama

# Note: We don't clean up the mock because:
# 1. Ollama has import issues in this environment (missing socksio dependency)
# 2. Other tests that need ollama will also benefit from the mock
# 3. The test suite was already running with ollama-related issues


class TestDetectOllama:
    """Tests for detect_ollama() function."""

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", False)
    def test_ollama_package_not_available(self):
        """When ollama package not installed, return not installed status."""
        result = detect_ollama()
        assert result.installed is False
        assert result.running is False
        assert result.version is None
        assert result.models_count == 0

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("file_organizer.core.backend_detector.subprocess.run")
    def test_ollama_cli_not_found(self, mock_run):
        """When ollama CLI not in PATH, return not installed."""
        mock_run.side_effect = FileNotFoundError("ollama command not found")

        result = detect_ollama()

        assert result.installed is False
        assert result.running is False

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("ollama.Client")
    @patch("file_organizer.core.backend_detector.subprocess.run")
    def test_ollama_installed_but_not_running(self, mock_run, mock_client):
        """When Ollama CLI installed but service not running."""
        mock_run.return_value = Mock(returncode=0, stdout="ollama version 0.1.0\n")
        mock_client.return_value.list.side_effect = Exception("Connection refused")

        result = detect_ollama()

        assert result.installed is True
        assert result.running is False
        assert result.version == "ollama version 0.1.0"

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("ollama.Client")
    @patch("file_organizer.core.backend_detector.subprocess.run")
    def test_ollama_installed_and_running(self, mock_run, mock_client):
        """When Ollama fully operational, return running status with model count."""
        mock_run.return_value = Mock(returncode=0, stdout="ollama version 0.1.29\n")
        mock_client.return_value.list.return_value = {
            "models": [
                {"name": "llama2:7b"},
                {"name": "qwen2.5:3b-instruct"},
            ]
        }

        result = detect_ollama()

        assert result.installed is True
        assert result.running is True
        assert result.version == "ollama version 0.1.29"
        assert result.models_count == 2

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("file_organizer.core.backend_detector.subprocess.run")
    def test_subprocess_timeout(self, mock_run):
        """When subprocess times out, return not installed."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("ollama", 5)

        result = detect_ollama()

        assert result.installed is False
        assert result.running is False

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("ollama.Client")
    @patch("file_organizer.core.backend_detector.subprocess.run")
    def test_ollama_cli_returns_error(self, mock_run, mock_client):
        """When Ollama CLI returns non-zero exit code."""
        mock_run.return_value = Mock(returncode=1, stdout="")

        result = detect_ollama()

        assert result.installed is False
        assert result.running is False

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("ollama.Client")
    @patch("file_organizer.core.backend_detector.subprocess.run")
    def test_ollama_with_list_response_format(self, mock_run, mock_client):
        """When ollama client returns list instead of dict."""
        mock_run.return_value = Mock(returncode=0, stdout="ollama version 0.1.29\n")
        # Return a list directly instead of dict with "models" key
        mock_client.return_value.list.return_value = [
            {"name": "llama2:7b"},
            {"name": "qwen2.5:3b-instruct"},
        ]

        result = detect_ollama()

        assert result.installed is True
        assert result.running is True
        assert result.models_count == 2


class TestListInstalledModels:
    """Tests for list_installed_models() function."""

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", False)
    def test_ollama_not_available(self):
        """When ollama package not available, return empty list."""
        result = list_installed_models()
        assert result == []

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("ollama.Client")
    def test_list_models_success(self, mock_client):
        """Successfully list installed models with metadata."""
        mock_client.return_value.list.return_value = {
            "models": [
                {"name": "llama2:7b", "size": 3825819519, "modified_at": "2024-01-15T10:30:00Z"},
                {
                    "name": "qwen2.5:3b-instruct",
                    "size": 1974030336,
                    "modified_at": "2024-01-20T14:45:00Z",
                },
            ]
        }

        result = list_installed_models()

        assert len(result) == 2
        assert result[0].name == "llama2:7b"
        assert result[0].size == 3825819519
        assert result[1].name == "qwen2.5:3b-instruct"

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("ollama.Client")
    def test_list_models_empty(self, mock_client):
        """When no models installed, return empty list."""
        mock_client.return_value.list.return_value = {"models": []}

        result = list_installed_models()

        assert result == []

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("file_organizer.core.backend_detector.subprocess.run")
    @patch("ollama.Client")
    def test_list_models_connection_error(self, mock_client, mock_run):
        """When Ollama service not reachable, return empty list."""
        import subprocess

        mock_client.return_value.list.side_effect = ConnectionError("Cannot connect to Ollama")
        # Mock CLI fallback to also fail
        mock_run.side_effect = subprocess.CalledProcessError(1, "ollama")

        result = list_installed_models()

        assert result == []

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("ollama.Client")
    def test_list_models_unexpected_format(self, mock_client):
        """When API returns unexpected format, handle gracefully."""
        mock_client.return_value.list.return_value = {"unexpected": "format"}

        result = list_installed_models()

        assert result == []

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("ollama.Client")
    def test_list_models_as_list_format(self, mock_client):
        """When API returns list format instead of dict."""
        mock_client.return_value.list.return_value = [
            {"name": "llama2:7b", "size": 3825819519, "modified_at": "2024-01-15T10:30:00Z"},
        ]

        result = list_installed_models()

        assert len(result) == 1
        assert result[0].name == "llama2:7b"
        assert result[0].size == 3825819519

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("file_organizer.core.backend_detector.subprocess.run")
    @patch("ollama.Client")
    def test_list_models_fallback_to_cli_json(self, mock_client, mock_run):
        """When Python client fails, fallback to CLI JSON output."""
        mock_client.return_value.list.side_effect = Exception("Client failed")

        mock_run.return_value = Mock(
            returncode=0, stdout='{"models": [{"name": "llama2:7b", "size": 3825819519}]}'
        )

        result = list_installed_models()

        assert len(result) == 1
        assert result[0].name == "llama2:7b"

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("file_organizer.core.backend_detector.subprocess.run")
    @patch("ollama.Client")
    def test_list_models_fallback_to_cli_text(self, mock_client, mock_run):
        """When JSON parsing fails, fallback to text output parser."""
        mock_client.return_value.list.side_effect = Exception("Client failed")

        # First call: JSON format fails
        # Second call: Text format succeeds
        mock_run.side_effect = [
            Mock(returncode=1, stdout=""),  # JSON command failed
            Mock(
                returncode=0,
                stdout="NAME                SIZE\nllama2:7b           4.0 GB\nqwen2.5:3b          2.0 GB\n",
            ),
        ]

        result = list_installed_models()

        assert len(result) == 2
        assert result[0].name == "llama2:7b"
        assert result[1].name == "qwen2.5:3b"

    @patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True)
    @patch("file_organizer.core.backend_detector.subprocess.run")
    @patch("ollama.Client")
    def test_list_models_cli_not_found(self, mock_client, mock_run):
        """When CLI not found, return empty list."""
        mock_client.return_value.list.side_effect = Exception("Client failed")
        mock_run.side_effect = FileNotFoundError("ollama not found")

        result = list_installed_models()

        assert result == []


class TestOllamaStatus:
    """Tests for OllamaStatus dataclass."""

    def test_create_not_installed(self):
        status = OllamaStatus(installed=False, running=False)
        assert status.installed is False
        assert status.running is False
        assert status.version is None
        assert status.models_count == 0

    def test_create_with_all_fields(self):
        status = OllamaStatus(installed=True, running=True, version="0.1.29", models_count=5)
        assert status.installed is True
        assert status.running is True
        assert status.version == "0.1.29"
        assert status.models_count == 5


class TestInstalledModel:
    """Tests for InstalledModel dataclass."""

    def test_create_minimal(self):
        model = InstalledModel(name="llama2:7b")
        assert model.name == "llama2:7b"
        assert model.size is None
        assert model.modified is None

    def test_create_with_metadata(self):
        model = InstalledModel(name="qwen2.5:3b", size=1974030336, modified="2024-01-20T14:45:00Z")
        assert model.name == "qwen2.5:3b"
        assert model.size == 1974030336
        assert model.modified == "2024-01-20T14:45:00Z"