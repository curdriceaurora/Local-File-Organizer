---
name: metadata-audio-video-organization
description: Metadata-based audio and video file organization without AI model dependencies
status: backlog
created: 2026-02-21T04:37:42Z
updated: 2026-02-21T04:56:05Z
priority: high
---

# PRD: Metadata-Based Audio/Video File Organization

## Problem Statement

The File Organizer currently **skips all audio files** (organizer.py line 217) and **routes video files through the heavy VisionProcessor AI model** (organizer.py line 194), which requires a 6 GB Qwen 2.5-VL model download and GPU resources. This means audio files — representing a common file type users want organized — are completely ignored, while video organization is unnecessarily slow and resource-intensive for what amounts to basic folder placement.

Users who run `file-organizer` on a directory containing MP3s, podcasts, screen recordings, and home videos get no organization for audio and suboptimal, slow processing for video. The audio metadata pipeline (extractor, classifier, organizer with 7 content-type templates) is **already fully implemented** in `services/audio/` (~3,200 LOC) but simply not wired into the core organizer.

**Who is affected**: All users with audio files; users with video files who don't need content-aware AI analysis.

**Impact of not solving**: Audio files remain permanently unorganized. Video files require unnecessary AI model initialization, adding 5-20 seconds per file and ~6 GB of model downloads for results that could be achieved in milliseconds with metadata parsing.

## Goals

1. **Organize 100% of audio files** using existing metadata pipeline (ID3 tags, container metadata) — currently 0% are processed
2. **Organize video files by metadata** (title, creation date, resolution, duration) without requiring VisionProcessor or Ollama models
3. **Reduce video processing time by 10-50x** — from 5-20s/file (AI) to <100ms/file (metadata)
4. **Eliminate mandatory Ollama model download** for users who only have audio/video files (currently requires ~6 GB Qwen 2.5-VL even if no images exist)
5. **Zero new required dependencies** — use optional deps already declared in pyproject.toml (mutagen, tinytag, opencv)

## Non-Goals

1. **AI-powered content analysis for audio/video** — transcription-based organization (faster-whisper), scene understanding, and content-aware classification are deferred to a future release. This PRD is metadata-only.
2. **New audio metadata extraction** — the AudioMetadataExtractor, AudioClassifier, and AudioOrganizer are already built and tested. We reuse them as-is.
3. **Video content classification** — classifying videos as "tutorial", "movie", "meeting recording" etc. requires AI and is out of scope. We classify by filename patterns, creation date, and resolution/duration only.
4. **Replacing VisionProcessor for images** — image processing continues to use VisionModel. Only video is decoupled from VisionProcessor.
5. **Custom user-facing configuration** — template customization for video organization folders is deferred. Default templates ship first.

## User Stories

### As a music collector
I want my MP3/FLAC files automatically sorted into `Genre/Artist/Album/` folders so that my music library is browsable without manual effort.

### As a podcast listener
I want downloaded podcast episodes organized into `Show/Year/Episode - Title` folders so I can find specific episodes quickly.

### As a content creator
I want my video files sorted primarily by title/date with resolution as a secondary signal so my footage is logically grouped without waiting for AI processing.

### As a user with screen recordings
I want my screen recordings (from OBS, QuickTime, Xbox Game Bar, etc.) automatically detected by filename patterns and placed in a dedicated folder so they don't clutter my other video folders.

### As a user with limited hardware
I want to organize my audio and video files without downloading 6 GB of AI models so the tool works immediately on any machine.

## Requirements

### P0 — Must-Have

**R1: Wire existing audio pipeline into core organizer**
- Add `_process_audio_files(files: list[Path]) -> list[ProcessedFile]` to `FileOrganizer`
- Import and use `AudioMetadataExtractor`, `AudioClassifier`, `AudioOrganizer` from `services.audio`
- Pipeline: extract metadata → classify type → generate folder/filename via AudioOrganizer templates
- Remove audio from the unsupported/skipped file list (line 217)
- Graceful error handling: if mutagen/tinytag unavailable, return error ProcessedFile with descriptive message
- No AI model initialization needed for audio files
- **Acceptance criteria**: `file-organizer --dry-run` on a directory with MP3/FLAC/M4A files shows organized folder structure using existing audio templates (Music/Genre/Artist, Podcasts/Show/Year, etc.)

