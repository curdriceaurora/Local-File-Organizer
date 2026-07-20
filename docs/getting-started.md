# Getting Started with File Organizer

This document helps you to install and configure File Organizer quickly.

## First run with CLI

If you are a new user, use this terminal procedure:

```bash
fo setup
fo preview ~/Downloads
fo organize ~/Downloads ~/Organized
fo undo
```

Use `fo undo` after you record one organize run.

Do you prefer a browser? Read the [Web UI Quick Start](web-ui/getting-started.md).

## Install Methods

Choose an installation method:

=== "Docker (Recommended)"

````markdown
**Best for**: Production deployments and consistent environments

**Requirements**:
- Install Docker and Docker Compose.
- Have 4GB or more of available disk space.

**Install**:

```bash
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd Local-File-Organizer
cp .env.example .env
docker-compose up -d
```

**Access**: Open your browser to `http://localhost:8000/ui/`

Read the [Deployment Guide](admin/deployment.md) for more Docker setup data.
````

=== "Python Package"

````markdown
**Best for**: Quick tests and simple deployments

**Requirements**:
- Install Python 3.11 or higher.
- Install and start Ollama.
- Have 4GB or more of available disk space.

**Install**:

```bash
pip install local-file-organizer

# Start the API server
file-organizer serve
```

**Access**: Open your browser to `http://localhost:8000/ui/`

Read the [Installation Guide](admin/installation.md) for more options.
````

=== "Desktop App"

````markdown
**Best for**: Users who want a native window.

**Requirements**:
- Install Python 3.11 or higher.
- Install and start Ollama.
- Linux only: run `sudo apt-get install -y libgirepository1.0-dev gir1.2-webkit2-4.1`

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

A native OS window opens automatically. You do not need a browser.

Read the [Desktop App Guide](desktop-app.md) for installation options and configuration procedures.
````

=== "From Source"

````markdown
**Best for**: Development and customization

**Requirements**:
- Install Python 3.11 or higher.
- Install Git.
- Install Ollama.
- Install development tools (C compiler).

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

**Access**: Open your browser to `http://localhost:8000/ui/`
````

## System Requirements

### Minimum Requirements

- **CPU**: 2-core processor
- **RAM**: 8 GB
- **Storage**: 10 GB (for AI models)
- **Python**: 3.11+
- **Ollama**: Latest version

### Recommended Requirements

- **CPU**: 4 cores or more
- **RAM**: 16 GB or more
- **Storage**: 20 GB SSD
- **GPU**: NVIDIA, AMD, or Apple Silicon

### Optional Requirements

- **FFmpeg**: Prepare audio and video.
- **Node.js**: Develop plugins.
- **Docker**: Use containers for deployment.

## Optional Features

Find the optional extras in one matrix:

