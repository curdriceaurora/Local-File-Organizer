# File Organizer Documentation

Welcome to the **File Organizer** documentation! A privacy-first, AI-powered local file management system that organizes files intelligently using local LLMs with zero cloud dependencies.

## Quick Navigation

=== "🚀 Getting Started"

    **New to File Organizer?** Start here to understand the basics.

    - [Installation & Setup](getting-started.md)
    - [Web UI Quick Start](web-ui/getting-started.md)
    - [CLI Reference](cli-reference.md)

=== "🖥️ Web Interface"

    **Using the web browser interface?** Learn how to use all features.

    - [File Management](web-ui/file-management.md)
    - [Organization Workflows](web-ui/organization.md)
    - [Analysis & Search](web-ui/analysis-search.md)
    - [Settings & Configuration](web-ui/settings.md)

=== "📚 API Reference"

    **Building integrations?** Use our REST API.

    - [Authentication](api/authentication.md)
    - [File Endpoints](api/file-endpoints.md)
    - [Organization Endpoints](api/organization-endpoints.md)
    - [Search & Analysis](api/search-endpoints.md)

=== "🔧 Deployment"

    **Running your own instance?** Deploy and configure File Organizer.

    - [Installation](admin/installation.md)
    - [Deployment](admin/deployment.md)
    - [Configuration](admin/configuration.md)
    - [Monitoring](admin/monitoring.md)

=== "👨‍💻 Development"

    **Extending File Organizer?** Build plugins and integrations.

    - [Architecture](developer/architecture.md)
    - [Plugin Development](developer/plugin-development.md)
    - [API Clients](developer/api-clients.md)

## Key Features

- 🔒 **Privacy-First**: 100% local processing, zero cloud dependencies
- 🤖 **AI-Powered**: Uses local LLMs for intelligent file organization
- 🎯 **Methodologies**: Supports PARA, Johnny Decimal, and custom organization systems
- 🔍 **Smart Search**: Full-text search with filters and saved searches
- 📊 **Analytics**: Storage analysis, duplicate detection, and insights
- 🔄 **Undo/Redo**: Reverse any operation instantly
- 🎨 **Multiple Interfaces**: Web UI, CLI, and Terminal UI
- 🔌 **Extensible**: Plugin system for custom functionality

## Supported File Types

File Organizer processes **43+ file formats** including:

- **Documents**: PDF, Word, Excel, PowerPoint, Markdown, EPUB
- **Images**: JPEG, PNG, GIF, BMP, TIFF
- **Video**: MP4, AVI, MKV, MOV, WMV
- **Audio**: MP3, WAV, FLAC, M4A, OGG
- **Archives**: ZIP, 7Z, TAR, RAR
- **Scientific**: HDF5, NetCDF, MATLAB files
- **CAD**: DXF, DWG, STEP, IGES

## System Requirements

- **Python**: 3.9+
- **RAM**: 8 GB minimum (16 GB recommended)
- **Storage**: ~10 GB for AI models
- **Ollama**: Latest version for local inference

## Documentation Sections

### User Guides

- [Web UI Guide](web-ui/index.md) - Browser-based file management
- [Getting Started](getting-started.md) - Initial setup and overview
- [CLI Reference](cli-reference.md) - Command-line interface guide
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

### API & Integration

- [API Reference](api/index.md) - Complete REST API documentation
- [Authentication](api/authentication.md) - API key management
- [WebSocket Events](api/websocket-api.md) - Real-time updates

### Deployment & Administration

- [Installation](admin/installation.md) - Setup instructions
- [Deployment Guide](admin/deployment.md) - Production deployment
- [Configuration](admin/configuration.md) - Environment setup
- [Security](admin/security.md) - Security best practices
- [Monitoring](admin/monitoring.md) - Health checks and logging

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
    pip install file-organizer
    file-organizer serve
    ```

=== "From Source"

    ```bash
    git clone https://github.com/curdriceaurora/Local-File-Organizer.git
    cd file_organizer_v2
    pip install -e .
    file-organizer serve
    ```

See the [Installation Guide](admin/installation.md) for detailed instructions.

## Documentation Updates

This documentation is maintained for File Organizer v2.0+. For older versions, check the [GitHub releases](https://github.com/curdriceaurora/Local-File-Organizer/releases).

**Last Updated**: 2026-02-16
**Version**: 2.0.0+

______________________________________________________________________

## License

File Organizer is open source and available under the MIT License. See [LICENSE](https://github.com/curdriceaurora/Local-File-Organizer/blob/main/LICENSE) for details.
