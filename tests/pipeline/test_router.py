"""Tests for FileRouter."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.pipeline.router import FileRouter, ProcessorType

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.smoke]


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


class TestFileRouterEdgeCases:
    """Additional edge case tests for FileRouter."""

    @pytest.fixture()
    def router(self) -> FileRouter:
        return FileRouter()

    def test_remove_extension_without_dot(self, router: FileRouter) -> None:
        """remove_extension normalizes extensions without leading dot."""
        assert router.route(Path("file.txt")) == ProcessorType.TEXT
        router.remove_extension("txt")
        assert router.route(Path("file.txt")) == ProcessorType.UNKNOWN

    def test_add_extension_case_normalized(self, router: FileRouter) -> None:
        """add_extension lowercases extensions."""
        router.add_extension(".FOO", ProcessorType.VIDEO)
        assert router.route(Path("file.foo")) == ProcessorType.VIDEO
        assert router.route(Path("file.FOO")) == ProcessorType.VIDEO

    def test_compound_extension_only_last_part_used(self, router: FileRouter) -> None:
        """Path.suffix returns only the last dot-segment."""
        # .tar.gz has suffix .gz, which is unknown by default
        assert router.route(Path("archive.tar.gz")) == ProcessorType.UNKNOWN

    def test_hidden_file_with_extension(self, router: FileRouter) -> None:
        """Hidden files (dotfiles) with known extensions are routed correctly."""
        assert router.route(Path(".hidden.txt")) == ProcessorType.TEXT

    def test_custom_rule_false_falls_through(self, router: FileRouter) -> None:
        """Custom rules returning False fall through to the next rule or extensions."""
        router.add_custom_rule(lambda p: False, ProcessorType.AUDIO)
        router.add_custom_rule(lambda p: p.suffix == ".txt", ProcessorType.VIDEO)
        # First rule returns False, second matches
        assert router.route(Path("file.txt")) == ProcessorType.VIDEO
        # Neither custom rule matches .pdf
        assert router.route(Path("file.pdf")) == ProcessorType.TEXT

    def test_custom_rule_error_continues_to_next_rule(self, router: FileRouter) -> None:
        """When a custom rule errors, the next custom rule is still checked."""

        def bad_rule(path: Path) -> bool:
            raise RuntimeError("broken")

        router.add_custom_rule(bad_rule, ProcessorType.AUDIO)
        router.add_custom_rule(lambda p: True, ProcessorType.VIDEO)
        # bad_rule errors out, second rule matches
        assert router.route(Path("file.txt")) == ProcessorType.VIDEO

    def test_get_extension_map_contains_all_defaults(self, router: FileRouter) -> None:
        """Extension map includes all default extensions."""
        ext_map = router.get_extension_map()
        # Spot-check a few from each category
        assert ext_map[".txt"] == ProcessorType.TEXT
        assert ext_map[".jpg"] == ProcessorType.IMAGE
        assert ext_map[".mp4"] == ProcessorType.VIDEO
        assert ext_map[".mp3"] == ProcessorType.AUDIO

    def test_processor_type_is_str_enum(self) -> None:
        """ProcessorType values are strings usable in string contexts."""
        assert f"type={ProcessorType.TEXT}" == "type=text"
        assert str(ProcessorType.IMAGE) == "image"

    def test_empty_filename(self, router: FileRouter) -> None:
        """Empty-string path has no suffix, routes to UNKNOWN."""
        assert router.route(Path("")) == ProcessorType.UNKNOWN

    def test_dotfile_without_extension(self, router: FileRouter) -> None:
        """A dotfile like '.txt' has no suffix on Python 3.14, routes to UNKNOWN."""
        # Path(".txt").suffix is "" on Python 3.14 (dotfile, no extension)
        assert router.route(Path(".txt")) == ProcessorType.UNKNOWN

    def test_add_then_remove_custom_extension(self, router: FileRouter) -> None:
        """Adding then removing a custom extension restores UNKNOWN routing."""
        router.add_extension(".xyz", ProcessorType.AUDIO)
        assert router.route(Path("file.xyz")) == ProcessorType.AUDIO
        router.remove_extension(".xyz")
        assert router.route(Path("file.xyz")) == ProcessorType.UNKNOWN

    def test_multiple_routers_are_independent(self) -> None:
        """Multiple FileRouter instances don't share state."""
        r1 = FileRouter()
        r2 = FileRouter()
        r1.add_extension(".custom", ProcessorType.TEXT)
        r1.add_custom_rule(lambda p: True, ProcessorType.AUDIO)
        # r2 should be unaffected
        assert r2.route(Path("file.custom")) == ProcessorType.UNKNOWN
        assert r2.custom_rule_count == 0
