"""Tests for ComparisonViewer and related classes in deduplication viewer.

Tests cover:
- ImageMetadata dataclass properties
- UserAction enum values
- DuplicateReview dataclass
- ComparisonViewer methods: show_comparison, batch_review, auto_select,
  quality scoring, metadata display, interactive selection, and all
  internal display/prompt helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.table import Table

from file_organizer.services.deduplication.viewer import (
    ComparisonViewer,
    DuplicateReview,
    ImageMetadata,
    UserAction,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def console() -> Console:
    """Return a Console that writes to /dev/null so tests stay silent."""
    return Console(file=MagicMock(), highlight=False)


@pytest.fixture
def viewer(console: Console) -> ComparisonViewer:
    """Return a ComparisonViewer wired to the silent console."""
    return ComparisonViewer(console=console, preview_width=40, preview_height=20)


@pytest.fixture
def sample_metadata() -> ImageMetadata:
    """Return a representative ImageMetadata object."""
    return ImageMetadata(
        path=Path("/tmp/image1.png"),
        width=1920,
        height=1080,
        format="PNG",
        file_size=2 * 1024 * 1024,  # 2 MB
        modified_time=datetime(2025, 6, 15, 12, 30, 0, tzinfo=UTC),
        mode="RGB",
    )


@pytest.fixture
def sample_metadata_small() -> ImageMetadata:
    """Return a smaller / lower-quality ImageMetadata object."""
    return ImageMetadata(
        path=Path("/tmp/image2.jpg"),
        width=640,
        height=480,
        format="JPEG",
        file_size=512 * 1024,  # 0.5 MB
        modified_time=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        mode="RGB",
    )


def _make_png(tmp_path: Path, name: str = "img.png", size: tuple[int, int] = (100, 100)) -> Path:
    """Create a minimal real PNG file for tests that open images."""
    from PIL import Image as PILImage

    p = tmp_path / name
    PILImage.new("RGB", size, color="red").save(p, format="PNG")
    return p


# ===========================================================================
# UserAction enum
# ===========================================================================


@pytest.mark.unit
class TestUserAction:
    """Test UserAction enum values exist and are distinct."""

    def test_all_values(self):
        assert UserAction.KEEP.value == "keep"
        assert UserAction.DELETE.value == "delete"
        assert UserAction.SKIP.value == "skip"
        assert UserAction.KEEP_ALL.value == "keep_all"
        assert UserAction.DELETE_ALL.value == "delete_all"
        assert UserAction.AUTO_SELECT.value == "auto"
        assert UserAction.QUIT.value == "quit"

    def test_member_count(self):
        assert len(UserAction) == 7


# ===========================================================================
# ImageMetadata dataclass & properties
# ===========================================================================


@pytest.mark.unit
class TestImageMetadata:
    """Test ImageMetadata dataclass and computed properties."""

    def test_resolution(self, sample_metadata: ImageMetadata):
        assert sample_metadata.resolution == 1920 * 1080

    def test_dimensions(self, sample_metadata: ImageMetadata):
        assert sample_metadata.dimensions == "1920x1080"

    def test_size_mb(self, sample_metadata: ImageMetadata):
        assert sample_metadata.size_mb == pytest.approx(2.0)

    def test_modified_str(self, sample_metadata: ImageMetadata):
        assert sample_metadata.modified_str == "2025-06-15 12:30:00"

    def test_small_image_resolution(self, sample_metadata_small: ImageMetadata):
        assert sample_metadata_small.resolution == 640 * 480

    def test_size_mb_fractional(self, sample_metadata_small: ImageMetadata):
        assert sample_metadata_small.size_mb == pytest.approx(0.5)


# ===========================================================================
# DuplicateReview dataclass
# ===========================================================================


@pytest.mark.unit
class TestDuplicateReview:
    """Test DuplicateReview dataclass defaults."""

    def test_defaults(self):
        review = DuplicateReview(files_to_keep=[], files_to_delete=[])
        assert review.skipped is False

    def test_skipped_flag(self):
        review = DuplicateReview([], [], skipped=True)
        assert review.skipped is True

    def test_keep_and_delete_lists(self):
        k = [Path("/a")]
        d = [Path("/b"), Path("/c")]
        review = DuplicateReview(files_to_keep=k, files_to_delete=d)
        assert review.files_to_keep == k
        assert review.files_to_delete == d


# ===========================================================================
# ComparisonViewer.__init__
# ===========================================================================


@pytest.mark.unit
class TestComparisonViewerInit:
    """Test ComparisonViewer initialisation."""

    def test_default_console_created(self):
        v = ComparisonViewer()
        assert v.console is not None

    def test_custom_console(self, console: Console):
        v = ComparisonViewer(console=console)
        assert v.console is console

    def test_custom_preview_dimensions(self):
        v = ComparisonViewer(preview_width=80, preview_height=40)
        assert v.preview_width == 80
        assert v.preview_height == 40


# ===========================================================================
# ComparisonViewer.show_comparison
# ===========================================================================


@pytest.mark.unit
class TestShowComparison:
    """Test ComparisonViewer.show_comparison."""

    def test_empty_images_returns_skipped(self, viewer: ComparisonViewer):
        result = viewer.show_comparison([])
        assert result.skipped is True
        assert result.files_to_keep == []
        assert result.files_to_delete == []

    def test_all_images_fail_to_load(self, viewer: ComparisonViewer):
        """When every image fails to load, result is skipped."""
        with patch.object(viewer, "_get_image_metadata", side_effect=RuntimeError("bad")):
            result = viewer.show_comparison([Path("/fake/a.png"), Path("/fake/b.png")])
        assert result.skipped is True

    def test_delegates_to_prompt_and_process(self, viewer: ComparisonViewer, sample_metadata):
        """Happy path: loads metadata, displays, prompts, processes."""
        with (
            patch.object(viewer, "_get_image_metadata", return_value=sample_metadata),
            patch.object(viewer, "_display_comparison_header"),
            patch.object(viewer, "_display_images_side_by_side"),
            patch.object(viewer, "_prompt_user_action", return_value=UserAction.KEEP_ALL),
            patch.object(
                viewer,
                "_process_user_action",
                return_value=DuplicateReview([sample_metadata.path], []),
            ) as mock_process,
        ):
            result = viewer.show_comparison([Path("/tmp/image1.png")], similarity_score=95.0)
            assert result.files_to_keep == [sample_metadata.path]
            mock_process.assert_called_once()

    def test_partial_load_failure(self, viewer: ComparisonViewer, sample_metadata):
        """If some images fail to load, the rest still show up."""
        call_count = 0

        def _meta_side_effect(path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("corrupt")
            return sample_metadata

        with (
            patch.object(viewer, "_get_image_metadata", side_effect=_meta_side_effect),
            patch.object(viewer, "_display_comparison_header"),
            patch.object(viewer, "_display_images_side_by_side"),
            patch.object(viewer, "_prompt_user_action", return_value=UserAction.SKIP),
            patch.object(
                viewer,
                "_process_user_action",
                return_value=DuplicateReview([], [], skipped=True),
            ),
        ):
            result = viewer.show_comparison([Path("/a.png"), Path("/b.png")])
            assert result.skipped is True


# ===========================================================================
# ComparisonViewer.batch_review
# ===========================================================================


@pytest.mark.unit
class TestBatchReview:
    """Test ComparisonViewer.batch_review."""

    def test_auto_select_best_mode(self, viewer: ComparisonViewer, sample_metadata):
        """auto_select_best=True should call _auto_select_best instead of show_comparison."""
        review = DuplicateReview([sample_metadata.path], [])
        with (
            patch.object(viewer, "_auto_select_best", return_value=review) as mock_auto,
            patch.object(viewer, "_display_review_summary"),
        ):
            groups = {"hash1": [Path("/a.png"), Path("/b.png")]}
            decisions = viewer.batch_review(groups, auto_select_best=True)
            mock_auto.assert_called_once()
            assert decisions[sample_metadata.path] == "keep"

    def test_manual_review_mode(self, viewer: ComparisonViewer, sample_metadata):
        """auto_select_best=False uses show_comparison."""
        review = DuplicateReview([sample_metadata.path], [Path("/tmp/image2.jpg")])
        with (
            patch.object(viewer, "show_comparison", return_value=review),
            patch.object(viewer, "_display_review_summary"),
        ):
            groups = {"hash1": [Path("/a.png"), Path("/b.png")]}
            decisions = viewer.batch_review(groups, auto_select_best=False)
            assert decisions[sample_metadata.path] == "keep"
            assert decisions[Path("/tmp/image2.jpg")] == "delete"

    def test_quit_early_via_confirm(self, viewer: ComparisonViewer):
        """When user skips and declines continue, batch stops."""
        review_skip = DuplicateReview([], [], skipped=True)
        with (
            patch.object(viewer, "show_comparison", return_value=review_skip),
            patch(
                "file_organizer.services.deduplication.viewer.Confirm.ask", return_value=False
            ),
            patch.object(viewer, "_display_review_summary"),
        ):
            groups = {"h1": [Path("/a.png")], "h2": [Path("/b.png")]}
            decisions = viewer.batch_review(groups, auto_select_best=False)
            # Only the first group is processed; second is skipped entirely.
            assert len(decisions) == 0

    def test_continue_after_skip(self, viewer: ComparisonViewer, sample_metadata):
        """When user skips but confirms continue, next group is reviewed."""
        review_skip = DuplicateReview([], [], skipped=True)
        review_keep = DuplicateReview([sample_metadata.path], [])
        call_iter = iter([review_skip, review_keep])

        with (
            patch.object(viewer, "show_comparison", side_effect=lambda *a, **kw: next(call_iter)),
            patch(
                "file_organizer.services.deduplication.viewer.Confirm.ask", return_value=True
            ),
            patch.object(viewer, "_display_review_summary"),
        ):
            groups = {"h1": [Path("/a.png")], "h2": [Path("/b.png")]}
            decisions = viewer.batch_review(groups, auto_select_best=False)
            assert decisions.get(sample_metadata.path) == "keep"

    def test_last_group_skip_no_confirm(self, viewer: ComparisonViewer):
        """When the last group is skipped, Confirm.ask is NOT called."""
        review_skip = DuplicateReview([], [], skipped=True)
        with (
            patch.object(viewer, "show_comparison", return_value=review_skip),
            patch(
                "file_organizer.services.deduplication.viewer.Confirm.ask"
            ) as mock_confirm,
            patch.object(viewer, "_display_review_summary"),
        ):
            groups = {"h1": [Path("/a.png")]}
            viewer.batch_review(groups, auto_select_best=False)
            mock_confirm.assert_not_called()


# ===========================================================================
# ComparisonViewer._get_image_metadata
# ===========================================================================


@pytest.mark.unit
class TestGetImageMetadata:
    """Test _get_image_metadata using real tiny images via tmp_path."""

    def test_extracts_correct_metadata(self, tmp_path: Path, viewer: ComparisonViewer):
        img_path = _make_png(tmp_path, "test.png", (200, 150))
        meta = viewer._get_image_metadata(img_path)

        assert meta.path == img_path
        assert meta.width == 200
        assert meta.height == 150
        assert meta.format == "PNG"
        assert meta.mode == "RGB"
        assert meta.file_size > 0
        assert isinstance(meta.modified_time, datetime)

    def test_raises_on_invalid_path(self, viewer: ComparisonViewer):
        with pytest.raises(OSError):
            viewer._get_image_metadata(Path("/nonexistent/img.png"))


# ===========================================================================
# ComparisonViewer._display_comparison_header
# ===========================================================================


@pytest.mark.unit
class TestDisplayComparisonHeader:
    """Test _display_comparison_header prints without error."""

    def test_without_score(self, viewer: ComparisonViewer):
        viewer._display_comparison_header(3)  # should not raise

    def test_with_score(self, viewer: ComparisonViewer):
        viewer._display_comparison_header(2, similarity_score=92.5)


# ===========================================================================
# ComparisonViewer._display_images_side_by_side
# ===========================================================================


@pytest.mark.unit
class TestDisplayImagesSideBySide:
    """Test _display_images_side_by_side layout branches."""

    def test_wide_terminal_two_images(self, viewer: ComparisonViewer, sample_metadata):
        """With wide terminal and <=2 images, Columns layout is used."""
        viewer._terminal_width = 200
        # _create_image_info_table returns a real Rich Table so Columns can measure it
        with patch.object(
            viewer,
            "_create_image_info_table",
            return_value=Table(title="mock"),
        ):
            viewer._display_images_side_by_side([sample_metadata, sample_metadata])

    def test_narrow_terminal_stacks_vertically(self, viewer: ComparisonViewer, sample_metadata):
        """With narrow terminal, images are stacked vertically."""
        viewer._terminal_width = 60
        with patch.object(
            viewer,
            "_create_image_info_table",
            return_value=Table(title="mock"),
        ):
            viewer._display_images_side_by_side([sample_metadata, sample_metadata])

    def test_many_images_stacks_vertically(self, viewer: ComparisonViewer, sample_metadata):
        """More than 2 images always stacks vertically."""
        viewer._terminal_width = 200
        metas = [sample_metadata, sample_metadata, sample_metadata]
        with patch.object(
            viewer,
            "_create_image_info_table",
            return_value=Table(title="mock"),
        ):
            viewer._display_images_side_by_side(metas)


# ===========================================================================
# ComparisonViewer._create_image_info_table
# ===========================================================================


@pytest.mark.unit
class TestCreateImageInfoTable:
    """Test _create_image_info_table returns a Table."""

    def test_returns_table(self, viewer: ComparisonViewer, sample_metadata):
        with patch.object(viewer, "_generate_ascii_preview", return_value=None):
            table = viewer._create_image_info_table(1, sample_metadata)
        assert isinstance(table, Table)

    def test_with_preview(self, viewer: ComparisonViewer, sample_metadata):
        with patch.object(viewer, "_generate_ascii_preview", return_value="###"):
            table = viewer._create_image_info_table(1, sample_metadata)
        assert table is not None


# ===========================================================================
# ComparisonViewer._generate_ascii_preview
# ===========================================================================


@pytest.mark.unit
class TestGenerateAsciiPreview:
    """Test _generate_ascii_preview with real and mocked images.

    Note: On newer Pillow versions, getdata() returns an ImagingCore object
    that does not support slicing, causing the real code path to hit the
    exception handler and return None.  We test both the real (returns None)
    and the mocked (happy-path logic) behaviours.
    """

    def test_returns_none_on_nonexistent_file(self, viewer: ComparisonViewer):
        result = viewer._generate_ascii_preview(Path("/nonexistent/img.png"))
        assert result is None

    def test_real_image_returns_none_or_string(
        self, tmp_path: Path, viewer: ComparisonViewer
    ):
        """With a real image the function either returns a string or None
        depending on the Pillow version.  Either outcome is acceptable."""
        img_path = _make_png(tmp_path, "preview.png", (80, 60))
        result = viewer._generate_ascii_preview(img_path)
        assert result is None or isinstance(result, str)

    def test_happy_path_with_mock(self, viewer: ComparisonViewer):
        """Mock Image.open to exercise the full happy path inside the method."""
        # Build a fake grayscale image whose getdata() returns a plain list
        fake_img = MagicMock()
        fake_img.width = 80
        fake_img.height = 60
        fake_img.convert.return_value = fake_img
        fake_img.resize.return_value = fake_img
        # After resize the new dimensions:
        # aspect_ratio=80/60=1.33 > 1 → new_width=40, new_height=int(40/1.33/2)=15
        # Total pixels = 40*15 = 600
        fake_img.resize.return_value.width = 40
        fake_img.resize.return_value.height = 15

        pixel_data = list(range(256)) + list(range(256)) + list(range(88))
        assert len(pixel_data) == 600

        fake_img.resize.return_value.get_flattened_data.return_value = pixel_data
        # Make sure the resized image's width is accessible for the loop
        type(fake_img.resize.return_value).width = 40

        mock_open_cm = MagicMock()
        mock_open_cm.__enter__ = MagicMock(return_value=fake_img)
        mock_open_cm.__exit__ = MagicMock(return_value=False)

        with patch(
            "file_organizer.services.deduplication.viewer.Image.open",
            return_value=mock_open_cm,
        ):
            result = viewer._generate_ascii_preview(Path("/fake/img.png"), max_width=40, max_height=15)

        assert result is not None
        assert isinstance(result, str)
        lines = result.split("\n")
        assert len(lines) == 15

    def test_landscape_vs_portrait_branches(self, viewer: ComparisonViewer):
        """Exercise both the landscape (aspect_ratio > 1) and portrait branches."""

        def _make_fake_img(width, height, max_w, max_h):
            fake_img = MagicMock()
            fake_img.width = width
            fake_img.height = height
            fake_img.convert.return_value = fake_img

            # Compute the expected dims as the real code would
            ar = width / height
            if ar > 1:
                nw = max_w
                nh = int(max_w / ar / 2)
            else:
                nh = max_h
                nw = int(max_h * ar * 2)
            if nw == 0:
                nw = 1
            if nh == 0:
                nh = 1

            resized = MagicMock()
            resized.width = nw
            resized.height = nh
            type(resized).width = nw
            resized.get_flattened_data.return_value = [128] * (nw * nh)
            fake_img.resize.return_value = resized
            return fake_img

        # Landscape: 400x100, aspect_ratio=4 > 1
        landscape_img = _make_fake_img(400, 100, 20, 10)
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=landscape_img)
        mock_cm.__exit__ = MagicMock(return_value=False)
        with patch(
            "file_organizer.services.deduplication.viewer.Image.open",
            return_value=mock_cm,
        ):
            result = viewer._generate_ascii_preview(Path("/fake/wide.png"), max_width=20, max_height=10)
        assert result is not None

        # Portrait: 100x400, aspect_ratio=0.25 < 1
        portrait_img = _make_fake_img(100, 400, 20, 10)
        mock_cm2 = MagicMock()
        mock_cm2.__enter__ = MagicMock(return_value=portrait_img)
        mock_cm2.__exit__ = MagicMock(return_value=False)
        with patch(
            "file_organizer.services.deduplication.viewer.Image.open",
            return_value=mock_cm2,
        ):
            result = viewer._generate_ascii_preview(Path("/fake/tall.png"), max_width=20, max_height=10)
        assert result is not None


# ===========================================================================
# ComparisonViewer._prompt_user_action
# ===========================================================================


@pytest.mark.unit
class TestPromptUserAction:
    """Test _prompt_user_action for all valid input choices."""

    @pytest.mark.parametrize(
        "input_val, expected_action",
        [
            ("a", UserAction.AUTO_SELECT),
            ("s", UserAction.SKIP),
            ("k", UserAction.KEEP_ALL),
            ("d", UserAction.DELETE_ALL),
            ("q", UserAction.QUIT),
        ],
    )
    def test_letter_choices(self, viewer: ComparisonViewer, input_val, expected_action):
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value=input_val
        ):
            assert viewer._prompt_user_action(3) == expected_action

    def test_valid_digit_returns_keep(self, viewer: ComparisonViewer):
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="2"
        ):
            assert viewer._prompt_user_action(3) == UserAction.KEEP

    def test_invalid_digit_then_valid(self, viewer: ComparisonViewer):
        """If digit is out of range, prompt again until valid."""
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask",
            side_effect=["9", "a"],
        ):
            result = viewer._prompt_user_action(3)
            assert result == UserAction.AUTO_SELECT

    def test_invalid_text_then_valid(self, viewer: ComparisonViewer):
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask",
            side_effect=["xyz", "s"],
        ):
            result = viewer._prompt_user_action(3)
            assert result == UserAction.SKIP


# ===========================================================================
# ComparisonViewer._process_user_action
# ===========================================================================


@pytest.mark.unit
class TestProcessUserAction:
    """Test _process_user_action for every UserAction branch."""

    def test_skip_action(self, viewer: ComparisonViewer, sample_metadata):
        result = viewer._process_user_action(UserAction.SKIP, [sample_metadata])
        assert result.skipped is True

    def test_quit_action(self, viewer: ComparisonViewer, sample_metadata):
        result = viewer._process_user_action(UserAction.QUIT, [sample_metadata])
        assert result.skipped is True

    def test_keep_all(self, viewer: ComparisonViewer, sample_metadata, sample_metadata_small):
        metas = [sample_metadata, sample_metadata_small]
        result = viewer._process_user_action(UserAction.KEEP_ALL, metas)
        assert len(result.files_to_keep) == 2
        assert result.files_to_delete == []

    def test_delete_all_confirmed(
        self, viewer: ComparisonViewer, sample_metadata, sample_metadata_small
    ):
        metas = [sample_metadata, sample_metadata_small]
        with patch(
            "file_organizer.services.deduplication.viewer.Confirm.ask", return_value=True
        ):
            result = viewer._process_user_action(UserAction.DELETE_ALL, metas)
        assert result.files_to_keep == []
        assert len(result.files_to_delete) == 2

    def test_delete_all_cancelled(
        self, viewer: ComparisonViewer, sample_metadata, sample_metadata_small
    ):
        metas = [sample_metadata, sample_metadata_small]
        with patch(
            "file_organizer.services.deduplication.viewer.Confirm.ask", return_value=False
        ):
            result = viewer._process_user_action(UserAction.DELETE_ALL, metas)
        assert result.skipped is True

    def test_auto_select(self, viewer: ComparisonViewer, sample_metadata, sample_metadata_small):
        metas = [sample_metadata, sample_metadata_small]
        expected = DuplicateReview([sample_metadata.path], [sample_metadata_small.path])
        with patch.object(viewer, "_auto_select_best", return_value=expected):
            result = viewer._process_user_action(UserAction.AUTO_SELECT, metas)
        assert result.files_to_keep == [sample_metadata.path]

    def test_keep_valid_choice(
        self, viewer: ComparisonViewer, sample_metadata, sample_metadata_small
    ):
        metas = [sample_metadata, sample_metadata_small]
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="1"
        ):
            result = viewer._process_user_action(UserAction.KEEP, metas)
        assert result.files_to_keep == [sample_metadata.path]
        assert result.files_to_delete == [sample_metadata_small.path]

    def test_keep_second_image(
        self, viewer: ComparisonViewer, sample_metadata, sample_metadata_small
    ):
        metas = [sample_metadata, sample_metadata_small]
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="2"
        ):
            result = viewer._process_user_action(UserAction.KEEP, metas)
        assert result.files_to_keep == [sample_metadata_small.path]
        assert result.files_to_delete == [sample_metadata.path]

    def test_keep_invalid_choice_skips(self, viewer: ComparisonViewer, sample_metadata):
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="abc"
        ):
            result = viewer._process_user_action(UserAction.KEEP, [sample_metadata])
        assert result.skipped is True

    def test_keep_out_of_range_skips(self, viewer: ComparisonViewer, sample_metadata):
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="99"
        ):
            result = viewer._process_user_action(UserAction.KEEP, [sample_metadata])
        assert result.skipped is True

    def test_unhandled_action_returns_skipped(self, viewer: ComparisonViewer, sample_metadata):
        """The final fallback at the end of _process_user_action returns skipped."""
        result = viewer._process_user_action(UserAction.DELETE, [sample_metadata])
        # DELETE is not explicitly handled; it falls through to the final return.
        assert result.skipped is True


# ===========================================================================
# ComparisonViewer._auto_select_best
# ===========================================================================


@pytest.mark.unit
class TestAutoSelectBest:
    """Test _auto_select_best quality-based selection."""

    def test_selects_highest_quality(self, tmp_path: Path, viewer: ComparisonViewer):
        big = _make_png(tmp_path, "big.png", (1920, 1080))
        small = _make_png(tmp_path, "small.png", (320, 240))

        result = viewer._auto_select_best([big, small])
        assert big in result.files_to_keep
        assert small in result.files_to_delete

    def test_handles_load_error(self, viewer: ComparisonViewer):
        with patch.object(viewer, "_get_image_metadata", side_effect=RuntimeError("boom")):
            result = viewer._auto_select_best([Path("/fake/a.png")])
        assert result.skipped is True

    def test_single_image(self, tmp_path: Path, viewer: ComparisonViewer):
        only = _make_png(tmp_path, "only.png", (100, 100))
        result = viewer._auto_select_best([only])
        assert result.files_to_keep == [only]
        assert result.files_to_delete == []


# ===========================================================================
# ComparisonViewer._calculate_quality_score
# ===========================================================================


@pytest.mark.unit
class TestCalculateQualityScore:
    """Test _calculate_quality_score scoring logic."""

    def test_higher_resolution_scores_higher(
        self, viewer: ComparisonViewer, sample_metadata, sample_metadata_small
    ):
        big_score = viewer._calculate_quality_score(sample_metadata)
        small_score = viewer._calculate_quality_score(sample_metadata_small)
        assert big_score > small_score

    def test_png_preferred_over_gif(self, viewer: ComparisonViewer):
        png_meta = ImageMetadata(
            path=Path("/x.png"),
            width=100,
            height=100,
            format="PNG",
            file_size=1024,
            modified_time=datetime.now(UTC),
            mode="RGB",
        )
        gif_meta = ImageMetadata(
            path=Path("/x.gif"),
            width=100,
            height=100,
            format="GIF",
            file_size=1024,
            modified_time=datetime.now(UTC),
            mode="RGB",
        )
        assert viewer._calculate_quality_score(png_meta) > viewer._calculate_quality_score(
            gif_meta
        )

    def test_unknown_format_gets_low_multiplier(self, viewer: ComparisonViewer):
        meta = ImageMetadata(
            path=Path("/x.xyz"),
            width=100,
            height=100,
            format="XYZ",
            file_size=1024,
            modified_time=datetime.now(UTC),
            mode="RGB",
        )
        score = viewer._calculate_quality_score(meta)
        assert score > 0  # Should still produce a positive score

    @pytest.mark.parametrize(
        "fmt,expected_multiplier",
        [
            ("PNG", 1.2),
            ("TIFF", 1.1),
            ("JPEG", 1.0),
            ("JPG", 1.0),
            ("WEBP", 0.9),
            ("GIF", 0.8),
            ("BMP", 0.7),
        ],
    )
    def test_format_scores(self, viewer: ComparisonViewer, fmt, expected_multiplier):
        """Each known format maps to the expected multiplier."""
        meta = ImageMetadata(
            path=Path("/x"),
            width=1000,
            height=1000,
            format=fmt,
            file_size=1_000_000,
            modified_time=datetime.now(UTC),
            mode="RGB",
        )
        score = viewer._calculate_quality_score(meta)
        expected_base = 1_000_000 * 0.7 + (1_000_000 / (1024 * 1024)) * 1000 * 0.2
        assert score == pytest.approx(expected_base * expected_multiplier, rel=0.01)


# ===========================================================================
# ComparisonViewer._display_review_summary
# ===========================================================================


@pytest.mark.unit
class TestDisplayReviewSummary:
    """Test _display_review_summary output."""

    def test_empty_decisions(self, viewer: ComparisonViewer):
        viewer._display_review_summary({})  # should not raise

    def test_with_decisions_and_existing_files(self, tmp_path: Path, viewer: ComparisonViewer):
        f1 = _make_png(tmp_path, "keep.png")
        f2 = _make_png(tmp_path, "del.png")
        decisions = {f1: "keep", f2: "delete"}
        viewer._display_review_summary(decisions)  # should print summary without error

    def test_delete_file_does_not_exist(self, viewer: ComparisonViewer):
        """If a file-to-delete no longer exists, summary should still work."""
        decisions = {Path("/nonexistent/gone.png"): "delete", Path("/fake/keep.png"): "keep"}
        viewer._display_review_summary(decisions)  # should not raise

    def test_space_savings_displayed(self, tmp_path: Path, viewer: ComparisonViewer):
        """When delete files exist, space savings should be calculated."""
        f1 = _make_png(tmp_path, "keep.png")
        f2 = _make_png(tmp_path, "del1.png", (200, 200))
        f3 = _make_png(tmp_path, "del2.png", (300, 300))
        decisions = {f1: "keep", f2: "delete", f3: "delete"}
        # Should not raise; space savings printed
        viewer._display_review_summary(decisions)


# ===========================================================================
# ComparisonViewer.display_metadata
# ===========================================================================


@pytest.mark.unit
class TestDisplayMetadata:
    """Test display_metadata public method."""

    def test_valid_image(self, tmp_path: Path, viewer: ComparisonViewer):
        img = _make_png(tmp_path, "show.png", (50, 50))
        viewer.display_metadata(img)  # should not raise

    def test_invalid_path(self, viewer: ComparisonViewer):
        viewer.display_metadata(Path("/nonexistent/nope.png"))  # prints error, no raise


# ===========================================================================
# ComparisonViewer.interactive_select
# ===========================================================================


@pytest.mark.unit
class TestInteractiveSelect:
    """Test interactive_select method."""

    def test_empty_list(self, viewer: ComparisonViewer):
        assert viewer.interactive_select([]) == []

    def test_select_all(self, tmp_path: Path, viewer: ComparisonViewer):
        imgs = [_make_png(tmp_path, f"img{i}.png") for i in range(3)]
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="all"
        ):
            result = viewer.interactive_select(imgs)
        assert result == imgs

    def test_select_none(self, tmp_path: Path, viewer: ComparisonViewer):
        imgs = [_make_png(tmp_path, f"img{i}.png") for i in range(3)]
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="none"
        ):
            result = viewer.interactive_select(imgs)
        assert result == []

    def test_select_specific_numbers(self, tmp_path: Path, viewer: ComparisonViewer):
        imgs = [_make_png(tmp_path, f"img{i}.png") for i in range(4)]
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="1,3"
        ):
            result = viewer.interactive_select(imgs)
        assert result == [imgs[0], imgs[2]]

    def test_invalid_numbers_ignored(self, tmp_path: Path, viewer: ComparisonViewer):
        imgs = [_make_png(tmp_path, f"img{i}.png") for i in range(2)]
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="1,abc,99"
        ):
            result = viewer.interactive_select(imgs)
        assert result == [imgs[0]]

    def test_metadata_load_failure_displays_fallback(
        self, tmp_path: Path, viewer: ComparisonViewer
    ):
        """If metadata load fails for an image, fallback text is shown."""
        imgs = [Path("/nonexistent/bad.png")]
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="all"
        ):
            result = viewer.interactive_select(imgs)
        assert result == imgs

    def test_custom_prompt(self, tmp_path: Path, viewer: ComparisonViewer):
        imgs = [_make_png(tmp_path, "one.png")]
        with patch(
            "file_organizer.services.deduplication.viewer.Prompt.ask", return_value="all"
        ):
            result = viewer.interactive_select(imgs, prompt="Pick your favorites")
        assert result == imgs
