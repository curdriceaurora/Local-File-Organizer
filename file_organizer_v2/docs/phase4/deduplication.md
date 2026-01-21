# Deduplication Guide

> **Phase 4 Feature** - Advanced duplicate detection using hash-based, perceptual, and semantic algorithms.

## Overview

File Organizer v2 provides three powerful deduplication strategies to help you reclaim storage space and maintain a clean file system:

1. **Hash-Based Deduplication** (#46) - Fast, byte-perfect duplicate detection
2. **Perceptual Image Deduplication** (#47) - Find visually similar images
3. **Semantic Document Deduplication** (#48) - Detect similar documents by content meaning

## Quick Start

### Hash-Based Deduplication

Perfect for finding exact duplicates:

```bash
# Interactive mode with dry-run preview
python -m file_organizer.cli.dedupe ~/Downloads --dry-run

# Automatically keep oldest files
python -m file_organizer.cli.dedupe ~/Downloads --strategy oldest

# Batch mode for automated cleanup
python -m file_organizer.cli.dedupe ~/Downloads --strategy newest --batch
```

### Perceptual Image Deduplication

Find visually similar images even if they've been edited:

```python
from file_organizer.services.deduplication import ImageDeduplicator
from pathlib import Path

# Initialize deduplicator
deduper = ImageDeduplicator()

# Find similar images
directory = Path("~/Pictures")
duplicates = deduper.find_duplicates(
    directory,
    similarity_threshold=0.90,  # 90% similarity
    algorithm="dhash"           # or "phash", "whash"
)

# Review and remove duplicates
for group in duplicates:
    print(f"Found {len(group)} similar images:")
    for img in group:
        print(f"  - {img.path} (quality: {img.quality_score})")

    # Keep highest quality image
    best = max(group, key=lambda x: x.quality_score)
    to_remove = [img for img in group if img != best]
```

### Semantic Document Deduplication

Find documents with similar content:

```python
from file_organizer.services.deduplication import DocumentDeduplicator
from pathlib import Path

# Initialize with text model
deduper = DocumentDeduplicator(model_name="qwen2.5:3b")

# Find semantically similar documents
directory = Path("~/Documents")
duplicates = deduper.find_similar_documents(
    directory,
    similarity_threshold=0.85,   # 85% semantic similarity
    recursive=True
)

# Review duplicates
for group in duplicates:
    print(f"\nSimilar documents found:")
    for doc in group:
        print(f"  - {doc.path}")
        print(f"    Summary: {doc.summary}")
        print(f"    Similarity: {doc.similarity_score:.2%}")
```

## Hash-Based Deduplication

### How It Works

Hash-based deduplication calculates cryptographic hashes (MD5 or SHA256) of file contents. Files with identical hashes are exact duplicates.

**Advantages:**
- Extremely fast and accurate
- Works with any file type
- Minimal memory usage
- No false positives

**Limitations:**
- Only finds byte-perfect duplicates
- Won't detect similar files (e.g., edited photos)

### CLI Usage

#### Basic Commands

```bash
# Scan directory for duplicates
python -m file_organizer.cli.dedupe /path/to/directory

# Use faster MD5 algorithm
python -m file_organizer.cli.dedupe ~/Downloads --algorithm md5

# Non-recursive scan (current directory only)
python -m file_organizer.cli.dedupe ~/Downloads --no-recursive
```

#### Selection Strategies

**Manual Selection (Default)**
```bash
python -m file_organizer.cli.dedupe ~/Documents --strategy manual
```
Interactively choose which files to keep for each duplicate group.

**Keep Oldest**
```bash
python -m file_organizer.cli.dedupe ~/Downloads --strategy oldest
```
Automatically keeps the file with the oldest modification time.

**Keep Newest**
```bash
python -m file_organizer.cli.dedupe ~/Downloads --strategy newest
```
Automatically keeps the file with the newest modification time.

**Keep Largest**
```bash
python -m file_organizer.cli.dedupe ~/Videos --strategy largest
```
Keeps the largest file (useful for media files).

**Keep Smallest**
```bash
python -m file_organizer.cli.dedupe ~/Documents --strategy smallest
```
Keeps the smallest file.

#### Filters

**Size Filters**
```bash
# Only files larger than 1MB
python -m file_organizer.cli.dedupe ~/Downloads --min-size 1048576

# Files between 1MB and 100MB
python -m file_organizer.cli.dedupe ~/Downloads \
    --min-size 1048576 \
    --max-size 104857600
```

**Pattern Filters**
```bash
# Only process image files
python -m file_organizer.cli.dedupe ~/Pictures \
    --include "*.jpg" \
    --include "*.png" \
    --include "*.gif"

# Exclude temporary files
python -m file_organizer.cli.dedupe ~/Documents \
    --exclude "*.tmp" \
    --exclude "*.cache"
```

#### Safety Features

**Dry Run (Recommended First Step)**
```bash
python -m file_organizer.cli.dedupe ~/Downloads --dry-run
```
Preview what would be removed without actually deleting files.

**Safe Mode (Default)**
```bash
python -m file_organizer.cli.dedupe ~/Downloads
```
Creates backups in `.file_organizer_backups/` before deletion.

**Disable Safe Mode (Not Recommended)**
```bash
python -m file_organizer.cli.dedupe ~/Downloads --no-safe-mode
```
⚠️ **Warning:** Deleted files cannot be recovered without backups.

### Python API

```python
from file_organizer.services.deduplication import HashDeduplicator
from pathlib import Path

# Initialize deduplicator
deduper = HashDeduplicator(algorithm="sha256")

# Find duplicates
directory = Path("~/Downloads")
duplicates = deduper.find_duplicates(
    directory,
    recursive=True,
    min_size=1024,  # Skip files < 1KB
)

# Process duplicates
for file_hash, files in duplicates.items():
    print(f"\nDuplicate group (hash: {file_hash[:16]}...):")
    for file_path in files:
        size = file_path.stat().st_size
        mtime = file_path.stat().st_mtime
        print(f"  - {file_path} ({size} bytes, modified {mtime})")

    # Keep oldest, remove rest
    oldest = min(files, key=lambda f: f.stat().st_mtime)
    to_remove = [f for f in files if f != oldest]

    for f in to_remove:
        print(f"  Removing: {f}")
        # f.unlink()  # Uncomment to actually delete
```

## Perceptual Image Deduplication

### How It Works

Perceptual hashing analyzes image visual content to find similar images, even if they've been:
- Resized
- Compressed
- Slightly edited
- Color-adjusted
- Cropped

**Algorithms:**
- **dHash (Difference Hash)**: Fast, good for basic similarity
- **pHash (Perceptual Hash)**: More accurate, handles transformations better
- **wHash (Wavelet Hash)**: Best for compressed/edited images

### Python API

```python
from file_organizer.services.deduplication import ImageDeduplicator, ImageQualityAnalyzer
from pathlib import Path

# Initialize deduplicator
deduper = ImageDeduplicator()

# Find similar images
directory = Path("~/Pictures")
duplicates = deduper.find_duplicates(
    directory,
    similarity_threshold=0.90,  # 90% similarity
    algorithm="phash",          # Use perceptual hash
    recursive=True
)

# Quality-based selection
quality_analyzer = ImageQualityAnalyzer()

for group in duplicates:
    # Analyze quality for each image
    analyzed = []
    for img_path in group:
        quality = quality_analyzer.analyze(img_path)
        analyzed.append((img_path, quality))

    # Keep highest quality, remove rest
    best = max(analyzed, key=lambda x: x[1].overall_score)
    to_remove = [img for img, _ in analyzed if img != best[0]]

    print(f"\nKeeping: {best[0]} (quality: {best[1].overall_score:.2f})")
    for img in to_remove:
        print(f"  Removing: {img}")
```

### Quality Metrics

The `ImageQualityAnalyzer` evaluates images based on:
- **Resolution**: Higher resolution = better quality
- **Sharpness**: Laplacian variance for edge detection
- **Compression**: JPEG quality factor
- **File size**: Larger = less compression artifacts

```python
from file_organizer.services.deduplication import ImageQualityAnalyzer

analyzer = ImageQualityAnalyzer()
quality = analyzer.analyze(Path("photo.jpg"))

print(f"Overall Score: {quality.overall_score:.2f}")
print(f"Resolution: {quality.resolution_score:.2f}")
print(f"Sharpness: {quality.sharpness_score:.2f}")
print(f"Size: {quality.size_score:.2f}")
```

### Interactive Viewer

View and compare duplicate images visually:

```python
from file_organizer.services.deduplication import ImageViewer

viewer = ImageViewer()

# Display duplicate group
viewer.show_duplicates(
    duplicate_group,
    show_quality=True,
    show_metadata=True
)

# User can interactively:
# - Compare images side-by-side
# - View quality metrics
# - Select which to keep
# - Zoom and pan images
```

## Semantic Document Deduplication

### How It Works

Semantic deduplication uses AI embeddings to understand document content and find semantically similar documents, even if:
- Text is paraphrased
- Format is different
- File names are different
- Minor edits have been made

**Use Cases:**
- Find duplicate reports with different file names
- Detect near-duplicate documents
- Identify similar meeting notes
- Consolidate related content

### Python API

```python
from file_organizer.services.deduplication import DocumentDeduplicator
from pathlib import Path

# Initialize with text model
deduper = DocumentDeduplicator(
    model_name="qwen2.5:3b",
    embedding_dim=768
)

# Find similar documents
directory = Path("~/Documents")
duplicates = deduper.find_similar_documents(
    directory,
    similarity_threshold=0.85,   # 85% semantic similarity
    recursive=True,
    file_extensions=[".txt", ".md", ".pdf", ".docx"]
)

# Process results
for group in duplicates:
    print(f"\nSimilar documents ({len(group)} files):")

    # Get representative document (highest word count)
    primary = max(group, key=lambda d: d.word_count)

    print(f"Primary: {primary.path}")
    print(f"Summary: {primary.summary}")

    for doc in group:
        if doc != primary:
            print(f"\n  Similar: {doc.path}")
            print(f"  Similarity: {doc.similarity_score:.2%}")
            print(f"  Preview: {doc.preview[:100]}...")
```

### Supported File Types

- Plain text (`.txt`, `.md`)
- PDF documents
- Word documents (`.docx`)
- Rich text (`.rtf`)
- HTML files

### Advanced Features

**Custom Similarity Function**
```python
def custom_similarity(doc1, doc2):
    """Custom similarity calculation."""
    # Weight different factors
    semantic_sim = doc1.semantic_similarity(doc2)
    title_sim = doc1.title_similarity(doc2)

    return 0.8 * semantic_sim + 0.2 * title_sim

deduper.similarity_function = custom_similarity
```

**Incremental Processing**
```python
# Build index incrementally for large datasets
deduper = DocumentDeduplicator()

# Add documents in batches
for batch_dir in [dir1, dir2, dir3]:
    deduper.add_documents(batch_dir)

# Find duplicates across all batches
duplicates = deduper.get_duplicates(threshold=0.85)
```

## Best Practices

### 1. Always Start with Dry Run
```bash
python -m file_organizer.cli.dedupe ~/Downloads --dry-run
```

### 2. Use Appropriate Algorithm

- **Hash-based**: Exact duplicates, any file type
- **Perceptual**: Similar images, photos
- **Semantic**: Similar documents, text files

### 3. Adjust Thresholds Carefully

```python
# Conservative (fewer false positives)
duplicates = deduper.find_duplicates(similarity_threshold=0.95)

# Aggressive (more duplicates found)
duplicates = deduper.find_duplicates(similarity_threshold=0.80)
```

### 4. Review Before Deleting

Always review duplicate groups before deletion, especially with perceptual and semantic methods.

### 5. Keep Backups

Enable safe mode or maintain separate backups:
```bash
python -m file_organizer.cli.dedupe ~/Documents  # Safe mode enabled by default
```

## Troubleshooting

### Hash-Based Issues

**"No duplicates found" but I know there are duplicates**
- Check file permissions
- Try `--recursive` flag
- Verify you're scanning correct directory

**Process is very slow**
- Use MD5 instead of SHA256: `--algorithm md5`
- Use size filters: `--min-size 1048576`
- Process smaller directories separately

### Perceptual Issues

**Too many false positives**
- Increase similarity threshold: `similarity_threshold=0.95`
- Try different algorithm: `algorithm="dhash"`
- Use quality-based filtering

**Missing similar images**
- Lower similarity threshold: `similarity_threshold=0.85`
- Try pHash: `algorithm="phash"`
- Check image formats are supported

### Semantic Issues

**Documents not being matched**
- Lower similarity threshold
- Verify file types are supported
- Check document content isn't empty
- Ensure AI model is running (Ollama)

**Too many false matches**
- Increase similarity threshold to 0.90+
- Use more sophisticated similarity function
- Filter by document type/category

## Performance Tips

### Hash-Based
1. Use MD5 for local deduplication (faster)
2. Use size filters to reduce file count
3. Process directories separately
4. Use batch mode for automation

### Perceptual
1. Use dHash for speed, pHash for accuracy
2. Process images in batches
3. Cache computed hashes
4. Use GPU acceleration if available

### Semantic
1. Use smaller embedding models for speed
2. Process documents in batches
3. Cache embeddings for reuse
4. Use incremental indexing for large datasets

## API Reference

### HashDeduplicator

```python
class HashDeduplicator:
    def __init__(self, algorithm: str = "sha256"):
        """Initialize hash deduplicator.

        Args:
            algorithm: 'md5' or 'sha256'
        """

    def find_duplicates(
        self,
        directory: Path,
        recursive: bool = True,
        min_size: int = 0,
        max_size: Optional[int] = None,
    ) -> Dict[str, List[Path]]:
        """Find duplicate files by hash."""
```

### ImageDeduplicator

```python
class ImageDeduplicator:
    def __init__(self):
        """Initialize image deduplicator."""

    def find_duplicates(
        self,
        directory: Path,
        similarity_threshold: float = 0.90,
        algorithm: str = "dhash",
        recursive: bool = True,
    ) -> List[List[ImageInfo]]:
        """Find visually similar images."""
```

### DocumentDeduplicator

```python
class DocumentDeduplicator:
    def __init__(
        self,
        model_name: str = "qwen2.5:3b",
        embedding_dim: int = 768,
    ):
        """Initialize document deduplicator."""

    def find_similar_documents(
        self,
        directory: Path,
        similarity_threshold: float = 0.85,
        recursive: bool = True,
        file_extensions: Optional[List[str]] = None,
    ) -> List[List[DocumentInfo]]:
        """Find semantically similar documents."""
```

## Examples

See [Usage Examples](./examples.md) for more detailed examples and use cases.

## Related Documentation

- [CLI Deduplication Guide](../CLI_DEDUPE.md) - CLI-specific documentation
- [Image Deduplication README](../../src/file_organizer/services/deduplication/README_IMAGE_DEDUP.md)
- [Viewer Documentation](../../src/file_organizer/services/deduplication/VIEWER_README.md)
- [Intelligence Guide](./intelligence.md) - Learn from deduplication patterns
- [Analytics Guide](./analytics.md) - Track storage savings