**R2: Create VideoMetadataExtractor**
- New file: `src/file_organizer/services/video/metadata_extractor.py`
- `VideoMetadata` dataclass: file_path, file_size, format, duration, width, height, fps, codec, bitrate, creation_date
- `VideoMetadataExtractor` class using `cv2.VideoCapture` (opencv already optional dep)
- `extract(video_path: Path) -> VideoMetadata` — reads container metadata via OpenCV
- `extract_batch(paths: list[Path]) -> list[VideoMetadata]`
- Graceful fallback if opencv unavailable: populate only file_size and format from filesystem
- Helper: `resolution_label(width, height) -> str` — returns "4k", "1080p", "720p", "480p", "sd"
- Follow `AudioMetadataExtractor` structure closely for consistency
- **Acceptance criteria**: `VideoMetadataExtractor().extract(Path("video.mp4"))` returns populated VideoMetadata; without opencv installed, returns partial metadata with file_size and format only

**R3: Create VideoOrganizer**
- New file: `src/file_organizer/services/video/organizer.py`
- `VideoOrganizer` class with template-based path generation
- **Primary organization by title/date** (not resolution):
  - Videos with meaningful titles → `Videos/{Year}/{Title}.{ext}`
  - Screen recordings (detected by filename) → `Screen_Recordings/{Year}/{Filename}`
  - Short clips (<60s) → `Short_Clips/{Filename}`
  - Fallback (no metadata) → `Videos/Unsorted/{Filename}`
- Resolution used as secondary signal only (e.g. subfolder or tag, not primary sort)
- `generate_path(metadata: VideoMetadata) -> tuple[str, str]` — returns (folder_name, filename)
- `is_screen_recording(filename: str) -> bool` — detects screen recordings by filename pattern
- Reuse `sanitize_filename` from `utils/text_processing.py`
- **Acceptance criteria**: VideoOrganizer prioritizes title/date for folder placement; screen recordings detected by filename are routed to dedicated folder

**R3a: Screen Recording Detection via Filename Patterns**
- Detect screen recordings from common default filename conventions:
  - **macOS**: `Screen Recording YYYY-MM-DD at H.MM.SS PM.mov`
  - **OBS Studio**: `YYYY-MM-DD HH-MM-SS.mkv` (pure timestamp = likely OBS)
  - **Xbox Game Bar**: `{AppName} YYYY-MM-DD HH-MM-SS.mp4`
  - **ShareX**: `{ProcessName}_{RandomAlphanumeric}.mp4`
  - **Camtasia**: `Capture{NN}.trec` / `Rec YYYY-MM-DD.*`
  - **Windows Snipping Tool**: `Screen Recording YYYY-MM-DD *.mp4`
  - **Generic**: filenames containing "screen recording", "screencast", "capture", "rec_"
- Regex-based matching — no AI needed, pure string pattern recognition
- Return confidence score (high = exact pattern match, medium = keyword match, low = heuristic)
- **Acceptance criteria**: `is_screen_recording("Screen Recording 2025-01-15 at 3.45.22 PM.mov")` returns True; `is_screen_recording("birthday_party.mp4")` returns False

**R4: Wire video metadata processing into core organizer**
- Add `_process_video_files(files: list[Path]) -> list[ProcessedFile]` to `FileOrganizer`
- Import `VideoMetadataExtractor`, `VideoOrganizer` from `services.video`
- Pipeline: extract metadata → generate folder/filename based on resolution/duration
- Replace current video processing (line 194 `_process_image_files(video_files)`) with `_process_video_files(video_files)`
- VisionProcessor initialization only for image_files — video no longer requires it
- Graceful fallback: if opencv unavailable, place in `Videos/Unsorted/` folder
- **Acceptance criteria**: `file-organizer --dry-run` on a directory with .mp4/.mkv files shows resolution-based folders without requiring Ollama models

