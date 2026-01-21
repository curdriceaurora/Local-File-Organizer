---
issue: 47
title: Implement perceptual hashing for similar images
analyzed: 2026-01-21T06:18:33Z
estimated_hours: 24
parallelization_factor: 2.8
---

# Parallel Work Analysis: Issue #47

## Overview
Implement perceptual hashing for detecting visually similar images using imagededup library. The system needs to compute image hashes, detect similarity, assess quality, and provide an interactive comparison UI for users to review and select which duplicates to keep.

## Parallel Streams

### Stream A: Core Image Hashing & Similarity Detection
**Scope**: Backend logic for perceptual hash computation and similarity matching
**Files**:
- `file_organizer/services/deduplication/image_dedup.py`
- `file_organizer/services/deduplication/image_utils.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 10 hours
**Dependencies**: none

**Deliverables**:
- ImageDeduplicator class with imagededup integration
- Support for pHash, dHash, aHash algorithms
- Hamming distance calculation for hash comparison
- Configurable similarity threshold (0-64)
- Image clustering by similarity
- Batch processing for large collections
- Progress tracking callbacks
- Corrupt image handling
- Support for JPEG, PNG, GIF, BMP, TIFF, WebP

### Stream B: Quality Assessment System
**Scope**: Image quality analysis and best-quality selection logic
**Files**:
- `file_organizer/services/deduplication/quality.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 4 hours
**Dependencies**: none

**Deliverables**:
- ImageQualityAnalyzer class
- Quality metrics: resolution, file size, format preference
- Quality scoring algorithm
- Comparison logic (which image is better quality)
- Best quality selection for image groups
- Detection of cropped/edited versions
- Format quality rankings (e.g., PNG > JPEG for certain use cases)

### Stream C: Comparison UI & Interactive Review
**Scope**: Terminal-based UI for reviewing duplicate images
**Files**:
- `file_organizer/services/deduplication/viewer.py`
**Agent Type**: fullstack-specialist
**Can Start**: immediately
**Estimated Hours**: 6 hours
**Dependencies**: none

**Deliverables**:
- ComparisonViewer class
- Terminal-based image preview (ASCII art or external viewer integration)
- Metadata display (dimensions, size, format, modification date)
- Interactive selection interface (keep/delete/skip)
- Side-by-side comparison layout
- Batch review operations
- User decision recording
- Preview using Pillow for cross-platform support

### Stream D: Integration & Testing
**Scope**: Bring components together, comprehensive testing, CLI integration
**Files**:
- `file_organizer/cli/dedupe_images.py` (new CLI subcommand)
- `tests/services/deduplication/test_image_dedup.py`
- `tests/services/deduplication/test_quality.py`
- `tests/services/deduplication/test_viewer.py`
- `tests/integration/test_image_deduplication_e2e.py`
- `file_organizer/services/deduplication/__init__.py` (update exports)
**Agent Type**: fullstack-specialist
**Can Start**: after Streams A, B, and C complete
**Estimated Hours**: 4 hours
**Dependencies**: Streams A, B, C

**Deliverables**:
- CLI subcommand for image deduplication
- Unit tests for all classes (>85% coverage)
- Integration tests with diverse image datasets
- Performance benchmarks (1,000+ images)
- Edge case testing (corrupt files, unsupported formats)
- Report generation with statistics
- Documentation with examples

## Coordination Points

### Shared Files
Minimal overlap - only module init file:
- `file_organizer/services/deduplication/__init__.py` - Stream D updates exports after A, B, C complete

### Interface Contracts
To enable parallel work, define these interfaces upfront:

**ImageDeduplicator Interface**:
```python
def __init__(hash_method: str = "phash", threshold: int = 10)
def find_duplicates(directory: Path) -> Dict[str, List[Path]]
def compute_similarity(img1: Path, img2: Path) -> float
def get_image_hash(image_path: Path) -> str
```

