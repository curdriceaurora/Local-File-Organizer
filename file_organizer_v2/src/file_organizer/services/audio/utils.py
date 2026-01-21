"""
Audio Utility Functions

Common utility functions for audio file processing and analysis.
"""

from pathlib import Path
from typing import List, Optional, Tuple, Union
import logging

logger = logging.getLogger(__name__)


def get_audio_duration(audio_path: Union[str, Path]) -> float:
    """
    Get audio file duration in seconds.

    Args:
        audio_path: Path to audio file

    Returns:
        Duration in seconds

    Raises:
        FileNotFoundError: If audio file doesn't exist
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(str(audio_path))
        return len(audio) / 1000.0  # Convert ms to seconds
    except ImportError:
        try:
            from tinytag import TinyTag
            tag = TinyTag.get(str(audio_path))
            return tag.duration or 0.0
        except ImportError:
            logger.warning("Neither pydub nor tinytag available for duration detection")
            return 0.0


def normalize_audio(
    audio_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    target_db: float = -20.0
) -> Path:
    """
    Normalize audio to target dB level.

    Args:
        audio_path: Input audio file path
        output_path: Output file path (None = overwrite input)
        target_db: Target dB level (default: -20.0)

    Returns:
        Path to normalized audio file
    """
    audio_path = Path(audio_path)
    if output_path is None:
        output_path = audio_path
    else:
        output_path = Path(output_path)

    try:
        from pydub import AudioSegment
        from pydub.effects import normalize

        audio = AudioSegment.from_file(str(audio_path))
        normalized = normalize(audio, headroom=abs(target_db))
        normalized.export(str(output_path), format=output_path.suffix[1:])

        logger.info(f"Audio normalized: {output_path}")
        return output_path

    except ImportError:
        logger.warning("pydub not available, returning original file")
        return audio_path


def split_audio(
    audio_path: Union[str, Path],
    chunk_length_ms: int = 60000,  # 1 minute
    output_dir: Optional[Union[str, Path]] = None,
) -> List[Path]:
    """
    Split audio file into chunks.

    Args:
        audio_path: Input audio file path
        chunk_length_ms: Length of each chunk in milliseconds
        output_dir: Output directory (None = same as input)

    Returns:
        List of paths to chunk files
    """
    audio_path = Path(audio_path)
    if output_dir is None:
        output_dir = audio_path.parent
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(audio_path))
        chunks = []

        for i, start in enumerate(range(0, len(audio), chunk_length_ms)):
            chunk = audio[start:start + chunk_length_ms]
            chunk_path = output_dir / f"{audio_path.stem}_chunk_{i:03d}{audio_path.suffix}"
            chunk.export(str(chunk_path), format=audio_path.suffix[1:])
            chunks.append(chunk_path)

        logger.info(f"Split audio into {len(chunks)} chunks")
        return chunks

    except ImportError:
        logger.error("pydub not available for audio splitting")
        return [audio_path]


def convert_audio_format(
    audio_path: Union[str, Path],
    output_format: str,
    output_path: Optional[Union[str, Path]] = None,
    bitrate: str = "128k",
) -> Path:
    """
    Convert audio to different format.

    Args:
        audio_path: Input audio file path
        output_format: Target format (e.g., "mp3", "wav", "flac")
        output_path: Output file path (None = auto-generate)
        bitrate: Target bitrate (e.g., "128k", "320k")

    Returns:
        Path to converted audio file
    """
    audio_path = Path(audio_path)
    if output_path is None:
        output_path = audio_path.with_suffix(f".{output_format}")
    else:
        output_path = Path(output_path)

    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(audio_path))
        audio.export(
            str(output_path),
            format=output_format,
            bitrate=bitrate
        )

        logger.info(f"Converted {audio_path} to {output_format}: {output_path}")
        return output_path

    except ImportError:
        logger.error("pydub not available for format conversion")
        return audio_path


def validate_audio_file(audio_path: Union[str, Path]) -> Tuple[bool, Optional[str]]:
    """
    Validate if file is a readable audio file.

    Args:
        audio_path: Path to audio file

    Returns:
        Tuple of (is_valid, error_message)
    """
    audio_path = Path(audio_path)

    # Check if file exists
    if not audio_path.exists():
        return False, "File does not exist"

    # Check if it's a file (not directory)
    if not audio_path.is_file():
        return False, "Path is not a file"

    # Check file extension
    supported_extensions = {
        ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus"
    }
    if audio_path.suffix.lower() not in supported_extensions:
        return False, f"Unsupported file extension: {audio_path.suffix}"

    # Try to read audio metadata
    try:
        duration = get_audio_duration(audio_path)
        if duration <= 0:
            return False, "Audio file has zero duration"
        return True, None
    except Exception as e:
        return False, f"Failed to read audio file: {str(e)}"


def detect_silence_segments(
    audio_path: Union[str, Path],
    silence_thresh: int = -40,  # dB
    min_silence_len: int = 1000,  # ms
) -> List[Tuple[int, int]]:
    """
    Detect silence segments in audio file.

    Args:
        audio_path: Path to audio file
        silence_thresh: Silence threshold in dB
        min_silence_len: Minimum silence length in ms

    Returns:
        List of (start_ms, end_ms) tuples for silent segments
    """
    try:
        from pydub import AudioSegment
        from pydub.silence import detect_silence

        audio = AudioSegment.from_file(str(audio_path))
        silence_ranges = detect_silence(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=silence_thresh
        )

        logger.info(f"Detected {len(silence_ranges)} silence segments")
        return silence_ranges

    except ImportError:
        logger.warning("pydub not available for silence detection")
        return []


def trim_audio(
    audio_path: Union[str, Path],
    start_ms: int = 0,
    end_ms: Optional[int] = None,
    output_path: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Trim audio file to specified time range.

    Args:
        audio_path: Input audio file path
        start_ms: Start time in milliseconds
        end_ms: End time in milliseconds (None = end of file)
        output_path: Output file path (None = overwrite input)

    Returns:
        Path to trimmed audio file
    """
    audio_path = Path(audio_path)
    if output_path is None:
        output_path = audio_path
    else:
        output_path = Path(output_path)

    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(audio_path))
        trimmed = audio[start_ms:end_ms]
        trimmed.export(str(output_path), format=output_path.suffix[1:])

        logger.info(f"Audio trimmed: {output_path}")
        return output_path

    except ImportError:
        logger.warning("pydub not available for audio trimming")
        return audio_path


