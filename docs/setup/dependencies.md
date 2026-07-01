# Dependencies & Optional Extras

This page is the canonical dependency matrix for installation extras defined in `pyproject.toml`.

## Base requirements

- Python 3.11+
- Ollama (for default local provider mode)
- Recommended resources: 8 GB RAM minimum, 16 GB preferred, ~10 GB storage for local models

## Install base package

```bash
# PyPI
pip install local-file-organizer

# Source checkout
pip install -e .
```

## Optional extras matrix

| Extra | Install command | What it enables | Type |
|------|---|---|---|
| `parsers` | `pip install -e ".[parsers]"` | PDF/Office/eBook/HTML parsing | Runtime |
| `web` | `pip install -e ".[web]"` | FastAPI/WS web stack dependencies | Runtime |
| `cloud` | `pip install -e ".[cloud]"` | OpenAI-compatible provider client (`openai`) | Runtime |
| `llama` | `pip install -e ".[llama]"` | Local llama.cpp GGUF inference | Runtime |
| `mlx` | `pip install -e ".[mlx]"` | Apple Silicon MLX inference | Runtime (macOS) |
| `claude` | `pip install -e ".[claude]"` | Anthropic Claude provider client | Runtime |
| `gui` | `pip install -e ".[gui]"` | PyQt6 GUI dependencies | Runtime/UI |
| `desktop` | `pip install -e ".[desktop]"` | Native desktop window (`pywebview`) | Runtime/UI |
| `audio` | `pip install -e ".[audio]"` | Audio transcription + metadata packages | Runtime |
| `video` | `pip install -e ".[video]"` | Video scene analysis packages | Runtime |
| `dedup` | `pip install -e ".[dedup]"` | Similarity dedupe dependencies | Runtime |
| `archive` | `pip install -e ".[archive]"` | 7z/RAR archive handling | Runtime |
| `scientific` | `pip install -e ".[scientific]"` | HDF5/NetCDF/MATLAB formats | Runtime |
| `cad` | `pip install -e ".[cad]"` | DXF/CAD parsing | Runtime |
| `build` | `pip install -e ".[build]"` | PyInstaller packaging tooling | Build |
| `docs` | `pip install -e ".[docs]"` | MkDocs documentation tooling | Docs |
| `dev` | `pip install -e ".[dev]"` | Test/lint/type/dev tooling | Development |
| `search` | `pip install -e ".[search]"` | BM25 ranking dependencies | Runtime |
| `all` | `pip install -e ".[all]"` | All extras above | Aggregate |

## Common install combinations

```bash
# Local default workflow
pip install -e ".[parsers,web]"

# Cloud/OpenAI-compatible or Claude providers
pip install -e ".[cloud,claude]"

# Full media + dedupe workflow
pip install -e ".[audio,video,dedup,archive]"
```

## System-level dependencies

- FFmpeg is required for most non-WAV audio inputs and recommended for richer media handling.
- Some extras have platform-specific requirements (for example, `mlx` on macOS only).

See [Audio & Video Processing](audio-video.md) for FFmpeg and acceleration details.
