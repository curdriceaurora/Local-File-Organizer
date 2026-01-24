#!/usr/bin/env python3
"""Test script for AudioModel with faster-whisper."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from file_organizer.models.audio_model import AudioModel
from file_organizer.models.base import DeviceType
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")


def create_test_audio():
    """Create a simple test audio file using pyttsx3 or return None."""
    try:
        import pyttsx3
        import tempfile

        engine = pyttsx3.init()
        temp_file = Path(tempfile.gettempdir()) / "test_audio.wav"

        # Create a simple test audio
        engine.save_to_file(
            "This is a test audio file for the audio model. "
            "It demonstrates speech to text transcription.",
            str(temp_file)
        )
        engine.runAndWait()

        if temp_file.exists():
            print(f"✓ Created test audio: {temp_file}")
            return str(temp_file)
    except ImportError:
        print("⚠ pyttsx3 not available, cannot create test audio")
    except Exception as e:
        print(f"⚠ Could not create test audio: {e}")

    return None


def test_audio_model(audio_path: str = None):
    """Test audio model with sample audio file.

    Args:
        audio_path: Path to audio file. If None, will try to create one.
    """
    print("\n" + "=" * 60)
    print("Testing Audio Model (faster-whisper)")
    print("=" * 60)

    try:
        # If no audio provided, try to create one
        if audio_path is None:
            audio_path = create_test_audio()
            if audio_path is None:
                print("\n⚠ No test audio available")
                print("To test audio transcription:")
                print("  python scripts/test_audio_model.py /path/to/audio.mp3")
                print("\nSkipping full transcription test...")
                # Still test model initialization
                return test_initialization_only()

        # Verify file exists
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        print(f"\nAudio file: {audio_file.name}")
        print(f"Size: {audio_file.stat().st_size / 1024:.2f} KB")

        # Create config
        config = AudioModel.get_default_config(
            model_name="base",  # Small model for testing
            device=DeviceType.AUTO
        )
        print(f"\nModel: {config.name}")
        print(f"Framework: {config.framework}")
        print(f"Device: {config.device.value}")

        # Initialize model
        print("\nInitializing model...")
        print("(First run will download the model, this may take a moment)")
        model = AudioModel(config)

        with model:
            # Test basic transcription
            print("\nTranscribing audio...")
            transcription = model.generate(audio_path)

            print("\nTranscription:")
            print("-" * 60)
            print(transcription)
            print("-" * 60)

            # Test transcription with timestamps
            print("\nTranscribing with timestamps...")
            result = model.transcribe_with_timestamps(audio_path)

            print(f"\nDetected language: {result['language']}")
            print(f"Duration: {result['duration']:.2f}s")
            print(f"Segments: {len(result['segments'])}")

            if result['segments']:
                print("\nFirst segment:")
                seg = result['segments'][0]
                print(f"  [{seg['start']:.2f}s - {seg['end']:.2f}s]: {seg['text']}")

        print("\n✓ Audio model test PASSED")
        return True

    except ImportError as e:
        print(f"\n✗ Import error: {e}")
        print("\nTo install faster-whisper:")
        print("  pip install faster-whisper")
        return False

    except Exception as e:
        print(f"\n✗ Audio model test FAILED: {e}")
        logger.exception("Test failed")
        return False


def test_initialization_only():
    """Test only model initialization without transcription."""
    print("\n" + "=" * 60)
    print("Testing Audio Model Initialization Only")
    print("=" * 60)

    try:
        # Create config
        config = AudioModel.get_default_config(
            model_name="base",
            device=DeviceType.AUTO
        )
        print(f"\nModel: {config.name}")
        print(f"Framework: {config.framework}")

        # Initialize model
        print("\nInitializing model...")
        print("(First run will download the model, this may take a moment)")
        model = AudioModel(config)
        model.initialize()

        print("\n✓ Model initialized successfully")

        # Cleanup
        model.cleanup()
        print("✓ Model cleanup successful")

        print("\n✓ Initialization test PASSED")
        return True

    except ImportError as e:
        print(f"\n✗ Import error: {e}")
        print("\nTo install faster-whisper:")
        print("  pip install faster-whisper")
        return False

    except Exception as e:
        print(f"\n✗ Initialization test FAILED: {e}")
        logger.exception("Test failed")
        return False


def main():
    """Run audio model tests."""
    print("\n" + "=" * 60)
    print("File Organizer v2 - Audio Model Test")
    print("=" * 60)

    # Check for audio file argument
    audio_path = None
    if len(sys.argv) > 1:
        audio_path = sys.argv[1]

    # Run test
    result = test_audio_model(audio_path)

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    if result:
        print("Audio Model: ✓ PASSED")
        print("\n✓ Test completed successfully")
        sys.exit(0)
    else:
        print("Audio Model: ✗ FAILED")
        print("\n✗ Test failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
