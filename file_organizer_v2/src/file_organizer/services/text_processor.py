"""Text file processing service."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from file_organizer.models import TextModel
from file_organizer.models.base import ModelConfig
from file_organizer.utils.file_readers import read_file, FileReadError
from file_organizer.utils.text_processing import (
    clean_text,
    sanitize_filename,
    truncate_text,
    ensure_nltk_data,
)
from loguru import logger


@dataclass
class ProcessedFile:
    """Result of file processing."""

    file_path: Path
    description: str
    folder_name: str
    filename: str
    original_content: Optional[str] = None
    processing_time: float = 0.0
    error: Optional[str] = None


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
        text_model: Optional[TextModel] = None,
        config: Optional[ModelConfig] = None,
    ):
        """Initialize text processor.

        Args:
            text_model: Pre-initialized text model (optional)
            config: Model configuration (used if text_model not provided)
        """
        if text_model is not None:
            self.text_model = text_model
            self._owns_model = False
        else:
            config = config or TextModel.get_default_config()
            self.text_model = TextModel(config)
            self._owns_model = True

        # Ensure NLTK data is available
        ensure_nltk_data()

        logger.info("TextProcessor initialized")

    def initialize(self) -> None:
        """Initialize the text model if not already initialized."""
        if not self.text_model.is_initialized:
            self.text_model.initialize()
            logger.info("Text model initialized")

    def process_file(
        self,
        file_path: Union[str, Path],
        generate_description: bool = True,
        generate_folder: bool = True,
        generate_filename: bool = True,
    ) -> ProcessedFile:
        """Process a single text file.

        Args:
            file_path: Path to file
            generate_description: Whether to generate description
            generate_folder: Whether to generate folder name
            generate_filename: Whether to generate filename

        Returns:
            ProcessedFile with metadata
        """
        import time

        file_path = Path(file_path)
        start_time = time.time()

        try:
            # Read file content
            logger.debug(f"Reading file: {file_path.name}")
            content = read_file(file_path)

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
                description = self._generate_description(content)
                logger.debug(f"Generated description ({len(description)} chars)")

            # Generate folder name
            folder_name = ""
            if generate_folder:
                folder_name = self._generate_folder_name(description or content)
                logger.debug(f"Generated folder name: {folder_name}")

            # Generate filename
            filename = ""
            if generate_filename:
                filename = self._generate_filename(description or content)
                logger.debug(f"Generated filename: {filename}")

            processing_time = time.time() - start_time

            return ProcessedFile(
                file_path=file_path,
                description=description,
                folder_name=folder_name,
                filename=filename,
                original_content=content[:500],  # Keep first 500 chars for reference
                processing_time=processing_time,
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
        except Exception as e:
            logger.exception(f"Failed to process {file_path.name}: {e}")
            return ProcessedFile(
                file_path=file_path,
                description="",
                folder_name="errors",
                filename=file_path.stem,
                error=str(e),
            )

    def _clean_ai_generated_name(self, name: str, max_words: int = 3) -> str:
        """Clean AI-generated folder/file names with lighter filtering.

        This uses minimal filtering since AI output is already clean.

        Args:
            name: AI-generated name
            max_words: Maximum number of words

        Returns:
            Cleaned name
        """
        import re

        # Convert underscores and hyphens to spaces
        name = name.replace('_', ' ').replace('-', ' ')

        # Remove special characters and numbers (keep letters and spaces)
        name = re.sub(r'[^a-z\s]', '', name.lower())

        # Split into words
        words = name.split()

        # Only filter out truly problematic words (very minimal list)
        bad_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
                     'to', 'for', 'of', 'is', 'are', 'was', 'were', 'be',
                     'document', 'file', 'text', 'untitled', 'unknown'}

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
        return '_'.join(filtered) if filtered else ''

    def _generate_description(self, content: str) -> str:
        """Generate a summary/description of the content.

        Args:
            content: File content

        Returns:
            Summary text
        """
        prompt = f"""Summarize the following text in 100-150 words. Focus on main ideas and key details.

TEXT:
{content}

