#!/usr/bin/env python3
"""Quick verification script for hardware detection screen."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from file_organizer.tui.setup_wizard_view import SetupWizardView, WizardScreen  # noqa: E402


def test_wizard_initialization():
    """Test wizard can be instantiated."""
    print("Testing wizard initialization...")
    wizard = SetupWizardView()
    assert wizard._current_screen == WizardScreen.WELCOME
    assert wizard._detection_status == "pending"
    assert wizard._detection_progress == 0
    assert wizard._detection_step == ""
    print("✓ Wizard initialization OK")


def test_progress_bar_rendering():
    """Test progress bar rendering."""
    print("\nTesting progress bar rendering...")
    wizard = SetupWizardView()

    # Test 0%
    bar_0 = wizard._render_progress_bar(0)
    assert len(bar_0) > 0
    print(f"  0%: {bar_0}")

    # Test 50%
    bar_50 = wizard._render_progress_bar(50)
    print(f"  50%: {bar_50}")

    # Test 100%
    bar_100 = wizard._render_progress_bar(100)
    print(f"  100%: {bar_100}")

    print("✓ Progress bar rendering OK")


def test_screen_rendering():
    """Test screen rendering for different states."""
    print("\nTesting screen rendering...")
    wizard = SetupWizardView()

    # Test welcome screen
    welcome = wizard._render_welcome_screen()
    assert "Welcome to File Organizer" in welcome
    assert "Quick Start" in welcome
    assert "Power User" in welcome
    print("✓ Welcome screen renders")

    # Test mode select screen
    mode_select = wizard._render_mode_select_screen()
    assert "Select Setup Mode" in mode_select
    print("✓ Mode select screen renders")

    # Test hardware detect screen - pending
    wizard._current_screen = WizardScreen.HARDWARE_DETECT
    detect_pending = wizard._render_hardware_detect_screen()
    assert "Hardware Detection" in detect_pending
    assert "Preparing to detect" in detect_pending
    print("✓ Hardware detect screen (pending) renders")

    # Test hardware detect screen - detecting
    wizard._detection_status = "detecting"
    wizard._detection_progress = 50
    wizard._detection_step = "Detecting RAM and CPU..."
    detect_in_progress = wizard._render_hardware_detect_screen()
    assert "50%" in detect_in_progress
    assert "Detecting RAM and CPU" in detect_in_progress
    assert "GPU detection complete" in detect_in_progress
    print("✓ Hardware detect screen (detecting) renders")

    # Test hardware detect screen - error
    wizard._detection_status = "error"
    wizard._detection_message = "Test error"
    detect_error = wizard._render_hardware_detect_screen()
    assert "Detection failed" in detect_error
    assert "Test error" in detect_error
    print("✓ Hardware detect screen (error) renders")


def test_detection_states():
    """Test detection status transitions."""
    print("\nTesting detection states...")
    wizard = SetupWizardView()

    # Initial state
    assert wizard._detection_status == "pending"
    assert wizard._detection_progress == 0

    # Simulate detection progress
    wizard._detection_status = "detecting"
    wizard._detection_progress = 33
    wizard._detection_step = "Detecting GPU..."
    screen = wizard._render_hardware_detect_screen()
    assert "33%" in screen
    assert "Detecting GPU" in screen

    wizard._detection_progress = 66
    wizard._detection_step = "Detecting RAM and CPU..."
    screen = wizard._render_hardware_detect_screen()
    assert "66%" in screen
    assert "RAM and CPU detection complete" in screen

    wizard._detection_progress = 100
    wizard._detection_step = "Detecting AI backend..."
    screen = wizard._render_hardware_detect_screen()
    assert "100%" in screen
    assert "Backend detection complete" in screen

    print("✓ Detection states work correctly")


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Hardware Detection Screen Verification")
    print("=" * 60)

    try:
        test_wizard_initialization()
        test_progress_bar_rendering()
        test_screen_rendering()
        test_detection_states()

        print("\n" + "=" * 60)
        print("✓ All verification tests passed!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
