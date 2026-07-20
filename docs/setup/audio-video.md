# Audio and Video Processing Guide

## Overview

File Organizer has audio and video processing tools. This guide explains these tools:

- **Audio Transcription**: Faster-Whisper models change speech to text.
- **Audio Classification**: The system categorizes files automatically.
- **Audio Metadata**: The system reads ID3 tags, duration, bitrate, and quality.
- **Video Processing**: The system detects scenes and extracts keyframes.

All tools operate locally. The system does not use cloud dependencies.

---

## Audio Transcription

### Overview

Audio transcription changes speech to text. The system uses Whisper models. This process gives you these abilities:

- **Content-based organization**: You can organize files by spoken content.
- **Searchable audio**: You can find audio files by their content.
- **Classification accuracy**: Transcribed content improves categorization.
- **Metadata extraction**: You can find speaker names, topics, and keywords.

### System Requirements

| Component | Requirement | Notes |
|-----------|------------|-------|
| **Python** | 3.11 or newer | Required |
| **FFmpeg** | Latest | Required |
| **RAM** | 4 to 8 GB | Depends on model size |
| **Storage** | 1 to 10 GB | For downloaded models |
| **GPU** | Optional | CUDA or ROCm for acceleration |

#### Install FFmpeg

**macOS:**

```bash
brew install ffmpeg
```

**Ubuntu or Debian:**

```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download the software from [ffmpeg.org](https://ffmpeg.org/download.html). You can also use this command:

```powershell
choco install ffmpeg
```

### Installation

Install the audio processing dependencies.

```bash
pip install -e ".[audio]"
```

This command installs these packages:
- `faster-whisper>=1.0.0`
- `torch>=2.1.0`
- `mutagen>=1.47.0`
- `tinytag>=1.10.0`
- `pydub>=0.25.0`

### Verify Installation

```bash
python -c "from faster_whisper import WhisperModel; print('✓ Audio transcription ready')"
```

### Model Sizes

Faster-Whisper has multiple model sizes.

| Model | Size | VRAM | Speed | Accuracy | Use Case |
|-------|------|------|-------|----------|----------|
| `tiny` | 75 MB | 1 GB | Very Fast | Fair | Quick previews |
| `base` | 150 MB | 1 GB | Fast | Good | General use |
| `small` | 500 MB | 2 GB | Moderate | Very Good | Recommended |
| `medium` | 1.5 GB | 5 GB | Slow | Excellent | High accuracy |
| `large-v2` | 3 GB | 10 GB | Very Slow | Best | Maximum accuracy |
| `large-v3` | 3 GB | 10 GB | Very Slow | Best | Latest version |

**Recommendation:** Use `small` for the best balance of speed and accuracy.

### Compute Types

| Type | Precision | Speed | VRAM | Supported Hardware |
|------|-----------|-------|------|-------------------|
| `float32` | Full | Slow | High | CPU, GPU |
| `float16` | Half | Fast | Medium | GPU only |
| `int8` | 8-bit | Very Fast | Low | CPU, GPU |
| `int8_float16` | Mixed | Very Fast | Low | GPU only |

**GPU Users:** Use `float16` or `int8_float16`.
**CPU Users:** Use `int8`.

### Basic Usage

#### CLI: Content-Aware Audio Organization

You can transcribe audio with the `organize` command. Use `--transcribe-audio`.

```bash
fo organize ~/Downloads ~/Organized --transcribe-audio

fo organize ~/Downloads ~/Organized --transcribe-audio --whisper-model small

fo organize ~/Downloads ~/Organized --transcribe-audio --max-transcribe-seconds 1800
```

Notes:

- You must install the `[audio]` extra.
- The system downloads model weights automatically.
- Transcription uses CUDA when available.

#### Programmatic API: AudioModel

`AudioModel` contains the transcription service.

```python
from file_organizer.models.audio_model import AudioModel

model = AudioModel(AudioModel.get_default_config("whisper:base"))
model.initialize()
try:
    result = model.transcribe("meeting.m4a")
    print(result.text, result.language)
    text = model.generate("meeting.m4a")
finally:
    model.safe_cleanup()
```

#### Programmatic API: AudioTranscriber

You can control the transcription service directly.

```python
from pathlib import Path
from file_organizer.services.audio.transcriber import AudioTranscriber, ModelSize, ComputeType

transcriber = AudioTranscriber(
    model_size=ModelSize.SMALL,
    compute_type=ComputeType.FLOAT16,
    device="cuda"
)

audio_file = Path("~/Downloads/podcast-episode.mp3")
result = transcriber.transcribe(audio_file)

