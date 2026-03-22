"""Integration tests for ComparisonViewer in deduplication viewer.

These tests exercise end-to-end workflows through ComparisonViewer using
real image files (created via PIL) and minimal mocking. They focus on:
- Full show_comparison → action → review workflow
- batch_review with auto-select and manual paths
- _generate_ascii_preview with the getdata() fallback branch (line 326)
- _auto_select_best ranking across real images
- _display_review_summary with real file stats
- interactive_select with various selection inputs
- display_metadata for both valid and invalid paths
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image as PILImage
from rich.console import Console

from file_organizer.services.deduplication.viewer import (
    ComparisonViewer,
    ImageMetadata,
    UserAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png(tmp_path: Path, name: str, size: tuple[int, int] = (100, 100)) -> Path:
    """Create a real PNG image file under tmp_path and return its path."""
    p = tmp_path / name
    PILImage.new("RGB", size, color=(128, 64, 32)).save(p, format="PNG")
    return p


def _make_jpeg(tmp_path: Path, name: str, size: tuple[int, int] = (100, 100)) -> Path:
    """Create a real JPEG image file under tmp_path and return its path."""
    p = tmp_path / name
    PILImage.new("RGB", size, color=(64, 128, 32)).save(p, format="JPEG")
    return p


def _silent_console() -> Console:
    """Return a Console instance that writes to a MagicMock (captures output silently)."""
    return Console(file=MagicMock(), highlight=False)


def _written(viewer: ComparisonViewer) -> str:
    """Return all text written to the viewer's mock console file."""
    return "".join(c.args[0] for c in viewer.console.file.write.call_args_list if c.args)


# ---------------------------------------------------------------------------
# TestShowComparisonIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestShowComparisonIntegration:
    """End-to-end show_comparison flow with real image files."""

    def test_empty_images_returns_skipped_review(self, tmp_path: Path) -> None:
        """show_comparison with an empty list returns a skipped ReviewResult."""
        viewer = ComparisonViewer(console=_silent_console())
        result = viewer.show_comparison([])
        assert result.skipped is True
        assert result.files_to_keep == []
        assert result.files_to_delete == []

    def test_auto_select_action_keeps_best_real_image(self, tmp_path: Path) -> None:
        """Auto-select action keeps the highest-quality image and marks the rest for deletion."""
        large = _make_png(tmp_path, "large.png", (800, 600))
        small = _make_png(tmp_path, "small.png", (200, 150))
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="a"):
            result = viewer.show_comparison([large, small])

        assert large in result.files_to_keep
        assert small in result.files_to_delete
        assert result.skipped is False

    def test_skip_action_returns_skipped(self, tmp_path: Path) -> None:
        """Pressing 's' in show_comparison returns a skipped ReviewResult."""
        img = _make_png(tmp_path, "img.png")
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="s"):
            result = viewer.show_comparison([img])

        assert result.skipped is True
        assert result.files_to_keep == []
        assert result.files_to_delete == []

    def test_keep_all_action_keeps_every_image(self, tmp_path: Path) -> None:
        """Pressing 'k' keeps all images and returns no files to delete."""
        imgs = [_make_png(tmp_path, f"img{i}.png", (50 * (i + 1), 50)) for i in range(3)]
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="k"):
            result = viewer.show_comparison(imgs)

        assert len(result.files_to_keep) == 3
        assert result.files_to_delete == []
        assert result.skipped is False

    def test_quit_action_returns_skipped(self, tmp_path: Path) -> None:
        """Pressing 'q' in show_comparison returns a skipped ReviewResult."""
        img = _make_png(tmp_path, "img.png")
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="q"):
            result = viewer.show_comparison([img])

        assert result.skipped is True

    def test_keep_specific_image_by_number(self, tmp_path: Path) -> None:
        """Selecting image 2 by number keeps it and marks image 1 for deletion."""
        img1 = _make_png(tmp_path, "first.png", (100, 100))
        img2 = _make_png(tmp_path, "second.png", (200, 200))
        viewer = ComparisonViewer(console=_silent_console())

        # Choose "1" from _prompt_user_action (digit → UserAction.KEEP),
        # then choose "2" from the follow-up prompt inside _process_user_action
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask",
            side_effect=["1", "2"],
        ):
            result = viewer.show_comparison([img1, img2])

        assert result.files_to_keep == [img2]
        assert result.files_to_delete == [img1]

    def test_all_images_unreadable_returns_skipped(self, tmp_path: Path) -> None:
        """show_comparison skips the group when all provided paths are unreadable."""
        viewer = ComparisonViewer(console=_silent_console())
        bad_paths = [tmp_path / "nonexistent1.png", tmp_path / "nonexistent2.png"]
        result = viewer.show_comparison(bad_paths)
        assert result.skipped is True

    def test_similarity_score_displayed_with_real_image(self, tmp_path: Path) -> None:
        """similarity_score parameter is accepted and the result is still a valid ReviewResult."""
        img = _make_png(tmp_path, "sim.png")
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="s"):
            result = viewer.show_comparison([img], similarity_score=87.5)

        assert result.skipped is True

    def test_delete_all_confirmed_deletes_all(self, tmp_path: Path) -> None:
        """Pressing 'd' and confirming marks all images for deletion."""
        img1 = _make_png(tmp_path, "del1.png")
        img2 = _make_png(tmp_path, "del2.png")
        viewer = ComparisonViewer(console=_silent_console())

        with (
            patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="d"),
            patch("file_organizer.services.deduplication.viewer.Confirm.ask", return_value=True),
        ):
            result = viewer.show_comparison([img1, img2])

        assert result.files_to_keep == []
        assert len(result.files_to_delete) == 2
        assert img1 in result.files_to_delete
        assert img2 in result.files_to_delete

    def test_delete_all_cancelled_skips(self, tmp_path: Path) -> None:
        """Pressing 'd' but declining the confirmation prompt skips the group."""
        img1 = _make_png(tmp_path, "c1.png")
        img2 = _make_png(tmp_path, "c2.png")
        viewer = ComparisonViewer(console=_silent_console())

        with (
            patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="d"),
            patch("file_organizer.services.deduplication.viewer.Confirm.ask", return_value=False),
        ):
            result = viewer.show_comparison([img1, img2])

        assert result.skipped is True


