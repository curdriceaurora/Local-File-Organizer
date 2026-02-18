"""Tests for FileRouter."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.pipeline.router import FileRouter, ProcessorType


class TestProcessorTypeEnum:
    """Test the ProcessorType enum values."""

    def test_text_value(self) -> None:
        assert ProcessorType.TEXT == "text"

    def test_image_value(self) -> None:
        assert ProcessorType.IMAGE == "image"

    def test_video_value(self) -> None:
        assert ProcessorType.VIDEO == "video"

    def test_audio_value(self) -> None:
        assert ProcessorType.AUDIO == "audio"

    def test_unknown_value(self) -> None:
        assert ProcessorType.UNKNOWN == "unknown"


class TestFileRouterExtensionRouting:
    """Test extension-based file routing."""

    @pytest.fixture()
    def router(self) -> FileRouter:
        return FileRouter()

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("document.txt", ProcessorType.TEXT),
            ("notes.md", ProcessorType.TEXT),
            ("report.pdf", ProcessorType.TEXT),
            ("data.csv", ProcessorType.TEXT),
            ("book.epub", ProcessorType.TEXT),
            ("spreadsheet.xlsx", ProcessorType.TEXT),
            ("presentation.pptx", ProcessorType.TEXT),
            ("blueprint.dwg", ProcessorType.TEXT),
            ("model.step", ProcessorType.TEXT),
        ],
    )
    def test_text_extensions(
        self, router: FileRouter, filename: str, expected: ProcessorType
    ) -> None:
        """Text file extensions route to TEXT processor."""
        assert router.route(Path(filename)) == expected

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("photo.jpg", ProcessorType.IMAGE),
            ("photo.jpeg", ProcessorType.IMAGE),
            ("screenshot.png", ProcessorType.IMAGE),
            ("animation.gif", ProcessorType.IMAGE),
            ("scan.bmp", ProcessorType.IMAGE),
            ("photo.tiff", ProcessorType.IMAGE),
        ],
    )
    def test_image_extensions(
        self, router: FileRouter, filename: str, expected: ProcessorType
    ) -> None:
        """Image file extensions route to IMAGE processor."""
        assert router.route(Path(filename)) == expected

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("movie.mp4", ProcessorType.VIDEO),
            ("clip.avi", ProcessorType.VIDEO),
            ("recording.mkv", ProcessorType.VIDEO),
            ("video.mov", ProcessorType.VIDEO),
            ("clip.wmv", ProcessorType.VIDEO),
        ],
    )
    def test_video_extensions(
        self, router: FileRouter, filename: str, expected: ProcessorType
    ) -> None:
        """Video file extensions route to VIDEO processor."""
        assert router.route(Path(filename)) == expected

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("song.mp3", ProcessorType.AUDIO),
            ("recording.wav", ProcessorType.AUDIO),
            ("track.flac", ProcessorType.AUDIO),
            ("podcast.m4a", ProcessorType.AUDIO),
            ("music.ogg", ProcessorType.AUDIO),
        ],
    )
    def test_audio_extensions(
        self, router: FileRouter, filename: str, expected: ProcessorType
    ) -> None:
        """Audio file extensions route to AUDIO processor."""
        assert router.route(Path(filename)) == expected

    def test_unknown_extension(self, router: FileRouter) -> None:
        """Unrecognized extensions route to UNKNOWN."""
        assert router.route(Path("archive.zip")) == ProcessorType.UNKNOWN
        assert router.route(Path("binary.exe")) == ProcessorType.UNKNOWN
        assert router.route(Path("data.json")) == ProcessorType.UNKNOWN

    def test_case_insensitive_routing(self, router: FileRouter) -> None:
        """Extension routing is case-insensitive."""
        assert router.route(Path("DOCUMENT.PDF")) == ProcessorType.TEXT
        assert router.route(Path("photo.JPG")) == ProcessorType.IMAGE
        assert router.route(Path("video.MP4")) == ProcessorType.VIDEO

    def test_no_extension(self, router: FileRouter) -> None:
        """Files without extensions route to UNKNOWN."""
        assert router.route(Path("Makefile")) == ProcessorType.UNKNOWN
        assert router.route(Path("README")) == ProcessorType.UNKNOWN


class TestFileRouterExtensionManagement:
    """Test adding and removing extension mappings."""

    @pytest.fixture()
    def router(self) -> FileRouter:
        return FileRouter()

    def test_add_extension(self, router: FileRouter) -> None:
        """Adding a new extension creates a mapping."""
        router.add_extension(".custom", ProcessorType.TEXT)
        assert router.route(Path("file.custom")) == ProcessorType.TEXT

    def test_add_extension_without_dot(self, router: FileRouter) -> None:
        """Extensions without leading dot are normalized."""
        router.add_extension("xyz", ProcessorType.IMAGE)
        assert router.route(Path("file.xyz")) == ProcessorType.IMAGE

    def test_override_extension(self, router: FileRouter) -> None:
        """Overriding an existing extension changes the mapping."""
        assert router.route(Path("file.txt")) == ProcessorType.TEXT
        router.add_extension(".txt", ProcessorType.IMAGE)
        assert router.route(Path("file.txt")) == ProcessorType.IMAGE

    def test_remove_extension(self, router: FileRouter) -> None:
        """Removing an extension makes it route to UNKNOWN."""
        assert router.route(Path("file.txt")) == ProcessorType.TEXT
        router.remove_extension(".txt")
        assert router.route(Path("file.txt")) == ProcessorType.UNKNOWN

    def test_remove_nonexistent_extension_raises(self, router: FileRouter) -> None:
        """Removing a non-existent extension raises KeyError."""
        with pytest.raises(KeyError):
            router.remove_extension(".nonexistent")

    def test_get_extension_map_returns_copy(self, router: FileRouter) -> None:
        """get_extension_map returns a copy, not the internal dict."""
        ext_map = router.get_extension_map()
        ext_map[".custom"] = ProcessorType.TEXT
        assert ".custom" not in router.get_extension_map()


class TestFileRouterCustomRules:
    """Test custom routing rules."""

    @pytest.fixture()
    def router(self) -> FileRouter:
        return FileRouter()

    def test_custom_rule_takes_precedence(self, router: FileRouter) -> None:
        """Custom rules are checked before extension mapping."""
        # .txt normally routes to TEXT
        router.add_custom_rule(
            lambda p: p.name.startswith("image_"),
            ProcessorType.IMAGE,
        )
        # Custom rule overrides extension for matching files
        assert router.route(Path("image_data.txt")) == ProcessorType.IMAGE
        # Non-matching files still use extension routing
        assert router.route(Path("normal.txt")) == ProcessorType.TEXT

    def test_first_matching_rule_wins(self, router: FileRouter) -> None:
        """When multiple rules match, the first one wins."""
        router.add_custom_rule(lambda p: True, ProcessorType.AUDIO)
        router.add_custom_rule(lambda p: True, ProcessorType.VIDEO)
        assert router.route(Path("anything.xyz")) == ProcessorType.AUDIO

    def test_custom_rule_error_is_skipped(self, router: FileRouter) -> None:
        """Custom rules that raise exceptions are skipped."""

        def bad_rule(path: Path) -> bool:
            raise ValueError("Rule error")

        router.add_custom_rule(bad_rule, ProcessorType.AUDIO)
        # Should fall through to extension routing despite error
        assert router.route(Path("document.txt")) == ProcessorType.TEXT

    def test_clear_custom_rules(self, router: FileRouter) -> None:
        """Clearing custom rules removes all of them."""
        router.add_custom_rule(lambda p: True, ProcessorType.AUDIO)
        assert router.custom_rule_count == 1
        router.clear_custom_rules()
        assert router.custom_rule_count == 0
        # Falls back to extension routing
        assert router.route(Path("document.txt")) == ProcessorType.TEXT

    def test_custom_rule_count(self, router: FileRouter) -> None:
        """custom_rule_count tracks the number of rules."""
        assert router.custom_rule_count == 0
        router.add_custom_rule(lambda p: False, ProcessorType.TEXT)
        assert router.custom_rule_count == 1
        router.add_custom_rule(lambda p: False, ProcessorType.IMAGE)
        assert router.custom_rule_count == 2

    def test_custom_rule_with_path_matching(self, router: FileRouter) -> None:
        """Custom rules can match on path components."""
        router.add_custom_rule(
            lambda p: "screenshots" in p.parts,
            ProcessorType.IMAGE,
        )
        assert router.route(Path("screenshots/data.csv")) == ProcessorType.IMAGE
        assert router.route(Path("documents/data.csv")) == ProcessorType.TEXT
