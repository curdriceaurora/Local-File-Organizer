"""Vision file processing service."""

from __future__ import annotations

import io
import mimetypes
import re
import threading
import time
import types as _t
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from file_organizer.models import VisionModel
from file_organizer.models.base import BaseModel, ModelConfig, ModelType
from file_organizer.models.provider_factory import get_vision_model
from file_organizer.models.vision_schema import VisionSchema
from file_organizer.services.inference_timer import time_inference
from file_organizer.utils.paths import format_path_context_clause, resolve_relative_path


@dataclass
class ProcessedImage:
    """Result of image processing.

    The ``source`` field indicates how the categorization was produced:
    ``"vision"`` is the normal AI-model path; ``"fallback_exif"`` and
    ``"fallback_filename"`` mark low-confidence placements assigned by
    the metadata-only fallback (#406) when the vision call timed out.
    """

    file_path: Path
    description: str
    folder_name: str
    filename: str
    has_text: bool = False
    extracted_text: str | None = None
    processing_time: float = 0.0
    error: str | None = None
    source: str = "vision"
    # Wall-clock duration of the inference path measured in milliseconds
    # (#410). Populated even on the error / fallback paths so summary
    # aggregation (p50/p95/p99) reflects every per-file attempt, not just
    # the happy path. None on results assembled without going through
    # process_file (e.g. metadata-only fallback constructed by the
    # dispatcher).
    inference_ms: float | None = None
    # Categorization confidence in [0.0, 1.0] (#409). 1.0 = happy-path
    # vision inference, 0.5 = EXIF-based fallback, 0.3 = filename-only
    # fallback (#406 metadata path), 0.0 = error / no usable result.
    # Files below `AppConfig.processing.low_confidence_threshold` are
    # surfaced in the summary's "Review recommended" section.
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)


def _mime_type_for_image_format(image_format: str | None) -> str:
    """Map a Pillow image format to the MIME type emitted by preprocessing."""
    if image_format == "JPEG":
        return "image/jpeg"
    if image_format in {"PNG", "WEBP", "GIF"}:
        return f"image/{image_format.lower()}"
    return "image/jpeg"


_VISION_API_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}
)


