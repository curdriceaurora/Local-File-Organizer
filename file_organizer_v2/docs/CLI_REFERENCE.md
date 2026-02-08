# CLI Reference

## Global Options

```
file-organizer [OPTIONS] COMMAND
fo [OPTIONS] COMMAND              # Short alias
```

| Option | Description |
|--------|-------------|
| `--verbose, -v` | Enable verbose output |
| `--dry-run` | Preview changes without executing |
| `--json` | Output results as JSON |
| `--yes, -y` | Auto-confirm all prompts |
| `--no-interactive` | Disable interactive prompts |
| `--help` | Show help |

## Commands

### organize

Organize files in a directory using AI models.

```bash
file-organizer organize INPUT_DIR OUTPUT_DIR [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview without moving files |
| `--verbose, -v` | Verbose output |

### preview

Preview how files would be organized (dry-run shortcut).

```bash
file-organizer preview INPUT_DIR
```

### tui

Launch the interactive terminal UI.

```bash
file-organizer tui
```

### version

Show the application version.

```bash
file-organizer version
```

## Config Sub-commands

### config show

```bash
file-organizer config show [--profile NAME]
```

### config list

```bash
file-organizer config list
```

### config edit

```bash
file-organizer config edit [OPTIONS]
  --profile NAME          Profile name (default: "default")
  --text-model NAME       Set text model
  --vision-model NAME     Set vision model
  --temperature FLOAT     Set temperature (0.0-1.0)
  --device DEVICE         Set device (auto, cpu, cuda, mps, metal)
  --methodology METHOD    Set methodology (none, para, jd)
```

## Model Sub-commands

### model list

```bash
file-organizer model list [--type TYPE]
```

### model pull

```bash
file-organizer model pull MODEL_NAME
```

### model cache

```bash
file-organizer model cache
```

## Copilot Sub-commands

### copilot chat

```bash
file-organizer copilot chat [MESSAGE] [--dir PATH]
```

Without `MESSAGE`, launches interactive REPL. With `MESSAGE`, responds once and exits.

### copilot status

```bash
file-organizer copilot status
```

## Rules Sub-commands

### rules list

```bash
file-organizer rules list [--set NAME]
```

### rules sets

```bash
file-organizer rules sets
```

### rules add

```bash
file-organizer rules add NAME [OPTIONS]
  --ext EXT             File extension filter (e.g. ".pdf,.docx")
  --pattern PATTERN     Filename glob pattern
  --action ACTION       Action type (move, rename, tag, categorize, archive, copy, delete)
  --dest PATH           Destination path or pattern
  --priority INT        Rule priority (higher = first)
  --set NAME            Target rule set (default: "default")
```

### rules remove

```bash
file-organizer rules remove NAME [--set NAME]
```

### rules toggle

```bash
file-organizer rules toggle NAME [--set NAME]
```

### rules preview

```bash
file-organizer rules preview DIRECTORY [OPTIONS]
  --set NAME                Rule set to evaluate
  --recursive/--no-recursive  Recurse into subdirectories
  --max-files INT           Maximum files to scan
```

### rules export

```bash
file-organizer rules export [--set NAME] [--output FILE]
```

### rules import

```bash
file-organizer rules import FILE [--set NAME]
```

## Update Sub-commands

### update check

```bash
file-organizer update check [--repo OWNER/REPO] [--pre]
```

### update install

```bash
file-organizer update install [--dry-run] [--repo OWNER/REPO]
```

### update rollback

```bash
file-organizer update rollback
```

## Undo/Redo Commands

### undo

```bash
file-organizer undo [OPTIONS]
  --operation-id INT    Specific operation ID
  --transaction-id STR  Transaction ID
  --dry-run             Preview without executing
  --verbose, -v         Verbose output
```

### redo

```bash
file-organizer redo [OPTIONS]
  --operation-id INT    Specific operation ID
  --dry-run             Preview
  --verbose, -v         Verbose output
```

### history

```bash
file-organizer history [OPTIONS]
  --limit INT           Max operations to show (default: 10)
  --type TYPE           Filter by type
  --status STATUS       Filter by status
  --stats               Show statistics
  --verbose, -v         Verbose output
```

### analytics

```bash
file-organizer analytics [DIRECTORY] [--verbose]
```

## Daemon Sub-commands

### daemon start/stop/status/logs

```bash
file-organizer daemon start
file-organizer daemon stop
file-organizer daemon status
file-organizer daemon logs
```
