"""Text file processing service."""

from __future__ import annotations

import json
import re
import sys
import types as _t
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pydantic
from loguru import logger

from file_organizer.models import TextModel
from file_organizer.models.base import (
    BaseModel,
    ModelConfig,
    ModelType,
    StructuredParseError,
)
from file_organizer.models.provider_factory import get_text_model
from file_organizer.services.auto_tagging.tag_normalize import normalize_tags
from file_organizer.utils.file_readers import FileReadError, read_file
from file_organizer.utils.paths import format_path_context_clause, resolve_relative_path
from file_organizer.utils.readers import read_file_via_safedir_anchored
from file_organizer.utils.text_processing import (
    clean_text,
    ensure_nltk_data,
    truncate_text,
)


class TextAnalysisSchema(pydantic.BaseModel):
    """Schema for structured text analysis including description and tags."""

    description: str = pydantic.Field(
        description="A 100-150 word summary of the text focusing on main ideas and key details."
    )
    tags: list[str] = pydantic.Field(
        default_factory=list,
        description="3-8 lowercase tags (single words or hyphenated phrases) describing the content.",
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
    # Best-effort audio transcript (#WP-4.1 anti-cascade audio path).
    # Populated by the dispatcher's audio pipeline when a transcriber is
    # configured and transcription succeeds within the duration cap; None
    # for metadata-only categorization or when transcription degraded on a
    # recoverable failure. Stored for the organizer's text-categorization
    # path; rendering consumers are out of scope for this port.
    transcript: str | None = None
    tags: list[str] = field(default_factory=list)


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
            except NotImplementedError:
                logger.debug("SafeDir unavailable; legacy read for {}", file_path.name)
        return read_file(file_path)

    def process_file(
        self,
        file_path: str | Path,
        generate_description: bool = True,
        generate_folder: bool = True,
        generate_filename: bool = True,
        *,
        scan_root: str | Path | None = None,
        relative_path: str | None = None,
        generate_tags: bool = False,
        tag_style: str | None = None,
        tag_prompt: str | None = None,
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
            relative_path: Optional explicit relative path context for prompts.
                When omitted, auto-derived from *scan_root* via
                :func:`resolve_relative_path`.
            generate_tags: Whether to generate descriptive tags using the text model.
            tag_style: Optional tagging style preset name.
            tag_prompt: Optional user-supplied tagging guidance prompt.

        Returns:
            ProcessedFile with metadata
        """
        import time

        file_path = Path(file_path)
        start_time = time.time()

        if relative_path is None:
            relative_path = resolve_relative_path(file_path, scan_root)
        path_clause = format_path_context_clause(relative_path)

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

            # Generate description (summary) and tags
            description = ""
            tags: list[str] = []
            if generate_tags:
                description, tags = self._analyze_structured(
                    content,
                    path_clause=path_clause,
                    tag_style=tag_style,
                    tag_prompt=tag_prompt,
                    generate_description=generate_description,
                )
            elif generate_description:
                description = self._generate_description(content, path_clause=path_clause)
                logger.debug("Generated description ({} chars)", len(description))

            # Generate folder name
            folder_name = ""
            if generate_folder:
                folder_name = self._generate_folder_name(
                    description or content,
                    original_stem=file_path.stem,
                    path_clause=path_clause,
                )
                logger.debug("Generated folder name ({} chars)", len(folder_name))

            # Generate filename
            filename = ""
            if generate_filename:
                filename = self._generate_filename(
                    description or content,
                    original_stem=file_path.stem,
                    path_clause=path_clause,
                )
                logger.debug("Generated filename ({} chars)", len(filename))

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

    def _analyze_structured(
        self,
        content: str,
        *,
        path_clause: str,
        tag_style: str | None,
        tag_prompt: str | None,
        generate_description: bool,
    ) -> tuple[str, list[str]]:
        """Run structured generation to produce description and tags.

        When *generate_description* is True, falls back to plain-text description
        generation on failure and returns ``(description, [])``. When False, skips
        the fallback call and returns ``("", [])``.
        """
        style_clause = (
            f"Favor terms fitting the '{tag_style}' domain (see the {tag_style} vocabulary hints below).\n"
            if tag_style
            else ""
        )
        prompt_clause = (
            f"Additional guidance: {json.dumps(tag_prompt, ensure_ascii=True)}\n"
            if tag_prompt
            else ""
        )
        parts = [
            "Analyze the following text. Provide a 100-150 word summary in the 'description' field, "
            "and 3-8 lowercase tags (single words or hyphenated phrases) in the 'tags' field."
        ]
        if path_clause:
            parts.append(path_clause.strip())
        if style_clause:
            parts.append(style_clause.strip())
        if prompt_clause:
            parts.append(prompt_clause.strip())
        structured_prompt = "\n".join(parts) + f"\n\nTEXT:\n{content}\n"

        try:
            schema_result = cast(
                TextAnalysisSchema,
                self.text_model.generate_structured(structured_prompt, schema=TextAnalysisSchema),
            )
            description = ""
            if generate_description:
                description = schema_result.description.strip()
                for prefix in ["summary:", "here is the summary:", "the summary is:"]:
                    if description.lower().startswith(prefix):
                        description = description[len(prefix) :].strip()
                logger.debug("Generated description ({} chars)", len(description))
            raw_tags = schema_result.tags
            if isinstance(raw_tags, str):
                raw_tags = [t.strip() for t in raw_tags.split(",")]
            tags = normalize_tags(raw_tags)
            logger.debug("Generated tags: {}", tags)
            return description, tags
        except (RuntimeError, ValueError, OSError, AttributeError, StructuredParseError) as e:
            logger.warning("Structured text analysis failed, falling back: {}", e)
            if generate_description:
                desc = self._generate_description(content, path_clause=path_clause)
                logger.debug("Generated description via fallback ({} chars)", len(desc))
                return desc, []
            return "", []

    def _generate_description(self, content: str, path_clause: str = "") -> str:
        """Generate a summary/description of the content.

        Args:
            content: File content
            path_clause: Formatted path context clause for prompt enrichment

        Returns:
            Summary text
        """
        path_line = f"\n{path_clause.strip()}\n" if path_clause else ""
        prompt = f"""Summarize the following text in 100-150 words. Focus on main ideas and key details.{path_line}
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
        path_clause: str = "",
    ) -> str:
        """Generate a folder name from text.

        Args:
            text: Description or content
            original_stem: Original filename stem (without extension) used as an
                additional hint for small models with limited context.
            path_clause: Formatted path context clause for prompt enrichment

        Returns:
            Folder name (max 2 words)
        """
        hint_line = (
            f"\nFILENAME HINT: {original_stem} (original filename — use only if helpful)\n"
            if original_stem
            else ""
        )
        path_line = f"\n{path_clause.strip()}\n" if path_clause else ""
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
{hint_line}{path_line}
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
        path_clause: str = "",
    ) -> str:
        """Generate a filename from text.

        Args:
            text: Description or content
            original_stem: Original filename stem (without extension) used as an
                additional hint for small models with limited context.
            path_clause: Formatted path context clause for prompt enrichment

        Returns:
            Filename (max 3 words, no extension)
        """
        hint_line = (
            f"\nFILENAME HINT: {original_stem} (original filename — use only if helpful)\n"
            if original_stem
            else ""
        )
        path_line = f"\n{path_clause.strip()}\n" if path_clause else ""
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
{hint_line}{path_line}
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
