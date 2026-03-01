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

## Audio Processing Prerequisites

Audio transcription and metadata extraction require additional system dependencies beyond the Python packages.

### FFmpeg

FFmpeg is required for audio format conversion (e.g. `.m4a` to `.wav`) and preprocessing before transcription.

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

    Alternatively, download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to your `PATH`.

!!! note
    FFmpeg is required for any audio format other than raw `.wav`. Without it, audio files in formats like `.mp3`, `.m4a`, `.flac`, and `.ogg` cannot be processed.

### GPU Acceleration (Optional)

Audio transcription uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) which benefits from GPU acceleration. CPU inference works but is significantly slower.

#### NVIDIA CUDA

For NVIDIA GPUs, install the CUDA Toolkit and cuDNN:

```bash
# Verify GPU is detected
nvidia-smi

# Verify CUDA compiler
nvcc --version
```

#### Verifying GPU Support in PyTorch

```bash
python3 -c "import torch; print('CUDA:', torch.cuda.is_available()); print('cuDNN:', torch.backends.cudnn.version())"
```

!!! tip
    CPU-only inference works out of the box — GPU acceleration is optional. Apple Silicon users get hardware acceleration via MPS automatically.

### Installing the Audio Pack

```bash
pip install -e ".[audio]"
```

This installs the following packages:

| Package | Version | Purpose |
|---------|---------|---------|
| `faster-whisper` | >= 1.0.0 | Speech-to-text transcription |
| `torch` | >= 2.1.0 | GPU acceleration for transcription |
| `mutagen` | >= 1.47.0 | Audio metadata extraction |
| `tinytag` | >= 1.10.0 | Lightweight metadata fallback |
| `pydub` | >= 0.25.0 | Audio format manipulation |
| `ffmpeg-python` | >= 0.2.0 | FFmpeg Python bindings |

### Fallback Behavior

!!! warning
    The `torch` package is approximately 2 GB. For CPU-only environments where download size is a concern, install the CPU-only variant:

    ```bash
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install -e ".[audio]"
    ```

If the audio pack is not installed, audio files (`.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg`) are still detected and moved by the organizer but will not be transcribed or analyzed for content.

### Verifying Audio Support

```bash
# Verify FFmpeg
ffmpeg -version

# Verify faster-whisper
python3 -c "from faster_whisper import WhisperModel; print('faster-whisper OK')"

# Verify audio metadata
python3 -c "import mutagen; print('mutagen OK')"

# Verify torch device
python3 -c "import torch; print('Device:', 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu')"
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
