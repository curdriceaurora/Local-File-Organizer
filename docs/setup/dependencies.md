# Dependencies and Optional Extras

This document shows the dependency matrix for installation extras in `pyproject.toml`.

## Base requirements

- Python 3.11 or newer
- Ollama (for the default local provider mode)
- Recommended resources: 8 GB RAM minimum, 16 GB preferred, 10 GB storage for local models

## Install the base package

```bash
# PyPI
pip install local-file-organizer

# Source checkout
pip install -e .
```

## Optional extras matrix

These commands use a source checkout. For PyPI installations, use `pip install "local-file-organizer[extra]"` instead of `-e`.

| Extra | Install command | Description | Type |
|------|---|---|---|
| `parsers` | `pip install -e ".[parsers]"` | Read PDF, Office, eBook, and HTML files | Runtime |
| `web` | `pip install -e ".[web]"` | Run the FastAPI and WS web stack | Runtime |
| `cloud` | `pip install -e ".[cloud]"` | Use the OpenAI-compatible provider client | Runtime |
| `llama` | `pip install -e ".[llama]"` | Run local llama.cpp GGUF inference | Runtime |
| `mlx` | `pip install -e ".[mlx]"` | Run Apple Silicon MLX inference | Runtime (macOS) |
| `claude` | `pip install -e ".[claude]"` | Use the Anthropic Claude provider client | Runtime |
| `gui` | `pip install -e ".[gui]"` | Use PyQt6 GUI dependencies | Runtime/UI |
| `desktop` | `pip install -e ".[desktop]"` | Run the native desktop window | Runtime/UI |
| `audio` | `pip install -e ".[audio]"` | Transcribe audio and read metadata | Runtime |
| `video` | `pip install -e ".[video]"` | Analyze video scenes | Runtime |
| `dedup` | `pip install -e ".[dedup]"` | Find and remove duplicate files | Runtime |
| `archive` | `pip install -e ".[archive]"` | Read 7z and RAR archives | Runtime |
| `scientific` | `pip install -e ".[scientific]"` | Read HDF5, NetCDF, and MATLAB files | Runtime |
| `cad` | `pip install -e ".[cad]"` | Read DXF and CAD files | Runtime |
| `build` | `pip install -e ".[build]"` | Build PyInstaller packages | Build |
| `docs` | `pip install -e ".[docs]"` | Build MkDocs documentation | Docs |
| `dev` | `pip install -e ".[dev]"` | Test, lint, and type code | Development |
| `search` | `pip install -e ".[search]"` | Rank BM25 search results | Runtime |
| `all` | `pip install -e ".[all]"` | Install all extras above | Aggregate |

## Common installation combinations

```bash
# A source checkout is necessary for the -e commands below

# Local default workflow
pip install -e ".[parsers,web]"

# Cloud or Claude providers
pip install -e ".[cloud,claude]"

# Full media and deduplication workflow
pip install -e ".[audio,video,dedup,archive]"
```

## System requirements

- You must install FFmpeg for most audio inputs.
- We recommend FFmpeg for advanced media processing.
- Some extras have platform requirements (for example, `mlx` operates on macOS only).

Read [Audio and Video Processing](audio-video.md) for FFmpeg and acceleration instructions.
