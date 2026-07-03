# Getting Started with File Organizer

This guide will help you install and set up File Organizer quickly.

## Essentials first run (CLI)

If you're new, use this terminal-first path first:

```bash
fo setup
fo preview ~/Downloads
fo organize ~/Downloads ~/Organized
fo undo
```

Use `fo undo` after at least one organize run has been recorded.

Prefer a browser? Start with [Web UI Quick Start](web-ui/getting-started.md).

## Installation Methods

Choose the installation method that best fits your needs:

=== "Docker (Recommended)"

````markdown
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

````markdown
**Best for**: Quick testing, simple deployments

**Prerequisites**:
- Python 3.11 or higher
- Ollama installed and running
- 4GB+ available disk space

**Install**:

```bash
pip install local-file-organizer

# Start the API server
file-organizer serve
```

**Access**: Open browser to `http://localhost:8000/ui/`

See [Installation Guide](admin/installation.md) for options.
````

=== "Desktop App"

````markdown
**Best for**: Users who want a native window without managing a browser tab

**Prerequisites**:
- Python 3.11 or higher
- Ollama installed and running
- Linux only: `sudo apt-get install -y libgirepository1.0-dev gir1.2-webkit2-4.1`

**Install**:

```bash
# From PyPI
pip install "local-file-organizer[desktop]"

# Or from source
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd Local-File-Organizer
pip install -e ".[desktop]"
```

**Launch**:

```bash
ollama serve &
file-organizer desktop   # preferred
# fo desktop             # short alias
# file-organizer-desktop # compatibility script (still available)
```

A native OS window opens automatically — no browser required.

See [Desktop App Guide](desktop-app.md) for installation options, configuration, and troubleshooting.
````

=== "From Source"

````markdown
**Best for**: Development, customization

**Prerequisites**:
- Python 3.11 or higher
- Git
- Ollama installed
- Development tools (C compiler)

**Install**:

```bash
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd Local-File-Organizer
pip install -e .

# Pull required AI models
ollama pull qwen2.5:3b-instruct-q4_K_M      # Text model
ollama pull qwen2.5vl:7b-q4_K_M             # Vision model

# Start the API server
file-organizer serve
```

**Access**: Open browser to `http://localhost:8000/ui/`
````

## System Requirements

### Minimum

- **CPU**: 2-core processor
- **RAM**: 8 GB
- **Storage**: 10 GB (for AI models)
- **Python**: 3.11+
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

## Optional Features

Optional extras are documented in one canonical matrix:

- [Dependencies & Optional Extras](setup/dependencies.md#optional-extras-matrix)

Common examples:

```bash
# Source checkout with parser + web features
pip install -e ".[parsers,web]"

# Add cloud and Claude providers
pip install -e ".[cloud,claude]"

# Install all extras
pip install -e ".[all]"
```

## First Run Setup

After installation, File Organizer will guide you through initial setup:

### 1. Welcome Screen

When you first access File Organizer, you'll see a welcome screen with:

- License agreement
- Basic configuration options
- Link to full setup guide

### 2. AI Model Configuration

Use this decision rule:

1. **Use Ollama (default)** unless you specifically need a cloud model or a custom OpenAI-compatible endpoint.
2. If you need cloud/remote providers, use [AI Provider Setup](setup/ai-providers.md).

Default local models:

- `qwen2.5:3b-instruct-q4_K_M` (text)
- `qwen2.5vl:7b-q4_K_M` (vision)

Manual model pull (if needed):

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

For provider-specific environment variables, see:

- [AI Provider Setup](setup/ai-providers.md)
- [Configuration Guide](CONFIGURATION.md)

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

Use the web interface at:

```text
http://localhost:8000/ui/
```

On first run, incomplete setup redirects to:

```text
http://localhost:8000/ui/setup
```

Current top navigation surfaces:

- Home
- Files
- Organize
- Marketplace
- Settings
- Profile

Use `/docs` and `/redoc` for API documentation.

## Using the CLI

File Organizer also provides a command-line interface:

### Basic Commands

```bash
# Run guided quick-start setup (recommended first CLI command)
file-organizer start

# Start the web server and API
file-organizer serve

# Organize files
fo organize ~/Downloads ~/Organized

# Preview without moving (dry run)
file-organizer organize ./Downloads ./Organized --dry-run

# Preview organisation plan
file-organizer preview ./Downloads

# Show advanced tuning flags for organize
file-organizer organize --advanced-help

# Search for files
file-organizer search "*.pdf" ~/Documents
file-organizer search "report" ~/Documents --type text

# Analyze a file with AI
file-organizer analyze ./report.pdf
file-organizer analyze ./report.pdf --verbose

# Auto-tag files
file-organizer autotag suggest ./Documents
file-organizer autotag popular

# Detect duplicates
file-organizer dedupe scan ./Documents

# Analyse storage
file-organizer analytics ./Documents

# View operation history
file-organizer history

# Interactive AI assistant
file-organizer copilot chat
```

### Short Alias

Use `fo` instead of `file-organizer`:

```bash
fo start
fo serve
fo organize ./Downloads ./Organized
fo preview ./Downloads
fo undo
```

After your first run, use the full [CLI Reference](cli-reference.md) for search, analysis, dedupe, rules, marketplace, and other advanced commands.

## Choosing an Organization Methodology

File Organizer supports multiple organization systems:

### PARA (Projects, Areas, Resources, Archives)

**Best for**: Knowledge workers, complex projects

**Structure**:

```text
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

```text
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

### OpenAI-Compatible API or Claude Not Connecting

**Issue**: Provider fails to connect, returns 401, or "unknown provider" error.

**Solutions**:

```bash
# Install the required extra
pip install "local-file-organizer[cloud]"    # OpenAI / Groq / LM Studio
pip install "local-file-organizer[claude]"   # Anthropic Claude

# Set environment variables for your provider
export FO_PROVIDER=openai
export FO_OPENAI_API_KEY=sk-...
# For OpenAI-compatible endpoints (LM Studio, Groq, custom):
# export FO_OPENAI_BASE_URL=http://localhost:1234/v1

# For Claude
export FO_PROVIDER=claude
export FO_CLAUDE_API_KEY=sk-ant-...
```

See [AI Provider Setup](setup/ai-providers.md) for full configuration details and provider-specific troubleshooting.

### Port Already in Use

**Issue**: "Port 8000 is already in use"

**Solution**:

```bash
# Find process using port 8000
lsof -i :8000

# Use a different port when starting the server
file-organizer serve --port 8001

# Or with Docker Compose, edit .env: APP_PORT=8001
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

For more issues, see the [Troubleshooting Guide](troubleshooting.md) — covers optional dependency failures, all AI providers, TUI/desktop issues, audio/video/FFmpeg, search, deduplication, and more.

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
