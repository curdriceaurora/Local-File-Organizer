"""Content Tag Analyzer.

Analyzes file content to extract relevant tags using multiple techniques:
- Keyword extraction (TF-IDF)
- Topic modeling (LDA)
- Entity recognition
- File metadata analysis
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "sfx": {
        "description": "Sound effects and Foley library categorization",
        "keywords": {
            "foley",
            "impact",
            "explosion",
            "weapon",
            "gunshot",
            "laser",
            "blaster",
            "sci-fi",
            "ambience",
            "ambient",
            "ui",
            "click",
            "beep",
            "button",
            "footstep",
            "whoosh",
            "transition",
            "magic",
            "spell",
            "vehicle",
            "engine",
            "crash",
            "creature",
            "monster",
            "vocal",
            "water",
            "splash",
            "fire",
            "wind",
            "nature",
            "glitch",
            "distortion",
            "drone",
            "cinematic",
            "sub",
            "bass",
            "drop",
            "loop",
            "oneshot",
            "stereo",
            "mono",
            "audio",
            "sound",
            "punch",
            "hit",
            "gore",
        },
    },
    "audio": {
        "description": "Music and audio production",
        "keywords": {
            "music",
            "beat",
            "melody",
            "synth",
            "vocal",
            "drums",
            "bass",
            "guitar",
            "piano",
            "acoustic",
            "electronic",
            "ambient",
            "loop",
            "sample",
            "stem",
            "mix",
            "master",
            "tempo",
            "bpm",
            "chord",
            "audio",
            "track",
            "song",
        },
    },
    "code": {
        "description": "Software development and source code",
        "keywords": {
            "backend",
            "frontend",
            "api",
            "cli",
            "test",
            "service",
            "model",
            "controller",
            "util",
            "helper",
            "config",
            "schema",
            "router",
            "auth",
            "component",
            "hook",
            "database",
            "migration",
            "script",
            "pipeline",
            "docker",
            "ci",
        },
    },
    "descriptive": {
        "description": "Detailed conceptual and semantic descriptors",
    },
    "hierarchical": {
        "description": "Multi-level category hierarchy",
    },
}


class ContentTagAnalyzer:
    """Analyzes file content to suggest relevant tags.

    Uses multiple techniques:
    1. Keyword extraction from text content
    2. File metadata analysis (EXIF, document properties)
    3. File type and extension analysis
    4. Directory and filename analysis
    """

    def __init__(
        self,
        min_keyword_length: int = 3,
        max_keywords: int = 20,
        stop_words: set[str] | None = None,
    ):
        """Initialize the content tag analyzer.

        Args:
            min_keyword_length: Minimum length for extracted keywords
            max_keywords: Maximum number of keywords to extract
            stop_words: Set of words to ignore during extraction
        """
        self.min_keyword_length = min_keyword_length
        self.max_keywords = max_keywords

        # Default stop words (common words to filter out)
        self.stop_words = stop_words or {
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
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "what",
            "which",
            "who",
            "when",
            "where",
            "why",
            "how",
            "file",
            "document",
        }

        logger.info("ContentTagAnalyzer initialized")

    def analyze_file(
        self,
        file_path: Path,
        style: str | None = None,
        custom_prompt: str | None = None,
    ) -> list[str]:
        """Analyze a file and return suggested tags.

        Args:
            file_path: Path to the file to analyze
            style: Optional tag style preset (e.g. "sfx", "audio", "code", "descriptive", "hierarchical")
            custom_prompt: Optional custom user prompt or instruction

        Returns:
            List of suggested tags
        """
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return []

        logger.debug(f"Analyzing file: {file_path}")

        tags = set()

        # Extract tags from different sources
        filename_tags = self._extract_from_filename(file_path)
        tags.update(filename_tags)
        tags.update(self._extract_from_extension(file_path))
        tags.update(self._extract_from_directory(file_path))

        # Extract from content if text-based
        if self._is_text_file(file_path):
            content_tags = self._extract_from_content(file_path)
            tags.update(content_tags[:10])  # Limit content tags

        # Extract from metadata
        metadata_tags = self._extract_from_metadata(file_path)
        tags.update(metadata_tags)

        # Style-guided enrichment
        if style:
            style_key = style.lower().strip()
            tags.update(self._extract_style_tags(file_path, style_key, filename_tags))

        # Custom prompt-guided enrichment
        if custom_prompt:
            tags.update(self._extract_prompt_tags(file_path, custom_prompt))

        # Clean and normalize tags
        cleaned_tags = self._clean_tags(list(tags))

        logger.info(f"Extracted {len(cleaned_tags)} tags from {file_path.name}")
        return cleaned_tags[: self.max_keywords]

    def extract_keywords(
        self,
        file_path: Path,
        top_n: int = 10,
        style: str | None = None,
        custom_prompt: str | None = None,
    ) -> list[tuple[str, float]]:
        """Extract keywords with confidence scores using TF-IDF.

        Args:
            file_path: Path to the file
            top_n: Number of top keywords to return
            style: Optional tag style preset
            custom_prompt: Optional custom user prompt

        Returns:
            List of (keyword, score) tuples
        """
        if not file_path.exists():
            return []

        if not self._is_text_file(file_path):
            if not style and not custom_prompt:
                return []
            # For non-text files (e.g. audio SFX or binary assets), extract and score keywords from filename & metadata
            filename_tags = self._extract_from_filename(file_path)
            metadata_tags = self._extract_from_metadata(file_path)
            combined_tags = list(filename_tags + metadata_tags)
            if style:
                combined_tags.extend(
                    self._extract_style_tags(file_path, style.lower().strip(), filename_tags)
                )
            if custom_prompt:
                combined_tags.extend(self._extract_prompt_tags(file_path, custom_prompt))
            cleaned = self._clean_tags(combined_tags)
            preset_kws = STYLE_PRESETS.get(style.lower().strip() if style else "", {}).get(
                "keywords", set()
            )
            scored = []
            for tag in cleaned[:top_n]:
                score = 15.0 if tag in preset_kws else 10.0
                if len(tag) > 6:
                    score *= 1.2
                scored.append((tag, score))
            return sorted(scored, key=lambda x: x[1], reverse=True)[:top_n]

        try:
            content = self._read_text_content(file_path)
            if not content:
                return []

            # Calculate term frequencies
            words = self._tokenize(content)
            word_freq = Counter(words)

            total_words = len(words)
            unique_words = len(set(words))

            preset_kws = (
                STYLE_PRESETS.get(style.lower().strip(), {}).get("keywords", set())
                if style
                else set()
            )
            prompt_terms = (
                set(re.findall(r"\w{3,}", custom_prompt.lower())) if custom_prompt else set()
            )

            scored_keywords = []
            for word, freq in word_freq.most_common(top_n * 2):
                tf = freq / total_words
                idf = 1.0 + (unique_words / (1 + freq))
                score = tf * idf

                if len(word) > 6:
                    score *= 1.2
                if word in preset_kws:
                    score *= 2.0
                if word in prompt_terms:
                    score *= 2.0

                scored_keywords.append((word, score))

            scored_keywords.sort(key=lambda x: x[1], reverse=True)
            return scored_keywords[:top_n]

        except (OSError, UnicodeDecodeError, ValueError) as e:
            logger.error(f"Error extracting keywords from {file_path}: {e}")
            return []

    def _extract_style_tags(
        self, file_path: Path, style_key: str, filename_tags: list[str]
    ) -> list[str]:
        """Extract tags according to the specified style preset."""
        style_tags: list[str] = []
        preset = STYLE_PRESETS.get(style_key)

        if style_key == "hierarchical":
            parts = [p for p in file_path.parts if p not in ("/", "\\")]
            if len(parts) >= 2:
                parent = parts[-2].lower()
                stem = file_path.stem.lower()
                style_tags.append(f"{parent}-{stem}")
            ext = file_path.suffix.lstrip(".").lower()
            if ext:
                style_tags.append(f"type-{ext}")
            return style_tags

        if preset and "keywords" in preset:
            domain_keywords = preset["keywords"]
            fn_tokens = re.split(r"[-_\s.]+", file_path.stem.lower())
            parent_tokens = re.split(r"[-_\s.]+", file_path.parent.name.lower())
            for token in fn_tokens + parent_tokens:
                if token in domain_keywords:
                    style_tags.append(token)

            if style_key in ("sfx", "audio"):
                style_tags.append("sfx" if style_key == "sfx" else "audio")
                for descriptor in (
                    "loop",
                    "stereo",
                    "mono",
                    "oneshot",
                    "foley",
                    "impact",
                    "reverb",
                    "ambience",
                ):
                    if descriptor in file_path.stem.lower():
                        style_tags.append(descriptor)

        elif style_key == "descriptive":
            for tag in filename_tags:
                if len(tag) >= 4:
                    style_tags.append(tag)

        return style_tags

    def _extract_prompt_tags(self, file_path: Path, custom_prompt: str) -> list[str]:
        """Extract tags matching guidance from a user prompt."""
        prompt_tags: list[str] = []
        prompt_lower = custom_prompt.lower()
        candidates = re.split(r"[,;:\s]+", prompt_lower)
        stem_lower = file_path.stem.lower()
        parent_lower = file_path.parent.name.lower()

        prompt_ignore = self.stop_words | {
            "sort",
            "tags",
            "tag",
            "based",
            "files",
            "folder",
            "folders",
            "into",
            "from",
            "different",
            "with",
            "like",
            "using",
            "contents",
            "properties",
            "name",
            "library",
            "whole",
            "mess",
            "please",
            "want",
            "would",
            "look",
            "only",
            "also",
            "each",
        }

        for cand in candidates:
            cand_clean = re.sub(r"[^\w_]", "", cand).strip("_")
            if len(cand_clean) >= 3 and cand_clean not in prompt_ignore:
                if cand_clean in ("genre", "emotion", "category", "mood", "theme"):
                    continue
                if cand_clean in stem_lower or cand_clean in parent_lower:
                    prompt_tags.append(cand_clean)
                else:
                    prompt_tags.append(cand_clean)

        return prompt_tags

    def extract_entities(self, file_path: Path) -> list[str]:
        """Extract named entities from file content.

        This is a simplified version. A full implementation would use
        an NLP model like spaCy or a LLM for better entity recognition.

        Args:
            file_path: Path to the file

        Returns:
            List of identified entities
        """
        if not file_path.exists() or not self._is_text_file(file_path):
            return []

        try:
            content = self._read_text_content(file_path)
            if not content:
                return []

            entities = set()

            # Extract capitalized words (potential proper nouns)
            # Pattern: Words starting with capital letter, possibly multi-word
            pattern = r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b"
            matches = re.findall(pattern, content)

            for match in matches:
                # Filter out common sentence starters
                if match.lower() not in {"the", "this", "that", "these", "those"}:
                    entities.add(match)

            # Extract potential acronyms (2-5 capital letters)
            acronym_pattern = r"\b[A-Z]{2,5}\b"
            acronyms = re.findall(acronym_pattern, content)
            entities.update(acronyms)

            return sorted(entities)[:20]  # Limit to top 20

        except (OSError, UnicodeDecodeError, ValueError) as e:
            logger.error(f"Error extracting entities from {file_path}: {e}")
            return []

    def batch_analyze(self, files: list[Path]) -> dict[Path, list[str]]:
        """Analyze multiple files in batch.

        Args:
            files: List of file paths to analyze

        Returns:
            Dictionary mapping file paths to tag lists
        """
        logger.info(f"Batch analyzing {len(files)} files")
        results = {}

        for file_path in files:
            try:
                tags = self.analyze_file(file_path)
                results[file_path] = tags
            except (OSError, UnicodeDecodeError, ValueError) as e:
                logger.error(f"Error analyzing {file_path}: {e}")
                results[file_path] = []

        return results

    def _extract_from_filename(self, file_path: Path) -> list[str]:
        """Extract tags from filename."""
        filename = file_path.stem

        # Split by common delimiters
        parts = re.split(r"[-_\s.]+", filename.lower())

        # Filter and clean
        tags = [
            part
            for part in parts
            if len(part) >= self.min_keyword_length
            and part not in self.stop_words
            and not part.isdigit()
        ]

        return tags

    def _extract_from_extension(self, file_path: Path) -> list[str]:
        """Extract tags from file extension."""
        ext = file_path.suffix.lower().lstrip(".")

        if not ext:
            return []

        tags = [ext]

        # Add category tags based on extension
        extension_categories = {
            "document": ["pdf", "doc", "docx", "txt", "md", "rtf", "odt"],
            "image": ["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp", "heic"],
            "video": ["mp4", "avi", "mov", "wmv", "flv", "mkv", "webm"],
            "audio": ["mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"],
            "spreadsheet": ["xls", "xlsx", "csv", "ods"],
            "presentation": ["ppt", "pptx", "key", "odp"],
            "archive": ["zip", "rar", "7z", "tar", "gz", "bz2"],
            "code": ["py", "js", "java", "cpp", "c", "rb", "go", "rs", "php"],
        }

        for category, extensions in extension_categories.items():
            if ext in extensions:
                tags.append(category)
                break

        return tags

    def _extract_from_directory(self, file_path: Path) -> list[str]:
        """Extract tags from directory structure."""
        tags = []

        # Get parent directory names (up to 2 levels)
        parts = file_path.parts
        if len(parts) > 1:
            # Last directory
            last_dir = parts[-2] if len(parts) > 1 else ""
            if last_dir and last_dir.lower() not in {"desktop", "downloads", "documents"}:
                # Split directory name
                dir_parts = re.split(r"[-_\s]+", last_dir.lower())
                tags.extend(
                    [
                        p
                        for p in dir_parts
                        if len(p) >= self.min_keyword_length and p not in self.stop_words
                    ]
                )

        return tags

    def _extract_from_content(self, file_path: Path) -> list[str]:
        """Extract tags from file content."""
        try:
            content = self._read_text_content(file_path)
            if not content:
                return []

            # Tokenize and count words
            words = self._tokenize(content)

            # Get most frequent meaningful words
            word_freq = Counter(words)

            # Return top words
            return [word for word, _ in word_freq.most_common(20)]

        except (OSError, UnicodeDecodeError) as e:
            logger.debug(f"Could not extract content tags from {file_path}: {e}")
            return []

    def _extract_from_metadata(self, file_path: Path) -> list[str]:
        """Extract tags from file metadata."""
        tags = []

        try:
            stat = file_path.stat()

            # Add size category
            size_mb = stat.st_size / (1024 * 1024)
            if size_mb < 1:
                tags.append("small")
            elif size_mb < 10:
                tags.append("medium")
            elif size_mb < 100:
                tags.append("large")
            else:
                tags.append("very-large")

            # For images, could extract EXIF data here
            # For documents, could extract author, title, etc.
            # This is simplified - full implementation would use libraries like:
            # - Pillow for image EXIF
            # - python-docx for Word documents
            # - pypdf for PDFs

        except OSError as e:
            logger.debug(f"Could not extract metadata from {file_path}: {e}")

        return tags

    def _is_text_file(self, file_path: Path) -> bool:
        """Check if file is likely a text file."""
        text_extensions = {
            ".txt",
            ".md",
            ".rst",
            ".log",
            ".csv",
            ".json",
            ".xml",
            ".html",
            ".css",
            ".js",
            ".py",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".rb",
            ".go",
            ".rs",
            ".php",
            ".sh",
            ".bash",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
        }

        return file_path.suffix.lower() in text_extensions

    def _read_text_content(self, file_path: Path, max_size_mb: int = 5) -> str:
        """Read text content from file with size limit."""
        try:
            # Check file size
            size_mb = file_path.stat().st_size / (1024 * 1024)
            if size_mb > max_size_mb:
                logger.debug(f"File too large to analyze: {file_path}")
                return ""

            # Try reading with UTF-8, fallback to latin-1
            try:
                return file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return file_path.read_text(encoding="latin-1")

        except OSError as e:
            logger.debug(f"Could not read {file_path}: {e}")
            return ""

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words."""
        # Convert to lowercase and split
        text = text.lower()

        # Remove special characters, keep letters and spaces
        text = re.sub(r"[^a-z\s]", " ", text)

        # Split and filter
        words = text.split()

        # Filter by length and stop words
        words = [
            word
            for word in words
            if len(word) >= self.min_keyword_length and word not in self.stop_words
        ]

        return words

    def _clean_tags(self, tags: list[str]) -> list[str]:
        """Clean and normalize tags."""
        cleaned = []
        seen = set()

        for tag in tags:
            # Normalize
            tag = tag.lower().strip()

            # Remove special characters
            tag = re.sub(r"[^a-z0-9-]", "", tag)

            # Skip if too short or duplicate
            if len(tag) < self.min_keyword_length or tag in seen:
                continue

            cleaned.append(tag)
            seen.add(tag)

        return cleaned
