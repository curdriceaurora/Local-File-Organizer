# File Format Reference

This reference documents every file format supported by File Organizer, including
extraction behavior, optional dependencies, and tunable parameters.

## Overview

File Organizer supports 48+ file formats across 8 categories. Each format has a
dedicated reader that extracts text, metadata, or structural information for
AI-based classification and organization.

| Category | Formats | Optional Dependencies | Install Group |
|----------|---------|----------------------|---------------|
| Documents | `.txt`, `.md`, `.pdf`, `.docx`, `.csv`, `.xlsx`, `.ppt`, `.pptx` | PyMuPDF, python-docx, pandas, python-pptx | Core / none |
| Ebooks | `.epub` | ebooklib | Core |
| Archives | `.zip`, `.7z`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.tar.xz`, `.rar` | py7zr, rarfile | `[archive]` |
| Scientific | `.hdf5`, `.h5`, `.hdf`, `.nc`, `.nc4`, `.netcdf`, `.mat` | h5py, netCDF4, scipy | `[scientific]` |
| CAD | `.dxf`, `.dwg`, `.step`, `.stp`, `.iges`, `.igs` | ezdxf | `[cad]` |
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.tif` | None (VisionProcessor) | Core |
| Audio | `.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg` | faster-whisper, torch | `[audio]` |
| Video | `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv` | opencv-python, scenedetect | `[video]` |

## Global Limits

All readers share a maximum file size check before processing:

| Parameter | Default | Location |
|-----------|---------|----------|
| `MAX_FILE_SIZE_BYTES` | 500 MB | `src/file_organizer/utils/readers/_base.py` |

Files exceeding this limit raise `FileTooLargeError` and are skipped.

## Installing Optional Dependencies

```bash
# Individual groups
pip install -e ".[archive]"      # 7z and RAR support
pip install -e ".[scientific]"   # HDF5, NetCDF, MATLAB
pip install -e ".[cad]"          # DXF/DWG/STEP/IGES
pip install -e ".[audio]"        # Audio transcription
pip install -e ".[video]"        # Video scene detection

# Everything
pip install -e ".[all]"
```

## Documents

Source module: `src/file_organizer/utils/readers/documents.py`

### Plain Text (`.txt`, `.md`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_chars` | 5000 | Maximum characters read from file |

- Reads with UTF-8 encoding, ignoring decode errors
- No optional dependencies required

### PDF (`.pdf`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_pages` | 5 | Maximum number of pages to extract text from |

- Uses PyMuPDF (`fitz`) for text extraction
- Extracts plain text from each page sequentially
- Requires: `PyMuPDF` (included in core dependencies)

### Word Documents (`.docx`)

- Extracts text from all non-empty paragraphs
- Joins paragraphs with newlines
- Requires: `python-docx` (included in core dependencies)

!!! note
    Only `.docx` (Office Open XML) is supported. Legacy `.doc` (binary format)
    files are not supported and will return `None` from the reader dispatcher.

### Spreadsheets (`.csv`, `.xlsx`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_rows` | 100 | Maximum rows read from the spreadsheet |

- CSV files read with `pandas.read_csv`
- Excel files read with `pandas.read_excel` (requires `openpyxl` for `.xlsx`)
- Returns string representation of the DataFrame
- Requires: `pandas`, `openpyxl` (included in core dependencies)

!!! note
    Only `.xlsx` (Office Open XML) is supported for Excel files. Legacy `.xls`
    (binary format) files are registered in the reader dispatch table but will
    fail at runtime because the required `xlrd` package is not included in
    project dependencies.

### Presentations (`.ppt`, `.pptx`)

- Extracts text from all shapes on each slide
- Formats output as `Slide N: text1 | text2 | ...`
- Requires: `python-pptx` (included in core dependencies)

## Ebooks

Source module: `src/file_organizer/utils/readers/ebook.py`

### EPUB (`.epub`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_chars` | 10000 | Maximum characters extracted from the ebook |

- Iterates over document items in the EPUB container
- Strips HTML tags using regex
- Stops extraction once `max_chars` is reached
- Requires: `ebooklib` (included in core dependencies)

!!! note
    Only `.epub` format is supported. Other ebook formats (`.mobi`, `.azw`)
    are not currently supported. The reader dispatcher returns `None` for
    unrecognized extensions, causing the file to be skipped.

## Archives

Source module: `src/file_organizer/utils/readers/archives.py`

Archive readers extract **metadata and file listings**, not file contents. This
provides enough information for AI classification without decompressing large
archives.

### ZIP (`.zip`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_files` | 50 | Maximum number of entries to list |

- Uses Python standard library `zipfile`
- Lists file names, sizes (original and compressed), and compression ratio
- No optional dependencies required

### 7z (`.7z`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_files` | 50 | Maximum number of entries to list |

- Lists file names and sizes from the 7z archive
- Requires: `py7zr` (install group: `[archive]`)

### TAR Archives (`.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.tar.xz`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_files` | 50 | Maximum number of entries to list |