print(f"Language: {result.language}")
print(f"Duration: {result.duration:.1f} seconds")
print(f"Text: {result.text}")

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

options = TranscriptionOptions(
    language="en",
    word_timestamps=True,
    beam_size=5,
    best_of=5,
    temperature=0.0,
    vad_filter=True,
    initial_prompt="This is a technical podcast."
)

transcriber = AudioTranscriber(
    model_size=ModelSize.MEDIUM,
    compute_type=ComputeType.INT8_FLOAT16
)

result = transcriber.transcribe("interview.wav", options=options)

for segment in result.segments:
    if segment.words:
        for word in segment.words:
            print(f"{word.word} [{word.start:.2f}s]")
```

### Language Support

Whisper supports more than 100 languages. It detects languages automatically.

**Auto-Detection (Recommended):**

```python
result = transcriber.transcribe("audio.mp3")
print(f"Detected: {result.language}")
```

**Manual Language Selection:**

```python
options = TranscriptionOptions(language="es")
result = transcriber.transcribe_with_options("audio.mp3", options)
```

### Supported Audio Formats

Audio transcription supports these file formats:

| Format | Extension | Notes |
|--------|-----------|-------|
| **MP3** | `.mp3` | Common format |
| **WAV** | `.wav` | Uncompressed format |
| **FLAC** | `.flac` | Lossless format |
| **M4A** | `.m4a` | Apple format |
| **Ogg** | `.ogg` | Open-source format |

**Requirements**: You must install FFmpeg.

**Verification**:

```python
from file_organizer.core.types import AUDIO_EXTENSIONS

file_path = "my-file.mp3"
is_supported = any(file_path.endswith(ext) for ext in AUDIO_EXTENSIONS)
print(f"Supported: {is_supported}")
```

### Performance Optimization

#### GPU Acceleration

**Examine GPU Availability:**

```python
import torch

print(f"CUDA available: {torch.cuda.is_available()}")
```

**Optimize for GPU:**

```python
transcriber = AudioTranscriber(
    model_size=ModelSize.SMALL,
    compute_type=ComputeType.FLOAT16,
    device="cuda",
    num_workers=4
)
```

#### CPU Optimization

**Optimize for CPU:**

```python
transcriber = AudioTranscriber(
    model_size=ModelSize.TINY,
    compute_type=ComputeType.INT8,
    device="cpu",
    num_workers=1
)
```

#### Batch Processing

Process multiple files.

```python
from pathlib import Path

audio_files = list(Path("~/Podcasts").glob("*.mp3"))

for audio_file in audio_files:
    try:
        result = transcriber.transcribe(audio_file)
        output_file = audio_file.with_suffix(".txt")
        output_file.write_text(result.text)
        print(f"✓ {audio_file.name}: {result.language}")
    except Exception as e:
        print(f"✗ {audio_file.name}: {e}")
```

### Integration with File Organization

#### Organize by Transcribed Content

```python
from file_organizer.services.audio.organizer import AudioOrganizer
from file_organizer.services.audio.classifier import AudioClassifier
from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

metadata_extractor = AudioMetadataExtractor()
metadata = metadata_extractor.extract("podcast.mp3")

transcriber = AudioTranscriber(model_size=ModelSize.SMALL)
transcription = transcriber.transcribe("podcast.mp3")

classifier = AudioClassifier()
classification = classifier.classify(
    metadata=metadata,
    transcription=transcription
)

print(f"Type: {classification.audio_type}")

