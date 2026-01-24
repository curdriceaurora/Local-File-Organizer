"""Tests for enhanced EPUB processing capabilities.

This module tests the EnhancedEPUBReader class which provides:
- Comprehensive metadata extraction
- Chapter-based content parsing
- Cover image extraction
- Series detection
- EPUB 2/3 support
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import io

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

try:
    import ebooklib
    from ebooklib import epub
    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False

from file_organizer.utils.epub_enhanced import (
    EnhancedEPUBReader,
    EPUBMetadata,
    EPUBChapter,
    EPUBContent,
    EPUBProcessingError,
    read_epub_simple,
    get_epub_metadata
)


# Skip all tests if ebooklib not available
pytestmark = pytest.mark.skipif(
    not EBOOKLIB_AVAILABLE,
    reason="ebooklib not installed"
)


@pytest.fixture
def mock_epub_book():
    """Create a mock EPUB book with metadata."""
    book = Mock(spec=epub.EpubBook)
    book.version = '3.0'

    # Set up metadata
    book.get_metadata = Mock(side_effect=lambda ns, key: {
        ('DC', 'title'): [('Test Book Title', {})],
        ('DC', 'creator'): [('John Doe', {}), ('Jane Smith', {})],
        ('DC', 'language'): [('en', {})],
        ('DC', 'publisher'): [('Test Publisher', {})],
        ('DC', 'date'): [('2024-01-15', {})],
        ('DC', 'description'): [('A test book for testing', {})],
        ('DC', 'subject'): [('Fiction', {}), ('Science Fiction', {})],
        ('DC', 'identifier'): [('978-1234567890', {'scheme': 'ISBN'})],
        ('DC', 'contributor'): [('Editor Name', {})],
        ('DC', 'rights'): [('Copyright 2024', {})],
        ('', 'calibre:series'): [('Test Series', {})],
        ('', 'calibre:series_index'): [('1.0', {})],
    }.get((ns, key), []))

    # Set up items
    book.get_items = Mock(return_value=[])

    return book


@pytest.fixture
def mock_epub_chapter():
    """Create a mock EPUB chapter item."""
    item = Mock()
    item.get_type = Mock(return_value=ebooklib.ITEM_DOCUMENT)
    item.get_name = Mock(return_value='chapter1.xhtml')
    item.file_name = 'chapter1.xhtml'

    html_content = b'''
    <html>
        <head><title>Chapter 1</title></head>
        <body>
            <h1>Chapter One: The Beginning</h1>
            <p>This is the first paragraph of the chapter.</p>
            <p>This is the second paragraph with more content.</p>
        </body>
    </html>
    '''
    item.get_content = Mock(return_value=html_content)

    return item


class TestEPUBMetadata:
    """Tests for EPUBMetadata dataclass."""

    def test_metadata_creation(self):
        """Test creating metadata with required fields."""
        metadata = EPUBMetadata(
            title="Test Book",
            authors=["Author One", "Author Two"]
        )

        assert metadata.title == "Test Book"
        assert len(metadata.authors) == 2
        assert metadata.identifiers == {}
        assert metadata.subjects == []
        assert metadata.contributors == []

    def test_metadata_with_series(self):
        """Test metadata with series information."""
        metadata = EPUBMetadata(
            title="Test Book",
            authors=["Author"],
            series="Test Series",
            series_index=2.5
        )

        assert metadata.series == "Test Series"
        assert metadata.series_index == 2.5

    def test_metadata_with_identifiers(self):
        """Test metadata with various identifiers."""
        metadata = EPUBMetadata(
            title="Test Book",
            authors=["Author"],
            isbn="978-1234567890",
            identifiers={"isbn": "978-1234567890", "uuid": "test-uuid"}
        )

        assert metadata.isbn == "978-1234567890"
        assert "uuid" in metadata.identifiers


class TestEPUBChapter:
    """Tests for EPUBChapter dataclass."""

    def test_chapter_creation(self):
        """Test creating a chapter."""
        chapter = EPUBChapter(
            title="Chapter One",
            content="This is chapter content.",
            order=0,
            word_count=4
        )

        assert chapter.title == "Chapter One"
        assert chapter.order == 0
        assert chapter.word_count == 4


class TestEnhancedEPUBReader:
    """Tests for EnhancedEPUBReader class."""

    def test_reader_initialization(self):
        """Test that reader initializes correctly."""
        reader = EnhancedEPUBReader()
        assert reader is not None

    def test_reader_requires_ebooklib(self):
        """Test that ImportError is raised if ebooklib not available."""
        with patch('file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE', False):
            with pytest.raises(ImportError, match="ebooklib"):
                EnhancedEPUBReader()

    def test_reader_requires_bs4(self):
        """Test that ImportError is raised if BeautifulSoup not available."""
        with patch('file_organizer.utils.epub_enhanced.BS4_AVAILABLE', False):
            with pytest.raises(ImportError, match="beautifulsoup4"):
                EnhancedEPUBReader()

    @patch('file_organizer.utils.epub_enhanced.epub.read_epub')
    def test_read_epub_nonexistent_file(self, mock_read):
        """Test reading non-existent file raises FileNotFoundError."""
        reader = EnhancedEPUBReader()

        with pytest.raises(FileNotFoundError):
            reader.read_epub(Path("/nonexistent/file.epub"))

    @patch('file_organizer.utils.epub_enhanced.epub.read_epub')
    def test_extract_metadata(self, mock_read, mock_epub_book, tmp_path):
        """Test metadata extraction from EPUB."""
        # Create a dummy file
        test_file = tmp_path / "test.epub"
        test_file.touch()

        mock_read.return_value = mock_epub_book

        reader = EnhancedEPUBReader()
        metadata = reader._extract_metadata(mock_epub_book)

        assert metadata.title == "Test Book Title"
        assert "John Doe" in metadata.authors
        assert "Jane Smith" in metadata.authors
        assert metadata.language == "en"
        assert metadata.publisher == "Test Publisher"
        assert metadata.isbn == "9781234567890"  # Cleaned
        assert "Fiction" in metadata.subjects
        assert metadata.series == "Test Series"
        assert metadata.series_index == 1.0

    def test_clean_isbn(self):
        """Test ISBN cleaning."""
        reader = EnhancedEPUBReader()

        # Test with hyphens
        assert reader._clean_isbn("978-1-234-56789-0") == "9781234567890"

        # Test with spaces
        assert reader._clean_isbn("978 1 234 56789 0") == "9781234567890"

        # Test with ISBN-10 ending in X
        assert reader._clean_isbn("123-456-789-X") == "123456789X"

    def test_detect_series_from_title(self):
        """Test series detection from title patterns."""
        reader = EnhancedEPUBReader()
        mock_book = Mock()
        mock_book.get_metadata = Mock(return_value=[])

        # Test pattern: "Series Name, Book 1"
        series, index = reader._detect_series("Test Series, Book 1", mock_book)
        assert series == "Test Series"
        assert index == 1.0

        # Test pattern: "Series Name #2"
        series, index = reader._detect_series("Test Series #2", mock_book)
        assert series == "Test Series"
        assert index == 2.0

        # Test pattern: "Series Name: Book Three"
        series, index = reader._detect_series("Test Series: Book Three", mock_book)
        assert series == "Test Series"
        assert index == 3.0

        # Test no series
        series, index = reader._detect_series("Standalone Book", mock_book)
        assert series is None
        assert index is None

    def test_word_to_number(self):
        """Test converting word numbers to floats."""
        reader = EnhancedEPUBReader()

        assert reader._word_to_number("one") == 1
        assert reader._word_to_number("first") == 1
        assert reader._word_to_number("five") == 5
        assert reader._word_to_number("tenth") == 10
        assert reader._word_to_number("eleventh") is None  # Not in map

    @patch('file_organizer.utils.epub_enhanced.BeautifulSoup')
    def test_extract_chapter_title(self, mock_bs):
        """Test extracting chapter title from HTML."""
        reader = EnhancedEPUBReader()

        # Mock soup with h1 heading
        mock_soup = Mock()
        mock_h1 = Mock()
        mock_h1.get_text = Mock(return_value="Chapter Title")
        mock_soup.find = Mock(return_value=mock_h1)

        mock_item = Mock()
        mock_item.file_name = "chapter1.xhtml"

        title = reader._extract_chapter_title(mock_soup, mock_item)
        assert title == "Chapter Title"

    @patch('file_organizer.utils.epub_enhanced.BeautifulSoup')
    def test_extract_chapter_title_from_filename(self, mock_bs):
        """Test extracting chapter title from filename."""
        reader = EnhancedEPUBReader()

        # Mock soup with no heading
        mock_soup = Mock()
        mock_soup.find = Mock(return_value=None)

        mock_item = Mock()
        mock_item.file_name = "chapter_one.xhtml"

        title = reader._extract_chapter_title(mock_soup, mock_item)
        assert title == "Chapter One"

    @patch('file_organizer.utils.epub_enhanced.BeautifulSoup')
    def test_extract_text_from_html(self, mock_bs):
        """Test extracting clean text from HTML."""
        reader = EnhancedEPUBReader()

        # Create real BeautifulSoup
        from bs4 import BeautifulSoup

        html = '''
        <html>
            <head><script>var x = 1;</script></head>
            <body>
                <h1>Title</h1>
                <p>Paragraph one.</p>
                <p>Paragraph two.</p>
            </body>
        </html>
        '''

        soup = BeautifulSoup(html, 'lxml')
        text = reader._extract_text_from_html(soup)

        assert "Title" in text
        assert "Paragraph one" in text
        assert "Paragraph two" in text
        assert "var x = 1" not in text  # Script removed

    @patch('file_organizer.utils.epub_enhanced.epub.read_epub')
    def test_extract_chapters(self, mock_read, mock_epub_chapter, tmp_path):
        """Test extracting chapters from EPUB."""
        mock_book = Mock()
        mock_book.get_items = Mock(return_value=[mock_epub_chapter])

        reader = EnhancedEPUBReader()
        chapters = reader._extract_chapters(mock_book)

        assert len(chapters) == 1
        assert chapters[0].title == "Chapter One: The Beginning"
        assert "first paragraph" in chapters[0].content
        assert chapters[0].word_count > 0

    @patch('file_organizer.utils.epub_enhanced.epub.read_epub')
    def test_extract_chapters_with_max_limit(self, mock_read, mock_epub_chapter):
        """Test extracting limited number of chapters."""
        # Create multiple chapter mocks
        chapters = [mock_epub_chapter for _ in range(5)]
        mock_book = Mock()
        mock_book.get_items = Mock(return_value=chapters)

        reader = EnhancedEPUBReader()
        extracted = reader._extract_chapters(mock_book, max_chapters=2)

        assert len(extracted) == 2

    def test_has_cover(self):
        """Test detecting if EPUB has cover."""
        reader = EnhancedEPUBReader()

        # Mock book with cover metadata
        mock_book = Mock()
        mock_book.get_metadata = Mock(return_value=[('cover-id', {})])
        assert reader._has_cover(mock_book) is True

        # Mock book without cover
        mock_book.get_metadata = Mock(return_value=[])
        mock_book.get_items = Mock(return_value=[])
        assert reader._has_cover(mock_book) is False

    @pytest.mark.skipif(not PILLOW_AVAILABLE, reason="Pillow not installed")
    @patch('file_organizer.utils.epub_enhanced.epub.read_epub')
    def test_extract_cover(self, mock_read, tmp_path):
        """Test extracting cover image."""
        reader = EnhancedEPUBReader()

        # Create mock cover item
        mock_cover = Mock()
        mock_cover.get_type = Mock(return_value=ebooklib.ITEM_COVER)

        # Create a minimal PNG image
        img = Image.new('RGB', (100, 150), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        mock_cover.get_content = Mock(return_value=img_bytes.read())

        mock_book = Mock()
        mock_book.get_metadata = Mock(return_value=[])
        mock_book.get_items = Mock(return_value=[mock_cover])
        mock_book.get_item_with_id = Mock(return_value=None)

        epub_path = tmp_path / "test.epub"
        epub_path.touch()

        cover_path = reader._extract_cover(mock_book, epub_path, tmp_path)

        assert cover_path is not None
        assert cover_path.exists()
        assert cover_path.suffix == '.png'

    def test_detect_epub_version(self):
        """Test detecting EPUB version."""
        reader = EnhancedEPUBReader()

        # Mock EPUB 3
        mock_book = Mock()
        mock_book.version = '3.0'
        assert reader._detect_epub_version(mock_book) == '3.0'

        # Mock EPUB 2
        mock_book.version = '2.0'
        assert reader._detect_epub_version(mock_book) == '2.0'


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    @patch('file_organizer.utils.epub_enhanced.EnhancedEPUBReader')
    def test_read_epub_simple(self, mock_reader_class):
        """Test simple EPUB reading function."""
        # Setup mock
        mock_reader = Mock()
        mock_content = Mock()
        mock_content.raw_text = "This is the book content." * 100

        mock_reader.read_epub = Mock(return_value=mock_content)
        mock_reader_class.return_value = mock_reader

        # Call function
        text = read_epub_simple(Path("test.epub"), max_chars=100)

        # Verify
        assert len(text) <= 100
        assert isinstance(text, str)

    @patch('file_organizer.utils.epub_enhanced.epub.read_epub')
    def test_get_epub_metadata(self, mock_read, mock_epub_book, tmp_path):
        """Test getting only metadata without chapter parsing."""
        test_file = tmp_path / "test.epub"
        test_file.touch()

        mock_read.return_value = mock_epub_book

        metadata = get_epub_metadata(test_file)

        assert isinstance(metadata, EPUBMetadata)
        assert metadata.title == "Test Book Title"
        assert len(metadata.authors) == 2


class TestIntegration:
    """Integration tests with real EPUB creation."""

    @pytest.mark.integration
    def test_create_and_read_epub(self, tmp_path):
        """Test creating a minimal EPUB and reading it."""
        # Create a minimal EPUB
        book = epub.EpubBook()
        book.set_title('Integration Test Book')
        book.add_author('Test Author')
        book.set_language('en')

        # Add a chapter with substantial content
        chapter = epub.EpubHtml(
            title='Chapter 1',
            file_name='chap_01.xhtml',
            lang='en'
        )
        chapter.content = '''
        <html xmlns="http://www.w3.org/1999/xhtml">
            <head><title>Chapter 1</title></head>
            <body>
                <h1>Chapter One: The Beginning</h1>
                <p>This is the first chapter content with enough text to pass minimum length check.</p>
                <p>Here is more content to make sure the chapter has enough words to be considered valid.</p>
                <p>And even more content to ensure we exceed the 50 character minimum threshold.</p>
            </body>
        </html>
        '''
        book.add_item(chapter)

        # Define TOC and spine
        book.toc = (chapter,)
        book.spine = ['nav', chapter]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Write EPUB
        epub_path = tmp_path / "test.epub"
        epub.write_epub(epub_path, book)

        # Read with enhanced reader
        reader = EnhancedEPUBReader()
        content = reader.read_epub(epub_path)

        # Verify
        assert content.metadata.title == 'Integration Test Book'
        assert 'Test Author' in content.metadata.authors
        assert len(content.chapters) >= 1, f"Expected at least 1 chapter, got {len(content.chapters)}"
        if len(content.chapters) > 0:
            assert 'first chapter' in content.raw_text.lower()
