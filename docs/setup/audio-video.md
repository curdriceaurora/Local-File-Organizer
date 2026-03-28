# Audio & Video Processing Guide

## Overview

File Organizer provides advanced audio and video processing capabilities for intelligent file organization. This guide covers:

- **Audio Transcription**: Speech-to-text using Faster-Whisper models
- **Audio Classification**: Automatic categorization (music, podcast, audiobook, etc.)
- **Audio Metadata**: ID3 tags, duration, bitrate, and quality analysis
- **Video Processing**: Scene detection and keyframe extraction (covered in separate section)

All features run **100% locally** with no cloud dependencies, preserving your privacy.

---

## Audio Transcription

### Overview

Audio transcription converts speech in audio files to text using state-of-the-art Whisper models via the faster-whisper library. This enables:

- **Content-based organization**: Organize by spoken content, not just filenames
- **Searchable audio**: Find audio files by what's said inside them
- **Classification accuracy**: Better categorization using transcribed content
- **Metadata extraction**: Extract speaker names, topics, and keywords

### System Requirements

| Component | Requirement | Notes |
|-----------|------------|-------|
| **Python** | 3.11+ | Required |
| **FFmpeg** | Latest | Required for audio processing |
| **RAM** | 4-8 GB | Depends on model size |
| **Storage** | 1-10 GB | For downloaded models |
| **GPU** | Optional | CUDA/ROCm for acceleration |

#### Installing FFmpeg

**macOS:**

```bash
brew install ffmpeg
```

**Ubuntu/Debian:**

```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use:

```powershell
choco install ffmpeg
```

### Installation

Install the audio processing dependencies:

```bash
# From your File Organizer directory
pip install -e ".[audio]"
```

This installs:
- `faster-whisper>=1.0.0` - Whisper transcription engine
- `torch>=2.1.0` - GPU acceleration support
- `mutagen>=1.47.0` - Audio metadata extraction
- `tinytag>=1.10.0` - Lightweight metadata fallback
- `pydub>=0.25.0` - Audio manipulation utilities

### Verify Installation

```bash
python -c "from faster_whisper import WhisperModel; print('✓ Audio transcription ready')"
```

If successful, you're ready to transcribe audio files.

### Model Sizes

Faster-Whisper supports multiple model sizes with different speed/accuracy tradeoffs:

| Model | Size | VRAM | Speed | Accuracy | Use Case |
|-------|------|------|-------|----------|----------|
| `tiny` | 75 MB | ~1 GB | Very Fast | Fair | Quick previews, low-resource systems |
| `base` | 150 MB | ~1 GB | Fast | Good | General use, balanced performance |
| `small` | 500 MB | ~2 GB | Moderate | Very Good | Recommended for most users |
| `medium` | 1.5 GB | ~5 GB | Slow | Excellent | High accuracy needs |
| `large-v2` | 3 GB | ~10 GB | Very Slow | Best | Maximum accuracy |
| `large-v3` | 3 GB | ~10 GB | Very Slow | Best | Latest Whisper version |

**Recommendation:** Start with `small` for a good balance of speed and accuracy.

### Compute Types

Control precision and performance with compute types:

| Type | Precision | Speed | VRAM | Supported Hardware |
|------|-----------|-------|------|-------------------|
| `float32` | Full | Slow | High | CPU, GPU |
| `float16` | Half | Fast | Medium | GPU only (CUDA, ROCm) |
| `int8` | 8-bit | Very Fast | Low | CPU, GPU |
| `int8_float16` | Mixed | Very Fast | Low | GPU only |

**GPU Users:** Use `float16` or `int8_float16` for best performance.
**CPU Users:** Use `int8` to reduce memory usage.

### Basic Usage

#### Programmatic API

```python
from pathlib import Path
from file_organizer.services.audio.transcriber import AudioTranscriber, ModelSize, ComputeType

# Initialize transcriber
transcriber = AudioTranscriber(
    model_size=ModelSize.SMALL,
    compute_type=ComputeType.FLOAT16,  # Use INT8 for CPU
    device="cuda"  # or "cpu"
)

# Transcribe audio file
audio_file = Path("~/Downloads/podcast-episode.mp3")
result = transcriber.transcribe(audio_file)

# Access results
print(f"Language: {result.language} ({result.language_confidence:.2%})")
print(f"Duration: {result.duration:.1f} seconds")
print(f"Text: {result.text}")

# Access segments with timestamps
for segment in result.segments:
    print(f"[{segment.start:.2f}s - {segment.end:.2f}s] {segment.text}")
