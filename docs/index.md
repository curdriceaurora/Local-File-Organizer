# File Organizer Documentation

Welcome to the **File Organizer** documentation. File Organizer is a local file management system. It uses AI. It protects your privacy. It runs locally by default. You can configure optional cloud providers.

## Essentials

Use this workflow for your first run:

```bash
fo setup
fo preview ~/Downloads
fo organize ~/Downloads ~/Organized
fo undo
```

Run `fo undo` after you record at least one organize run.

Do you prefer a browser? Start with the [Web UI Quick Start](web-ui/getting-started.md).

## Quick Navigation

=== "🚀 Essentials"

    - [Getting Started](getting-started.md)
    - [Core first run commands](cli-reference.md#core-first-run-commands)
    - [Workflow Map](USER_GUIDE.md#workflow-map-quick-paths)
    - [Web UI Quick Start](web-ui/getting-started.md)
    - [Troubleshooting](troubleshooting.md)

=== "🧭 Advanced"

    - [Terminal UI Guide](tui.md)
    - [Desktop App Guide](desktop-app.md)
    - [AI Provider Setup](setup/ai-providers.md)
    - [API Reference](api/index.md)
    - [Admin Guide](admin/index.md)
    - [Developer Guide](developer/index.md)
    - [Methodology selection workflow](USER_GUIDE.md#quick-workflow-choose-a-methodology)

## Key Features

- 🔒 **Privacy-First**: The software operates locally. Cloud providers are optional.
- 🤖 **AI-Powered**: The software uses local LLMs to organize files.
- 🎯 **Methodologies**: The software supports PARA, Johnny Decimal, and custom systems.
- 🔍 **Smart Search**: The software includes full-text search with filters.
- 📊 **Analytics**: The software shows storage analysis and detects duplicates.
- 🔄 **Undo/Redo**: You can reverse any operation instantly.
- 🎨 **Multiple Interfaces**: The software provides a Web UI, CLI, Terminal UI, and desktop app.
- 🔌 **Extensible**: You can add custom functions with plugins.

## Supported File Types

File Organizer processes more than 48 file formats. These include:

- **Documents**: PDF, Word, Excel, PowerPoint, Markdown, EPUB
- **Images**: JPEG, PNG, GIF, BMP, TIFF
- **Video**: MP4, AVI, MKV, MOV, WMV
- **Audio**: MP3, WAV, FLAC, M4A, OGG
- **Archives**: ZIP, 7Z, TAR, RAR
- **Scientific**: HDF5, NetCDF, MATLAB files
- **CAD**: DXF, DWG, STEP, IGES

## System Requirements

- **Python**: Version 3.11 or higher
- **RAM**: 8 GB minimum (16 GB recommended)
- **Storage**: Approximately 10 GB for AI models
- **Ollama**: Latest version for local operation

## Documentation Sections

### Essentials

- [Getting Started](getting-started.md) - Install the software.
- [Core first run commands](cli-reference.md#core-first-run-commands) - Read about `setup`, `preview`, `organize`, and `undo`.
- [Workflow Map](USER_GUIDE.md#workflow-map-quick-paths) - Find tasks by goal.
- [Web UI Quick Start](web-ui/getting-started.md) - Learn the browser interface.
- [Troubleshooting](troubleshooting.md) - Solve common problems.

### Advanced Setup & Interfaces

- [AI Provider Setup](setup/ai-providers.md) - Configure OpenAI-compatible, Claude, llama.cpp, or MLX providers.
- [Dependencies & Optional Extras](setup/dependencies.md) - Install optional features.
- [Models](setup/models.md) - Configure AI models.
- [Audio & Video Processing](setup/audio-video.md) - Setup media analysis.
- [Web UI Guide](web-ui/index.md) - Manage files in the browser.
- [Terminal UI Guide](tui.md) - Use the keyboard interface.
- [Desktop App Guide](desktop-app.md) - Use the native desktop window.
- [CLI Reference](cli-reference.md) - Read the full command reference.

### API & Integration

- [API Reference](api/index.md) - Read the REST API documentation.
- [Authentication](api/authentication.md) - Manage API keys.
- [WebSocket Events](api/websocket-api.md) - Monitor real-time updates.
- [Plugin Development](developer/plugin-development.md) - Build custom plugins.

### Deployment & Administration

- [Installation](admin/installation.md) - Read setup instructions.
- [Deployment Guide](admin/deployment.md) - Deploy to production environments.
- [Configuration](admin/configuration.md) - Setup the environment.
- [File Format Reference](admin/file-format-reference.md) - Read about supported formats.
- [Security](admin/security.md) - Review security practices.
- [Monitoring](admin/monitoring.md) - Monitor health and read logs.

### Configuration & Migration

- [Configuration Guide](CONFIGURATION.md) - Adjust global and profile settings.
- [Path Standardization & Migration](config/path-standardization.md) - Read about XDG paths.
- [Path Deprecation Notice](config/deprecation-notice.md) - Read about legacy paths.

### Methodology Workflows

- [Methodology selection workflow](USER_GUIDE.md#quick-workflow-choose-a-methodology) - Choose an organization system.
- [Johnny Decimal User Guide](methodologies/johnny-decimal/user-guide.md#getting-started) - Setup Johnny Decimal.
- [Johnny Decimal Migration Guide](methodologies/johnny-decimal/migration.md#step-by-step-migration) - Migrate existing structures.
- [Johnny Decimal + PARA Compatibility](methodologies/johnny-decimal/para-compatibility.md#integration-approaches) - Combine systems.

### Canonical setup references

- [Optional extras matrix](setup/dependencies.md#optional-extras-matrix)
- [Provider matrix](setup/ai-providers.md#provider-comparison)
- [Model/provider precedence](CONFIGURATION.md#modelprovider-precedence)

### CLI Feature Discoverability

- [Search commands](cli-reference.md#cli-search) - Search files.
- [Duplicate detection (`dedupe`)](cli-reference.md#cli-dedupe) - Find duplicates.
- [Undo/Redo history (`history`)](cli-reference.md#cli-history) - View operation history.
- [Configuration (`config`)](CONFIGURATION.md) - Edit settings.
- [Plugin marketplace (`marketplace`)](cli-reference.md#cli-marketplace) - Find plugins.
- [Copilot assistant (`copilot`)](cli-reference.md#cli-copilot) - Use the AI assistant.
- [Profile behavior](cli-reference.md#cli-profile) - Read about profile commands.

### Development & Extension

- [Architecture Guide](developer/architecture.md) - Read system design.
- [Plugin Development](developer/plugin-development.md) - Create plugins.
- [API Clients](developer/api-clients.md) - Use client libraries.

## Getting Help

- **Issues**: [Report bugs on GitHub](https://github.com/curdriceaurora/Local-File-Organizer/issues)
- **Discussions**: [Ask questions in discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions)
- **Troubleshooting**: Read the [Troubleshooting Guide](troubleshooting.md)
- **FAQ**: Read [Frequently Asked Questions](faq.md)

## Installation Quick Start

=== "Docker (Recommended)"

    ```bash
    git clone https://github.com/curdriceaurora/Local-File-Organizer.git
    cd Local-File-Organizer
    docker-compose up -d
    ```

    Open `http://localhost:8000`

=== "Python Package"

    ```bash
    pip install local-file-organizer
    file-organizer serve
    ```

=== "From Source"

    ```bash
    git clone https://github.com/curdriceaurora/Local-File-Organizer.git
    cd Local-File-Organizer
    pip install -e .
    file-organizer serve
    ```

Read the [Installation Guide](admin/installation.md) to find detailed instructions.

## Documentation Updates

This documentation supports File Organizer `2.0.2`. To read older versions, look at the [GitHub releases](https://github.com/curdriceaurora/Local-File-Organizer/releases).

**Last Updated**: 2026-07-09
**Version**: 2.1.0

______________________________________________________________________

## License

File Organizer is open source software. It uses the MIT License. Read [LICENSE](https://github.com/curdriceaurora/Local-File-Organizer/blob/main/LICENSE) for details.
