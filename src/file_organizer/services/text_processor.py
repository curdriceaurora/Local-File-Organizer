"""Text file processing service."""

from __future__ import annotations

import re
import sys
import types as _t
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from file_organizer.models import TextModel
from file_organizer.models.base import BaseModel, ModelConfig, ModelType
from file_organizer.models.provider_factory import get_text_model
from file_organizer.utils.file_readers import FileReadError, read_file
from file_organizer.utils.readers import read_file_via_safedir_anchored
from file_organizer.utils.text_processing import (
    clean_text,
    ensure_nltk_data,
    truncate_text,
)


@dataclass
class ProcessedFile:
    """Result of file processing."""

    file_path: Path
    description: str
    folder_name: str
    filename: str
    original_content: str | None = None
    processing_time: float = 0.0
    error: str | None = None
    tags: list[str] = field(default_factory=list)
    # Best-effort audio transcript (#WP-4.1 anti-cascade audio path).
    # Populated by the dispatcher's audio pipeline when a transcriber is
    # configured and transcription succeeds within the duration cap; None
    # for metadata-only categorization or when transcription degraded on a
    # recoverable failure. Stored for the organizer's text-categorization
    # path; rendering consumers are out of scope for this port.
    transcript: str | None = None


# Stop-words and noise words filtered from AI-generated names.
# Defined at module level to avoid recreation on every call.
_CLEAN_NAME_STOP_WORDS: frozenset[str] = frozenset(
    {
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
        "with",
        "about",
        "very",
        "here",
        "words",
        "document",
        "file",
        "text",
        "untitled",
        "unknown",
    }
)


