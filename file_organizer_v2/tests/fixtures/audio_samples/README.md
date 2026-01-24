# Audio Test Fixtures

## Overview

This directory contains fixtures for audio file testing. Tests use **in-memory synthetic fixtures** rather than real audio files to keep the repository lightweight.

## Testing Approach

### Synthetic Fixtures

Tests create temporary audio files using pytest's `tmp_path` fixture:

```python
@pytest.fixture
def temp_audio_file(tmp_path):
    """Create temporary audio file."""
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"fake audio data")
    return audio_file
```

### Mocked Audio Processing

Audio transcription and metadata extraction are mocked to avoid dependencies on actual audio processing libraries:

```python
@patch('file_organizer.models.audio_transcriber.WhisperModel')
def test_transcribe(mock_whisper):
    """Test with mocked Whisper model."""
    mock_whisper.return_value.transcribe.return_value = (
        [Mock(text="Hello", start=0.0, end=1.0)],
        {"language": "en"}
    )
```

## Supported Audio Formats

Tests cover the following audio formats:
- **MP3** (`.mp3`)
- **WAV** (`.wav`)
- **FLAC** (`.flac`)
- **M4A** (`.m4a`)
- **OGG** (`.ogg`)

## Adding Real Audio Samples (Optional)

If you want to test with real audio files:

1. Create audio samples (keep them small, < 100KB each)
2. Place them in this directory
3. Add `.gitignore` entry if they're too large
4. Update tests to use real files instead of synthetic ones

Example:
```python
AUDIO_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "audio_samples"

def test_with_real_audio():
    real_audio = AUDIO_FIXTURE_DIR / "sample.mp3"
    if real_audio.exists():
        # Test with real file
        pass
    else:
        pytest.skip("Real audio fixture not available")
```

## Phase 3 Status

Audio transcription is planned for Phase 3. Current tests serve as:
- Documentation of expected behavior
- Placeholders for future implementation
- Smoke tests to ensure modules load correctly

Most tests are marked with `@pytest.mark.skip(reason="Phase 3")` until implementation is complete.
