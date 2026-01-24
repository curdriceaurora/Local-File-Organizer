---
name: integrate-distil-whisper-transcription-analysis
task: 42
title: Analysis - Integrate Distil-Whisper for audio transcription
created: 2026-01-21T12:51:28Z
updated: 2026-01-21T12:51:28Z
status: draft
---

# Task 42 Analysis: Integrate Distil-Whisper for Audio Transcription

## Overview

This task implements audio transcription capabilities using faster-whisper 1.0+, enabling the File Organizer system to process audio files (MP3, WAV, FLAC, M4A, OGG) and extract textual content with language detection and speaker identification.

## 1. Technical Requirements

### 1.1 Core Functionality
- **Audio Transcription Engine**: faster-whisper 1.0+ integration with model management
- **Multi-Format Support**: MP3, WAV, FLAC, M4A, OGG audio file handling
- **Language Detection**: Automatic detection with confidence scores (99+ languages)
- **Speaker Identification**: Diarization with speaker labels and timestamps
- **Timestamp Generation**: Word-level and segment-level timestamps
- **Performance Optimization**: GPU acceleration (CUDA/Metal) with CPU fallback

### 1.2 Quality Requirements
- Transcription accuracy: >90% for clear audio
- Language detection confidence: >85% threshold
- Processing speed: Real-time or faster for typical audio files
- Memory efficiency: Handle files up to 2 hours without OOM
- Error handling: Graceful degradation for corrupted/unsupported files

### 1.3 Integration Points
- Extends existing `BaseModel` architecture
- Follows `TextProcessor` service pattern
- Integrates with file reader utilities
- Supports async processing for large files

## 2. Architecture

### 2.1 Component Structure

```
file_organizer_v2/src/file_organizer/
├── models/
│   ├── audio_model.py          # (EXISTS - needs full implementation)
│   ├── audio_transcriber.py    # NEW: Core transcription engine
│   └── audio_preprocessor.py   # NEW: Format handling & preprocessing
├── services/
│   └── audio_processor.py      # NEW: High-level audio service
└── utils/
    ├── audio_utils.py          # NEW: Helper functions
    └── file_readers.py         # MODIFY: Add audio file reading
```

### 2.2 Class Design

#### AudioModel (Existing - Enhanced)
```python
class AudioModel(BaseModel):
    """Wrapper for faster-whisper with BaseModel interface"""
    - initialize() -> None
    - generate(audio_path: str, **kwargs) -> str
    - transcribe(audio_path: str, **options) -> TranscriptionResult
    - cleanup() -> None
```

#### AudioTranscriber (New)
```python
class AudioTranscriber:
    """Core transcription engine using faster-whisper"""
    - __init__(model_size, device, compute_type)
    - transcribe(audio_path, language, detect_speakers) -> TranscriptionResult
    - detect_language(audio_path) -> LanguageDetection
    - get_supported_formats() -> List[str]
    - _load_model() -> WhisperModel
    - _ensure_ffmpeg() -> bool
```

#### AudioPreprocessor (New)
```python
class AudioPreprocessor:
    """Handle audio format conversion and validation"""
    - validate_format(audio_path) -> bool
    - convert_to_wav(audio_path, target_path) -> Path
    - normalize_audio(audio_path) -> Path
    - extract_metadata(audio_path) -> AudioMetadata
    - check_duration(audio_path) -> float
```

#### AudioProcessor (New)
```python
class AudioProcessor:
    """High-level service for audio file processing"""
    - __init__(audio_model, config)
    - process_file(audio_path, options) -> ProcessedAudioFile
    - batch_process(audio_paths) -> List[ProcessedAudioFile]
    - _generate_description(transcription) -> str
    - _generate_folder_name(transcription) -> str
    - _generate_filename(transcription) -> str
```

#### Data Classes
```python
@dataclass
class TranscriptionResult:
    text: str
    language: str
    language_confidence: float
    segments: List[TranscriptionSegment]
    speakers: Optional[List[Speaker]]
    duration: float
    processing_time: float

@dataclass
class TranscriptionSegment:
    start: float
    end: float
    text: str
    confidence: float
    speaker: Optional[str]

@dataclass
class ProcessedAudioFile:
    file_path: Path
    transcription: TranscriptionResult
    description: str
    folder_name: str
    filename: str
    processing_time: float
    error: Optional[str]
```