- Uses Python standard library `tarfile`
- Supports gzip, bzip2, and xz compression
- Lists member names, sizes, and types (file/directory/link)
- No optional dependencies required

### RAR (`.rar`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_files` | 50 | Maximum number of entries to list |

- Lists file names, sizes (original and compressed), and modification dates
- Requires: `rarfile` (install group: `[archive]`)
- Also requires the `unrar` command-line tool to be installed on the system

## Scientific Data

Source module: `src/file_organizer/utils/readers/scientific.py`

Scientific readers extract **structure and metadata** rather than raw data arrays.

### HDF5 (`.hdf5`, `.h5`, `.hdf`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_datasets` | 20 | Maximum number of datasets to list |

- Traverses HDF5 group hierarchy with `visititems`
- For each dataset: reports name, dtype, shape, size in KB
- Lists up to 3 attributes per dataset
- Reports total number of top-level groups
- Requires: `h5py` (install group: `[scientific]`)

### NetCDF (`.nc`, `.nc4`, `.netcdf`)

- Reports file format (e.g., `NETCDF4`)
- Lists all dimensions with sizes (marks unlimited dimensions)
- Lists first 20 variables with dtype and shape
- Shows `units` and `long_name` attributes when present
- Lists first 10 global attributes
- Requires: `netCDF4` (install group: `[scientific]`)

### MATLAB (`.mat`)

- Loads `.mat` file structure (not full data arrays)
- Lists first 30 variables with type and shape information
- Filters out internal metadata variables (names starting with `__`)
- Requires: `scipy` (install group: `[scientific]`)

## CAD

Source module: `src/file_organizer/utils/readers/cad.py`

### DXF (`.dxf`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_layers` | 20 | Maximum number of layers to list |

- Parses DXF structure using `ezdxf`
- Reports DXF version and number of entities
- Lists layers with entity counts
- Lists named blocks
- Extracts header variables (units, limits, extents)
- Requires: `ezdxf` (install group: `[cad]`)

### DWG (`.dwg`)

- Limited support via `ezdxf` (not all DWG versions supported)
- Falls back to basic file information (size, modification date) on failure
- Requires: `ezdxf` (install group: `[cad]`)

### STEP (`.step`, `.stp`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_lines` | 100 | Maximum header/data lines to parse |

- Plain text parser for ISO 10303 STEP files
- Extracts header information: file description, name, schema
- Counts data entities by type
- No optional dependencies required (plain text parsing)

### IGES (`.iges`, `.igs`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_lines` | 50 | Maximum lines to parse from each section |

- Plain text parser for IGES section-marked format
- Counts entities by section marker (S, G, D, P)
- Extracts global section parameters
- No optional dependencies required (plain text parsing)

## Images

Images are processed by `VisionProcessor` using the vision-language model
(Qwen 2.5-VL 7B by default). The vision model generates descriptions, folder
names, and filenames based on image content.

| Extension | Format |
|-----------|--------|
| `.jpg`, `.jpeg` | JPEG |
| `.png` | PNG |
| `.gif` | GIF |
| `.bmp` | BMP |
| `.tiff`, `.tif` | TIFF |

No optional dependencies required for image processing.

## Audio

Audio files are processed by `AudioModel` / `AudioTranscriber` using
faster-whisper for local transcription.

| Extension | Format |
|-----------|--------|
| `.mp3` | MPEG Audio Layer 3 |
| `.wav` | Waveform Audio |
| `.flac` | Free Lossless Audio Codec |
| `.m4a` | MPEG-4 Audio |
| `.ogg` | Ogg Vorbis |

Install dependencies:

```bash
pip install -e ".[audio]"
```

This installs: `faster-whisper`, `torch`, `mutagen`, `tinytag`, `pydub`,
`ffmpeg-python`.

## Video

Video files are processed by `VisionProcessor` with frame extraction using
OpenCV and optional scene detection.

| Extension | Format |
|-----------|--------|
| `.mp4` | MPEG-4 |
| `.avi` | AVI |
| `.mkv` | Matroska |
| `.mov` | QuickTime |
| `.wmv` | Windows Media Video |

Install dependencies:

```bash
pip install -e ".[video]"
```

This installs: `opencv-python`, `scenedetect[opencv]`.

## Reader Dispatch

The `read_file()` function in `src/file_organizer/utils/readers/__init__.py`
dispatches to the correct reader based on file extension. The dispatch logic:

1. Checks file size against `MAX_FILE_SIZE_BYTES` (500 MB)
2. Handles compound extensions (`.tar.gz`, `.tar.bz2`, `.tar.xz`)
3. Maps the extension to the appropriate reader function
4. Returns `None` for unsupported extensions (the file is skipped)

If an optional dependency is missing, the reader raises `ImportError` with
installation instructions.

## Adding Support for New Formats

To add a new file format:

1. Create or extend a reader function in `src/file_organizer/utils/readers/`
2. Register the extension in the `READERS` dict in `__init__.py`
3. If the format requires an optional dependency, add it to
   `pyproject.toml` under the appropriate install group
4. Use the `_check_file_size()` helper for size validation
5. Raise `FileReadError` on read failures