class TextProcessor:
    """Process text files using AI to generate metadata.

    This service:
    - Reads text from various file formats
    - Generates summaries using LLM
    - Creates folder names and filenames
    - Cleans and sanitizes output
    """

    def __init__(
        self,
        text_model: BaseModel | None = None,
        config: ModelConfig | None = None,
    ) -> None:
        """Initialize text processor.

        Args:
            text_model: Pre-initialized text model (optional). Any
                ``BaseModel`` subclass is accepted, allowing Ollama and
                OpenAI-compatible models to be passed interchangeably.
            config: Model configuration (used if ``text_model`` not provided).
                The ``config.provider`` field controls which backend is used.
                If omitted, the Ollama default configuration is applied
                regardless of any global provider setting.
        """
        if text_model is not None:
            if text_model.config.model_type != ModelType.TEXT:
                raise ValueError(
                    f"TextProcessor requires a TEXT model, got {text_model.config.model_type}"
                )
            self.text_model = text_model
            self._owns_model = False
        else:
            config = config or TextModel.get_default_config()
            self.text_model = get_text_model(config)
            self._owns_model = True

        # Ensure NLTK data is available
        ensure_nltk_data()

        logger.info("TextProcessor initialized")

    def initialize(self) -> None:
        """Initialize the text model if not already initialized."""
        if not self.text_model.is_initialized:
            self.text_model.initialize()
            logger.info("Text model initialized")

    @staticmethod
    def _read_content(file_path: Path, scan_root: str | Path | None) -> str | None:
        """Read *file_path*, routing through SafeDir when *scan_root* is given.

        With *scan_root* — the trusted directory the caller walked to discover
        *file_path* — the read goes through
        :func:`file_organizer.utils.readers.read_file_via_safedir_anchored`,
        which ``O_NOFOLLOW``-walks every component from the root so a symlink
        swapped in after the scan is refused (``SymlinkRejected``, an
        ``OSError`` subclass that propagates to ``process_file``'s handler)
        rather than dereferenced. Falls back to the legacy path-based reader on
        Windows or where SafeDir is unavailable (``NotImplementedError``).
        """
        if scan_root is not None and sys.platform != "win32":
            try:
                return read_file_via_safedir_anchored(file_path, trusted_root=Path(scan_root))
            except (NotImplementedError, ValueError):
                logger.debug(
                    "SafeDir unavailable or path outside root; legacy read for {}", file_path.name
                )
        return read_file(file_path)

    def process_file(
        self,
        file_path: str | Path,
        generate_description: bool = True,
        generate_folder: bool = True,
        generate_filename: bool = True,
        *,
        scan_root: str | Path | None = None,
        relative_path: str | Path | None = None,
        generate_tags: bool = False,
    ) -> ProcessedFile:
        """Process a single text file.

        Args:
            file_path: Path to file
            generate_description: Whether to generate description
            generate_folder: Whether to generate folder name
            generate_filename: Whether to generate filename
            scan_root: Trusted directory the caller walked to discover
                *file_path*. When supplied (POSIX), content is read through
                ``read_file_via_safedir_anchored`` so a symlink swapped in after
                the scan is refused rather than dereferenced (#264/#286).
                ``None`` keeps the legacy path-based read.
            relative_path: Relative path or directory context of the file to
                enrich LLM prompts (Upstream #66). If omitted and ``scan_root``
                is present, automatically computed from ``scan_root``.
            generate_tags: Whether to generate descriptive tags (Upstream #64).

        Returns:
            ProcessedFile with metadata
        """
        import time

        file_path = Path(file_path)
        start_time = time.time()

        if relative_path is None and scan_root is not None:
            try:
                relative_path = file_path.relative_to(Path(scan_root))
            except ValueError:
                relative_path = file_path.name
        rel_str = str(relative_path) if relative_path is not None else None

        try:
            # Read file content
            logger.debug("Reading file: {}", file_path.name)
            content = self._read_content(file_path, scan_root)

            if content is None:
                return ProcessedFile(
                    file_path=file_path,
                    description="",
                    folder_name="unsupported",
                    filename=file_path.stem,
                    error="Unsupported file type",
                )

            # Truncate if too long
            content = truncate_text(content, max_chars=5000)

            # Generate description (summary)
            description = ""
            if generate_description:
                description = self._generate_description(
                    content, file_name=file_path.name, relative_path=rel_str
                )
                logger.debug("Generated description ({} chars)", len(description))

            # Generate folder name
            folder_name = ""
            if generate_folder:
                folder_name = self._generate_folder_name(
                    description or content,
                    original_stem=file_path.stem,
                    relative_path=rel_str,
                )
                logger.debug("Generated folder name ({} chars)", len(folder_name))

            # Generate filename
            filename = ""
            if generate_filename:
                filename = self._generate_filename(
                    description or content,
                    original_stem=file_path.stem,
                    relative_path=rel_str,
                )
                logger.debug("Generated filename ({} chars)", len(filename))

            # Generate tags
            tags: list[str] = []
            if generate_tags:
                tags = self._generate_tags(
                    description or content,
                    file_name=file_path.name,
                    relative_path=rel_str,
                )
                logger.debug("Generated tags ({} items)", len(tags))

            processing_time = time.time() - start_time

            return ProcessedFile(
                file_path=file_path,
                description=description,
                folder_name=folder_name,
                filename=filename,
                original_content=content[:500],  # Keep first 500 chars for reference
                processing_time=processing_time,
                tags=tags,
            )

        except FileReadError as e:
            logger.error(f"Failed to read {file_path.name}: {e}")
            return ProcessedFile(
                file_path=file_path,
                description="",
                folder_name="errors",
                filename=file_path.stem,
                error=str(e),
            )
        except (RuntimeError, ValueError, OSError, AttributeError) as e:
            logger.exception(f"Failed to process {file_path.name}: {e}")
            return ProcessedFile(
                file_path=file_path,
                description="",
                folder_name="errors",
                filename=file_path.stem,
                error=str(e),
            )

    def _clean_ai_generated_name(self, name: str, max_words: int = 3) -> str:
        """Clean AI-generated folder/file names by stripping stop-words and noise.

        Filters common stop-words (articles, prepositions, filler adjectives) and
        generic noise words (file, document, untitled) so only meaningful terms remain.

        Args:
            name: AI-generated name
            max_words: Maximum number of words

        Returns:
            Cleaned name
        """
        # Convert underscores and hyphens to spaces
        name = name.replace("_", " ").replace("-", " ")

        # Remove special characters (keep letters, digits and spaces)
        name = re.sub(r"[^a-z0-9\s]", "", name.lower())

        # Split into words
        words = name.split()

        # Filter and deduplicate
        filtered = []
        seen = set()
        for word in words:
            if word and word not in _CLEAN_NAME_STOP_WORDS and word not in seen and len(word) > 1:
                filtered.append(word)
                seen.add(word)

        # Limit to max words
        filtered = filtered[:max_words]

        # Join with underscores
        return "_".join(filtered) if filtered else ""

    def _generate_description(
        self,
        content: str,
        file_name: str | None = None,
        relative_path: str | Path | None = None,
    ) -> str:
        """Generate a summary/description of the content.

        Args:
            content: File content
            file_name: Name of the file being summarized
            relative_path: Relative path or directory context of the file

        Returns:
            Summary text
        """
        context_parts = []
        if file_name:
            context_parts.append(f"FILENAME: {file_name}")
        if relative_path:
            context_parts.append(f"PATH CONTEXT: {relative_path}")
        context_header = ("\n" + "\n".join(context_parts) + "\n") if context_parts else ""

        prompt = f"""Summarize the following text in 100-150 words. Focus on main ideas and key details.{context_header}
TEXT:
{content}

SUMMARY:"""

        try:
            response = self.text_model.generate(prompt, temperature=0.5, max_tokens=200)
            summary = response.strip()

            # Remove any "Summary:" prefix the AI might add
            for prefix in ["summary:", "here is the summary:", "the summary is:"]:
                if summary.lower().startswith(prefix):
                    summary = summary[len(prefix) :].strip()

            return summary
        except (RuntimeError, ValueError, OSError, AttributeError) as e:
            logger.error(f"Failed to generate description: {e}")
            return f"Content about {content[:100]}..."

    def _generate_folder_name(
        self,
        text: str,
        original_stem: str | None = None,
        relative_path: str | Path | None = None,
    ) -> str:
        """Generate a folder name from text.

        Args:
            text: Description or content
            original_stem: Original filename stem (without extension) used as an
                additional hint for small models with limited context.
            relative_path: Relative path or directory context of the file.

        Returns:
            Folder name (max 2 words)
        """
        hint_parts = []
        if relative_path:
            hint_parts.append(
                f"PATH & FILENAME HINT: {relative_path} (existing file path context — use only if helpful)"
            )
        elif original_stem:
            hint_parts.append(
                f"FILENAME HINT: {original_stem} (original filename — use only if helpful)"
            )
        hint_line = ("\n" + "\n".join(hint_parts) + "\n") if hint_parts else ""

        prompt = f"""Based on the text below, generate a general category or theme.

RULES:
1. Maximum 2 words (e.g., "machine_learning", "healthcare", "recipes")
2. Use ONLY nouns, no verbs
3. Be general, not specific
4. Use lowercase with underscores between words
5. NO generic terms like 'document', 'file', 'text', 'untitled'
6. Output ONLY the category, NO explanation

EXAMPLES:
- Text about AI in healthcare → "healthcare_technology"
- Text about Python coding → "programming"
- Text about chocolate recipes → "recipes"
- Text about financial planning → "finance"
{hint_line}
TEXT:
{text[:1000]}

CATEGORY:"""

        try:
            response = self.text_model.generate(prompt, temperature=0.3, max_tokens=30)

            # Debug: Log raw AI response
            logger.debug("AI folder response received ({} chars)", len(response))

            # Clean the response
            folder_name = response.strip().lower()

            # Remove common prefixes and quotes
            for prefix in ["category:", "folder:", "the category is", "the folder is"]:
                folder_name = folder_name.replace(prefix, "").strip()
            folder_name = folder_name.strip("\"'")

            # Remove newlines and extra spaces
            folder_name = " ".join(folder_name.split())

            # Use lighter cleaning for AI-generated names
            folder_name = self._clean_ai_generated_name(folder_name, max_words=2)

            if not folder_name or len(folder_name) < 3:
                # Fallback to keyword extraction
                logger.warning(
                    "Folder name empty or too short after AI generation, using keyword fallback"
                )
                folder_name = clean_text(text, max_words=2)
                logger.debug("Fallback folder name ({} chars)", len(folder_name))

            # Skip sanitize_filename since we already cleaned it
            # Just do final safety check
            import re

            folder_name = re.sub(r"[^\w_]", "_", folder_name)
            folder_name = re.sub(r"_+", "_", folder_name).strip("_")
            result = folder_name[:50] if folder_name else "documents"
            logger.info(f"Folder name generated ({len(result)} chars)")
            return result

        except (RuntimeError, ValueError, OSError, AttributeError) as e:
            logger.error(f"Failed to generate folder name: {e}")
            return "documents"

    def _generate_filename(
        self,
        text: str,
        original_stem: str | None = None,
        relative_path: str | Path | None = None,
    ) -> str:
        """Generate a filename from text.

        Args:
            text: Description or content
            original_stem: Original filename stem (without extension) used as an
                additional hint for small models with limited context.
            relative_path: Relative path or directory context of the file.

        Returns:
            Filename (max 3 words, no extension)
        """
        hint_parts = []
        if relative_path:
            hint_parts.append(
                f"PATH & FILENAME HINT: {relative_path} (existing file path context — use only if helpful)"
            )
        elif original_stem:
            hint_parts.append(
                f"FILENAME HINT: {original_stem} (original filename — use only if helpful)"
            )
        hint_line = ("\n" + "\n".join(hint_parts) + "\n") if hint_parts else ""

        prompt = f"""Based on the text below, generate a specific descriptive filename.

RULES:
1. Maximum 3 words (e.g., "ai_healthcare_analysis", "python_best_practices")
2. Use meaningful nouns (NO verbs like 'shows', 'depicts', 'presents')
3. NO generic words like 'document', 'text', 'file', 'pdf', 'untitled'
4. Use lowercase with underscores between words
5. Be specific about the content, not generic
6. Output ONLY the filename, NO explanation

EXAMPLES:
- Text about AI in healthcare → "ai_healthcare_technology"
- Text about Python coding tips → "python_coding_guide"
- Text about chocolate chip cookies → "chocolate_chip_cookies"
- Text about 2023 budget → "budget_2023"
{hint_line}
TEXT:
{text[:1000]}

FILENAME:"""

        try:
            response = self.text_model.generate(prompt, temperature=0.3, max_tokens=30)

            # Debug: Log raw AI response
            logger.debug("AI filename response received ({} chars)", len(response))

            # Clean the response
            filename = response.strip().lower()

            # Remove common prefixes and quotes
            for prefix in ["filename:", "file:", "name:", "the filename is", "the name is"]:
                filename = filename.replace(prefix, "").strip()
            filename = filename.strip("\"'")

            # Remove file extensions if AI added them
            import re

            filename = re.sub(r"\.(txt|pdf|docx|md|jpg|png)$", "", filename)

            # Remove newlines and extra spaces
            filename = " ".join(filename.split())

            # Use lighter cleaning for AI-generated names
            filename = self._clean_ai_generated_name(filename, max_words=3)

            if not filename or len(filename) < 3:
                # Fallback to keyword extraction
                logger.warning(
                    "Filename empty or too short after AI generation, using keyword fallback"
                )
                filename = clean_text(text, max_words=3)
                logger.debug("Fallback filename ({} chars)", len(filename))

            # Skip sanitize_filename since we already cleaned it
            # Just do final safety check
            import re

            filename = re.sub(r"[^\w_]", "_", filename)
            filename = re.sub(r"_+", "_", filename).strip("_")
            result = filename[:50] if filename else "document"
            logger.info(f"Filename generated ({len(result)} chars)")
            return result

        except (RuntimeError, ValueError, OSError, AttributeError) as e:
            logger.error(f"Failed to generate filename: {e}")
            return "document"

    def _generate_tags(
        self,
        text: str,
        file_name: str | None = None,
        relative_path: str | Path | None = None,
        style: str | None = None,
        custom_prompt: str | None = None,
        max_tags: int = 6,
    ) -> list[str]:
        """Generate descriptive tags for the file using the AI model.

        Args:
            text: File content or description
            file_name: Name of the file
            relative_path: Relative path or directory context of the file
            style: Optional tagging style (e.g., "sfx", "audio", "code", "descriptive")
            custom_prompt: Optional user instructions for tag selection
            max_tags: Maximum number of tags to generate

        Returns:
            List of clean, lowercase, underscore-separated tags
        """
        hint_parts = []
        if file_name:
            hint_parts.append(f"FILENAME: {file_name}")
        if relative_path:
            hint_parts.append(f"PATH: {relative_path}")
        if style:
            hint_parts.append(f"STYLE: {style}")
        if custom_prompt:
            hint_parts.append(f"INSTRUCTIONS: {custom_prompt}")
        context_header = ("\n" + "\n".join(hint_parts) + "\n") if hint_parts else ""

        prompt = f"""Generate up to {max_tags} concise, relevant tags for this file.

RULES:
1. Each tag must be 1-2 words in lowercase, separated by commas (e.g. machine_learning, finance, audio)
2. Use ONLY lowercase alphanumeric characters and underscores
3. NO generic words like 'file', 'document', 'text', 'untitled'
4. Output ONLY the comma-separated tags, nothing else
{context_header}
CONTENT:
{text[:1000]}

TAGS:"""
        try:
            response = self.text_model.generate(prompt, temperature=0.3, max_tokens=60)
            raw_tags = [t.strip().lower() for t in response.split(",") if t.strip()]
            cleaned_tags = []
            for t in raw_tags:
                tag = re.sub(r"[^\w_]", "_", t)
                tag = re.sub(r"_+", "_", tag).strip("_")
                if (
                    tag
                    and tag not in _CLEAN_NAME_STOP_WORDS
                    and len(tag) > 1
                    and tag not in cleaned_tags
                ):
                    cleaned_tags.append(tag)
            return cleaned_tags[:max_tags]
        except Exception as e:
            logger.debug("Failed to generate AI tags: {}", e)
            return []

    def cleanup(self) -> None:
        """Cleanup resources.

        Uses ``safe_cleanup()`` to wait for any in-flight generations
        before tearing down the model client.
        """
        if self._owns_model:
            self.text_model.safe_cleanup()
            logger.info("Text model cleaned up")

    def __enter__(self) -> TextProcessor:
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