### 2.3 Processing Pipeline

```
Input Audio File
    ↓
[Validate Format] → Check extension, duration, corruption
    ↓
[Preprocess] → Convert to compatible format if needed
    ↓
[Load Model] → Initialize faster-whisper (cached)
    ↓
[Detect Language] → Automatic language detection
    ↓
[Transcribe] → Generate text with timestamps
    ↓
[Speaker Diarization] → Identify speakers (optional)
    ↓
[Post-process] → Clean text, format output
    ↓
[Generate Metadata] → Description, folder, filename
    ↓
Output: ProcessedAudioFile
```

## 3. Dependencies

### 3.1 External Libraries

**Core Dependencies** (Add to pyproject.toml):
```toml
# Already in pyproject.toml but may need version update
faster-whisper = "^1.0.0"  # Current: >=0.10.0

# New dependencies
ffmpeg-python = "^0.2.0"      # Audio format conversion
pydub = "^0.25.1"             # Audio manipulation
soundfile = "^0.12.1"         # Audio I/O
pyannote-audio = "^3.1.0"     # Speaker diarization (optional)
torch = "^2.1.0"              # GPU acceleration (optional)
```

**System Dependencies**:
- **ffmpeg**: Required for audio format conversion
  - macOS: `brew install ffmpeg`
  - Linux: `apt-get install ffmpeg`
  - Windows: Download from ffmpeg.org

### 3.2 Internal Dependencies

**Existing Modules to Import**:
- `file_organizer.models.base`: BaseModel, ModelConfig, ModelType, DeviceType
- `file_organizer.utils.file_readers`: read_file (extend for audio)
- `file_organizer.utils.text_processing`: clean_text, sanitize_filename
- `loguru`: logger

**Patterns to Follow**:
- Model initialization pattern from TextModel
- Service pattern from TextProcessor
- Error handling from VisionProcessor
- Context manager usage from BaseModel

### 3.3 Model Files

**Faster-Whisper Models** (Downloaded on first use):
- `tiny`: ~39 MB - Fastest, lower accuracy
- `base`: ~74 MB - Good balance
- `small`: ~244 MB - Better accuracy
- `medium`: ~769 MB - High accuracy
- `large-v3`: ~1.5 GB - Best accuracy

**Storage Location**: `~/.cache/huggingface/hub/`

## 4. Implementation Streams

### Stream A: Core Transcription Engine (Priority 1)
**Scope**: Implement AudioTranscriber and integrate faster-whisper
**Effort**: 8 hours
**Parallel**: No dependencies

**Tasks**:
1. Create `models/audio_transcriber.py`
2. Implement model loading and caching
3. Implement basic transcription (text only)
4. Add language detection
5. Add timestamp generation
6. Implement device selection (CPU/GPU)
7. Add error handling for model loading failures
8. Write unit tests for transcription core

**Deliverables**:
- `models/audio_transcriber.py`: 200-250 lines
- Unit tests: `tests/models/test_audio_transcriber.py`
- Can transcribe WAV files to text with timestamps

**Files Modified/Created**:
- CREATE: `src/file_organizer/models/audio_transcriber.py`
- CREATE: `tests/models/test_audio_transcriber.py`

---

### Stream B: Audio Format Support (Priority 2)
**Scope**: Implement AudioPreprocessor for multi-format support
**Effort**: 6 hours
**Parallel**: Can run parallel to Stream A

**Tasks**:
1. Create `models/audio_preprocessor.py`
2. Implement format validation (MP3, WAV, FLAC, M4A, OGG)
3. Add ffmpeg integration for format conversion
4. Implement audio normalization
5. Add duration and metadata extraction
6. Handle corrupted file detection
7. Add caching for converted files
8. Write unit tests for preprocessing

**Deliverables**:
- `models/audio_preprocessor.py`: 150-200 lines
- Unit tests: `tests/models/test_audio_preprocessor.py`
- Supports all target audio formats