# ---------------------------------------------------------------------------
# TestBatchReviewIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBatchReviewIntegration:
    """Integration tests for batch_review with real images."""

    def test_auto_select_batch_keeps_best_per_group(self, tmp_path: Path) -> None:
        """auto_select_best=True keeps the highest-quality image in each duplicate group."""
        grp1_big = _make_png(tmp_path, "g1big.png", (800, 600))
        grp1_small = _make_png(tmp_path, "g1small.png", (100, 100))
        grp2_best = _make_png(tmp_path, "g2best.png", (1920, 1080))
        grp2_worst = _make_png(tmp_path, "g2worst.png", (320, 240))

        viewer = ComparisonViewer(console=_silent_console())
        groups = {
            "group-aaa": [grp1_big, grp1_small],
            "group-bbb": [grp2_best, grp2_worst],
        }
        decisions = viewer.batch_review(groups, auto_select_best=True)

        assert decisions[grp1_big] == "keep"
        assert decisions[grp1_small] == "delete"
        assert decisions[grp2_best] == "keep"
        assert decisions[grp2_worst] == "delete"

    def test_manual_review_skip_continue_then_keep(self, tmp_path: Path) -> None:
        """Skipping one group and keeping another produces the correct per-file decisions."""
        img_a = _make_png(tmp_path, "a.png", (400, 300))
        img_b = _make_png(tmp_path, "b.png", (200, 150))
        img_c = _make_png(tmp_path, "c.png", (600, 400))

        viewer = ComparisonViewer(console=_silent_console())
        groups = {
            "skip-group": [img_a, img_b],
            "keep-group": [img_c],
        }

        # First group: user presses "s" (skip), then confirms continue
        # Second group: user presses "k" (keep all)
        with (
            patch(
                "file_organizer.services.deduplication.viewer.Prompt.ask",
                side_effect=["s", "k"],
            ),
            patch(
                "file_organizer.services.deduplication.viewer.Confirm.ask",
                return_value=True,
            ),
        ):
            decisions = viewer.batch_review(groups, auto_select_best=False)

        assert decisions[img_c] == "keep"
        assert img_a not in decisions
        assert img_b not in decisions

    def test_batch_review_quit_stops_at_last_group(self, tmp_path: Path) -> None:
        """Declining to continue after a skip stops processing and returns no decisions."""
        img1 = _make_png(tmp_path, "q1.png")
        img2 = _make_png(tmp_path, "q2.png")

        viewer = ComparisonViewer(console=_silent_console())
        groups = {"g1": [img1], "g2": [img2]}

        # Skip both groups, decline continue after first skip
        with (
            patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="s"),
            patch("file_organizer.services.deduplication.viewer.Confirm.ask", return_value=False),
        ):
            decisions = viewer.batch_review(groups, auto_select_best=False)

        assert len(decisions) == 0

    def test_batch_review_empty_groups(self, tmp_path: Path) -> None:
        """batch_review with an empty groups dict returns an empty decisions dict."""
        viewer = ComparisonViewer(console=_silent_console())
        decisions = viewer.batch_review({}, auto_select_best=False)
        assert decisions == {}

    def test_batch_review_single_group_no_confirm_prompt(self, tmp_path: Path) -> None:
        """With a single group, batch_review does not prompt to continue after reviewing."""
        img = _make_png(tmp_path, "only.png")
        viewer = ComparisonViewer(console=_silent_console())

        with (
            patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="k"),
            patch("file_organizer.services.deduplication.viewer.Confirm.ask") as mock_confirm,
        ):
            decisions = viewer.batch_review({"single": [img]}, auto_select_best=False)

        mock_confirm.assert_not_called()
        assert decisions[img] == "keep"


