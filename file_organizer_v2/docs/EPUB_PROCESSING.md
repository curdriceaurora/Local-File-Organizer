# Enhanced EPUB Processing

The enhanced EPUB processing module provides comprehensive capabilities for reading and analyzing EPUB ebook files with support for both EPUB 2 and EPUB 3 formats.

## Features

### Comprehensive Metadata Extraction

- **Basic Metadata**: Title, authors, language, publisher, publication date
- **Identifiers**: ISBN, UUID, and other identifier schemes
- **Classification**: Subjects/genres, description
- **Series Detection**: Automatic detection of book series and ordering
- **Rights Information**: Copyright and rights metadata
- **Contributors**: Editors, translators, and other contributors
- **Version Detection**: Automatic EPUB 2/3 format detection

### Advanced Content Processing

- **Chapter-Based Parsing**: Extract individual chapters with titles and content
- **HTML Cleaning**: Intelligent removal of scripts, styles, and formatting
- **Word Counting**: Automatic word count per chapter and total
- **Text Extraction**: Clean text extraction from XHTML content
- **Configurable Limits**: Control chapter count and text length

### Cover Image Support

- **Cover Detection**: Multiple methods for finding cover images
- **Image Extraction**: Save cover images to disk
- **Format Detection**: Automatic format detection (PNG, JPEG, etc.)
- **Metadata Preservation**: Track cover availability in metadata

## Installation

The enhanced EPUB reader requires:

```bash
pip install ebooklib beautifulsoup4 lxml
```

Optional for cover extraction:
```bash
pip install Pillow
```

## Quick Start

### Simple Text Extraction

Backward-compatible with existing code:

```python
from file_organizer.utils.epub_enhanced import read_epub_simple

# Extract text content (up to 10,000 characters)
text = read_epub_simple("book.epub", max_chars=10000)
print(text)
```

### Metadata-Only Extraction

Fast metadata extraction without parsing chapters:

```python
from file_organizer.utils.epub_enhanced import get_epub_metadata

# Get metadata only
metadata = get_epub_metadata("book.epub")

print(f"Title: {metadata.title}")
print(f"Authors: {', '.join(metadata.authors)}")
print(f"ISBN: {metadata.isbn}")
print(f"Series: {metadata.series} #{metadata.series_index}")
```

### Full Processing

Complete extraction with all features:

```python
from file_organizer.utils.epub_enhanced import EnhancedEPUBReader
from pathlib import Path

# Create reader
reader = EnhancedEPUBReader()

# Read EPUB with all features
content = reader.read_epub(
    file_path=Path("book.epub"),
    extract_cover=True,
    cover_output_dir=Path("covers"),
    max_chapters=None  # Read all chapters
)

# Access metadata
print(f"Title: {content.metadata.title}")
print(f"Authors: {', '.join(content.metadata.authors)}")
print(f"Total chapters: {content.total_chapters}")
print(f"Total words: {content.total_words}")

# Access chapters
for chapter in content.chapters:
    print(f"\nChapter: {chapter.title}")
    print(f"Words: {chapter.word_count}")
    print(f"Preview: {chapter.content[:100]}...")

# Access cover
if content.metadata.cover_path:
    print(f"Cover saved to: {content.metadata.cover_path}")
```

## API Reference

### Data Classes

#### EPUBMetadata

Comprehensive book metadata.

**Attributes:**

- `title: str` - Book title
- `authors: list[str]` - List of author names
- `language: Optional[str]` - Language code (e.g., 'en', 'fr')
- `publisher: Optional[str]` - Publisher name
- `publication_date: Optional[str]` - Publication date
- `isbn: Optional[str]` - ISBN identifier
- `identifiers: dict[str, str]` - All identifiers
- `subjects: list[str]` - Subject/genre tags
- `description: Optional[str]` - Book description
- `series: Optional[str]` - Series name (if part of series)
- `series_index: Optional[float]` - Book number in series
- `rights: Optional[str]` - Copyright information
- `contributors: list[str]` - Editors, translators, etc.
- `has_cover: bool` - Whether book has cover image
- `cover_path: Optional[Path]` - Path to extracted cover
- `epub_version: Optional[str]` - EPUB version ('2.0' or '3.0')

