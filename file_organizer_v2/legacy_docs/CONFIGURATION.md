# Configuration Guide

## Overview

File Organizer stores YAML configuration profiles in `config/file-organizer/config.yaml` relative to your config home directory. You can override the base directory with `FILE_ORGANIZER_CONFIG`.

Multiple named profiles are supported under the `profiles` key. Each profile can override model settings, update preferences, and module-specific configuration blocks.

## Configuration File Example

```yaml
profiles:
  default:
    version: "1.0"
    default_methodology: none

    models:
      text_model: "qwen2.5:3b-instruct-q4_K_M"
      vision_model: "qwen2.5vl:7b-q4_K_M"
      temperature: 0.5
      max_tokens: 3000
      device: auto
      framework: ollama

    updates:
      check_on_startup: true
      interval_hours: 24
      include_prereleases: false
      repo: "curdriceaurora/Local-File-Organizer"

    watcher:
      watch_directories:
        - "inbox"
      recursive: true
      exclude_patterns:
        - "*.tmp"
        - ".git/*"
      debounce_seconds: 2.0
      batch_size: 10
      file_types: [".pdf", ".md"]

    daemon:
      watch_directories:
        - "inbox"
      output_directory: "organized_files"
      pid_file: "state/daemon.pid"
      log_file: "logs/daemon.log"
      dry_run: true
      poll_interval: 1.0
      max_concurrent: 4

    parallel:
      max_workers: 4
      executor_type: thread
      chunk_size: 10
      timeout_per_file: 60
      retry_count: 2

    pipeline:
      output_directory: "organized_files"
      dry_run: true
      auto_organize: false
      supported_extensions: [".pdf", ".jpg", ".png"]
      max_concurrent: 4

    events:
      redis_url: "redis://localhost:6379/0"
      stream_prefix: "fileorg"
      consumer_group: "file-organizer"
      max_retries: 3
      retry_delay: 1.0
      block_ms: 5000
      max_stream_length: 10000
      batch_size: 10

    deploy:
      environment: dev
      redis_url: "redis://localhost:6379/0"
      data_directory: "data"
      log_level: "DEBUG"
      max_workers: 2
      host: "0.0.0.0"
      port: 8000

    para:
      auto_categorize: true
      enable_ai_heuristic: false
      project_dir: "Projects"
      area_dir: "Areas"
      resource_dir: "Resources"
      archive_dir: "Archive"

    johnny_decimal:
      scheme:
        name: "default"
        areas:
          - area_range_start: 10
            area_range_end: 19
            name: "Projects"
        categories:
          - area: 10
            category: 11
            name: "Active"
      migration:
        preserve_original_names: true
        create_backups: true
      compatibility:
        para_integration:
          enabled: false
  
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
| --- | --- | --- |
| `text_model` | `qwen2.5:3b-instruct-q4_K_M` | Ollama model for text processing |
| `vision_model` | `qwen2.5vl:7b-q4_K_M` | Ollama model for image/video |
| `temperature` | `0.5` | Generation randomness |
| `max_tokens` | `3000` | Maximum tokens for generation |
| `device` | `auto` | Inference device |
| `framework` | `ollama` | Inference framework |

### Device Options

| Device | Description |
| --- | --- |
| `auto` | Automatic detection (recommended) |
| `cpu` | CPU inference |
| `cuda` | NVIDIA GPU |
| `mps` | Apple Silicon GPU |
| `metal` | Apple Metal API |

### Updates

| Setting | Default | Description |
| --- | --- | --- |
| `check_on_startup` | `true` | Check for updates on app launch (TUI) |
| `interval_hours` | `24` | Minimum hours between update checks |
| `include_prereleases` | `false` | Allow prerelease versions |
| `repo` | `curdriceaurora/Local-File-Organizer` | GitHub repo for updates |

### Methodology Options

| Value | Description |
| --- | --- |
| `none` | AI-determined structure |
| `para` | Projects, Areas, Resources, Archives |
| `jd` | Johnny Decimal numbering system |

### Watcher

| Setting | Default | Description |
| --- | --- | --- |
| `watch_directories` | `[]` | Directories to monitor |
| `recursive` | `true` | Watch subdirectories |
| `exclude_patterns` | built-in list | Glob patterns to ignore |
| `debounce_seconds` | `2.0` | Minimum delay before processing |
| `batch_size` | `10` | Max events per batch |
| `file_types` | `null` | Extensions to include |

### Daemon

| Setting | Default | Description |
| --- | --- | --- |
| `watch_directories` | `[]` | Directories to monitor |
| `output_directory` | `organized_files` | Destination directory |
| `pid_file` | `null` | PID file path |
| `log_file` | `null` | Log file path |
| `dry_run` | `true` | Simulate operations |
| `poll_interval` | `1.0` | Poll interval in seconds |
| `max_concurrent` | `4` | Max concurrent files |

### Parallel Processing

| Setting | Default | Description |
| --- | --- | --- |
| `max_workers` | `null` | Worker count (null = CPU count) |
| `executor_type` | `thread` | `thread` or `process` |
| `chunk_size` | `10` | Files per scheduling chunk |
| `timeout_per_file` | `60` | Max seconds per file |
| `retry_count` | `2` | Retry attempts per file |

### Pipeline

| Setting | Default | Description |
| --- | --- | --- |
| `output_directory` | `organized_files` | Output directory |
| `dry_run` | `true` | Simulate all file ops |
| `auto_organize` | `false` | Move files when true |
| `supported_extensions` | default list | Override supported extensions |
| `max_concurrent` | `4` | Max concurrent files |

### Events

| Setting | Default | Description |
| --- | --- | --- |
| `redis_url` | `redis://localhost:6379/0` | Redis connection URL |
| `stream_prefix` | `fileorg` | Stream name prefix |
| `consumer_group` | `file-organizer` | Consumer group name |
| `max_retries` | `3` | Retry attempts |
| `retry_delay` | `1.0` | Delay between retries |
| `block_ms` | `5000` | Read block time (ms) |
| `max_stream_length` | `10000` | Stream trim length |
| `batch_size` | `10` | Messages per read |