**ImageQualityAnalyzer Interface**:
```python
def assess_quality(image_path: Path) -> float
def compare_quality(img1: Path, img2: Path) -> int  # Returns -1, 0, 1
def get_best_quality(images: List[Path]) -> Path
def get_quality_metrics(image_path: Path) -> dict
```

**ComparisonViewer Interface**:
```python
def show_comparison(images: List[Path]) -> Path
def batch_review(duplicate_groups: Dict) -> Dict[Path, str]
def display_metadata(image_path: Path) -> None
def interactive_select(images: List[Path]) -> List[Path]  # Returns images to keep
```

### Sequential Requirements
1. Streams A, B, C can all run in parallel
2. Stream D (integration/testing) must wait for A, B, C to complete
3. Interface contracts must be agreed upon before starting

## Conflict Risk Assessment
**Low Risk** - Streams work on completely different files:
- Stream A: `image_dedup.py`, `image_utils.py`
- Stream B: `quality.py`
- Stream C: `viewer.py`
- Stream D: `cli/dedupe_images.py`, `tests/**/*`, `__init__.py` (update only)

No shared implementation files between A, B, and C.

## Parallelization Strategy

**Recommended Approach**: parallel with final integration

**Execution Plan**:
1. **Pre-work** (0.5 hours): Define and document interface contracts
2. **Phase 1** (parallel, 10 hours): Launch Streams A, B, C simultaneously
3. **Phase 2** (sequential, 4 hours): Stream D integrates and tests

**Timeline**:
- Stream A: 10 hours (longest)
- Stream B: 4 hours (completes early)
- Stream C: 6 hours (completes early)
- Stream D: 4 hours (after Phase 1)

Total wall time: ~14.5 hours (including coordination)

## Expected Timeline

**With parallel execution**:
- Wall time: ~14.5 hours (pre-work + max(A,B,C) + D)
- Total work: 24 hours
- Efficiency gain: 40% time savings

**Without parallel execution**:
- Wall time: 24 hours (sequential completion)

**Parallelization factor**: 2.8x effective speedup (24h / 8.6h actual per developer)

## Agent Assignment Recommendations

- **Stream A**: Senior backend developer with image processing experience
- **Stream B**: Backend developer familiar with quality metrics
- **Stream C**: Fullstack developer with UI/UX experience
- **Stream D**: QA engineer or full-stack developer for testing and integration

## Notes

### Success Factors
- Clear interface contracts prevent integration issues
- Streams A, B, C are completely independent - no coordination needed during development
- Stream D benefits from having all components ready for comprehensive testing
- imagededup library handles the complex perceptual hashing internally

### Risks & Mitigation
- **Risk**: imagededup library compatibility or performance issues
  - **Mitigation**: Stream A validates library early, includes performance benchmarks
- **Risk**: Terminal image preview might not work on all platforms
  - **Mitigation**: Stream C provides fallback to external viewer or metadata-only display
- **Risk**: Quality assessment might be subjective
  - **Mitigation**: Stream B implements configurable weighting for quality factors

### Performance Targets
- Hash computation: >50 images/second for typical photos
- Similarity detection: <1 second for 1,000 image comparisons
- Quality assessment: <100ms per image
- UI responsiveness: Interactive review with no lag

### Integration Points
This task integrates with:
- Issue #46 (hash-based deduplication) - shares deduplication service directory
- Existing FileOrganizer service for directory scanning
- CLI framework for new image dedupe subcommand
- BackupManager (from #46) for safe deletion with backups

### Dependencies to Install
Required Python packages:
- `imagededup>=0.3.0` - Perceptual hashing
- `Pillow>=10.0.0` - Image processing
- `numpy>=1.24.0` - Numerical operations

Optional:
- `termplotlib` or `rich` for enhanced terminal display

### Test Data Requirements
Stream D should create/use diverse test image sets:
- Exact duplicates with different names
- Resized versions (various resolutions)
- JPEG quality variations
- Cropped images
- Color-adjusted images
- Mixed formats (PNG, JPEG, GIF, WebP)
- Corrupt/unreadable files
- Large collections (1,000+ images for performance testing)