#### EPUBChapter

Represents a single chapter.

**Attributes:**

- `title: str` - Chapter title
- `content: str` - Chapter text (HTML stripped)
- `order: int` - Chapter position/number
- `word_count: int` - Word count for chapter

#### EPUBContent

Complete book content and metadata.

**Attributes:**

- `metadata: EPUBMetadata` - Book metadata
- `chapters: list[EPUBChapter]` - List of chapters
- `total_words: int` - Total word count
- `total_chapters: int` - Number of chapters
- `raw_text: str` - Combined text from all chapters

### Classes

#### EnhancedEPUBReader

Main class for reading and processing EPUB files.

**Methods:**

##### `__init__()`

Initialize the reader.

**Raises:**
- `ImportError` - If ebooklib or BeautifulSoup not installed

##### `read_epub(file_path, extract_cover=False, cover_output_dir=None, max_chapters=None)`

Read and parse an EPUB file.

**Parameters:**
- `file_path: str | Path` - Path to EPUB file
- `extract_cover: bool` - Whether to extract cover image (default: False)
- `cover_output_dir: Optional[Path]` - Directory for cover (default: same as EPUB)
- `max_chapters: Optional[int]` - Maximum chapters to extract (default: all)

**Returns:**
- `EPUBContent` - Complete book data

**Raises:**
- `EPUBProcessingError` - If file cannot be read or parsed
- `FileNotFoundError` - If file does not exist

**Example:**
```python
reader = EnhancedEPUBReader()
content = reader.read_epub("book.epub", extract_cover=True, max_chapters=10)
```

### Helper Functions

#### `read_epub_simple(file_path, max_chars=10000)`

Simple text extraction for backward compatibility.

**Parameters:**
- `file_path: str | Path` - Path to EPUB file
- `max_chars: int` - Maximum characters to extract (default: 10000)

**Returns:**
- `str` - Extracted text content

**Example:**
```python
text = read_epub_simple("book.epub", max_chars=5000)
```

#### `get_epub_metadata(file_path)`

Extract only metadata (no chapter parsing).

**Parameters:**
- `file_path: str | Path` - Path to EPUB file

**Returns:**
- `EPUBMetadata` - Book metadata

**Example:**
```python
metadata = get_epub_metadata("book.epub")
print(metadata.title, metadata.isbn)
```

## Series Detection

The reader automatically detects if a book is part of a series using:

1. **Calibre Metadata**: Checks for `calibre:series` and `calibre:series_index` metadata
2. **Title Patterns**: Detects common series patterns:
   - "Series Name, Book 1"
   - "Series Name #2"
   - "Series Name: Book Three"
   - "Series Name (Book 4)"
   - "Series Name - Book 5"

**Example:**

```python
metadata = get_epub_metadata("harry_potter_1.epub")

if metadata.series:
    print(f"Book: {metadata.title}")
    print(f"Series: {metadata.series}")
    print(f"Book #{metadata.series_index}")
else:
    print("Standalone book")
```

## ISBN Handling

ISBNs are automatically:

- **Extracted** from multiple identifier types
- **Cleaned** (hyphens, spaces, and formatting removed)
- **Validated** for ISBN-10 (with X suffix) and ISBN-13

**Example:**

```python
# Original ISBN: "978-1-234-56789-0"
metadata = get_epub_metadata("book.epub")
print(metadata.isbn)  # Output: "9781234567890"
```

## Cover Image Extraction

Extract and save cover images:

```python
reader = EnhancedEPUBReader()

content = reader.read_epub(
    "book.epub",
    extract_cover=True,
    cover_output_dir=Path("covers")
)

if content.metadata.cover_path:
    print(f"Cover: {content.metadata.cover_path}")
    # Cover saved as: covers/book_cover.png (or .jpg)
```

Cover detection methods:

1. Check OPF metadata for cover reference
2. Look for items with type `ITEM_COVER`
3. Search images with "cover" in filename

## Performance Considerations

### Fast Metadata-Only

For quick metadata extraction without parsing chapters:

```python
# Fast - only reads metadata
metadata = get_epub_metadata("book.epub")  # ~50-100ms
```

### Controlled Chapter Parsing

