"""Tests for audio utility functions.

Tests audio duration, normalization, splitting, conversion, validation,
silence detection, trimming, merging, checksum, and peak amplitude.
All external dependencies (pydub, tinytag) are mocked.
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

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audio_file(tmp_path):
    """Create a fake audio file."""
    p = tmp_path / "test.mp3"
    p.write_bytes(b"fake audio data for testing")
    return p


@pytest.fixture
def wav_file(tmp_path):
    """Create a fake wav file."""
    p = tmp_path / "test.wav"
    p.write_bytes(b"fake wav data")
    return p


# ---------------------------------------------------------------------------
# get_audio_duration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAudioDuration:
    """Tests for get_audio_duration."""

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            get_audio_duration("/nonexistent/audio.mp3")

    def test_with_pydub(self, audio_file):
        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=5000)  # 5000 ms

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            duration = get_audio_duration(audio_file)
            assert duration == 5.0

    def test_fallback_to_tinytag(self, audio_file):
        mock_tag = MagicMock()
        mock_tag.duration = 3.5

        mock_tinytag = MagicMock()
        mock_tinytag.TinyTag.get.return_value = mock_tag

        # First import (pydub) fails, second (tinytag) succeeds
        def fake_import(name, *args, **kwargs):
            if name == "pydub":
                raise ImportError("no pydub")
            if name == "tinytag":
                return mock_tinytag
            raise ImportError(f"no {name}")

        with patch("builtins.__import__", side_effect=fake_import):
            duration = get_audio_duration(audio_file)

        assert duration == 3.5

    def test_no_audio_libs(self, audio_file):
        """When neither pydub nor tinytag is available."""
        def fake_import(name, *args, **kwargs):
            if name in ("pydub", "tinytag"):
                raise ImportError(f"no {name}")
            raise ImportError(f"no {name}")

        with patch("builtins.__import__", side_effect=fake_import):
            duration = get_audio_duration(audio_file)

        assert duration == 0.0


# ---------------------------------------------------------------------------
# normalize_audio
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeAudio:
    """Tests for normalize_audio."""

    def test_with_pydub(self, audio_file, tmp_path):
        mock_audio = MagicMock()
        mock_normalized = MagicMock()

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio
        mock_effects = MagicMock()
        mock_effects.normalize.return_value = mock_normalized

        with patch.dict(
            "sys.modules",
            {"pydub": mock_pydub, "pydub.effects": mock_effects},
        ):
            out = tmp_path / "normalized.mp3"
            result = normalize_audio(audio_file, output_path=out)
            assert result == out

    def test_no_output_path(self, audio_file):
        mock_pydub = MagicMock()
        mock_effects = MagicMock()
        mock_effects.normalize.return_value = MagicMock()

        with patch.dict(
            "sys.modules",
            {"pydub": mock_pydub, "pydub.effects": mock_effects},
        ):
            result = normalize_audio(audio_file)
            assert result == audio_file

    def test_no_pydub(self, audio_file):
        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError("no pydub")
            raise ImportError(f"no {name}")

        with patch("builtins.__import__", side_effect=fake_import):
            result = normalize_audio(audio_file)

        assert result == audio_file


# ---------------------------------------------------------------------------
# split_audio
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSplitAudio:
    """Tests for split_audio."""

    def test_split_success(self, audio_file, tmp_path):
        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=120000)  # 2 minutes
        mock_audio.__getitem__ = MagicMock(return_value=MagicMock())

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = split_audio(audio_file, chunk_length_ms=60000, output_dir=tmp_path)

        assert isinstance(result, list)
        assert len(result) == 2

    def test_no_pydub(self, audio_file):
        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError("no pydub")
            raise ImportError(f"no {name}")

        with patch("builtins.__import__", side_effect=fake_import):
            result = split_audio(audio_file)

        assert result == [audio_file]

    def test_default_output_dir(self, audio_file):
        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=30000)
        mock_audio.__getitem__ = MagicMock(return_value=MagicMock())

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = split_audio(audio_file)

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# convert_audio_format
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConvertAudioFormat:
    """Tests for convert_audio_format."""

    def test_convert_success(self, audio_file, tmp_path):
        mock_pydub = MagicMock()

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            out = tmp_path / "converted.wav"
            result = convert_audio_format(audio_file, "wav", output_path=out)
            assert result == out

    def test_auto_output_path(self, audio_file):
        mock_pydub = MagicMock()

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = convert_audio_format(audio_file, "wav")
            assert result == audio_file.with_suffix(".wav")

    def test_no_pydub(self, audio_file):
        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError("no pydub")
            raise ImportError(f"no {name}")

        with patch("builtins.__import__", side_effect=fake_import):
            result = convert_audio_format(audio_file, "wav")

        assert result == audio_file


# ---------------------------------------------------------------------------
# validate_audio_file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateAudioFile:
    """Tests for validate_audio_file."""

    def test_file_not_exists(self):
        valid, msg = validate_audio_file("/nonexistent/audio.mp3")
        assert not valid
        assert "does not exist" in msg

    def test_not_a_file(self, tmp_path):
        valid, msg = validate_audio_file(tmp_path)
        assert not valid
        assert "not a file" in msg

    def test_unsupported_extension(self, tmp_path):
        p = tmp_path / "file.xyz"
        p.write_bytes(b"data")
        valid, msg = validate_audio_file(p)
        assert not valid
        assert "Unsupported" in msg

    def test_valid_file(self, audio_file):
        with patch(
            "file_organizer.services.audio.utils.get_audio_duration", return_value=5.0
        ):
            valid, msg = validate_audio_file(audio_file)
        assert valid
        assert msg is None

    def test_zero_duration(self, audio_file):
        with patch(
            "file_organizer.services.audio.utils.get_audio_duration", return_value=0.0
        ):
            valid, msg = validate_audio_file(audio_file)
        assert not valid
        assert "zero duration" in msg

    def test_read_error(self, audio_file):
        with patch(
            "file_organizer.services.audio.utils.get_audio_duration",
            side_effect=Exception("corrupt"),
        ):
            valid, msg = validate_audio_file(audio_file)
        assert not valid
        assert "Failed to read" in msg


# ---------------------------------------------------------------------------
# detect_silence_segments
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectSilenceSegments:
    """Tests for detect_silence_segments."""

    def test_success(self, audio_file):
        mock_pydub = MagicMock()
        mock_silence = MagicMock()
        mock_silence.detect_silence.return_value = [(0, 1000), (5000, 6000)]

        with patch.dict(
            "sys.modules",
            {"pydub": mock_pydub, "pydub.silence": mock_silence},
        ):
            result = detect_silence_segments(audio_file)
        assert len(result) == 2

    def test_no_pydub(self, audio_file):
        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError("no pydub")
            raise ImportError(f"no {name}")

        with patch("builtins.__import__", side_effect=fake_import):
            result = detect_silence_segments(audio_file)
        assert result == []


# ---------------------------------------------------------------------------
# trim_audio
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTrimAudio:
    """Tests for trim_audio."""

    def test_success(self, audio_file, tmp_path):
        mock_audio = MagicMock()
        mock_audio.__getitem__ = MagicMock(return_value=MagicMock())

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            out = tmp_path / "trimmed.mp3"
            result = trim_audio(audio_file, start_ms=0, end_ms=5000, output_path=out)
            assert result == out

    def test_no_output_path(self, audio_file):
        mock_audio = MagicMock()
        mock_audio.__getitem__ = MagicMock(return_value=MagicMock())

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = trim_audio(audio_file)
            assert result == audio_file

    def test_no_pydub(self, audio_file):
        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError
            raise ImportError

        with patch("builtins.__import__", side_effect=fake_import):
            result = trim_audio(audio_file)
        assert result == audio_file


# ---------------------------------------------------------------------------
# merge_audio_files
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMergeAudioFiles:
    """Tests for merge_audio_files."""

    def test_merge_success(self, tmp_path):
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"fake1")
        f2.write_bytes(b"fake2")
        out = tmp_path / "merged.mp3"

        mock_empty = MagicMock()
        mock_empty.__iadd__ = MagicMock(return_value=mock_empty)
        mock_empty.__len__ = MagicMock(return_value=0)

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.empty.return_value = mock_empty
        mock_pydub.AudioSegment.from_file.return_value = MagicMock()

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = merge_audio_files([f1, f2], out)
            assert result == out

    def test_no_pydub_raises(self, tmp_path):
        out = tmp_path / "merged.mp3"

        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError
            raise ImportError

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError):
                merge_audio_files([], out)


# ---------------------------------------------------------------------------
# calculate_audio_checksum
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCalculateAudioChecksum:
    """Tests for calculate_audio_checksum."""

    def test_sha256(self, audio_file):
        result = calculate_audio_checksum(audio_file, algorithm="sha256")
        expected = hashlib.sha256(audio_file.read_bytes()).hexdigest()
        assert result == expected

    def test_md5(self, audio_file):
        result = calculate_audio_checksum(audio_file, algorithm="md5")
        expected = hashlib.md5(audio_file.read_bytes()).hexdigest()
        assert result == expected

    def test_sha1(self, audio_file):
        result = calculate_audio_checksum(audio_file, algorithm="sha1")
        expected = hashlib.sha1(audio_file.read_bytes()).hexdigest()
        assert result == expected


# ---------------------------------------------------------------------------
# get_audio_peak_amplitude
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAudioPeakAmplitude:
    """Tests for get_audio_peak_amplitude."""

    def test_success(self, audio_file):
        mock_audio = MagicMock()
        mock_audio.max_dBFS = -3.5

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = get_audio_peak_amplitude(audio_file)
        assert result == -3.5

    def test_no_pydub(self, audio_file):
        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError
            raise ImportError

        with patch("builtins.__import__", side_effect=fake_import):
            result = get_audio_peak_amplitude(audio_file)
        assert result == 0.0


# ---------------------------------------------------------------------------
# is_audio_file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsAudioFile:
    """Tests for is_audio_file."""

    def test_audio_extensions(self):
        assert is_audio_file("song.mp3")
        assert is_audio_file("track.wav")
        assert is_audio_file("voice.m4a")
        assert is_audio_file("music.flac")
        assert is_audio_file("audio.ogg")
        assert is_audio_file("file.aac")
        assert is_audio_file("record.wma")
        assert is_audio_file("stream.opus")

    def test_non_audio_extensions(self):
        assert not is_audio_file("image.jpg")
        assert not is_audio_file("doc.pdf")
        assert not is_audio_file("video.mp4")

    def test_case_insensitive(self):
        assert is_audio_file("song.MP3")
        assert is_audio_file("track.WAV")

    def test_path_objects(self):
        assert is_audio_file(Path("song.mp3"))
        assert not is_audio_file(Path("image.png"))
