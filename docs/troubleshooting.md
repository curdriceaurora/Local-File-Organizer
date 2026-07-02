# Troubleshooting Guide

Common issues and solutions for Local File Organizer. For advanced deployment and production issues, see the [Admin Troubleshooting Guide](admin/troubleshooting.md).

## Installation Issues

### Ollama Connection Failed

**Error**: `ConnectionRefusedError` or "Ollama unavailable"

**Cause**: Ollama service is not running or is bound to a different port.

**Solution**:

```bash
# Start Ollama
ollama serve

# Verify it's running
curl http://localhost:11434/api/version

# If using a custom port, set the environment variable
export OLLAMA_HOST=http://localhost:12345
```

### Model Not Found

**Error**: "Model not found"

**Cause**: Required Ollama models have not been downloaded.

**Solution**:

```bash
# Pull the required models
ollama pull qwen2.5:3b-instruct-q4_K_M      # Text model (~1.9 GB)
ollama pull qwen2.5vl:7b-q4_K_M             # Vision model (~6.0 GB)

# Verify they're installed
ollama list
```

### Port Already in Use

**Error**: "Port 8000 is already in use"

**Cause**: Another process is already using the default port.

**Solution**:

```bash
# Use different port
file-organizer serve --port 8001

# Or find and stop the process using port 8000
lsof -i :8000
kill <PID>          # graceful shutdown (SIGTERM)
# If the process doesn't stop:
kill -9 <PID>       # force kill (SIGKILL) as last resort
```

## Optional Dependency Issues

### Module Not Found Error

**Error**: `ModuleNotFoundError: No module named 'faster_whisper'` or similar

**Cause**: Attempting to use a feature that requires optional dependencies not installed with the base package.

**Solution**:

Install the appropriate optional dependency group based on the feature you're using:

| Feature | Error Pattern | Install Command |
|---------|---------------|-----------------|
| Audio transcription | `faster_whisper`, `torch` | `pip install "local-file-organizer[audio]"` |
| Video processing | `cv2`, `scenedetect` | `pip install "local-file-organizer[video]"` |
| Image deduplication | `imagededup` | `pip install "local-file-organizer[dedup]"` |
| Semantic search | `rank_bm25`, `sklearn` | `pip install "local-file-organizer[search]"` |
| Archive support | `py7zr` | `pip install "local-file-organizer[archive]"` |
| Scientific formats | `h5py`, `netCDF4` | `pip install "local-file-organizer[scientific]"` |
| CAD file support | `ezdxf` | `pip install "local-file-organizer[cad]"` |
| Claude API provider | `anthropic` | `pip install "local-file-organizer[claude]"` |
| Document parsers | `fitz`, `docx`, `openpyxl`, `pptx`, `ebooklib`, `bs4` | `pip install "local-file-organizer[parsers]"` |
| OpenAI-compatible API | `openai` | `pip install "local-file-organizer[cloud]"` |
| llama.cpp inference | `llama_cpp` | `pip install "local-file-organizer[llama]"` |
| MLX inference (macOS) | `mlx_lm` | `pip install "local-file-organizer[mlx]"` |
| GUI interface | `PyQt6` | `pip install "local-file-organizer[gui]"` |
| All features | Any of the above | `pip install "local-file-organizer[all]"` |

For more details, see [Dependencies & Setup](setup/dependencies.md).

### Import Error with Specific Message

**Error**: `ImportError: faster-whisper is required for audio transcription. Install it with: pip install faster-whisper`

**Cause**: The error message indicates exactly which package is missing.

**Solution**:

Follow the instruction in the error message, or use the table above to install the complete feature group.

## Permission Errors

### File Access Denied (macOS)

**Error**: `PermissionError: [Errno 13] Permission denied: '/Users/username/Desktop'`

**Cause**: macOS protects certain directories (Desktop, Documents, Downloads) and requires explicit permission for applications to access them.

**Solution**:

```bash
# Option 1: Grant Full Disk Access
# System Settings > Privacy & Security > Full Disk Access
# Add your terminal application or Python

# Option 2: Use a different directory
mkdir ~/file-organizer-workspace
file-organizer organize ~/file-organizer-workspace ~/organized

# Option 3: Copy files to an accessible location first
cp -r ~/Desktop/files ~/file-organizer-workspace/
```

