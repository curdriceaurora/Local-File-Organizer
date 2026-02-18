"""Tests for Docker Compose service scaling wrapper."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.deploy.compose_scaler import ComposeScaler


class TestComposeScalerInit:
    """Tests for ComposeScaler initialisation."""

    def test_default_compose_file(self) -> None:
        """Test that the default compose file is docker-compose.yml."""
        scaler = ComposeScaler()
        assert scaler._compose_file == "docker-compose.yml"

    def test_custom_compose_file(self) -> None:
        """Test using a custom compose file path."""
        scaler = ComposeScaler(compose_file="docker-compose.prod.yml")
        assert scaler._compose_file == "docker-compose.prod.yml"

    def test_project_name(self) -> None:
        """Test setting a project name."""
        scaler = ComposeScaler(project_name="myproject")
        assert scaler._project_name == "myproject"


class TestComposeScalerScaleService:
    """Tests for the scale_service method."""

    @patch.object(ComposeScaler, "_run_command", return_value=True)
    def test_scale_service_success(self, mock_run: MagicMock) -> None:
        """Test successful service scaling."""
        scaler = ComposeScaler()
        result = scaler.scale_service("file-organizer", 3)

        assert result is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "docker-compose" in cmd
        assert "file-organizer=3" in " ".join(cmd)

    @patch.object(ComposeScaler, "_run_command", return_value=False)
    def test_scale_service_failure(self, mock_run: MagicMock) -> None:
        """Test that scale_service returns False on command failure."""
        scaler = ComposeScaler()
        result = scaler.scale_service("file-organizer", 3)
        assert result is False

    def test_scale_service_negative_replicas(self) -> None:
        """Test that negative replicas raises ValueError."""
        scaler = ComposeScaler()
        with pytest.raises(ValueError, match="replicas must be >= 0"):
            scaler.scale_service("file-organizer", -1)

    @patch.object(ComposeScaler, "_run_command", return_value=True)
    def test_scale_service_zero_replicas(self, mock_run: MagicMock) -> None:
        """Test scaling to zero replicas (shutdown)."""
        scaler = ComposeScaler()
        result = scaler.scale_service("file-organizer", 0)
        assert result is True

    @patch.object(ComposeScaler, "_run_command", return_value=True)
    def test_scale_service_with_project_name(self, mock_run: MagicMock) -> None:
        """Test that project name is included in the command."""
        scaler = ComposeScaler(project_name="myproj")
        scaler.scale_service("web", 2)

        cmd = mock_run.call_args[0][0]
        assert "-p" in cmd
        assert "myproj" in cmd


class TestComposeScalerGetServiceCount:
    """Tests for the get_service_count method."""

    @patch.object(ComposeScaler, "_run_command_output")
    def test_get_service_count_multiple(self, mock_output: MagicMock) -> None:
        """Test counting multiple running containers."""
        # Simulate 3 containers, each producing one JSON line
        mock_output.return_value = (
            '{"ID":"abc","Service":"web"}\n'
            '{"ID":"def","Service":"web"}\n'
            '{"ID":"ghi","Service":"web"}\n'
        )
        scaler = ComposeScaler()
        count = scaler.get_service_count("web")
        assert count == 3

    @patch.object(ComposeScaler, "_run_command_output", return_value=None)
    def test_get_service_count_on_failure(self, mock_output: MagicMock) -> None:
        """Test that 0 is returned when the command fails."""
        scaler = ComposeScaler()
        count = scaler.get_service_count("web")
        assert count == 0

    @patch.object(ComposeScaler, "_run_command_output", return_value="")
    def test_get_service_count_empty(self, mock_output: MagicMock) -> None:
        """Test that 0 is returned for no running containers."""
        scaler = ComposeScaler()
        count = scaler.get_service_count("web")
        assert count == 0


class TestComposeScalerSubprocess:
    """Tests for the internal subprocess execution methods."""

    @patch("subprocess.run")
    def test_run_command_success(self, mock_run: MagicMock) -> None:
        """Test _run_command returns True on success."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        scaler = ComposeScaler()
        result = scaler._run_command(["docker-compose", "up"])
        assert result is True

    @patch("subprocess.run")
    def test_run_command_nonzero_exit(self, mock_run: MagicMock) -> None:
        """Test _run_command returns False on non-zero exit."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        scaler = ComposeScaler()
        result = scaler._run_command(["docker-compose", "up"])
        assert result is False

    @patch(
        "subprocess.run",
        side_effect=FileNotFoundError("docker-compose not found"),
    )
    def test_run_command_file_not_found(self, mock_run: MagicMock) -> None:
        """Test _run_command handles missing docker-compose binary."""
        scaler = ComposeScaler()
        result = scaler._run_command(["docker-compose", "up"])
        assert result is False

    @patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="docker-compose", timeout=120),
    )
    def test_run_command_timeout(self, mock_run: MagicMock) -> None:
        """Test _run_command handles timeout."""
        scaler = ComposeScaler()
        result = scaler._run_command(["docker-compose", "up"])
        assert result is False

    @patch("subprocess.run")
    def test_run_command_output_success(self, mock_run: MagicMock) -> None:
        """Test _run_command_output returns stdout on success."""
        mock_run.return_value = MagicMock(returncode=0, stdout="output data\n", stderr="")
        scaler = ComposeScaler()
        result = scaler._run_command_output(["docker-compose", "ps"])
        assert result == "output data\n"

    @patch("subprocess.run")
    def test_run_command_output_failure(self, mock_run: MagicMock) -> None:
        """Test _run_command_output returns None on failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="err")
        scaler = ComposeScaler()
        result = scaler._run_command_output(["docker-compose", "ps"])
        assert result is None