**Files Modified/Created**:
- CREATE: `src/file_organizer/models/audio_preprocessor.py`
- CREATE: `src/file_organizer/utils/audio_utils.py`
- CREATE: `tests/models/test_audio_preprocessor.py`
- MODIFY: `src/file_organizer/utils/file_readers.py` (add audio support)

---

### Stream C: Speaker Identification (Priority 3)
**Scope**: Integrate speaker diarization with pyannote.audio
**Effort**: 5 hours
**Parallel**: Depends on Stream A completion

**Tasks**:
1. Integrate pyannote.audio for diarization
2. Implement speaker detection pipeline
3. Merge speaker labels with transcription segments
4. Handle overlapping speech scenarios
5. Add speaker count estimation
6. Optimize for performance
7. Write unit tests for diarization

**Deliverables**:
- Extended `AudioTranscriber` with speaker support
- Unit tests for speaker identification
- Speaker labels in TranscriptionResult

**Files Modified/Created**:
- MODIFY: `src/file_organizer/models/audio_transcriber.py` (add diarization)
- CREATE: `tests/models/test_speaker_diarization.py`

---

### Stream D: AudioModel Enhancement (Priority 4)
**Scope**: Complete AudioModel implementation with BaseModel interface
**Effort**: 4 hours
**Parallel**: Depends on Stream A completion

**Tasks**:
1. Update `models/audio_model.py` with real implementation
2. Integrate AudioTranscriber into AudioModel
3. Implement generate() method for BaseModel interface
4. Add configuration management
5. Implement resource cleanup
6. Add context manager support
7. Write unit tests for AudioModel

**Deliverables**:
- Fully functional `AudioModel` class
- Follows BaseModel interface pattern
- Unit tests achieving >80% coverage

**Files Modified/Created**:
- MODIFY: `src/file_organizer/models/audio_model.py` (complete implementation)
- CREATE: `tests/models/test_audio_model.py`

---

### Stream E: Audio Processing Service (Priority 5)
**Scope**: Create AudioProcessor service following TextProcessor pattern
**Effort**: 5 hours
**Parallel**: Depends on Streams A, B, D completion

**Tasks**:
1. Create `services/audio_processor.py`
2. Implement file processing pipeline
3. Add description generation from transcription
4. Add folder name generation
5. Add filename generation
6. Implement batch processing
7. Add progress tracking for long files
8. Write integration tests

**Deliverables**:
- `services/audio_processor.py`: 250-300 lines
- Integration tests with real audio files
- Follows TextProcessor service pattern

**Files Modified/Created**:
- CREATE: `src/file_organizer/services/audio_processor.py`
- CREATE: `tests/services/test_audio_processor.py`
- MODIFY: `src/file_organizer/services/__init__.py` (export AudioProcessor)

---

### Stream F: Testing & Documentation (Priority 6)
**Scope**: Comprehensive testing, benchmarking, and documentation
**Effort**: 3 hours
**Parallel**: After all streams complete

**Tasks**:
1. Create integration tests with sample audio files
2. Test all supported formats (MP3, WAV, FLAC, M4A, OGG)
3. Test language detection with multi-language samples
4. Test speaker identification with multi-speaker audio
5. Run performance benchmarks (various file sizes)
6. Document API usage and examples
7. Update CHANGELOG and README
8. Create usage guide

**Deliverables**:
- Integration test suite: `tests/integration/test_audio_integration.py`
- Performance benchmarks document
- API documentation
- Usage examples

**Files Modified/Created**:
- CREATE: `tests/integration/test_audio_integration.py`
- CREATE: `docs/audio_transcription_guide.md`
- MODIFY: `README.md` (add audio features)
- MODIFY: `CHANGELOG.md` (document changes)

---

## 5. Testing Strategy

### 5.1 Unit Tests

**Coverage Target**: >80% for all new code

**Test Categories**:
1. **AudioTranscriber Tests**
   - Model loading (tiny, base, small)
   - Basic transcription (English, non-English)
   - Language detection accuracy
   - Timestamp generation
   - Error handling (invalid files, missing models)
   - Device selection (CPU, GPU if available)

2. **AudioPreprocessor Tests**
   - Format validation (valid/invalid formats)
   - Format conversion (MP3→WAV, FLAC→WAV, etc.)
   - Audio normalization
   - Metadata extraction
   - Corrupted file handling
   - Duration checking