organizer = AudioOrganizer()
plan = organizer.preview_organization(
    files=[(Path("podcast.mp3"), classification.audio_type, metadata)],
    base_path=Path("~/Audio").expanduser(),
)
print(f"Planned moves: {len(plan.planned_moves)}")
```

### TUI Integration

Open the Terminal UI to examine audio files.

```bash
file-organizer tui
```

**Press 5 to open the Audio view.**

### Troubleshooting

#### "FFmpeg not found"

**Solution:**

```bash
ffmpeg -version
```

If the system does not find FFmpeg, install it.

#### Out of Memory

**Error:**

```text
RuntimeError: CUDA out of memory
```

**Solutions:**

```python
transcriber = AudioTranscriber(model_size=ModelSize.TINY)
transcriber = AudioTranscriber(compute_type=ComputeType.INT8)
transcriber = AudioTranscriber(device="cpu")
```

#### Poor Transcription Quality

**Solutions:**
1. **Use larger model**: Select `medium` or `large-v3`.
2. **Specify language**: Select `language="en"`.
3. **Add context**: Write an `initial_prompt`.
4. **Enable VAD**: Select `vad_filter=True`.
5. **Increase beam size**: Select `beam_size=10`.

### Best Practices

#### Model Selection

- **Quick previews**: Select `tiny` or `base`.
- **General use**: Select `small`.
- **High accuracy**: Select `medium` or `large-v3`.
- **Non-English**: Select `medium` or a larger model.

#### Compute Type Selection

- **GPU with 6+ GB VRAM**: Select `float16`.
- **GPU with <6 GB VRAM**: Select `int8_float16`.
- **CPU**: Select `int8`.
- **Development**: Select `float32`.

#### Processing Strategy

1. **Start small**: Test the `tiny` or `base` model first.
2. **Validate quality**: Examine some transcriptions first.
3. **Monitor resources**: Monitor RAM and VRAM during processing.
4. **Save incrementally**: Save your results after each file.
5. **Handle errors**: Use try and except blocks.

### Configuration

Change your transcription settings in your profile `config.yaml`.

```yaml
audio:
  transcription:
    enabled: true
    model_size: small
    compute_type: float16
    device: cuda
    language: null
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

Video analysis provides tools to organize your video files. This process gives you these abilities:

- **Scene Detection**: The system detects scene changes.
- **Keyframe Extraction**: The system extracts frames from each scene.
- **Content-based Organization**: You can organize videos by visual content.
- **Metadata Extraction**: You can read resolution, codec, duration, bitrate, and creation date.
- **Screen Recording Detection**: The system identifies screen recordings.

All features operate locally with OpenCV and PySceneDetect. The system does not use cloud dependencies.

### System Requirements

| Component | Requirement | Notes |
|-----------|------------|-------|
| **Python** | 3.11 or newer | Required |
| **OpenCV** | 4.8.0 or newer | Required |
| **FFmpeg** | Latest | Recommended for metadata |
| **RAM** | 2 to 4 GB | Depends on video resolution |
| **Storage** | Minimal | No models to download |

#### Install FFmpeg (Optional)

FFmpeg is an optional component. We recommend FFmpeg for richer metadata extraction.

**macOS:**

```bash
brew install ffmpeg
```

**Ubuntu or Debian:**

```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download the software from [ffmpeg.org](https://ffmpeg.org/download.html). You can also use this command:

```powershell
choco install ffmpeg
```

### Installation

Install the video processing dependencies.

```bash
pip install -e ".[video]"
```

This command installs these packages:
- `opencv-python>=4.8.0`
- `scenedetect[opencv]>=0.6.0`

### Verify Installation

```bash
python -c "import cv2; import scenedetect; print('✓ Video analysis ready')"
```

### Detection Methods

PySceneDetect supports multiple scene detection algorithms.

| Method | Algorithm | Speed | Accuracy | Use Case |
|--------|-----------|-------|----------|----------|
| `content` | Content-aware analysis | Moderate | Excellent | General use |
| `threshold` | Simple pixel difference | Fast | Good | Quick previews |
| `adaptive` | Adaptive threshold | Slow | Very Good | Variable lighting |
| `histogram` | Color histogram comparison | Moderate | Very Good | Color-based transitions |

**Recommendation:** Select the `content` method for the best balance of speed and accuracy.

### Detection Thresholds

Control the detection sensitivity.

| Threshold | Sensitivity | Scene Count | Use Case |
|-----------|-------------|-------------|----------|
| `15.0` | Very High | Many scenes | Subtle transitions |
| `27.0` | High | Moderate | Default value |
| `40.0` | Medium | Fewer scenes | Action videos |
| `60.0` | Low | Minimal scenes | Major scene changes |

**Note:** A lower threshold detects more scenes.

### Basic Usage

#### Programmatic API

```python
from pathlib import Path
from file_organizer.services.video.scene_detector import SceneDetector, DetectionMethod

detector = SceneDetector(
    method=DetectionMethod.CONTENT,
    threshold=27.0,
    min_scene_length=1.0
)

video_file = Path("~/Videos/movie.mp4")
result = detector.detect_scenes(video_file)

print(f"Video: {result.video_path.name}")
print(f"Duration: {result.total_duration:.1f} seconds")
print(f"Detected {len(result.scenes)} scenes")

for scene in result.scenes:
    print(f"Scene {scene.scene_number}: {scene.start_time:.2f}s - {scene.end_time:.2f}s")
```

#### Advanced Options

```python
from file_organizer.services.video.scene_detector import SceneDetector, DetectionMethod

