#!/usr/bin/env python3
"""
Example usage of ImageDeduplicator for finding duplicate images.

This script demonstrates:
1. Basic duplicate detection
2. Configurable similarity thresholds
3. Progress tracking
4. Quality-based selection
"""

import sys
from pathlib import Path

# Add src to path for development
from file_organizer.services.deduplication import (
    ImageDeduplicator,
    get_best_quality_image,
    get_image_info_string,
)


def progress_callback(current: int, total: int) -> None:
    """Print progress updates."""
    percent = (current / total) * 100
    print(f"\rProcessing: {current}/{total} ({percent:.1f}%)", end="", flush=True)
    if current == total:
        print()  # New line when done


def example_basic_usage():
    """Basic example of finding duplicates."""
    print("=" * 60)
    print("Example 1: Basic Duplicate Detection")
    print("=" * 60)
    print()

    # Initialize deduplicator with pHash and threshold of 10
    deduper = ImageDeduplicator(hash_method="phash", threshold=10)

    # Specify directory to scan
    directory = Path("./test_images")  # Change this to your image directory

    if not directory.exists():
        print(f"Directory not found: {directory}")
        print("Please create a directory with some images to test.")
        return

    print(f"Scanning directory: {directory}")
    print(f"Hash method: {deduper.hash_method}")
    print(f"Similarity threshold: {deduper.threshold}")
    print()

    # Find duplicates with progress callback
    duplicates = deduper.find_duplicates(
        directory,
        recursive=True,
        progress_callback=progress_callback
    )

    print()
    print(f"Found {len(duplicates)} groups of duplicate images")
    print()

    # Display results
    if duplicates:
        for idx, (hash_key, images) in enumerate(duplicates.items(), 1):
            print(f"Group {idx} ({len(images)} images):")
            for img_path in images:
                print(f"  - {get_image_info_string(img_path)}")

            # Show best quality image
            best = get_best_quality_image(images)
            if best:
                print(f"  → Best quality: {best.name}")
            print()
    else:
        print("No duplicates found.")


def example_strict_matching():
    """Example with strict similarity threshold."""
    print("=" * 60)
    print("Example 2: Strict Matching (Exact Duplicates Only)")
    print("=" * 60)
    print()

    # Very strict threshold (0-5 means nearly identical)
    deduper = ImageDeduplicator(hash_method="phash", threshold=5)

    directory = Path("./test_images")

    if not directory.exists():
        print(f"Directory not found: {directory}")
        return

    print(f"Using strict threshold: {deduper.threshold}")
    print("This will only find nearly identical images.")
    print()

    duplicates = deduper.find_duplicates(directory, recursive=True)

    print(f"Found {len(duplicates)} groups of near-identical images")
    print()


def example_loose_matching():
    """Example with loose similarity threshold."""
    print("=" * 60)
    print("Example 3: Loose Matching (Similar Images)")
    print("=" * 60)
    print()

    # Loose threshold (15-20 allows more variation)
    deduper = ImageDeduplicator(hash_method="phash", threshold=20)

    directory = Path("./test_images")

    if not directory.exists():
        print(f"Directory not found: {directory}")
        return

    print(f"Using loose threshold: {deduper.threshold}")
    print("This will find similar images (resized, compressed, etc.).")
    print()

    duplicates = deduper.find_duplicates(directory, recursive=True)

    print(f"Found {len(duplicates)} groups of similar images")
    print()


def example_compare_two_images():
    """Example of comparing two specific images."""
    print("=" * 60)
    print("Example 4: Compare Two Images")
    print("=" * 60)
    print()

    deduper = ImageDeduplicator(hash_method="phash")

    # Specify two images to compare
    img1 = Path("./test_images/image1.jpg")
    img2 = Path("./test_images/image2.jpg")

    if not (img1.exists() and img2.exists()):
        print("Please provide two images to compare:")
        print(f"  - {img1}")
        print(f"  - {img2}")
        return

    print(f"Comparing:")
    print(f"  1. {img1.name}")
    print(f"  2. {img2.name}")
    print()

    # Compute similarity
    similarity = deduper.compute_similarity(img1, img2)

    if similarity is not None:
        print(f"Similarity: {similarity:.2%}")
        print()

        # Interpret the result
        if similarity >= 0.95:
            print("→ These images are nearly identical")
        elif similarity >= 0.85:
            print("→ These images are very similar")
        elif similarity >= 0.70:
            print("→ These images are somewhat similar")
        else:
            print("→ These images are quite different")
    else:
        print("Could not compute similarity (one or both images failed to load)")


def example_different_hash_methods():
    """Example comparing different hash methods."""
    print("=" * 60)
    print("Example 5: Compare Hash Methods")
    print("=" * 60)
    print()

    directory = Path("./test_images")

    if not directory.exists():
        print(f"Directory not found: {directory}")
        return

    for method in ["phash", "dhash", "ahash"]:
        print(f"Using {method.upper()}:")

        deduper = ImageDeduplicator(hash_method=method, threshold=10)
        duplicates = deduper.find_duplicates(directory, recursive=True)

        print(f"  Found {len(duplicates)} duplicate groups")
        print()


def main():
    """Run all examples."""
    print("\n")
    print("*" * 60)
    print("ImageDeduplicator Usage Examples")
    print("*" * 60)
    print()
    print("These examples demonstrate various ways to use the")
    print("ImageDeduplicator for finding duplicate and similar images.")
    print()

    # Run examples
    try:
        example_basic_usage()
        print("\n")

        # Uncomment to run other examples:
        # example_strict_matching()
        # print("\n")
        #
        # example_loose_matching()
        # print("\n")
        #
        # example_compare_two_images()
        # print("\n")
        #
        # example_different_hash_methods()
        # print("\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