```

#### Advanced Options

```python
from file_organizer.services.audio.transcriber import (
    AudioTranscriber,
    TranscriptionOptions,
    ModelSize,
    ComputeType
)

# Configure advanced options
options = TranscriptionOptions(
    language="en",  # Force English (None for auto-detect)
    word_timestamps=True,  # Enable word-level timestamps
    beam_size=5,  # Beam search size (higher = slower, more accurate)
    best_of=5,  # Number of candidates (higher = slower, more accurate)
    temperature=0.0,  # Sampling temperature (0 = deterministic)
    vad_filter=True,  # Voice Activity Detection (removes silence)
    initial_prompt="This is a technical podcast about AI and machine learning."
)

transcriber = AudioTranscriber(
    model_size=ModelSize.MEDIUM,
    compute_type=ComputeType.INT8_FLOAT16
)

result = transcriber.transcribe("interview.wav", options=options)

# Word-level timestamps
for segment in result.segments:
    if segment.words:
        for word in segment.words:
            print(f"{word.word} [{word.start:.2f}s] (confidence: {word.probability:.2%})")
```

### Language Support

Whisper supports 100+ languages with automatic detection:

**Auto-Detection (Recommended):**

```python
# Language is detected automatically
result = transcriber.transcribe("audio.mp3")
print(f"Detected: {result.language}")
```

**Manual Language Selection:**

```python
options = TranscriptionOptions(language="es")  # Spanish
result = transcriber.transcribe_with_options("audio.mp3", options)
```

**Supported Languages:**
- English (`en`), Spanish (`es`), French (`fr`), German (`de`)
- Mandarin (`zh`), Japanese (`ja`), Korean (`ko`)
- Arabic (`ar`), Russian (`ru`), Portuguese (`pt`)
- Italian (`it`), Dutch (`nl`), Polish (`pl`)
- And 90+ more...

### Supported Audio Formats

Audio transcription supports the following file formats:

| Format | Extension | Notes |
|--------|-----------|-------|
| **MP3** | `.mp3` | Most common, widely supported |
| **WAV** | `.wav` | Uncompressed, highest quality |
| **FLAC** | `.flac` | Lossless compression |
| **M4A** | `.m4a` | Apple/iTunes format |
| **Ogg Vorbis** | `.ogg` | Open-source format |

**Requirements**: FFmpeg must be installed for format conversion and preprocessing.

**Verification**: Check if a file is supported:

```python
from file_organizer.core.types import AUDIO_EXTENSIONS

file_path = "my-file.mp3"
is_supported = any(file_path.endswith(ext) for ext in AUDIO_EXTENSIONS)
print(f"Supported: {is_supported}")
```

### Performance Optimization

#### GPU Acceleration

**Check GPU Availability:**

```python
import torch

print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
```

**Optimize for GPU:**

```python
transcriber = AudioTranscriber(
    model_size=ModelSize.SMALL,
    compute_type=ComputeType.FLOAT16,  # GPU-optimized
    device="cuda",
    num_workers=4  # Parallel processing
)
```

#### CPU Optimization

**Optimize for CPU:**

```python
transcriber = AudioTranscriber(
    model_size=ModelSize.TINY,  # Smaller model
    compute_type=ComputeType.INT8,  # Quantized precision
    device="cpu",
    num_workers=1  # Limit workers to avoid thrashing
)
```

#### Batch Processing

Process multiple files efficiently:

```python
from pathlib import Path

audio_files = list(Path("~/Podcasts").glob("*.mp3"))

for audio_file in audio_files:
    try:
        result = transcriber.transcribe(audio_file)

        # Save transcription
        output_file = audio_file.with_suffix(".txt")
        output_file.write_text(result.text)

        print(f"✓ {audio_file.name}: {result.language} ({len(result.text)} chars)")
    except Exception as e:
        print(f"✗ {audio_file.name}: {e}")
```

### Integration with File Organization

#### Organize by Transcribed Content

```python
from file_organizer.services.audio.organizer import AudioOrganizer
from file_organizer.services.audio.classifier import AudioClassifier
from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

# Extract metadata
metadata_extractor = AudioMetadataExtractor()
metadata = metadata_extractor.extract("podcast.mp3")

# Transcribe audio
transcriber = AudioTranscriber(model_size=ModelSize.SMALL)
transcription = transcriber.transcribe("podcast.mp3")

# Classify audio type
classifier = AudioClassifier()
classification = classifier.classify(
    metadata=metadata,
    transcription=transcription
)

print(f"Type: {classification.audio_type}")
print(f"Confidence: {classification.confidence:.2%}")
print(f"Reasoning: {classification.reasoning}")