SUMMARY:"""

        try:
            response = self.text_model.generate(prompt, temperature=0.5, max_tokens=200)
            summary = response.strip()

            # Remove any "Summary:" prefix the AI might add
            for prefix in ['summary:', 'here is the summary:', 'the summary is:']:
                if summary.lower().startswith(prefix):
                    summary = summary[len(prefix):].strip()

            return summary
        except Exception as e:
            logger.error(f"Failed to generate description: {e}")
            return f"Content about {content[:100]}..."

    def _generate_folder_name(self, text: str) -> str:
        """Generate a folder name from text.

        Args:
            text: Description or content

        Returns:
            Folder name (max 2 words)
        """
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

TEXT:
{text[:1000]}

CATEGORY:"""

        try:
            response = self.text_model.generate(prompt, temperature=0.3, max_tokens=30)

            # Debug: Log raw AI response
            logger.debug(f"AI folder response (raw): '{response}'")

            # Clean the response
            folder_name = response.strip().lower()

            # Remove common prefixes and quotes
            for prefix in ['category:', 'folder:', 'the category is', 'the folder is']:
                folder_name = folder_name.replace(prefix, '').strip()
            folder_name = folder_name.strip('"\'')

            # Remove newlines and extra spaces
            folder_name = ' '.join(folder_name.split())

            logger.debug(f"AI folder response (cleaned): '{folder_name}'")

            # Use lighter cleaning for AI-generated names
            folder_name = self._clean_ai_generated_name(folder_name, max_words=2)

            logger.debug(f"AI folder response (after filter): '{folder_name}'")

            if not folder_name or len(folder_name) < 3:
                # Fallback to keyword extraction
                logger.warning(f"Folder name empty or too short ('{folder_name}'), using fallback")
                folder_name = clean_text(text, max_words=2)
                logger.debug(f"Fallback folder name: '{folder_name}'")

            # Skip sanitize_filename since we already cleaned it
            # Just do final safety check
            import re
            folder_name = re.sub(r'[^\w_]', '_', folder_name)
            folder_name = re.sub(r'_+', '_', folder_name).strip('_')
            result = folder_name[:50] if folder_name else 'documents'
            logger.info(f"Final folder name: '{result}'")
            return result

        except Exception as e:
            logger.error(f"Failed to generate folder name: {e}")
            return 'documents'

    def _generate_filename(self, text: str) -> str:
        """Generate a filename from text.

        Args:
            text: Description or content

        Returns:
            Filename (max 3 words, no extension)
        """
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

TEXT:
{text[:1000]}

FILENAME:"""

        try:
            response = self.text_model.generate(prompt, temperature=0.3, max_tokens=30)

            # Debug: Log raw AI response
            logger.debug(f"AI filename response (raw): '{response}'")

            # Clean the response
            filename = response.strip().lower()

            # Remove common prefixes and quotes
            for prefix in ['filename:', 'file:', 'name:', 'the filename is', 'the name is']:
                filename = filename.replace(prefix, '').strip()
            filename = filename.strip('"\'')

            # Remove file extensions if AI added them
            import re
            filename = re.sub(r'\.(txt|pdf|docx|md|jpg|png)$', '', filename)

            # Remove newlines and extra spaces
            filename = ' '.join(filename.split())

            logger.debug(f"AI filename response (cleaned): '{filename}'")

            # Use lighter cleaning for AI-generated names
            filename = self._clean_ai_generated_name(filename, max_words=3)

            logger.debug(f"AI filename response (after filter): '{filename}'")

            if not filename or len(filename) < 3:
                # Fallback to keyword extraction
                logger.warning(f"Filename empty or too short ('{filename}'), using fallback")
                filename = clean_text(text, max_words=3)
                logger.debug(f"Fallback filename: '{filename}'")

            # Skip sanitize_filename since we already cleaned it
            # Just do final safety check
            import re
            filename = re.sub(r'[^\w_]', '_', filename)
            filename = re.sub(r'_+', '_', filename).strip('_')
            result = filename[:50] if filename else 'document'
            logger.info(f"Final filename: '{result}'")
            return result

        except Exception as e:
            logger.error(f"Failed to generate filename: {e}")
            return 'document'

    def cleanup(self) -> None:
        """Cleanup resources."""
        if self._owns_model:
            self.text_model.cleanup()
            logger.info("Text model cleaned up")

    def __enter__(self) -> "TextProcessor":
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.cleanup()
