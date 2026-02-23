# File Organizer CLI Reference

All commands are available via `file-organizer` or the short alias `fo`.

## Global Options

These options apply to every command and may be passed before or after the command name:

| Flag | Short | Description |
|------|-------|-------------|
| `--verbose` | `-v` | Enable verbose output |
| `--dry-run` | | Preview changes without executing |
| `--json` | | Output results as JSON |
| `--yes` | `-y` | Auto-confirm all prompts |
| `--no-interactive` | | Disable interactive prompts |
| `--help` | | Show help and exit |

---

## Top-Level Commands

### `version`

Show the application version.

```bash
file-organizer version
```

---

### `organize`

Organize files in a directory using AI models.

**Usage:**
```bash
file-organizer organize INPUT_DIR OUTPUT_DIR [OPTIONS]
```

**Arguments:**
- `INPUT_DIR` — Directory containing files to organize
- `OUTPUT_DIR` — Destination directory for organized files

**Options:**
- `--dry-run` — Preview without moving files
- `--verbose, -v` — Verbose output

**Examples:**
```bash
# Organize ~/Downloads into ~/Organized
file-organizer organize ~/Downloads ~/Organized

# Preview what would happen (no files moved)
file-organizer organize ~/Downloads ~/Organized --dry-run

# Verbose output
file-organizer organize ~/Downloads ~/Organized --verbose
```

> **Note:** To set a default methodology (PARA, Johnny Decimal, etc.) or override AI models, use `file-organizer config edit` before running organize.

---

### `preview`

Preview how files would be organized without moving them (dry-run shortcut).

**Usage:**
```bash
file-organizer preview INPUT_DIR
```

**Examples:**
```bash
file-organizer preview ~/Downloads
fo preview ~/Downloads
```

---

### `serve`

Start the File Organizer web server and API.

**Usage:**
```bash
file-organizer serve [OPTIONS]
```

**Options:**
- `--host TEXT` — Bind address (default: `0.0.0.0`)
- `--port INTEGER` — Port number (default: `8000`)
- `--reload` — Auto-reload on code changes (development mode)
- `--workers INTEGER` — Number of worker processes (default: `1`)

**Examples:**
```bash
# Start with defaults (port 8000, all interfaces)
file-organizer serve

# Development mode with auto-reload
file-organizer serve --reload

# Custom host and port
file-organizer serve --host 127.0.0.1 --port 9000

# Production with multiple workers
file-organizer serve --workers 4
```

> **Access:** Once running, open `http://localhost:8000/ui/` in your browser.

---

### `search`

Search for files by name pattern with optional type filtering.

**Usage:**
```bash
file-organizer search QUERY [DIRECTORY] [OPTIONS]
```

**Arguments:**
- `QUERY` — Search query (glob pattern like `*.pdf` or keyword like `report`)
- `DIRECTORY` — Directory to search in (default: current directory)

**Options:**
- `--type, -t TEXT` — Filter by type: `text`, `image`, `video`, `audio`, `archive`
- `--limit, -n INTEGER` — Max results to show (default: 50)
- `--recursive / --no-recursive` — Search subdirectories (default: recursive)
- `--json` — Output as JSON array

**Examples:**
```bash
# Search by glob pattern
file-organizer search "*.pdf" ~/Documents

# Keyword search (case-insensitive)
file-organizer search "report" ~/Documents

# Filter by type
file-organizer search "*" ~/Pictures --type image

# Non-recursive, limited results
file-organizer search "*.log" /var/log --no-recursive --limit 10

# JSON output for scripting
file-organizer search "*.py" ./src --json
```

---

### `analyze`

Analyze a file using AI and show its description, category, and confidence score.

**Usage:**
```bash
file-organizer analyze FILE [OPTIONS]
```

**Arguments:**
- `FILE` — Path to the file to analyze

**Options:**
- `--verbose, -v` — Show additional details (model name, processing time, content length)
- `--json` — Output as JSON

**Examples:**
```bash
# Basic analysis
file-organizer analyze ~/Documents/report.pdf

# Verbose output
file-organizer analyze ~/Documents/report.pdf --verbose

# JSON output for scripting
file-organizer analyze ~/Documents/report.pdf --json
```

> **Note:** Requires Ollama to be installed and running with a text model available.

---

### `tui`

Launch the interactive Terminal User Interface.

```bash
file-organizer tui
```

---

### `undo`

Undo file operations.

**Usage:**
```bash
file-organizer undo [OPTIONS]
```

**Options:**
- `--operation-id INTEGER` — Specific operation ID to undo
- `--transaction-id TEXT` — Transaction ID to undo (undoes all operations in a transaction)
- `--dry-run` — Preview without executing
- `--verbose, -v` — Verbose output