def preprocess_and_clamp_image(image_path: Path, max_edge: int = 1024) -> tuple[bytes, str]:
    """Load, validate dimensions, and clamp/resize image to fit within max_edge limit.

    If Pillow is not installed, returns the raw un-clamped bytes of the file
    with a MIME type guessed from the filename.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed; skipping shape validation and clamping.")
        guessed, _ = mimetypes.guess_type(str(image_path))
        return image_path.read_bytes(), guessed or "image/jpeg"

    try:
        with Image.open(image_path) as opened_img:
            img: Image.Image = opened_img
            width, height = img.size
            if width == 0 or height == 0:
                raise ValueError(f"Invalid image dimensions: {width}x{height}")

            needs_resize = max(width, height) > max_edge
            if needs_resize:
                if width > height:
                    new_width = max_edge
                    new_height = int(height * (max_edge / width))
                else:
                    new_height = max_edge
                    new_width = int(width * (max_edge / height))

                resample = getattr(Image, "Resampling", None)
                filter_type = getattr(resample, "LANCZOS", 1)

                img = img.resize((new_width, new_height), filter_type)
                logger.info(
                    "Clamped image {} from {}x{} to {}x{}",
                    image_path.name,
                    width,
                    height,
                    new_width,
                    new_height,
                )

            img_format = img.format or "JPEG"
            if img_format not in ("JPEG", "PNG", "WEBP", "GIF"):
                img_format = "JPEG"
            mime_type = _mime_type_for_image_format(img_format)

            needs_rgb_conversion = img_format == "JPEG" and img.mode in ("RGBA", "LA", "P")
            if (
                not needs_resize
                and not needs_rgb_conversion
                and img_format == (img.format or "JPEG")
            ):
                return image_path.read_bytes(), mime_type

            if needs_rgb_conversion:
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format=img_format)
            return buf.getvalue(), mime_type
    except Exception as e:
        logger.warning(
            "Image preprocessing failed for {}: {}. Using raw bytes.",
            image_path.name,
            e,
        )
        guessed, _ = mimetypes.guess_type(str(image_path))
        return image_path.read_bytes(), guessed or "image/jpeg"


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
        "out of memory",
        "oom:",
        "oom ",
        "failed to allocate",
        "cuda out of memory",
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
        *,
        context_root: Path | None = None,
    ) -> ProcessedImage:
        """Process a single image file.

        Args:
            file_path: Path to image file
            generate_description: Whether to generate description
            generate_folder: Whether to generate folder name
            generate_filename: Whether to generate filename
            perform_ocr: Whether to extract text (OCR)
            context_root: Optional directory path used exclusively for prompt
                context hints (relative path / parent folder). Does not gate
                the image read.

        Returns:
            ProcessedImage with metadata
        """
        file_path = Path(file_path)
        start_time = time.time()

        # Per-file inference timer (#410). The context manager exposes the
        # measured duration on ``_timer.elapsed_ms`` and emits a structured
        # ``vision_inference_ms=<N>`` log line for invoked calls. The inner
        # method returns a (result, model_invoked) tuple so timing is
        # attributed only when a model call was actually attempted —
        # pre-inference early returns (circuit-open, file-not-found) do not
        # contribute to the p95/p99 sample set.
        with time_inference("vision", file_path) as _timer:
            result, model_invoked = self._process_file_inner(
                file_path,
                start_time=start_time,
                generate_description=generate_description,
                generate_folder=generate_folder,
                generate_filename=generate_filename,
                perform_ocr=perform_ocr,
                context_root=context_root,
            )
            if model_invoked:
                _timer.mark_invoked()
        if model_invoked:
            result.inference_ms = _timer.elapsed_ms
        return result

    def _process_file_inner(
        self,
        file_path: Path,
        *,
        start_time: float,
        generate_description: bool,
        generate_folder: bool,
        generate_filename: bool,
        perform_ocr: bool,
        context_root: Path | None = None,
    ) -> tuple[ProcessedImage, bool]:
        """Inner body of :meth:`process_file` using structured generation.

        Returns ``(result, model_invoked)``.
        """
        model_invoked = False
        try:
            if not (generate_description or generate_folder or generate_filename or perform_ocr):
                # All flags off, bypass model call entirely
                processing_time = time.time() - start_time
                return (
                    ProcessedImage(
                        file_path=file_path,
                        description="",
                        folder_name="",
                        filename="",
                        has_text=False,
                        extracted_text=None,
                        processing_time=processing_time,
                        source="vision",
                        confidence=1.0,
                    ),
                    False,  # no model call attempted
                )

            if self._is_circuit_open():
                logger.warning(
                    "Vision backend circuit open; skipping model calls for {}",
                    file_path.name,
                )
                error_message = self._circuit_open_error()
                from file_organizer.services.vision_fallback import compute_fallback

                fb = compute_fallback(file_path)
                fallback_conf = 0.5 if fb.source == "fallback_exif" else 0.3
                return (
                    ProcessedImage(
                        file_path=file_path,
                        description=f"Image from {file_path.name}",
                        folder_name=fb.folder,
                        filename=fb.filename,
                        error=error_message,
                        source=fb.source,
                        confidence=fallback_conf,
                    ),
                    False,  # no model call attempted
                )

            # Validate file exists
            if not file_path.exists():
                return (
                    ProcessedImage(
                        file_path=file_path,
                        description="",
                        folder_name="errors",
                        filename=file_path.stem,
                        error="File not found",
                        confidence=0.0,
                    ),
                    False,  # no model call attempted
                )

            if file_path.suffix.lower() not in _VISION_API_SUPPORTED_EXTENSIONS:
                from file_organizer.services.vision_fallback import compute_fallback

                fb = compute_fallback(file_path)
                fallback_conf = 0.5 if fb.source == "fallback_exif" else 0.3
                return (
                    ProcessedImage(
                        file_path=file_path,
                        description=f"Image from {file_path.name}",
                        folder_name=fb.folder,
                        filename=fb.filename,
                        error=(
                            "Unsupported image format for vision model: "
                            f"{file_path.suffix.lower() or '<none>'}"
                        ),
                        source=fb.source,
                        confidence=fallback_conf,
                    ),
                    False,  # no model call attempted
                )

            # Preprocess and clamp image
            image_bytes, image_mime_type = preprocess_and_clamp_image(file_path)

            relative_path = resolve_relative_path(file_path, context_root)
            path_clause = format_path_context_clause(relative_path)

            prompt = self._build_structured_prompt(
                file_path=file_path,
                generate_folder=generate_folder,
                generate_filename=generate_filename,
                perform_ocr=perform_ocr,
                path_clause=path_clause,
            )

            logger.debug(f"Analyzing image: {file_path.name}")
            model_invoked = True

            # Call structured generation
            schema_result = self._guarded_generate_structured(
                prompt=prompt,
                schema=VisionSchema,
                image_data=image_bytes,
                mime_type=image_mime_type,
            )

            description = schema_result.description if generate_description else ""
            has_text = schema_result.has_text if perform_ocr else False
            extracted_text = (
                (schema_result.extracted_text if has_text else None) if perform_ocr else None
            )

            # Clean folder name
            folder_name = ""
            if generate_folder:
                folder_name = schema_result.folder_name
                # Remove common prefixes and quotes
                for prefix in ["folder:", "category:", "the folder is", "the category is"]:
                    folder_name = folder_name.replace(prefix, "").strip()
                folder_name = folder_name.strip("\"'")
                folder_name = self._clean_ai_generated_name(folder_name, max_words=2)
                if not folder_name or len(folder_name) < 3:
                    folder_name = "images"
            else:
                folder_name = "images"

            # Clean filename
            filename = ""
            if generate_filename:
                filename = schema_result.filename
                # Remove common prefixes and quotes
                for prefix in ["filename:", "file:", "name:", "the filename is", "the name is"]:
                    filename = filename.replace(prefix, "").strip()
                filename = filename.strip("\"'")
                # Remove file extensions if AI added them
                filename = re.sub(r"\.(txt|pdf|jpg|jpeg|png|gif|bmp)$", "", filename)
                filename = self._clean_ai_generated_name(filename, max_words=3)
                if not filename or len(filename) < 3:
                    filename = file_path.stem
                # Final safety check
                filename = re.sub(r"[^\w_]", "_", filename)
                filename = re.sub(r"_+", "_", filename).strip("_")
                filename = filename[:50] if filename else "image"
            else:
                filename = file_path.stem

            processing_time = time.time() - start_time

            return (
                ProcessedImage(
                    file_path=file_path,
                    description=description,
                    folder_name=folder_name,
                    filename=filename,
                    has_text=has_text,
                    extracted_text=extracted_text[:500] if extracted_text else None,
                    processing_time=processing_time,
                    source="vision",
                    confidence=1.0,
                ),
                model_invoked,
            )

        except Exception as e:
            logger.exception(f"Failed to process {file_path.name}: {e}")
            # Fallback to metadata-only fallback
            from file_organizer.services.vision_fallback import compute_fallback

            try:
                fb = compute_fallback(file_path)
                fallback_conf = 0.5 if fb.source == "fallback_exif" else 0.3
                return (
                    ProcessedImage(
                        file_path=file_path,
                        description=f"Image from {file_path.name}",
                        folder_name=fb.folder,
                        filename=fb.filename,
                        error=str(e),
                        source=fb.source,
                        confidence=fallback_conf,
                    ),
                    model_invoked,
                )
            except Exception as fb_exc:
                logger.error(f"Fallback also failed for {file_path.name}: {fb_exc}")
                return (
                    ProcessedImage(
                        file_path=file_path,
                        description="",
                        folder_name="errors",
                        filename=file_path.stem,
                        error=str(e),
                        confidence=0.0,
                    ),
                    model_invoked,
                )

    def _build_structured_prompt(
        self,
        *,
        file_path: Path,
        generate_folder: bool,
        generate_filename: bool,
        perform_ocr: bool,
        path_clause: str = "",
    ) -> str:
        """Build the structured single-call image analysis prompt."""
        prompt_lines = [
            "Analyze this image and provide the following details:",
        ]
        if path_clause:
            prompt_lines.append(path_clause.strip())
        prompt_lines.append(
            "- description: A detailed description of the main subject and important details."
        )
        if generate_folder:
            prompt_lines.append(
                "- folder_name: A general plural lowercase category (max 2 words) e.g. 'screenshots', 'receipts'."
            )
        else:
            prompt_lines.append("- folder_name: Return the string 'images'.")

        if generate_filename:
            prompt_lines.append(
                "- filename: A descriptive snake_case filename (max 3 words) e.g. 'grocery_receipt_target'."
            )
        else:
            prompt_lines.append(f"- filename: Return the string '{file_path.stem}'.")

        if perform_ocr:
            prompt_lines.append(
                "- has_text: True if there is significant visible text that should be extracted."
            )
            prompt_lines.append(
                "- extracted_text: The exact text extracted from the image if has_text is True."
            )
        else:
            prompt_lines.append("- has_text: Return False.")
            prompt_lines.append("- extracted_text: Return null.")

        return "\n".join(prompt_lines)

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

    def _guarded_generate_structured(self, **kwargs: Any) -> Any:
        """Run model.generate_structured behind a fatal-error circuit-breaker."""
        if self._is_circuit_open():
            reason = self._circuit_reason or "backend unavailable"
            raise RuntimeError(f"Vision backend circuit open: {reason}")

        try:
            return self.vision_model.generate_structured(**kwargs)
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