# Organize with AudioOrganizer
organizer = AudioOrganizer()
plan = organizer.preview_organization(
    files=[(Path("podcast.mp3"), classification.audio_type, metadata)],
    base_path=Path("~/Audio").expanduser(),
)
print(f"Planned moves: {len(plan.planned_moves)}")
```

### TUI Integration

View audio files and transcriptions in the Terminal UI:

```bash
file-organizer tui
```

**Press `5` to access the Audio view**, which displays:
- Discovered audio files in current directory
- Metadata (title, artist, album, duration, bitrate)
- Classification results (music, podcast, audiobook, etc.)
- Transcription preview (if available)

### Troubleshooting

#### "FFmpeg not found"

**Error:**

```text
FileNotFoundError: FFmpeg not found
```

**Solution:**

```bash
# Verify FFmpeg installation
ffmpeg -version

# If not installed, see "Installing FFmpeg" section above
```

#### Out of Memory

**Error:**

```text
RuntimeError: CUDA out of memory
```

**Solutions:**

```python
# 1. Use smaller model
transcriber = AudioTranscriber(model_size=ModelSize.TINY)

# 2. Use quantized compute type
transcriber = AudioTranscriber(compute_type=ComputeType.INT8)

# 3. Switch to CPU
transcriber = AudioTranscriber(device="cpu")
```

#### Poor Transcription Quality

**Solutions:**
1. **Use larger model**: `medium` or `large-v3`
2. **Specify language**: `language="en"` instead of auto-detect
3. **Add context**: `initial_prompt="Technical discussion about..."`
4. **Enable VAD**: `vad_filter=True` to remove silence
5. **Increase beam size**: `beam_size=10` for better accuracy

### Best Practices

#### Model Selection

- **Quick previews**: `tiny` or `base`
- **General use**: `small` (recommended)
- **High accuracy**: `medium` or `large-v3`
- **Non-English**: `medium` or larger for best results

#### Compute Type Selection

- **GPU with 6+ GB VRAM**: `float16`
- **GPU with <6 GB VRAM**: `int8_float16`
- **CPU**: `int8`
- **Development/debugging**: `float32`

#### Processing Strategy

1. **Start small**: Test with `tiny` or `base` model first
2. **Validate quality**: Check a few transcriptions before batch processing
3. **Monitor resources**: Watch RAM/VRAM usage during processing
4. **Save incrementally**: Save results after each file in batch jobs
5. **Handle errors**: Wrap transcription calls in try/except blocks

### Configuration

Configure transcription settings in `~/.config/file-organizer/config.yaml`:

```yaml
audio:
  transcription:
    enabled: true
    model_size: small
    compute_type: float16
    device: cuda  # or cpu
    language: null  # null for auto-detect
    word_timestamps: false
    vad_filter: true
    beam_size: 5
    best_of: 5
    temperature: 0.0
```

---

---

## Video Analysis

### Overview

Video analysis provides advanced scene detection and metadata extraction capabilities for intelligent video file organization. This enables:

- **Scene Detection**: Automatically detect scene changes and transitions
- **Keyframe Extraction**: Extract representative frames from each scene
- **Content-based Organization**: Organize videos by visual content, not just filenames
- **Metadata Extraction**: Resolution, codec, duration, bitrate, and creation date
- **Screen Recording Detection**: Identify and categorize screen recordings

All features run **100% locally** using OpenCV and PySceneDetect with no cloud dependencies.

### System Requirements

| Component | Requirement | Notes |
|-----------|------------|-------|
| **Python** | 3.11+ | Required |
| **OpenCV** | 4.8.0+ | Core video processing |
| **FFmpeg** | Latest | Metadata extraction (optional) |
| **RAM** | 2-4 GB | Depends on video resolution |
| **Storage** | Minimal | No models to download |

#### Installing FFmpeg (Optional)

FFmpeg is optional but recommended for richer metadata extraction.

**macOS:**

```bash
brew install ffmpeg
```

**Ubuntu/Debian:**

```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use:

```powershell
choco install ffmpeg
```

### Installation

Install the video processing dependencies:

```bash
# From your File Organizer directory
pip install -e ".[video]"
```

This installs:
- `opencv-python>=4.8.0` - Video frame processing and analysis
- `scenedetect[opencv]>=0.6.0` - Advanced scene detection algorithms

### Verify Installation

```bash
python -c "import cv2; import scenedetect; print('✓ Video analysis ready')"
```

If successful, you're ready to analyze video files.

### Detection Methods

PySceneDetect supports multiple scene detection algorithms with different characteristics:

