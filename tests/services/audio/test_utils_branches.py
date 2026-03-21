"""Branch-coverage tests for audio utility functions.

Targets the 134 lines missing from the 9% baseline in
src/file_organizer/services/audio/utils.py.  Every test class carries
@pytest.mark.integration as requested.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.audio.utils import (
    calculate_audio_checksum,
    convert_audio_format,
    detect_silence_segments,
    get_audio_duration,
    get_audio_peak_amplitude,
    is_audio_file,
    merge_audio_files,
    normalize_audio,
    split_audio,
    trim_audio,
    validate_audio_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_import_no_pydub(name: str, *args, **kwargs):
    """Side-effect for builtins.__import__ that blocks every import."""
    raise ImportError(f"no {name}")


# ---------------------------------------------------------------------------
# get_audio_duration — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetAudioDurationBranches:
    """Covers tinytag fallback where duration is None (returns 0.0 via `or 0.0`)."""

    def test_tinytag_duration_none_returns_zero(self, tmp_path: Path) -> None:
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"fake audio")

        mock_tag = MagicMock()
        mock_tag.duration = None  # tag exists but duration is None

        mock_tinytag = MagicMock()
        mock_tinytag.TinyTag.get.return_value = mock_tag

        def fake_import(name, *args, **kwargs):
            if name == "pydub":
                raise ImportError("no pydub")
            if name == "tinytag":
                return mock_tinytag
            raise ImportError(f"no {name}")

        with patch("builtins.__import__", side_effect=fake_import):
            duration = get_audio_duration(audio)

        assert duration == 0.0

    def test_string_path_converted_to_path(self, tmp_path: Path) -> None:
        """Passes a str path; verifies coercion and correct return value."""
        audio = tmp_path / "clip.mp3"
        audio.write_bytes(b"audio bytes")

        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=2000)

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            duration = get_audio_duration(str(audio))

        assert duration == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# normalize_audio — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestNormalizeAudioBranches:
    """Covers custom target_db and explicit output_path as string."""

    def test_explicit_string_output_path(self, tmp_path: Path) -> None:
        src = tmp_path / "input.mp3"
        src.write_bytes(b"audio")
        out = tmp_path / "out.mp3"

        mock_pydub = MagicMock()
        mock_effects = MagicMock()
        mock_effects.normalize.return_value = MagicMock()

        with patch.dict("sys.modules", {"pydub": mock_pydub, "pydub.effects": mock_effects}):
            result = normalize_audio(src, output_path=str(out), target_db=-14.0)

        assert result == out

    def test_normalize_calls_effects_with_headroom(self, tmp_path: Path) -> None:
        src = tmp_path / "input.wav"
        src.write_bytes(b"wav")
        out = tmp_path / "norm.wav"

        mock_audio_obj = MagicMock()
        mock_normalized_obj = MagicMock()

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio_obj
        mock_effects = MagicMock()
        mock_effects.normalize.return_value = mock_normalized_obj

        with patch.dict("sys.modules", {"pydub": mock_pydub, "pydub.effects": mock_effects}):
            result = normalize_audio(src, output_path=out, target_db=-20.0)

        # headroom should be abs(target_db) = 20.0
        mock_effects.normalize.assert_called_once_with(mock_audio_obj, headroom=20.0)
        mock_normalized_obj.export.assert_called_once_with(str(out), format="wav")
        assert result == out


# ---------------------------------------------------------------------------
# split_audio — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSplitAudioBranches:
    """Covers custom output_dir (mkdir path) and chunk naming."""

    def test_custom_output_dir_is_created(self, tmp_path: Path) -> None:
        src = tmp_path / "long.mp3"
        src.write_bytes(b"audio data")
        out_dir = tmp_path / "chunks"  # does not yet exist

        # Audio is exactly 90 000 ms → 2 chunks of 60 000 ms
        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=90000)
        chunk_mock = MagicMock()
        mock_audio.__getitem__ = MagicMock(return_value=chunk_mock)

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = split_audio(src, chunk_length_ms=60000, output_dir=out_dir)

        assert out_dir.is_dir()
        assert len(result) == 2
        assert result[0] == out_dir / "long_chunk_000.mp3"
        assert result[1] == out_dir / "long_chunk_001.mp3"

    def test_chunk_export_called_for_each_chunk(self, tmp_path: Path) -> None:
        src = tmp_path / "audio.wav"
        src.write_bytes(b"x")
        out_dir = tmp_path / "out"

        chunk_mock = MagicMock()
        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=120000)
        mock_audio.__getitem__ = MagicMock(return_value=chunk_mock)

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = split_audio(src, chunk_length_ms=60000, output_dir=out_dir)

        assert len(result) == 2
        assert chunk_mock.export.call_count == 2
        # Verify format is derived from suffix
        chunk_mock.export.assert_any_call(str(result[0]), format="wav")
        chunk_mock.export.assert_any_call(str(result[1]), format="wav")


# ---------------------------------------------------------------------------
# convert_audio_format — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestConvertAudioFormatBranches:
    """Covers custom bitrate and string output_path."""

    def test_custom_bitrate_passed_to_export(self, tmp_path: Path) -> None:
        src = tmp_path / "track.mp3"
        src.write_bytes(b"audio")
        out = tmp_path / "track.flac"

        mock_audio_obj = MagicMock()
        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio_obj

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = convert_audio_format(src, "flac", output_path=out, bitrate="320k")

        mock_audio_obj.export.assert_called_once_with(str(out), format="flac", bitrate="320k")
        assert result == out

    def test_string_output_path_converted(self, tmp_path: Path) -> None:
        src = tmp_path / "input.mp3"
        src.write_bytes(b"audio")
        out = tmp_path / "output.wav"

        mock_pydub = MagicMock()

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = convert_audio_format(src, "wav", output_path=str(out))

        assert result == out


# ---------------------------------------------------------------------------
# validate_audio_file — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestValidateAudioFileBranches:
    """Covers all validate_audio_file branches not in existing unit tests."""

    def test_negative_duration_returns_invalid(self, tmp_path: Path) -> None:
        """duration <= 0 branch — negative value."""
        audio = tmp_path / "silent.mp3"
        audio.write_bytes(b"audio")

        with patch("file_organizer.services.audio.utils.get_audio_duration", return_value=-1.0):
            valid, msg = validate_audio_file(audio)

        assert valid is False
        assert msg is not None
        assert "zero duration" in msg

    def test_all_supported_extensions_pass_extension_check(self, tmp_path: Path) -> None:
        """Every extension in supported_extensions reaches the duration check."""
        supported = [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus"]
        for ext in supported:
            audio = tmp_path / f"test{ext}"
            audio.write_bytes(b"x")
            with patch("file_organizer.services.audio.utils.get_audio_duration", return_value=1.0):
                valid, msg = validate_audio_file(audio)
            assert valid is True, f"Extension {ext} should be valid"
            assert msg is None

    def test_path_object_input(self, tmp_path: Path) -> None:
        """Accepts a Path object directly."""
        audio = tmp_path / "song.flac"
        audio.write_bytes(b"flac data")
        with patch("file_organizer.services.audio.utils.get_audio_duration", return_value=3.0):
            valid, msg = validate_audio_file(audio)
        assert valid is True
        assert msg is None


# ---------------------------------------------------------------------------
# detect_silence_segments — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDetectSilenceBranches:
    """Covers custom threshold and min_silence_len parameters."""

    def test_custom_params_forwarded(self, tmp_path: Path) -> None:
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"x")

        mock_audio_obj = MagicMock()
        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio_obj
        mock_silence = MagicMock()
        mock_silence.detect_silence.return_value = [(500, 1500)]

        with patch.dict("sys.modules", {"pydub": mock_pydub, "pydub.silence": mock_silence}):
            result = detect_silence_segments(audio, silence_thresh=-50, min_silence_len=500)

        mock_silence.detect_silence.assert_called_once_with(
            mock_audio_obj, min_silence_len=500, silence_thresh=-50
        )
        assert len(result) == 1
        assert result[0] == (500, 1500)

    def test_returns_empty_list_on_no_silence(self, tmp_path: Path) -> None:
        audio = tmp_path / "voice.mp3"
        audio.write_bytes(b"x")

        mock_pydub = MagicMock()
        mock_silence = MagicMock()
        mock_silence.detect_silence.return_value = []

        with patch.dict("sys.modules", {"pydub": mock_pydub, "pydub.silence": mock_silence}):
            result = detect_silence_segments(audio)

        assert result == []


# ---------------------------------------------------------------------------
# trim_audio — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTrimAudioBranches:
    """Covers trim with start_ms only (end_ms=None) and string path inputs."""

    def test_trim_with_no_end_ms(self, tmp_path: Path) -> None:
        src = tmp_path / "long.mp3"
        src.write_bytes(b"audio")
        out = tmp_path / "trimmed.mp3"

        chunk_mock = MagicMock()
        mock_audio = MagicMock()
        mock_audio.__getitem__ = MagicMock(return_value=chunk_mock)

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = trim_audio(src, start_ms=5000, end_ms=None, output_path=out)

        # end_ms=None means audio[5000:None] — slices to end
        mock_audio.__getitem__.assert_called_once_with(slice(5000, None))
        assert result == out

    def test_string_path_inputs(self, tmp_path: Path) -> None:
        src = tmp_path / "src.wav"
        src.write_bytes(b"wav")
        out = tmp_path / "out.wav"

        chunk_mock = MagicMock()
        mock_audio = MagicMock()
        mock_audio.__getitem__ = MagicMock(return_value=chunk_mock)

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = trim_audio(str(src), start_ms=0, end_ms=3000, output_path=str(out))

        assert result == out


# ---------------------------------------------------------------------------
# merge_audio_files — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMergeAudioFilesBranches:
    """Covers crossfade_ms > 0 path and output_dir creation."""

    def test_crossfade_path_uses_append(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"a")
        f2.write_bytes(b"b")
        out = tmp_path / "merged.mp3"

        # First segment: merged is initially empty (__len__=0), so no crossfade on first
        # Second segment: merged is non-empty (__len__>0), so crossfade is triggered
        merged_mock = MagicMock()
        merged_mock.__len__ = MagicMock(side_effect=[0, 1000])
        merged_mock.append.return_value = merged_mock
        merged_mock.__iadd__ = MagicMock(return_value=merged_mock)

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.empty.return_value = merged_mock
        mock_pydub.AudioSegment.from_file.return_value = MagicMock()

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = merge_audio_files([f1, f2], out, crossfade_ms=500)

        # append() should be called once (for f2, when merged has length > 0)
        merged_mock.append.assert_called_once()
        call_args = merged_mock.append.call_args
        assert call_args.kwargs.get("crossfade") == 500 or call_args[1].get("crossfade") == 500
        assert result == out

    def test_output_parent_dir_created_if_missing(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.mp3"
        f1.write_bytes(b"a")
        nested_out = tmp_path / "deep" / "nested" / "merged.mp3"

        merged_mock = MagicMock()
        merged_mock.__len__ = MagicMock(return_value=0)
        merged_mock.__iadd__ = MagicMock(return_value=merged_mock)

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.empty.return_value = merged_mock
        mock_pydub.AudioSegment.from_file.return_value = MagicMock()

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = merge_audio_files([f1], nested_out)

        assert nested_out.parent.is_dir()
        assert result == nested_out


# ---------------------------------------------------------------------------
# calculate_audio_checksum — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCalculateAudioChecksumBranches:
    """Covers multi-chunk reads (large file) and deterministic output."""

    def test_large_file_multiple_chunks(self, tmp_path: Path) -> None:
        audio = tmp_path / "large.flac"
        # Write > 4096 bytes to force multiple chunk reads
        data = b"A" * 10000
        audio.write_bytes(data)

        result = calculate_audio_checksum(audio, algorithm="sha256")
        expected = hashlib.sha256(data).hexdigest()

        assert result == expected

    def test_empty_file_checksum(self, tmp_path: Path) -> None:
        audio = tmp_path / "empty.mp3"
        audio.write_bytes(b"")

        result = calculate_audio_checksum(audio, algorithm="sha256")
        expected = hashlib.sha256(b"").hexdigest()

        assert result == expected

    def test_default_algorithm_is_sha256(self, tmp_path: Path) -> None:
        audio = tmp_path / "track.mp3"
        content = b"test content for checksum"
        audio.write_bytes(content)

        result = calculate_audio_checksum(audio)
        expected = hashlib.sha256(content).hexdigest()

        assert result == expected


# ---------------------------------------------------------------------------
# get_audio_peak_amplitude — missing branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetAudioPeakAmplitudeBranches:
    """Covers positive amplitude and string path input."""

    def test_positive_amplitude(self, tmp_path: Path) -> None:
        audio = tmp_path / "loud.wav"
        audio.write_bytes(b"wav data")

        mock_audio_obj = MagicMock()
        mock_audio_obj.max_dBFS = 0.0

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio_obj

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = get_audio_peak_amplitude(audio)

        assert result == pytest.approx(0.0)

    def test_string_path_accepted(self, tmp_path: Path) -> None:
        audio = tmp_path / "clip.mp3"
        audio.write_bytes(b"data")

        mock_audio_obj = MagicMock()
        mock_audio_obj.max_dBFS = -6.0

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio_obj

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = get_audio_peak_amplitude(str(audio))

        assert result == pytest.approx(-6.0)


# ---------------------------------------------------------------------------
# is_audio_file — negative / edge cases
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIsAudioFileBranches:
    """Covers edge cases: no extension, hidden files, mixed-case paths."""

    def test_no_extension_is_not_audio(self) -> None:
        assert is_audio_file("audiofile_without_extension") is False

    def test_empty_string_is_not_audio(self) -> None:
        assert is_audio_file("") is False

    def test_dot_only_extension_is_not_audio(self) -> None:
        assert is_audio_file("file.") is False

    def test_uppercase_extensions_are_audio(self) -> None:
        assert is_audio_file("TRACK.FLAC") is True
        assert is_audio_file("VOICE.AAC") is True
        assert is_audio_file("RECORD.WMA") is True
        assert is_audio_file("STREAM.OPUS") is True

    def test_video_extension_is_not_audio(self) -> None:
        assert is_audio_file("video.mp4") is False
        assert is_audio_file("clip.avi") is False

    def test_path_with_audio_extension_in_dirname_not_filename(self) -> None:
        # The directory has .mp3 in name but the file has .txt extension
        # is_audio_file uses suffix of the full path, so it checks the last component
        p = Path("/audio.mp3/actual_file.txt")
        assert is_audio_file(p) is False


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    """Create a minimal fake audio file on disk."""
    p = tmp_path / "sample.mp3"
    p.write_bytes(b"fake audio bytes")
    return p


@pytest.mark.integration
class TestDetectSilenceSegmentsBranches:
    """Integration coverage for detect_silence_segments ImportError branch."""

    def test_no_pydub_returns_empty_list(self, audio_file: Path) -> None:
        """Lines 221-223: ImportError → warning logged, returns []."""

        def _no_pydub(name: str, *args: object, **kwargs: object) -> object:
            if "pydub" in name:
                raise ImportError("no pydub")
            raise ImportError(f"no {name}")

        with patch("builtins.__import__", side_effect=_no_pydub):
            result = detect_silence_segments(audio_file)

        assert result == []
