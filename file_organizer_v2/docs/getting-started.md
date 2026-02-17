# Getting Started with File Organizer

This guide will help you install and set up File Organizer quickly.

## Installation Methods

Choose the installation method that best fits your needs:

=== "Docker (Recommended)"

````
**Best for**: Production deployments, consistent environments

**Prerequisites**:
- Docker & Docker Compose installed
- 4GB+ available disk space

**Install**:

```bash
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd Local-File-Organizer
cp .env.example .env
docker-compose up -d
```

**Access**: Open browser to `http://localhost:8000/ui/`

See [Deployment Guide](admin/deployment.md) for detailed Docker setup.
````

=== "Python Package"

````
**Best for**: Quick testing, simple deployments

**Prerequisites**:
- Python 3.9 or higher
- Ollama installed and running
- 4GB+ available disk space

**Install**:

```bash
pip install file-organizer
file-organizer serve
```

**Access**: Open browser to `http://localhost:8000/ui/`

See [Installation Guide](admin/installation.md) for options.
````

=== "From Source"

````
**Best for**: Development, customization

**Prerequisites**:
- Python 3.9 or higher
- Git
- Ollama installed
- Development tools (C compiler)

**Install**:

```bash
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd file_organizer_v2
pip install -e .

# Pull required AI models
ollama pull qwen2.5:3b-instruct-q4_K_M      # Text model
ollama pull qwen2.5vl:7b-q4_K_M             # Vision model

# Start the web server
file-organizer serve
```

**Access**: Open browser to `http://localhost:8000/ui/`
````

## System Requirements

### Minimum

- **CPU**: 2-core processor
- **RAM**: 8 GB
- **Storage**: 10 GB (for AI models)
- **Python**: 3.9+
- **Ollama**: Latest version

### Recommended

- **CPU**: 4+ cores
- **RAM**: 16 GB or more
- **Storage**: 20 GB SSD
- **GPU**: NVIDIA, AMD, or Apple Silicon (optional, for faster processing)

### Optional

- **FFmpeg**: For audio/video preprocessing
- **Node.js**: For plugin development
- **Docker**: For containerized deployment

## First Run Setup

After installation, File Organizer will guide you through initial setup:

### 1. Welcome Screen

When you first access File Organizer, you'll see a welcome screen with:

- License agreement
- Basic configuration options
- Link to full setup guide

### 2. AI Model Configuration

File Organizer requires local AI models:

- **Text Model**: `qwen2.5:3b-instruct-q4_K_M` (~1.9 GB)
- **Vision Model**: `qwen2.5vl:7b-q4_K_M` (~6.0 GB)

These are automatically pulled on first run if Ollama is available.

**Manual pull** (if needed):

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

### 3. Workspace Configuration

Set up your workspace:

- **Workspace Path**: Where to store workspace data
- **Watch Directories**: Which folders to monitor (optional)
- **Organization Methodology**: Choose PARA, Johnny Decimal, or Custom

### 4. API Configuration (Optional)

For external integrations:

- Generate API keys
- Configure rate limits
- Set security options

## Web Interface Overview

Once logged in, the web interface has these main sections:

### Dashboard

- Overview of recent activity
- Quick access to main features
- Storage statistics

### File Browser

- Browse and organize files
- Upload new files
- View file properties

### Organization

- Select methodology
- Configure options
- Start organization jobs
- Monitor progress

### Analysis

- Duplicate detection
- Storage analysis
- Metadata extraction

### Search

- Full-text search
- Apply filters
- Save searches
- Export results

### Settings

- Workspace management
- User preferences
- API configuration

## Using the CLI

File Organizer also provides a command-line interface:

### Basic Commands

```bash
# Organize files
file-organizer organize ./Downloads ./Organized

# Preview without moving
file-organizer organize ./Downloads ./Organized --dry-run

# Find files
file-organizer search "*.pdf"

# Detect duplicates
file-organizer dedupe scan ./Documents

# Analyze storage
file-organizer analyze ./Documents

# Start web server
file-organizer serve

# Interactive mode
file-organizer copilot chat
```

### Short Alias

Use `fo` instead of `file-organizer`:

```bash
fo organize ./Downloads ./Organized
fo search "report"
```

See [CLI Reference](cli-reference.md) for all commands.

## Choosing an Organization Methodology

File Organizer supports multiple organization systems:

### PARA (Projects, Areas, Resources, Archives)

**Best for**: Knowledge workers, complex projects

**Structure**:

```
PARA/
├── Projects/        # Active projects with deadlines
├── Areas/           # Ongoing responsibilities
├── Resources/       # Reference materials
└── Archives/        # Completed projects
```

**Learn more**: [PARA Guide](https://forte.com/reference/PARA)

### Johnny Decimal

**Best for**: Hierarchical organization, fixed categories

**Structure**:

```
JD/
├── 10-19 Area 1/
│   ├── 11 Category A
│   ├── 12 Category B
├── 20-29 Area 2/
│   ├── 21 Category C
```

**Learn more**: [Johnny Decimal Guide](https://johnnydecimal.com)

### Custom Methodology

Create your own organization system using rules and templates.

**Learn more**: [Custom Methodologies](developer/plugin-development.md)

## Common First Tasks

### 1. Upload Files

Click the **Upload Files** button or drag files directly into the browser.

Supported formats: 43+ file types including documents, images, videos, and more.

### 2. Organize Files

1. Click **Organize**
1. Select files to organize
1. Choose methodology (PARA, Johnny Decimal, etc.)
1. Review preview
1. Click **Apply** to organize

### 3. Find Duplicates

1. Click **Analysis**
1. Select **Duplicate Detection**
1. Choose directory to scan
1. Review results
1. Choose files to keep or remove

### 4. Search Files

1. Click **Search**
1. Enter search terms
1. Apply filters if needed
1. View results
1. Export or download

### 5. Configure Settings

1. Click **Settings** (gear icon)
1. Update workspace preferences
1. Generate API keys if needed
1. Configure methodology options

## Troubleshooting Installation

### Ollama Connection Failed

**Issue**: "Cannot connect to Ollama service"

**Solutions**:

```bash
# Start Ollama service
ollama serve

# Verify it's running
curl http://localhost:11434/api/version
```

### Port Already in Use

**Issue**: "Port 8000 is already in use"

**Solution**:

```bash
# Use different port
file-organizer serve --port 8001

# Or find process using port 8000
lsof -i :8000
```

### Models Not Found

**Issue**: "Model not found" error

**Solution**:

```bash
# Pull models manually
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M

# Verify models are installed
ollama list
```

### Out of Memory

**Issue**: "Out of memory" when processing files

**Solutions**:

- Increase available RAM
- Process smaller batches
- Reduce maximum file size
- Use CPU-only mode (slower but uses less RAM)

For more issues, see [Troubleshooting Guide](troubleshooting.md).

## Next Steps

- **Web Users**: Continue to [Web UI Guide](web-ui/index.md)
- **API Users**: See [API Reference](api/index.md)
- **Administrators**: Check [Deployment Guide](admin/deployment.md)
- **Developers**: Read [Developer Guide](developer/index.md)

## Getting Help

- 📚 **Documentation**: [Full documentation](index.md)
- ❓ **FAQ**: [Frequently Asked Questions](faq.md)
- 🐛 **Issues**: [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions)

______________________________________________________________________

**Ready to start?** Access File Organizer at `http://localhost:8000/ui/` and begin organizing your files!
