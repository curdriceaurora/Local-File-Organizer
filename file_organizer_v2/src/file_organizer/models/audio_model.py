"""Audio model implementation using faster-whisper."""

from pathlib import Path
from typing import Any, Dict, Optional

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False

from file_organizer.models.base import BaseModel, ModelConfig, ModelType, DeviceType
from loguru import logger


class AudioModel(BaseModel):
    """Audio transcription model using faster-whisper.

    This model wraps faster-whisper for:
    - Audio transcription
    - Speech-to-text conversion
    - Audio file categorization based on content
    """

    def __init__(self, config: ModelConfig):
        """Initialize audio model.

        Args:
            config: Model configuration

        Raises:
            ImportError: If faster-whisper is not installed
            ValueError: If model type is not AUDIO
        """
        if not FASTER_WHISPER_AVAILABLE:
            raise ImportError(
                "faster-whisper is not installed. Install it with: pip install faster-whisper"
            )

        if config.model_type != ModelType.AUDIO:
            raise ValueError(f"Expected AUDIO model type, got {config.model_type}")

        super().__init__(config)
        self.model: Optional[WhisperModel] = None

    def initialize(self) -> None:
        """Initialize the faster-whisper model."""
        if self._initialized:
            logger.debug(f"Audio model {self.config.name} already initialized")
            return

        logger.info(f"Initializing audio model: {self.config.name}")

        try:
            # Map device type to faster-whisper format
            device = self._get_device()
            compute_type = self._get_compute_type()

            # Initialize faster-whisper model
            self.model = WhisperModel(
                self.config.name,
                device=device,
                compute_type=compute_type,
                download_root=self.config.local_path,
            )

            self._initialized = True
            logger.info(
                f"Audio model {self.config.name} initialized successfully on {device} "
                f"with {compute_type} compute"
            )

        except Exception as e:
            logger.error(f"Failed to initialize audio model: {e}")
            raise

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Transcribe audio file.

        Args:
            prompt: Path to audio file
            **kwargs: Additional transcription parameters:
                - language: Language code (e.g., 'en', 'es'). None for auto-detect.
                - task: 'transcribe' or 'translate'
                - beam_size: Beam size for decoding (default: 5)
                - vad_filter: Use voice activity detection (default: True)
                - word_timestamps: Include word-level timestamps (default: False)

        Returns:
            Transcribed text

        Raises:
            RuntimeError: If model is not initialized
            FileNotFoundError: If audio file does not exist
        """
        if not self._initialized or self.model is None:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        audio_path = Path(prompt)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.debug(f"Transcribing audio: {audio_path}")

        try:
            # Get transcription parameters
            language = kwargs.get("language", None)
            task = kwargs.get("task", "transcribe")
            beam_size = kwargs.get("beam_size", 5)
            vad_filter = kwargs.get("vad_filter", True)
            word_timestamps = kwargs.get("word_timestamps", False)

            # Transcribe audio
            segments, info = self.model.transcribe(
                str(audio_path),
                language=language,
                task=task,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=word_timestamps,
            )

            # Collect transcription segments
            transcription_parts = []
            for segment in segments:
                transcription_parts.append(segment.text)

            transcription = " ".join(transcription_parts).strip()

            logger.debug(
                f"Transcription complete. Detected language: {info.language}, "
                f"Duration: {info.duration:.2f}s"
            )

            return transcription

        except Exception as e:
            logger.error(f"Failed to transcribe audio: {e}")
            raise

    def transcribe_with_timestamps(
        self, audio_path: str, **kwargs: Any
    ) -> Dict[str, Any]:
        """Transcribe audio with segment timestamps.

        Args:
            audio_path: Path to audio file
            **kwargs: Additional transcription parameters (see generate())

        Returns:
            Dictionary containing:
                - text: Full transcription
                - segments: List of segments with timestamps
                - language: Detected language
                - duration: Audio duration in seconds

        Raises:
            RuntimeError: If model is not initialized
            FileNotFoundError: If audio file does not exist
        """
        if not self._initialized or self.model is None:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        logger.debug(f"Transcribing audio with timestamps: {audio_file}")

        try:
            # Get transcription parameters
            language = kwargs.get("language", None)
            task = kwargs.get("task", "transcribe")
            beam_size = kwargs.get("beam_size", 5)
            vad_filter = kwargs.get("vad_filter", True)

            # Transcribe audio
            segments, info = self.model.transcribe(
                str(audio_file),
                language=language,
                task=task,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=True,
            )

            # Collect segments with timestamps
            segment_list = []
            transcription_parts = []

            for segment in segments:
                segment_list.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                })
                transcription_parts.append(segment.text)

            return {
                "text": " ".join(transcription_parts).strip(),
                "segments": segment_list,
                "language": info.language,
                "duration": info.duration,
            }

        except Exception as e:
            logger.error(f"Failed to transcribe audio with timestamps: {e}")
            raise

    def cleanup(self) -> None:
        """Cleanup model resources."""
        logger.debug("Cleaning up audio model")
        if self.model is not None:
            del self.model
            self.model = None
        self._initialized = False

    def _get_device(self) -> str:
        """Get device string for faster-whisper.

        Returns:
            Device string ('cpu', 'cuda', or 'auto')
        """
        device_map = {
            DeviceType.CPU: "cpu",
            DeviceType.CUDA: "cuda",
            DeviceType.AUTO: "auto",
            DeviceType.MPS: "cpu",  # MPS not supported by faster-whisper
            DeviceType.METAL: "cpu",  # Metal not supported by faster-whisper
        }
        return device_map.get(self.config.device, "auto")

    def _get_compute_type(self) -> str:
        """Get compute type for faster-whisper.

        Returns:
            Compute type string (e.g., 'int8', 'float16')
        """
        # Map quantization to compute type
        quant_map = {
            "q4_k_m": "int8",
            "q5_k_m": "int8",
            "q8_0": "int8",
            "fp16": "float16",
            "fp32": "float32",
        }
        return quant_map.get(self.config.quantization, "int8")

    @staticmethod
    def get_default_config(
        model_name: str = "base",
        device: DeviceType = DeviceType.AUTO,
    ) -> ModelConfig:
        """Get default configuration for audio model.

        Args:
            model_name: Whisper model size ('tiny', 'base', 'small', 'medium', 'large-v3')
            device: Device type for inference

        Returns:
            Default model configuration
        """
        return ModelConfig(
            name=model_name,
            model_type=ModelType.AUDIO,
            framework="faster-whisper",
            device=device,
            temperature=0.0,  # Not used for transcription
            max_tokens=1000,  # Not directly used
            quantization="int8",  # Default compute type
        )
