"""Tests for AudioPreprocessor class.

Tests format conversion, normalization, silence removal,
full preprocessing pipeline, and audio info retrieval.
External dependencies (ffmpeg, pydub) are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.audio.preprocessor import (
    AudioConfig,
    AudioFormat,
    AudioPreprocessor,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def preprocessor():
    """Create AudioPreprocessor with mocked ffmpeg check."""
    with patch.object(AudioPreprocessor, "_check_ffmpeg"):
        return AudioPreprocessor()


@pytest.fixture
def custom_config():
    """Create custom AudioConfig."""
    return AudioConfig(sample_rate=44100, channels=2, bit_rate="320k", codec="aac")


@pytest.fixture
def audio_file(tmp_path):
    """Create a fake audio file."""
    p = tmp_path / "test.mp3"
    p.write_bytes(b"fake audio data")
    return p


@pytest.fixture
def wav_file(tmp_path):
    """Create a fake wav file."""
    p = tmp_path / "test.wav"
    p.write_bytes(b"fake wav data")
    return p


# ---------------------------------------------------------------------------
# AudioFormat enum
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioFormat:
    """Tests for AudioFormat enum."""

    def test_values(self):
        assert AudioFormat.WAV == "wav"
        assert AudioFormat.MP3 == "mp3"
        assert AudioFormat.M4A == "m4a"
        assert AudioFormat.FLAC == "flac"
        assert AudioFormat.OGG == "ogg"
        assert AudioFormat.AAC == "aac"
        assert AudioFormat.WMA == "wma"
        assert AudioFormat.OPUS == "opus"


# ---------------------------------------------------------------------------
# AudioConfig
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioConfig:
    """Tests for AudioConfig dataclass."""

    def test_defaults(self):
        config = AudioConfig()
        assert config.sample_rate == 16000
        assert config.channels == 1
        assert config.bit_rate == "128k"
        assert config.codec == "pcm_s16le"

    def test_custom(self, custom_config):
        assert custom_config.sample_rate == 44100
        assert custom_config.channels == 2


# ---------------------------------------------------------------------------
# AudioPreprocessor init
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreprocessorInit:
    """Tests for AudioPreprocessor initialization."""

    def test_default_config(self, preprocessor):
        assert preprocessor.config.sample_rate == 16000
        assert preprocessor.config.channels == 1

    def test_custom_config(self, custom_config):
        with patch.object(AudioPreprocessor, "_check_ffmpeg"):
            pp = AudioPreprocessor(config=custom_config)
        assert pp.config.sample_rate == 44100

    def test_check_ffmpeg_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            pp = AudioPreprocessor()
            assert pp is not None

    def test_check_ffmpeg_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            pp = AudioPreprocessor()  # Should not raise
            assert pp is not None

    def test_check_ffmpeg_timeout(self):
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 5)):
            pp = AudioPreprocessor()
            assert pp is not None

    def test_check_ffmpeg_nonzero_return(self):
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            pp = AudioPreprocessor()
            assert pp is not None


# ---------------------------------------------------------------------------
# convert_to_wav
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConvertToWav:
    """Tests for convert_to_wav."""

    def test_file_not_found(self, preprocessor):
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            preprocessor.convert_to_wav("/nonexistent/audio.mp3")

    def test_ffmpeg_success(self, preprocessor, audio_file, tmp_path):
        out = tmp_path / "out.wav"
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = preprocessor.convert_to_wav(audio_file, output_path=out)
        assert result == out

    def test_ffmpeg_failure_raises(self, preprocessor, audio_file, tmp_path):
        out = tmp_path / "out.wav"
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "conversion error"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="ffmpeg conversion failed"):
                preprocessor.convert_to_wav(audio_file, output_path=out)

    def test_ffmpeg_not_found_falls_back_to_pydub(self, preprocessor, audio_file, tmp_path):
        out = tmp_path / "out.wav"

        with patch("subprocess.run", side_effect=FileNotFoundError("ffmpeg not found")):
            with patch.object(preprocessor, "_convert_with_pydub", return_value=out) as mock_pydub:
                result = preprocessor.convert_to_wav(audio_file, output_path=out)
                mock_pydub.assert_called_once()
                assert result == out

    def test_auto_output_path(self, preprocessor, audio_file):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = preprocessor.convert_to_wav(audio_file)
        assert str(result).endswith("_converted.wav")

    def test_custom_sample_rate_and_channels(self, preprocessor, audio_file, tmp_path):
        out = tmp_path / "out.wav"
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            preprocessor.convert_to_wav(audio_file, output_path=out, sample_rate=44100, channels=2)
            # Verify ffmpeg was called with correct args
            cmd = mock_run.call_args[0][0]
            assert "44100" in cmd
            assert "2" in cmd


# ---------------------------------------------------------------------------
# _convert_with_pydub
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConvertWithPydub:
    """Tests for _convert_with_pydub fallback."""

    def test_success(self, preprocessor, audio_file, tmp_path):
        out = tmp_path / "out.wav"
        mock_audio = MagicMock()

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = preprocessor._convert_with_pydub(audio_file, out, 16000, 1)
        assert result == out

    def test_no_pydub(self, preprocessor, audio_file, tmp_path):
        out = tmp_path / "out.wav"

        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError("no pydub")
            raise ImportError(f"no {name}")

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="Neither ffmpeg nor pydub"):
                preprocessor._convert_with_pydub(audio_file, out, 16000, 1)


# ---------------------------------------------------------------------------
# normalize_audio
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeAudio:
    """Tests for normalize_audio method."""

    def test_success(self, preprocessor, audio_file, tmp_path):
        out = tmp_path / "normalized.mp3"
        mock_pydub = MagicMock()
        mock_effects = MagicMock()
        mock_effects.normalize.return_value = MagicMock()

        with patch.dict("sys.modules", {"pydub": mock_pydub, "pydub.effects": mock_effects}):
            result = preprocessor.normalize_audio(audio_file, output_path=out)
        assert result == out

    def test_no_output_path(self, preprocessor, audio_file):
        mock_pydub = MagicMock()
        mock_effects = MagicMock()
        mock_effects.normalize.return_value = MagicMock()

        with patch.dict("sys.modules", {"pydub": mock_pydub, "pydub.effects": mock_effects}):
            result = preprocessor.normalize_audio(audio_file)
        assert result == audio_file

    def test_no_pydub(self, preprocessor, audio_file):
        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError
            raise ImportError

        with patch("builtins.__import__", side_effect=fake_import):
            result = preprocessor.normalize_audio(audio_file)
        assert result == audio_file


# ---------------------------------------------------------------------------
# remove_silence
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRemoveSilence:
    """Tests for remove_silence."""

    def test_success(self, preprocessor, audio_file, tmp_path):
        out = tmp_path / "trimmed.mp3"

        mock_audio = MagicMock()
        mock_audio.__getitem__ = MagicMock(return_value=MagicMock())

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio
        mock_pydub.AudioSegment.empty.return_value = MagicMock()

        mock_silence = MagicMock()
        mock_silence.detect_nonsilent.return_value = [(0, 1000), (2000, 3000)]

        with patch.dict(
            "sys.modules",
            {"pydub": mock_pydub, "pydub.silence": mock_silence},
        ):
            result = preprocessor.remove_silence(audio_file, output_path=out)
        assert result == out

    def test_no_nonsilent(self, preprocessor, audio_file):
        mock_pydub = MagicMock()
        mock_silence = MagicMock()
        mock_silence.detect_nonsilent.return_value = []

        with patch.dict(
            "sys.modules",
            {"pydub": mock_pydub, "pydub.silence": mock_silence},
        ):
            result = preprocessor.remove_silence(audio_file)
        assert result == audio_file

    def test_no_pydub(self, preprocessor, audio_file):
        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError
            raise ImportError

        with patch("builtins.__import__", side_effect=fake_import):
            result = preprocessor.remove_silence(audio_file)
        assert result == audio_file


# ---------------------------------------------------------------------------
# preprocess (pipeline)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreprocess:
    """Tests for the complete preprocessing pipeline."""

    def test_full_pipeline(self, preprocessor, audio_file, tmp_path):
        out = tmp_path / "preprocessed.wav"

        with patch.object(preprocessor, "convert_to_wav", return_value=out) as mock_conv:
            with patch.object(preprocessor, "normalize_audio", return_value=out) as mock_norm:
                with patch.object(preprocessor, "remove_silence", return_value=out) as mock_sil:
                    result = preprocessor.preprocess(
                        audio_file,
                        output_path=out,
                        convert_to_wav=True,
                        normalize=True,
                        remove_silence=True,
                    )
                    mock_conv.assert_called_once()
                    mock_norm.assert_called_once()
                    mock_sil.assert_called_once()
        assert result == out

    def test_skip_conversion_for_wav(self, preprocessor, wav_file):
        with patch.object(preprocessor, "normalize_audio", return_value=wav_file):
            result = preprocessor.preprocess(wav_file, convert_to_wav=True, normalize=True)
        assert result == wav_file

    def test_no_conversion(self, preprocessor, audio_file):
        with patch.object(preprocessor, "normalize_audio", return_value=audio_file):
            result = preprocessor.preprocess(
                audio_file, convert_to_wav=False, normalize=True, remove_silence=False
            )
        assert result == audio_file

    def test_normalize_only(self, preprocessor, audio_file):
        with patch.object(preprocessor, "normalize_audio", return_value=audio_file):
            result = preprocessor.preprocess(
                audio_file, convert_to_wav=False, normalize=True, remove_silence=False
            )
        assert result is not None

    def test_output_path_no_conversion(self, preprocessor, audio_file, tmp_path):
        """When output_path is set but convert_to_wav=False, copies file."""
        out = tmp_path / "output" / "processed.mp3"

        with patch.object(preprocessor, "normalize_audio", return_value=out):
            with patch("shutil.copy2"):
                preprocessor.preprocess(
                    audio_file,
                    output_path=out,
                    convert_to_wav=False,
                    normalize=True,
                    remove_silence=False,
                )


# ---------------------------------------------------------------------------
# get_audio_info
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAudioInfo:
    """Tests for get_audio_info static method."""

    def test_with_pydub(self, audio_file):
        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=5000)
        mock_audio.channels = 2
        mock_audio.frame_rate = 44100
        mock_audio.sample_width = 2
        mock_audio.frame_count.return_value = 220500

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_audio

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            info = AudioPreprocessor.get_audio_info(audio_file)

        assert info["duration_seconds"] == 5.0
        assert info["channels"] == 2
        assert info["sample_rate"] == 44100

    def test_no_pydub(self, audio_file):
        def fake_import(name, *args, **kwargs):
            if "pydub" in name:
                raise ImportError
            raise ImportError

        with patch("builtins.__import__", side_effect=fake_import):
            info = AudioPreprocessor.get_audio_info(audio_file)
        assert "error" in info


# ---------------------------------------------------------------------------
# is_supported_format
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsSupportedFormat:
    """Tests for is_supported_format static method."""

    def test_supported(self):
        assert AudioPreprocessor.is_supported_format("test.wav")
        assert AudioPreprocessor.is_supported_format("test.mp3")
        assert AudioPreprocessor.is_supported_format("test.flac")
        assert AudioPreprocessor.is_supported_format("test.ogg")

    def test_unsupported(self):
        assert not AudioPreprocessor.is_supported_format("test.xyz")
        assert not AudioPreprocessor.is_supported_format("test.mp4")

    def test_case_insensitive(self):
        assert AudioPreprocessor.is_supported_format("test.WAV")
        assert AudioPreprocessor.is_supported_format("test.Mp3")
