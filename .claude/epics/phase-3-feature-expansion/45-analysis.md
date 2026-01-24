---
name: implement-multi-frame-video-analysis-analysis
task: 45
epic: phase-3-feature-expansion
created: 2026-01-21T12:51:30Z
updated: 2026-01-21T12:51:30Z
status: in_progress
---

# Task 45 Analysis: Implement Multi-Frame Video Analysis

## Overview

This task implements comprehensive multi-frame video analysis to improve video understanding beyond single frame analysis. The system will detect scene boundaries, extract representative frames, generate thumbnails, and integrate with the existing vision model for content understanding.

## Technical Requirements

### Core Functionality

1. **Scene Detection**
   - Detect scene boundaries using content-based analysis
   - Adaptive threshold for different video types (movies, lectures, screencasts)
   - Extract scene metadata: timestamp, duration, frame index
   - Support videos up to 2 hours in length

2. **Multi-Frame Sampling**
   - Intelligent sampling strategies (temporal, scene-based, quality-based)
   - Extract 5-10 representative frames per video
   - Balance between accuracy and performance
   - Frame deduplication to avoid redundant analysis

3. **Thumbnail Generation**
   - Select most representative frame per scene
   - Generate multiple sizes (small: 240p, medium: 480p, large: 720p)
   - Quality optimization (sharpness, brightness, contrast)
   - Configurable output location and format

4. **Video Metadata Extraction**
   - Resolution, codec, duration, fps
   - Frame count and bitrate
   - Audio track information
   - Container format details

5. **Integration with Vision Model**
   - Analyze extracted frames using existing VisionModel
   - Aggregate frame descriptions into video summary
   - Generate category and filename from multi-frame analysis
   - Enhanced accuracy compared to single-frame analysis

### Performance Requirements

- Handle videos up to 2 hours without memory issues
- Frame extraction: < 500ms per frame
- Scene detection: < 2 seconds per minute of video
- Thumbnail generation: < 100ms per thumbnail
- Total processing time: < 5 minutes for 2-hour video (excluding AI analysis)

### Quality Requirements

- Scene detection accuracy: > 85% (matches human perception)
- Thumbnail quality: sharp, well-exposed, representative
- Frame diversity: avoid similar/duplicate frames
- Robust error handling for corrupted/unsupported video files

## Architecture

### Component Design

```
video_analyzer.py (Main Service)
├── VideoAnalyzer (orchestrator)
│   ├── analyze_video() - main entry point
│   ├── _extract_scenes() - scene detection
│   ├── _sample_frames() - frame extraction
│   ├── _analyze_with_vision() - AI analysis
│   └── _aggregate_results() - combine analyses
│
utils/scene_detector.py
├── SceneDetector
│   ├── detect_scenes() - main detection algorithm
│   ├── _calculate_content_diff() - frame comparison
│   ├── _adaptive_threshold() - dynamic sensitivity
│   └── _filter_short_scenes() - post-processing
│
utils/frame_sampler.py
├── FrameSampler
│   ├── sample_frames() - extract frames
│   ├── _temporal_sampling() - time-based
│   ├── _scene_based_sampling() - scene-aware
│   ├── _quality_filter() - blur/exposure check
│   └── _deduplicate() - remove similar frames
│
utils/thumbnail_generator.py
├── ThumbnailGenerator
│   ├── generate_thumbnails() - main entry
│   ├── _select_best_frame() - quality analysis
│   ├── _resize_and_optimize() - image processing
│   └── _enhance_quality() - sharpening, contrast
│
utils/video_metadata.py
└── VideoMetadata
    ├── extract_metadata() - ffprobe wrapper
    └── get_video_info() - basic video info
```

### Integration Points

1. **VisionModel** (existing)
   - Use `analyze_video_frame()` method for each extracted frame
   - Pass custom prompts for video-specific analysis
   - Aggregate descriptions from multiple frames

2. **VisionProcessor** (existing)
   - Extend to support multi-frame video processing
   - Add `process_video()` method alongside `process_file()`
   - Return `ProcessedVideo` dataclass with aggregated metadata

3. **FileOrganizer** (existing)
   - Integrate video analysis into main organization flow
   - Use VIDEO_EXTENSIONS from existing config
   - Apply same folder/filename generation logic

4. **Storage**
   - Store thumbnails in configurable location (default: `.thumbnails/`)
   - Cache extracted frames temporarily (auto-cleanup)
   - Store scene metadata in JSON sidecar files (optional)

### Data Flow

