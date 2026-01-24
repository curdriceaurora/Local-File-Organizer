# Video Test Fixtures

## Overview

This directory contains fixtures for video file testing. Tests use **in-memory synthetic fixtures** rather than real video files to keep the repository lightweight and fast.

## Testing Approach

### Synthetic Fixtures

Tests create temporary video files using pytest's `tmp_path` fixture:

```python
@pytest.fixture
def temp_video_file(tmp_path):
    """Create temporary video file."""
    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"fake video data")
    return video_file
```

### Mocked Video Processing

Video processing is mocked to avoid dependencies on actual video processing libraries (OpenCV, ffmpeg):

```python
@patch('cv2.VideoCapture')
def test_extract_frames(mock_video_capture):
    """Test with mocked OpenCV."""
    mock_cap = Mock()
    mock_cap.read.return_value = (True, np.zeros((480, 640, 3)))
    mock_video_capture.return_value = mock_cap
```

## Supported Video Formats

Tests cover the following video formats:
- **MP4** (`.mp4`)
- **AVI** (`.avi`)
- **MKV** (`.mkv`)
- **MOV** (`.mov`)
- **WMV** (`.wmv`)

## Video Processing Features Tested

### Frame Extraction
- Extract frames at regular intervals
- Extract key frames
- Extract frames from specific timestamps

### Scene Detection
- Detect scene changes
- Extract representative frames per scene
- Calculate scene boundaries

### Metadata Extraction
- Video resolution (width x height)
- Frame rate (FPS)
- Duration
- Codec information
- Bitrate

### Thumbnail Generation
- Generate thumbnails at key moments
- Resize and optimize thumbnails
- Multiple thumbnail sizes

## Adding Real Video Samples (Optional)

If you want to test with real video files:

1. Create small video samples (< 1MB each, 2-3 seconds duration)
2. Place them in this directory
3. Add to `.gitignore` if needed
4. Update tests to use real files

Example:
```python
VIDEO_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "video_samples"

def test_with_real_video():
    real_video = VIDEO_FIXTURE_DIR / "sample.mp4"
    if real_video.exists():
        processor = VisionProcessor()
        result = processor.process_file(real_video)
        assert result is not None
    else:
        pytest.skip("Real video fixture not available")
```

## Performance Considerations

Video processing can be computationally expensive. Tests are designed to:
- Use mocks for heavy operations
- Process minimal frames
- Skip tests requiring actual video processing
- Mark slow tests with `@pytest.mark.slow`

## Phase 3 Status

Advanced video processing is planned for Phase 3. Current tests serve as:
- Documentation of expected behavior
- Placeholders for future implementation
- Smoke tests to ensure modules load correctly

Most tests are marked with `@pytest.mark.skip(reason="Phase 3")` until:
- Multi-frame analysis is implemented
- Scene detection is complete
- Video transcription (audio track) is added
- Thumbnail generation is finalized