### Cannot Read File Error

**Error**: `PermissionError: Cannot read file: /path/to/file`

**Cause**: Insufficient permissions to read the file, typically from file ownership or mode restrictions.

**Solution**:

```bash
# Check file permissions
ls -la /path/to/file

# Make file readable
chmod +r /path/to/file

# If owned by another user, change ownership (requires sudo)
sudo chown $USER /path/to/file
```

## Memory and Performance Issues

### Out of Memory During Organization

**Error**: Process killed or `MemoryError` when organizing large directories

**Cause**: Processing too many files simultaneously or analyzing very large files (videos, high-res images).

**Solution**:

```bash
# Process sequentially instead of in parallel
file-organizer organize /path/to/input /path/to/output --sequential

# Limit number of parallel workers
file-organizer organize /path/to/input /path/to/output --max-workers 2

# Process subdirectories separately
for dir in /path/*/; do
  file-organizer organize "$dir" /output
done

# Skip vision processing for large directories
file-organizer organize /path/to/input /path/to/output --no-vision
```

For production deployments with high memory demands, see [Performance Tuning](admin/performance-tuning.md).

### Audio Transcription Out of Memory

**Error**: `RuntimeError: CUDA out of memory` or system OOM killer

**Cause**: Whisper model too large for available GPU memory, or processing very long audio files.

**Solution**:

Audio transcription uses `faster-whisper` (not Ollama). Model size and device are configured via the application config. To reduce memory usage:

```bash
# Process files sequentially to limit concurrent memory use
file-organizer organize /audio /output --sequential

# Skip vision processing to free up resources
file-organizer organize /audio /output --text-only
```

For GPU memory issues with Ollama models, reduce the model size or restrict GPU access via environment variables like `CUDA_VISIBLE_DEVICES=""` (NVIDIA) or `HIP_VISIBLE_DEVICES=""` (AMD) to force CPU-only inference.

Available Whisper model sizes (smallest to largest):

- `tiny` - ~1 GB VRAM, fastest
- `base` - ~1 GB VRAM, good balance (default)
- `small` - ~2 GB VRAM, better accuracy
- `medium` - ~5 GB VRAM, high accuracy
- `large-v3` - ~10 GB VRAM, best accuracy

## Configuration Issues

### YAML Parse Error

**Error**: `yaml.scanner.ScannerError: mapping values are not allowed here`

**Cause**: Invalid YAML syntax in configuration file.

**Solution**:

```bash
# Validate YAML syntax online or with a linter
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Common issues:
# - Tabs instead of spaces (use spaces only)
# - Missing quotes around strings with special characters
# - Incorrect indentation

# View current config to check for errors
file-organizer config show
```

### Config File Not Found

**Error**: `FileNotFoundError` for configuration file

**Cause**: Configuration file does not exist in the expected location. The config path is determined by `platformdirs` and varies by OS:

- **Linux**: `~/.config/file-organizer/`
- **macOS**: `~/Library/Application Support/file-organizer/`
- **Windows**: `%APPDATA%\file-organizer\`

**Solution**:

```bash
# View the current config path and values
file-organizer config show

# Open the config file in your editor to create/edit it
file-organizer config edit

# List all available config keys
file-organizer config list
```

### XDG Config Migration

**Error**: Warning about deprecated config location

**Cause**: Old config files in a legacy location instead of the platform-appropriate directory managed by `platformdirs`.

**Solution**:

```bash
# Check where config is currently stored
file-organizer config show

# Edit config in the correct location
file-organizer config edit

# Or set XDG_CONFIG_HOME explicitly (Linux only)
export XDG_CONFIG_HOME=~/.config
```

See [Path Standardization](config/path-standardization.md) for details on config migration.

## Web UI Issues

### Web Server Won't Start

**Error**: `Error: uvicorn is not installed.`

**Cause**: Web server dependencies are not installed.

**Solution**:

```bash
# Install web dependencies
pip install "local-file-organizer[web]"

# Or install uvicorn directly
pip install uvicorn[standard]

# Start the web server
file-organizer serve
```

### Redis Connection Failed

**Error**: `ConnectionError: Error connecting to Redis`

**Cause**: Redis is not running or not accessible at the configured URL.

**Solution**:

```bash
# Option 1: Install and start Redis locally
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl start redis-server

