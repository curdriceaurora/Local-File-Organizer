# Image Deduplication Module

Perceptual hashing-based image duplicate detection for finding visually similar images.

## Overview

The `image_dedup` module uses perceptual hashing algorithms to detect duplicate and visually similar images. Unlike cryptographic hashing (MD5, SHA256), perceptual hashing creates similar hashes for visually similar images, even if they have different:

- File sizes
- Resolutions
- Compression levels
- Minor edits or adjustments
- File formats (JPEG vs PNG)

## Features

- **Multiple Hash Algorithms**: pHash, dHash, aHash
- **Configurable Similarity**: Adjustable Hamming distance threshold
- **Batch Processing**: Efficient processing of large image collections
- **Progress Tracking**: Callback support for UI/CLI progress indicators
- **Error Handling**: Graceful handling of corrupt or unreadable images
- **Format Support**: JPEG, PNG, GIF, BMP, TIFF, WebP
- **Quality Assessment**: Helper utilities for selecting best quality duplicates

## Installation

The module requires the `imagededup` library:

```bash
pip install imagededup>=0.3.0
```

Additional dependencies (automatically installed):
- Pillow (PIL fork) for image processing
- NumPy for numerical operations
- scikit-learn, scipy, matplotlib (imagededup dependencies)

## Quick Start

```python
from pathlib import Path
from file_organizer.services.deduplication import ImageDeduplicator

# Create deduplicator
deduper = ImageDeduplicator(hash_method="phash", threshold=10)

# Find duplicates in a directory
duplicates = deduper.find_duplicates(Path("./images"), recursive=True)

# Display results
for hash_key, images in duplicates.items():
    print(f"Found {len(images)} similar images:")
    for img in images:
        print(f"  - {img}")
```

## Hash Methods

### pHash (Perceptual Hash) - **Recommended**
- Best for general similarity detection
- Robust to minor edits, compression, resizing
- Slower but most accurate
- Good for finding images that "look similar"

```python
deduper = ImageDeduplicator(hash_method="phash", threshold=10)
```

### dHash (Difference Hash)
- Fast computation
- Good for detecting resized images
- Tracks gradients between pixels
- Best for finding scaled versions

```python
deduper = ImageDeduplicator(hash_method="dhash", threshold=10)
```

### aHash (Average Hash)
- Fastest algorithm
- Good for exact duplicates and minor variations
- Less robust to major changes
- Best for quick scanning

```python
deduper = ImageDeduplicator(hash_method="ahash", threshold=10)
```

## Similarity Threshold

The threshold parameter controls how strict the matching is. It represents the maximum Hamming distance (number of differing bits) between two hashes.

| Threshold | Strictness | Use Case |
|-----------|------------|----------|
| 0-5 | Very Strict | Exact duplicates with minor compression |
| 6-10 | Strict | Same image resized or re-compressed |
| 11-15 | Moderate | Similar images with edits or crops |
| 16-20 | Loose | Images with significant variations |
| 21+ | Very Loose | Potentially different images |

**Default: 10** (good balance for most use cases)

```python
# Strict matching - only near-identical images
strict_deduper = ImageDeduplicator(threshold=5)

# Loose matching - catch more variations
loose_deduper = ImageDeduplicator(threshold=15)
```

## Core API

### ImageDeduplicator

Main class for image duplicate detection.

#### Methods

##### `__init__(hash_method="phash", threshold=10)`
Initialize the deduplicator.

**Parameters:**
- `hash_method` (str): Hash algorithm - "phash", "dhash", or "ahash"
- `threshold` (int): Maximum Hamming distance (0-64)

**Raises:**
- `ValueError`: Invalid hash method or threshold

---

##### `find_duplicates(directory, recursive=True, progress_callback=None)`
Find duplicate images in a directory.

**Parameters:**
- `directory` (Path): Directory to scan
- `recursive` (bool): Search subdirectories
- `progress_callback` (callable): Function(current, total) for progress updates

**Returns:**
- `Dict[str, List[Path]]`: Groups of similar images keyed by representative hash

**Example:**
```python
def progress(current, total):
    print(f"Processing: {current}/{total}")

duplicates = deduper.find_duplicates(
    Path("./photos"),
    recursive=True,
    progress_callback=progress
)
```

---

##### `compute_similarity(img1, img2)`
Calculate similarity score between two images.

**Parameters:**
- `img1` (Path): First image path
- `img2` (Path): Second image path

**Returns:**
- `float`: Similarity from 0.0 (different) to 1.0 (identical), or None if error