| Method | Algorithm | Speed | Accuracy | Use Case |
|--------|-----------|-------|----------|----------|
| `content` | Content-aware analysis | Moderate | Excellent | General use (recommended) |
| `threshold` | Simple pixel difference | Fast | Good | Quick previews, low-resource systems |
| `adaptive` | Adaptive threshold | Slow | Very Good | Variable lighting, complex scenes |
| `histogram` | Color histogram comparison | Moderate | Very Good | Color-based transitions |

**Recommendation:** Start with `content` for best balance of speed and accuracy.

### Detection Thresholds

Control sensitivity with threshold parameters:

| Threshold | Sensitivity | Scene Count | Use Case |
|-----------|-------------|-------------|----------|
| `15.0` | Very High | Many scenes | Subtle transitions, slow-paced content |
| `27.0` | High | Moderate | **Default - recommended for most videos** |
| `40.0` | Medium | Fewer scenes | Action videos, music videos |
| `60.0` | Low | Minimal scenes | Only major scene changes |

**Lower threshold = more sensitive = more scenes detected**

### Basic Usage

#### Programmatic API

```python
from pathlib import Path
from file_organizer.services.video.scene_detector import SceneDetector, DetectionMethod

# Initialize detector
detector = SceneDetector(
    method=DetectionMethod.CONTENT,
    threshold=27.0,
    min_scene_length=1.0  # seconds
)

# Detect scenes in video
video_file = Path("~/Videos/movie.mp4")
result = detector.detect_scenes(video_file)

# Access results
print(f"Video: {result.video_path.name}")
print(f"Duration: {result.total_duration:.1f} seconds")
print(f"FPS: {result.fps:.2f}")
print(f"Detected {len(result.scenes)} scenes")

# Access individual scenes
for scene in result.scenes:
    print(f"Scene {scene.scene_number}: {scene.start_time:.2f}s - {scene.end_time:.2f}s "
          f"({scene.duration:.2f}s, {scene.frame_count} frames)")
```

#### Advanced Options

```python
from file_organizer.services.video.scene_detector import SceneDetector, DetectionMethod

# High-sensitivity detection for subtle transitions
detector = SceneDetector(
    method=DetectionMethod.ADAPTIVE,
    threshold=15.0,  # Lower = more sensitive
    min_scene_length=0.5  # Allow shorter scenes
)

result = detector.detect_scenes("interview.mp4")

# Override method/threshold per video
result = detector.detect_scenes(
    "action-movie.mp4",
    method=DetectionMethod.CONTENT,
    threshold=40.0  # Less sensitive for fast-paced content
)
```

#### Extract Scene Thumbnails

```python
from pathlib import Path
from file_organizer.services.video.scene_detector import SceneDetector

detector = SceneDetector()
result = detector.detect_scenes("video.mp4")

# Extract thumbnail for each scene
output_dir = Path("~/Videos/thumbnails")
SceneDetector.extract_scene_thumbnails(
    video_path="video.mp4",
    result=result,
    output_dir=output_dir,
    frame_offset=0.5  # Extract frame 0.5s into each scene
)

print(f"Saved {len(result.scenes)} thumbnails to {output_dir}")
```

#### Save Scene List

```python
from file_organizer.services.video.scene_detector import SceneDetector

detector = SceneDetector()
result = detector.detect_scenes("video.mp4")

# Save scene list as CSV
SceneDetector.save_scene_list(result, "scenes.csv")

# CSV format:
# Scene,Start Time,End Time,Duration,Start Frame,End Frame,Frame Count,Score
# 1,0.00,5.23,5.23,0,157,157,0.850
# 2,5.23,12.45,7.22,157,373,216,0.920
```

### Video Metadata Extraction

#### Extract Metadata

```python
from pathlib import Path
from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

# Initialize extractor
extractor = VideoMetadataExtractor()

# Extract metadata
video_file = Path("~/Videos/movie.mp4")
metadata = extractor.extract(video_file)

# Access metadata
print(f"File: {metadata.file_path.name}")
print(f"Size: {metadata.file_size / 1024 / 1024:.1f} MB")
print(f"Format: {metadata.format}")
print(f"Duration: {metadata.duration:.1f} seconds")
print(f"Resolution: {metadata.width}x{metadata.height}")
print(f"FPS: {metadata.fps:.2f}")
print(f"Codec: {metadata.codec}")
print(f"Bitrate: {metadata.bitrate / 1000:.0f} kbps")
```

#### Resolution Classification

