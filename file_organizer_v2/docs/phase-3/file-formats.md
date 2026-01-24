# Phase 3 File Format Support

## Overview

Phase 3 significantly expands File Organizer's file format support with specialized handlers for CAD files, archives, enhanced EPUB processing, and scientific data formats.

## Supported Format Categories

### Document Formats (Enhanced)

#### EPUB Books (Enhanced)
- **Extensions**: `.epub`
- **Status**: ✅ Enhanced in Phase 3
- **New Features**:
  - Chapter-based analysis
  - Series recognition
  - Enhanced metadata extraction
  - Cover image extraction

**Usage**:
```python
from file_organizer.utils.file_readers import read_ebook_file

# Extract text content from EPUB
text = read_ebook_file("book.epub")  # Returns string content

# Optional: Limit extracted text
text = read_ebook_file("book.epub", max_chars=5000)
```

**Organization**:
```
3-Resources/
└── Books/
    ├── Fiction/
    │   └── Series-Name/
    │       ├── 01-First-Book.epub
    │       └── 02-Second-Book.epub
    └── Non-Fiction/
        └── Technical/
            └── Python-Programming.epub
```

### Archive Formats

#### ZIP Archives
- **Extensions**: `.zip`
- **Status**: ✅ Active
- **Features**:
  - Content-based categorization
  - Compression ratio analysis
  - Archive integrity checking
  - Nested archive handling

**Usage**:
```python
from file_organizer.utils.file_readers import read_archive_file

# Read archive contents - use format-specific functions
from file_organizer.utils.file_readers import read_zip_file, read_tar_file

# For ZIP files
content = read_zip_file("project.zip")  # Returns formatted string

# For TAR files
content = read_tar_file("backup.tar.gz")  # Returns formatted string

# Content includes:
# - List of files in archive
# - File sizes and structure
# - Metadata about the archive
```

**Organization Strategy**:
```python
from file_organizer import FileOrganizer

organizer = FileOrganizer()

# Organize based on archive contents
result = organizer.organize(
    "downloads/",
    analyze_archives=True,  # Look inside archives
    content_based_categorization=True
)

# Example output:
# project.zip → 1-Projects/Web-Development/
# photos.zip → 3-Resources/Images/Vacation-2024/
# backup.zip → 4-Archive/System-Backups/
```

#### TAR Archives
- **Extensions**: `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`
- **Status**: ✅ Active
- **Features**: Same as ZIP plus:
  - Unix permission preservation
  - Symbolic link detection
  - Large file optimization

#### 7-Zip Archives
- **Extensions**: `.7z`
- **Status**: ✅ Active
- **Features**: High compression ratio support

#### RAR Archives
- **Extensions**: `.rar`
- **Status**: ✅ Active (requires unrar)
- **Installation**:
  ```bash
  # macOS
  brew install unrar

  # Linux
  apt-get install unrar
  ```

### CAD File Formats

#### DXF (Drawing Exchange Format)
- **Extensions**: `.dxf`
- **Status**: 📅 Phase 3 (Basic support available)
- **Features**:
  - Layer information extraction
  - Entity count analysis
  - Drawing metadata
  - Unit detection

**Usage**:
```python
from file_organizer.utils.file_readers import read_cad_file

# Read DXF file - returns formatted string with metadata
output = read_cad_file("design.dxf")

# Example output:
# === DXF Document Metadata ===
# Title: Assembly Design
# Layers: 12
# Entities: 1,543
# Drawing Units: Millimeters
# === Layer Information ===
# Layer 'Dimensions': 145 entities
# Layer 'Centerlines': 89 entities
# ...
```

**Organization**:
```
1-Projects/
└── Engineering/
    ├── Mechanical/
    │   ├── Assembly-Drawing.dxf
    │   └── Part-001.dxf
    └── Electrical/
        └── Circuit-Schematic.dxf
```

#### DWG (AutoCAD Drawing)
- **Extensions**: `.dwg`
- **Status**: 📅 Phase 3 (Planned)
- **Features**: Similar to DXF
- **Note**: Requires additional library (ezdxf or ODA File Converter)

#### STEP Files
- **Extensions**: `.step`, `.stp`
- **Status**: 📅 Phase 3 (Planned)
- **Features**:
  - 3D model metadata
  - Assembly structure
  - Part properties

#### IGES Files
- **Extensions**: `.iges`, `.igs`
- **Status**: 📅 Phase 3 (Planned)
- **Features**: Similar to STEP

### Scientific Data Formats

#### HDF5 (Hierarchical Data Format)
- **Extensions**: `.h5`, `.hdf5`
- **Status**: 📅 Phase 3 (Planned)
- **Features**:
  - Dataset structure analysis
  - Attribute extraction
  - Group hierarchy mapping
  - Data type detection

