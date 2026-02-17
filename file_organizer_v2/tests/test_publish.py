"""Tests for publishing helpers.

Covers package building, validation, publishing configuration,
and distribution file listing. Uses mocked subprocess to avoid
actual PyPI operations.
"""

from __future__ import annotations

# Import the publish module by path since it's in scripts/
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
_publish_spec = importlib.util.spec_from_file_location("publish", _SCRIPTS_DIR / "publish.py")
assert _publish_spec is not None
assert _publish_spec.loader is not None
publish_mod = importlib.util.module_from_spec(_publish_spec)
sys.modules["publish"] = publish_mod
_publish_spec.loader.exec_module(publish_mod)

PublishConfig = publish_mod.PublishConfig
build_package = publish_mod.build_package
check_package = publish_mod.check_package
publish_pypi = publish_mod.publish_pypi
get_dist_files = publish_mod.get_dist_files


class TestPublishConfig:
    """Tests for PublishConfig dataclass."""

    def test_default_config_values(self) -> None:
        """Default config has standard PyPI URLs."""
        config = PublishConfig()
        # codeql[py/incomplete-url-substring-sanitization] - Test assertion verifying expected URL pattern, not sanitizing user input
        assert "pypi.org" in config.pypi_url
        # codeql[py/incomplete-url-substring-sanitization] - Test assertion verifying expected URL pattern, not sanitizing user input
        assert "test.pypi.org" in config.test_pypi_url

    def test_default_token_env_var(self) -> None:
        """Default config uses PYPI_API_TOKEN env var."""
        config = PublishConfig()
        assert config.token_env_var == "PYPI_API_TOKEN"

    def test_default_test_token_env_var(self) -> None:
        """Default config uses TEST_PYPI_API_TOKEN for test uploads."""
        config = PublishConfig()
        assert config.test_token_env_var == "TEST_PYPI_API_TOKEN"

    def test_custom_config(self) -> None:
        """Custom config overrides default values."""
        config = PublishConfig(
            pypi_url="https://custom.pypi.example.com/",
            token_env_var="CUSTOM_TOKEN",
        )
        assert config.pypi_url == "https://custom.pypi.example.com/"
        assert config.token_env_var == "CUSTOM_TOKEN"

    def test_config_is_frozen(self) -> None:
        """PublishConfig instances are immutable."""
        config = PublishConfig()
        with pytest.raises(AttributeError):
            config.pypi_url = "https://other.url/"  # type: ignore[misc]

    def test_default_dist_dir(self) -> None:
        """Default config uses 'dist' directory name."""
        config = PublishConfig()
        assert config.dist_dir == "dist"