```python
from file_organizer.services.video.metadata_extractor import resolution_label

# Classify resolution
label = resolution_label(1920, 1080)
print(label)  # "1080p"

label = resolution_label(3840, 2160)
print(label)  # "4k"

label = resolution_label(1280, 720)
print(label)  # "720p"
```

### Batch Processing

Process multiple videos efficiently:

```python
from pathlib import Path
from file_organizer.services.video.scene_detector import SceneDetector

detector = SceneDetector()
video_files = list(Path("~/Videos").glob("*.mp4"))

# Batch detect scenes
results = detector.detect_scenes_batch(video_files)

# Process results
for result in results:
    print(f"{result.video_path.name}: {len(result.scenes)} scenes")

    # Save scene list for each video
    output_csv = result.video_path.with_suffix(".scenes.csv")
    SceneDetector.save_scene_list(result, output_csv)
```

### Supported Video Formats

#### Core Formats (Recognized by File Organizer)

These formats are explicitly supported by File Organizer's VIDEO_EXTENSIONS:

| Format | Extension | Notes |
|--------|-----------|-------|
| **MP4** | `.mp4` | Most common, recommended |
| **MKV** | `.mkv` | High-quality container |
| **AVI** | `.avi` | Legacy Windows format |
| **MOV** | `.mov` | QuickTime format |
| **WMV** | `.wmv` | Windows Media Video |

**Verification**: Check if a file is recognized:

```python
from file_organizer.core.types import VIDEO_EXTENSIONS

file_path = "my-video.mp4"
is_recognized = any(file_path.endswith(ext) for ext in VIDEO_EXTENSIONS)
print(f"Recognized: {is_recognized}")
```

#### Additional Formats (OpenCV/FFmpeg Runtime Support)

Depending on your OpenCV and FFmpeg installation, these formats may also work for scene detection:
- **WebM** (`.webm`) - Web-optimized format
- **FLV** (`.flv`) - Flash video
- **MPEG** (`.mpeg`, `.mpg`) - MPEG-1/2 format
- **M4V** (`.m4v`) - iTunes video format
- **3GP** (`.3gp`) - Mobile video format

**Note**: Additional formats may work for scene detection via OpenCV, but are not recognized by File Organizer's file organization logic (filtering, categorization). For best compatibility, use core formats.

### Integration with File Organization

#### Organize by Scene Count

```python
from pathlib import Path
from file_organizer.services.video.organizer import VideoOrganizer
from file_organizer.services.video.scene_detector import SceneDetector
from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

# Extract metadata
metadata_extractor = VideoMetadataExtractor()
metadata = metadata_extractor.extract("video.mp4")

# Detect scenes
detector = SceneDetector()
scene_result = detector.detect_scenes("video.mp4")

# Organize based on video characteristics
if len(scene_result.scenes) > 50:
    category = "long-form"
elif scene_result.total_duration < 60:
    category = "short-clips"
else:
    category = "standard"

print(f"Category: {category}")
print(f"Scenes: {len(scene_result.scenes)}")
print(f"Duration: {scene_result.total_duration:.1f}s")
```

#### Screen Recording Detection

```python
from file_organizer.services.video.organizer import is_screen_recording

# Detect screen recordings by filename
if is_screen_recording("Screen Recording 2025-01-15 at 3.45.22 PM.mp4"):
    print("macOS QuickTime screen recording detected")

if is_screen_recording("2025-01-15 14-05-32.mp4"):
    print("OBS Studio recording detected")

# Supports patterns from:
# - macOS QuickTime
# - Windows Snipping Tool
# - OBS Studio
# - Xbox Game Bar
# - Camtasia
```

### Troubleshooting

#### "OpenCV not found"

**Error:**

```text
ImportError: No module named 'cv2'
```

**Solution:**

```bash
# Verify installation
python -c "import cv2; print(cv2.__version__)"

# If not installed
pip install opencv-python>=4.8.0
```

#### "scenedetect not found"

**Error:**

```text
ImportError: No module named 'scenedetect'
```

**Solution:**

```bash
pip install scenedetect[opencv]>=0.6.0
```

#### Platform-Specific OpenCV Issues

**macOS - Conflicting Installations:**

```bash
# Remove brew version if conflicts occur
brew uninstall opencv

# Use pip version only
pip install opencv-python
```

**Linux - Missing System Libraries:**

```bash
# Ubuntu/Debian
sudo apt install libgl1-mesa-glx libglib2.0-0

# Fedora/RHEL
sudo dnf install mesa-libGL glib2
```

**Windows - Binary Compatibility:**

```bash
# Use prebuilt binaries
pip install opencv-python

# Avoid building from source unless necessary
```