**R5: Update file breakdown display**
- `_show_file_breakdown()` changes audio status from "⊘ Skip (needs audio model)" to "✓ Will process (metadata)"
- Video status changes to "✓ Will process (metadata)"
- **Acceptance criteria**: CLI output shows correct processing status for both audio and video

**R6: Update services/video/__init__.py exports**
- Export `VideoMetadata`, `VideoMetadataExtractor`, `VideoOrganizer`
- **Acceptance criteria**: `from file_organizer.services.video import VideoMetadataExtractor` works

### P1 — Nice-to-Have

**R7: Add pymediainfo as optional dependency**
- Add `pymediainfo>=6.0.0` to video optional deps in pyproject.toml as richer fallback for video metadata
- Keep opencv as primary extractor (already declared)
- **Acceptance criteria**: `pip install -e ".[video]"` installs pymediainfo alongside opencv

**R8: Batch processing with progress**
- Use `ParallelProcessor` from `parallel/processor.py` for batch audio/video processing
- Show progress bar during metadata extraction
- **Acceptance criteria**: Processing 100+ files shows progress indicator

### P2 — Future Considerations

- AI-powered audio transcription and content-aware classification (faster-whisper integration)
- Video scene detection + content-aware classification (tutorial, movie, meeting, etc.)
- Custom user-configurable templates for video organization
- Video thumbnail generation for preview in TUI/Web UI
- Cross-referencing audio/video metadata with existing folder patterns (Intelligence service)

## Success Metrics

### Leading Indicators (change within days of release)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Audio files processed per run | >0 (currently 0) | CLI output count |
| Video processing time (avg/file) | <500ms | Timer in ProcessedFile |
| Ollama model required for audio/video | No | Check model init code path |

### Lagging Indicators (change within weeks)

| Metric | Target | Measurement |
|--------|--------|-------------|
| File types with zero organization support | 0 (currently audio = 0%) | Supported type matrix |
| User-reported "files skipped" complaints | Decrease | GitHub issues |
| Average total processing time (mixed dirs) | 30-50% faster | Benchmark script |

## Technical Design Summary

### Files Created

| File | Purpose |
|------|---------|
| `src/file_organizer/services/video/metadata_extractor.py` | VideoMetadata dataclass + VideoMetadataExtractor |
| `src/file_organizer/services/video/organizer.py` | VideoOrganizer with resolution-based templates |
| `tests/services/video/test_metadata_extractor.py` | Video metadata extraction tests |
| `tests/services/video/test_video_organizer.py` | Video organizer template tests |
| `tests/services/video/__init__.py` | Test package init |
| `tests/core/test_audio_video_integration.py` | Core organizer integration tests |

### Files Modified

| File | Changes |
|------|---------|
| `src/file_organizer/services/video/__init__.py` | Export new classes |
| `src/file_organizer/core/organizer.py` | Add `_process_audio_files()`, `_process_video_files()`, update `_show_file_breakdown()`, remove audio skip, replace video AI path |
| `pyproject.toml` | Add pymediainfo optional dep |

### Existing Code Reused

| Component | Location | Purpose |
|-----------|----------|---------|
| AudioMetadataExtractor | `services/audio/metadata_extractor.py` | Extract audio tags (ID3, Vorbis, etc.) |
| AudioClassifier | `services/audio/classifier.py` | Classify audio type (music, podcast, audiobook, etc.) |
| AudioOrganizer | `services/audio/organizer.py` | Generate audio folder paths from 7 templates |
| ProcessedFile | `services/text_processor.py` | Standard result dataclass (file_path, folder_name, filename, error) |
| sanitize_filename | `utils/text_processing.py` | Clean generated filenames |

### Data Flow