**Example:**
```python
similarity = deduper.compute_similarity(
    Path("photo1.jpg"),
    Path("photo2.jpg")
)
if similarity > 0.9:
    print("Images are very similar!")
```

---

##### `cluster_by_similarity(images, progress_callback=None)`
Group images into clusters of similar images.

**Parameters:**
- `images` (List[Path]): List of image paths
- `progress_callback` (callable): Progress callback function

**Returns:**
- `List[List[Path]]`: List of image clusters (groups)

**Example:**
```python
images = list(Path("./photos").glob("*.jpg"))
clusters = deduper.cluster_by_similarity(images)

for i, cluster in enumerate(clusters, 1):
    print(f"Cluster {i}: {len(cluster)} images")
```

---

##### `batch_compute_hashes(image_paths, progress_callback=None)`
Compute hashes for multiple images.

**Parameters:**
- `image_paths` (List[Path]): Images to hash
- `progress_callback` (callable): Progress callback

**Returns:**
- `Dict[Path, str]`: Mapping of paths to their perceptual hashes

---

##### `get_image_hash(image_path)`
Compute hash for a single image.

**Parameters:**
- `image_path` (Path): Image file path

**Returns:**
- `str`: Perceptual hash (hex string), or None if error

---

##### `compute_hamming_distance(hash1, hash2)`
Calculate Hamming distance between two hashes.

**Parameters:**
- `hash1` (str): First hash
- `hash2` (str): Second hash

**Returns:**
- `int`: Number of differing bits (0-64)

---

##### `validate_image(image_path)`
Check if an image can be processed.

**Parameters:**
- `image_path` (Path): Image to validate

**Returns:**
- `Tuple[bool, Optional[str]]`: (is_valid, error_message)

## Utility Functions

### Image Metadata

```python
from file_organizer.services.deduplication import get_image_metadata

metadata = get_image_metadata(Path("photo.jpg"))
print(f"Size: {metadata.width}x{metadata.height}")
print(f"Format: {metadata.format}")
print(f"File size: {metadata.size_bytes} bytes")
```

### Image Validation

```python
from file_organizer.services.deduplication import validate_image_file

is_valid, error = validate_image_file(Path("photo.jpg"))
if is_valid:
    print("Image is valid")
else:
    print(f"Invalid: {error}")
```

### Best Quality Selection

```python
from file_organizer.services.deduplication import get_best_quality_image

# Given a list of duplicate images
images = [Path("photo1.jpg"), Path("photo2.png"), Path("photo3.jpg")]

# Select the one with best quality (resolution, format, file size)
best = get_best_quality_image(images)
print(f"Keep: {best}")
```

### Format File Size

```python
from file_organizer.services.deduplication import format_file_size

size = 1536 * 1024  # bytes
print(format_file_size(size))  # Output: "1.5 MB"
```

## Usage Patterns

### Pattern 1: Basic Duplicate Detection

```python
from pathlib import Path
from file_organizer.services.deduplication import ImageDeduplicator

deduper = ImageDeduplicator(hash_method="phash", threshold=10)
duplicates = deduper.find_duplicates(Path("./photos"))

print(f"Found {len(duplicates)} groups of duplicates")
for images in duplicates.values():
    print(f"  Group: {len(images)} images")
```

### Pattern 2: With Progress Tracking

```python
def show_progress(current, total):
    percent = (current / total) * 100
    print(f"\rProgress: {current}/{total} ({percent:.1f}%)", end="")

duplicates = deduper.find_duplicates(
    Path("./photos"),
    progress_callback=show_progress
)
```

### Pattern 3: Quality-Based Cleanup

```python
from file_organizer.services.deduplication import (
    ImageDeduplicator,
    get_best_quality_image
)

deduper = ImageDeduplicator()
duplicates = deduper.find_duplicates(Path("./photos"))

for images in duplicates.values():
    best = get_best_quality_image(images)
    to_delete = [img for img in images if img != best]

    print(f"Keep: {best.name}")
    print(f"Delete: {[img.name for img in to_delete]}")
```

### Pattern 4: Compare Specific Images

```python
img1 = Path("photo1.jpg")
img2 = Path("photo2.jpg")

similarity = deduper.compute_similarity(img1, img2)

if similarity >= 0.95:
    print("Nearly identical")
elif similarity >= 0.85:
    print("Very similar")
elif similarity >= 0.70:
    print("Somewhat similar")
else:
    print("Different")
```

### Pattern 5: Directory Comparison