**Examples:**
```bash
# Undo the last operation
file-organizer undo

# Undo a specific operation
file-organizer undo --operation-id 42

# Undo all operations in a transaction
file-organizer undo --transaction-id abc123
```

---

### `redo`

Redo previously undone file operations.

**Usage:**
```bash
file-organizer redo [OPTIONS]
```

**Options:**
- `--operation-id INTEGER` — Specific operation ID to redo
- `--dry-run` — Preview without executing
- `--verbose, -v` — Verbose output

---

### `history`

View operation history.

**Usage:**
```bash
file-organizer history [OPTIONS]
```

**Options:**
- `--limit INTEGER` — Maximum number of operations to show (default: 10)
- `--type TEXT` — Filter by operation type
- `--status TEXT` — Filter by status
- `--stats` — Show statistics summary
- `--verbose, -v` — Verbose output

**Examples:**
```bash
file-organizer history
file-organizer history --limit 50
file-organizer history --stats
```

---

### `analytics`

Display storage analytics dashboard.

**Usage:**
```bash
file-organizer analytics [DIRECTORY] [OPTIONS]
```

**Arguments:**
- `DIRECTORY` — Directory to analyze (optional; defaults to configured workspace)

**Options:**
- `--verbose, -v` — Verbose output

**Examples:**
```bash
file-organizer analytics
file-organizer analytics ~/Documents
```

---

## Sub-Commands

### `config` — Configuration Management

Manage configuration profiles.

#### `config show`

Display the current configuration profile.

```bash
file-organizer config show [--profile PROFILE]
```

Options:
- `--profile TEXT` — Profile name (default: `default`)

#### `config list`

List all available configuration profiles.

```bash
file-organizer config list
```

#### `config edit`

Edit a configuration profile.

```bash
file-organizer config edit [OPTIONS]
```

Options:
- `--profile TEXT` — Profile name to edit (default: `default`)
- `--text-model TEXT` — Set the text model name
- `--vision-model TEXT` — Set the vision model name
- `--temperature FLOAT` — Set temperature (0.0–1.0)
- `--device TEXT` — Set device (`auto`, `cpu`, `cuda`, `mps`, `metal`)
- `--methodology TEXT` — Set default methodology (`none`, `para`, `jd`)

**Examples:**
```bash
file-organizer config show
file-organizer config show --profile work
file-organizer config edit --text-model qwen2.5:3b-instruct-q4_K_M
file-organizer config edit --device cuda --methodology para
file-organizer config edit --profile work --temperature 0.7
```

---

### `model` — AI Model Management

Manage AI models via Ollama.

#### `model list`

List available models with their install status.

```bash
file-organizer model list [--type TYPE]
```

Options:
- `--type TEXT` — Filter by type: `text`, `vision`, or `audio`

#### `model pull`

Download a model via Ollama.

```bash
file-organizer model pull MODEL_NAME
```

#### `model cache`

Show model cache statistics.

```bash
file-organizer model cache
```

**Examples:**
```bash
file-organizer model list
file-organizer model list --type vision
file-organizer model pull qwen2.5:3b-instruct-q4_K_M
file-organizer model cache
```

---

### `copilot` — AI Assistant

Interactive AI copilot for file organisation.

#### `copilot chat`

Chat with the file-organisation copilot.

```bash
file-organizer copilot chat [MESSAGE] [--dir DIRECTORY]
```

Arguments:
- `MESSAGE` — Single message (optional; omit to start interactive REPL)

Options:
- `--dir, -d TEXT` — Working directory for file operations

**Examples:**
```bash
# Interactive REPL
file-organizer copilot chat

# Single question
file-organizer copilot chat "Help me organize my photos"

# Scoped to a specific directory
file-organizer copilot chat --dir ~/Documents "What duplicates do I have?"
```

---

### `daemon` — Background File Watcher

Run the file watcher as a background daemon.

#### `daemon start`

```bash
file-organizer daemon start [OPTIONS]
```

Common options: `--watch-dir PATH`, `--output-dir PATH`

#### `daemon stop`

```bash
file-organizer daemon stop
```

#### `daemon status`

```bash
file-organizer daemon status
```

#### `daemon watch`

Run in foreground mode (useful for debugging).

```bash
file-organizer daemon watch
```

**Examples:**
```bash
file-organizer daemon start --watch-dir ~/Inbox --output-dir ~/Organized
file-organizer daemon status
file-organizer daemon stop
```

---

### `dedupe` — Duplicate File Management

Find and manage duplicate files.

#### `dedupe scan`

Scan a directory for duplicate files.

```bash
file-organizer dedupe scan DIRECTORY [OPTIONS]
```

#### `dedupe report`

Generate a duplication report.

```bash
file-organizer dedupe report [OPTIONS]
```

