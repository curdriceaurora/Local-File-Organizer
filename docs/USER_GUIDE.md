# File Organizer v2 User Guide

## Introduction

File Organizer v2 is an AI-powered local file management system built with a privacy-first architecture. It uses local LLMs through Ollama to analyze, categorize, rename, and organize your files without sending any data to the cloud.

## Installation

### Prerequisites

- Python 3.11 or higher
- [Ollama](https://ollama.ai/) installed and running
- 8 GB RAM minimum (16 GB recommended)
- ~10 GB disk space for AI models

### Setup

```bash
# Clone the repository
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd Local-File-Organizer

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install the package
pip install -e .

# Pull the required AI models
ollama pull qwen2.5:3b-instruct-q4_K_M    # Text model (~1.9 GB)
ollama pull qwen2.5vl:7b-q4_K_M           # Vision model (~6.0 GB)

# Verify the installation
file-organizer version
```

### Optional Feature Packs

Extend functionality by installing optional dependency groups:

| Pack | Install Command | Features |
|------|----------------|----------|
| Audio | `pip install -e ".[audio]"` | Speech-to-text transcription (faster-whisper, torch) |
| Video | `pip install -e ".[video]"` | Scene detection, keyframe extraction (OpenCV) |
| Dedup | `pip install -e ".[dedup]"` | Image deduplication (perceptual hashing) |
| Archive | `pip install -e ".[archive]"` | 7z and RAR archive support |
| Scientific | `pip install -e ".[scientific]"` | HDF5, NetCDF, MATLAB file support |
| CAD | `pip install -e ".[cad]"` | DXF and other CAD format support |
| Build | `pip install -e ".[build]"` | Executable packaging (PyInstaller) |
| All | `pip install -e ".[all]"` | Everything above |

!!! note
    The audio pack requires FFmpeg and optionally a CUDA-capable GPU. See the [Installation Guide](admin/installation.md) for detailed prerequisites.

## CLI Commands Overview

File Organizer provides two equivalent entrypoints: `file-organizer` and the short alias `fo`.

| Command | Description |
|---------|-------------|
| `organize` | Organize files from an input directory to an output directory |
| `preview` | Preview organization changes without moving files |
| `search` | Search files by filename pattern/keyword with optional `--type` filter |
| `analyze` | Analyze a file and display AI-generated metadata |
| `tui` | Launch the Terminal User Interface |
| `serve` | Start the web UI server |
| `undo` | Undo the last file operation |
| `redo` | Redo a previously undone operation |
| `history` | Show operation history |
| `analytics` | Display storage analytics and insights |
| `version` | Show the application version |
| `config` | View and edit configuration |
| `model` | Manage AI models |
| `autotag` | Auto-tagging suggestions and batch operations |
| `copilot` | AI assistant for file management questions |
| `daemon` | Background file watching and auto-organization |
| `dedupe` | Find and resolve duplicate files |
| `rules` | Manage custom organization rules |
| `suggest` | Get smart file placement suggestions |
| `update` | Check for and install application updates |
| `profile` | Manage named configuration profiles |
| `marketplace` | Browse and install community plugins |
| `benchmark` | Run performance benchmarks |
| `api` | Start the REST API server |

## Organizing Files

### Basic Organization

The `organize` command analyzes files in an input directory and moves them to categorized folders in an output directory:

```bash
# Dry run first to preview changes
file-organizer organize ~/Downloads ~/Organized --dry-run

# Run the actual organization
file-organizer organize ~/Downloads ~/Organized

# Verbose output for debugging
file-organizer organize ~/Downloads ~/Organized --verbose
```

### Previewing Changes

Use `preview` for a quick dry-run view:

```bash
file-organizer preview ~/Downloads
```

### Searching Files

Search through organized files by filename pattern or keyword:

```bash
file-organizer search "quarterly report" ~/Organized
```

### Analyzing Individual Files

Inspect what the AI detects about a specific file:

```bash
file-organizer analyze ~/Documents/report.pdf
```

## Terminal UI (TUI)

The TUI provides a rich, interactive terminal interface for managing your files.

### Launching the TUI

```bash
file-organizer tui
```

### Views and Key Bindings

| Key | View |
|-----|------|
| `1` | File browser |
| `2` | Organized |
| `3` | Storage analytics |
| `4` | Methodology |
| `5` | Audio |
| `6` | History |
| `7` | Settings |
| `8` | Copilot chat |

Navigation: Use arrow keys to move, `Enter` to select, `q` to quit, `?` for help.

## Copilot

The Copilot is an AI assistant that can answer questions about your files and perform management tasks using natural language.

### Interactive Chat (REPL)

```bash
# Start an interactive session
file-organizer copilot chat

# Specify a working directory
file-organizer copilot chat --dir ~/Documents
```

### Single-Shot Mode

```bash
# Ask a single question
file-organizer copilot chat "How many PDF files are in my Documents folder?"
```

## Daemon and Background Processing

The daemon watches directories for new files and organizes them automatically.

### Starting the Daemon

```bash
# Watch a directory
file-organizer daemon start --watch-dir ~/Downloads --output-dir ~/Organized

# Run in foreground (useful for debugging)
file-organizer daemon start --watch-dir ~/Downloads --output-dir ~/Organized --foreground

# Adjust poll interval (seconds)
file-organizer daemon start --watch-dir ~/Downloads --output-dir ~/Organized --poll-interval 30

# Dry-run mode (log actions without moving files)
file-organizer daemon start --watch-dir ~/Downloads --output-dir ~/Organized --dry-run
```

### Managing the Daemon

```bash
# Check daemon status
file-organizer daemon status

# Stop the daemon
file-organizer daemon stop
```

## Organization Methodologies

File Organizer supports multiple organization systems. Configure these through the `config edit` command or the TUI settings view.

### Default AI Organization

The default method uses AI to analyze file content and suggest categories based on the content itself, not just file extensions.

### PARA Method

Projects, Areas, Resources, Archive -- a productivity-focused system:

- **Projects**: Active work with deadlines
- **Areas**: Ongoing responsibilities
- **Resources**: Reference materials by topic
- **Archive**: Completed or inactive items

### Johnny Decimal

A numerical categorization system using `XX.YY` numbering:

- **Areas** (10-19, 20-29, ...): Broad categories
- **Categories** (X1, X2, ...): Specific sub-categories
- **IDs** (XX.01, XX.02, ...): Individual items

## Deduplication

Find and resolve duplicate files using perceptual hashing (for images) and content-based comparison (for documents).

### Scanning for Duplicates

```bash
file-organizer dedupe scan ~/Documents
```

### Resolving Duplicates

```bash
file-organizer dedupe resolve ~/Documents
```

### Generating Reports

```bash
file-organizer dedupe report ~/Documents
```

!!! note
    Image deduplication requires the dedup optional pack: `pip install -e ".[dedup]"`

## Auto-Tagging

The auto-tagging system suggests and applies tags to files based on AI analysis of their content.

### Getting Tag Suggestions

```bash
# Suggest tags for files in a directory
file-organizer autotag suggest ~/Documents
```

### Applying Tags

```bash
# Apply specific tags to a file
file-organizer autotag apply ~/Documents/report.pdf finance quarterly
```

### Viewing Popular Tags

```bash
# List the most commonly used tags
file-organizer autotag popular
```

### Batch Operations

```bash
# Tag files in batch
file-organizer autotag batch ~/Documents

# View recently applied tags
file-organizer autotag recent
```

## Organization Rules

Rules let you override AI decisions with explicit patterns. When a file matches a rule, it is organized according to that rule instead of the AI suggestion.

### Listing Rules

```bash
# List all rules
file-organizer rules list

# List rule sets
file-organizer rules sets
```

### Adding Rules

```bash
file-organizer rules add my-rule --pattern "*.invoice.*" --action move --dest "Documents/Financial"
```

### Previewing and Managing Rules

```bash
# Preview what a rule would match in a directory
file-organizer rules preview ~/Documents

# Remove a rule
file-organizer rules remove my-rule

# Export rules to a YAML file
file-organizer rules export --output rules-backup.yaml

# Import rules from a YAML file
file-organizer rules import rules-backup.yaml
```

## Smart Suggestions

Get AI-powered suggestions for where to place files based on your existing directory structure and past organization patterns.

### Getting Suggestions

```bash
# Suggest placements for files
file-organizer suggest files ~/Unsorted

# View detected patterns
file-organizer suggest patterns ~/Unsorted
```

### Applying Suggestions

```bash
file-organizer suggest apply ~/Unsorted
```

## Analytics

View storage analytics, file distribution, and organization metrics.

```bash
# Display analytics dashboard
file-organizer analytics
```

## Profiles

Profiles allow you to save and switch between different configuration sets. This is useful for managing separate environments (e.g., work vs. personal).

### Managing Profiles

```bash
# List all profiles
file-organizer profile list

# Show current active profile
file-organizer profile current

# Create a new profile
file-organizer profile create work

# Activate a profile
file-organizer profile activate work

# Delete a profile
file-organizer profile delete old-profile
```

### Exporting and Importing

```bash
# Export a profile (--output is required)
file-organizer profile export work --output work-profile.json

# Import a profile from a JSON file
file-organizer profile import work-profile.json

# Merge two or more profiles into a new one (--output is required)
file-organizer profile merge work personal --output combined
```

## Undo and Redo

All file move operations are tracked and reversible.

```bash
# Undo the last operation
file-organizer undo

# Redo the last undone operation
file-organizer redo

# View operation history
file-organizer history
```

## Web UI

File Organizer includes a browser-based interface for managing files visually.

### Starting the Web Server

```bash
# Start with default settings (localhost:8000)
file-organizer serve

# Specify host and port
file-organizer serve --host 0.0.0.0 --port 9000
```

Then open `http://localhost:8000/ui/` in your browser.

## Configuration

### Viewing Configuration

```bash
# Show current configuration
file-organizer config show

# Show configuration for a specific profile
file-organizer config show --profile work

# List available configuration profiles
file-organizer config list
```

### Editing Configuration

```bash
# Edit configuration interactively
file-organizer config edit

# Edit specific settings directly
file-organizer config edit --text-model "qwen2.5:3b-instruct-q4_K_M"
file-organizer config edit --vision-model "qwen2.5vl:7b-q4_K_M"
file-organizer config edit --temperature 0.7
file-organizer config edit --device auto

# Edit a specific profile's configuration
file-organizer config edit --profile work
```

## AI Model Management

### Listing Models

```bash
# List all available models
file-organizer model list

# Filter by type
file-organizer model list --type text
file-organizer model list --type vision
```

### Pulling Models

```bash
# Pull a model by name
file-organizer model pull qwen2.5:3b-instruct-q4_K_M
```

### Cache Management

```bash
# View model cache status
file-organizer model cache
```

## Self-Update

### Checking for Updates

```bash
# Check if a newer version is available
file-organizer update check

# Include pre-release versions
file-organizer update check --pre
```

### Installing Updates

```bash
# Download and install the latest version
file-organizer update install

# Dry run (download without installing)
file-organizer update install --dry-run
```

## Supported File Types

| Category | Formats |
|----------|---------|
| Documents | `.txt`, `.md`, `.pdf`, `.docx`, `.doc`*, `.csv`, `.xlsx`, `.xls`*, `.pptx` |
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.tif` |
| Video | `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv` |
| Audio | `.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg` |
| Archives | `.zip`, `.7z`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.rar` |
| Scientific | `.hdf5`, `.h5`, `.hdf`, `.nc`, `.nc4`, `.netcdf`, `.mat` |
| CAD | `.dxf`, `.dwg`, `.step`, `.stp`, `.iges`, `.igs` |

*Legacy formats (`.doc`, `.xls`) have limited support and may return `None` or require additional dependencies. See the [File Format Reference](admin/file-format-reference.md) for details.

!!! tip
    Some format categories require optional feature packs. See [Optional Feature Packs](#optional-feature-packs) above.

## Privacy and Security

File Organizer is designed to keep your data completely private:

- All AI processing runs locally through Ollama -- no files or content are uploaded to any cloud service.
- Network requests are limited to:
  - Communicating with your local Ollama instance (localhost only)
  - Checking for application updates (optional, can be disabled)
- No telemetry, analytics, or usage tracking of any kind.

## Troubleshooting

### Ollama Not Running

If you see connection errors, ensure Ollama is running:

```bash
ollama ps
```

If no models are listed, pull the required models:

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

### Verbose Output

Add `--verbose` (or `-v`) to any command for detailed logging:

```bash
file-organizer organize ~/Downloads ~/Organized --verbose
```

### Checking Health

Verify the API server is responding:

```bash
curl http://localhost:8000/api/v1/health
```

For more detailed troubleshooting, see [Troubleshooting](troubleshooting.md).
