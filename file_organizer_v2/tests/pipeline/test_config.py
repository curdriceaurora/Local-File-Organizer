"""Tests for PipelineConfig."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.pipeline.config import (
    DEFAULT_SUPPORTED_EXTENSIONS,
    PipelineConfig,
)


class TestPipelineConfigDefaults:
    """Test default configuration values."""

    def test_default_dry_run_is_true(self) -> None:
        """Pipeline defaults to dry-run mode for safety."""
        config = PipelineConfig()
        assert config.dry_run is True

    def test_default_auto_organize_is_false(self) -> None:
        """Pipeline defaults to not auto-organizing for safety."""
        config = PipelineConfig()
        assert config.auto_organize is False

    def test_default_output_directory(self) -> None:
        """Default output directory is set."""
        config = PipelineConfig()
        assert config.output_directory == Path("organized_files")

    def test_default_max_concurrent(self) -> None:
        """Default max_concurrent is 4."""
        config = PipelineConfig()
        assert config.max_concurrent == 4

    def test_default_watch_config_is_none(self) -> None:
        """Watch config is None by default (batch mode)."""
        config = PipelineConfig()
        assert config.watch_config is None

    def test_default_supported_extensions_is_none(self) -> None:
        """Supported extensions default to None (use global defaults)."""
        config = PipelineConfig()
        assert config.supported_extensions is None

    def test_default_notification_callback_is_none(self) -> None:
        """Notification callback defaults to None."""
        config = PipelineConfig()
        assert config.notification_callback is None


class TestPipelineConfigValidation:
    """Test configuration validation logic."""

    def test_max_concurrent_must_be_positive(self) -> None:
        """max_concurrent below 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_concurrent must be at least 1"):
            PipelineConfig(max_concurrent=0)

    def test_max_concurrent_negative_raises(self) -> None:
        """Negative max_concurrent raises ValueError."""
        with pytest.raises(ValueError, match="max_concurrent must be at least 1"):
            PipelineConfig(max_concurrent=-1)

    def test_output_directory_normalized_to_path(self) -> None:
        """Output directory is converted to Path."""
        config = PipelineConfig(output_directory=Path("/tmp/test"))
        assert isinstance(config.output_directory, Path)
        assert config.output_directory == Path("/tmp/test")

    def test_extensions_normalized_with_dots(self) -> None:
        """Extensions without leading dots get them added."""
        config = PipelineConfig(supported_extensions={"txt", "pdf", ".jpg"})
        assert ".txt" in config.supported_extensions
        assert ".pdf" in config.supported_extensions
        assert ".jpg" in config.supported_extensions


class TestPipelineConfigProperties:
    """Test computed properties."""

    def test_effective_extensions_with_defaults(self) -> None:
        """effective_extensions returns defaults when none configured."""
        config = PipelineConfig()
        assert config.effective_extensions == DEFAULT_SUPPORTED_EXTENSIONS

    def test_effective_extensions_with_custom(self) -> None:
        """effective_extensions returns custom set when configured."""
        config = PipelineConfig(supported_extensions={".txt", ".pdf"})
        assert config.effective_extensions == frozenset({".txt", ".pdf"})

    def test_should_move_files_dry_run(self) -> None:
        """should_move_files is False when dry_run is True."""
        config = PipelineConfig(dry_run=True, auto_organize=True)
        assert config.should_move_files is False

    def test_should_move_files_no_auto_organize(self) -> None:
        """should_move_files is False when auto_organize is False."""
        config = PipelineConfig(dry_run=False, auto_organize=False)
        assert config.should_move_files is False

    def test_should_move_files_enabled(self) -> None:
        """should_move_files is True only when both flags allow it."""
        config = PipelineConfig(dry_run=False, auto_organize=True)
        assert config.should_move_files is True

    def test_is_supported_known_extension(self) -> None:
        """Known extensions are supported."""
        config = PipelineConfig()
        assert config.is_supported(Path("document.pdf")) is True
        assert config.is_supported(Path("image.jpg")) is True
        assert config.is_supported(Path("video.mp4")) is True

    def test_is_supported_unknown_extension(self) -> None:
        """Unknown extensions are not supported."""
        config = PipelineConfig()
        assert config.is_supported(Path("archive.zip")) is False
        assert config.is_supported(Path("binary.exe")) is False

    def test_is_supported_custom_extensions(self) -> None:
        """Custom extensions override defaults for is_supported."""
        config = PipelineConfig(supported_extensions={".custom"})
        assert config.is_supported(Path("file.custom")) is True
        assert config.is_supported(Path("document.pdf")) is False

    def test_is_supported_case_insensitive(self) -> None:
        """Extension matching is case-insensitive."""
        config = PipelineConfig()
        assert config.is_supported(Path("DOCUMENT.PDF")) is True
        assert config.is_supported(Path("image.JPG")) is True
