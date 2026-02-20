# Installation Guide

## Overview

This guide covers installing the File Organizer system for deployment and administration.

## System Requirements

### Minimum Requirements

- Python 3.11 or higher
- 4GB RAM
- 10GB disk space (for models and application)
- Docker (optional, but recommended)
- Docker Compose 1.29+ (if using Docker)

### Recommended Requirements

- Python 3.11 or higher
- 8GB+ RAM
- 20GB+ disk space
- Modern Linux distribution (Ubuntu 20.04+) or macOS
- Docker and Docker Compose

## Installation Methods

### Method 1: Docker (Recommended)

#### Prerequisites

- Docker 20.10+
- Docker Compose 1.29+

#### Steps

1. **Clone the repository**:

   ```bash
   git clone https://github.com/curdriceaurora/Local-File-Organizer.git
   cd Local-File-Organizer
   ```

1. **Configure environment** (see Configuration Guide)

1. **Start services**:

   ```bash
   docker-compose up -d
   ```

1. **Access the web UI**:

   ```
   http://localhost:8000/ui/
   ```

### Method 2: Manual Installation

#### Prerequisites

- Python 3.11+
- pip package manager
- Virtual environment tool (venv or poetry)

#### Steps

1. **Clone the repository**:

   ```bash
   git clone https://github.com/curdriceaurora/Local-File-Organizer.git
   cd Local-File-Organizer
   ```

1. **Create virtual environment**:

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

1. **Install dependencies**:

   ```bash
   pip install -e .
   ```

1. **Install Ollama** (for AI models):

   ```bash
   # macOS/Linux
   curl -fsSL https://ollama.ai/install.sh | sh

   # Pull required models
   ollama pull qwen2.5:3b-instruct-q4_K_M
   ollama pull qwen2.5vl:7b-q4_K_M
   ```

1. **Start the application**:

   ```bash
   python app.py
   # Or using the CLI
   file-organizer web-ui --host 0.0.0.0 --port 8000
   ```

## Verification

### Docker Verification

```bash
# Check service status
docker-compose ps

# View application logs
docker-compose logs -f web
```

### Manual Installation Verification

```bash
# Verify Ollama is running
ollama ps

# Check available models
ollama list

# Test the API
curl http://localhost:8000/api/v1/health
```

## Next Steps

- See [Deployment Guide](deployment.md) for production setup
- See [Configuration Guide](configuration.md) for customization
- See [Monitoring Guide](monitoring.md) for monitoring and maintenance