def merge_audio_files(
    audio_paths: List[Union[str, Path]],
    output_path: Union[str, Path],
    crossfade_ms: int = 0,
) -> Path:
    """
    Merge multiple audio files into one.

    Args:
        audio_paths: List of input audio file paths
        output_path: Output file path
        crossfade_ms: Crossfade duration in milliseconds

    Returns:
        Path to merged audio file
    """
    output_path = Path(output_path)

    try:
        from pydub import AudioSegment

        merged = AudioSegment.empty()

        for audio_path in audio_paths:
            audio = AudioSegment.from_file(str(audio_path))
            if crossfade_ms > 0 and len(merged) > 0:
                merged = merged.append(audio, crossfade=crossfade_ms)
            else:
                merged += audio

        merged.export(str(output_path), format=output_path.suffix[1:])

        logger.info(f"Merged {len(audio_paths)} files into: {output_path}")
        return output_path

    except ImportError:
        logger.error("pydub not available for audio merging")
        raise


def calculate_audio_checksum(audio_path: Union[str, Path], algorithm: str = "sha256") -> str:
    """
    Calculate checksum of audio file.

    Args:
        audio_path: Path to audio file
        algorithm: Hash algorithm ("md5", "sha1", "sha256")

    Returns:
        Hexadecimal checksum string
    """
    import hashlib

    audio_path = Path(audio_path)
    hash_func = getattr(hashlib, algorithm)()

    with open(audio_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)

    return hash_func.hexdigest()


def get_audio_peak_amplitude(audio_path: Union[str, Path]) -> float:
    """
    Get peak amplitude of audio file.

    Args:
        audio_path: Path to audio file

    Returns:
        Peak amplitude in dB
    """
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(audio_path))
        return audio.max_dBFS

    except ImportError:
        logger.warning("pydub not available for peak amplitude detection")
        return 0.0


def is_audio_file(file_path: Union[str, Path]) -> bool:
    """
    Check if file is an audio file based on extension.

    Args:
        file_path: Path to file

    Returns:
        True if file has audio extension
    """
    file_path = Path(file_path)
    audio_extensions = {
        ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus",
        ".MP3", ".WAV", ".M4A", ".FLAC", ".OGG", ".AAC", ".WMA", ".OPUS"
    }
    return file_path.suffix in audio_extensions