```
Audio: file → AudioMetadataExtractor → AudioClassifier → AudioOrganizer → ProcessedFile
Video: file → VideoMetadataExtractor → VideoOrganizer → ProcessedFile
```

No AI models in either path. Pure metadata parsing.

## Testing Strategy

### Unit Tests
- `test_metadata_extractor.py`: VideoMetadata creation, extraction with/without opencv, resolution_label helper, batch extraction
- `test_video_organizer.py`: template generation for each resolution tier, short clip detection, filename sanitization

### Integration Tests
- `test_audio_video_integration.py`: Core organizer processes audio files via metadata pipeline, core organizer processes video files via metadata pipeline, mixed file type directory (text + images + audio + video), graceful fallback when optional deps unavailable, ProcessedFile output format compatibility with `_organize_files()`

### Test Approach
- Mock `cv2.VideoCapture` for video metadata tests (no real video files needed)
- Mock `AudioMetadataExtractor` for audio integration tests
- Test graceful fallback when optional deps unavailable (mutagen, tinytag, opencv)

## Verification Plan

```bash
# 1. Existing audio service tests still pass
pytest tests/services/audio/ -v

# 2. New video service tests pass
pytest tests/services/video/ -v

# 3. Core organizer tests pass
pytest tests/core/ -v

# 4. Full test suite
pytest tests/ -x --timeout=30

# 5. Manual verification
# Create temp dir with sample audio/video files
# Run: file-organizer --dry-run <dir>
# Verify: metadata-based folder structure generated without Ollama models
```

## Resolved Decisions

### Q1: Should video organization use creation_date for year-based folders?

**Decision**: Yes — title and creation_date are the primary organization axes, not resolution. Resolution/duration in the modern day is not a meaningful primary sort key (most videos are 1080p+). Title-first, date-second, resolution as tertiary metadata only. Content-aware classification (tutorial, movie, meeting, etc.) is deferred to the future AI-powered tier.

### Q2: Should we add a tiered processing architecture (`--no-ai` flag)?

**Decision**: Yes — but bigger than a flag. The codebase already has natural processing tiers that should be formalized into a coherent architecture. This PRD implements Tier 1 (filesystem) and Tier 2 (lightweight metadata) for audio/video. A future PRD should formalize the full tiered model. See the **Tiered Processing Architecture** appendix below for the complete vision.

### Q3: How should screen recordings be detected and organized?

**Decision**: Filename pattern matching. Research shows that every major screen recording tool uses distinctive default filenames:

| Tool | Default Pattern | Example |
|------|----------------|---------|
| macOS QuickTime | `Screen Recording {date} at {time}` | `Screen Recording 2025-01-15 at 3.45.22 PM.mov` |
| OBS Studio | `{YYYY-MM-DD HH-MM-SS}` | `2025-01-15 14-05-32.mkv` |
| Xbox Game Bar | `{AppName} {YYYY-MM-DD HH-MM-SS}` | `Firefox 2025-01-15 14-05-32.mp4` |
| ShareX | `{ProcessName}_{random10}` | `firefox_3HnsyZ5Npt.mp4` |
| Camtasia | `Capture{NN}` | `Capture05.trec` |
| Snipping Tool | `Screenshot ({N})` or `Screen Recording {date}` | `Screen Recording 2025-01-15 143022.mp4` |

Implementation: regex-based `is_screen_recording(filename)` helper in VideoOrganizer. Screen recordings route to `Screen_Recordings/{Year}/`. See requirement R3a.

## Open Questions

| Question | Owner | Status |
|----------|-------|--------|
| Should the tiered processing architecture be a separate PRD or an appendix to this one? | Engineering | Open |
| Should screen recording detection also check video dimensions (e.g. exact monitor resolutions like 2560x1440)? | Engineering | Open |

## Timeline Considerations

