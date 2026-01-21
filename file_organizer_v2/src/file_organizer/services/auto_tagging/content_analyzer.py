"""
Content Tag Analyzer

Analyzes file content to extract relevant tags using multiple techniques:
- Keyword extraction (TF-IDF)
- Topic modeling (LDA)
- Entity recognition
- File metadata analysis
"""

import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from collections import Counter
import re
import json

logger = logging.getLogger(__name__)


class ContentTagAnalyzer:
    """
    Analyzes file content to suggest relevant tags.

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
        stop_words: Optional[Set[str]] = None
    ):
        """
        Initialize the content tag analyzer.

        Args:
            min_keyword_length: Minimum length for extracted keywords
            max_keywords: Maximum number of keywords to extract
            stop_words: Set of words to ignore during extraction
        """
        self.min_keyword_length = min_keyword_length
        self.max_keywords = max_keywords

        # Default stop words (common words to filter out)
        self.stop_words = stop_words or {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this',
            'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
            'what', 'which', 'who', 'when', 'where', 'why', 'how', 'file', 'document'
        }

        logger.info("ContentTagAnalyzer initialized")

    def analyze_file(self, file_path: Path) -> List[str]:
        """
        Analyze a file and return suggested tags.

        Args:
            file_path: Path to the file to analyze

        Returns:
            List of suggested tags
        """
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return []

        logger.debug(f"Analyzing file: {file_path}")

        tags = set()

        # Extract tags from different sources
        tags.update(self._extract_from_filename(file_path))
        tags.update(self._extract_from_extension(file_path))
        tags.update(self._extract_from_directory(file_path))

        # Extract from content if text-based
        if self._is_text_file(file_path):
            content_tags = self._extract_from_content(file_path)
            tags.update(content_tags[:10])  # Limit content tags

        # Extract from metadata
        metadata_tags = self._extract_from_metadata(file_path)
        tags.update(metadata_tags)

        # Clean and normalize tags
        cleaned_tags = self._clean_tags(list(tags))

        logger.info(f"Extracted {len(cleaned_tags)} tags from {file_path.name}")
        return cleaned_tags[:self.max_keywords]

    def extract_keywords(
        self, file_path: Path, top_n: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Extract keywords with confidence scores using TF-IDF.

        Args:
            file_path: Path to the file
            top_n: Number of top keywords to return

        Returns:
            List of (keyword, score) tuples
        """
        if not file_path.exists() or not self._is_text_file(file_path):
            return []

        try:
            content = self._read_text_content(file_path)
            if not content:
                return []

            # Calculate term frequencies
            words = self._tokenize(content)
            word_freq = Counter(words)

            # Simple TF-IDF-like scoring
            # In a full implementation, this would use scikit-learn or similar
            total_words = len(words)
            unique_words = len(set(words))

            scored_keywords = []
            for word, freq in word_freq.most_common(top_n * 2):
                # Score based on frequency and word characteristics
                tf = freq / total_words
                idf = 1.0 + (unique_words / (1 + freq))  # Simplified IDF
                score = tf * idf

                # Boost score for longer words (usually more meaningful)
                if len(word) > 6:
                    score *= 1.2

                scored_keywords.append((word, score))

            # Sort by score and return top N
            scored_keywords.sort(key=lambda x: x[1], reverse=True)
            return scored_keywords[:top_n]

        except Exception as e:
            logger.error(f"Error extracting keywords from {file_path}: {e}")
            return []

    def extract_entities(self, file_path: Path) -> List[str]:
        """
        Extract named entities from file content.

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
            pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
            matches = re.findall(pattern, content)

            for match in matches:
                # Filter out common sentence starters
                if match.lower() not in {'the', 'this', 'that', 'these', 'those'}:
                    entities.add(match)

            # Extract potential acronyms (2-5 capital letters)
            acronym_pattern = r'\b[A-Z]{2,5}\b'
            acronyms = re.findall(acronym_pattern, content)
            entities.update(acronyms)

            return sorted(list(entities))[:20]  # Limit to top 20

        except Exception as e:
            logger.error(f"Error extracting entities from {file_path}: {e}")
            return []

    def batch_analyze(self, files: List[Path]) -> Dict[Path, List[str]]:
        """
        Analyze multiple files in batch.

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
            except Exception as e:
                logger.error(f"Error analyzing {file_path}: {e}")
                results[file_path] = []

        return results

    def _extract_from_filename(self, file_path: Path) -> List[str]:
        """Extract tags from filename."""
        filename = file_path.stem

        # Split by common delimiters
        parts = re.split(r'[-_\s.]+', filename.lower())

        # Filter and clean
        tags = [
            part for part in parts
            if len(part) >= self.min_keyword_length
            and part not in self.stop_words
            and not part.isdigit()
        ]

        return tags

    def _extract_from_extension(self, file_path: Path) -> List[str]:
        """Extract tags from file extension."""
        ext = file_path.suffix.lower().lstrip('.')

        if not ext:
            return []

        tags = [ext]

        # Add category tags based on extension
        extension_categories = {
            'document': ['pdf', 'doc', 'docx', 'txt', 'md', 'rtf', 'odt'],
            'image': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'heic'],
            'video': ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm'],
            'audio': ['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a', 'wma'],
            'spreadsheet': ['xls', 'xlsx', 'csv', 'ods'],
            'presentation': ['ppt', 'pptx', 'key', 'odp'],
            'archive': ['zip', 'rar', '7z', 'tar', 'gz', 'bz2'],
            'code': ['py', 'js', 'java', 'cpp', 'c', 'rb', 'go', 'rs', 'php'],
        }

        for category, extensions in extension_categories.items():
            if ext in extensions:
                tags.append(category)
                break

        return tags

    def _extract_from_directory(self, file_path: Path) -> List[str]:
        """Extract tags from directory structure."""
        tags = []

        # Get parent directory names (up to 2 levels)
        parts = file_path.parts
        if len(parts) > 1:
            # Last directory
            last_dir = parts[-2] if len(parts) > 1 else ''
            if last_dir and last_dir.lower() not in {'desktop', 'downloads', 'documents'}:
                # Split directory name
                dir_parts = re.split(r'[-_\s]+', last_dir.lower())
                tags.extend([
                    p for p in dir_parts
                    if len(p) >= self.min_keyword_length and p not in self.stop_words
                ])

        return tags

    def _extract_from_content(self, file_path: Path) -> List[str]:
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

        except Exception as e:
            logger.debug(f"Could not extract content tags from {file_path}: {e}")
            return []

    def _extract_from_metadata(self, file_path: Path) -> List[str]:
        """Extract tags from file metadata."""
        tags = []

        try:
            stat = file_path.stat()

            # Add size category
            size_mb = stat.st_size / (1024 * 1024)
            if size_mb < 1:
                tags.append('small')
            elif size_mb < 10:
                tags.append('medium')
            elif size_mb < 100:
                tags.append('large')
            else:
                tags.append('very-large')

            # For images, could extract EXIF data here
            # For documents, could extract author, title, etc.
            # This is simplified - full implementation would use libraries like:
            # - Pillow for image EXIF
            # - python-docx for Word documents
            # - PyPDF2 for PDFs

        except Exception as e:
            logger.debug(f"Could not extract metadata from {file_path}: {e}")

        return tags

    def _is_text_file(self, file_path: Path) -> bool:
        """Check if file is likely a text file."""
        text_extensions = {
            '.txt', '.md', '.rst', '.log', '.csv', '.json', '.xml', '.html',
            '.css', '.js', '.py', '.java', '.cpp', '.c', '.h', '.rb', '.go',
            '.rs', '.php', '.sh', '.bash', '.yaml', '.yml', '.toml', '.ini'
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
                return file_path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                return file_path.read_text(encoding='latin-1')

        except Exception as e:
            logger.debug(f"Could not read {file_path}: {e}")
            return ""

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into words."""
        # Convert to lowercase and split
        text = text.lower()

        # Remove special characters, keep letters and spaces
        text = re.sub(r'[^a-z\s]', ' ', text)

        # Split and filter
        words = text.split()

        # Filter by length and stop words
        words = [
            word for word in words
            if len(word) >= self.min_keyword_length
            and word not in self.stop_words
        ]

        return words

    def _clean_tags(self, tags: List[str]) -> List[str]:
        """Clean and normalize tags."""
        cleaned = []
        seen = set()

        for tag in tags:
            # Normalize
            tag = tag.lower().strip()

            # Remove special characters
            tag = re.sub(r'[^a-z0-9-]', '', tag)

            # Skip if too short or duplicate
            if len(tag) < self.min_keyword_length or tag in seen:
                continue

            cleaned.append(tag)
            seen.add(tag)

        return cleaned