# Verify Redis is running
redis-cli ping  # Should return "PONG"

# Option 2: Use Docker
docker run -d -p 6379:6379 redis:latest

# Option 3: Configure different Redis URL
export FO_REDIS_URL=redis://localhost:6379/0
file-organizer serve
```

### FastAPI Startup Error

**Error**: `RuntimeError: Application startup failed`

**Cause**: Missing environment variables, database connection issues, or port conflicts.

**Solution**:

```bash
# Check logs with verbose output
file-organizer serve --verbose

# Verify all dependencies
pip install "local-file-organizer[web]"

# Check for port conflicts
lsof -i :8000

# Use different port if needed
file-organizer serve --port 8001
```

## AI Provider Issues

### Provider Not Found / Missing Extra

**Error**: `Unknown provider 'openai'. Registered providers: ['ollama']` or similar

**Cause**: The required provider package is not installed.

**Solution**:

```bash
# OpenAI, Groq, or LM Studio (OpenAI-compatible)
pip install "local-file-organizer[cloud]"

# Claude (Anthropic)
pip install "local-file-organizer[claude]"

# LLaMA.cpp
pip install "local-file-organizer[llama]"

# MLX (Apple Silicon)
pip install "local-file-organizer[mlx]"
```

See [AI Provider Setup](setup/ai-providers.md) for full configuration details.

### OpenAI-Compatible API: Auth Warning or 401

**Error**: Warning `FO_PROVIDER=openai but neither FO_OPENAI_API_KEY nor FO_OPENAI_BASE_URL is set` or HTTP 401 from the API

**Cause**: API key or base URL not set in the environment.

**Solution**:

```bash
# For OpenAI
export FO_OPENAI_API_KEY=sk-...
export FO_OPENAI_MODEL=gpt-4o-mini

# For LM Studio (no key needed, custom base URL)
export FO_PROVIDER=openai
export FO_OPENAI_BASE_URL=http://localhost:1234/v1
export FO_OPENAI_MODEL=your-loaded-model

# For Groq
export FO_PROVIDER=openai
export FO_OPENAI_API_KEY=gsk_...
export FO_OPENAI_BASE_URL=https://api.groq.com/openai/v1
export FO_OPENAI_MODEL=llama-3.3-70b-versatile
```

The standard `OPENAI_API_KEY` env var is also accepted as a fallback.

### OpenAI-Compatible API: Model Not Found at Custom Endpoint

**Error**: `404 Not Found` or `model not found` when using `FO_OPENAI_BASE_URL`

**Cause**: The model name set in `FO_OPENAI_MODEL` is not available at the configured endpoint, or the endpoint URL is missing the `/v1` path.

**Solution**:

```bash
# Verify your base URL ends with /v1
export FO_OPENAI_BASE_URL=http://localhost:1234/v1   # correct
# export FO_OPENAI_BASE_URL=http://localhost:1234    # missing /v1

# List available models at the endpoint
curl "${FO_OPENAI_BASE_URL}/models" -H "Authorization: Bearer ${FO_OPENAI_API_KEY:-none}"

# Set the model to one returned by the above command
export FO_OPENAI_MODEL=actual-model-id-from-list
```

### Claude / Anthropic: Auth Error or Missing Extra

**Error**: `AuthenticationError` or `401 Unauthorized` from the Anthropic API

**Cause**: `FO_CLAUDE_API_KEY` is not set, expired, or the `[claude]` extra is not installed.

**Solution**:

```bash
# Install the Claude extra
pip install "local-file-organizer[claude]"

# Set your API key
export FO_PROVIDER=claude
export FO_CLAUDE_API_KEY=sk-ant-...
export FO_CLAUDE_MODEL=claude-3-5-sonnet-20241022
```

The standard `ANTHROPIC_API_KEY` env var is also accepted as a fallback.

### Claude / Anthropic: Rate Limit

**Error**: `RateLimitError` or HTTP 429 from the Anthropic API

**Cause**: API request rate or token quota exceeded on your Anthropic account.

**Solution**: Wait a moment before retrying. For batch processing large directories, process files sequentially to reduce concurrent API calls:

```bash
file-organizer organize /input /output --sequential
```

Check your usage and limits in the [Anthropic console](https://console.anthropic.com/).

### LM Studio: Connection Refused

**Error**: `ConnectionRefusedError` or `Failed to connect to http://localhost:1234`