class TestBuildPackage:
    """Tests for build_package function."""

    @patch("publish._run_command")
    def test_build_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Successful build returns dist path."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "file_organizer-2.0.0.tar.gz").touch()
        (dist / "file_organizer-2.0.0-py3-none-any.whl").touch()

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch("publish._V2_ROOT", tmp_path):
            result = build_package(clean=False)
            assert result == dist

    @patch("publish._run_command")
    def test_build_failure_raises(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Failed build raises RuntimeError."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="Build failed",
            stderr="error details",
        )

        with patch("publish._V2_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="Package build failed"):
                build_package(clean=False)

    @patch("publish._run_command")
    def test_build_no_dist_raises(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Build that produces no dist/ raises RuntimeError."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch("publish._V2_ROOT", tmp_path):
            with pytest.raises(RuntimeError, match="no dist"):
                build_package(clean=False)

    @patch("publish._run_command")
    def test_build_clean_removes_old_dist(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Clean build removes existing dist/ directory."""
        dist = tmp_path / "dist"
        dist.mkdir()
        old_file = dist / "old_package-1.0.0.tar.gz"
        old_file.touch()

        def build_side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            # Simulate build creating new files
            new_dist = tmp_path / "dist"
            new_dist.mkdir(exist_ok=True)
            (new_dist / "file_organizer-2.0.0.tar.gz").touch()
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = build_side_effect

        with patch("publish._V2_ROOT", tmp_path):
            build_package(clean=True)
            # old_file should no longer exist (was cleaned)
            assert not old_file.exists()


class TestCheckPackage:
    """Tests for check_package function."""

    def test_check_nonexistent_dir_raises(self) -> None:
        """Non-existent directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Distribution directory not found"):
            check_package(Path("/nonexistent/dist"))

    def test_check_empty_dir_raises(self, tmp_path: Path) -> None:
        """Empty dist directory raises FileNotFoundError."""
        dist = tmp_path / "dist"
        dist.mkdir()
        with pytest.raises(FileNotFoundError, match="No distribution files"):
            check_package(dist)

    @patch("publish._run_command")
    def test_check_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Successful twine check returns True."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "package-1.0.0.tar.gz").touch()

        mock_run.return_value = MagicMock(returncode=0)
        assert check_package(dist) is True

    @patch("publish._run_command")
    def test_check_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Failed twine check returns False."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "package-1.0.0.tar.gz").touch()

        mock_run.return_value = MagicMock(returncode=1)
        assert check_package(dist) is False


class TestPublishPypi:
    """Tests for publish_pypi function."""

    def test_publish_nonexistent_dir_raises(self) -> None:
        """Non-existent dist directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            publish_pypi(Path("/nonexistent/dist"))

    @patch("publish._run_command")
    def test_publish_test_pypi_uses_test_url(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Test mode uses Test PyPI URL."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "package-1.0.0.tar.gz").touch()

        mock_run.return_value = MagicMock(returncode=0)
        publish_pypi(dist, test=True)

        call_args = mock_run.call_args[0][0]
        # codeql[py/incomplete-url-substring-sanitization] - Test assertion verifying expected URL pattern, not sanitizing user input
        assert any("test.pypi.org" in str(arg) for arg in call_args)

    @patch("publish._run_command")
    def test_publish_production_uses_prod_url(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Production mode uses production PyPI URL."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "package-1.0.0.tar.gz").touch()

        mock_run.return_value = MagicMock(returncode=0)
        publish_pypi(dist, test=False)

        call_args = mock_run.call_args[0][0]
        # codeql[py/incomplete-url-substring-sanitization] - Test assertion verifying expected URL pattern, not sanitizing user input
        assert any("upload.pypi.org" in str(arg) for arg in call_args)

    @patch("publish._run_command")
    def test_publish_success_returns_true(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Successful publish returns True."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "package-1.0.0.tar.gz").touch()

        mock_run.return_value = MagicMock(returncode=0)
        assert publish_pypi(dist) is True

    @patch("publish._run_command")
    def test_publish_failure_returns_false(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Failed publish returns False."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "package-1.0.0.tar.gz").touch()

        mock_run.return_value = MagicMock(returncode=1)
        assert publish_pypi(dist) is False

    @patch("publish._run_command")
    def test_publish_custom_config(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Custom config overrides default URLs."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "package-1.0.0.tar.gz").touch()

        config = PublishConfig(
            pypi_url="https://custom.pypi.example.com/",
            test_pypi_url="https://test.custom.pypi.example.com/",
        )

        mock_run.return_value = MagicMock(returncode=0)
        publish_pypi(dist, test=True, config=config)

        call_args = mock_run.call_args[0][0]
        assert any("test.custom.pypi" in str(arg) for arg in call_args)


class TestGetDistFiles:
    """Tests for get_dist_files function."""

    def test_nonexistent_dir_returns_empty(self) -> None:
        """Non-existent directory returns empty list."""
        result = get_dist_files(Path("/nonexistent/dist"))
        assert result == []

    def test_lists_tar_and_whl_files(self, tmp_path: Path) -> None:
        """Lists .tar.gz and .whl files."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "pkg-1.0.0.tar.gz").touch()
        (dist / "pkg-1.0.0-py3-none-any.whl").touch()
        (dist / "README.txt").touch()  # Should be excluded

        files = get_dist_files(dist)
        names = [f.name for f in files]
        assert "pkg-1.0.0.tar.gz" in names
        assert "pkg-1.0.0-py3-none-any.whl" in names
        assert "README.txt" not in names

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        """Empty directory returns empty list."""
        dist = tmp_path / "dist"
        dist.mkdir()
        assert get_dist_files(dist) == []