```
Video File
    ↓
VideoAnalyzer.analyze_video()
    ↓
├─→ VideoMetadata.extract_metadata() → basic info
├─→ SceneDetector.detect_scenes() → scene boundaries
├─→ FrameSampler.sample_frames() → extract key frames
│       ↓
│   ├─→ temporal sampling (every N seconds)
│   ├─→ scene-based sampling (1 per scene)
│   ├─→ quality filter (blur detection)
│   └─→ deduplication (perceptual hash)
│       ↓
├─→ ThumbnailGenerator.generate_thumbnails() → preview images
└─→ VisionModel.analyze_video_frame() × N frames
        ↓
    Aggregate descriptions → Video summary
        ↓
    ProcessedVideo result
```

## Dependencies

### External Libraries (New)

```python
# Video processing
opencv-python = ">=4.12.0"  # ALREADY INSTALLED
scenedetect = ">=0.6.0"     # NEEDS INSTALL
numpy = ">=1.24.0"          # likely already available

# Performance optimization
imageio-ffmpeg = ">=0.4.0"  # FFmpeg wrapper for metadata
```

### Internal Modules (Existing)

- `file_organizer.models.vision_model` - VisionModel class
- `file_organizer.services.vision_processor` - VisionProcessor class
- `file_organizer.utils.file_readers` - File utilities
- `file_organizer.core.organizer` - Main orchestrator

### System Dependencies

- FFmpeg (for video metadata extraction)
- Sufficient disk space for temporary frame storage (configurable cleanup)

## Implementation Streams

### Stream A: Video Metadata and Scene Detection (6 hours)

**Scope**: Core video processing infrastructure

**Files to Create**:
- `file_organizer_v2/src/file_organizer/utils/video_metadata.py`
- `file_organizer_v2/src/file_organizer/utils/scene_detector.py`

**Files to Modify**: None

**Deliverables**:
1. `VideoMetadata` class with FFmpeg integration
   - Extract duration, resolution, fps, codec
   - Handle errors gracefully (missing FFmpeg, corrupted files)
   - Return structured metadata dict

2. `SceneDetector` class with adaptive algorithm
   - Content-based scene detection using OpenCV
   - Adaptive threshold based on video characteristics
   - Filter out too-short scenes (< 1 second)
   - Return list of scene boundaries with timestamps

**Dependencies**: None (foundational)

**Parallel**: Yes - independent of other streams

**Testing**:
- Unit tests with sample video files (various formats)
- Test edge cases: very short videos, single-scene videos
- Performance benchmarks for long videos

**Estimated Effort**: 6 hours
- VideoMetadata: 2 hours
- SceneDetector: 4 hours

---

### Stream B: Frame Sampling and Thumbnail Generation (8 hours)

**Scope**: Frame extraction and quality optimization

**Files to Create**:
- `file_organizer_v2/src/file_organizer/utils/frame_sampler.py`
- `file_organizer_v2/src/file_organizer/utils/thumbnail_generator.py`

**Files to Modify**: None

**Deliverables**:
1. `FrameSampler` class with multiple sampling strategies
   - Temporal sampling (every N seconds)
   - Scene-based sampling (1 per scene)
   - Quality filtering (blur/exposure detection)
   - Frame deduplication (perceptual hashing)
   - Save frames to temporary directory

2. `ThumbnailGenerator` class
   - Select best frame from scene (sharpness scoring)
   - Resize to multiple sizes (240p, 480p, 720p)
   - Image enhancement (contrast, brightness, sharpness)
   - Save to configurable location

**Dependencies**:
- Stream A (needs scene boundaries)

**Parallel**: No - requires Stream A completion

**Testing**:
- Unit tests for sampling algorithms
- Visual inspection of generated thumbnails
- Quality metrics (sharpness, exposure)
- Performance tests for batch operations

**Estimated Effort**: 8 hours
- FrameSampler: 5 hours
- ThumbnailGenerator: 3 hours

---

### Stream C: Video Analysis Service (6 hours)

**Scope**: Main orchestration and vision integration

**Files to Create**:
- `file_organizer_v2/src/file_organizer/services/video_analyzer.py`

**Files to Modify**:
- `file_organizer_v2/src/file_organizer/services/__init__.py` (add VideoAnalyzer export)

**Deliverables**:
1. `VideoAnalyzer` main service class
   - `analyze_video()` - main entry point
   - Orchestrate metadata extraction, scene detection, frame sampling
   - Integrate with VisionModel for frame analysis
   - Aggregate multi-frame descriptions into video summary
   - Return `ProcessedVideo` dataclass

2. `ProcessedVideo` dataclass
   - File path, duration, resolution, scene count
   - Frame descriptions, video summary
   - Suggested folder name and filename
   - Thumbnail paths
   - Processing time and metadata

**Dependencies**:
- Stream A (metadata, scenes)
- Stream B (frames, thumbnails)
- Existing VisionModel

