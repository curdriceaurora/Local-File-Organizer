"""Audio model implementation backed by faster-whisper.

Wraps the service-level :class:`~file_organizer.services.audio.transcriber.AudioTranscriber`
behind the :class:`~file_organizer.models.base.BaseModel` lifecycle so the
organizer/dispatcher and benchmark paths get a real transcription engine
with thread-safe initialize/generate/cleanup semantics.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from file_organizer.models.base import BaseModel, DeviceType, ModelConfig, ModelType

# Probed locally (not imported from the services package) to avoid a circular
# import: models/__init__ -> audio_model -> services/__init__ -> models.
try:
    import faster_whisper  # noqa: F401

    _FASTER_WHISPER_AVAILABLE = True
except ImportError:
    _FASTER_WHISPER_AVAILABLE = False

if TYPE_CHECKING:
    from file_organizer.services.audio.transcriber import (
        AudioTranscriber,
        TranscriptionResult,
    )

#: Whisper model sizes accepted by ``ModelConfig.name`` (optionally prefixed
#: with ``whisper:`` / ``whisper-`` to match registry naming, e.g. ``whisper:base``).
VALID_MODEL_SIZES: tuple[str, ...] = (
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
)

_NAME_PREFIXES: tuple[str, ...] = ("whisper:", "whisper-", "faster-whisper-")


def parse_model_size(name: str) -> str:
    """Normalize a configured model name to a Whisper size string.

    Accepts bare sizes (``"base"``) as well as registry-style names
    (``"whisper:base"``, ``"whisper-base"``, ``"faster-whisper-base"``).

    Raises:
        ValueError: If the name does not resolve to a supported size.
    """
    normalized = name.strip().lower()
    for prefix in _NAME_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    if normalized not in VALID_MODEL_SIZES:
        raise ValueError(
            f"Invalid Whisper model name: {name!r}. "
            f"Expected one of {', '.join(VALID_MODEL_SIZES)} "
            "(optionally prefixed with 'whisper:')."
        )
    return normalized


class AudioModel(BaseModel):
    """Audio transcription model wrapping faster-whisper.

    Provides:
    - ``generate(audio_path) -> str`` — plain transcript text (BaseModel contract)
    - ``transcribe(audio_path) -> TranscriptionResult`` — full result with
      segments, mirroring ``VisionModel.analyze_image()`` as the domain-specific
      convenience API. The dispatcher prefers this so the audio classifier's
      segment-based heuristics (speaker count, narrative length) receive real
      segments instead of a synthesized segment-less result.
    """

    def __init__(self, config: ModelConfig):
        """Initialize audio model.

        Args:
            config: Model configuration. ``config.name`` selects the Whisper
                size (``tiny`` … ``large-v3``, with or without a ``whisper:``
                prefix). ``config.extra_params["compute_type"]`` optionally
                overrides the precision (default: float16 on CUDA, int8 on CPU).

        Raises:
            ImportError: If faster-whisper is not installed (the [audio] extra)
            ValueError: If model type is not AUDIO or the name is not a
                supported Whisper size
        """
        if not _FASTER_WHISPER_AVAILABLE:
            raise ImportError(
                "faster-whisper is required for audio transcription. "
                "Install it with: pip install 'local-file-organizer[audio]'"
            )

        if config.model_type != ModelType.AUDIO:
            raise ValueError(f"Expected AUDIO model type, got {config.model_type}")

        self.model_size = parse_model_size(config.name)

        super().__init__(config)
        self._transcriber: AudioTranscriber | None = None

    def _resolve_device(self) -> str:
        """Resolve the configured device to one CTranslate2 supports.

        faster-whisper (CTranslate2) only runs on ``cpu`` and ``cuda``; the
        MPS/METAL backends used by other models are unsupported, so Apple
        Silicon transparently falls back to CPU rather than failing at load.
        """
        device = self.config.device
        requested = device.value if isinstance(device, DeviceType) else str(device)
        if requested == DeviceType.AUTO.value:
            try:
                import torch

                if torch.cuda.is_available():
                    return "cuda"
            except ImportError:
                pass
            return "cpu"
        if requested in (DeviceType.MPS.value, DeviceType.METAL.value):
            logger.warning(
                "faster-whisper does not support {} (CTranslate2 is CPU/CUDA only); "
                "falling back to CPU.",
                requested,
            )
            return "cpu"
        return requested

    def initialize(self) -> None:
        """Load the Whisper model via the audio transcription service."""
        if self._initialized:
            logger.debug("Audio model {} already initialized", self.config.name)
            return

        from file_organizer.services.audio.transcriber import (
            AudioTranscriber,
            ComputeType,
            ModelSize,
        )

        device = self._resolve_device()
        extra = self.config.extra_params or {}
        compute_type = extra.get(
            "compute_type",
            ComputeType.FLOAT16.value if device == "cuda" else ComputeType.INT8.value,
        )
        cache_dir = extra.get("cache_dir")

        logger.info(
            "Initializing audio model: whisper-{} on {} ({})",
            self.model_size,
            device,
            compute_type,
        )
        self._transcriber = AudioTranscriber(
            model_size=ModelSize(self.model_size),
            device=device,
            compute_type=ComputeType(compute_type),
            cache_dir=Path(cache_dir) if cache_dir else None,
        )
        super().initialize()

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Transcribe the audio file at *prompt* and return the transcript text.

        Args:
            prompt: Path to the audio file (BaseModel contract reuses the
                ``prompt`` parameter for the primary input)
            **kwargs: Forwarded to :meth:`transcribe`

        Returns:
            Full transcribed text (empty string for silent audio)
        """
        return self.transcribe(prompt, **kwargs).text

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        language: str | None = None,
        word_timestamps: bool = False,
        **kwargs: Any,
    ) -> TranscriptionResult:
        """Transcribe an audio file, returning the full result with segments.

        Args:
            audio_path: Path to the audio file
            language: Force a language code (None = auto-detect)
            word_timestamps: Also produce word-level timestamps (slower)
            **kwargs: Additional :class:`TranscriptionOptions` fields

        Returns:
            TranscriptionResult with text, segments, language, and duration

        Raises:
            RuntimeError: If the model is not initialized or transcription fails
            FileNotFoundError: If the audio file does not exist
        """
        self._enter_generate()
        try:
            if self._transcriber is None:
                raise RuntimeError("Model not initialized. Call initialize() first.")

            from file_organizer.services.audio.transcriber import TranscriptionOptions

            options = TranscriptionOptions(
                language=language,
                word_timestamps=word_timestamps,
                **kwargs,
            )
            return self._transcriber.transcribe(audio_path, options)
        finally:
            self._exit_generate()

    def cleanup(self) -> None:
        """Release the Whisper model from memory."""
        logger.debug("Cleaning up audio model")
        with self._lifecycle_lock:
            if self._transcriber is not None:
                self._transcriber.unload_model()
                self._transcriber = None
            self._initialized = False

    @staticmethod
    def get_default_config(model_name: str = "whisper:base") -> ModelConfig:
        """Get default configuration for audio model.

        Args:
            model_name: Whisper model name/size (default: ``whisper:base``)

        Returns:
            Default model configuration
        """
        return ModelConfig(
            name=model_name,
            model_type=ModelType.AUDIO,
            framework="faster-whisper",
            temperature=0.0,
            max_tokens=1000,
        )