**Cause**: LM Studio's local server is not running, or no model is loaded.

**Solution**:

1. Open LM Studio and navigate to **Local Server** (left sidebar).
2. Load a model — the server only becomes active once a model is selected.
3. Click **Start Server** and confirm the port matches `FO_OPENAI_BASE_URL`.
4. Verify the server is responding:

```bash
curl http://localhost:1234/v1/models
```

See [AI Provider Setup — LM Studio](setup/ai-providers.md) for full configuration.

## Audio Transcription Issues

### No GPU Available Warning

**Error**: `UserWarning: No GPU detected, falling back to CPU`

**Cause**: PyTorch cannot detect CUDA or MPS (Apple Silicon) acceleration.

**Solution**:

```bash
# Install PyTorch with CUDA support (NVIDIA GPUs)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# For Apple Silicon (MPS)
pip install torch torchvision torchaudio

# Verify GPU detection
python -c "
import torch
print(f'CUDA: {torch.cuda.is_available()}')
print(f'MPS: {torch.backends.mps.is_available() if hasattr(torch.backends, \"mps\") else False}')
"

# CPU mode works but is slower - no special flags needed,
# the application auto-detects available hardware
```

### Model Download Timeout

**Error**: `TimeoutError` or `ConnectionError` when downloading Whisper model

**Cause**: Network issues or slow connection when downloading large model files.

**Solution**:

```bash
# Increase timeout and retry
export HF_HUB_DOWNLOAD_TIMEOUT=600

# Pre-download models manually
python -c "from faster_whisper import WhisperModel; WhisperModel('base')"

# Check disk space (models require several GB)
df -h
```

### Unsupported Audio Format

**Error**: `ValueError: Unsupported audio format` or FFmpeg error

**Cause**: Audio file format not supported by FFmpeg or corrupted file.

**Solution**:

```bash
# Install/update FFmpeg
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Convert unsupported format to WAV
ffmpeg -i input.unknown output.wav

# Supported formats: WAV, MP3, FLAC, OGG, M4A, AAC, WMA
# Check file integrity
ffmpeg -v error -i audio.mp3 -f null - 2>error.log
cat error.log
```

## File Organization Errors

### Duplicate File Handling

**Error**: `FileExistsError: Destination file already exists` or "Duplicate file detected"

**Cause**: A file with the same name already exists in the destination directory.

**Solution**:

Use the built-in deduplication tools to identify and manage duplicates:

```bash
# Scan for duplicates
file-organizer dedupe scan /path/to/files

# View deduplication report
file-organizer dedupe report /path/to/files

# Resolve duplicates interactively
file-organizer dedupe resolve /path/to/files

# Preview organization without moving files
file-organizer organize /input /output --dry-run
```

### Filename Too Long Error

**Error**: `OSError: [Errno 63] File name too long` or `OSError: [Errno 36] File name too long` (ENAMETOOLONG)

**Cause**: Generated filename exceeds filesystem limits (typically 255 characters on most systems).

**Solution**:

The application handles filename length internally. If you encounter this error:

```bash
# Preview what filenames would be generated
file-organizer organize /path/to/input /path/to/output --dry-run

# Manually rename problematic source files before organizing
for f in *; do
  if [ ${#f} -gt 200 ]; then
    mv "$f" "${f:0:200}.${f##*.}"
  fi
done
```

### Invalid Filename Characters

**Error**: `OSError: Invalid argument` or files with strange characters in names

**Cause**: Filename contains characters not allowed by the filesystem (e.g., `:`, `<`, `>`, `|`, `*`, `?` on Windows).

**Solution**:

The application sanitizes filenames automatically during organization. To preview the results:

```bash
# Preview organization to see how filenames will be handled
file-organizer organize /path/to/input /path/to/output --dry-run
```

If source files have problematic names, rename them before organizing:

```bash
# Use detox to batch-clean filenames
# macOS
brew install detox

# Ubuntu/Debian
sudo apt-get install detox

detox -r /path/to/files
```

## Metadata Extraction Errors

### EXIF Data Extraction Failed

