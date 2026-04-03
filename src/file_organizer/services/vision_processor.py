"""Vision file processing service."""

from __future__ import annotations

import re
import threading
import time
import types as _t
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from file_organizer.models import VisionModel
from file_organizer.models.base import BaseModel, ModelConfig, ModelType
from file_organizer.models.provider_factory import get_vision_model


@dataclass
class ProcessedImage:
    """Result of image processing."""

    file_path: Path
    description: str
    folder_name: str
    filename: str
    has_text: bool = False
    extracted_text: str | None = None
    processing_time: float = 0.0
    error: str | None = None


class VisionProcessor:
    """Process image and video files using AI to generate metadata.

    This service:
    - Analyzes images with vision-language models
    - Generates descriptions and summaries
    - Creates folder names and filenames
    - Performs OCR when needed
    - Handles video frames
    """

    _FATAL_BACKEND_MARKERS: tuple[str, ...] = (
        "connection refused",
        "actively refused",
        "dial tcp",
        "health resp",
        "runner has unexpectedly stopped",
        "failed to connect",
    )

    def __init__(
        self,
        vision_model: BaseModel | None = None,
        config: ModelConfig | None = None,
        *,
        backend_cooldown_seconds: float = 20.0,
    ) -> None:
        """Initialize vision processor.

        Args:
            vision_model: Pre-initialized vision model (optional). Any
                ``BaseModel`` subclass is accepted, allowing Ollama and
                OpenAI-compatible models to be passed interchangeably.
            config: Model configuration (used if ``vision_model`` not provided).
                The ``config.provider`` field controls which backend is used.
                If omitted, the Ollama default configuration is applied
                regardless of any global provider setting.
            backend_cooldown_seconds: Cooldown period for fatal backend
                failures before retrying model calls.
        """
        if vision_model is not None:
            if vision_model.config.model_type not in (ModelType.VISION, ModelType.VIDEO):
                raise ValueError(
                    f"VisionProcessor requires a VISION or VIDEO model, "
                    f"got {vision_model.config.model_type}"
                )
            self.vision_model = vision_model
            self._owns_model = False
        else:
            config = config or VisionModel.get_default_config()
            self.vision_model = get_vision_model(config)
            self._owns_model = True

        self._backend_cooldown_seconds = backend_cooldown_seconds
        self._circuit_lock = threading.Lock()
        self._circuit_opened_at: float | None = None
        self._circuit_reason: str | None = None

        logger.info("VisionProcessor initialized")

    def initialize(self) -> None:
        """Initialize the vision model if not already initialized."""
        if not self.vision_model.is_initialized:
            self.vision_model.initialize()
            logger.info("Vision model initialized")

    def process_file(
        self,
        file_path: str | Path,
        generate_description: bool = True,
        generate_folder: bool = True,
        generate_filename: bool = True,
        perform_ocr: bool = True,
    ) -> ProcessedImage:
        """Process a single image file.

        Args:
            file_path: Path to image file
            generate_description: Whether to generate description
            generate_folder: Whether to generate folder name
            generate_filename: Whether to generate filename
            perform_ocr: Whether to extract text (OCR)

        Returns:
            ProcessedImage with metadata
        """
        import time

        file_path = Path(file_path)
        start_time = time.time()

        try:
            if self._is_circuit_open():
                logger.warning(
                    "Vision backend circuit open; skipping model calls for {}",
                    file_path.name,
                )
                error_message = self._circuit_open_error()
                logger.debug(
                    "Circuit-open fallback for {} with error={}",
                    file_path.name,
                    error_message,
                )
                return ProcessedImage(
                    file_path=file_path,
                    description=f"Image from {file_path.name}",
                    folder_name="images",
                    filename=file_path.stem,
                    error=error_message,
                )

            # Validate file exists
            if not file_path.exists():
                return ProcessedImage(
                    file_path=file_path,
                    description="",
                    folder_name="errors",
                    filename=file_path.stem,
                    error="File not found",
                )

            # Generate description
            description = ""
            if generate_description:
                logger.debug(f"Analyzing image: {file_path.name}")
                description = self._generate_description(file_path)
                logger.debug(f"Generated description ({len(description)} chars)")
                if self._is_circuit_open():
                    error_message = self._circuit_open_error()
                    return ProcessedImage(
                        file_path=file_path,
                        description=description or f"Image from {file_path.name}",
                        folder_name="images",
                        filename=file_path.stem,
                        error=error_message,
                    )

            # Extract text if needed
            extracted_text = None
            has_text = False
            if perform_ocr:
                extracted_text = self._extract_text(file_path)
                has_text = bool(extracted_text and len(extracted_text.strip()) > 10)
                if has_text and extracted_text is not None:
                    logger.debug(f"Extracted {len(extracted_text)} chars of text")

            # Generate folder name
            folder_name = ""
            if generate_folder:
                # Use extracted text if available, otherwise use description
                context: str = (extracted_text or description) if has_text else description
                folder_name = self._generate_folder_name(file_path, context)
                logger.debug(f"Generated folder name: {folder_name}")

            # Generate filename
            filename = ""
            if generate_filename:
                # Use extracted text if available, otherwise use description
                context = (extracted_text or description) if has_text else description
                filename = self._generate_filename(file_path, context)
                logger.debug(f"Generated filename: {filename}")

            processing_time = time.time() - start_time

            return ProcessedImage(
                file_path=file_path,
                description=description,
                folder_name=folder_name,
                filename=filename,
                has_text=has_text,
                extracted_text=extracted_text[:500] if extracted_text else None,
                processing_time=processing_time,
            )

        except (RuntimeError, ValueError, OSError, AttributeError) as e:
            logger.exception(f"Failed to process {file_path.name}: {e}")
            return ProcessedImage(
                file_path=file_path,
                description="",
                folder_name="errors",
                filename=file_path.stem,
                error=str(e),
            )

    def _clean_ai_generated_name(self, name: str, max_words: int = 3) -> str:
        """Clean AI-generated folder/file names with lighter filtering.

        Args:
            name: AI-generated name
            max_words: Maximum number of words

        Returns:
            Cleaned name
        """
        # Convert underscores and hyphens to spaces
        name = name.replace("_", " ").replace("-", " ")

        # Remove special characters and numbers (keep letters and spaces)
        name = re.sub(r"[^a-z\s]", "", name.lower())

        # Split into words
        words = name.split()

        # Only filter out truly problematic words
        bad_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "is",
            "are",
            "was",
            "were",
            "be",
            "image",
            "picture",
            "photo",
            "untitled",
            "unknown",
        }

        # Filter and deduplicate
        filtered = []
        seen = set()
        for word in words:
            if word and word not in bad_words and word not in seen and len(word) > 1:
                filtered.append(word)
                seen.add(word)

        # Limit to max words
        filtered = filtered[:max_words]

        # Join with underscores
        return "_".join(filtered) if filtered else ""

    def _generate_description(self, image_path: Path) -> str:
        """Generate a description of the image.

        Args:
            image_path: Path to image file

        Returns:
            Image description
        """
        prompt = """Describe this image in detail. Include:
1. Main subject or focus
2. Important objects, people, or elements
3. Setting or environment
4. Colors, mood, or atmosphere
5. Any visible text or labels

Provide a clear, descriptive paragraph (100-150 words)."""

        try:
            response = self._guarded_generate(
                prompt=prompt,
                image_path=image_path,
                temperature=0.5,
                max_tokens=250,
            )
            return response.strip()
        except (RuntimeError, ValueError, OSError, AttributeError) as e:
            logger.error(f"Failed to generate description: {e}")
            return f"Image from {image_path.name}"

    def _extract_text(self, image_path: Path) -> str | None:
        """Extract text from image using OCR.

        Args:
            image_path: Path to image file

        Returns:
            Extracted text or None
        """
        prompt = """Extract ALL visible text from this image.
Include any text you see, whether it's:
- Titles, headings, or labels
- Body text or paragraphs
- Numbers, dates, or codes
- Signs, captions, or watermarks

Provide ONLY the text, preserving the order but not necessarily the formatting.
If there's no readable text, respond with "NO_TEXT"."""

        try:
            response = self._guarded_generate(
                prompt=prompt,
                image_path=image_path,
                temperature=0.1,
                max_tokens=500,
            )

            response = response.strip()

            # Check if no text was found
            if response.upper() in ["NO_TEXT", "NO TEXT", "NONE", "N/A"]:
                return None

            # Check if response is too short to be meaningful
            if len(response) < 10:
                return None

            return response

        except (RuntimeError, ValueError, OSError, AttributeError) as e:
            logger.error(f"Failed to extract text: {e}")
            return None

    def _generate_folder_name(self, image_path: Path, context: str) -> str:
        """Generate a folder name from image context.

        Args:
            image_path: Path to image file
            context: Description or extracted text

        Returns:
            Folder name (max 2 words)
        """
        prompt = f"""Based on the image analysis below, generate a general category or theme.

RULES:
1. Maximum 2 words (e.g., "nature_photography", "architecture", "food")
2. Use ONLY nouns, no verbs
3. Be general, not specific
4. Use lowercase with underscores between words
5. NO generic terms like 'image', 'photo', 'picture', 'untitled'
6. Output ONLY the category, NO explanation

EXAMPLES:
- Image of mountains and forest → "nature_landscapes"
- Image of city buildings → "urban_architecture"
- Image of food dish → "food"
- Image of people at meeting → "business_meetings"

IMAGE ANALYSIS:
{context[:1000]}

CATEGORY:"""

        try:
            response = self._guarded_generate(
                prompt=prompt,
                image_path=image_path,
                temperature=0.3,
                max_tokens=30,
            )

            logger.debug(f"AI folder response (raw): '{response}'")

            # Clean the response
            folder_name = response.strip().lower()

            # Remove common prefixes and quotes
            for prefix in ["category:", "folder:", "the category is", "the folder is"]:
                folder_name = folder_name.replace(prefix, "").strip()
            folder_name = folder_name.strip("\"'")

            # Remove newlines and extra spaces
            folder_name = " ".join(folder_name.split())

            logger.debug(f"AI folder response (cleaned): '{folder_name}'")

            # Use lighter cleaning for AI-generated names
            folder_name = self._clean_ai_generated_name(folder_name, max_words=2)

            logger.debug(f"AI folder response (after filter): '{folder_name}'")

            if not folder_name or len(folder_name) < 3:
                logger.warning(f"Folder name empty or too short ('{folder_name}'), using fallback")
                folder_name = "images"

            # Final safety check
            folder_name = re.sub(r"[^\w_]", "_", folder_name)
            folder_name = re.sub(r"_+", "_", folder_name).strip("_")
            result = folder_name[:50] if folder_name else "images"
            logger.info(f"Final folder name: '{result}'")
            return result

        except (RuntimeError, ValueError, OSError, AttributeError) as e:
            logger.error(f"Failed to generate folder name: {e}")
            return "images"

    def _generate_filename(self, image_path: Path, context: str) -> str:
        """Generate a filename from image context.

        Args:
            image_path: Path to image file
            context: Description or extracted text

        Returns:
            Filename (max 3 words, no extension)
        """
        prompt = f"""Based on the image analysis below, generate a specific descriptive filename.

RULES:
1. Maximum 3 words (e.g., "sunset_mountain_view", "coffee_cup_closeup")
2. Use meaningful nouns (NO verbs like 'shows', 'depicts', 'presents')
3. NO generic words like 'image', 'photo', 'picture', 'jpg', 'untitled'
4. Use lowercase with underscores between words
5. Be specific about the content, not generic
6. Output ONLY the filename, NO explanation

EXAMPLES:
- Image of sunset over mountains → "mountain_sunset_view"
- Image of coffee cup on table → "coffee_cup_table"
- Image of laptop with code → "laptop_coding_setup"
- Image of golden retriever → "golden_retriever_dog"

IMAGE ANALYSIS:
{context[:1000]}

FILENAME:"""

        try:
            response = self._guarded_generate(
                prompt=prompt,
                image_path=image_path,
                temperature=0.3,
                max_tokens=30,
            )

            logger.debug(f"AI filename response (raw): '{response}'")

            # Clean the response
            filename = response.strip().lower()

            # Remove common prefixes and quotes
            for prefix in ["filename:", "file:", "name:", "the filename is", "the name is"]:
                filename = filename.replace(prefix, "").strip()
            filename = filename.strip("\"'")

            # Remove file extensions if AI added them
            filename = re.sub(r"\.(txt|pdf|jpg|jpeg|png|gif|bmp)$", "", filename)

            # Remove newlines and extra spaces
            filename = " ".join(filename.split())

            logger.debug(f"AI filename response (cleaned): '{filename}'")

            # Use lighter cleaning for AI-generated names
            filename = self._clean_ai_generated_name(filename, max_words=3)

            logger.debug(f"AI filename response (after filter): '{filename}'")

            if not filename or len(filename) < 3:
                logger.warning(f"Filename empty or too short ('{filename}'), using fallback")
                filename = image_path.stem

            # Final safety check
            filename = re.sub(r"[^\w_]", "_", filename)
            filename = re.sub(r"_+", "_", filename).strip("_")
            result = filename[:50] if filename else "image"
            logger.info(f"Final filename: '{result}'")
            return result

        except (RuntimeError, ValueError, OSError, AttributeError) as e:
            logger.error(f"Failed to generate filename: {e}")
            return image_path.stem

    def _guarded_generate(self, **kwargs: Any) -> str:
        """Run model.generate behind a fatal-error circuit-breaker.

        The circuit opens only for known backend fatal failures (connection
        refused, runner stopped, health endpoint refusal). While open, calls
        are short-circuited so we do not keep hammering an unhealthy backend.
        """
        if self._is_circuit_open():
            reason = self._circuit_reason or "backend unavailable"
            raise RuntimeError(f"Vision backend circuit open: {reason}")

        try:
            return self.vision_model.generate(**kwargs)
        except Exception as exc:  # Intentional catch-all: circuit-breaker for any backend error
            if self._is_fatal_backend_error(exc):
                self._trip_backend_circuit(exc)
            raise

    def _is_fatal_backend_error(self, exc: Exception) -> bool:
        """Return True when an exception indicates backend process failure."""
        text = str(exc).lower()
        return any(marker in text for marker in self._FATAL_BACKEND_MARKERS)

    def _trip_backend_circuit(self, exc: Exception) -> None:
        """Open the backend circuit for a cooldown window."""
        with self._circuit_lock:
            self._circuit_opened_at = time.monotonic()
            self._circuit_reason = str(exc)
        logger.warning("Vision backend circuit opened: {}", exc)

    def _is_circuit_open(self) -> bool:
        """Return True while backend circuit cooldown is active."""
        with self._circuit_lock:
            opened_at = self._circuit_opened_at
            if opened_at is None:
                return False
            if (time.monotonic() - opened_at) < self._backend_cooldown_seconds:
                return True
            self._circuit_opened_at = None
            self._circuit_reason = None
            return False

    def _circuit_open_error(self) -> str:
        """Return a stable, user-visible degradation message."""
        reason = self._circuit_reason or "vision backend unavailable"
        return f"Vision backend unavailable: {reason}"

    def cleanup(self) -> None:
        """Cleanup resources.

        Uses ``safe_cleanup()`` to wait for any in-flight generations
        before tearing down the model client.
        """
        if self._owns_model:
            self.vision_model.safe_cleanup()
            logger.info("Vision model cleaned up")

    def __enter__(self) -> VisionProcessor:
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: _t.TracebackType | None,
    ) -> None:
        """Context manager exit."""
        self.cleanup()
