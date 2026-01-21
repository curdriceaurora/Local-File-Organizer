#!/usr/bin/env python3
"""Test script for AI models."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from file_organizer.models import TextModel, VisionModel
from file_organizer.models.base import ModelConfig, ModelType
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")


def test_text_model():
    """Test text model with sample prompt."""
    print("\n" + "=" * 60)
    print("Testing Text Model (Qwen2.5 3B)")
    print("=" * 60)

    try:
        # Create config
        config = TextModel.get_default_config()
        print(f"\nModel: {config.name}")
        print(f"Framework: {config.framework}")
        print(f"Quantization: {config.quantization}")

        # Initialize model
        print("\nInitializing model...")
        model = TextModel(config)
        model.initialize()

        # Test connection
        print("\nTesting connection...")
        info = model.test_connection()
        print(f"Status: {info['status']}")
        print(f"Size: {info.get('size', 'unknown')}")

        # Test generation
        print("\nGenerating text...")
        prompt = """Provide a concise and accurate summary of the following text, focusing on the main ideas and key details.
Limit your summary to a maximum of 150 words.

Text: Artificial intelligence has revolutionized the field of file management. Modern AI systems can understand content, categorize files intelligently, and even predict user preferences over time. Local LLMs make this possible while preserving privacy.

Summary:"""

        response = model.generate(prompt)
        print("\nGenerated Summary:")
        print("-" * 60)
        print(response)
        print("-" * 60)

        # Cleanup
        model.cleanup()
        print("\n✓ Text model test PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Text model test FAILED: {e}")
        logger.exception("Test failed")
        return False


def test_vision_model():
    """Test vision model with sample image."""
    print("\n" + "=" * 60)
    print("Testing Vision Model (Qwen2.5-VL 7B)")
    print("=" * 60)

    try:
        # Create config
        config = VisionModel.get_default_config()
        print(f"\nModel: {config.name}")
        print(f"Framework: {config.framework}")
        print(f"Quantization: {config.quantization}")

        # Check if model exists
        print("\nChecking if model is installed...")
        import ollama
        client = ollama.Client()

        try:
            client.show(config.name)
            print(f"✓ Model {config.name} found")
        except ollama.ResponseError:
            print(f"✗ Model {config.name} not found")
            print("\nTo install vision model, run:")
            print(f"  ollama pull {config.name}")
            print("\nSkipping vision model test...")
            return None

        # Initialize model
        print("\nInitializing model...")
        model = VisionModel(config)
        model.initialize()

        # Test connection
        print("\nTesting connection...")
        info = model.test_connection()
        print(f"Status: {info['status']}")
        print(f"Type: {info.get('type', 'unknown')}")

        # For now, we'll skip actual image testing without a sample image
        print("\n✓ Vision model initialization test PASSED")
        print("(Full image analysis will be tested when processing real files)")

        # Cleanup
        model.cleanup()
        return True

    except Exception as e:
        print(f"\n✗ Vision model test FAILED: {e}")
        logger.exception("Test failed")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("File Organizer v2 - Model Tests")
    print("=" * 60)

    results = {}

    # Test text model
    results["text"] = test_text_model()

    # Test vision model
    results["vision"] = test_vision_model()

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for model_name, result in results.items():
        if result is True:
            status = "✓ PASSED"
        elif result is None:
            status = "⊘ SKIPPED"
        else:
            status = "✗ FAILED"
        print(f"{model_name.capitalize()} Model: {status}")

    passed = sum(1 for r in results.values() if r is True)
    total = len([r for r in results.values() if r is not None])

    print(f"\nTotal: {passed}/{total} tests passed")

    # Exit code
    if all(r is not False for r in results.values()):
        print("\n✓ All tests passed or skipped")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
