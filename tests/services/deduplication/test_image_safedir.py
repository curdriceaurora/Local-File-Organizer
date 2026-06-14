"""Tests for the SafeDir-aware ``safedir_image_open`` helper and its
integration with the image-dedup utilities (WP-2.1, #264/#286).

This slice wires ``utils.safedir.SafeDir`` into the image-dedup ingestion
path: every ``PIL.Image.open(...)`` in
``services/deduplication/{image_utils,image_dedup}.py`` now goes through
``safedir_image_open`` so a symlink swapped into the organize root between
the directory walk and the read is refused with ``SymlinkRejected`` rather
than dereferenced. (The ``viewer.py`` / ``quality.py`` read paths are a
separate follow-up slice and are out of scope here.)

Verifies:

- ``safedir_image_open`` opens a real image and yields a PIL.Image
- Symlinks under the SafeDir root are refused
- On Windows (``NotImplementedError``) the helper falls back to direct
  ``Image.open(path)``
- The downstream utility functions
  (``get_image_metadata`` / ``get_image_dimensions`` / etc.) route
  symlinks to the same safe-default returns as other I/O errors
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image as _PILImage

from file_organizer.services.deduplication.image_utils import (
    get_image_dimensions,
    get_image_format,
    get_image_metadata,
    safedir_image_open,
    validate_image_file,
)
from file_organizer.utils.safedir import SymlinkRejected

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only"),
]


def _make_jpeg(path: Path, size: tuple[int, int] = (8, 8)) -> None:
    """Write a tiny JPEG to ``path`` for round-trip tests."""
    img = _PILImage.new("RGB", size, color=(100, 150, 200))
    img.save(path, format="JPEG")


class TestSafedirImageOpenHelper:
    def test_opens_real_image(self, tmp_path: Path) -> None:
        target = tmp_path / "photo.jpg"
        _make_jpeg(target, size=(16, 8))
        with safedir_image_open(target) as (img, _fd):
            assert img.size == (16, 8)
            assert img.format == "JPEG"

    def test_refuses_symlinked_image(self, tmp_path: Path) -> None:
        """A symlinked image in the organize root must be refused —
        ``SafeDir.open_for_reader`` raises ``SymlinkRejected``, which
        is an ``OSError`` subclass.
        """
        real = tmp_path / "secret.jpg"
        _make_jpeg(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "decoy.jpg").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")

        with pytest.raises(SymlinkRejected):
            with safedir_image_open(organize / "decoy.jpg"):
                pass

    def test_falls_back_to_path_open_when_safedir_not_implemented(self, tmp_path: Path) -> None:
        """When SafeDir.open_root raises NotImplementedError (Windows-style
        port not available), the helper falls back to direct
        ``Image.open(path)`` — preserves the legacy API surface.
        """
        target = tmp_path / "fallback.jpg"
        _make_jpeg(target)
        with patch(
            "file_organizer.services.deduplication.image_utils.SafeDir.open_root",
            side_effect=NotImplementedError("simulated unavailable SafeDir"),
        ):
            with safedir_image_open(target) as (img, _fd):
                assert img.size == (8, 8)

    def test_closes_fd_when_fdopen_raises(self, tmp_path: Path) -> None:
        """If ``os.fdopen`` raises (e.g. transient OSError on a closed
        dir_fd race), the helper must close the raw fd returned by
        ``open_for_reader`` before the exception propagates — otherwise
        we leak a descriptor. Verified via patch on ``os.fdopen``.

        ``os.close`` is patched with ``side_effect=os.close`` (i.e. the
        real ``os.close``) so the leak guard's call AND SafeDir's own
        dir_fd cleanup actually close their fds — patching with a bare
        ``MagicMock`` would just record the calls and leak the fds
        during the test run (Copilot #281 review).
        """
        target = tmp_path / "fd_leak_test.jpg"
        _make_jpeg(target)
        real_os_close = os.close  # capture before patching
        with patch(
            "file_organizer.services.deduplication.image_utils.os.fdopen",
            side_effect=OSError("synthetic fdopen failure"),
        ) as mock_fdopen:
            with patch(
                "file_organizer.services.deduplication.image_utils.os.close",
                side_effect=real_os_close,
            ) as mock_close:
                with pytest.raises(OSError, match="synthetic fdopen failure"):
                    with safedir_image_open(target):
                        pass
                # The raw fd from SafeDir.open_for_reader must be reclaimed when
                # os.fdopen raises. Assert the concrete effect: the exact fd
                # that ``os.fdopen`` tried to wrap is among the closed fds.
                # (SafeDir.__exit__ also closes its own dir_fd, so we assert fd
                # membership rather than a weak call-count lower bound.)
                fdopen_fd = mock_fdopen.call_args[0][0]
                assert isinstance(fdopen_fd, int) and fdopen_fd >= 0
                closed_fds = {call.args[0] for call in mock_close.call_args_list}
                assert fdopen_fd in closed_fds


class TestImageUtilsRoutesThroughHelper:
    """The migrated image_utils functions return the legacy safe-default
    ``None`` when the underlying image is unreadable. Symlink rejection is
    just another OSError and routes the same way."""

    def test_get_image_metadata_returns_none_on_symlink(self, tmp_path: Path) -> None:
        real = tmp_path / "real.jpg"
        _make_jpeg(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "link.jpg").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")

        out = get_image_metadata(organize / "link.jpg")
        assert out is None

    def test_get_image_dimensions_returns_none_on_symlink(self, tmp_path: Path) -> None:
        real = tmp_path / "real.jpg"
        _make_jpeg(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "link.jpg").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")

        assert get_image_dimensions(organize / "link.jpg") is None

    def test_get_image_format_returns_none_on_symlink(self, tmp_path: Path) -> None:
        real = tmp_path / "real.jpg"
        _make_jpeg(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "link.jpg").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")

        assert get_image_format(organize / "link.jpg") is None

    def test_validate_image_file_rejects_symlink(self, tmp_path: Path) -> None:
        """``validate_image_file`` exists-checks first (the symlink itself
        exists), then tries to open via SafeDir — which refuses. The
        function returns ``(False, "...")``.
        """
        real = tmp_path / "real.jpg"
        _make_jpeg(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "link.jpg").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")

        is_valid, err = validate_image_file(organize / "link.jpg")
        assert is_valid is False
        assert err is not None

    def test_get_image_metadata_happy_path(self, tmp_path: Path) -> None:
        target = tmp_path / "p.jpg"
        _make_jpeg(target, size=(20, 10))
        meta = get_image_metadata(target)
        assert meta is not None
        assert meta.width == 20
        assert meta.height == 10
        assert meta.format == "JPEG"
        assert meta.size_bytes > 0


class TestImageDedupValidateRefusesSymlinks:
    """The ``ImageDeduplicator.validate_image`` flow now goes through
    ``safedir_image_open`` — symlinks return ``(False, "Cannot read
    image: ...")``."""

    def test_validate_refuses_symlinked_image(self, tmp_path: Path) -> None:
        pytest.importorskip("imagededup")  # dedup-image extra not in [dev,search]
        from file_organizer.services.deduplication.image_dedup import ImageDeduplicator

        real = tmp_path / "real.jpg"
        _make_jpeg(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "decoy.jpg").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")

        dedup = ImageDeduplicator()
        is_valid, err = dedup.validate_image(organize / "decoy.jpg")
        assert is_valid is False
        assert err is not None
        assert "Cannot read image" in err or "symlink" in err.lower()


class TestGetImageHashErrorBranches:
    """Cover the new error-handling branches in ``ImageDeduplicator.
    get_image_hash`` introduced by PR3f's SafeDir-routed hashing
    (#281 reviews). These run with mocked imagededup so they don't
    need the ``dedup-image`` extra installed.
    """

    def _make_dedup(self):
        """Build an ImageDeduplicator with a controllable hasher mock.

        Patches the imagededup availability flag so the constructor
        succeeds even when the optional extra is absent (CI matrix).
        """
        from unittest.mock import MagicMock
        from unittest.mock import patch as _patch

        from file_organizer.services.deduplication import image_dedup as _id

        with (
            _patch.object(_id, "_IMAGEDEDUP_AVAILABLE", True),
            _patch.object(_id, "PHash", MagicMock(return_value=MagicMock())),
            _patch.object(_id, "DHash", MagicMock(return_value=MagicMock())),
            _patch.object(_id, "AHash", MagicMock(return_value=MagicMock())),
        ):
            d = _id.ImageDeduplicator()
        d.hasher = MagicMock()
        return d

    def test_decompression_bomb_returns_none(self, tmp_path: Path) -> None:
        """DecompressionBombError on Image.open is caught and returns
        None — must not abort a find_duplicates / batch_compute_hashes
        scan."""
        from PIL.Image import DecompressionBombError

        img = tmp_path / "bomb.jpg"
        img.write_bytes(b"\x00")  # bytes irrelevant; we patch safedir_image_open

        dedup = self._make_dedup()
        with patch(
            "file_organizer.services.deduplication.image_dedup.safedir_image_open",
            side_effect=DecompressionBombError("synthetic bomb"),
        ):
            result = dedup.get_image_hash(img)
        assert result is None

    def test_non_rgb_image_is_converted(self, tmp_path: Path) -> None:
        """Non-RGB images (e.g. RGBA, L) are converted before being
        handed to imagededup as a numpy array. Exercises the
        ``img.mode != "RGB": img = img.convert("RGB")`` branch.
        """
        from unittest.mock import MagicMock

        img = tmp_path / "rgba.png"
        _make_jpeg(img)

        # Mock the helper to return a non-RGB image.
        mock_rgba_img = MagicMock()
        mock_rgba_img.mode = "RGBA"
        mock_rgb_img = MagicMock()
        mock_rgb_img.mode = "RGB"
        mock_rgba_img.convert.return_value = mock_rgb_img

        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=(mock_rgba_img, None))
        mock_cm.__exit__ = MagicMock(return_value=False)

        dedup = self._make_dedup()
        dedup.hasher.encode_image.return_value = "deadbeef"

        import numpy as np

        # Provide a real 3-channel uint8 array so the RGB conversion and
        # ``np.ascontiguousarray`` path run (get_image_hash passes an RGB
        # array straight to imagededup — no channel reversal).
        fake_rgb = np.zeros((4, 4, 3), dtype=np.uint8)
        with (
            patch(
                "file_organizer.services.deduplication.image_dedup.safedir_image_open",
                return_value=mock_cm,
            ),
            patch("numpy.asarray", return_value=fake_rgb),
        ):
            result = dedup.get_image_hash(img)

        assert result == "deadbeef"
        # The non-RGB branch was taken: convert("RGB") called once.
        mock_rgba_img.convert.assert_called_once_with("RGB")
        # imagededup received a contiguous RGB 3-channel array.
        # ``ascontiguousarray`` is preserved for future-proofing even
        # though plain ``np.asarray(img)`` is already C-contiguous —
        # the assertion locks the contract.
        passed_array = dedup.hasher.encode_image.call_args.kwargs["image_array"]
        assert passed_array.shape == (4, 4, 3)
        assert passed_array.flags["C_CONTIGUOUS"]


class TestHashEquivalenceWithPathCodepath:
    """The SafeDir-routed ``get_image_hash`` must produce the same
    perceptual hash as imagededup's path-based ``encode_image(path)``
    flow — otherwise the migration silently breaks dedup matches on
    existing corpora. This test runs with REAL imagededup installed
    and asserts byte-for-byte hash equality between the two paths.

    Skipped when ``imagededup`` is absent (CI matrix without the
    dedup-image extra). Locally with the extra installed this is the
    regression test that catches channel-order / preprocessing
    mismatches like the one Codex flagged on PR3f.
    """

    def test_safedir_hash_matches_path_hash(self, tmp_path: Path) -> None:
        # ``test_image_dedup.py`` injects a fake ``imagededup`` into
        # ``sys.modules`` via ``setdefault`` when the real extra is
        # absent, which means a plain ``importorskip("imagededup")``
        # succeeds against the mock and the test would then fail
        # calling real hash methods. Probe a submodule the fake doesn't
        # provide instead — it only exists when the actual library is
        # installed.
        pytest.importorskip("imagededup.utils.image_utils")
        # A color photo where R/B differ noticeably, so any R/B swap
        # would produce a clearly different perceptual hash.
        from PIL import Image as _PILImage

        from file_organizer.services.deduplication.image_dedup import ImageDeduplicator

        target = tmp_path / "color.jpg"
        # Diagonal gradient with strong red dominance so the grayscale
        # luminance differs from a B-dominant version.
        img = _PILImage.new("RGB", (32, 32))
        pixels = img.load()
        for y in range(32):
            for x in range(32):
                pixels[x, y] = (200 + (x % 16), 50, 30 + (y % 32))
        img.save(target, format="JPEG", quality=95)

        dedup = ImageDeduplicator(hash_method="phash")
        # Path-based reference hash (what imagededup would compute on
        # its own, no SafeDir involved).
        reference = dedup.hasher.encode_image(image_file=str(target))

        # SafeDir-routed hash via our refactored get_image_hash.
        safedir_hash = dedup.get_image_hash(target)

        assert safedir_hash == reference, (
            f"SafeDir hash {safedir_hash!r} != path-based reference "
            f"{reference!r} — channel ordering or preprocessing drift"
        )
