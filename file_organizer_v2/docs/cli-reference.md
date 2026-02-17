# CLI Reference

Complete reference for File Organizer command-line interface.

## Basic Commands

### Organize Files

```bash
file-organizer organize <input> <output> [OPTIONS]
```

**Example**:

```bash
file-organizer organize ./Downloads ./Organized
```

**Options**:

- `--methodology {para,johnny-decimal}` - Organization system
- `--dry-run` - Preview without moving files
- `--preserve` - Keep originals
- `--verbose` - Detailed output

### Search Files

```bash
file-organizer search <query> [OPTIONS]
```

**Example**:

```bash
file-organizer search "*.pdf"
```

### Deduplicate

```bash
file-organizer dedupe scan <path> [OPTIONS]
```

**Example**:

```bash
file-organizer dedupe scan ~/Documents
```

### Start Web Server

```bash
file-organizer serve [OPTIONS]
```

**Options**:

- `--host` - Server host (default: localhost)
- `--port` - Server port (default: 8000)

### Interactive Mode

```bash
file-organizer copilot chat
```

## Advanced Options

- `--config` - Custom configuration file
- `--debug` - Debug output
- `--version` - Show version

## Short Alias

Use `fo` instead of `file-organizer`:

```bash
fo organize ./Downloads ./Organized
```

See [Getting Started](getting-started.md) for tutorials.