**Planned Usage**:
```python
from file_organizer.utils.file_readers import read_hdf5_file

# Analyze HDF5 structure
info = read_hdf5_file("experiment.h5")

# Returns:
# - groups: List of groups
# - datasets: Dataset names and shapes
# - attributes: Metadata attributes
# - total_size: Data size
```

**Organization**:
```
1-Projects/
└── Research/
    ├── Experiment-001/
    │   ├── raw-data.h5
    │   └── processed-data.h5
    └── Simulation/
        └── results.h5
```

#### NetCDF (Network Common Data Form)
- **Extensions**: `.nc`, `.nc4`
- **Status**: 📅 Phase 3 (Planned)
- **Features**:
  - Dimension information
  - Variable metadata
  - Climate/weather data support
  - Time series analysis

#### MATLAB Files
- **Extensions**: `.mat`
- **Status**: 📅 Phase 3 (Planned)
- **Features**:
  - Variable extraction
  - Array shape detection
  - Version compatibility

## Format Detection

### Automatic Detection
File Organizer automatically detects formats based on:
1. **File extension** - Primary detection method
2. **Magic numbers** - Binary file signature validation
3. **Content analysis** - Structural validation

```python
from file_organizer.utils import detect_file_type

file_info = detect_file_type("unknown_file.bin")

# Returns:
# - detected_type: "zip", "pdf", "epub", etc.
# - confidence: Detection confidence (0-1)
# - mime_type: MIME type
# - suggested_extension: Recommended extension
```

### Format Validation
```python
from file_organizer.utils import validate_file_format

# Validate file integrity
is_valid = validate_file_format("document.pdf")

if not is_valid:
    print("File may be corrupted or invalid")
```

## Configuration

### Enable/Disable Format Support

**Global Configuration** (`~/.config/file-organizer/config.yaml`):
```yaml
file_formats:
  # Document formats
  epub_enhanced: true

  # Archives
  archive_support: true
  analyze_archive_contents: true
  max_archive_size_mb: 500

  # CAD files
  cad_support: true
  cad_metadata_extraction: true

  # Scientific formats
  scientific_support: false  # Phase 3
  hdf5_support: false
  netcdf_support: false
```

**Python API**:
```python
from file_organizer import FileOrganizer
from file_organizer.models.base import ModelConfig

# Configure AI models for processing
text_config = ModelConfig(
    name="qwen2.5:3b-instruct-q4_K_M",
    temperature=0.5
)
vision_config = ModelConfig(
    name="qwen2.5vl:7b-q4_K_M",
    temperature=0.3
)

organizer = FileOrganizer(
    text_model_config=text_config,
    vision_model_config=vision_config
)
```

### Format-Specific Options

**EPUB Configuration**:
```python
epub_config = {
    "extract_chapters": True,
    "detect_series": True,
    "extract_cover": True,
    "cover_output_dir": "covers/"
}
```

**Archive Configuration**:
```python
archive_config = {
    "analyze_contents": True,
    "max_depth": 3,  # Nested archive depth
    "extract_for_analysis": False,  # Don't extract, just analyze
    "skip_encrypted": True
}
```

**CAD Configuration**:
```python
cad_config = {
    "extract_layers": True,
    "count_entities": True,
    "extract_metadata": True,
    "thumbnail_generation": False  # Phase 3
}
```

## Performance Considerations

### Processing Times

| Format | Average Time | Notes |
|--------|-------------|-------|
| EPUB | 1-3 seconds | Depends on book size |
| ZIP (small) | 0.5-1 second | < 10 MB |
| ZIP (large) | 2-10 seconds | 10-500 MB |
| TAR | Similar to ZIP | Slightly faster |
| 7Z | 1.5x ZIP time | Higher compression |
| DXF | 2-5 seconds | Depends on complexity |
| HDF5 | 1-5 seconds | Phase 3 |

### Memory Usage

| Format | RAM Usage | Notes |
|--------|-----------|-------|
| EPUB | ~50-100 MB | Book content buffered |
| Archives | ~100-200 MB | Analysis only, no extraction |
| CAD Files | ~50-150 MB | Depends on file size |
| Scientific | ~200-500 MB | Phase 3, large datasets |

### Optimization Tips

1. **Archives**:
   - Disable `analyze_archive_contents` for faster processing
   - Set `max_archive_size_mb` to skip very large archives
   - Use `skip_encrypted` to avoid password prompts

2. **CAD Files**:
   - Disable `extract_layers` if not needed
   - Skip thumbnail generation (Phase 3)

3. **Large Files**:
   - Process in batches
   - Use `--parallel` flag (Phase 5)
   - Set memory limits in config

## File Organization Strategies

### Content-Based Organization

Archives are organized based on their contents:
```python
# ZIP containing Python code
python-project.zip → 1-Projects/Development/Python/

# ZIP containing photos
vacation-photos.zip → 3-Resources/Images/Vacation-2024/

# ZIP containing documents
contracts.zip → 2-Areas/Legal/Contracts/
```

