"""Core audio transcription engine using faster-whisper."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel
from loguru import logger


class ModelSize(Enum):
    """Supported Whisper model sizes."""

    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE_V3 = "large-v3"


class ComputeType(Enum):
    """Compute types for inference."""

    FLOAT16 = "float16"
    INT8 = "int8"
    INT4 = "int4"
    FLOAT32 = "float32"


@dataclass
class TranscriptionSegment:
    """Segment of transcribed audio with timing and metadata."""

    start: float  # Start time in seconds
    end: float  # End time in seconds
    text: str  # Transcribed text
    confidence: float  # Confidence score (0-1)
    speaker: str | None = None  # Speaker label (if diarization enabled)
    words: list[dict[str, Any]] | None = None  # Word-level timestamps


@dataclass
class LanguageDetection:
    """Result of language detection."""

    language: str  # ISO 639-1 language code
    language_name: str  # Full language name
    confidence: float  # Detection confidence (0-1)


@dataclass
class TranscriptionResult:
    """Complete transcription result with metadata."""

    text: str  # Full transcribed text
    language: str  # Detected language code
    language_confidence: float  # Language detection confidence
    segments: list[TranscriptionSegment]  # All segments
    duration: float  # Audio duration in seconds
    processing_time: float  # Time taken to transcribe
    model_size: str  # Model used for transcription
    device: str  # Device used (cpu, cuda, mps)
    error: str | None = None  # Error message if any


@dataclass
class TranscriptionOptions:
    """Options for transcription."""

    language: str | None = None  # Force language (None = auto-detect)
    detect_language: bool = True  # Enable language detection
    word_timestamps: bool = True  # Generate word-level timestamps
    vad_filter: bool = True  # Voice activity detection
    beam_size: int = 5  # Beam search size
    best_of: int = 5  # Number of candidates
    temperature: float = 0.0  # Sampling temperature
    suppress_numerals: bool = False  # Keep numbers as digits
    initial_prompt: str | None = None  # Context hint
    progress_callback: Callable[[int, int], None] | None = None  # Progress updates


class AudioTranscriber:
    """Core audio transcription engine using faster-whisper.

    This class provides audio transcription capabilities with:
    - Multiple model sizes (tiny to large-v3)
    - Automatic device selection (CPU/CUDA/MPS)
    - Language detection (99+ languages)
    - Word-level and segment-level timestamps
    - Progress tracking for long files

    Example:
        >>> transcriber = AudioTranscriber(model_size=ModelSize.BASE)
        >>> result = transcriber.transcribe("audio.wav")
        >>> print(result.text)
        >>> print(f"Language: {result.language} ({result.language_confidence:.2%})")
    """

    _model_cache: dict[str, WhisperModel] = {}  # Class-level model cache

    def __init__(
        self,
        model_size: ModelSize | str = ModelSize.BASE,
        device: str = "auto",
        compute_type: ComputeType | str = ComputeType.FLOAT16,
        cache_dir: Path | None = None,
        num_workers: int = 1,
    ):
        """Initialize the audio transcriber.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v3)
            device: Device to use ('auto', 'cpu', 'cuda', 'mps')
            compute_type: Compute precision (float16, int8, int4, float32)
            cache_dir: Directory to cache models (None = default ~/.cache)
            num_workers: Number of workers for CPU inference

        Raises:
            ValueError: If model size or device is invalid
            RuntimeError: If model loading fails
        """
        # Convert enums to strings if needed
        self.model_size = model_size.value if isinstance(model_size, ModelSize) else model_size
        self.compute_type = (
            compute_type.value if isinstance(compute_type, ComputeType) else compute_type
        )

        # Validate model size
        valid_sizes = [m.value for m in ModelSize]
        if self.model_size not in valid_sizes:
            raise ValueError(
                f"Invalid model size: {self.model_size}. "
                f"Must be one of: {', '.join(valid_sizes)}"
            )

        # Auto-detect device
        self.device = self._detect_device(device)
        self.cache_dir = cache_dir
        self.num_workers = num_workers

        # Model will be lazily loaded
        self.model: WhisperModel | None = None
        self._model_loaded = False

        logger.info(
            f"Initialized AudioTranscriber: model={self.model_size}, "
            f"device={self.device}, compute_type={self.compute_type}"
        )

    def _detect_device(self, device: str) -> str:
        """Detect the best available device for inference.

        Args:
            device: Requested device ('auto', 'cpu', 'cuda', 'mps')

        Returns:
            Actual device to use
        """
        if device != "auto":
            return device

        # Check for CUDA (NVIDIA GPU)
        try:
            import torch

            if torch.cuda.is_available():
                logger.info("CUDA GPU detected, using GPU acceleration")
                return "cuda"
        except ImportError:
            pass

        # Check for MPS (Apple Silicon)
        try:
            import torch

            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                logger.info("Apple Silicon detected, using MPS acceleration")
                return "mps"
        except (ImportError, AttributeError):
            pass

        logger.info("No GPU detected, using CPU")
        return "cpu"

    def _load_model(self) -> WhisperModel:
        """Load the Whisper model (with caching).

        Returns:
            Loaded WhisperModel instance

        Raises:
            RuntimeError: If model loading fails
        """
        cache_key = f"{self.model_size}_{self.device}_{self.compute_type}"

        # Check class-level cache
        if cache_key in self._model_cache:
            logger.debug(f"Using cached model: {cache_key}")
            return self._model_cache[cache_key]

        # Load model
        logger.info(f"Loading Whisper model: {self.model_size} on {self.device}...")
        start_time = time.time()

        try:
            model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(self.cache_dir) if self.cache_dir else None,
                num_workers=self.num_workers,
            )

            # Cache the model
            self._model_cache[cache_key] = model

            load_time = time.time() - start_time
            logger.info(f"Model loaded successfully in {load_time:.2f}s")

            return model

        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise RuntimeError(f"Model loading failed: {e}") from e

    def detect_language(self, audio_path: str | Path) -> LanguageDetection:
        """Detect the language of the audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            LanguageDetection with language code and confidence

        Raises:
            FileNotFoundError: If audio file doesn't exist
            RuntimeError: If detection fails
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Ensure model is loaded
        if not self._model_loaded:
            self.model = self._load_model()
            self._model_loaded = True

        logger.debug(f"Detecting language for: {audio_path}")

        try:
            # Detect language from first 30 seconds
            segments, info = self.model.transcribe(
                str(audio_path), beam_size=5, language=None
            )

            # Get language from detected info
            language = info.language
            confidence = info.language_probability

            # Map language code to full name (simplified mapping)
            language_names = {
                "en": "English",
                "es": "Spanish",
                "fr": "French",
                "de": "German",
                "zh": "Chinese",
                "ja": "Japanese",
                "ko": "Korean",
                # Add more as needed
            }
            language_name = language_names.get(language, language.upper())

            logger.info(
                f"Detected language: {language_name} ({language}) "
                f"with confidence {confidence:.2%}"
            )

            return LanguageDetection(
                language=language, language_name=language_name, confidence=confidence
            )

        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            raise RuntimeError(f"Language detection failed: {e}") from e

    def transcribe(
        self, audio_path: str | Path, options: TranscriptionOptions | None = None
    ) -> TranscriptionResult:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to audio file (WAV, MP3, FLAC, M4A, OGG)
            options: Transcription options (None = defaults)

        Returns:
            TranscriptionResult with text, segments, and metadata

        Raises:
            FileNotFoundError: If audio file doesn't exist
            RuntimeError: If transcription fails
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Use default options if none provided
        if options is None:
            options = TranscriptionOptions()

        # Ensure model is loaded
        if not self._model_loaded:
            self.model = self._load_model()
            self._model_loaded = True

        logger.info(f"Transcribing audio file: {audio_path}")
        start_time = time.time()

        try:
            # Run transcription
            segments, info = self.model.transcribe(
                str(audio_path),
                language=options.language,
                beam_size=options.beam_size,
                best_of=options.best_of,
                temperature=options.temperature,
                vad_filter=options.vad_filter,
                word_timestamps=options.word_timestamps,
                initial_prompt=options.initial_prompt,
            )

            # Convert segments to our format
            transcription_segments = []
            full_text_parts = []

            for seg in segments:
                segment_text = seg.text.strip()
                full_text_parts.append(segment_text)

                # Extract word-level timestamps if available
                words = None
                if options.word_timestamps and hasattr(seg, "words"):
                    words = [
                        {"word": w.word, "start": w.start, "end": w.end, "confidence": w.probability}
                        for w in seg.words
                    ]

                transcription_segments.append(
                    TranscriptionSegment(
                        start=seg.start,
                        end=seg.end,
                        text=segment_text,
                        confidence=seg.avg_logprob,  # Approximate confidence
                        words=words,
                    )
                )

            # Assemble full text
            full_text = " ".join(full_text_parts)

            processing_time = time.time() - start_time
            duration = info.duration

            logger.info(
                f"Transcription complete: {duration:.1f}s audio in {processing_time:.1f}s "
                f"({duration/processing_time:.2f}x realtime)"
            )

            return TranscriptionResult(
                text=full_text,
                language=info.language,
                language_confidence=info.language_probability,
                segments=transcription_segments,
                duration=duration,
                processing_time=processing_time,
                model_size=self.model_size,
                device=self.device,
            )

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return TranscriptionResult(
                text="",
                language="unknown",
                language_confidence=0.0,
                segments=[],
                duration=0.0,
                processing_time=time.time() - start_time,
                model_size=self.model_size,
                device=self.device,
                error=str(e),
            )

    @staticmethod
    def get_supported_formats() -> list[str]:
        """Get list of supported audio formats.

        Returns:
            List of file extensions (e.g., ['wav', 'mp3', 'flac'])
        """
        return ["wav", "mp3", "flac", "m4a", "ogg", "webm", "opus"]

    def clear_cache(self) -> None:
        """Clear the model cache to free memory."""
        cache_key = f"{self.model_size}_{self.device}_{self.compute_type}"
        if cache_key in self._model_cache:
            del self._model_cache[cache_key]
            logger.info(f"Cleared model cache: {cache_key}")
        self.model = None
        self._model_loaded = False

    @classmethod
    def clear_all_caches(cls) -> None:
        """Clear all cached models (class method)."""
        cls._model_cache.clear()
        logger.info("Cleared all model caches")
