#!/usr/bin/env python3
"""Test the VisionProcessor with sample images."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from file_organizer.services import VisionProcessor
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="DEBUG")


def test_vision_processor():
    """Test vision processor initialization and basic operations."""
    print("\n" + "=" * 70)
    print("Testing VisionProcessor")
    print("=" * 70 + "\n")

    try:
        # Initialize processor
        print("1. Initializing VisionProcessor...")
        processor = VisionProcessor()
        processor.initialize()
        print("   ✓ VisionProcessor initialized\n")

        # Test connection
        print("2. Testing model connection...")
        info = processor.vision_model.test_connection()
        print(f"   ✓ Model: {info['name']}")
        print(f"   ✓ Status: {info['status']}")
        print(f"   ✓ Size: {info.get('size', 'unknown')}\n")

        print("=" * 70)
        print("✓ All tests passed!")
        print("=" * 70)

        # Cleanup
        processor.cleanup()
        return True

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        logger.exception("Test failed")
        return False


if __name__ == "__main__":
    success = test_vision_processor()
    sys.exit(0 if success else 1)