3. **AudioModel Tests**
   - Initialization with different configs
   - Generate method with various inputs
   - Resource cleanup
   - Context manager usage
   - Error propagation

4. **AudioProcessor Tests**
   - File processing pipeline
   - Description generation
   - Folder/filename generation
   - Batch processing
   - Error handling

### 5.2 Integration Tests

**Test Files Required**:
- `test_samples/audio/sample_english.wav` (30 sec, clear speech)
- `test_samples/audio/sample_spanish.mp3` (30 sec, Spanish)
- `test_samples/audio/sample_multispeaker.flac` (60 sec, 2 speakers)
- `test_samples/audio/sample_music.m4a` (30 sec, music only)
- `test_samples/audio/sample_noisy.ogg` (30 sec, background noise)
- `test_samples/audio/sample_corrupted.wav` (invalid file)

**Integration Scenarios**:
1. End-to-end transcription for each format
2. Language detection with non-English audio
3. Speaker identification with multi-speaker audio
4. Performance with various file sizes (1 min, 5 min, 30 min)
5. Error handling with corrupted files
6. GPU vs CPU performance comparison (if GPU available)

### 5.3 Performance Benchmarks

**Metrics to Track**:
- Transcription time vs audio duration (real-time factor)
- Memory usage vs audio duration
- Model loading time (first vs cached)
- GPU speedup factor (if available)
- Accuracy metrics (WER if reference transcripts available)

**Target Benchmarks**:
- Real-time factor: <1.0 for base model on CPU
- Memory usage: <2GB for 1-hour audio
- Model loading: <10 seconds (first), <1 second (cached)
- GPU speedup: 3-5x faster than CPU

### 5.4 Acceptance Tests

**Manual Verification**:
1. ✅ Transcribe 30-second English audio with >90% accuracy
2. ✅ Correctly detect language in Spanish/French/German audio
3. ✅ Identify 2 distinct speakers in multi-speaker audio
4. ✅ Process MP3, WAV, FLAC, M4A, OGG formats without errors
5. ✅ Generate meaningful folder names from transcriptions
6. ✅ Generate descriptive filenames from transcriptions
7. ✅ Handle corrupted files gracefully (no crashes)
8. ✅ Process 5-minute audio in <5 minutes on CPU
9. ✅ Use GPU acceleration if available (verify with logs)
10. ✅ Cache transcription results to avoid reprocessing

## 6. Risks & Mitigation

### 6.1 Technical Risks

**Risk 1: ffmpeg Availability**
- **Impact**: High - Cannot process non-WAV formats without ffmpeg
- **Probability**: Medium - Not pre-installed on all systems
- **Mitigation**:
  - Check ffmpeg availability on startup
  - Provide clear installation instructions
  - Fallback to WAV-only mode if ffmpeg unavailable
  - Add ffmpeg check to setup validation

**Risk 2: Model Download Size**
- **Impact**: Medium - Large model downloads may deter users
- **Probability**: High - Models range from 39MB to 1.5GB
- **Mitigation**:
  - Default to base model (74MB) - good balance
  - Allow user to select model size
  - Show download progress with rich progress bar
  - Cache models after first download
  - Document model size vs accuracy tradeoffs

**Risk 3: GPU Availability**
- **Impact**: Low - CPU fallback available but slower
- **Probability**: High - Most users won't have CUDA/Metal
- **Mitigation**:
  - Automatic device detection with fallback
  - Use smaller models on CPU (tiny/base)
  - Optimize for CPU performance
  - Document GPU setup for advanced users
  - Set realistic performance expectations

**Risk 4: Speaker Diarization Accuracy**
- **Impact**: Medium - Poor speaker ID reduces utility
- **Probability**: Medium - Depends on audio quality
- **Mitigation**:
  - Make speaker ID optional (default: off)
  - Use pyannote.audio 3.1+ (best available)
  - Require minimum audio quality thresholds
  - Provide confidence scores for speaker labels
  - Document limitations clearly