#### Failed to Open Video

**Error:**

```text
ValueError: Failed to open video: video.mp4
```

**Solutions:**
1. **Check file exists**: Verify path is correct
2. **Check format support**: Try with `.mp4` file first
3. **Install FFmpeg**: Some codecs require FFmpeg
4. **Test with OpenCV**:

   ```python
   import cv2
   cap = cv2.VideoCapture("video.mp4")
   print(f"Opened: {cap.isOpened()}")
   cap.release()
   ```

#### Too Many/Few Scenes Detected

**Solutions:**

**Too many scenes:**

```python
# Increase threshold (less sensitive)
detector = SceneDetector(threshold=40.0)

# Increase minimum scene length
detector = SceneDetector(min_scene_length=2.0)  # 2 seconds minimum
```

**Too few scenes:**

```python
# Decrease threshold (more sensitive)
detector = SceneDetector(threshold=15.0)

# Try different detection method
detector = SceneDetector(method=DetectionMethod.ADAPTIVE)
```

### Best Practices

#### Detection Method Selection

- **General videos**: `content` method (recommended)
- **Fast previews**: `threshold` method
- **Variable lighting**: `adaptive` method
- **Color-based transitions**: `histogram` method

#### Threshold Selection

- **Subtle transitions** (interviews, documentaries): `15.0 - 20.0`
- **General content** (movies, TV shows): `27.0` (default)
- **Fast-paced** (action, music videos): `40.0 - 50.0`
- **Major changes only**: `60.0+`

#### Processing Strategy

1. **Start with defaults**: Test with `content` method and threshold `27.0`
2. **Validate on sample**: Check scene detection quality on representative video
3. **Adjust parameters**: Tune threshold based on content type
4. **Batch process**: Use `detect_scenes_batch()` for multiple files
5. **Save results**: Export scene lists to CSV for review
6. **Extract thumbnails**: Visual verification of scene boundaries

### Performance Optimization

#### Fast Processing

```python
# Use threshold method for speed
detector = SceneDetector(
    method=DetectionMethod.THRESHOLD,
    threshold=30.0
)

# Skip scene extraction, metadata only
from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor
extractor = VideoMetadataExtractor()
metadata = extractor.extract("video.mp4")  # Much faster than scene detection
```

#### High-Quality Processing

```python
# Use adaptive method for accuracy
detector = SceneDetector(
    method=DetectionMethod.ADAPTIVE,
    min_scene_length=0.5  # Detect shorter scenes
)

# Extract high-resolution thumbnails
SceneDetector.extract_scene_thumbnails(
    video_path="video.mp4",
    result=result,
    output_dir="thumbnails",
    frame_offset=1.0  # Use frame 1s into scene
)
```

### Configuration

Configure video analysis settings in `~/.config/file-organizer/config.yaml`:

```yaml
video:
  scene_detection:
    enabled: true
    method: content  # content, threshold, adaptive, histogram
    threshold: 27.0
    min_scene_length: 1.0
  metadata:
    use_ffprobe: true  # Prefer ffprobe over OpenCV
    extract_thumbnails: false
  organization:
    detect_screen_recordings: true
    short_clip_threshold: 60.0  # seconds
```

---

## Verification

This section provides comprehensive tests to verify your audio and video processing setup is working correctly.

### System Dependencies

Verify all required system dependencies are installed:

```bash
# Check Python version (requires 3.11+)
python3 --version

# Check FFmpeg installation
ffmpeg -version

# Check pip installation
pip --version
```

**Expected Output:**
- Python 3.11.0 or higher
- FFmpeg version information (any recent version)
- pip 23.0 or higher

### Audio Processing Verification

#### 1. Verify Audio Dependencies

```bash
# Test faster-whisper installation
python -c "from faster_whisper import WhisperModel; print('✓ faster-whisper installed')"

# Test torch installation
python -c "import torch; print(f'✓ PyTorch {torch.__version__} installed')"

# Test audio metadata libraries
python -c "import mutagen; import tinytag; print('✓ Audio metadata libraries installed')"

# Check GPU availability (if applicable)
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

**Expected Output:**

```
✓ faster-whisper installed
✓ PyTorch 2.1.0+ installed
✓ Audio metadata libraries installed
CUDA available: True  # or False if no GPU
```

#### 2. Test Audio Transcription

Create a test script to verify transcription works:

```bash
# Create test script
cat > test_audio.py << 'EOF'
from file_organizer.services.audio.transcriber import AudioTranscriber, ModelSize, ComputeType
from pathlib import Path
import sys

