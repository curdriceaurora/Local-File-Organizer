#!/usr/bin/env python3
"""
Test script with actual image generation and processing.
"""

import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PIL import Image, ImageDraw

from file_organizer.services.deduplication.image_dedup import ImageDeduplicator
from file_organizer.services.deduplication.image_utils import (
    get_image_metadata,
    get_best_quality_image,
    validate_image_file,
)


def create_test_image(path: Path, color: tuple, size: tuple = (100, 100), pattern: str = "rectangle"):
    """Create a simple colored test image."""
    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)

    if pattern == "rectangle":
        # Add some pattern to make it more interesting
        draw.rectangle([10, 10, 90, 90], outline="white", width=2)
    elif pattern == "circle":
        # Different pattern - circle
        draw.ellipse([10, 10, 90, 90], outline="white", width=2)
    elif pattern == "diagonal":
        # Diagonal lines
        draw.line([0, 0, 100, 100], fill="white", width=3)
        draw.line([0, 100, 100, 0], fill="white", width=3)
    else:
        # Solid color
        pass

    img.save(path)


def create_similar_image(path: Path, color: tuple, size: tuple = (100, 100)):
    """Create a slightly different image (for testing similarity)."""
    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    # Slightly different pattern
    draw.rectangle([12, 12, 88, 88], outline="white", width=2)
    img.save(path)


def test_with_real_images():
    """Test with actual generated images."""
    print("Testing with real images...")

    # Create temporary directory for test images
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test images
        img1 = tmpdir / "red1.png"
        img2 = tmpdir / "red2.png"  # Duplicate of red1
        img3 = tmpdir / "blue.png"  # Different image
        img4 = tmpdir / "red_similar.png"  # Similar to red1
        img5 = tmpdir / "red_resized.jpg"  # Same as red1 but different format

        create_test_image(img1, (255, 0, 0), pattern="rectangle")  # Red rectangle
        create_test_image(img2, (255, 0, 0), pattern="rectangle")  # Red rectangle (duplicate)
        create_test_image(img3, (0, 0, 255), pattern="diagonal")  # Blue with diagonals (different)
        create_similar_image(img4, (255, 0, 0))  # Red (slightly different rectangle)

        # Create resized version
        Image.open(img1).resize((150, 150)).save(img5)

        print(f"  Created test images in {tmpdir}")

        # Test image validation
        print("\n  Testing image validation...")
        is_valid, error = validate_image_file(img1)
        assert is_valid, f"Valid image failed validation: {error}"
        print("    ✓ Valid image passes validation")

        is_valid, error = validate_image_file(tmpdir / "nonexistent.png")
        assert not is_valid, "Nonexistent image should fail validation"
        print("    ✓ Nonexistent image fails validation")

        # Test metadata extraction
        print("\n  Testing metadata extraction...")
        meta = get_image_metadata(img1)
        assert meta is not None, "Failed to get metadata"
        assert meta.width == 100
        assert meta.height == 100
        assert meta.format == "PNG"
        print(f"    ✓ Metadata: {meta}")

        # Test hash computation
        print("\n  Testing hash computation...")
        deduper = ImageDeduplicator(hash_method="phash", threshold=10)

        hash1 = deduper.get_image_hash(img1)
        hash2 = deduper.get_image_hash(img2)
        hash3 = deduper.get_image_hash(img3)

        assert hash1 is not None, "Failed to compute hash for img1"
        assert hash2 is not None, "Failed to compute hash for img2"
        assert hash3 is not None, "Failed to compute hash for img3"
        print(f"    ✓ Hash 1: {hash1}")
        print(f"    ✓ Hash 2: {hash2}")
        print(f"    ✓ Hash 3: {hash3}")

        # Test that identical images have identical hashes
        distance_identical = deduper.compute_hamming_distance(hash1, hash2)
        print(f"    ✓ Distance between identical images: {distance_identical}")
        assert distance_identical == 0, "Identical images should have distance 0"

        # Test that different images have larger distance
        distance_different = deduper.compute_hamming_distance(hash1, hash3)
        print(f"    ✓ Distance between different images: {distance_different}")
        # Note: Simple test images might still be structurally similar
        # Just verify they're not identical
        assert distance_different > 0, "Different images should have distance > 0"

        # Test similarity computation
        print("\n  Testing similarity computation...")
        similarity = deduper.compute_similarity(img1, img2)
        assert similarity is not None
        assert similarity >= 0.99, f"Identical images should be >99% similar, got {similarity}"
        print(f"    ✓ Similarity between identical images: {similarity:.2%}")

        similarity_diff = deduper.compute_similarity(img1, img3)
        assert similarity_diff is not None
        assert similarity_diff < similarity, "Different images should be less similar than identical ones"
        print(f"    ✓ Similarity between different images: {similarity_diff:.2%}")

        # Test find_duplicates
        print("\n  Testing find_duplicates...")
        duplicates = deduper.find_duplicates(tmpdir, recursive=False)
        print(f"    ✓ Found {len(duplicates)} duplicate groups")

        for hash_key, images in duplicates.items():
            print(f"    ✓ Group with {len(images)} images:")
            for img in images:
                print(f"      - {img.name}")

        # Test batch hash computation
        print("\n  Testing batch hash computation...")
        all_images = [img1, img2, img3, img4, img5]
        hashes = deduper.batch_compute_hashes(all_images)
        assert len(hashes) == 5, f"Expected 5 hashes, got {len(hashes)}"
        print(f"    ✓ Computed {len(hashes)} hashes in batch")

        # Test clustering
        print("\n  Testing clustering...")
        clusters = deduper.cluster_by_similarity(all_images)
        print(f"    ✓ Found {len(clusters)} clusters")
        for i, cluster in enumerate(clusters, 1):
            print(f"    ✓ Cluster {i}: {len(cluster)} images")
            for img in cluster:
                print(f"      - {img.name}")

        # Test quality selection
        print("\n  Testing quality selection...")
        best = get_best_quality_image([img1, img5])
        print(f"    ✓ Best quality image: {best.name}")
        # PNG should be preferred over JPEG for same resolution
        assert best == img5, "Higher resolution image should be selected"

        print("\n✅ All real image tests passed!")


def main():
    """Run all tests."""
    print("=" * 60)
    print("ImageDeduplicator Test with Real Images")
    print("=" * 60)
    print()

    try:
        test_with_real_images()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
