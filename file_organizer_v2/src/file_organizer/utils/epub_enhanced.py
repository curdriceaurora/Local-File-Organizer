"""Enhanced EPUB file processing with comprehensive metadata extraction.

This module provides advanced EPUB processing capabilities including:
- Chapter-based content extraction (EPUB 2 and EPUB 3)
- Rich metadata extraction (author, series, publisher, language)
- Cover image extraction
- Genre and subject detection
- ISBN and identifier parsing
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re
import io

try:
    import ebooklib
    from ebooklib import epub
    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from loguru import logger


class EPUBProcessingError(Exception):
    """Exception raised when EPUB processing fails."""
    pass


@dataclass
class EPUBChapter:
    """Represents a chapter in an EPUB book.

    Attributes:
        title: Chapter title
        content: Chapter text content (HTML stripped)
        order: Chapter order/position in book
        word_count: Number of words in chapter
    """
    title: str
    content: str
    order: int
    word_count: int


@dataclass
class EPUBMetadata:
    """Comprehensive EPUB metadata.

    Attributes:
        title: Book title
        authors: List of author names
        language: Language code (e.g., 'en', 'fr')
        publisher: Publisher name
        publication_date: Publication date string
        isbn: ISBN identifier (if available)
        identifiers: Dict of all identifiers (ISBN, UUID, etc.)
        subjects: List of subject/genre tags
        description: Book description/summary
        series: Series name (if part of a series)
        series_index: Book number in series
        rights: Copyright/rights information
        contributors: List of contributors (editors, translators)
        has_cover: Whether book has cover image
        cover_path: Path to extracted cover image (if extracted)
        epub_version: EPUB version (2 or 3)
    """
    title: str
    authors: list[str]
    language: Optional[str] = None
    publisher: Optional[str] = None
    publication_date: Optional[str] = None
    isbn: Optional[str] = None
    identifiers: dict[str, str] = None
    subjects: list[str] = None
    description: Optional[str] = None
    series: Optional[str] = None
    series_index: Optional[float] = None
    rights: Optional[str] = None
    contributors: list[str] = None
    has_cover: bool = False
    cover_path: Optional[Path] = None
    epub_version: Optional[str] = None

    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.identifiers is None:
            self.identifiers = {}
        if self.subjects is None:
            self.subjects = []
        if self.contributors is None:
            self.contributors = []


@dataclass
class EPUBContent:
    """Complete EPUB book content and metadata.

    Attributes:
        metadata: Book metadata
        chapters: List of chapters
        total_words: Total word count across all chapters
        total_chapters: Number of chapters
        raw_text: Combined text from all chapters
    """
    metadata: EPUBMetadata
    chapters: list[EPUBChapter]
    total_words: int
    total_chapters: int
    raw_text: str


class EnhancedEPUBReader:
    """Enhanced EPUB reader with comprehensive metadata and content extraction.

    Supports both EPUB 2 and EPUB 3 formats with:
    - Detailed metadata extraction
    - Chapter-by-chapter content parsing
    - Cover image extraction
    - Series detection
    - Genre/subject classification

    Example:
        >>> reader = EnhancedEPUBReader()
        >>> content = reader.read_epub(Path("book.epub"))
        >>> print(f"Title: {content.metadata.title}")
        >>> print(f"Authors: {', '.join(content.metadata.authors)}")
        >>> print(f"Chapters: {content.total_chapters}")
    """

    def __init__(self):
        """Initialize the EPUB reader.

        Raises:
            ImportError: If required libraries are not installed
        """
        if not EBOOKLIB_AVAILABLE:
            raise ImportError(
                "ebooklib is not installed. Install with: pip install ebooklib"
            )
        if not BS4_AVAILABLE:
            raise ImportError(
                "beautifulsoup4 is not installed. Install with: pip install beautifulsoup4 lxml"
            )

    def read_epub(
        self,
        file_path: str | Path,
        extract_cover: bool = False,
        cover_output_dir: Optional[Path] = None,
        max_chapters: Optional[int] = None
    ) -> EPUBContent:
        """Read and parse an EPUB file.

        Args:
            file_path: Path to EPUB file
            extract_cover: Whether to extract cover image
            cover_output_dir: Directory to save cover image (if extract_cover=True)
            max_chapters: Maximum number of chapters to extract (None = all)

        Returns:
            EPUBContent with complete book data

        Raises:
            EPUBProcessingError: If file cannot be read or parsed
            FileNotFoundError: If file does not exist
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"EPUB file not found: {file_path}")

        try:
            book = epub.read_epub(file_path)
            logger.debug(f"Successfully opened EPUB: {file_path.name}")
        except Exception as e:
            raise EPUBProcessingError(f"Failed to read EPUB file {file_path}: {e}") from e

        # Extract metadata
        metadata = self._extract_metadata(book)

        # Extract cover if requested
        if extract_cover:
            cover_path = self._extract_cover(book, file_path, cover_output_dir)
            metadata.cover_path = cover_path

        # Extract chapters
        chapters = self._extract_chapters(book, max_chapters)

        # Calculate totals
        total_words = sum(ch.word_count for ch in chapters)
        raw_text = "\n\n".join(ch.content for ch in chapters)

        logger.info(
            f"Extracted {len(chapters)} chapters, {total_words} words from {file_path.name}"
        )

        return EPUBContent(
            metadata=metadata,
            chapters=chapters,
            total_words=total_words,
            total_chapters=len(chapters),
            raw_text=raw_text
        )

    def _extract_metadata(self, book: epub.EpubBook) -> EPUBMetadata:
        """Extract comprehensive metadata from EPUB.

        Args:
            book: EpubBook instance

        Returns:
            EPUBMetadata with all available metadata
        """
        # Helper to get metadata value
        def get_meta(key: str) -> Optional[str]:
            """Get single metadata value."""
            values = book.get_metadata('DC', key)
            if values and len(values) > 0:
                return str(values[0][0]) if values[0] else None
            return None

        def get_meta_list(key: str) -> list[str]:
            """Get list of metadata values."""
            values = book.get_metadata('DC', key)
            return [str(v[0]) for v in values if v and v[0]] if values else []

        # Extract basic metadata
        title = get_meta('title') or "Unknown Title"
        authors = get_meta_list('creator') or ["Unknown Author"]
        language = get_meta('language')
        publisher = get_meta('publisher')
        publication_date = get_meta('date')
        description = get_meta('description')
        rights = get_meta('rights')

        # Extract subjects/genres
        subjects = get_meta_list('subject')

        # Extract contributors (editors, translators, etc.)
        contributors = get_meta_list('contributor')

        # Extract identifiers
        identifiers = {}
        identifier_list = book.get_metadata('DC', 'identifier')
        if identifier_list:
            for identifier_tuple in identifier_list:
                if identifier_tuple and len(identifier_tuple) >= 2:
                    value = str(identifier_tuple[0])
                    attrs = identifier_tuple[1] if len(identifier_tuple) > 1 else {}

                    # Try to determine identifier type
                    scheme = attrs.get('scheme', '').lower() if isinstance(attrs, dict) else ''

                    if 'isbn' in scheme or 'isbn' in value.lower():
                        identifiers['isbn'] = self._clean_isbn(value)
                    elif 'uuid' in scheme or 'uuid' in value.lower():
                        identifiers['uuid'] = value
                    else:
                        identifiers['identifier'] = value

        # Get ISBN specifically
        isbn = identifiers.get('isbn')

        # Try to detect series information from title or metadata
        series, series_index = self._detect_series(title, book)

        # Check for cover
        has_cover = self._has_cover(book)

        # Detect EPUB version
        epub_version = self._detect_epub_version(book)

        return EPUBMetadata(
            title=title,
            authors=authors,
            language=language,
            publisher=publisher,
            publication_date=publication_date,
            isbn=isbn,
            identifiers=identifiers,
            subjects=subjects,
            description=description,
            series=series,
            series_index=series_index,
            rights=rights,
            contributors=contributors,
            has_cover=has_cover,
            epub_version=epub_version
        )

    def _extract_chapters(
        self,
        book: epub.EpubBook,
        max_chapters: Optional[int] = None
    ) -> list[EPUBChapter]:
        """Extract chapters from EPUB.

        Args:
            book: EpubBook instance
            max_chapters: Maximum chapters to extract (None = all)

        Returns:
            List of EPUBChapter objects
        """
        chapters = []
        chapter_num = 0

        # Get all document items
        for item in book.get_items():
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            # Stop if we've reached max chapters
            if max_chapters and chapter_num >= max_chapters:
                break

            try:
                # Parse HTML content
                content_bytes = item.get_content()
                soup = BeautifulSoup(content_bytes, 'lxml')

                # Extract title from heading tags or filename
                title = self._extract_chapter_title(soup, item)

                # Extract text content
                text = self._extract_text_from_html(soup)

                # Skip if no meaningful content
                if not text or len(text.strip()) < 50:
                    continue

                word_count = len(text.split())

                chapters.append(EPUBChapter(
                    title=title,
                    content=text,
                    order=chapter_num,
                    word_count=word_count
                ))

                chapter_num += 1

            except Exception as e:
                logger.warning(f"Failed to parse chapter {chapter_num}: {e}")
                continue

        return chapters

    def _extract_chapter_title(self, soup: BeautifulSoup, item) -> str:
        """Extract chapter title from HTML or item metadata.

        Args:
            soup: BeautifulSoup HTML parser
            item: EPUB item

        Returns:
            Chapter title
        """
        # Try to find title in heading tags
        for tag in ['h1', 'h2', 'h3', 'title']:
            heading = soup.find(tag)
            if heading and heading.get_text(strip=True):
                return heading.get_text(strip=True)

        # Fall back to filename
        if hasattr(item, 'file_name'):
            name = Path(item.file_name).stem
            # Clean up filename
            name = name.replace('_', ' ').replace('-', ' ')
            return name.title()

        return "Untitled Chapter"

    def _extract_text_from_html(self, soup: BeautifulSoup) -> str:
        """Extract clean text from HTML.

        Args:
            soup: BeautifulSoup HTML parser

        Returns:
            Clean text content
        """
        # Remove script and style elements
        for element in soup(['script', 'style', 'meta', 'link']):
            element.decompose()

        # Get text
        text = soup.get_text(separator=' ', strip=True)

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)

        return text.strip()

    def _detect_series(
        self,
        title: str,
        book: epub.EpubBook
    ) -> tuple[Optional[str], Optional[float]]:
        """Detect if book is part of a series.

        Args:
            title: Book title
            book: EpubBook instance

        Returns:
            Tuple of (series_name, series_index)
        """
        # Check for calibre series metadata
        try:
            calibre_meta = book.get_metadata('', 'calibre:series')
            if calibre_meta and calibre_meta[0]:
                series_name = str(calibre_meta[0][0])

                # Get series index
                series_index_meta = book.get_metadata('', 'calibre:series_index')
                series_index = None
                if series_index_meta and series_index_meta[0]:
                    try:
                        series_index = float(series_index_meta[0][0])
                    except (ValueError, TypeError):
                        pass

                return series_name, series_index
        except (KeyError, AttributeError):
            # Namespace doesn't exist or metadata not available
            pass

        # Try to detect from title patterns
        # Pattern: "Series Name, Book 1" or "Series Name #1" or "Series Name: Book One"
        patterns = [
            r'^(.+?),\s*Book\s+(\d+)',
            r'^(.+?)\s+#(\d+)',
            r'^(.+?):\s*Book\s+(\w+)',
            r'^(.+?)\s+\(Book\s+(\d+)\)',
            r'^(.+?)\s+-\s+Book\s+(\d+)',
        ]

        for pattern in patterns:
            match = re.match(pattern, title, re.IGNORECASE)
            if match:
                series_name = match.group(1).strip()
                try:
                    # Try to convert to number
                    index_str = match.group(2)
                    if index_str.isdigit():
                        series_index = float(index_str)
                    else:
                        # Handle word numbers (One, Two, etc.)
                        series_index = self._word_to_number(index_str)

                    return series_name, series_index
                except (ValueError, IndexError):
                    return series_name, None

        return None, None

    def _word_to_number(self, word: str) -> Optional[float]:
        """Convert word numbers to floats.

        Args:
            word: Word representation of number

        Returns:
            Float value or None
        """
        word_map = {
            'one': 1, 'first': 1,
            'two': 2, 'second': 2,
            'three': 3, 'third': 3,
            'four': 4, 'fourth': 4,
            'five': 5, 'fifth': 5,
            'six': 6, 'sixth': 6,
            'seven': 7, 'seventh': 7,
            'eight': 8, 'eighth': 8,
            'nine': 9, 'ninth': 9,
            'ten': 10, 'tenth': 10,
        }
        return word_map.get(word.lower())

    def _clean_isbn(self, isbn: str) -> str:
        """Clean and format ISBN.

        Args:
            isbn: Raw ISBN string

        Returns:
            Cleaned ISBN (digits only)
        """
        # Remove all non-digit characters except X (for ISBN-10)
        cleaned = re.sub(r'[^\dX]', '', isbn.upper())
        return cleaned

    def _has_cover(self, book: epub.EpubBook) -> bool:
        """Check if book has a cover image.

        Args:
            book: EpubBook instance

        Returns:
            True if cover exists
        """
        try:
            # Try multiple methods to find cover

            # Method 1: Use get_metadata
            cover_meta = book.get_metadata('OPF', 'cover')
            if cover_meta:
                return True

            # Method 2: Look for cover item
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_COVER:
                    return True
                # Check if it's an image with 'cover' in the name
                if item.get_type() == ebooklib.ITEM_IMAGE:
                    if 'cover' in item.get_name().lower():
                        return True

            return False
        except Exception:
            return False

    def _extract_cover(
        self,
        book: epub.EpubBook,
        epub_path: Path,
        output_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """Extract cover image from EPUB.

        Args:
            book: EpubBook instance
            epub_path: Path to original EPUB file
            output_dir: Directory to save cover (default: same as EPUB)

        Returns:
            Path to extracted cover image, or None if not found
        """
        if not PILLOW_AVAILABLE:
            logger.warning("Pillow not available, cannot extract cover image")
            return None

        try:
            # Find cover item
            cover_item = None

            # Method 1: Check metadata
            cover_meta = book.get_metadata('OPF', 'cover')
            if cover_meta and cover_meta[0]:
                cover_id = cover_meta[0][0]
                cover_item = book.get_item_with_id(cover_id)

            # Method 2: Look through items
            if not cover_item:
                for item in book.get_items():
                    if item.get_type() == ebooklib.ITEM_COVER:
                        cover_item = item
                        break
                    # Check images with 'cover' in name
                    if item.get_type() == ebooklib.ITEM_IMAGE:
                        if 'cover' in item.get_name().lower():
                            cover_item = item
                            break

            if not cover_item:
                logger.debug("No cover image found in EPUB")
                return None

            # Get cover data
            cover_data = cover_item.get_content()

            # Determine output path
            if output_dir is None:
                output_dir = epub_path.parent
            else:
                output_dir = Path(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)

            # Determine file extension from content
            img = Image.open(io.BytesIO(cover_data))
            ext = img.format.lower() if img.format else 'jpg'

            output_path = output_dir / f"{epub_path.stem}_cover.{ext}"

            # Save cover
            with open(output_path, 'wb') as f:
                f.write(cover_data)

            logger.info(f"Extracted cover to: {output_path}")
            return output_path

        except Exception as e:
            logger.warning(f"Failed to extract cover: {e}")
            return None

    def _detect_epub_version(self, book: epub.EpubBook) -> Optional[str]:
        """Detect EPUB version.

        Args:
            book: EpubBook instance

        Returns:
            Version string ('2.0' or '3.0') or None
        """
        try:
            # Check OPF version attribute
            version = book.version
            if version:
                return str(version)

            # Try to detect from content
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_NAVIGATION:
                    return '3.0'  # EPUB 3 uses nav documents

            return '2.0'  # Default to EPUB 2
        except Exception:
            return None


def read_epub_simple(
    file_path: str | Path,
    max_chars: int = 10000
) -> str:
    """Simple EPUB text extraction (backward compatible).

    This is a simplified version for quick text extraction,
    compatible with the existing file_readers.py interface.

    Args:
        file_path: Path to EPUB file
        max_chars: Maximum characters to extract

    Returns:
        Extracted text content

    Raises:
        EPUBProcessingError: If file cannot be read
    """
    reader = EnhancedEPUBReader()
    content = reader.read_epub(file_path, max_chapters=10)

    # Return truncated raw text
    return content.raw_text[:max_chars]


def get_epub_metadata(file_path: str | Path) -> EPUBMetadata:
    """Extract only metadata from EPUB (no chapter parsing).

    Args:
        file_path: Path to EPUB file

    Returns:
        EPUBMetadata object

    Raises:
        EPUBProcessingError: If file cannot be read
    """
    if not EBOOKLIB_AVAILABLE:
        raise ImportError("ebooklib is not installed. Install with: pip install ebooklib")

    file_path = Path(file_path)

    try:
        book = epub.read_epub(file_path)
        reader = EnhancedEPUBReader()
        return reader._extract_metadata(book)
    except Exception as e:
        raise EPUBProcessingError(f"Failed to read EPUB metadata: {e}") from e
