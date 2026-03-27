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
from file_organizer.models.audio_transcriber import AudioTranscriber, ModelSize, ComputeType

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

result = transcriber.transcribe_with_options("interview.wav", options)

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
organizer = AudioOrganizer(
    input_dir="~/Downloads",
    output_dir="~/Audio",
    enable_transcription=True
)
results = organizer.organize()
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
```
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
```
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

## Next Steps

- **Video Processing**: See the video section below for scene detection and keyframe extraction
- **Audio Classification**: Learn about automatic audio type detection (music, podcast, etc.)
- **Integration**: Combine transcription with organization workflows
- **Advanced**: Explore speaker diarization and custom model training

For more information, see:
- [User Guide](../USER_GUIDE.md) - General usage patterns
- [Dependencies](./dependencies.md) - Installation and requirements
- [API Reference](../api/audio.md) - Detailed API documentation