**Error**: `ValueError: Invalid EXIF data` or "Cannot read image metadata"

**Cause**: Image file has corrupted or non-standard EXIF metadata, or file is not actually an image.

**Solution**:

```bash
# Repair EXIF data with exiftool
# macOS
brew install exiftool

# Ubuntu/Debian
sudo apt-get install libimage-exiftool-perl

# Fix corrupted EXIF
exiftool -all= -tagsfromfile @ -all:all -unsafe -icc_profile image.jpg

# Verify file type
file image.jpg  # Should show "JPEG image data"

# Analyze a specific file for details
file-organizer analyze image.jpg --verbose
```

### PDF Metadata Extraction Timeout

**Error**: `TimeoutError: PDF processing timed out` or process hangs on certain PDFs

**Cause**: PDF file is very large, corrupted, or contains complex embedded content that takes too long to process.

**Solution**:

```bash
# Analyze the problematic PDF to see what's happening
file-organizer analyze problematic.pdf --verbose

# Repair corrupt PDF with Ghostscript
gs -o repaired.pdf -sDEVICE=pdfwrite -dPDFSETTINGS=/prepress input.pdf

# Install parsers group for better PDF support
pip install "local-file-organizer[parsers]"
```

### Video Metadata Extraction Error

**Error**: `RuntimeError: ffprobe failed` or "Cannot extract video metadata"

**Cause**: FFmpeg/ffprobe is not installed or the video file is corrupted.

**Solution**:

```bash
# Install FFmpeg
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Verify installation
ffprobe -version

# Check video file integrity
ffmpeg -v error -i video.mp4 -f null - 2>error.log
cat error.log

# Analyze the video file
file-organizer analyze video.mp4 --verbose
```

## Plugin/Extension Errors

### Plugin Load Failed

**Error**: `ImportError: Cannot load plugin` or "Plugin not found"

**Cause**: Plugin is not installed, has incompatible version, or has missing dependencies.

**Solution**:

```bash
# List available plugins in the marketplace
file-organizer marketplace list

# Search for a specific plugin
file-organizer marketplace search <keyword>

# Install a plugin
file-organizer marketplace install <plugin-name>

# Check plugin details
file-organizer marketplace info <plugin-name>

# List installed plugins
file-organizer marketplace installed
```

### Plugin Configuration Error

**Error**: `ValueError: Invalid plugin configuration` or plugin crashes during execution

**Cause**: Plugin configuration file has invalid values or required settings are missing.

**Solution**:

```bash
# Check plugin details for configuration requirements
file-organizer marketplace info <plugin-name>

# Check for available updates
file-organizer marketplace updates

# Reinstall the plugin
file-organizer marketplace uninstall <plugin-name>
file-organizer marketplace install <plugin-name>
```

## Archive Processing Errors

### Cannot Extract Archive

**Error**: `RuntimeError: Archive extraction failed` or "Unsupported archive format"

**Cause**: Archive is corrupted, password-protected, or format is not supported.

**Solution**:

```bash
# Install archive support
pip install "local-file-organizer[archive]"

# Supported formats: ZIP, TAR, GZ, BZ2, XZ, 7Z, RAR (read-only)

# Test archive integrity before processing
7z t archive.7z
unzip -t archive.zip
tar -tzf archive.tar.gz
```

### Archive Bomb Detection

**Error**: `SecurityError: Archive bomb detected` or "Archive extraction aborted"

**Cause**: Archive contains excessive compression ratio (potential zip bomb) as a security measure.

**Solution**:

```bash
# Manually inspect suspicious archive contents without extracting
7z l -slt archive.zip  # List contents without extracting

# Extract to a sandboxed location to inspect
mkdir /tmp/archive-inspect
cd /tmp/archive-inspect
unzip -l suspicious.zip  # List only, don't extract
```

Archive bomb detection is a built-in safety feature. If you trust the archive source, extract it manually before organizing its contents.

## Scientific Format Errors

### HDF5 / NetCDF / MATLAB File Not Processed

**Error**: `ModuleNotFoundError: No module named 'h5py'`, `No module named 'netCDF4'`, or `No module named 'scipy'` when organizing `.h5`, `.nc`, `.mat`, or `.hdf` files

**Cause**: Scientific file format dependencies are not installed.

