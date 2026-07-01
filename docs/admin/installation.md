# Installation Guide

## Overview

This guide covers practical installation paths for operators and administrators.

## Minimum requirements

- Python 3.11+
- 8 GB RAM (16 GB recommended)
- ~10 GB free storage for local models
- Ollama for default local provider mode

## Method 1: Docker Compose

```bash
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd Local-File-Organizer
cp .env.example .env
docker-compose up -d
```

Open `http://localhost:8000/ui/`.

> `.env.example` is for Docker Compose stack settings. It is not the canonical source for all app/provider configuration.

## Method 2: Python installation (source)

```bash
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd Local-File-Organizer
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

Optional provider/dependency extras are documented in [Dependencies & Optional Extras](../setup/dependencies.md).

## Pull default local models (Ollama mode)

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

## Start the app

```bash
# Web/API server
file-organizer serve

# Optional native desktop window (requires [desktop] extra)
file-organizer desktop
```

## Audio/video prerequisites

Install FFmpeg for broad audio format support:

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install -y ffmpeg
    ```

=== "Windows"
    ```bash
    winget install ffmpeg
    ```

See [Audio & Video Processing](../setup/audio-video.md) for accelerator and troubleshooting details.

## Verification

```bash
file-organizer version
fo version
curl http://localhost:8000/api/v1/health
```

## Next steps

- [Configuration Guide](configuration.md)
- [Deployment Guide](deployment.md)
- [Monitoring Guide](monitoring.md)
