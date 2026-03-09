---
created: 2026-03-08T23:57:34Z
last_updated: 2026-03-08T23:57:34Z
version: 1.0
author: Claude Code PM System
---

# Technical Context

> **CI patterns to follow**: `.claude/rules/ci-generation-patterns.md`
> Key: coverage gate is `cov-fail-under=95` in `pyproject.toml` — verify before documenting.
> PR CI runs `pytest -m "ci"` only (no coverage gate). Main push enforces 95%.

## Core Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Language | Python | 3.11+ |
| AI Inference | Ollama | >=0.1.0 |
| Audio transcription | faster-whisper | optional |
| Image processing | Pillow | >=10.0.0 |
| PDF processing | PyMuPDF | >=1.23.0 |
| CLI framework | Typer | >=0.12.0 |
| TUI framework | Textual | >=0.50.0 |
| Web API | FastAPI | >=0.109.0 |
| ASGI server | Uvicorn | >=0.27.0 |
| NLP | NLTK | >=3.8.0 |

## AI Models (Default)

| Task | Model | Size |
|------|-------|------|
| Text analysis | Qwen 2.5 3B (`qwen2.5:3b-instruct-q4_K_M`) | ~1.9 GB |
| Vision/image | Qwen 2.5-VL 7B (`qwen2.5vl:7b-q4_K_M`) | ~6.0 GB |
| Audio | faster-whisper (base) | ~140 MB |

## Build & Packaging

- **Build system**: setuptools >=68.0
- **Package name**: `file-organizer`
- **Entry points**: `file-organizer`, `fo` (short alias)
- **Install**: `pip install -e .`

## Testing

- **Framework**: pytest >=7.4.0 + pytest-asyncio >=0.23.0
- **Coverage gate**: 95% (`--cov-fail-under=95`) — enforced on main push
- **PR CI**: runs `pytest -m "ci"` (subset, no coverage gate)
- **Test count**: ~10,851 tests across 237 test files
- **Markers**: `smoke`, `ci`, `unit`, `integration`, `regression`

## Code Quality

- **Linter**: Ruff (strict)
- **Formatter**: Black (100 char line length)
- **Type checker**: mypy (strict)
- **Import sorter**: isort
- **Pre-commit hooks**: ruff check, pytest (subset), codespell, absolute-path-check, pymarkdown

## Optional Dependencies

```
pip install 'file-organizer[dedup]'    # imagededup for perceptual hashing
pip install 'file-organizer[audio]'   # faster-whisper
pip install 'file-organizer[scientific]' # h5py, scipy for HDF5/NetCDF/MAT
pip install 'file-organizer[cad]'     # ezdxf, cadquery for DXF/STEP
pip install 'file-organizer[dev]'     # pytest, mypy, ruff, etc.
```

## Infrastructure

- **CI/CD**: GitHub Actions
- **Containerization**: Docker + docker-compose
- **Deployment**: Local or self-hosted Docker
- **Python requirement**: >=3.11 (uses match statements, `datetime.UTC`, etc.)

## Key File Locations

| Purpose | Path |
|---------|------|
| Main package | `src/file_organizer/` |
| Tests | `tests/` |
| Config | `pyproject.toml` |
| Pre-commit | `.pre-commit-config.yaml` |
| CI workflow | `.github/workflows/ci.yml` |
| PM system | `.claude/` |