**Solution**:

```bash
# Install scientific format support
pip install "local-file-organizer[scientific]"

# Verify installation
python -c "import h5py, netCDF4, scipy; print('Scientific extras OK')"

# Then retry analysis
file-organizer analyze data.h5 --verbose
```

Supported formats after install: HDF5 (`.h5`, `.hdf`, `.hdf5`), NetCDF (`.nc`, `.nc4`), MATLAB (`.mat`).

### Scientific File Metadata Unreadable

**Error**: `OSError: Unable to open file` or corrupt HDF5/NetCDF error

**Cause**: File is truncated, written by an incompatible library version, or on a network filesystem with locking issues.

**Solution**:

```bash
# Check file integrity with h5py
python -c "import h5py; h5py.File('data.h5', 'r').close(); print('OK')"

# For NetCDF files
python -c "import netCDF4; netCDF4.Dataset('data.nc').close(); print('OK')"

# Analyze the file directly for details
file-organizer analyze data.h5 --verbose
```

If the file is intact but on a network drive, copy it locally before processing.

## CAD Format Errors

### DXF / DWG File Not Processed

**Error**: `ModuleNotFoundError: No module named 'ezdxf'` when organizing `.dxf` files

**Cause**: CAD file format dependencies are not installed.

**Solution**:

```bash
# Install CAD format support
pip install "local-file-organizer[cad]"

# Verify installation
python -c "import ezdxf; print('CAD extras OK')"
```

Note: `.dwg` support requires `ezdxf` (read-only) and is limited to DWG versions that ezdxf can parse. If a `.dwg` file fails, try exporting it to `.dxf` from your CAD application.

### DXF Parse Error

**Error**: `ezdxf.lldxf.const.DXFStructureError` or "DXF version not supported"

**Cause**: The DXF file uses an older version (pre-R12) or is created by software that writes non-standard DXF.

**Solution**:

```bash
# Analyze the file to see the detected DXF version
file-organizer analyze drawing.dxf --verbose

# Re-export from your CAD application as DXF R2010 or later
# Most applications: Save As → DXF → select version R2010/R2013/R2018
```



## Video Processing Errors

### Video Scene Detection Failed

**Error**: `ModuleNotFoundError: No module named 'scenedetect'` or "Scene detection error"

**Cause**: Video processing dependencies not installed or video format not supported.

**Solution**:

```bash
# Install video dependencies
pip install "local-file-organizer[video]"

# This includes: opencv-python, scenedetect, and related libraries

# Verify installation
python -c "import cv2; from scenedetect import detect, ContentDetector; print('OK')"
```

### Video Thumbnail Generation Failed

**Error**: `RuntimeError: Cannot generate thumbnail` or FFmpeg error during thumbnail extraction

**Cause**: Video codec not supported, video is corrupted, or FFmpeg cannot seek to the specified position.

**Solution**:

```bash
# Install FFmpeg with full codec support
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Generate a thumbnail manually with FFmpeg
ffmpeg -i video.mp4 -ss 00:00:05 -vframes 1 thumbnail.jpg

# Analyze the video file for details
file-organizer analyze video.mp4 --verbose
```

### Video Processing Timeout

**Error**: `TimeoutError: Video processing exceeded time limit`

**Cause**: Video file is very large or high resolution, causing processing to take too long.

**Solution**:

```bash
# Process videos sequentially to avoid resource contention
file-organizer organize /videos /output --sequential

# Skip vision processing for video-heavy directories
file-organizer organize /videos /output --text-only

# Analyze individual files to identify problematic ones
file-organizer analyze large-video.mp4 --verbose
```

## Image Processing Errors

### Image Deduplication Error

**Error**: `ModuleNotFoundError: No module named 'imagededup'` or "Deduplication failed"

**Cause**: Image deduplication dependencies not installed.

**Solution**:

```bash
# Install deduplication dependencies
pip install "local-file-organizer[dedup]"

# Scan for duplicates
file-organizer dedupe scan /path/to/images

# View the deduplication report
file-organizer dedupe report /path/to/images

# Resolve duplicates interactively
file-organizer dedupe resolve /path/to/images
```

### Image Format Conversion Failed

**Error**: `ValueError: Cannot convert image format` or PIL/Pillow error