try:
    # Initialize with smallest model for quick test
    print("Initializing transcriber...")
    transcriber = AudioTranscriber(
        model_size=ModelSize.TINY,
        compute_type=ComputeType.INT8,
        device="cpu"
    )
    print("✓ Transcriber initialized successfully")

    # Test with a sample file if provided
    if len(sys.argv) > 1:
        audio_file = Path(sys.argv[1])
        if audio_file.exists():
            print(f"Transcribing {audio_file.name}...")
            result = transcriber.transcribe(audio_file)
            print(f"✓ Transcription completed")
            print(f"  Language: {result.language}")
            print(f"  Duration: {result.duration:.1f}s")
            print(f"  Text preview: {result.text[:100]}...")
        else:
            print(f"✗ File not found: {audio_file}")
            sys.exit(1)
    else:
        print("✓ Ready to transcribe (pass audio file path as argument)")

except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
EOF

# Run test (without audio file)
python test_audio.py

# Or test with your own audio file
# python test_audio.py ~/path/to/your/audio.mp3
```

**Expected Output:**

```
Initializing transcriber...
✓ Transcriber initialized successfully
✓ Ready to transcribe (pass audio file path as argument)
```

#### 3. Test Audio Metadata Extraction

```bash
# Create metadata test script
cat > test_audio_metadata.py << 'EOF'
from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor
from pathlib import Path
import sys

if len(sys.argv) < 2:
    print("Usage: python test_audio_metadata.py <audio_file>")
    print("Note: Metadata extraction requires an actual audio file")
    sys.exit(0)

try:
    extractor = AudioMetadataExtractor()
    audio_file = Path(sys.argv[1])

    print(f"Extracting metadata from {audio_file.name}...")
    metadata = extractor.extract(audio_file)

    print("✓ Metadata extraction successful")
    print(f"  Title: {metadata.title or 'N/A'}")
    print(f"  Artist: {metadata.artist or 'N/A'}")
    print(f"  Duration: {metadata.duration:.1f}s")
    print(f"  Bitrate: {metadata.bitrate / 1000:.0f} kbps")
    print(f"  Format: {metadata.format}")

except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
EOF

# This requires an actual audio file to test
echo "✓ Metadata test script created (run with: python test_audio_metadata.py <audio_file>)"
```

### Video Processing Verification

#### 1. Verify Video Dependencies

```bash
# Test OpenCV installation
python -c "import cv2; print(f'✓ OpenCV {cv2.__version__} installed')"

# Test PySceneDetect installation
python -c "import scenedetect; print(f'✓ PySceneDetect {scenedetect.__version__} installed')"

# Test video capture capability
python -c "import cv2; cap = cv2.VideoCapture(); print('✓ Video capture available')"
```

**Expected Output:**

```
✓ OpenCV 4.8.0+ installed
✓ PySceneDetect 0.6.0+ installed
✓ Video capture available
```

#### 2. Test Video Scene Detection

Create a test script to verify scene detection works:

```bash
# Create test script
cat > test_video.py << 'EOF'
from file_organizer.services.video.scene_detector import SceneDetector, DetectionMethod
from pathlib import Path
import sys

try:
    # Initialize detector
    print("Initializing scene detector...")
    detector = SceneDetector(
        method=DetectionMethod.CONTENT,
        threshold=27.0
    )
    print("✓ Scene detector initialized successfully")

    # Test with a sample file if provided
    if len(sys.argv) > 1:
        video_file = Path(sys.argv[1])
        if video_file.exists():
            print(f"Detecting scenes in {video_file.name}...")
            result = detector.detect_scenes(video_file)
            print(f"✓ Scene detection completed")
            print(f"  Duration: {result.total_duration:.1f}s")
            print(f"  FPS: {result.fps:.2f}")
            print(f"  Scenes detected: {len(result.scenes)}")
            if result.scenes:
                print(f"  First scene: {result.scenes[0].start_time:.2f}s - {result.scenes[0].end_time:.2f}s")
        else:
            print(f"✗ File not found: {video_file}")
            sys.exit(1)
    else:
        print("✓ Ready to detect scenes (pass video file path as argument)")

except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
EOF

# Run test (without video file)
python test_video.py

# Or test with your own video file
# python test_video.py ~/path/to/your/video.mp4
```

**Expected Output:**

```
Initializing scene detector...
✓ Scene detector initialized successfully
✓ Ready to detect scenes (pass video file path as argument)
```

#### 3. Test Video Metadata Extraction

```bash
# Create metadata test script
cat > test_video_metadata.py << 'EOF'
from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor, resolution_label
from pathlib import Path
import sys

