# File Organizer v2 Configuration Guide

## Overview

Configuration is managed via a YAML file located at `config/file-organizer/config.yaml` (relative to your system's config directory). You can also manage configuration via the CLI or TUI.

## CLI Configuration

You can view and edit configuration using the `config` command:

```bash
# View current config
file-organizer config show

# Edit specific settings
file-organizer config edit --text-model "qwen2.5:3b-instruct-q4_K_M"
file-organizer config edit --temperature 0.7
```

## Configuration File Structure

### Global Settings

| Key | Description | Default |
|-----|-------------|---------|
| `default_methodology` | Organization style (`none`, `para`, `jd`) | `none` |
| `version` | Config version | `1.0` |

### Models

Settings for Local LLM inference.

```yaml
models:
  text_model: "qwen2.5:3b-instruct-q4_K_M"
  vision_model: "qwen2.5vl:7b-q4_K_M"
  temperature: 0.5
  max_tokens: 3000
  device: "auto"     # auto, cpu, cuda, mps
  framework: "ollama"
```

### OpenAI-Compatible Provider (Cloud or Local API)

File Organizer can route model calls to any OpenAI-compatible endpoint instead of
Ollama. This covers hosted providers (OpenAI) and local servers
(LM Studio, vLLM, Ollama's built-in OpenAI-compat endpoint).

Install the optional dependency first:

```bash
# From PyPI (installed package)
pip install "local-file-organizer[cloud]"

# From source checkout
pip install -e ".[cloud]"
```

Then configure via environment variables — no config file changes needed:

| Variable | Description | Default |
|----------|-------------|---------|
| `FO_PROVIDER` | `ollama` or `openai` | `ollama` |
| `FO_OPENAI_API_KEY` | API key (omit for local endpoints) | — |
| `FO_OPENAI_BASE_URL` | API base URL | — (OpenAI SDK default: `https://api.openai.com/v1`) |
| `FO_OPENAI_MODEL` | Text model name | `gpt-4o-mini` |
| `FO_OPENAI_VISION_MODEL` | Vision model name (falls back to `FO_OPENAI_MODEL`) | — |

**Examples:**

```bash
# OpenAI
FO_PROVIDER=openai \
FO_OPENAI_API_KEY=sk-... \
FO_OPENAI_MODEL=gpt-4o \
fo organize ~/Downloads

# LM Studio (fully local, no API key)
FO_PROVIDER=openai \
FO_OPENAI_BASE_URL=http://localhost:1234/v1 \
FO_OPENAI_MODEL=your-loaded-model \
fo organize ~/Downloads
```

> **Privacy note**: When `FO_PROVIDER=openai`, file content is sent to the
> configured endpoint. Use a local server (LM Studio, vLLM) to keep data
> on-device while using the OpenAI-compatible interface.

### Watcher

Configuration for the file system watcher.

```yaml
watcher:
  watch_directories:
    - "/Users/username/Downloads"
  recursive: true
  debounce_seconds: 2.0
  exclude_patterns:
    - "*.tmp"
    - ".DS_Store"
```

### Profiles

You can define multiple profiles (e.g., `work`, `personal`) and switch between them.

```bash
file-organizer config edit --profile work --methodology para
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `FILE_ORGANIZER_CONFIG` | Custom path to config file |
| `OLLAMA_HOST` | Ollama server URL (default: `http://localhost:11434`) |
| `FO_DISABLE_UPDATE_CHECK` | Set to `1` to disable update checks |
| `FO_PROVIDER` | AI provider: `ollama` (default) or `openai` |
| `FO_OPENAI_API_KEY` | API key for OpenAI-compatible provider |
| `FO_OPENAI_BASE_URL` | Custom endpoint URL (LM Studio, Groq, vLLM, etc.) |
| `FO_OPENAI_MODEL` | Text model name when `FO_PROVIDER=openai` |
| `FO_OPENAI_VISION_MODEL` | Vision model name (defaults to `FO_OPENAI_MODEL`) |

## Advanced Configuration

### PARA Methodology

Configure folder names for Projects, Areas, Resources, and Archives.

```yaml
para:
  project_dir: "Projects"
  area_dir: "Areas"
  resource_dir: "Resources"
  archive_dir: "Archive"
  auto_categorize: true
```

### Johnny Decimal

Configure your specific numbering scheme.

```yaml
johnny_decimal:
  scheme:
    name: "default"
    areas:
      - { name: "Finance", range_start: 10, range_end: 19 }
```
