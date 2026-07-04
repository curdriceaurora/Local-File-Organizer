# File Organizer Documentation

Welcome to the **File Organizer** documentation! A privacy-first, AI-powered local file management system that is local-first by default, with optional cloud provider integrations when explicitly configured.

## Essentials (Start Here)

Use this first-run terminal workflow:

```bash
fo setup
fo preview ~/Downloads
fo organize ~/Downloads ~/Organized
fo undo
```

Use `fo undo` after at least one organize run has been recorded.

Prefer a browser? Start with [Web UI Quick Start](web-ui/getting-started.md).

## Quick Navigation

=== "🚀 Essentials"

    - [Getting Started](getting-started.md)
    - [Core first run commands](cli-reference.md#core-first-run-commands)
    - [Workflow Map](USER_GUIDE.md#workflow-map-quick-paths)
    - [Web UI Quick Start](web-ui/getting-started.md)
    - [Troubleshooting](troubleshooting.md)

=== "🧭 Advanced / Admin / Developer"

    - [Terminal UI Guide](tui.md)
    - [Desktop App Guide](desktop-app.md)
    - [AI Provider Setup](setup/ai-providers.md)
    - [API Reference](api/index.md)
    - [Admin Guide](admin/index.md)
    - [Developer Guide](developer/index.md)
    - [Methodology selection workflow](USER_GUIDE.md#quick-workflow-choose-a-methodology)

## Key Features

- 🔒 **Privacy-First**: Local-first defaults with optional cloud provider opt-in
- 🤖 **AI-Powered**: Uses local LLMs for intelligent file organization
- 🎯 **Methodologies**: Supports PARA, Johnny Decimal, and custom organization systems
- 🔍 **Smart Search**: Full-text search with filters and saved searches
- 📊 **Analytics**: Storage analysis, duplicate detection, and insights
- 🔄 **Undo/Redo**: Reverse any operation instantly
- 🎨 **Multiple Interfaces**: Web UI, CLI, Terminal UI, and native desktop app
- 🔌 **Extensible**: Plugin system for custom functionality

## Supported File Types

File Organizer processes **48+ file formats** including:

- **Documents**: PDF, Word, Excel, PowerPoint, Markdown, EPUB
- **Images**: JPEG, PNG, GIF, BMP, TIFF
- **Video**: MP4, AVI, MKV, MOV, WMV
- **Audio**: MP3, WAV, FLAC, M4A, OGG
- **Archives**: ZIP, 7Z, TAR, RAR
- **Scientific**: HDF5, NetCDF, MATLAB files
- **CAD**: DXF, DWG, STEP, IGES

## System Requirements

- **Python**: 3.11+
- **RAM**: 8 GB minimum (16 GB recommended)
- **Storage**: ~10 GB for AI models
- **Ollama**: Latest version for local inference

## Documentation Sections

### Essentials

- [Getting Started](getting-started.md) - Install and complete your first run
- [Core first run commands](cli-reference.md#core-first-run-commands) - `setup`, `preview`, `organize`, `undo`
- [Workflow Map](USER_GUIDE.md#workflow-map-quick-paths) - Practical jump table by goal
- [Web UI Quick Start](web-ui/getting-started.md) - Secondary browser-first path
- [Troubleshooting](troubleshooting.md) - Common issues and fixes

### Advanced Setup & Interfaces

- [AI Provider Setup](setup/ai-providers.md) - OpenAI-compatible, Claude, llama.cpp, MLX
- [Dependencies & Optional Extras](setup/dependencies.md) - Canonical extras matrix and install groups
- [Models](setup/models.md) - AI model configuration
- [Audio & Video Processing](setup/audio-video.md) - Media analysis prerequisites and setup
- [Web UI Guide](web-ui/index.md) - Browser-based file management
- [Terminal UI Guide](tui.md) - Keyboard-driven terminal interface
- [Desktop App Guide](desktop-app.md) - Native OS desktop window
- [CLI Reference](cli-reference.md) - Full command-line reference

### API & Integration

- [API Reference](api/index.md) - Complete REST API documentation
- [Authentication](api/authentication.md) - API key management
- [WebSocket Events](api/websocket-api.md) - Real-time updates
- [Plugin Development](developer/plugin-development.md) - Build and extend plugin capabilities

### Deployment & Administration

- [Installation](admin/installation.md) - Setup instructions
- [Deployment Guide](admin/deployment.md) - Production deployment
- [Configuration](admin/configuration.md) - Environment setup
- [File Format Reference](admin/file-format-reference.md) - Supported formats and handling details
- [Audio & Video Processing](setup/audio-video.md) - Audio and video processing setup
- [Security](admin/security.md) - Security best practices
- [Monitoring](admin/monitoring.md) - Health checks and logging

### Configuration & Migration

- [Configuration Guide](CONFIGURATION.md) - Global and profile-level settings
- [Path Standardization & Migration](config/path-standardization.md) - XDG path migration and compatibility
- [Path Deprecation Notice](config/deprecation-notice.md) - Legacy path and config deprecations

### Methodology Workflows

- [Methodology selection workflow](USER_GUIDE.md#quick-workflow-choose-a-methodology) - Choose content-based vs PARA vs Johnny Decimal
- [Johnny Decimal User Guide](methodologies/johnny-decimal/user-guide.md#getting-started) - Step-by-step setup
- [Johnny Decimal Migration Guide](methodologies/johnny-decimal/migration.md#step-by-step-migration) - Migrate existing structures
- [Johnny Decimal + PARA Compatibility](methodologies/johnny-decimal/para-compatibility.md#integration-approaches) - Hybrid approach patterns

### Canonical setup references

- [Optional extras matrix](setup/dependencies.md#optional-extras-matrix)
- [Provider matrix](setup/ai-providers.md#provider-comparison)
- [Model/provider precedence](CONFIGURATION.md#modelprovider-precedence)

### CLI Feature Discoverability

- [Search commands](cli-reference.md#cli-search) - Pattern and semantic file search
- [Duplicate detection (`dedupe`)](cli-reference.md#cli-dedupe) - Duplicate scan and management workflows
- [Undo/Redo history (`history`)](cli-reference.md#cli-history) - Operation history and rollback navigation
- [Configuration (`config`)](CONFIGURATION.md) - Global and named-profile settings
- [Plugin marketplace (`marketplace`)](cli-reference.md#cli-marketplace) - Discover and manage marketplace plugins
- [Copilot assistant (`copilot`)](cli-reference.md#cli-copilot) - Natural-language workflows in CLI/TUI contexts
- [Profile behavior and compatibility](cli-reference.md#cli-profile) - Runtime-specific profile command availability

### Development & Extension

- [Architecture Guide](developer/architecture.md) - System design
- [Plugin Development](developer/plugin-development.md) - Creating plugins
- [API Clients](developer/api-clients.md) - Client libraries

## Getting Help

- **Issues**: Found a bug? [Report it on GitHub](https://github.com/curdriceaurora/Local-File-Organizer/issues)
- **Discussions**: [Ask questions in discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions)
- **Troubleshooting**: Check the [Troubleshooting Guide](troubleshooting.md)
- **FAQ**: Browse [Frequently Asked Questions](faq.md)

## Installation Quick Start

=== "Docker (Recommended)"

    ```bash
    git clone https://github.com/curdriceaurora/Local-File-Organizer.git
    cd Local-File-Organizer
    docker-compose up -d
    ```

    Access at `http://localhost:8000`

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

See the [Installation Guide](admin/installation.md) for detailed instructions.

## Documentation Updates

This documentation is maintained for File Organizer `2.0.0-beta.1`. For older versions, check the [GitHub releases](https://github.com/curdriceaurora/Local-File-Organizer/releases).

**Last Updated**: 2026-04-05
**Version**: 2.0.0-beta.1

______________________________________________________________________

## License

File Organizer is open source and available under the MIT License. See [LICENSE](https://github.com/curdriceaurora/Local-File-Organizer/blob/main/LICENSE) for details.
