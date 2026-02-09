# CLI Reference

## Global Options

```
file-organizer [OPTIONS] COMMAND
fo [OPTIONS] COMMAND
```

| Option | Description |
| --- | --- |
| `--verbose`, `-v` | Enable verbose output |
| `--dry-run` | Preview changes without executing |
| `--json` | Output results as JSON when supported |
| `--yes`, `-y` | Auto-confirm all prompts |
| `--no-interactive` | Disable interactive prompts |
| `--help` | Show help |

## Command Summary

| Command | Description |
| --- | --- |
| `organize` | Organize files using AI models |
| `preview` | Dry-run preview of organization |
| `tui` | Launch the Textual terminal UI |
| `version` | Show version |
| `config` | Manage configuration profiles |
| `model` | Manage AI models |
| `copilot` | Chat-based copilot |
| `rules` | Manage organization rules |
| `suggest` | Generate/apply suggestions |
| `dedupe` | Duplicate detection and resolution |
| `undo` / `redo` / `history` | Operation history |
| `analytics` | Storage analytics dashboard |
| `daemon` | Watcher + pipeline daemon |
| `update` | Auto-update commands |
| `profile` | Advanced profile management |

## organize

```bash
file-organizer organize INPUT_DIR OUTPUT_DIR [OPTIONS]
```

| Option | Description |
| --- | --- |
| `--dry-run` | Preview without moving files |
| `--verbose`, `-v` | Verbose output |

## preview

```bash
file-organizer preview INPUT_DIR
```

## tui

```bash
file-organizer tui
```

## version

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
  --set NAME                   Rule set to evaluate
  --recursive/--no-recursive   Recurse into subdirectories
  --max-files INT              Maximum files to scan
```

### rules export

```bash
file-organizer rules export [--set NAME] [--output FILE]
```

### rules import

```bash
file-organizer rules import FILE [--set NAME]
```

## Suggest Sub-commands

### suggest files

```bash
file-organizer suggest files DIRECTORY [OPTIONS]
  --min-confidence FLOAT   Minimum confidence threshold (0-100)
  --max-results INT        Maximum suggestions
  --json                   Output as JSON
  --dry-run                Alias for preview mode
```

### suggest apply

```bash
file-organizer suggest apply DIRECTORY [OPTIONS]
  --min-confidence FLOAT   Minimum confidence for auto-apply
  --dry-run                Preview without changes
  --json                   Output as JSON
```

### suggest patterns

```bash
file-organizer suggest patterns DIRECTORY [--json]
```

## Dedupe Sub-commands

### dedupe scan

```bash
file-organizer dedupe scan DIRECTORY [OPTIONS]
  --algorithm ALGO       Hash algorithm (md5, sha256)
  --recursive            Scan subdirectories
  --min-size BYTES       Minimum file size in bytes
  --max-size BYTES       Maximum file size in bytes
  --include PATTERNS     Comma-separated include patterns
  --exclude PATTERNS     Comma-separated exclude patterns
  --json                 Output as JSON
```

### dedupe resolve

```bash
file-organizer dedupe resolve DIRECTORY [OPTIONS]
  --strategy STRATEGY    manual, oldest, newest, largest, smallest
  --algorithm ALGO       Hash algorithm
  --recursive            Scan subdirectories
  --dry-run              Preview without deleting
  --min-size BYTES       Minimum file size in bytes
  --max-size BYTES       Maximum file size in bytes
  --include PATTERNS     Comma-separated include patterns
  --exclude PATTERNS     Comma-separated exclude patterns
```

### dedupe report

```bash
file-organizer dedupe report DIRECTORY [OPTIONS]
  --algorithm ALGO       Hash algorithm
  --recursive            Scan subdirectories
  --json                 Output as JSON
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

## analytics

```bash
file-organizer analytics [DIRECTORY] [--verbose]
```

## Daemon Sub-commands

### daemon start

```bash
file-organizer daemon start [OPTIONS]
  --watch-dir PATH      Directory to watch
  --output-dir PATH     Destination directory
  --foreground          Run in foreground
  --poll-interval FLOAT Seconds between polls
  --dry-run             Preview without moving files
```

### daemon stop

```bash
file-organizer daemon stop
```

### daemon status

```bash
file-organizer daemon status
```

### daemon watch

```bash
file-organizer daemon watch DIRECTORY [--poll-interval FLOAT]
```

### daemon process

```bash
file-organizer daemon process INPUT_DIR OUTPUT_DIR [--dry-run]
```

## Update Sub-commands

### update check

```bash
file-organizer update check [--repo OWNER/REPO] [--pre]
```

### update install

```bash
file-organizer update install [--dry-run] [--repo OWNER/REPO] [--pre]
```

### update rollback

```bash
file-organizer update rollback
```

## Profile Sub-commands

```bash
file-organizer profile COMMAND
```

| Command | Description |
| --- | --- |
| `list` | List profiles |
| `create` | Create a profile |
| `activate` | Activate a profile |
| `delete` | Delete a profile |
| `current` | Show current profile |
| `export` | Export a profile to JSON |
| `import` | Import a profile from JSON |
| `merge` | Merge multiple profiles |
| `template list` | List templates |
| `template preview` | Preview a template |
| `template apply` | Apply template to profile |
| `migrate` | Migrate profile to new version |
| `validate` | Validate profile configuration |

## Auto-tagging (Legacy)

Auto-tagging commands exist as a legacy argparse CLI. Run it directly:

```bash
python -m file_organizer.cli.autotag --help
```
