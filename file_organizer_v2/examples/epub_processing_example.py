#!/usr/bin/env python3
"""Example usage of enhanced EPUB processing capabilities.

This script demonstrates how to use the EnhancedEPUBReader to extract
comprehensive metadata and content from EPUB files.
"""

from pathlib import Path
from file_organizer.utils.epub_enhanced import (
    EnhancedEPUBReader,
    get_epub_metadata,
    read_epub_simple
)


def example_basic_text_extraction():
    """Example 1: Quick text extraction from EPUB."""
    print("=" * 60)
    print("Example 1: Basic Text Extraction")
    print("=" * 60)

    epub_path = Path("sample.epub")

    # Quick text extraction (backward compatible with existing code)
    text = read_epub_simple(epub_path, max_chars=500)

    print(f"\nExtracted text (first 500 chars):")
    print(text)
    print()


def example_metadata_only():
    """Example 2: Extract only metadata (fast, no chapter parsing)."""
    print("=" * 60)
    print("Example 2: Metadata-Only Extraction")
    print("=" * 60)

    epub_path = Path("sample.epub")

    # Get only metadata
    metadata = get_epub_metadata(epub_path)

    print(f"\nTitle: {metadata.title}")
    print(f"Authors: {', '.join(metadata.authors)}")
    print(f"Language: {metadata.language}")
    print(f"Publisher: {metadata.publisher}")
    print(f"ISBN: {metadata.isbn}")

    if metadata.series:
        print(f"\nSeries: {metadata.series}")
        print(f"Series Index: {metadata.series_index}")

    if metadata.subjects:
        print(f"\nSubjects/Genres: {', '.join(metadata.subjects)}")

    if metadata.description:
        print(f"\nDescription: {metadata.description[:200]}...")

    print(f"\nEPUB Version: {metadata.epub_version}")
    print(f"Has Cover: {metadata.has_cover}")
    print()


def example_full_processing():
    """Example 3: Full EPUB processing with chapters."""
    print("=" * 60)
    print("Example 3: Full Processing with Chapters")
    print("=" * 60)

    epub_path = Path("sample.epub")

    # Create reader instance
    reader = EnhancedEPUBReader()

    # Read entire EPUB (metadata + chapters)
    content = reader.read_epub(epub_path)

    # Display metadata
    print(f"\nTitle: {content.metadata.title}")
    print(f"Authors: {', '.join(content.metadata.authors)}")
    print(f"Total Chapters: {content.total_chapters}")
    print(f"Total Words: {content.total_words:,}")

    # Display chapter information
    print("\nChapters:")
    for i, chapter in enumerate(content.chapters[:5], 1):  # Show first 5
        print(f"  {i}. {chapter.title}")
        print(f"     Words: {chapter.word_count:,}")
        print(f"     Preview: {chapter.content[:100]}...")
        print()

    if len(content.chapters) > 5:
        print(f"  ... and {len(content.chapters) - 5} more chapters")

    print()


def example_with_cover_extraction():
    """Example 4: Extract cover image."""
    print("=" * 60)
    print("Example 4: Cover Image Extraction")
    print("=" * 60)

    epub_path = Path("sample.epub")
    output_dir = Path("covers")

    reader = EnhancedEPUBReader()

    # Read with cover extraction
    content = reader.read_epub(
        epub_path,
        extract_cover=True,
        cover_output_dir=output_dir
    )

    print(f"\nTitle: {content.metadata.title}")
    print(f"Has Cover: {content.metadata.has_cover}")

    if content.metadata.cover_path:
        print(f"Cover saved to: {content.metadata.cover_path}")
    else:
        print("No cover image found or extraction failed")

    print()


def example_limited_chapters():
    """Example 5: Extract limited number of chapters (fast preview)."""
    print("=" * 60)
    print("Example 5: Limited Chapter Extraction")
    print("=" * 60)

    epub_path = Path("sample.epub")

    reader = EnhancedEPUBReader()

    # Read only first 3 chapters (faster for previews)
    content = reader.read_epub(epub_path, max_chapters=3)

    print(f"\nTitle: {content.metadata.title}")
    print(f"Extracted {len(content.chapters)} chapters (limited to 3)")
    print(f"Total words in preview: {content.total_words:,}")

    for chapter in content.chapters:
        print(f"\n- {chapter.title} ({chapter.word_count} words)")

    print()


