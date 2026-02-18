# File Organizer v2 CLI Reference

## Global Options
- `--version`: Show version and exit.
- `--help`: Show help message.
- `-v, --verbose`: Enable verbose logging.

## Commands

### `organize`
Organize files in a directory using AI or rules.

**Usage:**
```bash
file-organizer organize [OPTIONS] INPUT_DIR OUTPUT_DIR
```

**Options:**
- `--dry-run`: Simulate the organization without moving files.
- `--recursive / --no-recursive`: Process subdirectories (default: True).
- `--methodology [none|para|jd]`: Override default methodology.
- `--text-model TEXT`: Override AI text model.
- `--vision-model TEXT`: Override AI vision model.

### `config`
Manage configuration settings.

**Subcommands:**
- `show`: Display current configuration.
- `edit`: Modify settings via CLI flags.
- `list`: List available profiles.

**Examples:**
```bash
file-organizer config show --profile work
file-organizer config edit --temperature 0.8
```

### `rules`
Manage organization rules.

**Subcommands:**
- `add`: Add a new rule.
- `remove`: Remove a rule.
- `list`: List all active rules.
- `preview`: Preview rule application.

**Examples:**
```bash
file-organizer rules add my-rule --ext ".pdf" --action move --dest "Docs"
```

### `dedupe`
Find and manage duplicate files.

**Subcommands:**
- `scan`: Scan for duplicates.
- `report`: Generate a duplication report.
- `resolve`: Interactively or automatically resolve duplicates.

**Examples:**
```bash
file-organizer dedupe scan ./Images
```

### `daemon`
Run the file watcher daemon.

**Subcommands:**
- `start`: Start the background daemon.
- `stop`: Stop the daemon.
- `status`: Check daemon status.
- `watch`: Run in foreground mode (for debugging).

**Examples:**
```bash
file-organizer daemon start --watch-dir ./Inbox --output-dir ./Organized
```

### `tui`
Launch the Terminal User Interface.

**Usage:**
```bash
file-organizer tui
```

### `copilot`
Interact with the AI assistant via CLI.

**Subcommands:**
- `chat`: Start a chat session or send a single command.

**Examples:**
```bash
file-organizer copilot chat "Help me organize my photos"
```

### `update`
Manage application updates.

**Subcommands:**
- `check`: Check for new versions.
- `install`: Install the latest version.
- `rollback`: Revert to the previous version.
