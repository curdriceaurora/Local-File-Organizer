---
issue: 48
title: Add semantic similarity for document deduplication
analyzed: 2026-01-21T06:20:56Z
estimated_hours: 24
parallelization_factor: 2.4
---

# Parallel Work Analysis: Issue #48

## Overview
Implement semantic similarity detection for documents using TF-IDF vectorization and cosine similarity. This integrates with existing hash-based (#46) and image perceptual (#47) deduplication to create a unified deduplication system. The system extracts text from multiple formats (PDF, DOCX, TXT, RTF, ODT), generates embeddings, computes similarity, and provides comprehensive storage reclamation reporting.

## Parallel Streams

### Stream A: Text Extraction Module
**Scope**: Extract text content from various document formats
**Files**:
- `file_organizer/services/deduplication/extractor.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 5 hours
**Dependencies**: none

**Deliverables**:
- DocumentExtractor class
- PDF text extraction (PyPDF2)
- DOCX text extraction (python-docx)
- TXT/RTF/ODT support
- Error handling for corrupt files
- Batch extraction capabilities
- UTF-8 encoding support

### Stream B: Embedding & Similarity Engine
**Scope**: TF-IDF vectorization and cosine similarity computation
**Files**:
- `file_organizer/services/deduplication/embedder.py`
- `file_organizer/services/deduplication/semantic.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 9 hours
**Dependencies**: none

**Deliverables**:
- DocumentEmbedder class with TF-IDF
- Configurable parameters (max_features, ngram_range, min_df)
- Embedding caching for performance
- SemanticAnalyzer class
- Cosine similarity computation
- Similarity threshold configuration
- Document clustering by similarity
- Efficient pairwise comparison for large datasets

### Stream C: Integration & Reporting
**Scope**: Integrate with existing deduplication, unified reporting
**Files**:
- `file_organizer/services/deduplication/document_dedup.py`
- `file_organizer/services/deduplication/reporter.py`
- `file_organizer/services/deduplication/__init__.py`
**Agent Type**: fullstack-specialist
**Can Start**: after Streams A and B complete
**Estimated Hours**: 7 hours
**Dependencies**: Streams A, B

**Deliverables**:
- DocumentDeduplicator orchestrator class
- Integration with hash-based deduplication (#46)
- Integration with image deduplication (#47)
- StorageReporter class
- Storage reclamation calculator
- CSV/JSON export functionality
- Unified duplicate reports
- CLI integration with existing dedupe commands

### Stream D: Testing & Documentation
**Scope**: Comprehensive testing and documentation
**Files**:
- `tests/services/deduplication/test_extractor.py`
- `tests/services/deduplication/test_embedder.py`
- `tests/services/deduplication/test_semantic.py`
- `tests/services/deduplication/test_document_dedup.py`
- `tests/integration/test_semantic_dedup_e2e.py`
**Agent Type**: fullstack-specialist
**Can Start**: after Stream C completes
**Estimated Hours**: 3 hours
**Dependencies**: Stream C

**Deliverables**:
- Unit tests for all classes (>85% coverage)
- Integration tests with real document datasets
- Performance tests for 1,000+ documents
- Memory profiling and optimization
- Test scenarios (reformatted docs, minor edits, corrupted files)
- Documentation with examples
- API reference documentation

## Coordination Points

### Shared Files
Minimal overlap:
- `file_organizer/services/deduplication/__init__.py` - Stream C updates exports after A, B complete

### Interface Contracts
Define these interfaces upfront:

**DocumentExtractor Interface**:
```python
def extract_text(file_path: Path) -> str
def extract_batch(file_paths: List[Path]) -> Dict[Path, str]
def supports_format(file_path: Path) -> bool
```

**DocumentEmbedder Interface**:
```python
def __init__(max_features: int = 5000, ngram_range: Tuple = (1, 2))
def fit_transform(documents: List[str]) -> np.ndarray
def transform(document: str) -> np.ndarray
def get_feature_names() -> List[str]
```

**SemanticAnalyzer Interface**:
```python
def __init__(threshold: float = 0.85)
def compute_similarity(doc1_vector: np.ndarray, doc2_vector: np.ndarray) -> float
def find_similar_documents(embeddings: np.ndarray, paths: List[Path]) -> Dict
def cluster_by_similarity(duplicates: Dict) -> List[List[Path]]
```

**StorageReporter Interface**:
```python
def calculate_reclamation(duplicate_groups: Dict) -> dict
def generate_report(output_format: str = "text") -> str
def export_to_csv(duplicate_groups: Dict, output_path: Path)
```

### Sequential Requirements
1. Streams A and B can run in parallel
2. Stream C requires both A and B to complete (needs text extraction and similarity analysis)
3. Stream D requires C to complete (needs full integration for testing)

## Conflict Risk Assessment
**Low Risk** - Clear separation between streams:
- Stream A: `extractor.py` only
- Stream B: `embedder.py`, `semantic.py` only
- Stream C: `document_dedup.py`, `reporter.py`, `__init__.py`
- Stream D: `tests/**/*`

## Parallelization Strategy

**Recommended Approach**: hybrid (parallel then sequential)

**Execution Plan**:
1. **Phase 1** (parallel, 9 hours): Launch Streams A and B simultaneously
2. **Phase 2** (sequential, 7 hours): Stream C integrates A and B
3. **Phase 3** (sequential, 3 hours): Stream D tests everything

**Timeline**:
- Streams A & B: 9 hours (parallel, limited by Stream B)
- Stream C: 7 hours (depends on A & B)
- Stream D: 3 hours (depends on C)

Total wall time: ~19 hours

## Expected Timeline

**With parallel execution**:
- Wall time: ~19 hours (max(A,B) + C + D)
- Total work: 24 hours
- Efficiency gain: 21% time savings

**Without parallel execution**:
- Wall time: 24 hours (sequential)

**Parallelization factor**: 2.4x effective speedup for two developers (24h / 10h each)

## Agent Assignment Recommendations

- **Stream A**: Backend developer with document processing experience
- **Stream B**: Backend developer with ML/NLP experience (TF-IDF, scikit-learn)
- **Stream C**: Fullstack developer for integration work
- **Stream D**: QA engineer or fullstack developer for testing

## Notes

### Success Factors
- Streams A and B are completely independent
- Stream C integrates cleanly via defined interfaces
- Dependencies on #46 and #47 are only for integration, not core functionality
- scikit-learn handles TF-IDF complexity

### Risks & Mitigation
- **Risk**: Large documents might cause memory issues
  - **Mitigation**: Stream A chunks large files, Stream B uses sparse matrices
- **Risk**: Integration complexity with #46, #47
  - **Mitigation**: Stream C focuses on clean interfaces, unified API
- **Risk**: TF-IDF might not work well for all document types
  - **Mitigation**: Stream B includes configurable parameters, Stream D validates with diverse documents

### Performance Targets
- Text extraction: >20 documents/second
- TF-IDF vectorization: <5 seconds for 1,000 documents
- Similarity computation: <10 seconds for 1,000 pairwise comparisons
- Memory usage: <2GB for 1,000 document corpus

### Integration Notes
Must integrate with:
- Issue #46: Hash-based deduplication (exact duplicates)
- Issue #47: Image perceptual hashing (similar images)
- Existing DuplicateDetector for unified scanning
- BackupManager for safe deletion

### Dependencies to Install
```bash
pip install scikit-learn>=1.4.0
pip install PyPDF2>=3.0.0
pip install python-docx>=1.0.0
pip install numpy>=1.24.0
```