detector = SceneDetector(
    method=DetectionMethod.ADAPTIVE,
    threshold=15.0,
    min_scene_length=0.5
)

result = detector.detect_scenes("interview.mp4")
```

#### Extract Scene Thumbnails

```python
from pathlib import Path
from file_organizer.services.video.scene_detector import SceneDetector

detector = SceneDetector()
result = detector.detect_scenes("video.mp4")

output_dir = Path("~/Videos/thumbnails")
SceneDetector.extract_scene_thumbnails(
    video_path="video.mp4",
    result=result,
    output_dir=output_dir,
    frame_offset=0.5
)
```

#### Save Scene List

```python
from file_organizer.services.video.scene_detector import SceneDetector

detector = SceneDetector()
result = detector.detect_scenes("video.mp4")

SceneDetector.save_scene_list(result, "scenes.csv")
```

### Video Metadata Extraction

#### Extract Metadata

```python
from pathlib import Path
from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

extractor = VideoMetadataExtractor()
video_file = Path("~/Videos/movie.mp4")
metadata = extractor.extract(video_file)

print(f"File: {metadata.file_path.name}")
print(f"Format: {metadata.format}")
print(f"Duration: {metadata.duration:.1f} seconds")
print(f"Resolution: {metadata.width}x{metadata.height}")
```

#### Resolution Classification

```python
from file_organizer.services.video.metadata_extractor import resolution_label

label = resolution_label(1920, 1080)
print(label)

label = resolution_label(3840, 2160)
print(label)
```

### Batch Processing

Process multiple videos.

```python
from pathlib import Path
from file_organizer.services.video.scene_detector import SceneDetector

detector = SceneDetector()
video_files = list(Path("~/Videos").glob("*.mp4"))

results = detector.detect_scenes_batch(video_files)

for result in results:
    output_csv = result.video_path.with_suffix(".scenes.csv")
    SceneDetector.save_scene_list(result, output_csv)
```

### Supported Video Formats

#### Core Formats

File Organizer recognizes these formats:

| Format | Extension | Notes |
|--------|-----------|-------|
| **MP4** | `.mp4` | Recommended format |
| **MKV** | `.mkv` | High-quality container |
| **AVI** | `.avi` | Windows format |
| **MOV** | `.mov` | QuickTime format |
| **WMV** | `.wmv` | Windows Media Video |

#### Additional Formats

OpenCV and FFmpeg support these additional formats for scene detection:
- **WebM** (`.webm`)
- **FLV** (`.flv`)
- **MPEG** (`.mpeg`, `.mpg`)
- **M4V** (`.m4v`)
- **3GP** (`.3gp`)

### Integration with File Organization

#### Organize by Scene Count

```python
from pathlib import Path
from file_organizer.services.video.organizer import VideoOrganizer
from file_organizer.services.video.scene_detector import SceneDetector
from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

detector = SceneDetector()
scene_result = detector.detect_scenes("video.mp4")

if len(scene_result.scenes) > 50:
    category = "long-form"
elif scene_result.total_duration < 60:
    category = "short-clips"
else:
    category = "standard"

print(f"Category: {category}")
```

#### Screen Recording Detection

```python
from file_organizer.services.video.organizer import is_screen_recording

if is_screen_recording("Screen Recording 2025-01-15 at 3.45.22 PM.mp4"):
    print("Screen recording detected")
```

### Troubleshooting

#### "OpenCV not found"

**Solution:**

```bash
pip install opencv-python>=4.8.0
```

#### "scenedetect not found"

**Solution:**

```bash
pip install scenedetect[opencv]>=0.6.0
```

#### Failed to Open Video

**Solutions:**
1. **Check file exists**: Verify the path.
2. **Check format support**: Process an `.mp4` file first.
3. **Install FFmpeg**: Some video codecs need FFmpeg.

#### Too Many or Too Few Scenes Detected

**Solutions:**

**Too many scenes:**
Increase the threshold value. Increase the minimum scene length.

**Too few scenes:**
Decrease the threshold value. Change the detection method.

### Best Practices

#### Detection Method Selection

- **General videos**: Select `content`.
- **Fast previews**: Select `threshold`.
- **Variable lighting**: Select `adaptive`.
- **Color-based transitions**: Select `histogram`.

#### Threshold Selection

- **Subtle transitions**: Select `15.0 - 20.0`.
- **General content**: Select `27.0`.
- **Fast-paced videos**: Select `40.0 - 50.0`.
- **Major changes only**: Select `60.0`.

#### Processing Strategy

1. **Start with defaults**: Test the `content` method and threshold `27.0`.
2. **Validate on sample**: Examine the scene detection quality on one video.
3. **Adjust parameters**: Change the threshold value for your content.
4. **Batch process**: Use `detect_scenes_batch()` for multiple files.
5. **Save results**: Export your scene lists to a CSV file.
6. **Extract thumbnails**: Examine the scene boundaries visually.

### Performance Optimization

#### Fast Processing

```python
detector = SceneDetector(
    method=DetectionMethod.THRESHOLD,
    threshold=30.0
)

