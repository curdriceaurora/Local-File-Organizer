# Dependencies & Setup

## System Requirements

- **Python**: 3.11+
- **Ollama**: Latest version for local inference
- **Storage**: ~10 GB for models
- **RAM**: 8 GB minimum, 16 GB recommended

## Installation

```bash
# 1. Clone repository
git clone <repo-url>
cd Local-File-Organizer

# 2. Install Ollama and pull models
ollama pull qwen2.5:3b-instruct-q4_K_M    # Text: ~1.9 GB
ollama pull qwen2.5vl:7b-q4_K_M           # Vision: ~6.0 GB

# 3. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install package
pip install -e .

# 5. Verify
file-organizer --version
fo --version
```

## Optional Dependencies

```bash
pip install -e ".[audio]"       # Audio transcription (faster-whisper, torch)
pip install -e ".[video]"       # Video processing (opencv, scenedetect)
pip install -e ".[dedup]"       # Image deduplication (imagededup)
pip install -e ".[archive]"     # Archive support (7z, RAR)
pip install -e ".[scientific]"  # Scientific formats (HDF5, NetCDF, MATLAB)
pip install -e ".[cad]"         # CAD formats (ezdxf)
pip install -e ".[build]"       # Executable packaging (PyInstaller)
pip install -e ".[all]"         # Everything
```

> **Note**: Additional extras (`gui`, `docs`, `dev`, `web`, `parsers`, `cloud`) are available in `pyproject.toml` for GUI support, documentation building, development tooling, and cloud/OpenAI-compatible provider support.

## CLI Entrypoints

```toml
# pyproject.toml
[project.scripts]
file-organizer = "file_organizer.cli:main"
fo = "file_organizer.cli:main"
```

---

