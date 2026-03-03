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

- `FILE_ORGANIZER_CONFIG`: Custom path to config file.
- `OLLAMA_HOST`: URL of the Ollama server (default: `http://localhost:11434`).
- `FO_DISABLE_UPDATE_CHECK`: Set to `1` to disable update checks.

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