- [Dependencies & Optional Extras](setup/dependencies.md#optional-extras-matrix)

Common examples:

```bash
# Source checkout with parser and web features
pip install -e ".[parsers,web]"

# Add cloud and Claude providers
pip install -e ".[cloud,claude]"

# Install all extras
pip install -e ".[all]"
```

## First Run Setup

File Organizer starts an initial setup procedure after installation:

### 1. Welcome Screen

When you first open File Organizer, a welcome screen shows:

- The license agreement.
- Basic configuration options.
- A link to the full setup guide.

### 2. AI Model Configuration

Use this rule to make a decision:

1. **Use Ollama (default)** unless you need a cloud model.
2. If you need cloud providers, use the [AI Provider Setup](setup/ai-providers.md).

Default local models:

- `qwen2.5:3b-instruct-q4_K_M` (text)
- `qwen2.5vl:7b-q4_K_M` (vision)

Manual model pull:

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

Read these documents to find provider-specific environment variables:

- [AI Provider Setup](setup/ai-providers.md)
- [Configuration Guide](CONFIGURATION.md)

### 3. Workspace Configuration

Set up your workspace:

- **Workspace Path**: Give the software a location to store workspace data.
- **Watch Directories**: Give the software folders to monitor.
- **Organization Methodology**: Choose PARA, Johnny Decimal, or Custom.

### 4. API Configuration

Configure external integrations:

- Generate API keys.
- Configure rate limits.
- Set security options.

## Web Interface Overview

Use the web interface at this address:

```text
http://localhost:8000/ui/
```

During the first run, an incomplete setup goes to this address:

```text
http://localhost:8000/ui/setup
```

Current top navigation sections:

- Home
- Files
- Organize
- Marketplace
- Settings
- Profile

Use `/docs` and `/redoc` to find API documentation.

## Use the CLI

File Organizer includes a command-line interface:

### Basic Commands

```bash
# Run guided quick-start setup
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

Use the full [CLI Reference](cli-reference.md) for advanced commands.

## Organization Methodology

File Organizer includes multiple organization systems:

### PARA

**Best for**: Knowledge workers and complex projects.

**Structure**:

```text
PARA/
├── Projects/        # Active projects with deadlines
├── Areas/           # Ongoing responsibilities
├── Resources/       # Reference materials
└── Archives/        # Completed projects
```

**Learn more**: Read the [PARA Guide](https://forte.com/reference/PARA).

### Johnny Decimal

**Best for**: Hierarchical organization and fixed categories.

**Structure**:

```text
JD/
├── 10-19 Area 1/
│   ├── 11 Category A
│   ├── 12 Category B
├── 20-29 Area 2/
│   ├── 21 Category C
```

**Learn more**: Read the [Johnny Decimal Guide](https://johnnydecimal.com).

### Custom Methodology

Create your own organization system with rules and templates.

**Learn more**: Read [Custom Methodologies](developer/plugin-development.md).

## Common First Tasks

### 1. Upload Files

Click **Upload Files** or drag files into the browser. The software supports 43 or more file types.

### 2. Organize Files

1. Click **Organize**.
2. Select files to organize.
3. Choose the methodology.
4. Review the preview.
5. Click **Apply**.

### 3. Find Duplicates

1. Click **Analysis**.
2. Select **Duplicate Detection**.
3. Choose the directory to scan.
4. Review the results.
5. Choose the files to keep or remove.

### 4. Search Files

1. Click **Search**.
2. Type the search terms.
3. Apply filters.
4. View the results.
5. Export or download the results.

### 5. Configure Settings

1. Click **Settings**.
2. Update the workspace preferences.
3. Generate API keys.
4. Configure methodology options.

## Troubleshoot Installation

### Ollama Connection Failed

**Problem**: The software shows "Cannot connect to Ollama service".

**Solutions**:

```bash
# Start Ollama service
ollama serve

# Verify it operates correctly
curl http://localhost:11434/api/version
```

### AI Provider Not Connecting

**Problem**: Provider fails to connect or shows an "unknown provider" error.

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

Read [AI Provider Setup](setup/ai-providers.md) for full configuration data.

### Port Already in Use

**Problem**: The software shows "Port 8000 is already in use".

**Solution**:

```bash
# Find process using port 8000
lsof -i :8000

# Use a different port when you start the server
file-organizer serve --port 8001

# Or with Docker Compose, edit .env: APP_PORT=8001
```

### Models Not Found

**Problem**: The software shows a "Model not found" error.

**Solution**:

```bash
# Pull models manually
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M

# Verify models are installed
ollama list
```

### Out of Memory

**Problem**: The software shows "Out of memory" when it processes files.

**Solutions**:

- Increase the available RAM.
- Process smaller batches of files.
- Decrease the maximum file size.
- Use CPU-only mode.

Read the [Troubleshooting Guide](troubleshooting.md) for more solutions.

## Next Steps

- **Web Users**: Read the [Web UI Guide](web-ui/index.md).
- **API Users**: Read the [API Reference](api/index.md).
- **Administrators**: Read the [Deployment Guide](admin/deployment.md).
- **Developers**: Read the [Developer Guide](developer/index.md).

## Getting Help

- 📚 **Documentation**: [Full documentation](index.md)
- ❓ **FAQ**: [Frequently Asked Questions](faq.md)
- 🐛 **Issues**: [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions)

______________________________________________________________________

**Ready to start?** Open File Organizer at `http://localhost:8000/ui/` and start to organize your files!