#### `dedupe resolve`

Interactively or automatically resolve duplicates.

```bash
file-organizer dedupe resolve [OPTIONS]
```

**Examples:**
```bash
file-organizer dedupe scan ~/Images
file-organizer dedupe report
file-organizer dedupe resolve
```

---

### `rules` — Organisation Rules

Manage copilot organisation rules and rule sets.

#### `rules list`

List all rules in a rule set.

```bash
file-organizer rules list [--set RULE_SET]
```

#### `rules sets`

List available rule sets.

```bash
file-organizer rules sets
```

#### `rules add`

Add a new rule to a rule set.

```bash
file-organizer rules add RULE_NAME [OPTIONS]
```

Options:
- `--ext TEXT` — File extension filter (e.g. `.pdf,.docx`)
- `--pattern TEXT` — Filename glob pattern
- `--action, -a TEXT` — Action type: `move`, `rename`, `tag`, `categorize`, `archive`, `copy`, `delete` (default: `move`)
- `--dest, -d TEXT` — Destination path or pattern
- `--priority, -p INTEGER` — Rule priority (higher = runs first; default: 0)
- `--set, -s TEXT` — Target rule set (default: `default`)

#### `rules remove`

Remove a rule from a rule set.

```bash
file-organizer rules remove RULE_NAME [--set RULE_SET]
```

#### `rules toggle`

Enable or disable a rule.

```bash
file-organizer rules toggle RULE_NAME [--set RULE_SET]
```

#### `rules preview`

Preview what rules would do against a directory (dry-run).

```bash
file-organizer rules preview DIRECTORY [OPTIONS]
```

Options:
- `--set, -s TEXT` — Rule set to evaluate (default: `default`)
- `--recursive/--no-recursive` — Recurse into subdirectories (default: true)
- `--max-files INTEGER` — Maximum files to scan (default: 500)

#### `rules export`

Export a rule set to YAML.

```bash
file-organizer rules export [--set RULE_SET] [--output FILE]
```

#### `rules import`

Import a rule set from a YAML file.

```bash
file-organizer rules import FILE [--set RULE_SET]
```

**Examples:**
```bash
# List rules in the default rule set
file-organizer rules list

# Add a rule to move PDFs to a Docs folder
file-organizer rules add move-pdfs --ext .pdf --action move --dest Docs

# Add a rule with glob pattern, high priority
file-organizer rules add archive-old --pattern "*.2022*" --action archive --priority 10

# Preview rules against a directory
file-organizer rules preview ~/Downloads

# Export/import rule sets
file-organizer rules export --set work --output work-rules.yaml
file-organizer rules import work-rules.yaml
```

---

### `suggest` — Smart File Suggestions

Generate AI-powered file organisation suggestions using pattern analysis.

#### `suggest files`

Generate organisation suggestions for files in a directory.

```bash
file-organizer suggest files DIRECTORY [OPTIONS]
```

Options:
- `--min-confidence FLOAT` — Minimum confidence threshold 0–100 (default: 40.0)
- `--max-results INTEGER` — Maximum suggestions (default: 50)
- `--json` — Output as JSON
- `--dry-run` — Preview mode

#### `suggest apply`

Apply accepted suggestions.

```bash
file-organizer suggest apply [OPTIONS]
```

#### `suggest patterns`

Analyze naming patterns in a directory.

```bash
file-organizer suggest patterns DIRECTORY [OPTIONS]
```

**Examples:**
```bash
file-organizer suggest files ~/Downloads
file-organizer suggest files ~/Documents --min-confidence 60
file-organizer suggest patterns ~/Projects
```

---

### `marketplace` — Plugin Marketplace

Browse and manage plugins from the marketplace.

#### `marketplace list`

List available plugins.

```bash
file-organizer marketplace list [OPTIONS]
```

Options:
- `--page, -p INTEGER` — Page number (default: 1)
- `--per-page INTEGER` — Results per page (default: 20)
- `--category, -c TEXT` — Filter by category
- `--tag, -t TEXT` — Filter by tag (repeatable)

#### `marketplace search`

Search the marketplace.

```bash
file-organizer marketplace search QUERY [OPTIONS]
```

#### `marketplace info`

Show details for a specific plugin.

```bash
file-organizer marketplace info PLUGIN_NAME
```

#### `marketplace install`

Install a plugin.

```bash
file-organizer marketplace install PLUGIN_NAME [--version VERSION]
```

#### `marketplace uninstall`

Remove an installed plugin.

```bash
file-organizer marketplace uninstall PLUGIN_NAME
```

#### `marketplace installed`

List installed plugins.

```bash
file-organizer marketplace installed
```

#### `marketplace updates`

Check for plugin updates.

```bash
file-organizer marketplace updates
```