def example_series_detection():
    """Example 6: Series detection and book ordering."""
    print("=" * 60)
    print("Example 6: Series Detection")
    print("=" * 60)

    # Examples of series detection
    test_titles = [
        "The Hobbit",  # Standalone
        "Harry Potter, Book 1",  # Explicit series
        "Foundation #2",  # Series with number
        "The Lord of the Rings: Book Three",  # Series with word number
    ]

    reader = EnhancedEPUBReader()

    for title in test_titles:
        # Simulate series detection
        from unittest.mock import Mock
        mock_book = Mock()
        mock_book.get_metadata = Mock(return_value=[])

        series, index = reader._detect_series(title, mock_book)

        print(f"\nTitle: {title}")
        if series:
            print(f"  Series: {series}")
            print(f"  Index: {index}")
        else:
            print("  Standalone book (no series detected)")

    print()


def example_isbn_cleaning():
    """Example 7: ISBN cleaning and validation."""
    print("=" * 60)
    print("Example 7: ISBN Cleaning")
    print("=" * 60)

    reader = EnhancedEPUBReader()

    # Examples of ISBN formats
    test_isbns = [
        "978-1-234-56789-0",
        "978 1 234 56789 0",
        "ISBN: 978-1-234-56789-0",
        "123-456-789-X",  # ISBN-10 with X
    ]

    for isbn in test_isbns:
        cleaned = reader._clean_isbn(isbn)
        print(f"\nOriginal: {isbn}")
        print(f"Cleaned:  {cleaned}")

    print()


def example_batch_processing():
    """Example 8: Process multiple EPUB files."""
    print("=" * 60)
    print("Example 8: Batch Processing")
    print("=" * 60)

    epub_dir = Path("ebooks")

    if not epub_dir.exists():
        print(f"\nDirectory '{epub_dir}' not found. Skipping batch example.")
        print()
        return

    reader = EnhancedEPUBReader()

    # Find all EPUB files
    epub_files = list(epub_dir.glob("*.epub"))

    print(f"\nFound {len(epub_files)} EPUB files")

    # Process each file
    for epub_file in epub_files:
        try:
            # Quick metadata extraction
            metadata = get_epub_metadata(epub_file)

            print(f"\n{epub_file.name}")
            print(f"  Title: {metadata.title}")
            print(f"  Author: {', '.join(metadata.authors[:2])}")
            if len(metadata.authors) > 2:
                print(f"         ... and {len(metadata.authors) - 2} more")

        except Exception as e:
            print(f"\n{epub_file.name}")
            print(f"  Error: {e}")

    print()


def main():
    """Run all examples."""
    examples = [
        ("Basic Text Extraction", example_basic_text_extraction),
        ("Metadata Only", example_metadata_only),
        ("Full Processing", example_full_processing),
        ("Cover Extraction", example_with_cover_extraction),
        ("Limited Chapters", example_limited_chapters),
        ("Series Detection", example_series_detection),
        ("ISBN Cleaning", example_isbn_cleaning),
        ("Batch Processing", example_batch_processing),
    ]

    print("\n" + "=" * 60)
    print("Enhanced EPUB Processing Examples")
    print("=" * 60)
    print("\nNote: These examples require sample EPUB files.")
    print("Replace 'sample.epub' with your own EPUB file path.\n")

    # Run non-file examples (they work without actual EPUB files)
    example_series_detection()
    example_isbn_cleaning()

    print("\n" + "=" * 60)
    print("For file-based examples, provide EPUB files and uncomment below:")
    print("=" * 60)
    print()

    # Uncomment these when you have EPUB files:
    # example_basic_text_extraction()
    # example_metadata_only()
    # example_full_processing()
    # example_with_cover_extraction()
    # example_limited_chapters()
    # example_batch_processing()


if __name__ == "__main__":
    main()