# ---------------------------------------------------------------------------
# TestAutoSelectBestIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAutoSelectBestIntegration:
    """Integration tests for _auto_select_best with real images."""

    def test_png_preferred_over_jpeg_same_resolution(self, tmp_path: Path) -> None:
        """PNG is preferred over JPEG when both have the same resolution."""
        png = _make_png(tmp_path, "img.png", (300, 300))
        jpg = _make_jpeg(tmp_path, "img.jpg", (300, 300))
        viewer = ComparisonViewer(console=_silent_console())

        result = viewer._auto_select_best([jpg, png])

        assert png in result.files_to_keep
        assert jpg in result.files_to_delete

    def test_higher_resolution_wins_over_format(self, tmp_path: Path) -> None:
        """A much higher-resolution JPEG beats a lower-resolution PNG."""
        # A JPEG at 4x the resolution should beat a PNG at 1x
        large_jpg = _make_jpeg(tmp_path, "big.jpg", (2000, 1500))
        small_png = _make_png(tmp_path, "small.png", (100, 100))
        viewer = ComparisonViewer(console=_silent_console())

        result = viewer._auto_select_best([small_png, large_jpg])

        assert large_jpg in result.files_to_keep
        assert small_png in result.files_to_delete

    def test_single_image_is_kept_and_delete_is_empty(self, tmp_path: Path) -> None:
        """A single image is always kept with an empty delete list."""
        img = _make_png(tmp_path, "lone.png", (640, 480))
        viewer = ComparisonViewer(console=_silent_console())

        result = viewer._auto_select_best([img])

        assert result.files_to_keep == [img]
        assert result.files_to_delete == []
        assert result.skipped is False

    def test_unreadable_image_returns_skipped(self, tmp_path: Path) -> None:
        """_auto_select_best returns a skipped result when the only image path does not exist."""
        viewer = ComparisonViewer(console=_silent_console())
        result = viewer._auto_select_best([tmp_path / "ghost.png"])
        assert result.skipped is True

    def test_three_images_keeps_exactly_one(self, tmp_path: Path) -> None:
        """_auto_select_best keeps exactly one image (the best) out of three candidates."""
        imgs = [
            _make_png(tmp_path, "a.png", (100, 100)),
            _make_png(tmp_path, "b.png", (500, 500)),
            _make_png(tmp_path, "c.png", (300, 300)),
        ]
        viewer = ComparisonViewer(console=_silent_console())

        result = viewer._auto_select_best(imgs)

        assert len(result.files_to_keep) == 1
        assert len(result.files_to_delete) == 2
        assert imgs[1] in result.files_to_keep