if len(sys.argv) < 2:
    print("Usage: python test_video_metadata.py <video_file>")
    print("Note: Metadata extraction requires an actual video file")
    sys.exit(0)

try:
    extractor = VideoMetadataExtractor()
    video_file = Path(sys.argv[1])

    print(f"Extracting metadata from {video_file.name}...")
    metadata = extractor.extract(video_file)

    print("✓ Metadata extraction successful")
    print(f"  Size: {metadata.file_size / 1024 / 1024:.1f} MB")
    print(f"  Format: {metadata.format}")
    print(f"  Duration: {metadata.duration:.1f}s")
    print(f"  Resolution: {metadata.width}x{metadata.height} ({resolution_label(metadata.width, metadata.height)})")
    print(f"  FPS: {metadata.fps:.2f}")
    print(f"  Codec: {metadata.codec}")
    print(f"  Bitrate: {metadata.bitrate / 1000:.0f} kbps")

except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
EOF

# This requires an actual video file to test
echo "✓ Metadata test script created (run with: python test_video_metadata.py <video_file>)"
```

### Integration Verification

Test the complete audio/video processing pipeline:

```bash
# Create integration test script
cat > test_integration.py << 'EOF'
import sys
from pathlib import Path

def test_audio_video_integration():
    """Test that audio and video processing can be imported together"""
    try:
        # Import audio components
        from file_organizer.services.audio.transcriber import AudioTranscriber
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor
        print("✓ Audio processing modules imported")

        # Import video components
        from file_organizer.services.video.scene_detector import SceneDetector
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor
        print("✓ Video processing modules imported")

        # Test initialization
        audio_transcriber = AudioTranscriber()
        audio_metadata = AudioMetadataExtractor()
        video_detector = SceneDetector()
        video_metadata = VideoMetadataExtractor()
        print("✓ All processors initialized successfully")

        print("\n✓ Integration test PASSED")
        print("  Audio and video processing are ready to use")
        return True

    except Exception as e:
        print(f"\n✗ Integration test FAILED: {e}")
        return False

if __name__ == "__main__":
    success = test_audio_video_integration()
    sys.exit(0 if success else 1)
EOF

# Run integration test
python test_integration.py
```

**Expected Output:**

```
✓ Audio processing modules imported
✓ Video processing modules imported
✓ All processors initialized successfully

✓ Integration test PASSED
  Audio and video processing are ready to use
```

### Quick Verification Command

Run all basic checks at once:

```bash
# One-line verification
python -c "
import sys
try:
    from faster_whisper import WhisperModel
    import torch, cv2, scenedetect
    from file_organizer.services.audio.transcriber import AudioTranscriber
    from file_organizer.services.video.scene_detector import SceneDetector
    print('✓ All audio/video dependencies installed')
    print(f'  - PyTorch: {torch.__version__}')
    print(f'  - OpenCV: {cv2.__version__}')
    print(f'  - PySceneDetect: {scenedetect.__version__}')
    print(f'  - CUDA: {torch.cuda.is_available()}')
except ImportError as e:
    print(f'✗ Missing dependency: {e}')
    sys.exit(1)
"
```

**Expected Output:**

```
✓ All audio/video dependencies installed
  - PyTorch: 2.1.0+
  - OpenCV: 4.8.0+
  - PySceneDetect: 0.6.0+
  - CUDA: True/False
```

### Troubleshooting Verification Issues

If any verification step fails, refer to the troubleshooting sections in the Audio Transcription and Video Analysis sections above, or check:

1. **Import errors**: Reinstall dependencies with `pip install -e ".[audio]"` or `pip install -e ".[video]"`
2. **FFmpeg not found**: Install FFmpeg following instructions in the respective sections
3. **CUDA errors**: Update GPU drivers or use CPU mode
4. **File not found**: Ensure file paths are correct and files exist
5. **Permission errors**: Check file/directory permissions

### Cleanup Test Scripts

After verification, remove test scripts:

```bash
rm -f test_audio.py test_audio_metadata.py test_video.py test_video_metadata.py test_integration.py
```

---

## Next Steps

- **Audio Transcription**: See the audio section above for speech-to-text capabilities
- **Audio Classification**: Learn about automatic audio type detection (music, podcast, etc.)
- **Integration**: Combine audio and video analysis in organization workflows
- **Advanced**: Explore custom scene detection algorithms and ML-based classification

For more information, see:
- [User Guide](../USER_GUIDE.md) - General usage patterns
- [Dependencies](./dependencies.md) - Installation and requirements
- [Audio and Video Setup](./audio-video.md) - This guide