**Parallel**: No - requires both A and B

**Testing**:
- Integration tests with VisionModel
- End-to-end video processing tests
- Test aggregation logic for multi-frame descriptions
- Error handling for various video types

**Estimated Effort**: 6 hours

---

### Stream D: Vision Processor Integration (4 hours)

**Scope**: Extend existing VisionProcessor for videos

**Files to Modify**:
- `file_organizer_v2/src/file_organizer/services/vision_processor.py`

**Deliverables**:
1. Add `process_video()` method to VisionProcessor
   - Accept video file path
   - Create VideoAnalyzer instance
   - Call `analyze_video()` and return results
   - Handle initialization of vision model

2. Update `__init__` and class documentation
   - Document video processing capabilities
   - Add video-specific configuration options

**Dependencies**:
- Stream C (VideoAnalyzer must exist)

**Parallel**: No - requires Stream C

**Testing**:
- Integration tests with VisionProcessor
- Test video + image processing in same session
- Verify model initialization/cleanup

**Estimated Effort**: 4 hours

---

## Testing Strategy

### Unit Tests (Coverage target: >80%)

**test_video_metadata.py**
- Test metadata extraction for various formats (MP4, AVI, MKV, MOV)
- Test error handling (missing file, corrupted video, no FFmpeg)
- Test edge cases (very short, very long, high resolution)

**test_scene_detector.py**
- Test scene detection accuracy with known scene changes
- Test adaptive threshold for different video types
- Test performance with long videos
- Test edge cases (single scene, rapid cuts)

**test_frame_sampler.py**
- Test temporal sampling consistency
- Test scene-based sampling (one per scene)
- Test quality filtering (detect blurry frames)
- Test deduplication (similar frames removed)

**test_thumbnail_generator.py**
- Test frame selection (best quality)
- Test resizing to multiple sizes
- Test image enhancement
- Test file saving and cleanup

**test_video_analyzer.py**
- Test end-to-end video analysis
- Test integration with VisionModel (mocked)
- Test result aggregation
- Test error handling and graceful degradation

### Integration Tests

**test_video_processing_integration.py**
- Test full pipeline with real video files
- Test various video formats and durations
- Test with real VisionModel (slow test, marked)
- Verify thumbnail generation and storage
- Test memory usage with large videos

### Performance Tests

**test_video_performance.py**
- Benchmark scene detection speed (seconds per minute of video)
- Benchmark frame extraction speed
- Benchmark memory usage for 2-hour videos
- Verify processing time targets are met

### Acceptance Tests

**Manual Testing Checklist**:
- [ ] Process 10-second video → extracts 5-10 frames
- [ ] Process 2-hour movie → completes in < 5 minutes
- [ ] Scene detection identifies obvious scene changes
- [ ] Thumbnails are sharp and representative
- [ ] Video summary is coherent and accurate
- [ ] Works with MP4, AVI, MKV, MOV formats
- [ ] Handles corrupted files gracefully
- [ ] Memory usage stays reasonable (< 2GB peak)

### Test Data Requirements

**Sample Videos** (to be created or sourced):
1. Short video (10 seconds, single scene) - test basic functionality
2. Medium video (2 minutes, 3-5 scenes) - test scene detection
3. Long video (10 minutes, 20+ scenes) - test performance
4. Lecture/screencast (static camera) - test adaptive threshold
5. Movie clip (dynamic scenes) - test content detection
6. Various formats (MP4, AVI, MKV, MOV) - test compatibility

## Risks & Mitigation

### Risk 1: Memory Usage with Large Videos
**Impact**: High
**Probability**: Medium

**Mitigation**:
- Stream video frames instead of loading entire video
- Process frames in batches with cleanup
- Use frame sampling to limit total frames extracted
- Implement configurable memory limits
- Add memory monitoring and warnings

### Risk 2: Scene Detection Accuracy
**Impact**: Medium
**Probability**: Medium

**Mitigation**:
- Use proven algorithm (PySceneDetect ContentDetector)
- Implement adaptive thresholds for different video types
- Allow manual threshold adjustment via config
- Fall back to temporal sampling if scene detection fails
- Extensive testing with diverse video types

### Risk 3: Processing Time for Long Videos
**Impact**: Medium
**Probability**: Low

**Mitigation**:
- Optimize frame extraction (skip decoding unnecessary frames)
- Use hardware acceleration where available (GPU)
- Implement parallel frame analysis
- Provide progress feedback to users
- Allow interruption and resume (future enhancement)

### Risk 4: PySceneDetect Library Compatibility
**Impact**: Medium
**Probability**: Low

