"""
Audio Transcription Service

Provides audio transcription capabilities using Faster-Whisper models.
Supports multiple model sizes, languages, and advanced transcription options.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ModelSize(str, Enum):
    """Whisper model sizes."""
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE_V2 = "large-v2"
    LARGE_V3 = "large-v3"


class ComputeType(str, Enum):
    """Computation precision types."""
    FLOAT16 = "float16"
    FLOAT32 = "float32"
    INT8 = "int8"
    INT8_FLOAT16 = "int8_float16"


@dataclass
class TranscriptionOptions:
    """Options for audio transcription."""
    language: str | None = None  # Auto-detect if None
    word_timestamps: bool = False
    beam_size: int = 5
    best_of: int = 5
    temperature: float = 0.0
    compression_ratio_threshold: float = 2.4
    log_prob_threshold: float = -1.0
    no_speech_threshold: float = 0.6
    condition_on_previous_text: bool = True
    initial_prompt: str | None = None
    vad_filter: bool = True  # Voice Activity Detection
    vad_parameters: dict[str, Any] | None = None


@dataclass
class WordTiming:
    """Word-level timing information."""
    word: str
    start: float  # seconds
    end: float  # seconds
    probability: float


@dataclass
class Segment:
    """Transcription segment with timing."""
    id: int
    start: float
    end: float
    text: str
    words: list[WordTiming] = field(default_factory=list)
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


@dataclass
class TranscriptionResult:
    """Complete transcription result."""
    text: str
    segments: list[Segment]
    language: str
    language_confidence: float
    duration: float  # seconds
    options: TranscriptionOptions


class AudioTranscriber:
    """
    Audio transcription service using Faster-Whisper.

    Features:
    - Multiple Whisper model sizes (tiny to large-v3)
    - Automatic language detection
    - Word-level timestamps
    - Voice Activity Detection (VAD)
    - GPU/CPU support with automatic fallback
    - Model caching for performance

    Example:
        >>> transcriber = AudioTranscriber()
        >>> result = transcriber.transcribe("audio.wav")
        >>> print(result.text)
        >>> print(f"Language: {result.language}")
    """

    def __init__(
        self,
        model_size: ModelSize = ModelSize.BASE,
        device: str = "auto",
        compute_type: ComputeType = ComputeType.FLOAT16,
        cache_dir: Path | None = None,
        num_workers: int = 1,
    ):
        """
        Initialize the audio transcriber.

        Args:
            model_size: Whisper model size to use
            device: Device to run on ("cpu", "cuda", "mps", or "auto")
            compute_type: Computation precision
            cache_dir: Directory to cache models (None = default)
            num_workers: Number of parallel workers for inference
        """
        self.model_size = model_size
        self.device = self._detect_device(device)
        self.compute_type = compute_type
        self.cache_dir = cache_dir
        self.num_workers = num_workers
        self._model = None

        logger.info(
            f"Initializing AudioTranscriber with model={model_size.value}, "
            f"device={self.device}, compute_type={compute_type.value}"
        )

    def _detect_device(self, device: str) -> str:
        """Detect the best available device."""
        if device != "auto":
            return device

        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass

        return "cpu"

    def _load_model(self):
        """Lazy load the Whisper model."""
        if self._model is not None:
            return self._model

        try:
            from faster_whisper import WhisperModel

            logger.info(f"Loading Whisper model: {self.model_size.value}")
            self._model = WhisperModel(
                self.model_size.value,
                device=self.device,
                compute_type=self.compute_type.value,
                download_root=str(self.cache_dir) if self.cache_dir else None,
                num_workers=self.num_workers,
            )
            logger.info("Model loaded successfully")
            return self._model

        except ImportError as e:
            raise ImportError(
                "faster-whisper is required for audio transcription. "
                "Install it with: pip install faster-whisper"
            ) from e
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def transcribe(
        self,
        audio_path: str | Path,
        options: TranscriptionOptions | None = None,
    ) -> TranscriptionResult:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to the audio file
            options: Transcription options (uses defaults if None)

        Returns:
            TranscriptionResult with full transcription and metadata

        Raises:
            FileNotFoundError: If audio file doesn't exist
            Exception: If transcription fails (e.g., unsupported format, corrupted file)
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if options is None:
            options = TranscriptionOptions()

        logger.info(f"Transcribing audio file: {audio_path}")

        # Load model
        model = self._load_model()

        # Prepare transcription parameters
        transcribe_params = {
            "beam_size": options.beam_size,
            "best_of": options.best_of,
            "temperature": options.temperature,
            "compression_ratio_threshold": options.compression_ratio_threshold,
            "log_prob_threshold": options.log_prob_threshold,
            "no_speech_threshold": options.no_speech_threshold,
            "condition_on_previous_text": options.condition_on_previous_text,
            "word_timestamps": options.word_timestamps,
        }

        if options.language:
            transcribe_params["language"] = options.language

        if options.initial_prompt:
            transcribe_params["initial_prompt"] = options.initial_prompt

        if options.vad_filter:
            transcribe_params["vad_filter"] = True
            if options.vad_parameters:
                transcribe_params["vad_parameters"] = options.vad_parameters

        try:
            # Perform transcription
            segments_iter, info = model.transcribe(
                str(audio_path),
                **transcribe_params
            )

            # Process segments
            segments = []
            full_text_parts = []

            for seg in segments_iter:
                words = []
                if options.word_timestamps and hasattr(seg, 'words'):
                    words = [
                        WordTiming(
                            word=w.word,
                            start=w.start,
                            end=w.end,
                            probability=w.probability
                        )
                        for w in seg.words
                    ]

                segment = Segment(
                    id=seg.id,
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    words=words,
                    avg_logprob=seg.avg_logprob,
                    no_speech_prob=seg.no_speech_prob,
                )
                segments.append(segment)
                full_text_parts.append(segment.text)

            # Combine results
            full_text = " ".join(full_text_parts)

            result = TranscriptionResult(
                text=full_text,
                segments=segments,
                language=info.language,
                language_confidence=info.language_probability,
                duration=info.duration,
                options=options,
            )

            logger.info(
                f"Transcription complete: {len(segments)} segments, "
                f"language={info.language}, duration={info.duration:.2f}s"
            )

            return result

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise

    def transcribe_batch(
        self,
        audio_paths: list[str | Path],
        options: TranscriptionOptions | None = None,
    ) -> list[TranscriptionResult]:
        """
        Transcribe multiple audio files.

        Args:
            audio_paths: List of paths to audio files
            options: Transcription options (shared across all files)

        Returns:
            List of TranscriptionResult objects
        """
        results = []
        for audio_path in audio_paths:
            try:
                result = self.transcribe(audio_path, options)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to transcribe {audio_path}: {e}")
                # Continue with other files

        return results

    def unload_model(self):
        """Unload the model to free memory."""
        if self._model is not None:
            del self._model
            self._model = None
            logger.info("Model unloaded")