- **No hard deadline** — this is a quality-of-life improvement
- **Dependency**: None — all required services already exist
- **Phasing**: This is Phase 1 (metadata-only). Phase 2 (AI content analysis) is a separate PRD
- **Estimated effort**: 2-3 days for implementation + tests
- **Risk**: Low — reusing proven audio services, video metadata extraction is straightforward

---

## Appendix: Tiered Processing Architecture

This PRD implements Tiers 1-2 for audio/video. The following documents the full architecture that already exists across the codebase and should be formalized in a future PRD.

### Tier 1: Filesystem Only (Zero Dependencies)
**Always available. Instant. No optional deps required.**

- File extension detection and categorization (48+ types)
- File size, modification timestamps, creation date
- Filename pattern parsing (dates, versions, naming conventions)
- Directory structure analysis

**Used by**: All file types as a baseline.

### Tier 2: Lightweight Metadata Parsing (Optional Libraries)
**Sub-second per file. No ML models. Optional deps: mutagen, tinytag, opencv, Pillow, PyMuPDF, python-docx.**

- Audio: ID3 tags, Vorbis comments, M4A metadata (artist, album, genre, duration, bitrate)
- Video: Container metadata (resolution, duration, fps, codec, creation_date)
- Images: EXIF data, dimensions, color mode
- Documents: Text extraction from PDF (up to 5 pages), DOCX, XLSX, PPTX, EPUB
- Archives: File listing, structure metadata
- Scientific: HDF5/NetCDF/MATLAB structure inspection
- CAD: Layer, entity, and drawing metadata

**Used by**: Audio organization (this PRD), video organization (this PRD), document text extraction (existing).

### Tier 3: Local ML/Heuristics (No LLM Required)
**Seconds per file. Pattern recognition and classification without Ollama.**

- Audio classification: keyword-based type detection (music/podcast/audiobook/recording/lecture) with confidence scores — 7 content types, ~545 LOC already built
- Pattern analysis: naming convention detection (prefix, date, version, camelCase, snake_case, kebab-case)
- Image deduplication: perceptual hashing (pHash, dHash, aHash) with Hamming distance
- Document deduplication: TF-IDF cosine similarity
- User preference learning: folder preference tracking, naming pattern extraction, confidence scoring with time-decay, conflict resolution
- Content clustering: file grouping by keywords, size ranges, type associations

**Used by**: Audio classifier (this PRD), pattern analyzer (existing), deduplication (existing), intelligence services (existing).

### Tier 4: AI/LLM Processing (Requires Ollama)
**2-20 seconds per file. Deep content understanding.**

- TextModel (Qwen 2.5 3B, ~1.9 GB): file summarization, intelligent folder/filename generation, content categorization
- VisionModel (Qwen 2.5-VL 7B, ~6.0 GB): image description, scene understanding, OCR
- AudioTranscriber (faster-whisper, ~0.1-0.5 GB): speech-to-text, language detection, segment timestamps

**Used by**: Text files (existing), image files (existing). Future: audio content analysis, video content classification.

### Tier 5: Heavy Compute (GPU/ffmpeg)
**Variable time. Computationally intensive.**

- Video scene detection: content-aware, threshold, adaptive, histogram methods (OpenCV + scenedetect)
- Audio preprocessing: format conversion, normalization, splitting (pydub + ffmpeg)
- Video frame extraction: multi-frame key scene capture

**Used by**: Scene detection (existing, optional). Future: video content analysis.

### Design Principle: Graceful Degradation

Each tier falls back to the tier below if its dependencies are unavailable:

```
Tier 5 unavailable → Tier 4 handles it (or skips heavy analysis)
Tier 4 unavailable → Tier 3 uses heuristics + patterns
Tier 3 unavailable → Tier 2 uses raw metadata
Tier 2 unavailable → Tier 1 uses filesystem only
Tier 1 always works → basic extension-based organization
```

This PRD adds the Tier 1→2→3 path for audio/video. The existing text/image pipeline is Tier 1→2→4. A future `--processing-level` flag (or automatic detection) could let users choose their ceiling tier.