# ---------------------------------------------------------------------------
# TestGetImageMetadataIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetImageMetadataIntegration:
    """Integration tests for _get_image_metadata with real files."""

    def test_png_metadata_fields(self, tmp_path: Path) -> None:
        """_get_image_metadata returns correct width, height, format, and file_size for a PNG."""
        img_path = _make_png(tmp_path, "meta.png", (320, 240))
        viewer = ComparisonViewer(console=_silent_console())

        meta = viewer._get_image_metadata(img_path)

        assert meta.path == img_path
        assert meta.width == 320
        assert meta.height == 240
        assert meta.format == "PNG"
        assert meta.mode == "RGB"
        assert meta.file_size > 0
        assert meta.resolution == 320 * 240
        assert meta.dimensions == "320x240"
        assert meta.size_mb == pytest.approx(meta.file_size / (1024 * 1024))

    def test_jpeg_metadata_fields(self, tmp_path: Path) -> None:
        """_get_image_metadata returns correct width, height, and format for a JPEG."""
        img_path = _make_jpeg(tmp_path, "meta.jpg", (640, 480))
        viewer = ComparisonViewer(console=_silent_console())

        meta = viewer._get_image_metadata(img_path)

        assert meta.width == 640
        assert meta.height == 480
        assert meta.format == "JPEG"
        assert meta.file_size > 0

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        """_get_image_metadata raises FileNotFoundError when the image path does not exist."""
        viewer = ComparisonViewer(console=_silent_console())
        with pytest.raises(FileNotFoundError):
            viewer._get_image_metadata(tmp_path / "no_such_file.png")

    def test_modified_str_format(self, tmp_path: Path) -> None:
        """modified_str on the returned metadata is formatted as YYYY-MM-DD HH:MM:SS."""
        img_path = _make_png(tmp_path, "ts.png", (10, 10))
        viewer = ComparisonViewer(console=_silent_console())

        meta = viewer._get_image_metadata(img_path)

        # Modified string should match YYYY-MM-DD HH:MM:SS
        parts = meta.modified_str.split(" ")
        assert len(parts) == 2
        date_parts = parts[0].split("-")
        assert len(date_parts) == 3
        assert len(date_parts[0]) == 4


