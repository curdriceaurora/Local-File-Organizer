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
export OLLAMA_HOST=http://localhost:11434
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
kill -9 <PID>
```

## Optional Dependency Issues

### Module Not Found Error

**Error**: `ModuleNotFoundError: No module named 'faster_whisper'` or similar

**Cause**: Attempting to use a feature that requires optional dependencies not installed with the base package.

**Solution**:

Install the appropriate optional dependency group based on the feature you're using:

| Feature | Error Pattern | Install Command |
|---------|---------------|-----------------|
| Audio transcription | `faster_whisper`, `torch` | `pip install -e ".[audio]"` |
| Video processing | `cv2`, `scenedetect` | `pip install -e ".[video]"` |
| Image deduplication | `imagededup` | `pip install -e ".[dedup]"` |
| Semantic search | `rank_bm25`, `sklearn` | `pip install -e ".[search]"` |
| Archive support | `py7zr` | `pip install -e ".[archive]"` |
| Scientific formats | `h5py`, `netCDF4` | `pip install -e ".[scientific]"` |
| CAD file support | `ezdxf` | `pip install -e ".[cad]"` |
| Claude API provider | `anthropic` | `pip install -e ".[claude]"` |
| All features | Any of the above | `pip install -e ".[all]"` |

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
file-organizer organize ~/file-organizer-workspace --destination ~/organized

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
# Reduce batch size for processing
file-organizer organize /path --batch-size 10

# Process subdirectories separately
for dir in /path/*/; do
  file-organizer organize "$dir" --destination /output
done

# Use streaming mode for large directories
file-organizer organize /path --stream
```

For production deployments with high memory demands, see [Performance Tuning](admin/performance-tuning.md).

### Audio Transcription Out of Memory

**Error**: `RuntimeError: CUDA out of memory` or system OOM killer

**Cause**: Whisper model too large for available GPU memory, or processing very long audio files.

**Solution**:

```bash
# Use smaller model
file-organizer organize /audio --transcribe --whisper-model tiny

# Force CPU usage (slower but uses system RAM)
file-organizer organize /audio --transcribe --device cpu

# Process files one at a time
file-organizer organize /audio --transcribe --workers 1
```

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

# Example of correct YAML:
cat > config.yaml <<EOF
organize:
  destination: "~/organized"
  tags:
    - documents
    - photos
EOF
```

### Config File Not Found

**Error**: `FileNotFoundError: [Errno 2] No such file or directory: '/home/user/.config/file-organizer/config.yaml'`

**Cause**: Configuration file does not exist in expected XDG location.

**Solution**:

```bash
# Create default config directory
mkdir -p ~/.config/file-organizer

# Generate default config
file-organizer config init

