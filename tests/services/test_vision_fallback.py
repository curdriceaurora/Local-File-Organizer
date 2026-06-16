"""Tests for ``services.vision_fallback`` (#406 — degraded categorization).

Covers the three resolution paths:
  1. EXIF DateTime / DateTimeOriginal → ``Images/Photos/YYYY/MM/``
  2. Filename pattern (Screenshot / IMG_YYYYMMDD)
  3. Generic ``Images/Untagged/`` bucket
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.services.vision_fallback import FallbackResult, compute_fallback

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


class TestComputeFallbackFilenamePatterns:
    """When EXIF is unavailable, filename heuristics drive the placement."""

    @patch("file_organizer.services.vision_fallback._from_exif", return_value=None)
    def test_screenshot_pattern(self, _mock_exif, tmp_path: Path) -> None:
        img = tmp_path / "Screenshot 2026-05-22 at 14.03.07.png"
        img.write_bytes(b"")

        result = compute_fallback(img)

        assert isinstance(result, FallbackResult)
        assert result.folder == "Images/Screenshots/2026"
        assert result.filename == img.stem
        assert result.source == "fallback_filename"

    @patch("file_organizer.services.vision_fallback._from_exif", return_value=None)
    def test_img_datestamp_pattern(self, _mock_exif, tmp_path: Path) -> None:
        img = tmp_path / "IMG_20260522_140307.jpg"
        img.write_bytes(b"")

        result = compute_fallback(img)

        assert result.folder == "Images/Photos/2026/05"
        assert result.source == "fallback_filename"

    @patch("file_organizer.services.vision_fallback._from_exif", return_value=None)
    def test_pxl_datestamp_pattern(self, _mock_exif, tmp_path: Path) -> None:
        # Google Pixel camera prefix
        img = tmp_path / "PXL_20260601_093015.jpg"
        img.write_bytes(b"")

        result = compute_fallback(img)

        assert result.folder == "Images/Photos/2026/06"
        assert result.source == "fallback_filename"

    @patch("file_organizer.services.vision_fallback._from_exif", return_value=None)
    def test_unknown_filename_falls_to_untagged(self, _mock_exif, tmp_path: Path) -> None:
        img = tmp_path / "random_photo_thing.png"
        img.write_bytes(b"")

        result = compute_fallback(img)

        assert result.folder == "Images/Untagged"
        assert result.filename == "random_photo_thing"
        assert result.source == "fallback_filename"


class TestComputeFallbackExif:
    """When EXIF carries a DateTime, it takes priority over filename heuristics."""

    @patch("file_organizer.services.vision_fallback._from_exif")
    @patch("file_organizer.services.vision_fallback._from_filename", return_value=None)
    def test_exif_datetime_wins(self, _mock_fname, mock_exif, tmp_path: Path) -> None:
        mock_exif.return_value = FallbackResult(
            folder="Images/Photos/2025/11",
            filename="DSC_0042",
            source="fallback_exif",
        )

        img = tmp_path / "DSC_0042.jpg"
        img.write_bytes(b"")

        result = compute_fallback(img)
        assert result.source == "fallback_exif"
        assert result.folder == "Images/Photos/2025/11"

    @patch("file_organizer.services.vision_fallback._from_exif")
    def test_exif_overrides_filename_screenshot(self, mock_exif, tmp_path: Path) -> None:
        # A "Screenshot YYYY-MM-DD" filename has a filename match, but EXIF wins.
        mock_exif.return_value = FallbackResult(
            folder="Images/Photos/2024/01",
            filename="Screenshot 2026-05-22",
            source="fallback_exif",
        )
        img = tmp_path / "Screenshot 2026-05-22 at 14.03.07.png"
        img.write_bytes(b"")

        result = compute_fallback(img)
        assert result.source == "fallback_exif"
        assert result.folder == "Images/Photos/2024/01"

    def test_pillow_unavailable_degrades_to_filename(self, tmp_path: Path) -> None:
        """An ImportError on Pillow does not break the fallback path."""
        img = tmp_path / "Screenshot 2026-05-22 at 14.03.07.png"
        img.write_bytes(b"")

        # The real _from_exif catches ImportError internally and returns None,
        # so EXIF resolution silently degrades to filename matching.
        with patch.dict("sys.modules", {"PIL": None}):
            result = compute_fallback(img)

        # Filename path still works
        assert result.source == "fallback_filename"
        assert result.folder == "Images/Screenshots/2026"


class TestComputeFallbackExifEndToEnd:
    """Exercise _from_exif with a real Pillow-encoded EXIF image (not mocked)."""

    def _write_image_with_exif(self, path: Path, date_str: str) -> None:
        """Create a 1x1 JPEG carrying DateTimeOriginal == date_str."""
        from PIL import Image
        from PIL.ExifTags import TAGS

        # Find numeric tag IDs by name so we don't hardcode magic numbers.
        date_tag = next(k for k, v in TAGS.items() if v == "DateTimeOriginal")

        img = Image.new("RGB", (1, 1), color="red")
        exif = img.getexif()
        exif[date_tag] = date_str
        img.save(path, "JPEG", exif=exif.tobytes())

    def test_real_exif_drives_year_month_folder(self, tmp_path: Path) -> None:
        """A JPEG carrying DateTimeOriginal=2025:11:15… lands in 2025/11."""
        pytest.importorskip("PIL")
        img = tmp_path / "DSC_0042.jpg"
        self._write_image_with_exif(img, "2025:11:15 14:30:00")

        result = compute_fallback(img)

        assert result.source == "fallback_exif"
        assert result.folder == "Images/Photos/2025/11"
        assert result.filename == "DSC_0042"

    def test_exif_datetime_only_drives_year_month_folder(self, tmp_path: Path) -> None:
        """A JPEG carrying only the standard DateTime tag (no DateTimeOriginal)
        still lands by EXIF date rather than degrading to filename (#1287 review)."""
        pytest.importorskip("PIL")
        from PIL import Image
        from PIL.ExifTags import TAGS

        datetime_tag = next(k for k, v in TAGS.items() if v == "DateTime")
        # Neutral filename (no date pattern) → filename path would be untagged,
        # so an EXIF-dated folder unambiguously proves the DateTime tag was used.
        img_path = tmp_path / "photo.jpg"
        img = Image.new("RGB", (1, 1), color="blue")
        exif = img.getexif()
        exif[datetime_tag] = "2025:11:15 14:30:00"
        img.save(img_path, "JPEG", exif=exif.tobytes())

        result = compute_fallback(img_path)

        assert result.source == "fallback_exif"
        assert result.folder == "Images/Photos/2025/11"
        assert result.filename == "photo"

    def test_image_without_exif_returns_none_from_exif(self, tmp_path: Path) -> None:
        """A bare image with no EXIF data → _from_exif returns None → filename path."""
        pytest.importorskip("PIL")
        from PIL import Image

        img_path = tmp_path / "Screenshot 2026-05-22 at 09.00.00.jpg"
        Image.new("RGB", (1, 1)).save(img_path, "JPEG")  # no exif kwarg

        result = compute_fallback(img_path)
        assert result.source == "fallback_filename"
        assert result.folder == "Images/Screenshots/2026"

    def test_exif_with_empty_datetime_value_falls_through(self, tmp_path: Path) -> None:
        """EXIF carries the DateTime tag but value is empty → falls through."""
        pytest.importorskip("PIL")
        from PIL import Image
        from PIL.ExifTags import TAGS

        date_tag = next(k for k, v in TAGS.items() if v == "DateTimeOriginal")
        img_path = tmp_path / "Screenshot 2026-05-22 at 09.00.00.jpg"
        img = Image.new("RGB", (1, 1))
        exif = img.getexif()
        exif[date_tag] = ""  # empty string
        img.save(img_path, "JPEG", exif=exif.tobytes())

        result = compute_fallback(img_path)
        # Filename path picks it up
        assert result.source == "fallback_filename"
        assert result.folder == "Images/Screenshots/2026"

    def test_real_exif_malformed_date_falls_through(self, tmp_path: Path) -> None:
        """An unparseable DateTimeOriginal string falls back to filename / untagged."""
        pytest.importorskip("PIL")
        img = tmp_path / "Screenshot 2024-07-04 at 09.30.00.png"
        self._write_image_with_exif(img, "not-a-real-date")

        # PNG won't actually round-trip EXIF via Pillow, but the function still
        # reaches the parse path and returns None on ValueError.  Filename
        # heuristic then catches the Screenshot pattern.
        result = compute_fallback(img)
        # PNG carries no round-trippable EXIF here, so the malformed-date EXIF
        # path yields None and the filename Screenshot heuristic takes over
        # deterministically — pin the concrete fallback, not just the type.
        assert isinstance(result, FallbackResult)
        assert result.source == "fallback_filename"
        assert result.folder == "Images/Screenshots/2024"
        assert result.filename == "Screenshot 2024-07-04 at 09.30.00"


class TestDispatcherTimeoutFallbackIntegration:
    """The dispatcher's timeout branch routes through compute_fallback (#406)."""

    def test_timed_out_image_becomes_fallback_not_failure(self, tmp_path: Path) -> None:
        """Vision timeout → ProcessedImage with source=fallback_*, no error."""
        from unittest.mock import MagicMock

        from file_organizer.core.dispatcher import process_image_files
        from file_organizer.parallel.processor import FileResult

        img = tmp_path / "Screenshot 2026-05-22 at 09.00.00.png"
        img.write_bytes(b"")

        # parallel_processor.process_batch_iter yields a single timed-out FileResult
        timed_out = FileResult(
            path=img,
            success=False,
            error="Timed out after 300.0s",
            non_retryable=True,
        )
        mock_parallel = MagicMock()
        mock_parallel.process_batch_iter.return_value = iter([timed_out])

        mock_vision = MagicMock()
        mock_console = MagicMock()

        results = process_image_files([img], mock_vision, mock_parallel, mock_console)

        assert len(results) == 1
        result = results[0]
        # Fallback placement, no error, source marker present
        assert result.error is None or result.error == ""
        assert result.folder_name == "Images/Screenshots/2026"
        assert result.source == "fallback_filename"

    def test_non_timeout_error_still_takes_failure_path(self, tmp_path: Path) -> None:
        """A non-timeout failure (e.g. read error) is NOT rerouted to fallback."""
        from unittest.mock import MagicMock

        from file_organizer.core.dispatcher import ERROR_FALLBACK_FOLDER, process_image_files
        from file_organizer.parallel.processor import FileResult

        img = tmp_path / "broken.png"
        img.write_bytes(b"")

        read_error = FileResult(
            path=img,
            success=False,
            error="PermissionError: [Errno 13] Permission denied",
        )
        mock_parallel = MagicMock()
        mock_parallel.process_batch_iter.return_value = iter([read_error])
        mock_vision = MagicMock()
        mock_console = MagicMock()

        results = process_image_files([img], mock_vision, mock_parallel, mock_console)

        assert len(results) == 1
        result = results[0]
        # Real failure: error preserved, folder is the error bucket
        assert result.error is not None
        assert "Permission denied" in result.error
        assert result.folder_name == ERROR_FALLBACK_FOLDER
        # Default source unchanged
        assert result.source == "vision"