**Risk 5: Memory Consumption**
- **Impact**: High - Large audio files may cause OOM
- **Probability**: Medium - Depends on file size
- **Mitigation**:
  - Set maximum file duration (default: 2 hours)
  - Use streaming transcription for very long files
  - Monitor memory usage during processing
  - Implement chunking for large files
  - Clear cache aggressively

### 6.2 Performance Risks

**Risk 6: Slow CPU Transcription**
- **Impact**: Medium - Poor UX for long audio files
- **Probability**: High - CPU transcription is slower
- **Mitigation**:
  - Default to smaller models (base)
  - Show progress bar with ETA
  - Enable async processing (non-blocking)
  - Cache transcriptions to avoid reprocessing
  - Recommend GPU for power users

**Risk 7: Model Loading Latency**
- **Impact**: Low - First-run delay may surprise users
- **Probability**: High - Model loading takes 5-10 seconds
- **Mitigation**:
  - Cache loaded models in memory
  - Lazy load models (only on first audio file)
  - Show "Loading model..." message
  - Pre-load models during initialization if configured
  - Document first-run behavior

### 6.3 Integration Risks

**Risk 8: Breaking BaseModel Interface**
- **Impact**: High - May break existing code
- **Probability**: Low - Clear interface defined
- **Mitigation**:
  - Follow TextModel pattern exactly
  - Run full test suite before merge
  - Test with existing core orchestration
  - Add integration tests
  - Code review focusing on interface compliance

**Risk 9: Dependency Conflicts**
- **Impact**: Medium - Version conflicts with existing dependencies
- **Probability**: Medium - Adding several new libraries
- **Mitigation**:
  - Test in clean virtual environment
  - Use flexible version constraints
  - Document any conflicts in setup guide
  - Test with poetry and pip installations
  - CI/CD dependency checks

### 6.4 Quality Risks

**Risk 10: Low Transcription Accuracy**
- **Impact**: High - Reduces product value
- **Probability**: Medium - Depends on audio quality
- **Mitigation**:
  - Use latest faster-whisper (1.0+)
  - Use large-v3 model for best accuracy
  - Preprocess audio (normalize, denoise)
  - Set minimum quality thresholds
  - Document accuracy expectations
  - Provide confidence scores

## 7. Performance Optimization

### 7.1 Optimization Strategies

**Model Selection**:
- Default: `base` (74MB) - Best balance
- Fast: `tiny` (39MB) - Quick preview mode
- Accurate: `large-v3` (1.5GB) - Best results

**Caching Layers**:
1. **Model Cache**: Keep loaded models in memory
2. **Transcription Cache**: Store results by file hash
3. **Conversion Cache**: Cache format conversions

**Async Processing**:
- Use asyncio for non-blocking transcription
- Queue long-running transcriptions
- Provide progress callbacks

**Batch Processing**:
- Process multiple files in parallel
- Share model instance across files
- Optimize for throughput over latency

### 7.2 Resource Management

**Memory Limits**:
- Model: 200MB-2GB depending on size
- Audio buffer: 100MB per file
- Total: <3GB for typical usage

**Timeout Strategy**:
- Default timeout: 5 minutes per file
- Configurable per file size
- Graceful cancellation support

**Cleanup Strategy**:
- Release models after idle timeout (5 min)
- Clear conversion cache periodically
- Delete temporary files after processing

## 8. Configuration

### 8.1 Default Configuration

```python
AudioConfig(
    model_size="base",           # tiny, base, small, medium, large-v3
    device="auto",               # auto, cpu, cuda, mps
    compute_type="float16",      # float16, int8, int4
    enable_speaker_diarization=False,  # Speaker ID
    language=None,               # Auto-detect if None
    max_duration_seconds=7200,   # 2 hours
    cache_transcriptions=True,
    cache_models=True,
    num_workers=1,               # For batch processing
    timeout_seconds=300,         # 5 minutes
)
```

### 8.2 Advanced Options

```python
AdvancedConfig(
    beam_size=5,                 # Beam search size
    best_of=5,                   # Number of candidates
    temperature=0.0,             # Sampling temperature
    vad_filter=True,             # Voice activity detection
    word_timestamps=True,        # Word-level timestamps
    suppress_numerals=False,     # Keep numbers
    initial_prompt=None,         # Context hint
)
```

## 9. Success Criteria

