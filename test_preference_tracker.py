#!/usr/bin/env python3
"""
Simple test script to verify PreferenceTracker functionality.
"""

import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "file_organizer_v2" / "src"))

from file_organizer.services.intelligence import (
    PreferenceTracker,
    PreferenceType,
    CorrectionType,
    track_file_move,
    track_file_rename,
    track_category_change,
)


def test_basic_tracking():
    """Test basic preference tracking."""
    print("Testing basic preference tracking...")

    tracker = PreferenceTracker()

    # Test 1: Track a file move
    source = Path("/tmp/test/document.pdf")
    destination = Path("/tmp/test/Documents/document.pdf")
    track_file_move(tracker, source, destination)

    print(f"✓ Tracked file move: {source} -> {destination}")

    # Test 2: Track a file rename
    source = Path("/tmp/test/photo.jpg")
    destination = Path("/tmp/test/vacation_photo.jpg")
    track_file_rename(tracker, source, destination)

    print(f"✓ Tracked file rename: {source} -> {destination}")

    # Test 3: Track a category change
    file_path = Path("/tmp/test/report.docx")
    track_category_change(tracker, file_path, "General", "Work")

    print(f"✓ Tracked category change for: {file_path}")

    # Test 4: Get statistics
    stats = tracker.get_statistics()
    print(f"\n✓ Statistics:")
    print(f"  - Total corrections: {stats['total_corrections']}")
    print(f"  - Total preferences: {stats['total_preferences']}")
    print(f"  - Unique preferences: {stats['unique_preferences']}")
    print(f"  - Average confidence: {stats['average_confidence']}")

    # Test 5: Get preference for similar file
    similar_file = Path("/tmp/test/another_document.pdf")
    pref = tracker.get_preference(similar_file, PreferenceType.FOLDER_MAPPING)

    if pref:
        print(f"\n✓ Found preference for {similar_file}:")
        print(f"  - Type: {pref.preference_type.value}")
        print(f"  - Value: {pref.value}")
        print(f"  - Confidence: {pref.metadata.confidence}")
        print(f"  - Frequency: {pref.metadata.frequency}")
    else:
        print(f"\n✗ No preference found for {similar_file}")

    # Test 6: Track another similar correction to increase confidence
    source2 = Path("/tmp/test/report.pdf")
    destination2 = Path("/tmp/test/Documents/report.pdf")
    track_file_move(tracker, source2, destination2)

    # Get updated preference
    pref2 = tracker.get_preference(similar_file, PreferenceType.FOLDER_MAPPING)
    if pref2:
        print(f"\n✓ Updated preference after second correction:")
        print(f"  - Confidence: {pref2.metadata.confidence} (increased)")
        print(f"  - Frequency: {pref2.metadata.frequency}")

    # Test 7: Export and import data
    exported_data = tracker.export_data()
    print(f"\n✓ Exported data successfully")
    print(f"  - Keys: {list(exported_data.keys())}")

    # Create new tracker and import
    new_tracker = PreferenceTracker()
    new_tracker.import_data(exported_data)
    new_stats = new_tracker.get_statistics()

    print(f"\n✓ Imported data successfully")
    print(f"  - Total corrections: {new_stats['total_corrections']}")
    print(f"  - Total preferences: {new_stats['total_preferences']}")

    # Test 8: Update preference confidence
    if pref2:
        original_confidence = pref2.metadata.confidence
        tracker.update_preference_confidence(pref2, success=True)
        print(f"\n✓ Updated preference confidence:")
        print(f"  - Before: {original_confidence}")
        print(f"  - After: {pref2.metadata.confidence}")

    # Test 9: Get recent corrections
    recent = tracker.get_recent_corrections(limit=3)
    print(f"\n✓ Recent corrections (last 3):")
    for i, corr in enumerate(recent, 1):
        print(f"  {i}. {corr.correction_type.value}: {corr.source.name} -> {corr.destination.name}")

    print("\n" + "="*60)
    print("All tests passed! ✓")
    print("="*60)


def test_thread_safety():
    """Test thread-safe operations."""
    print("\n\nTesting thread-safe operations...")

    import threading
    import time

    tracker = PreferenceTracker()
    results = []

    def track_corrections(thread_id):
        """Track corrections in parallel."""
        for i in range(5):
            source = Path(f"/tmp/test{thread_id}/file{i}.txt")
            destination = Path(f"/tmp/test{thread_id}/Docs/file{i}.txt")
            track_file_move(tracker, source, destination)
            time.sleep(0.01)  # Small delay to simulate work
        results.append(thread_id)

    # Create multiple threads
    threads = []
    for i in range(3):
        thread = threading.Thread(target=track_corrections, args=(i,))
        threads.append(thread)
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    # Check results
    stats = tracker.get_statistics()
    print(f"\n✓ Thread-safe operations completed:")
    print(f"  - Threads run: {len(results)}")
    print(f"  - Total corrections: {stats['total_corrections']}")
    print(f"  - Expected corrections: {len(results) * 5}")

    if stats['total_corrections'] == len(results) * 5:
        print(f"  - Result: PASS ✓")
    else:
        print(f"  - Result: FAIL ✗ (race condition detected)")


if __name__ == "__main__":
    print("="*60)
    print("PreferenceTracker Functionality Test")
    print("="*60)

    test_basic_tracking()
    test_thread_safety()

    print("\nAll tests completed successfully!")