# ---------------------------------------------------------------------------
# TestGenerateAsciiPreviewIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGenerateAsciiPreviewIntegration:
    """Integration tests for _generate_ascii_preview exercising the getdata() fallback.

    In current Pillow, getdata() returns an ImagingCore object that does not
    support integer indexing via list slicing, so the real image path typically
    reaches the exception handler and returns None.  We use a mock that
    explicitly removes get_flattened_data to force the getdata() branch (line 326).
    """

    def test_getdata_fallback_branch_executed(self, tmp_path: Path) -> None:
        """Force the else-branch (line 326) by removing get_flattened_data from the resized image.

        The production code checks:
            _get_flat = getattr(img, "get_flattened_data", None)
            if callable(_get_flat):
                pixels = _get_flat()
            else:
                pixels = list(img.getdata())   ← line 326

        We use a regular MagicMock (not spec=[]) for the resized image but
        explicitly delete the get_flattened_data attribute so that getattr
        returns None → the else-branch fires.
        """
        viewer = ComparisonViewer(console=_silent_console())
        img_path = _make_png(tmp_path, "fallback.png", (20, 20))

        resized = MagicMock()
        resized.width = 10
        resized.height = 5
        pixel_list = [128] * 50
        resized.getdata.return_value = pixel_list
        # Remove get_flattened_data so the else-branch is taken
        del resized.get_flattened_data

        fake_img = MagicMock()
        fake_img.width = 20
        fake_img.height = 20
        fake_img.convert.return_value = fake_img
        fake_img.resize.return_value = resized

        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=fake_img)
        mock_cm.__exit__ = MagicMock(return_value=False)

        with patch(
            "file_organizer.services.deduplication.viewer.Image.open",
            return_value=mock_cm,
        ):
            result = viewer._generate_ascii_preview(img_path, max_width=10, max_height=5)

        # The else-branch produces a string; getdata was called
        resized.getdata.assert_called_once()
        assert result is not None
        lines = result.split("\n")
        assert len(lines) == 5

    def test_nonexistent_file_returns_none(self, tmp_path: Path) -> None:
        """_generate_ascii_preview returns None when the image path does not exist."""
        viewer = ComparisonViewer(console=_silent_console())
        result = viewer._generate_ascii_preview(tmp_path / "ghost.png")
        assert result is None

    def test_landscape_image_produces_string_or_none(self, tmp_path: Path) -> None:
        """_generate_ascii_preview produces a multi-line string wider than it is tall for a landscape image."""
        landscape = _make_png(tmp_path, "land.png", (200, 50))
        viewer = ComparisonViewer(console=_silent_console())
        result = viewer._generate_ascii_preview(landscape, max_width=20, max_height=10)
        assert result is not None
        lines = result.split("\n")
        # landscape: width (chars per line) > height (number of lines)
        assert len(lines[0]) > len(lines)

    def test_portrait_image_produces_string_or_none(self, tmp_path: Path) -> None:
        """_generate_ascii_preview produces a multi-line string taller than it is wide for a portrait image."""
        portrait = _make_png(tmp_path, "port.png", (50, 200))
        viewer = ComparisonViewer(console=_silent_console())
        result = viewer._generate_ascii_preview(portrait, max_width=20, max_height=10)
        assert result is not None
        lines = result.split("\n")
        # portrait: height (number of lines) > width (chars per line)
        assert len(lines) > len(lines[0])


# ---------------------------------------------------------------------------
# TestDisplayReviewSummaryIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDisplayReviewSummaryIntegration:
    """Integration tests for _display_review_summary."""

    def test_summary_with_existing_delete_files(self, tmp_path: Path) -> None:
        """_display_review_summary includes Summary, Keep, Delete, and space-saving text when files exist."""
        kept = _make_png(tmp_path, "keep.png", (100, 100))
        to_delete = _make_png(tmp_path, "delete.png", (100, 100))
        viewer = ComparisonViewer(console=_silent_console())

        decisions = {kept: "keep", to_delete: "delete"}
        viewer._display_review_summary(decisions)

        output = _written(viewer)
        assert "Summary" in output
        assert "Keep" in output
        assert "Delete" in output
        assert "space" in output.lower()

    def test_summary_zero_files(self, tmp_path: Path) -> None:
        """_display_review_summary with an empty decisions dict still prints Summary headers."""
        viewer = ComparisonViewer(console=_silent_console())
        viewer._display_review_summary({})

        output = _written(viewer)
        assert "Summary" in output
        assert "Keep" in output
        assert "Delete" in output

    def test_summary_all_keep_no_space_savings(self, tmp_path: Path) -> None:
        """_display_review_summary with all-keep decisions does not mention space savings."""
        imgs = [_make_png(tmp_path, f"k{i}.png") for i in range(3)]
        viewer = ComparisonViewer(console=_silent_console())
        decisions = dict.fromkeys(imgs, "keep")
        viewer._display_review_summary(decisions)

        output = _written(viewer)
        assert "Summary" in output
        assert "Keep" in output
        assert "space" not in output.lower()

    def test_summary_missing_delete_file_does_not_raise(self, tmp_path: Path) -> None:
        """_display_review_summary does not raise when a file marked for deletion no longer exists."""
        missing = tmp_path / "gone.png"
        viewer = ComparisonViewer(console=_silent_console())
        decisions = {missing: "delete"}
        viewer._display_review_summary(decisions)

        output = _written(viewer)
        assert "Summary" in output
        assert "Delete" in output


