# Plan: Audio & Video Metadata-Based Organization

## Context

Audio files are currently **skipped** in the core organizer (`organizer.py:217`), and video files use the heavy VisionProcessor AI model (`organizer.py:194`). The user wants a **lightweight, quick-win** approach: organize audio/video using **metadata parsing only** (ID3 tags, container metadata) — no AI transcription or vision model processing. Content-aware AI processing is deferred to a future release.

**Key insight**: The audio metadata pipeline (extractor, classifier, organizer) is **already fully implemented** — it just needs to be wired into the core organizer. Video needs a new lightweight metadata extractor.

---

## Step 1: Create VideoMetadataExtractor

**New file**: `src/file_organizer/services/video/metadata_extractor.py`

- `VideoMetadata` dataclass: `file_path`, `file_size`, `format`, `duration`, `width`, `height`, `fps`, `codec`, `bitrate`, `creation_date`
- `VideoMetadataExtractor` class using `cv2.VideoCapture` (opencv already an optional dep)
  - `extract(video_path) -> VideoMetadata` — reads container metadata via OpenCV
  - `extract_batch(paths) -> list[VideoMetadata]`
  - Graceful fallback if opencv unavailable: populate only file_size/format from filesystem
- Helper: `resolution_label(width, height) -> str` — returns "4k", "1080p", "720p", "480p", "sd"

**Pattern**: Follow `AudioMetadataExtractor` structure closely.

---

## Step 2: Create VideoOrganizer

**New file**: `src/file_organizer/services/video/organizer.py`

- `VideoOrganizer` class with template-based path generation
- Default templates by resolution:
  - `4K_Videos/{Filename}`, `HD_Videos/{Filename}`, `SD_Videos/{Filename}`
  - Short clips (<60s): `Short_Clips/{Filename}`
- `generate_path(metadata: VideoMetadata) -> tuple[str, str]` — returns (folder_name, filename)
- Reuse `sanitize_filename` from `utils/text_processing.py`

---

## Step 3: Update `services/video/__init__.py`

Export new classes: `VideoMetadata`, `VideoMetadataExtractor`, `VideoOrganizer`

---

## Step 4: Wire Audio into Core Organizer

**Modify**: `src/file_organizer/core/organizer.py`

- Add `_process_audio_files(files: list[Path]) -> list[ProcessedFile]` method:
  1. Import `AudioMetadataExtractor`, `AudioClassifier`, `AudioOrganizer` from `services.audio`
  2. For each audio file: extract metadata → classify → generate folder/filename via AudioOrganizer templates
  3. Return `ProcessedFile` objects (reusing existing dataclass) with `folder_name` and `filename` set from metadata
  4. Graceful error handling: if mutagen/tinytag unavailable, return error ProcessedFile
- Remove audio from `unsupported` list (line 217)
- Call `_process_audio_files()` in the `organize()` method between image and video processing
- Update `_show_file_breakdown()`: change audio status from "⊘ Skip (needs audio model)" to "✓ Will process (metadata)"
- No AI model initialization needed for audio files

---

## Step 5: Wire Video Metadata into Core Organizer

**Modify**: `src/file_organizer/core/organizer.py`

- Add `_process_video_files(files: list[Path]) -> list[ProcessedFile]` method:
  1. Import `VideoMetadataExtractor`, `VideoOrganizer` from `services.video`
  2. For each video file: extract metadata → generate folder/filename based on resolution/duration
  3. Return `ProcessedFile` objects
  4. Graceful fallback: if opencv unavailable, place in "Videos/Unsorted/" folder
- Replace current video processing (line 194 `_process_image_files(video_files)`) with `_process_video_files(video_files)`
- Video no longer requires VisionProcessor initialization — only init VisionProcessor for `image_files` (not `image_files or video_files`)
- Update `_show_file_breakdown()`: change video status to "✓ Will process (metadata)"

---

## Step 6: Add `pymediainfo` as Optional Dependency (lightweight alternative)

**Modify**: `pyproject.toml`

- Add `pymediainfo>=6.0.0` to `video` optional deps as a richer fallback for video metadata
- Keep opencv as primary (already declared)

---

## Step 7: Tests

### New test files:
- `tests/services/video/test_metadata_extractor.py` — VideoMetadata, extraction with/without opencv, resolution_label helper
- `tests/services/video/test_video_organizer.py` — template generation, short clips, resolution-based folders
- `tests/core/test_audio_video_integration.py` — core organizer processes audio/video files via metadata path

### Test approach:
- Mock `cv2.VideoCapture` for video metadata tests (no real video files needed)
- Mock `AudioMetadataExtractor` for audio integration tests
- Test graceful fallback when optional deps unavailable
- Test ProcessedFile output format matches what `_organize_files()` expects

---

## Files Modified (Summary)

| File | Action |
|------|--------|
| `src/file_organizer/services/video/metadata_extractor.py` | **CREATE** — VideoMetadata + VideoMetadataExtractor |
| `src/file_organizer/services/video/organizer.py` | **CREATE** — VideoOrganizer with templates |
| `src/file_organizer/services/video/__init__.py` | **MODIFY** — export new classes |
| `src/file_organizer/core/organizer.py` | **MODIFY** — add `_process_audio_files()`, `_process_video_files()`, remove audio/video from unsupported |
| `pyproject.toml` | **MODIFY** — add pymediainfo optional dep |
| `tests/services/video/__init__.py` | **CREATE** — empty init |
| `tests/services/video/test_metadata_extractor.py` | **CREATE** — video metadata tests |
| `tests/services/video/test_video_organizer.py` | **CREATE** — video organizer tests |
| `tests/core/test_audio_video_integration.py` | **CREATE** — integration tests |

## Existing Code Reused

| Component | Location | Purpose |
|-----------|----------|---------|
| `AudioMetadataExtractor` | `services/audio/metadata_extractor.py` | Extract audio tags (already built) |
| `AudioClassifier` | `services/audio/classifier.py` | Classify audio type (already built) |
| `AudioOrganizer` | `services/audio/organizer.py` | Generate audio folder paths (already built) |
| `ProcessedFile` | `services/text_processor.py` | Standard result dataclass |
| `sanitize_filename` | `utils/text_processing.py` | Clean generated filenames |
| `ParallelProcessor` | `parallel/processor.py` | Batch processing with progress |

---

## Verification

1. Run existing audio service tests: `pytest tests/services/audio/ -v`
2. Run new video service tests: `pytest tests/services/video/ -v`
3. Run core organizer tests: `pytest tests/core/ -v`
4. Run full test suite: `pytest tests/ -x --timeout=30`
5. Manual verification: create a temp dir with sample audio/video files, run `file-organizer --dry-run` and verify metadata-based folder structure is generated without requiring Ollama models
