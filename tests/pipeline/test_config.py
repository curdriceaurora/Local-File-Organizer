"""Tests for PipelineConfig."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.pipeline.config import (
    DEFAULT_SUPPORTED_EXTENSIONS,
    PipelineConfig,
)


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
class TestPipelineConfigEdgeCases:
    """Additional edge case tests for PipelineConfig."""

    def test_max_concurrent_boundary_value_one(self) -> None:
        """max_concurrent=1 is the minimum valid value."""
        config = PipelineConfig(max_concurrent=1)
        assert config.max_concurrent == 1

    def test_max_concurrent_large_value(self) -> None:
        """Large max_concurrent values are accepted."""
        config = PipelineConfig(max_concurrent=1000)
        assert config.max_concurrent == 1000

    def test_should_move_files_both_false(self) -> None:
        """should_move_files is False when both dry_run=True and auto_organize=False."""
        config = PipelineConfig(dry_run=True, auto_organize=False)
        assert config.should_move_files is False

    def test_notification_callback_stored(self) -> None:
        """notification_callback is stored as provided."""

        def callback(path, success):
            return None

        config = PipelineConfig(notification_callback=callback)
        assert config.notification_callback is callback

    def test_output_directory_string_coercion(self) -> None:
        """String output_directory is coerced to Path."""
        config = PipelineConfig(output_directory="/some/path")
        assert isinstance(config.output_directory, Path)
        assert config.output_directory == Path("/some/path")

    def test_empty_supported_extensions(self) -> None:
        """Empty set of supported extensions means nothing is supported."""
        config = PipelineConfig(supported_extensions=set())
        assert config.effective_extensions == frozenset()
        assert config.is_supported(Path("document.pdf")) is False
        assert config.is_supported(Path("image.jpg")) is False

    def test_is_supported_no_extension(self) -> None:
        """Files without extensions are not supported."""
        config = PipelineConfig()
        assert config.is_supported(Path("Makefile")) is False
        assert config.is_supported(Path("README")) is False

    def test_effective_extensions_returns_frozenset(self) -> None:
        """effective_extensions always returns a frozenset (immutable)."""
        config = PipelineConfig()
        result = config.effective_extensions
        assert isinstance(result, frozenset)

        config2 = PipelineConfig(supported_extensions={".txt"})
        result2 = config2.effective_extensions
        assert isinstance(result2, frozenset)

    def test_supported_extensions_all_normalized(self) -> None:
        """All extensions in supported_extensions get dot-prefixed."""
        config = PipelineConfig(supported_extensions={"txt", "pdf", "jpg"})
        for ext in config.supported_extensions:
            assert ext.startswith("."), f"Extension {ext!r} missing leading dot"

    def test_default_supported_extensions_constant(self) -> None:
        """DEFAULT_SUPPORTED_EXTENSIONS contains expected categories."""
        from file_organizer.pipeline.config import DEFAULT_SUPPORTED_EXTENSIONS

        # Text
        assert ".txt" in DEFAULT_SUPPORTED_EXTENSIONS
        assert ".pdf" in DEFAULT_SUPPORTED_EXTENSIONS
        # Image
        assert ".jpg" in DEFAULT_SUPPORTED_EXTENSIONS
        assert ".png" in DEFAULT_SUPPORTED_EXTENSIONS
        # Video
        assert ".mp4" in DEFAULT_SUPPORTED_EXTENSIONS
        # Audio
        assert ".mp3" in DEFAULT_SUPPORTED_EXTENSIONS
        # CAD
        assert ".dwg" in DEFAULT_SUPPORTED_EXTENSIONS

    def test_watch_config_can_be_set(self) -> None:
        """watch_config accepts arbitrary values (type-checked at usage)."""
        # We use a mock since WatcherConfig is only imported for TYPE_CHECKING
        from unittest.mock import MagicMock

        mock_watcher = MagicMock()
        config = PipelineConfig(watch_config=mock_watcher)
        assert config.watch_config is mock_watcher

    def test_multiple_configs_independent(self) -> None:
        """Multiple PipelineConfig instances don't share mutable state."""
        c1 = PipelineConfig(supported_extensions={".txt"})
        c2 = PipelineConfig(supported_extensions={".pdf"})
        assert c1.supported_extensions != c2.supported_extensions
        assert ".txt" in c1.supported_extensions
        assert ".pdf" in c2.supported_extensions