# ---------------------------------------------------------------------------
# TestDisplayMetadataIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDisplayMetadataIntegration:
    """Integration tests for display_metadata public method."""

    def test_valid_image_displays_metadata(self, tmp_path: Path) -> None:
        """display_metadata for a valid image path prints an Image header to the console."""
        img = _make_png(tmp_path, "show.png", (64, 48))
        viewer = ComparisonViewer(console=_silent_console())
        viewer.display_metadata(img)
        output = _written(viewer)
        assert "Image" in output

    def test_invalid_path_prints_error_no_raise(self, tmp_path: Path) -> None:
        """display_metadata for a nonexistent path prints an Error message and does not raise."""
        viewer = ComparisonViewer(console=_silent_console())
        viewer.display_metadata(tmp_path / "nope.png")
        output = _written(viewer)
        assert "Error" in output

    def test_jpeg_image_metadata_display(self, tmp_path: Path) -> None:
        """display_metadata for a JPEG prints an Image header containing the filename."""
        jpg = _make_jpeg(tmp_path, "photo.jpg", (128, 96))
        viewer = ComparisonViewer(console=_silent_console())
        viewer.display_metadata(jpg)
        output = _written(viewer)
        assert "Image" in output
        assert "photo" in output


# ---------------------------------------------------------------------------
# TestInteractiveSelectIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestInteractiveSelectIntegration:
    """Integration tests for interactive_select with real images."""

    def test_empty_list_returns_empty(self, tmp_path: Path) -> None:
        """interactive_select with an empty list returns an empty list without prompting."""
        viewer = ComparisonViewer(console=_silent_console())
        result = viewer.interactive_select([])
        assert result == []

    def test_select_all_returns_all_images(self, tmp_path: Path) -> None:
        """Entering 'all' in interactive_select returns every image in the list."""
        imgs = [_make_png(tmp_path, f"img{i}.png") for i in range(4)]
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="all"):
            result = viewer.interactive_select(imgs)

        assert result == imgs

    def test_select_none_returns_empty(self, tmp_path: Path) -> None:
        """Entering 'none' in interactive_select returns an empty list."""
        imgs = [_make_png(tmp_path, f"n{i}.png") for i in range(2)]
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="none"):
            result = viewer.interactive_select(imgs)

        assert result == []

    def test_select_by_comma_separated_indices(self, tmp_path: Path) -> None:
        """Entering comma-separated 1-based indices selects the corresponding images."""
        imgs = [_make_png(tmp_path, f"s{i}.png") for i in range(5)]
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="2,4"):
            result = viewer.interactive_select(imgs)

        assert result == [imgs[1], imgs[3]]

    def test_out_of_range_indices_ignored(self, tmp_path: Path) -> None:
        """Out-of-range indices in interactive_select are silently ignored."""
        imgs = [_make_png(tmp_path, f"r{i}.png") for i in range(3)]
        viewer = ComparisonViewer(console=_silent_console())

        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask",
            return_value="1,99,0",
        ):
            result = viewer.interactive_select(imgs)

        assert result == [imgs[0]]

    def test_non_numeric_entries_ignored(self, tmp_path: Path) -> None:
        """Non-numeric entries in the comma-separated selection are silently ignored."""
        imgs = [_make_png(tmp_path, f"v{i}.png") for i in range(2)]
        viewer = ComparisonViewer(console=_silent_console())

        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask",
            return_value="abc,1,xyz",
        ):
            result = viewer.interactive_select(imgs)

        assert result == [imgs[0]]

    def test_failed_metadata_load_shows_fallback(self, tmp_path: Path) -> None:
        """interactive_select returns the path even when image metadata cannot be loaded."""
        viewer = ComparisonViewer(console=_silent_console())
        bad_path = tmp_path / "missing.png"

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="all"):
            result = viewer.interactive_select([bad_path])

        assert result == [bad_path]

    def test_custom_prompt_text_accepted(self, tmp_path: Path) -> None:
        """interactive_select accepts a custom prompt string and still returns the selected images."""
        imgs = [_make_png(tmp_path, "custom.png")]
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="1"):
            result = viewer.interactive_select(imgs, prompt="Pick the best photo")

        assert result == [imgs[0]]