#### `marketplace update`

Update a specific plugin.

```bash
file-organizer marketplace update PLUGIN_NAME
```

---

### `api` — Remote API Client

Interact with a running File Organizer API server.

#### `api health`

Check API server health.

```bash
file-organizer api health [--base-url URL] [--json]
```

#### `api login`

Authenticate and store access tokens.

```bash
file-organizer api login [--base-url URL] [--save-token PATH]
```

#### `api me`

Show current authenticated user.

```bash
file-organizer api me [--base-url URL] [--token TOKEN]
```

#### `api logout`

Invalidate the current session token.

```bash
file-organizer api logout [--base-url URL] [--token TOKEN]
```

#### `api files`

List files via the API.

```bash
file-organizer api files [OPTIONS]
```

#### `api system-status`

Show system status from the API server.

```bash
file-organizer api system-status [--base-url URL]
```

#### `api system-stats`

Show system statistics from the API server.

```bash
file-organizer api system-stats [--base-url URL]
```

**Default base URL:** `http://localhost:8000`

**Examples:**
```bash
file-organizer api health
file-organizer api health --base-url http://myserver:8000
file-organizer api login
file-organizer api system-status
```

---

### `update` — Application Updates

Manage application updates.

#### `update check`

Check for new versions.

```bash
file-organizer update check
```

#### `update install`

Install the latest version.

```bash
file-organizer update install
```

#### `update rollback`

Revert to the previous version.

```bash
file-organizer update rollback
```

---

### `profile` — User Preference Profiles

Manage user preference profiles (powered by the intelligence/learning system).

#### `profile list`

List all available profiles.

```bash
file-organizer profile list
```

#### `profile create`

Create a new profile.

```bash
file-organizer profile create PROFILE_NAME [OPTIONS]
```

#### `profile activate`

Load and activate a profile.

```bash
file-organizer profile activate PROFILE_NAME
```

#### `profile delete`

Delete a profile.

```bash
file-organizer profile delete PROFILE_NAME
```

#### `profile export`

Export a profile to a file.

```bash
file-organizer profile export PROFILE_NAME [--output FILE]
```

#### `profile import`

Import a profile from a file.

```bash
file-organizer profile import FILE [OPTIONS]
```

**Examples:**
```bash
file-organizer profile list
file-organizer profile create work --description "Work files config"
file-organizer profile activate work
```

> **Note:** The `profile` command requires the intelligence/learning optional dependencies (`pip install -e ".[all]"`). It degrades gracefully if not installed.

---

### `autotag` — Auto-Tagging

AI-powered tag suggestions and management.

#### `autotag suggest`

Suggest tags for files in a directory.

```bash
file-organizer autotag suggest DIRECTORY [OPTIONS]
```

Options:
- `--top-n, -n INTEGER` — Max suggestions per file (default: 10)
- `--min-confidence FLOAT` — Minimum confidence % (default: 40.0)
- `--json` — Output as JSON

#### `autotag apply`

Apply tags to a file and record for learning.

```bash
file-organizer autotag apply FILE TAG...
```

#### `autotag popular`

Show the most popular tags.

```bash
file-organizer autotag popular [--limit N]
```

Options:
- `--limit, -n INTEGER` — Number of tags to show (default: 20)

#### `autotag recent`

Show recently used tags.

```bash
file-organizer autotag recent [OPTIONS]
```

Options:
- `--days INTEGER` — Days to look back (default: 30)
- `--limit, -n INTEGER` — Number of tags to show (default: 20)

#### `autotag batch`

Batch tag suggestion for a directory.

```bash
file-organizer autotag batch DIRECTORY [OPTIONS]
```

Options:
- `--pattern TEXT` — File pattern (default: `*`)
- `--recursive / --no-recursive` — Recurse into subdirectories (default: true)
- `--json` — Output as JSON

**Examples:**
```bash
file-organizer autotag suggest ~/Documents
file-organizer autotag apply ~/Documents/report.pdf finance quarterly
file-organizer autotag popular --limit 10
file-organizer autotag recent --days 7
file-organizer autotag batch ~/Documents --pattern "*.pdf" --json
```

---

## Short Alias

Use `fo` as a short alias for `file-organizer`:

```bash
fo serve
fo organize ~/Downloads ~/Organized
fo search "*.pdf" ~/Documents
fo analyze ~/Documents/report.pdf
fo tui
fo copilot chat
fo dedupe scan ~/Pictures
fo autotag suggest ~/Documents
```

---

## Getting Help

```bash
file-organizer --help
file-organizer COMMAND --help
file-organizer COMMAND SUBCOMMAND --help
```

For example:
```bash
file-organizer rules --help
file-organizer rules add --help
file-organizer suggest --help
```