from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor
extractor = VideoMetadataExtractor()
metadata = extractor.extract("video.mp4")
```

#### High-Quality Processing

```python
detector = SceneDetector(
    method=DetectionMethod.ADAPTIVE,
    min_scene_length=0.5
)
```

### Configuration

Change your video analysis settings in your profile `config.yaml`.

```yaml
video:
  scene_detection:
    enabled: true
    method: content
    threshold: 27.0
    min_scene_length: 1.0
  metadata:
    use_ffprobe: true
    extract_thumbnails: false
  organization:
    detect_screen_recordings: true
    short_clip_threshold: 60.0
```

---

## Verification

This section has tests to verify your audio and video processing tools.

### System Dependencies

Verify all system dependencies.

```bash
python3 --version
ffmpeg -version
pip --version
```

### Audio Processing Verification

#### 1. Verify Audio Dependencies

```bash
python -c "from faster_whisper import WhisperModel; print('✓ faster-whisper installed')"
python -c "import torch; print('✓ PyTorch installed')"
python -c "import mutagen; import tinytag; print('✓ Audio metadata libraries installed')"
```

#### 2. Test Audio Transcription

Create a test script.

```bash
cat > test_audio.py << 'EOF'
from file_organizer.services.audio.transcriber import AudioTranscriber, ModelSize, ComputeType
from pathlib import Path
import sys

try:
    transcriber = AudioTranscriber(
        model_size=ModelSize.TINY,
        compute_type=ComputeType.INT8,
        device="cpu"
    )
    print("✓ Transcriber initialized successfully")
except Exception as e:
    print(f"✗ Error: {e}")
EOF

python test_audio.py
```

#### 3. Test Audio Metadata Extraction

Create a test script.

```bash
cat > test_audio_metadata.py << 'EOF'
from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor
from pathlib import Path
import sys

if len(sys.argv) < 2:
    print("Usage: python test_audio_metadata.py <audio_file>")
    sys.exit(0)

try:
    extractor = AudioMetadataExtractor()
    audio_file = Path(sys.argv[1])
    metadata = extractor.extract(audio_file)
    print("✓ Metadata extraction successful")
except Exception as e:
    print(f"✗ Error: {e}")
EOF
```

### Video Processing Verification

#### 1. Verify Video Dependencies

```bash
python -c "import cv2; print('✓ OpenCV installed')"
python -c "import scenedetect; print('✓ PySceneDetect installed')"
```

#### 2. Test Video Scene Detection

Create a test script.

```bash
cat > test_video.py << 'EOF'
from file_organizer.services.video.scene_detector import SceneDetector, DetectionMethod

try:
    detector = SceneDetector(
        method=DetectionMethod.CONTENT,
        threshold=27.0
    )
    print("✓ Scene detector initialized successfully")
except Exception as e:
    print(f"✗ Error: {e}")
EOF

python test_video.py
```

#### 3. Test Video Metadata Extraction

Create a test script.

```bash
cat > test_video_metadata.py << 'EOF'
from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor
from pathlib import Path
import sys

if len(sys.argv) < 2:
    print("Usage: python test_video_metadata.py <video_file>")
    sys.exit(0)

try:
    extractor = VideoMetadataExtractor()
    video_file = Path(sys.argv[1])
    metadata = extractor.extract(video_file)
    print("✓ Metadata extraction successful")
except Exception as e:
    print(f"✗ Error: {e}")
EOF
```

### Cleanup Test Scripts

Remove the test scripts.

```bash
rm -f test_audio.py test_audio_metadata.py test_video.py test_video_metadata.py test_integration.py
```

---

## Next Steps

- **Audio Transcription**: Read the audio section.
- **Audio Classification**: Learn about automatic audio type detection.
- **Integration**: Combine audio and video analysis.
- **Advanced**: Read about custom scene detection algorithms.

Read these documents for more information:
- [User Guide](../USER_GUIDE.md)
- [Dependencies](./dependencies.md)
- [AI Provider Setup](./ai-providers.md)
