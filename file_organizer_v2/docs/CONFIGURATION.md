# Configuration Guide

## Overview

File Organizer uses YAML-based configuration stored in `~/.config/file-organizer/config.yaml`. Multiple named profiles are supported.

## Configuration File

```yaml
# ~/.config/file-organizer/config.yaml
profiles:
  default:
    version: "1.0"
    default_methodology: none    # none, para, jd
    models:
      text_model: "qwen2.5:3b-instruct-q4_K_M"
      vision_model: "qwen2.5vl:7b-q4_K_M"
      temperature: 0.5
      max_tokens: 3000
      device: auto               # auto, cpu, cuda, mps, metal
      framework: ollama           # ollama, llama_cpp, mlx

  work:
    version: "1.0"
    default_methodology: para
    models:
      text_model: "qwen2.5:3b-instruct-q4_K_M"
      vision_model: "qwen2.5vl:7b-q4_K_M"
      temperature: 0.3
      max_tokens: 3000
      device: auto
      framework: ollama
```

## Settings Reference

### Models

| Setting | Default | Description |
|---------|---------|-------------|
| `text_model` | `qwen2.5:3b-instruct-q4_K_M` | Ollama model for text processing |
| `vision_model` | `qwen2.5vl:7b-q4_K_M` | Ollama model for image/video |
| `temperature` | `0.5` | Generation randomness (0.0 = deterministic, 1.0 = creative) |
| `max_tokens` | `3000` | Maximum tokens for generation |
| `device` | `auto` | Inference device |
| `framework` | `ollama` | Inference framework |

### Device Options

| Device | Description |
|--------|-------------|
| `auto` | Automatic detection (recommended) |
| `cpu` | CPU inference (universal, slower) |
| `cuda` | NVIDIA GPU (fastest for NVIDIA) |
| `mps` | Apple Silicon GPU (fast on Mac) |
| `metal` | Apple Metal API |

### Methodology Options

| Methodology | Description |
|-------------|-------------|
| `none` | AI-determined folder structure |
| `para` | Projects, Areas, Resources, Archives |
| `jd` | Johnny Decimal numbering system |

## Managing Profiles

```bash
# Create/edit a profile
file-organizer config edit --profile work --methodology para --temperature 0.3

# Use a profile
file-organizer config show --profile work

# List all profiles
file-organizer config list
```

## Rules Configuration

Rules are stored in `~/.config/file-organizer/rules/` as YAML files.

```yaml
# ~/.config/file-organizer/rules/default.yaml
name: default
description: Default organisation rules
version: "1.0"
rules:
  - name: pdf-to-docs
    description: Move PDFs to Documents
    conditions:
      - type: extension
        value: ".pdf"
    action:
      type: move
      destination: "~/Documents/PDFs"
    enabled: true
    priority: 10

  - name: archive-old
    description: Archive files older than 90 days
    conditions:
      - type: extension
        value: ".zip,.7z,.tar.gz"
      - type: size_greater
        value: "10000000"
    action:
      type: archive
      destination: "~/Archive/{ext}"
    enabled: true
    priority: 5
```

### Rule Condition Types

| Type | Value Format | Example |
|------|-------------|---------|
| `extension` | Comma-separated extensions | `.pdf,.docx` |
| `name_pattern` | Glob pattern | `report_*` |
| `size_greater` | Bytes | `1000000` (1 MB) |
| `size_less` | Bytes | `100` |
| `content_contains` | Search string | `confidential` |
| `modified_before` | ISO date | `2025-01-01` |
| `modified_after` | ISO date | `2025-06-01` |
| `path_matches` | Regex | `.*/(Downloads|Desktop)/.*` |

### Rule Action Types

| Type | Description |
|------|-------------|
| `move` | Move file to destination |
| `copy` | Copy file to destination |
| `rename` | Rename the file |
| `tag` | Add metadata tags |
| `categorize` | Assign category |
| `archive` | Move to archive |
| `delete` | Delete the file |

### Destination Templates

Destinations support template variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `{name}` | Full filename | `report.pdf` |
| `{stem}` | Filename without extension | `report` |
| `{ext}` | Extension without dot | `pdf` |

Example: `~/Documents/{ext}/{stem}` produces `~/Documents/pdf/report`.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `FILE_ORGANIZER_CONFIG` | Override config directory path |
| `OLLAMA_HOST` | Ollama server address (default: localhost:11434) |
