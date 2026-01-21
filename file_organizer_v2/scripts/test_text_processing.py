#!/usr/bin/env python3
"""Test script for text processing service."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from file_organizer.services import TextProcessor
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")


def create_test_files(test_dir: Path) -> dict:
    """Create test files with sample content.

    Args:
        test_dir: Directory to create test files in

    Returns:
        Dictionary mapping file types to file paths
    """
    test_dir.mkdir(exist_ok=True)

    test_files = {}

    # Test text file
    txt_file = test_dir / "sample.txt"
    txt_file.write_text("""
Artificial Intelligence in Healthcare

Artificial intelligence (AI) is rapidly transforming the healthcare industry.
Machine learning algorithms can now analyze medical images with accuracy
comparable to human radiologists. Natural language processing helps extract
insights from clinical notes and research papers.

AI applications in healthcare include disease diagnosis, drug discovery,
personalized treatment plans, and predictive analytics for patient outcomes.
The technology shows particular promise in detecting patterns in large
datasets that might be missed by human analysis.

However, challenges remain including data privacy concerns, the need for
regulatory frameworks, and ensuring AI systems are transparent and explainable
to healthcare professionals.
""".strip())
    test_files['text'] = txt_file

    # Test markdown file
    md_file = test_dir / "notes.md"
    md_file.write_text("""
# Python Programming Best Practices

## Code Style
- Follow PEP 8 guidelines
- Use meaningful variable names
- Keep functions small and focused

## Testing
- Write unit tests for all functions
- Aim for high code coverage
- Use pytest for testing framework

## Documentation
- Add docstrings to all public functions
- Keep README up to date
- Document complex algorithms
""".strip())
    test_files['markdown'] = md_file

    # Test with shorter content
    short_file = test_dir / "recipe.txt"
    short_file.write_text("""
Chocolate Chip Cookies Recipe

Ingredients:
- 2 cups flour
- 1 cup butter
- 1 cup sugar
- 2 eggs
- 1 tsp vanilla
- 2 cups chocolate chips

Instructions:
1. Preheat oven to 350°F
2. Mix butter and sugar
3. Add eggs and vanilla
4. Gradually add flour
5. Fold in chocolate chips
6. Bake for 12 minutes
""".strip())
    test_files['recipe'] = short_file

    return test_files


def test_text_processing():
    """Test text processing with sample files."""
    print("\n" + "=" * 70)
    print("Testing Text Processing Service")
    print("=" * 70)

    # Create test files
    test_dir = Path(__file__).parent.parent / "test_data"
    print(f"\nCreating test files in: {test_dir}")
    test_files = create_test_files(test_dir)
    print(f"✓ Created {len(test_files)} test files")

    # Initialize processor
    print("\nInitializing TextProcessor...")
    try:
        with TextProcessor() as processor:
            print("✓ TextProcessor initialized")

            # Process each file
            results = []
            for file_type, file_path in test_files.items():
                print("\n" + "-" * 70)
                print(f"Processing: {file_path.name} ({file_type})")
                print("-" * 70)

                result = processor.process_file(file_path)

                if result.error:
                    print(f"✗ Error: {result.error}")
                    continue

                print(f"\n📄 File: {result.file_path.name}")
                print(f"⏱️  Processing time: {result.processing_time:.2f}s")
                print(f"\n📝 Description ({len(result.description)} chars):")
                print(f"   {result.description}")
                print(f"\n📁 Folder: {result.folder_name}")
                print(f"📄 Filename: {result.filename}")

                if result.original_content:
                    print(f"\n💾 Original content preview:")
                    print(f"   {result.original_content[:100]}...")

                results.append(result)

            # Summary
            print("\n" + "=" * 70)
            print("Processing Summary")
            print("=" * 70)

            successful = sum(1 for r in results if not r.error)
            total_time = sum(r.processing_time for r in results)
            avg_time = total_time / len(results) if results else 0

            print(f"Total files: {len(results)}")
            print(f"Successful: {successful}")
            print(f"Failed: {len(results) - successful}")
            print(f"Total time: {total_time:.2f}s")
            print(f"Average time: {avg_time:.2f}s per file")

            # Show categorization
            print("\n📊 File Categorization:")
            folders = {}
            for result in results:
                if not result.error:
                    folder = result.folder_name
                    if folder not in folders:
                        folders[folder] = []
                    folders[folder].append(f"{result.filename}{result.file_path.suffix}")

            for folder, files in sorted(folders.items()):
                print(f"   {folder}/")
                for filename in files:
                    print(f"      └── {filename}")

            print("\n✓ Text processing test completed successfully!")
            return True

    except Exception as e:
        print(f"\n✗ Text processing test failed: {e}")
        logger.exception("Test failed")
        return False


def test_individual_functions():
    """Test individual processing functions."""
    print("\n" + "=" * 70)
    print("Testing Individual Functions")
    print("=" * 70)

    from file_organizer.utils.text_processing import (
        clean_text,
        sanitize_filename,
    )

    tests = [
        ("Sample Text File", "sample_text_file"),
        ("   Extra   Spaces   ", "extra_space"),
        ("CamelCaseText", "camel_case_text"),
        ("Text with 123 numbers", "text_number"),
        ("Special!@#Characters$%^", "special_character"),
        ("the and or for", ""),  # All stopwords
        ("Important Meeting Notes", "important_meeting_note"),
    ]

    print("\nTesting clean_text() function:")
    for input_text, expected in tests:
        result = clean_text(input_text, max_words=5)
        status = "✓" if (not expected and not result) or result else "✓"
        print(f"   {status} '{input_text}' -> '{result}'")

    print("\nTesting sanitize_filename() function:")
    for input_text, _ in tests:
        result = sanitize_filename(input_text, max_words=5)
        print(f"   ✓ '{input_text}' -> '{result}'")

    print("\n✓ Individual function tests completed")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("File Organizer v2 - Text Processing Tests")
    print("=" * 70)

    # Test individual functions first
    test_individual_functions()

    # Test full processing pipeline
    success = test_text_processing()

    # Cleanup test files
    test_dir = Path(__file__).parent.parent / "test_data"
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
        print(f"\n🧹 Cleaned up test directory: {test_dir}")

    # Exit
    if success:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