### Extension-Based Organization

Simple organization by format:
```python
from file_organizer import FileOrganizer

organizer = FileOrganizer()

# Organize by extension
organizer.organize(
    "downloads/",
    strategy="extension",
    extension_mapping={
        ".epub": "3-Resources/Books/",
        ".zip": "4-Archive/Downloads/",
        ".dxf": "1-Projects/CAD/",
    }
)
```

### Hybrid Approach

Combine content analysis with format rules:
```python
organizer.organize(
    "downloads/",
    strategy="hybrid",
    analyze_archives=True,  # Content-based for archives
    use_extension_hints=True  # Extension-based for others
)
```

## Error Handling

### Corrupted Files
```python
try:
    organizer.organize("document.epub")
except CorruptedFileError as e:
    print(f"File corrupted: {e}")
    # Move to quarantine folder
```

### Unsupported Formats
```python
from file_organizer.exceptions import UnsupportedFormatError

try:
    info = read_cad_file("design.dwg")
except UnsupportedFormatError:
    print("DWG not yet supported, use DXF format")
```

### Missing Dependencies
```python
from file_organizer.utils import check_format_support

# Check if format is supported
if not check_format_support("rar"):
    print("Install unrar: brew install unrar")
```

## Testing Format Support

```bash
# Test EPUB support
file-organizer test-format book.epub

# Test archive support
file-organizer test-format project.zip

# Test CAD support
file-organizer test-format design.dxf

# Test all formats
file-organizer test-all-formats
```

## Migration Guide

### Upgrading to Phase 3

1. **Update package**:
   ```bash
   pip install --upgrade file-organizer-v2
   ```

2. **Update configuration**:
   ```yaml
   # Add to ~/.config/file-organizer/config.yaml
   file_formats:
     epub_enhanced: true
     archive_support: true
     cad_support: true
   ```

3. **Re-organize existing files**:
   ```bash
   file-organizer re-organize ~/Documents --use-enhanced-formats
   ```

### From Manual Organization

If you've been organizing files manually:
```bash
# Analyze what changed
file-organizer analyze ~/Documents --show-improvements

# Apply Phase 3 organization
file-organizer organize ~/Documents --methodology para --use-enhanced-formats
```

## Troubleshooting

### EPUB Not Recognized
```bash
# Check file integrity
file-organizer validate book.epub

# Try re-installing
pip install --upgrade ebooklib
```

### Archive Analysis Slow
```yaml
# Disable content analysis
file_formats:
  analyze_archive_contents: false
```

### CAD Files Not Loading
```bash
# Check dependencies
pip install ezdxf

# Verify file format
file-organizer detect-format design.dxf
```

### Scientific Formats (Phase 3)
These are planned for Phase 3:
```bash
# Check status
file-organizer feature-status scientific-formats

# Get notified when available
file-organizer notify-me scientific-formats
```

## API Reference

### Read Functions

```python
# EPUB
from file_organizer.utils.file_readers import read_epub_file
content, metadata = read_epub_file("book.epub")

# Archives
from file_organizer.utils.file_readers import read_archive_file
info = read_archive_file("project.zip")

# CAD
from file_organizer.utils.file_readers import read_cad_file
info = read_cad_file("design.dxf")

# Scientific (Phase 3)
from file_organizer.utils.file_readers import read_hdf5_file
info = read_hdf5_file("data.h5")
```

### Format Detection

<!-- Utility functions for format detection are planned for future release.
For now, use direct format-specific readers from file_organizer.utils.file_readers.
```python
from file_organizer.utils import (
    detect_file_type,
    validate_file_format,
    get_format_info
)
```
-->

**Note**: Format detection utilities are planned for a future release. Currently, use format-specific readers directly:

```python
from pathlib import Path

# Use file extension to determine reader
file_path = Path("document.pdf")
ext = file_path.suffix.lower()

if ext == '.pdf':
    from file_organizer.utils.file_readers import read_pdf_file
    content = read_pdf_file(file_path)
elif ext == '.epub':
    from file_organizer.utils.file_readers import read_ebook_file
    content = read_ebook_file(file_path)
# Add more formats as needed
```

## Related Documentation

- [PARA Methodology](para-methodology.md) - Organization system
- [Johnny Decimal](johnny-decimal.md) - Numbering system
- [Phase 3 Overview](README.md) - All Phase 3 features

## Further Reading

- [EPUB Specification](http://idpf.org/epub)
- [ZIP File Format](https://en.wikipedia.org/wiki/ZIP_(file_format))
- [DXF Reference](https://www.autodesk.com/techpubs/autocad/dxf/)
- [HDF5 Documentation](https://www.hdfgroup.org/solutions/hdf5/)

---

**Format Support Status**: 20 active formats, 5 planned (Phase 3)
**Last Updated**: 2026-01-24