# Or specify config file explicitly
file-organizer organize /path --config /path/to/config.yaml
```

### XDG Config Migration

**Error**: Warning about deprecated config location

**Cause**: Old config files in `~/.file-organizer` instead of XDG-compliant `~/.config/file-organizer`.

**Solution**:

```bash
# Migrate to XDG-compliant location
mkdir -p ~/.config/file-organizer
mv ~/.file-organizer/* ~/.config/file-organizer/

# Or set XDG_CONFIG_HOME explicitly
export XDG_CONFIG_HOME=~/.config
```

See [Path Standardization](config/path-standardization.md) for details on XDG migration.

## Web UI Issues

### Web Server Won't Start

**Error**: `Error: uvicorn is not installed.`

**Cause**: Web server dependencies are not installed.

**Solution**:

```bash
# Install web dependencies
pip install -e ".[web]"

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
# Check logs for specific error
file-organizer serve --log-level debug

# Verify all dependencies
pip install -e ".[web]"

# Check for port conflicts
lsof -i :8000

# Use different port if needed
file-organizer serve --port 8001
```

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
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, MPS: {torch.backends.mps.is_available() if hasattr(torch.backends, \"mps\") else False}')"

# If no GPU available, CPU mode works but is slower
file-organizer organize /audio --transcribe --device cpu
```

### Model Download Timeout

**Error**: `TimeoutError` or `ConnectionError` when downloading Whisper model

**Cause**: Network issues or slow connection when downloading large model files.

**Solution**:

```bash
# Increase timeout and retry
export HF_HUB_DOWNLOAD_TIMEOUT=600
file-organizer organize /audio --transcribe

# Pre-download models manually
python -c "from faster_whisper import WhisperModel; WhisperModel('base')"

# Use smaller model that downloads faster
file-organizer organize /audio --transcribe --whisper-model tiny

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

### Duplicate File Handling Error

**Error**: `FileExistsError: Destination file already exists` or "Duplicate file detected"

**Cause**: A file with the same name already exists in the destination directory, and the duplicate handling strategy is not configured.

**Solution**:

```bash
# Use automatic duplicate handling
file-organizer organize /path --duplicate-strategy rename

# Available strategies:
# - skip: Skip duplicates (default)
# - rename: Add suffix like file_001.jpg, file_002.jpg
# - overwrite: Replace existing files (use with caution)
# - compare: Only overwrite if content differs

# Configure default strategy in config
cat >> ~/.config/file-organizer/config.yaml <<EOF
organize:
  duplicate_strategy: rename
  duplicate_compare_hash: true  # Use content hash for deduplication
EOF
```

### Filename Too Long Error

**Error**: `OSError: [Errno 63] File name too long` or `OSError: [Errno 36] File name too long` (ENAMETOOLONG)

**Cause**: Generated filename exceeds filesystem limits (typically 255 characters on most systems).

**Solution**:

```bash
# Enable filename truncation
file-organizer organize /path --max-filename-length 200

# Configure in config file
cat >> ~/.config/file-organizer/config.yaml <<EOF
organize:
  max_filename_length: 200
  truncate_method: smart  # Preserves extension and important parts
EOF

# Manually rename problematic files first
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

```bash
# Enable automatic sanitization
file-organizer organize /path --sanitize-filenames

# Configure sanitization rules
cat >> ~/.config/file-organizer/config.yaml <<EOF
organize:
  sanitize_filenames: true
  sanitize_rules:
    - replace_spaces: false  # Keep spaces
    - remove_special: true   # Remove special characters
    - transliterate: true    # Convert unicode to ASCII
EOF

# Preview what files would be renamed
file-organizer organize /path --dry-run --sanitize-filenames
```

## Metadata Extraction Errors

### EXIF Data Extraction Failed

**Error**: `ValueError: Invalid EXIF data` or "Cannot read image metadata"

**Cause**: Image file has corrupted or non-standard EXIF metadata, or file is not actually an image.

**Solution**:

```bash
# Skip files with invalid metadata
file-organizer organize /path --skip-invalid-metadata

# Use fallback to file modification time
file-organizer organize /path --fallback-to-mtime

# Repair EXIF data with exiftool
# macOS
brew install exiftool

# Ubuntu/Debian
sudo apt-get install libimage-exiftool-perl

# Fix corrupted EXIF
exiftool -all= -tagsfromfile @ -all:all -unsafe -icc_profile image.jpg

# Verify file type
file image.jpg  # Should show "JPEG image data"
```

### PDF Metadata Extraction Timeout

**Error**: `TimeoutError: PDF processing timed out` or process hangs on certain PDFs

**Cause**: PDF file is very large, corrupted, or contains complex embedded content that takes too long to process.

**Solution**:

```bash
# Increase processing timeout
file-organizer organize /path --pdf-timeout 60

# Skip PDF metadata extraction
file-organizer organize /path --skip-pdf-metadata

# Configure in config file
cat >> ~/.config/file-organizer/config.yaml <<EOF
metadata:
  pdf_timeout: 60
  skip_large_pdfs: true
  max_pdf_size_mb: 100
EOF

# Repair corrupt PDF
gs -o repaired.pdf -sDEVICE=pdfwrite -dPDFSETTINGS=/prepress input.pdf
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

# Skip video metadata if not needed
file-organizer organize /path --skip-video-metadata
```

## Plugin/Extension Errors

### Plugin Load Failed

**Error**: `ImportError: Cannot load plugin` or "Plugin not found"

**Cause**: Plugin is not installed, has incompatible version, or has missing dependencies.

**Solution**:

```bash
# List available plugins
file-organizer plugin list

# Install plugin
file-organizer plugin install <plugin-name>

# Check plugin compatibility
file-organizer plugin info <plugin-name>

# Disable problematic plugin
file-organizer organize /path --disable-plugin <plugin-name>

# Configure plugin directory
export FO_PLUGIN_DIR=~/.config/file-organizer/plugins
```

### Plugin Configuration Error

**Error**: `ValueError: Invalid plugin configuration` or plugin crashes during execution

**Cause**: Plugin configuration file has invalid values or required settings are missing.

**Solution**:

```bash
# Generate default plugin config
file-organizer plugin init <plugin-name>

# Validate plugin config
file-organizer plugin validate <plugin-name>

# Check plugin logs
cat ~/.config/file-organizer/logs/plugins/<plugin-name>.log

# Reset plugin to defaults
file-organizer plugin reset <plugin-name>
```

## Backup and Recovery Issues

### Backup Creation Failed

**Error**: `IOError: Cannot create backup` or "Insufficient space for backup"

**Cause**: Not enough disk space, backup directory not writable, or backup operation timed out.

**Solution**:

```bash
# Check available disk space
df -h

# Specify different backup location
file-organizer organize /path --backup-dir /external/backup

# Use compression to save space
file-organizer organize /path --backup --backup-compress

# Configure backup settings
cat >> ~/.config/file-organizer/config.yaml <<EOF
backup:
  enabled: true
  directory: /external/backup
  compress: true
  keep_versions: 5
  incremental: true
EOF
```

### Restore from Backup Failed

**Error**: `FileNotFoundError: Backup not found` or "Backup integrity check failed"

**Cause**: Backup file is corrupted, missing, or was created with a different version.

**Solution**:

```bash
# List available backups
file-organizer backup list

# Verify backup integrity
file-organizer backup verify <backup-id>

# Restore from specific backup
file-organizer backup restore <backup-id> --destination /restore/path

# Restore specific files only
file-organizer backup restore <backup-id> --files "*.jpg" --destination /restore/path

# Check backup format version
file-organizer backup info <backup-id>
```

## Archive Processing Errors

### Cannot Extract Archive

**Error**: `RuntimeError: Archive extraction failed` or "Unsupported archive format"

**Cause**: Archive is corrupted, password-protected, or format is not supported.

**Solution**:

```bash
# Install archive support
pip install -e ".[archive]"

# Supported formats: ZIP, TAR, GZ, BZ2, XZ, 7Z, RAR (read-only)

# Extract with password
file-organizer organize /path --extract-archives --archive-password "password"

# Skip corrupted archives
file-organizer organize /path --extract-archives --skip-corrupt

# Test archive integrity first
7z t archive.7z
unzip -t archive.zip
tar -tzf archive.tar.gz
```

### Archive Bomb Detection

**Error**: `SecurityError: Archive bomb detected` or "Archive extraction aborted"

**Cause**: Archive contains excessive compression ratio (potential zip bomb) as a security measure.

**Solution**:

```bash
# Increase compression ratio threshold (use with caution)
file-organizer organize /path --extract-archives --max-compression-ratio 1000

# Skip archive extraction entirely
file-organizer organize /path --no-extract-archives

# Configure in config file
cat >> ~/.config/file-organizer/config.yaml <<EOF
archive:
  extract: true
  max_compression_ratio: 100  # Default safety limit
  max_extracted_size_gb: 10
  detect_bombs: true
EOF

# Manually inspect suspicious archive
7z l -slt archive.zip  # List contents without extracting
```

## Video Processing Errors

### Video Scene Detection Failed

**Error**: `ModuleNotFoundError: No module named 'scenedetect'` or "Scene detection error"

**Cause**: Video processing dependencies not installed or video format not supported.

**Solution**:

```bash
# Install video dependencies
pip install -e ".[video]"

# This includes: opencv-python, scenedetect, and related libraries

# Verify installation
python -c "import cv2; from scenedetect import detect, ContentDetector; print('OK')"

# Skip scene detection if not needed
file-organizer organize /path --no-video-scenes

# Configure scene detection sensitivity
cat >> ~/.config/file-organizer/config.yaml <<EOF
video:
  scene_detection: true
  threshold: 27.0  # Lower = more sensitive
  min_scene_length: 15  # Minimum frames
EOF
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

# Generate thumbnail from different timestamp
file-organizer organize /path --thumbnail-time 5  # 5 seconds into video

# Skip thumbnail generation
file-organizer organize /path --no-thumbnails

# Use first frame if seeking fails
cat >> ~/.config/file-organizer/config.yaml <<EOF
video:
  thumbnail: true
  thumbnail_time: 0  # Use first frame
  thumbnail_fallback: true
EOF
```

### Video Processing Timeout

**Error**: `TimeoutError: Video processing exceeded time limit`

**Cause**: Video file is very large or high resolution, causing processing to take too long.

**Solution**:

```bash
# Increase processing timeout
file-organizer organize /path --video-timeout 300  # 5 minutes

# Skip video processing for large files
file-organizer organize /path --skip-large-videos --max-video-size-mb 500

# Process videos in background
file-organizer organize /path --video-async

# Configure timeouts
cat >> ~/.config/file-organizer/config.yaml <<EOF
video:
  processing_timeout: 300
  max_size_mb: 500
  skip_large_files: true
  async_processing: true
EOF
```

## Image Processing Errors

### Image Deduplication Error

**Error**: `ModuleNotFoundError: No module named 'imagededup'` or "Deduplication failed"

**Cause**: Image deduplication dependencies not installed.

**Solution**:

```bash
# Install deduplication dependencies
pip install -e ".[dedup]"

# This includes: imagededup, and related libraries

# Run deduplication
file-organizer deduplicate /path --method phash

# Available methods:
# - phash: Perceptual hash (recommended, fastest)
# - dhash: Difference hash
# - whash: Wavelet hash
# - cnn: Deep learning (most accurate, requires GPU)

# Configure deduplication
cat >> ~/.config/file-organizer/config.yaml <<EOF
deduplication:
  enabled: true
  method: phash
  threshold: 5  # Lower = more strict
EOF
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
# Force RGB conversion
file-organizer organize /path --convert-to-rgb

# Skip optimization for problematic images
file-organizer organize /path --skip-optimization

# Configure image processing
cat >> ~/.config/file-organizer/config.yaml <<EOF
image:
  convert_to_rgb: true
  preserve_transparency: false
  optimize: true
  quality: 85
EOF

# Manually convert problematic images
python -c "from PIL import Image; img = Image.open('input.png').convert('RGB'); img.save('output.jpg')"
```

## Search Issues

### Search Returns No Results

**Error**: No results returned when searching, or "Search index not built"

**Cause**: Semantic search is not enabled, index hasn't been built, or required dependencies are missing.

**Solution**:

```bash
# Install search dependencies
pip install -e ".[search]"

# Enable semantic search in config
cat >> ~/.config/file-organizer/config.yaml <<EOF
search:
  enabled: true
  engine: hybrid  # BM25 + vector search
EOF

# Build search index
file-organizer index build /path/to/files

# Verify index exists
file-organizer index status

# Rebuild index if corrupted
file-organizer index rebuild /path/to/files
```

### Search Index Build Failed

**Error**: `ValueError` during index building or "Corpus too small"

**Cause**: Not enough documents to build vector index, or documents are empty/too short.

**Solution**:

```bash
# Check if files have extractable text
file-organizer analyze /path/to/files --verbose

# Use BM25-only mode for small corpora
cat >> ~/.config/file-organizer/config.yaml <<EOF
search:
  enabled: true
  engine: bm25  # Keyword-based only
EOF

# Ensure files contain actual text content
# Vector search requires at least a few meaningful documents
```

## Getting Help

If you can't find a solution here:

1. **Check documentation**:
   - [Getting Started Guide](getting-started.md)
   - [Admin Troubleshooting](admin/troubleshooting.md) - Deployment and production issues
   - [Performance Tuning](admin/performance-tuning.md) - Memory and optimization
   - [FAQ](faq.md) - Frequently Asked Questions

2. **Review logs**:
   ```bash
   # Enable debug logging
   file-organizer --log-level debug organize /path

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
   file-organizer --version
   python --version
   ollama --version

   # Environment details
   file-organizer diagnose
   ```