### 9.1 Functional Success
- ✅ All acceptance criteria met (10/10)
- ✅ Unit test coverage >80%
- ✅ Integration tests passing with all formats
- ✅ No regressions in existing functionality

### 9.2 Performance Success
- ✅ Real-time factor <1.0 for base model
- ✅ Memory usage <2GB for 1-hour audio
- ✅ Processing 5-min audio in <5 minutes (CPU)
- ✅ GPU acceleration working (3-5x speedup)

### 9.3 Quality Success
- ✅ Transcription accuracy >90% (clear audio)
- ✅ Language detection accuracy >95%
- ✅ Speaker identification accuracy >80% (clear speech)
- ✅ Meaningful folder/filename generation >90%

### 9.4 Integration Success
- ✅ Follows BaseModel interface exactly
- ✅ Compatible with existing service patterns
- ✅ Works with orchestration layer
- ✅ No breaking changes to existing code

## 10. Implementation Timeline

**Total Estimated Time**: 24 hours

### Week 1 (16 hours)
- **Day 1-2** (8h): Stream A - Core Transcription Engine
- **Day 3** (6h): Stream B - Audio Format Support
- **Day 4** (2h): Testing Stream A + B

### Week 2 (8 hours)
- **Day 5** (5h): Stream C - Speaker Identification
- **Day 5** (4h): Stream D - AudioModel Enhancement
- **Day 6** (5h): Stream E - Audio Processing Service
- **Day 7** (3h): Stream F - Testing & Documentation

### Parallel Execution
- Streams A and B can run in parallel (Day 1-3)
- Streams C, D depend on Stream A
- Stream E depends on Streams A, B, D
- Stream F depends on all streams

## 11. Deliverables Summary

### Code Deliverables
1. **New Files** (7 files):
   - `models/audio_transcriber.py` (~250 lines)
   - `models/audio_preprocessor.py` (~200 lines)
   - `services/audio_processor.py` (~300 lines)
   - `utils/audio_utils.py` (~150 lines)

2. **Modified Files** (2 files):
   - `models/audio_model.py` (complete implementation)
   - `utils/file_readers.py` (add audio support)

3. **Test Files** (6 files):
   - Unit tests for each new module
   - Integration test suite
   - Performance benchmarks

### Documentation Deliverables
1. API documentation
2. Usage guide with examples
3. Performance benchmark report
4. Setup instructions (ffmpeg, GPU)
5. Updated CHANGELOG
6. Updated README

### Dependencies Update
- Update `pyproject.toml` with new dependencies
- Update requirements documentation
- System dependency guide (ffmpeg)

## 12. Definition of Done Checklist

- [ ] All 6 implementation streams completed
- [ ] Unit tests written and passing (>80% coverage)
- [ ] Integration tests passing with all formats (MP3, WAV, FLAC, M4A, OGG)
- [ ] Performance benchmarks documented
- [ ] All 10 acceptance criteria verified
- [ ] Code follows project style guidelines (ruff, mypy passing)
- [ ] No regressions in existing functionality
- [ ] API documentation complete
- [ ] Usage guide with examples written
- [ ] Code reviewed and approved
- [ ] Manual testing completed with real audio files
- [ ] GPU acceleration tested (if available)
- [ ] Error handling comprehensive (corrupted files, missing deps)
- [ ] ffmpeg dependency check implemented
- [ ] Model caching working correctly
- [ ] Transcription caching working correctly

## 13. Future Enhancements (Out of Scope)

These are explicitly out of scope for Task 42 but documented for future work:

1. **Advanced Speaker Features**
   - Speaker identification by voice (recognize known speakers)
   - Speaker emotion detection
   - Speaker gender/age estimation

2. **Audio Quality Enhancement**
   - Noise reduction preprocessing
   - Audio upsampling for better transcription
   - Background music removal

3. **Advanced Transcription**
   - Real-time streaming transcription
   - Subtitle generation (SRT, VTT)
   - Translation to other languages

4. **Podcast-Specific Features**
   - Chapter detection
   - Topic segmentation
   - Show notes generation

5. **Performance Optimizations**
   - Quantized model support (int4, int8)
   - Model distillation for faster inference
   - Distributed processing for very long files