### Deployment

| Setting | Default | Description |
| --- | --- | --- |
| `environment` | `dev` | Environment (dev, staging, prod) |
| `redis_url` | `redis://localhost:6379/0` | Redis URL |
| `data_directory` | `data` | Persistent data directory |
| `log_level` | `DEBUG` | Log level |
| `max_workers` | `2` | Worker processes |
| `host` | `0.0.0.0` | Web bind host |
| `port` | `8000` | Web bind port |

Note: deployment defaults may be tuned for container environments. Use `FO_DATA_DIR` to align the data directory with your runtime.

### PARA

| Setting | Default | Description |
| --- | --- | --- |
| `auto_categorize` | `true` | Auto-categorize high confidence files |
| `enable_ai_heuristic` | `false` | Use AI heuristic |
| `project_dir` | `Projects` | Project folder name |
| `area_dir` | `Areas` | Area folder name |
| `resource_dir` | `Resources` | Resource folder name |
| `archive_dir` | `Archive` | Archive folder name |

### Johnny Decimal

Johnny Decimal configuration includes a numbering scheme, migration options, and compatibility settings. For full examples, see `docs/phase-3/johnny-decimal.md`.

Key settings:

- `scheme` with `areas` and `categories`
- `migration` flags (preserve names, backups, depth)
- `compatibility` for PARA integration

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

Rules are stored in `config/file-organizer/rules/` relative to your config home directory.

```yaml
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
      destination: "Documents/PDFs"
    enabled: true
    priority: 10
```

### Rule Condition Types

| Type | Value Format | Example |
| --- | --- | --- |
| `extension` | Comma-separated extensions | `.pdf,.docx` |
| `name_pattern` | Glob pattern | `report_*` |
| `size_greater` | Bytes | `1000000` |
| `size_less` | Bytes | `100` |
| `content_contains` | Search string | `confidential` |
| `modified_before` | ISO date | `2025-01-01` |
| `modified_after` | ISO date | `2025-06-01` |
| `path_matches` | Regex | `.*/(Downloads|Desktop)/.*` |

### Rule Action Types

| Type | Description |
| --- | --- |
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
| --- | --- | --- |
| `{name}` | Full filename | `report.pdf` |
| `{stem}` | Filename without extension | `report` |
| `{ext}` | Extension without dot | `pdf` |

Example: `Documents/{ext}/{stem}` produces `Documents/pdf/report`.

## Environment Variables

| Variable | Description |
| --- | --- |
| `FILE_ORGANIZER_CONFIG` | Override config directory path |
| `OLLAMA_HOST` | Ollama server address |
| `FO_DISABLE_UPDATE_CHECK` | Disable automatic update checks (set to `1`) |
| `FO_ENVIRONMENT` | Deployment environment |
| `FO_DATA_DIR` | Deployment data directory |