```python
from file_organizer.services.deduplication import find_images_in_directory

# Find all images in two directories
dir1_images = find_images_in_directory(Path("./folder1"))
dir2_images = find_images_in_directory(Path("./folder2"))

# Hash all images
deduper = ImageDeduplicator()
hashes1 = deduper.batch_compute_hashes(dir1_images)
hashes2 = deduper.batch_compute_hashes(dir2_images)

# Find common hashes
common = set(hashes1.values()) & set(hashes2.values())
print(f"Found {len(common)} images in both directories")
```

## Error Handling

The module gracefully handles errors:

```python
# Invalid images are skipped, not raised
duplicates = deduper.find_duplicates(Path("./mixed_files"))
# Will skip corrupt images, non-images, etc.

# Individual operations return None on error
hash_value = deduper.get_image_hash(Path("corrupt.jpg"))
if hash_value is None:
    print("Could not process image")

# Validation provides details
is_valid, error = deduper.validate_image(Path("test.jpg"))
if not is_valid:
    print(f"Validation failed: {error}")
```

## Performance Considerations

### Memory Usage
- Images are not loaded into memory all at once
- Only hashes are stored (64 bits per image)
- Suitable for large collections (10,000+ images)

### Processing Speed
Approximate speeds on modern hardware:

| Algorithm | Speed | Images/Second |
|-----------|-------|---------------|
| aHash | Fast | 100-200 |
| dHash | Fast | 80-150 |
| pHash | Medium | 50-100 |

For large collections:
```python
# Process in batches if needed
from pathlib import Path

all_images = list(Path("./photos").rglob("*.jpg"))
batch_size = 1000

for i in range(0, len(all_images), batch_size):
    batch = all_images[i:i + batch_size]
    hashes = deduper.batch_compute_hashes(batch)
    # Process this batch
```

### Optimization Tips

1. **Choose the right algorithm**: Use aHash for speed, pHash for accuracy
2. **Adjust threshold**: Lower threshold = faster (fewer comparisons)
3. **Pre-filter by size**: Group images by file size first
4. **Use recursive wisely**: Non-recursive is faster for flat directories

## Supported Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| JPEG | .jpg, .jpeg | Most common format |
| PNG | .png | Lossless, supports transparency |
| GIF | .gif | Limited colors, animations not supported |
| BMP | .bmp | Large file size |
| TIFF | .tiff, .tif | High quality, multiple pages not supported |
| WebP | .webp | Modern format, good compression |

## Limitations

1. **Structural similarity only**: Perceptual hashing detects structural similarity, not semantic similarity. Two completely different images with similar layouts might hash similarly.

2. **Heavy modifications**: Extreme crops, rotations, or distortions may not be detected.

3. **No animation support**: Only the first frame of animated GIFs is processed.

4. **Memory for large collections**: While efficient, very large collections (100,000+ images) may require careful memory management.

## Troubleshooting

### Issue: No duplicates found
- **Check threshold**: Try increasing it (e.g., threshold=15)
- **Check hash method**: Try pHash for better similarity detection
- **Verify images**: Ensure images are valid and readable

### Issue: Too many false positives
- **Lower threshold**: Use stricter matching (e.g., threshold=5)
- **Check image quality**: Low-quality images may hash similarly

### Issue: Slow processing
- **Use aHash**: Faster algorithm for large collections
- **Disable recursion**: If not needed for subdirectories
- **Process in batches**: Don't load all images at once

### Issue: Import errors
```bash
pip install imagededup Pillow numpy
```

## Examples

See `examples/image_dedup_example.py` for comprehensive usage examples.

Run tests:
```bash
python test_image_dedup_with_images.py
```

## Technical Details

### How Perceptual Hashing Works

1. **Resize**: Image is resized to small size (e.g., 32x32)
2. **Convert**: Convert to grayscale
3. **Compute**: Calculate hash based on pixel patterns
4. **Compare**: Use Hamming distance to find similar hashes

### Hash Algorithm Details

**pHash (DCT-based)**:
- Applies Discrete Cosine Transform (DCT)
- Captures frequency information
- Most robust to modifications

**dHash (Gradient-based)**:
- Compares adjacent pixels
- Tracks image gradients
- Good for resized images

**aHash (Average-based)**:
- Compares pixels to mean value
- Simplest algorithm
- Fast but less robust

## References

- [imagededup Library](https://github.com/idealo/imagededup)
- [Perceptual Hashing](https://www.phash.org/)
- [Image Similarity Detection](https://realpython.com/image-processing-with-the-python-pillow-library/)

## License

Part of File Organizer v2.0 - See main project LICENSE file.