# ---------------------------------------------------------------------------
# TestCalculateQualityScoreIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCalculateQualityScoreIntegration:
    """Integration tests verifying quality score properties with real metadata."""

    def test_score_is_positive(self, tmp_path: Path) -> None:
        """_calculate_quality_score returns a positive value for a valid image."""
        img = _make_png(tmp_path, "score.png", (400, 300))
        viewer = ComparisonViewer(console=_silent_console())
        meta = viewer._get_image_metadata(img)
        score = viewer._calculate_quality_score(meta)
        assert score > 0

    def test_larger_image_scores_higher_than_smaller(self, tmp_path: Path) -> None:
        """A higher-resolution image receives a strictly higher quality score than a smaller one."""
        big = _make_png(tmp_path, "big.png", (1000, 1000))
        small = _make_png(tmp_path, "small.png", (100, 100))
        viewer = ComparisonViewer(console=_silent_console())
        big_meta = viewer._get_image_metadata(big)
        small_meta = viewer._get_image_metadata(small)
        assert viewer._calculate_quality_score(big_meta) > viewer._calculate_quality_score(
            small_meta
        )

    def test_all_known_formats_produce_finite_score(self, tmp_path: Path) -> None:
        """_calculate_quality_score returns a positive finite score for every recognized image format."""
        viewer = ComparisonViewer(console=_silent_console())
        for fmt in ("PNG", "JPEG", "TIFF", "WEBP", "GIF", "BMP", "JPG"):
            meta = ImageMetadata(
                path=tmp_path / f"img.{fmt.lower()}",
                width=200,
                height=200,
                format=fmt,
                file_size=50_000,
                modified_time=datetime.now(UTC),
                mode="RGB",
            )
            score = viewer._calculate_quality_score(meta)
            assert score > 0, f"Score for format {fmt} should be positive"


# ---------------------------------------------------------------------------
# TestPromptUserActionIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPromptUserActionIntegration:
    """Integration tests for _prompt_user_action parsing all branches."""

    def test_auto_select_letter(self) -> None:
        """Entering 'a' in _prompt_user_action returns UserAction.AUTO_SELECT."""
        viewer = ComparisonViewer(console=_silent_console())
        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="a"):
            action = viewer._prompt_user_action(image_count=2)
        assert action == UserAction.AUTO_SELECT

    def test_skip_letter(self) -> None:
        """Entering 's' in _prompt_user_action returns UserAction.SKIP."""
        viewer = ComparisonViewer(console=_silent_console())
        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="s"):
            action = viewer._prompt_user_action(image_count=2)
        assert action == UserAction.SKIP

    def test_keep_all_letter(self) -> None:
        """Entering 'k' in _prompt_user_action returns UserAction.KEEP_ALL."""
        viewer = ComparisonViewer(console=_silent_console())
        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="k"):
            action = viewer._prompt_user_action(image_count=2)
        assert action == UserAction.KEEP_ALL

    def test_delete_all_letter(self) -> None:
        """Entering 'd' in _prompt_user_action returns UserAction.DELETE_ALL."""
        viewer = ComparisonViewer(console=_silent_console())
        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="d"):
            action = viewer._prompt_user_action(image_count=2)
        assert action == UserAction.DELETE_ALL

    def test_quit_letter(self) -> None:
        """Entering 'q' in _prompt_user_action returns UserAction.QUIT."""
        viewer = ComparisonViewer(console=_silent_console())
        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="q"):
            action = viewer._prompt_user_action(image_count=2)
        assert action == UserAction.QUIT

    def test_valid_digit_in_range_returns_keep(self) -> None:
        """A valid in-range digit in _prompt_user_action returns UserAction.KEEP."""
        viewer = ComparisonViewer(console=_silent_console())
        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="1"):
            action = viewer._prompt_user_action(image_count=3)
        assert action == UserAction.KEEP

    def test_digit_out_of_range_retries_then_succeeds(self) -> None:
        """An out-of-range digit causes _prompt_user_action to retry until a valid input is given."""
        viewer = ComparisonViewer(console=_silent_console())
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask",
            side_effect=["5", "a"],
        ):
            action = viewer._prompt_user_action(image_count=3)
        assert action == UserAction.AUTO_SELECT

    def test_invalid_text_retries_until_valid(self) -> None:
        """Unrecognized input in _prompt_user_action causes repeated retries until a valid key is entered."""
        viewer = ComparisonViewer(console=_silent_console())
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask",
            side_effect=["!!!", "???", "q"],
        ):
            action = viewer._prompt_user_action(image_count=2)
        assert action == UserAction.QUIT