Limit chapters for faster preview:

```python
# Faster - only parses first 5 chapters
content = reader.read_epub("book.epub", max_chapters=5)  # ~200-500ms
```

### Full Parsing

Read everything:

```python
# Slower - parses all chapters
content = reader.read_epub("book.epub")  # ~500-2000ms
```

### Batch Processing

Process multiple EPUBs efficiently:

```python
from pathlib import Path

reader = EnhancedEPUBReader()

for epub_file in Path("ebooks").glob("*.epub"):
    try:
        # Quick metadata only
        metadata = get_epub_metadata(epub_file)
        print(f"{metadata.title} by {metadata.authors[0]}")
    except Exception as e:
        print(f"Error processing {epub_file.name}: {e}")
```

## Error Handling

The module defines a custom exception:

```python
from file_organizer.utils.epub_enhanced import EPUBProcessingError

try:
    content = reader.read_epub("book.epub")
except FileNotFoundError:
    print("EPUB file not found")
except EPUBProcessingError as e:
    print(f"Failed to process EPUB: {e}")
except ImportError as e:
    print(f"Missing dependency: {e}")
```

## EPUB Format Support

### EPUB 2

- Full support for EPUB 2.x specification
- NCX navigation parsing
- OPF metadata extraction
- HTML content parsing

### EPUB 3

- Full support for EPUB 3.x specification
- Nav document parsing
- Enhanced metadata attributes
- HTML5 content parsing
- Media overlays detection (metadata only)

## Limitations

1. **Text-Only**: Only text content is extracted (images, audio, video are skipped)
2. **No Interactive Elements**: JavaScript and interactive content ignored
3. **Basic Formatting**: Complex CSS and formatting removed
4. **English-Focused**: Series detection patterns optimized for English titles
5. **No DRM**: Does not handle DRM-protected EPUBs

## Examples

See `examples/epub_processing_example.py` for comprehensive usage examples including:

- Basic text extraction
- Metadata-only extraction
- Full processing with chapters
- Cover image extraction
- Series detection
- ISBN handling
- Batch processing

## Testing

Run the test suite:

```bash
# All EPUB tests
pytest tests/utils/test_epub_enhanced.py -v

# Specific test categories
pytest tests/utils/test_epub_enhanced.py::TestEPUBMetadata -v
pytest tests/utils/test_epub_enhanced.py::TestEnhancedEPUBReader -v

# With coverage
pytest tests/utils/test_epub_enhanced.py --cov=file_organizer.utils.epub_enhanced
```

Current test coverage: **83%** (23 tests, all passing)

## Integration with File Organizer

The enhanced EPUB reader integrates seamlessly with the existing file organizer:

```python
from file_organizer.utils.file_readers import read_ebook_file

# Automatically uses enhanced reader
text = read_ebook_file("book.epub", max_chars=10000)
```

For advanced features, import the enhanced reader directly:

```python
from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

reader = EnhancedEPUBReader()
content = reader.read_epub("book.epub")
```

## Changelog

### Version 1.0 (2026-01-24)

- Initial release with comprehensive EPUB processing
- Support for EPUB 2 and EPUB 3 formats
- Rich metadata extraction (authors, series, ISBN, etc.)
- Chapter-based content parsing
- Cover image extraction
- Series detection from metadata and titles
- 23 comprehensive tests with 83% coverage

## Future Enhancements

Potential improvements for future versions:

- [ ] Support for MOBI/AZW formats
- [ ] Enhanced series detection for non-English titles
- [ ] Image extraction from chapter content
- [ ] Table of contents generation
- [ ] Reading progress tracking
- [ ] Annotation and highlight support
- [ ] Multi-language metadata translation

## Contributing

When contributing EPUB processing enhancements:

1. Maintain backward compatibility with `read_ebook_file()`
2. Add tests for new features
3. Update this documentation
4. Follow project coding standards (type hints, docstrings)
5. Handle errors gracefully with clear messages

## Support

For issues related to EPUB processing:

1. Check that `ebooklib` and `beautifulsoup4` are installed
2. Verify EPUB file is not corrupted
3. Test with different EPUB files
4. Check logs for detailed error messages
5. Report issues with sample EPUB files (if redistributable)
