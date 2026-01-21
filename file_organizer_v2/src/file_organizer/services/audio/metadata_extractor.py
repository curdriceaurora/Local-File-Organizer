"""
Audio Metadata Extraction Service

Extracts comprehensive metadata from audio files including:
- Basic properties (duration, bitrate, sample rate)
- ID3 tags (artist, album, title, genre)
- Technical metadata (codec, channels)
- Embedded artwork
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Union, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class AudioMetadata:
    """Comprehensive audio file metadata."""
    # File information
    file_path: Path
    file_size: int  # bytes
    format: str

    # Audio properties
    duration: float  # seconds
    bitrate: int  # bits per second
    sample_rate: int  # Hz
    channels: int
    bits_per_sample: Optional[int] = None

    # ID3 / Vorbis tags
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[int] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    comment: Optional[str] = None

    # Technical metadata
    codec: Optional[str] = None
    encoder: Optional[str] = None

    # Additional tags
    extra_tags: Dict[str, str] = field(default_factory=dict)

    # Artwork
    has_artwork: bool = False
    artwork_count: int = 0


class AudioMetadataExtractor:
    """
    Audio metadata extraction service.

    Supports multiple audio formats and tag types:
    - MP3 (ID3v1, ID3v2)
    - M4A/AAC (iTunes metadata)
    - FLAC (Vorbis comments)
    - OGG (Vorbis comments)
    - WMA (ASF tags)
    - WAV (INFO chunks)

    Uses mutagen as primary library with tinytag as fallback.
    """

    def __init__(self, use_fallback: bool = True):
        """
        Initialize metadata extractor.

        Args:
            use_fallback: Use tinytag as fallback if mutagen fails
        """
        self.use_fallback = use_fallback

    def extract(self, audio_path: Union[str, Path]) -> AudioMetadata:
        """
        Extract metadata from audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            AudioMetadata object with all available metadata

        Raises:
            FileNotFoundError: If audio file doesn't exist
            ValueError: If file format is unsupported
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.info(f"Extracting metadata from: {audio_path}")

        # Try mutagen first (more comprehensive)
        try:
            return self._extract_with_mutagen(audio_path)
        except Exception as e:
            logger.warning(f"Mutagen extraction failed: {e}")
            if self.use_fallback:
                logger.info("Falling back to tinytag")
                return self._extract_with_tinytag(audio_path)
            raise

    def _extract_with_mutagen(self, audio_path: Path) -> AudioMetadata:
        """Extract metadata using mutagen library."""
        try:
            from mutagen import File as MutagenFile
            from mutagen.id3 import ID3
            from mutagen.mp4 import MP4
            from mutagen.flac import FLAC
            from mutagen.oggvorbis import OggVorbis

        except ImportError:
            raise ImportError(
                "mutagen is required for audio metadata extraction. "
                "Install it with: pip install mutagen"
            )

        # Load file
        audio = MutagenFile(str(audio_path))
        if audio is None:
            raise ValueError(f"Unsupported audio format: {audio_path}")

        # Extract basic properties
        file_size = audio_path.stat().st_size
        format_name = audio_path.suffix[1:].upper()

        # Duration and bitrate
        duration = audio.info.length if hasattr(audio.info, 'length') else 0.0
        bitrate = audio.info.bitrate if hasattr(audio.info, 'bitrate') else 0

        # Sample rate and channels
        sample_rate = audio.info.sample_rate if hasattr(audio.info, 'sample_rate') else 0
        channels = audio.info.channels if hasattr(audio.info, 'channels') else 0

        # Codec information
        codec = None
        if hasattr(audio.info, 'codec'):
            codec = audio.info.codec
        elif hasattr(audio.info, 'codec_name'):
            codec = audio.info.codec_name

        # Extract tags based on format
        tags = self._extract_tags_mutagen(audio)

        # Check for artwork
        has_artwork, artwork_count = self._check_artwork_mutagen(audio)

        metadata = AudioMetadata(
            file_path=audio_path,
            file_size=file_size,
            format=format_name,
            duration=duration,
            bitrate=bitrate,
            sample_rate=sample_rate,
            channels=channels,
            codec=codec,
            **tags,
            has_artwork=has_artwork,
            artwork_count=artwork_count,
        )

        logger.info(f"Metadata extracted: {duration:.2f}s, {bitrate}bps")
        return metadata

    def _extract_tags_mutagen(self, audio) -> dict:
        """Extract tags from mutagen audio object."""
        tags = {
            "title": None,
            "artist": None,
            "album": None,
            "album_artist": None,
            "genre": None,
            "year": None,
            "track_number": None,
            "disc_number": None,
            "comment": None,
            "encoder": None,
            "extra_tags": {},
        }

        if audio.tags is None:
            return tags

        # Common tag mappings for different formats
        tag_mappings = {
            # ID3 (MP3)
            "TIT2": "title",
            "TPE1": "artist",
            "TALB": "album",
            "TPE2": "album_artist",
            "TCON": "genre",
            "TDRC": "year",
            "TRCK": "track_number",
            "TPOS": "disc_number",
            "COMM": "comment",
            "TENC": "encoder",
            # Vorbis Comments (FLAC, OGG)
            "title": "title",
            "artist": "artist",
            "album": "album",
            "albumartist": "album_artist",
            "genre": "genre",
            "date": "year",
            "tracknumber": "track_number",
            "discnumber": "disc_number",
            "comment": "comment",
            "encoder": "encoder",
            # MP4 (M4A)
            "©nam": "title",
            "©ART": "artist",
            "©alb": "album",
            "aART": "album_artist",
            "©gen": "genre",
            "©day": "year",
            "trkn": "track_number",
            "disk": "disc_number",
            "©cmt": "comment",
            "©too": "encoder",
        }

        # Extract mapped tags
        for tag_key, value in audio.tags.items():
            if tag_key in tag_mappings:
                field = tag_mappings[tag_key]
                if field in tags:
                    # Convert to appropriate type
                    if isinstance(value, (list, tuple)):
                        value = value[0] if value else None
                    if value is not None:
                        value_str = str(value)
                        if field == "year" and value_str.isdigit():
                            tags[field] = int(value_str[:4])
                        elif field in ("track_number", "disc_number"):
                            # Handle "1/10" format
                            if "/" in value_str:
                                tags[field] = int(value_str.split("/")[0])
                            elif value_str.isdigit():
                                tags[field] = int(value_str)
                        else:
                            tags[field] = value_str
            else:
                # Store unmapped tags in extra_tags
                tags["extra_tags"][str(tag_key)] = str(value)

        return tags

    def _check_artwork_mutagen(self, audio) -> tuple[bool, int]:
        """Check for embedded artwork."""
        if audio.tags is None:
            return False, 0

        artwork_count = 0

        # Check different artwork tag formats
        if hasattr(audio.tags, 'pictures'):  # FLAC
            artwork_count = len(audio.tags.pictures)
        elif hasattr(audio, 'pictures'):  # OGG
            artwork_count = len(audio.pictures)
        elif "APIC" in audio.tags:  # MP3 ID3
            apic_frames = [k for k in audio.tags.keys() if k.startswith("APIC")]
            artwork_count = len(apic_frames)
        elif "covr" in audio.tags:  # MP4
            artwork_count = len(audio.tags["covr"])

        return artwork_count > 0, artwork_count

    def _extract_with_tinytag(self, audio_path: Path) -> AudioMetadata:
        """Fallback extraction using tinytag library."""
        try:
            from tinytag import TinyTag
        except ImportError:
            raise ImportError(
                "tinytag is required as fallback for audio metadata extraction. "
                "Install it with: pip install tinytag"
            )

        tag = TinyTag.get(str(audio_path))

        metadata = AudioMetadata(
            file_path=audio_path,
            file_size=audio_path.stat().st_size,
            format=audio_path.suffix[1:].upper(),
            duration=tag.duration or 0.0,
            bitrate=tag.bitrate or 0,
            sample_rate=tag.samplerate or 0,
            channels=tag.channels or 0,
            title=tag.title,
            artist=tag.artist,
            album=tag.album,
            album_artist=tag.albumartist,
            genre=tag.genre,
            year=int(tag.year) if tag.year else None,
            track_number=int(tag.track) if tag.track else None,
            disc_number=int(tag.disc) if tag.disc else None,
            comment=tag.comment,
        )

        logger.info(f"Metadata extracted (tinytag): {metadata.duration:.2f}s")
        return metadata

    def extract_batch(
        self,
        audio_paths: List[Union[str, Path]]
    ) -> List[AudioMetadata]:
        """
        Extract metadata from multiple audio files.

        Args:
            audio_paths: List of audio file paths

        Returns:
            List of AudioMetadata objects
        """
        results = []
        for audio_path in audio_paths:
            try:
                metadata = self.extract(audio_path)
                results.append(metadata)
            except Exception as e:
                logger.error(f"Failed to extract metadata from {audio_path}: {e}")
                # Continue with other files

        return results

    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def format_bitrate(bitrate: int) -> str:
        """Format bitrate as human-readable string."""
        if bitrate >= 1_000_000:
            return f"{bitrate / 1_000_000:.1f} Mbps"
        elif bitrate >= 1_000:
            return f"{bitrate / 1_000:.0f} kbps"
        else:
            return f"{bitrate} bps"