# ---------------------------------------------------------------------------
# TestProcessUserActionIntegration — branches not yet reached from integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestProcessUserActionMissingBranchesIntegration:
    """Integration tests for the ValueError-path and final fallback in _process_user_action."""

    def test_keep_action_non_numeric_choice_returns_skipped(self, tmp_path: Path) -> None:
        """Providing a non-numeric string to the KEEP prompt triggers ValueError → skipped."""

        meta = ImageMetadata(
            path=tmp_path / "img.png",
            width=100,
            height=100,
            format="PNG",
            file_size=1024,
            modified_time=datetime.now(UTC),
            mode="RGB",
        )
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="abc"):
            result = viewer._process_user_action(UserAction.KEEP, [meta])

        assert result.skipped is True
        assert result.files_to_keep == []
        assert result.files_to_delete == []

    def test_keep_action_out_of_range_index_returns_skipped(self, tmp_path: Path) -> None:
        """Choosing an out-of-range index for KEEP falls through to skipped."""

        meta = ImageMetadata(
            path=tmp_path / "img.png",
            width=100,
            height=100,
            format="PNG",
            file_size=1024,
            modified_time=datetime.now(UTC),
            mode="RGB",
        )
        viewer = ComparisonViewer(console=_silent_console())

        with patch("file_organizer.services.deduplication.viewer.Prompt.ask", return_value="99"):
            result = viewer._process_user_action(UserAction.KEEP, [meta])

        assert result.skipped is True

    def test_unhandled_action_enum_reaches_final_fallback(self, tmp_path: Path) -> None:
        """UserAction.DELETE is not handled by any branch → final return at line 433."""

        meta = ImageMetadata(
            path=tmp_path / "img.png",
            width=100,
            height=100,
            format="PNG",
            file_size=1024,
            modified_time=datetime.now(UTC),
            mode="RGB",
        )
        viewer = ComparisonViewer(console=_silent_console())
        result = viewer._process_user_action(UserAction.DELETE, [meta])
        assert result.skipped is True
        assert result.files_to_keep == []
        assert result.files_to_delete == []


# ---------------------------------------------------------------------------
# TestDisplayImagesSideBySideIntegration — Columns layout (line 245)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDisplayImagesSideBySideIntegration:
    """Integration tests exercising the Columns (wide terminal) path in _display_images_side_by_side."""

    def test_wide_terminal_two_images_uses_columns_layout(self, tmp_path: Path) -> None:
        """_terminal_width >= 120 + 2 images → Columns branch (line 245) is executed."""

        viewer = ComparisonViewer(console=_silent_console())
        viewer._terminal_width = 200

        metas = [
            ImageMetadata(
                path=tmp_path / f"img{i}.png",
                width=100,
                height=100,
                format="PNG",
                file_size=1024,
                modified_time=datetime.now(UTC),
                mode="RGB",
            )
            for i in range(2)
        ]

        with patch("file_organizer.services.deduplication.viewer.Columns") as mock_columns:
            with patch.object(viewer, "_generate_ascii_preview", return_value=None):
                viewer._display_images_side_by_side(metas)

        mock_columns.assert_called_once()

    def test_narrow_terminal_two_images_stacks_vertically(self, tmp_path: Path) -> None:
        """_terminal_width < 120 → vertical stacking path executed."""

        viewer = ComparisonViewer(console=_silent_console())
        viewer._terminal_width = 60

        metas = [
            ImageMetadata(
                path=tmp_path / f"img{i}.png",
                width=100,
                height=100,
                format="PNG",
                file_size=1024,
                modified_time=datetime.now(UTC),
                mode="RGB",
            )
            for i in range(2)
        ]

        with patch("file_organizer.services.deduplication.viewer.Columns") as mock_columns:
            with patch.object(viewer, "_generate_ascii_preview", return_value=None):
                viewer._display_images_side_by_side(metas)

        mock_columns.assert_not_called()
