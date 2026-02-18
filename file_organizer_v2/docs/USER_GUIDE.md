# File Organizer v2 User Guide

## Introduction
File Organizer v2 is a privacy-first, AI-powered tool for managing your local files. It runs entirely on your device using local LLMs (Ollama) to categorize, rename, and organize your documents, images, and media.

## Key Features
- **AI-Powered Organization**: Uses Qwen 2.5 (3B) and Qwen 2.5-VL (7B) to understand file content.
- **Privacy First**: No data leaves your machine.
- **Terminal UI (TUI)**: A rich terminal interface for managing files.
- **Copilot**: Natural language assistant for file operations.
- **Methodologies**: Built-in support for PARA and Johnny Decimal systems.

## Installation

### Prerequisites
- Python 3.9+
- [Ollama](https://ollama.ai/) installed and running.

### Setup
```bash
pip install file-organizer
# Or from source:
pip install -e .
```

### Pulling Models
You need to pull the specific models used by File Organizer:
```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

## Basic Usage

### Organizing a Folder
To organize a folder using the default AI settings:
```bash
file-organizer organize ./Downloads ./Organized --dry-run
```
Remove `--dry-run` to actually move files.

### Using the TUI
Launch the Terminal User Interface:
```bash
file-organizer tui
```
In the TUI, you can:
- Browse files (Key `1`)
- Chat with Copilot (Key `8`)
- View storage analytics (Key `3`)
- Manage settings (Key `7`)

### The Daemon
To watch a directory and organize files automatically:
```bash
file-organizer daemon start --watch-dir ./Inbox --output-dir ./Documents
```

## Advanced Features

### Rules
Create custom rules to override AI decisions:
```bash
file-organizer rules add invoice-rule --name-pattern "*invoice*" --action move --dest "Documents/Financial"
```

### Deduplication
Find duplicate files:
```bash
file-organizer dedupe scan ./Documents
```

## Privacy & Security
All processing is local. Network requests are only made for:
- Checking for application updates (can be disabled)
- Communicating with your local Ollama instance (localhost)

## Troubleshooting
If you encounter issues, check the logs or run with `-v` for verbose output.
See [troubleshooting.md](troubleshooting.md) for more details.