**Mitigation**:
- Test thoroughly during development
- Pin specific version in dependencies
- Implement fallback to pure OpenCV if library unavailable
- Document alternative installation methods
- Consider implementing custom scene detection as backup

### Risk 5: FFmpeg Dependency
**Impact**: High
**Probability**: Low

**Mitigation**:
- Check for FFmpeg availability at startup
- Provide clear installation instructions
- Use imageio-ffmpeg as bundled alternative
- Gracefully degrade if FFmpeg unavailable
- Extract basic metadata using OpenCV as fallback

### Risk 6: Vision Model Performance with Multiple Frames
**Impact**: Medium
**Probability**: Medium

**Mitigation**:
- Limit frame analysis to 5-10 frames maximum
- Implement smart frame selection (avoid redundant frames)
- Use lower temperature for faster inference
- Cache frame analyses to avoid reprocessing
- Allow disabling AI analysis for speed (metadata-only mode)

## Implementation Notes

### Configuration Options

```python
@dataclass
class VideoAnalysisConfig:
    """Configuration for video analysis."""

    # Scene detection
    scene_detection_threshold: float = 27.0  # ContentDetector threshold
    min_scene_length: float = 1.0  # seconds

    # Frame sampling
    max_frames: int = 10  # maximum frames to extract
    sampling_strategy: str = "scene_based"  # temporal, scene_based, adaptive
    temporal_interval: float = 10.0  # seconds between frames (temporal mode)

    # Quality filtering
    enable_quality_filter: bool = True
    min_sharpness: float = 100.0  # Laplacian variance threshold
    min_brightness: float = 30.0  # mean pixel value threshold

    # Thumbnail generation
    thumbnail_sizes: List[Tuple[int, int]] = [(240, -1), (480, -1), (720, -1)]
    thumbnail_format: str = "jpg"
    thumbnail_quality: int = 85
    thumbnail_dir: Optional[Path] = None  # default: .thumbnails/

    # Performance
    enable_frame_cache: bool = True
    max_memory_mb: int = 2000
    enable_parallel_analysis: bool = False  # future enhancement

    # AI analysis
    enable_vision_analysis: bool = True
    vision_prompt_template: str = "Describe this video frame..."
```

### Code Quality Standards

- Type hints for all functions and methods
- Comprehensive docstrings (Google style)
- Logging at appropriate levels (debug, info, warning, error)
- Error handling with specific exceptions
- Resource cleanup (context managers, try/finally)
- Performance monitoring (timing, memory tracking)

### Documentation Requirements

Each new file should include:
1. Module-level docstring explaining purpose
2. Class docstrings with usage examples
3. Method docstrings with Args/Returns/Raises
4. Inline comments for complex algorithms
5. Type hints for IDE support

### Progress Tracking

The implementation should provide progress feedback:
- Log key milestones (scene detection started, frames extracted, etc.)
- Track processing time for each stage
- Report frame counts and scene counts
- Warn about performance issues (slow processing, high memory)

## Future Enhancements (Out of Scope)

These are potential future improvements NOT included in this task:

1. **Audio Transcription Integration** (Task 46)
   - Use scene timestamps for audio segmentation
   - Align transcription with visual scenes

2. **Action Recognition** (Future)
   - Detect specific actions in video (sports, activities)
   - Use specialized models (e.g., SlowFast, I3D)

3. **Object Tracking** (Future)
   - Track specific objects across frames
   - Generate object-based summaries

4. **Video Summarization** (Future)
   - Generate short highlight clips
   - Create GIF previews from key moments

5. **Hardware Acceleration** (Future)
   - Use GPU for frame extraction and processing
   - CUDA/Metal optimization for scene detection

## Success Criteria

This task is complete when:

1. ✅ All 4 implementation streams are complete
2. ✅ Unit test coverage > 80% for new code
3. ✅ Integration tests pass with real video files
4. ✅ Performance benchmarks meet targets:
   - Scene detection: < 2s per minute of video
   - Frame extraction: < 500ms per frame
   - Total processing: < 5 minutes for 2-hour video
5. ✅ Acceptance criteria met (all manual tests pass)
6. ✅ Code review completed and approved
7. ✅ Documentation is complete and accurate
8. ✅ Integration with existing VisionProcessor works
9. ✅ No memory leaks or performance degradation
10. ✅ Dependencies added to pyproject.toml

## Timeline Estimate

- **Stream A**: 6 hours (Days 1-2)
- **Stream B**: 8 hours (Days 2-3, after Stream A)
- **Stream C**: 6 hours (Days 3-4, after A+B)
- **Stream D**: 4 hours (Day 4, after C)
- **Total**: 24 hours over 4-5 working days

This matches the original estimate in the task file.