**Cause**: Source image format is not supported by Pillow, or image is corrupted.

**Solution**:

```bash
# Update Pillow to latest version
pip install --upgrade Pillow

# Install additional image format support
pip install pillow-heif  # For HEIC/HEIF support

# Check supported formats
python -c "from PIL import Image; print(Image.registered_extensions())"

# Convert using external tool for unsupported formats
# Install ImageMagick
brew install imagemagick  # macOS
sudo apt-get install imagemagick  # Ubuntu/Debian

# Convert manually
convert input.rare output.jpg
```

### Image Resize/Optimization Failed

**Error**: `OSError: cannot write mode P as JPEG` or "Image optimization failed"

**Cause**: Image has transparency or palette mode that's incompatible with target format.

**Solution**:

```bash
# Manually convert problematic images before organizing
python -c "
from PIL import Image
img = Image.open('input.png').convert('RGB')
img.save('output.jpg')
"

# Analyze the image to understand the issue
file-organizer analyze input.png --verbose
```

## Search Issues

### Search Returns No Results

**Error**: No results returned when searching, or "Search index not built"

**Cause**: Search dependencies not installed or search has not been run against the target directory.

**Solution**:

```bash
# Install search dependencies
pip install "local-file-organizer[search]"

# Run a search query
file-organizer search "query terms" --type documents

# Use semantic search mode
file-organizer search "query terms" --semantic

# Limit results
file-organizer search "query terms" --limit 20

# Output as JSON for programmatic use
file-organizer search "query terms" --json
```

### Search Index Build Failed

**Error**: `ValueError` during index building or "Corpus too small"

**Cause**: Not enough documents to build vector index, or documents are empty/too short.

**Solution**:

```bash
# Check if files have extractable text
file-organizer analyze /path/to/files --verbose

# Ensure files contain actual text content
# Vector search requires at least a few meaningful documents
# Try with more files or use keyword-based search
file-organizer search "query" --type all
```

## Operation Undo / Rollback Issues

> **Note**: This section covers *file operation undo* — reversing file moves, renames, or copies performed by `file-organizer organize` and related commands. For rolling back a Docker deployment to a previous app version, see [Deployment Rollback](admin/troubleshooting.md#deployment-rollback) in the Admin Troubleshooting Guide.

### History Shows No Operations

**Error**: `file-organizer history` returns an empty list

**Cause**: No operations have been run yet in this workspace, or the workspace path has changed since the operations were recorded.

**Solution**:

```bash
# Check current workspace configuration
file-organizer config show

# List history for a specific path if needed
file-organizer history --path /path/to/workspace

# Run an organize operation first, then check history
file-organizer organize /input /output --dry-run
```

### Undo Fails or Reports "Nothing to Undo"

**Error**: `file-organizer undo` reports "No operations to undo" or similar

**Cause**: The operation history is empty, the last operation was already undone, or the files have been moved or deleted since the operation was recorded.

**Solution**:

```bash
# Review the full operation history first
file-organizer history

# Undo the most recent operation
file-organizer undo

# Undo a specific operation by ID (shown in history output)
file-organizer undo --id <operation-id>

# Preview what undo would do without making changes
file-organizer undo --dry-run
```

If files were manually moved after the organize operation, undo may not be able to locate them. In that case, you can review the history to see the original file paths and restore them manually.

## Getting Help

If you can't find a solution here:

1. **Check documentation**:
   - [Getting Started Guide](getting-started.md)
   - [Admin Troubleshooting](admin/troubleshooting.md) - Deployment and production issues
   - [Performance Tuning](admin/performance-tuning.md) - Memory and optimization
   - [FAQ](faq.md) - Frequently Asked Questions

2. **Review logs**:

   ```bash
   # Enable verbose logging
   file-organizer organize /input /output --verbose

   # Docker logs
   docker-compose logs

   # Check system logs
   journalctl -u file-organizer
   ```

3. **Community Support**:
   - [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues) - Report bugs
   - [GitHub Discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions) - Ask questions
   - Include: OS, Python version, error message, and steps to reproduce

4. **Diagnostic Information**:

   ```bash
   # System information
   file-organizer version
   python --version
   ollama --version

   # Hardware details
   file-organizer hardware-info
   ```
