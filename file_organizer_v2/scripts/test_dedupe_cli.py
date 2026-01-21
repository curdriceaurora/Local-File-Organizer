#!/usr/bin/env python3
"""
Test script for deduplication CLI.

Creates sample files with duplicates and tests the CLI functionality.
"""

import sys
import tempfile
from pathlib import Path

# Add src to path
from file_organizer.cli.dedupe import dedupe_command


def create_test_files(base_dir: Path):
    """Create test files with known duplicates."""
    print(f"Creating test files in {base_dir}")

    # Create some unique files
    (base_dir / "unique1.txt").write_text("This is a unique file 1")
    (base_dir / "unique2.txt").write_text("This is a unique file 2")

    # Create duplicate set 1
    duplicate_content_1 = "This is duplicate content set 1\n" * 100
    (base_dir / "dup1_original.txt").write_text(duplicate_content_1)
    (base_dir / "dup1_copy1.txt").write_text(duplicate_content_1)
    (base_dir / "dup1_copy2.txt").write_text(duplicate_content_1)

    # Create duplicate set 2 in a subdirectory
    subdir = base_dir / "subdir"
    subdir.mkdir()
    duplicate_content_2 = "This is duplicate content set 2\n" * 50
    (subdir / "dup2_original.txt").write_text(duplicate_content_2)
    (subdir / "dup2_copy.txt").write_text(duplicate_content_2)

    # Create a large duplicate set
    large_content = "X" * 1024 * 100  # 100KB
    (base_dir / "large_dup1.dat").write_text(large_content)
    (base_dir / "large_dup2.dat").write_text(large_content)

    print("✓ Created test files:")
    print("  - 2 unique files")
    print("  - 3 duplicates of content set 1")
    print("  - 2 duplicates of content set 2")
    print("  - 2 large duplicates (100KB each)")
    print()


def test_dry_run(test_dir: Path):
    """Test dry-run mode."""
    print("=" * 70)
    print("TEST 1: Dry-run mode with SHA256")
    print("=" * 70)
    print()

    # Run dedupe in dry-run mode
    exit_code = dedupe_command([
        str(test_dir),
        "--algorithm", "sha256",
        "--dry-run",
        "--strategy", "oldest",
    ])

    print()
    print(f"Exit code: {exit_code}")
    print()

    return exit_code == 0


def test_md5_algorithm(test_dir: Path):
    """Test with MD5 algorithm."""
    print("=" * 70)
    print("TEST 2: Dry-run mode with MD5")
    print("=" * 70)
    print()

    exit_code = dedupe_command([
        str(test_dir),
        "--algorithm", "md5",
        "--dry-run",
        "--strategy", "newest",
    ])

    print()
    print(f"Exit code: {exit_code}")
    print()

    return exit_code == 0


def test_size_filters(test_dir: Path):
    """Test with size filters."""
    print("=" * 70)
    print("TEST 3: Size filters (only files > 10KB)")
    print("=" * 70)
    print()

    # Should only find the large duplicates (100KB each)
    exit_code = dedupe_command([
        str(test_dir),
        "--min-size", "10240",  # 10KB minimum
        "--dry-run",
    ])

    print()
    print(f"Exit code: {exit_code}")
    print()

    return exit_code == 0


def test_non_recursive(test_dir: Path):
    """Test non-recursive mode."""
    print("=" * 70)
    print("TEST 4: Non-recursive mode (should skip subdir)")
    print("=" * 70)
    print()

    exit_code = dedupe_command([
        str(test_dir),
        "--no-recursive",
        "--dry-run",
    ])

    print()
    print(f"Exit code: {exit_code}")
    print()

    return exit_code == 0


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("DEDUPLICATION CLI TEST SUITE")
    print("=" * 70)
    print()

    # Create temporary directory for tests
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)
        create_test_files(test_dir)

        # Run tests
        results = []
        results.append(("Dry-run with SHA256", test_dry_run(test_dir)))
        results.append(("Dry-run with MD5", test_md5_algorithm(test_dir)))
        results.append(("Size filters", test_size_filters(test_dir)))
        results.append(("Non-recursive mode", test_non_recursive(test_dir)))

        # Summary
        print("=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        print()

        passed = sum(1 for _, result in results if result)
        total = len(results)

        for test_name, result in results:
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"{status}: {test_name}")

        print()
        print(f"Results: {passed}/{total} tests passed")
        print()

        if passed == total:
            print("✓ All tests passed!")
            return 0
        else:
            print("✗ Some tests failed")
            return 1


if __name__ == "__main__":
    sys.exit(main())
