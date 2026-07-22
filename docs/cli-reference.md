# File Organizer CLI Reference

All commands are available through `file-organizer` or the alias `fo`.

## Core first run commands

Start with this minimal workflow:

```bash
fo setup
fo preview ~/Downloads
fo organize ~/Downloads ~/Organized
fo undo
```

Use `fo undo` after at least one organize run has been recorded.

See the canonical command sections:

- [`setup`](#setup)
- [`preview`](#preview)
- [`organize`](#organize)
- [`undo`](#undo)

## Global Options

These options apply to all commands. You can pass them before or after the command name:

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

### `start`

Run the first-run setup with safe defaults. We recommend this path for beginners.

**Usage:**

```bash
file-organizer start [OPTIONS]
```

**Options:**

- `--profile, -p` — Profile name (default: `default`)
- `--dry-run` — Preview setup choices without saving configuration

**Examples:**

```bash
# Run quick-start setup
file-organizer start

# Configure a named profile
file-organizer start --profile work
```

---

### `quickstart`

Alias of `start` for quick-start setup.

**Usage:**

```bash
file-organizer quickstart [OPTIONS]
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
- `--advanced-help` — Show advanced tuning options and exit

**Advanced tuning options:**

```bash
file-organizer organize --advanced-help
```

Advanced help includes:

- `--max-workers INTEGER` — Cap parallel worker count
- `--sequential` — Force single-worker sequential processing
- `--no-vision`, `--text-only` — Disable vision model loading and use extension fallback for images
- `--prefetch-depth INTEGER` — Parallel task queue-ahead depth (`0` disables prefetch queueing)
- `--no-prefetch` — Backward-compatible alias for `--prefetch-depth 0`
- `--transcribe-audio` — Transcribe audio files with Whisper and use the transcript for content-aware categorization (requires the `[audio]` extra; off by default because transcription is the expensive step)
- `--max-transcribe-seconds FLOAT` — Skip transcription for audio files longer than this (default: 600; `0` disables the cap)
- `--whisper-model TEXT` — Whisper model size for `--transcribe-audio`: `tiny` (default), `base`, `small`, `medium`, `large-v2`, or `large-v3`. Larger models transcribe more accurately but are slower and need a bigger download

**Examples:**

```bash
# Organize ~/Downloads into ~/Organized
file-organizer organize ~/Downloads ~/Organized

# Preview what would happen (no files moved)
file-organizer organize ~/Downloads ~/Organized --dry-run

# Verbose output
file-organizer organize ~/Downloads ~/Organized --verbose

# Show advanced tuning flags
file-organizer organize --advanced-help

# Limit CPU/IO pressure on constrained machines
file-organizer organize ~/Downloads ~/Organized --max-workers 2 --prefetch-depth 1

# Strict sequential mode for deterministic debugging
file-organizer organize ~/Downloads ~/Organized --sequential

# Disable AI vision processing and use extension-based image fallback
file-organizer organize ~/Downloads ~/Organized --no-vision

# Backward-compatible alias
file-organizer organize ~/Downloads ~/Organized --no-prefetch

# Categorize audio by spoken content (podcasts vs. music vs. voice memos)
file-organizer organize ~/Downloads ~/Organized --transcribe-audio

# Higher-accuracy transcription with a larger Whisper model
file-organizer organize ~/Downloads ~/Organized --transcribe-audio --whisper-model small
```

> **Note:** To set a default methodology (PARA, Johnny Decimal, etc.) or override AI models, use `file-organizer config edit` before running organize.

---

### `preview`

Preview how files would be organized without moving them (dry-run shortcut).

**Usage:**

```bash
file-organizer preview INPUT_DIR
```

Supports the same processing options as `organize` (`--max-workers`, `--sequential`, `--no-vision`, `--prefetch-depth`, `--transcribe-audio`, `--max-transcribe-seconds`, `--whisper-model`).

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

<a id="cli-search"></a>
### `search`

Search for files by name pattern with optional type filtering, or use hybrid
BM25+vector semantic search to find files by content relevance.

**Usage:**

```bash
file-organizer search QUERY [DIRECTORY] [OPTIONS]
```

**Arguments:**
- `QUERY` — Search query (glob pattern like `*.pdf`, keyword like `report`, or
  a natural-language phrase when using `--semantic`)
- `DIRECTORY` — Directory to search in (default: current directory)

**Options:**
- `--type, -t TEXT` — Filter by type: `text`, `image`, `video`, `audio`, `archive`
- `--limit, -n INTEGER` — Max results to show (default: 50)
- `--recursive / --no-recursive` — Search subdirectories (default: recursive)
- `--json` — Output as JSON array
- `--semantic` — Use hybrid BM25+vector semantic search instead of filename
  matching; ranks results by content relevance using Reciprocal Rank Fusion

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

# Semantic search — finds files by content relevance, not just filename
file-organizer search "quarterly budget forecast" ~/Documents --semantic

# Semantic search with type filter and JSON output
file-organizer search "meeting notes" ~/work --semantic --type text --json
```

---

### `analyze`

Analyze a file using AI and show its description, category, and confidence score.

**Usage:**

```bash
file-organizer analyze FILE [OPTIONS]
```

**Arguments:**
- `FILE_PATH` — Path to the file to analyze

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

> **Note:** Requires an active model provider configuration (Ollama by default, or another provider configured via `FO_PROVIDER` and related vars).

---

### `tui`

Launch the interactive Terminal User Interface.

```bash
file-organizer tui
```

---

### `doctor`

Scan a directory for file types and recommend optional dependencies.

**Usage:**

```bash
file-organizer doctor PATH [OPTIONS]
```

**Arguments:**

- `PATH` — Directory to scan for file types

**Options:**

- `--install` — Automatically install recommended dependency groups
- `--json` — Output results as JSON

---

### `setup`

Interactive setup wizard for first-run configuration.

**Usage:**

```bash
file-organizer setup [COMMAND]
```

Running `setup` without a subcommand launches the wizard with default settings.

#### `setup run`

Run the setup wizard to configure File Organizer.

```bash
file-organizer setup run [OPTIONS]
```

**Options:**

- `--mode, -m` — Setup mode: `quick-start` (default) or `power-user`
- `--profile, -p` — Profile name (default: `default`)
- `--dry-run` — Preview configuration without saving

---

### `hardware-info`

Detect hardware capabilities and print model-sizing recommendations.

**Usage:**

```bash
file-organizer hardware-info [OPTIONS]
```

**Options:**
- `--json` — Output the hardware profile as JSON

**Examples:**

```bash
# Human-readable hardware summary
file-organizer hardware-info

# JSON output for automation or debugging
file-organizer hardware-info --json
```

> **Why it exists:** This command exposes the same hardware profile the app uses to choose sane defaults for model size and worker count, which helps explain performance differences across machines.

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

**Behavior notes:**

- `--dry-run` previews the exact undo action without modifying history.
- When both selectors are provided, `--transaction-id` takes precedence over `--operation-id`.
- Empty or whitespace-only transaction IDs are rejected instead of being treated as valid input.

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

**Behavior notes:**

- `--dry-run` previews the redo action without changing history.
- `operation_id=0` is treated as a valid operation ID rather than falling back to “redo last”.

---

### `recover`

Replay or sweep the durable-move journal to recover interrupted cross-device moves.

A crash midway through a cross-device rollback move can leave the durable-move
JSONL journal with unfinished `started`/`copied` entries (and possibly orphan
files on disk). Reconciliation is **not** automatic — run this command on demand
(for example, after a crash) to sweep the journal and complete or roll back the
interrupted moves.

**Usage:**

```bash
file-organizer recover [OPTIONS]
```

**Options:**
- `--journal PATH` — Path to the durable-move journal. Defaults to the shared undo journal.
- `--dry-run` — Report planned recovery actions without mutating the journal or disk.

**Examples:**

```bash
# Sweep the default journal
file-organizer recover

# Preview what recovery would do, without touching disk
file-organizer recover --dry-run

# Recover from a specific journal file
file-organizer recover --journal /path/to/durable_move.jsonl
```

**Behavior notes:**

- `--dry-run` calls the same `plan_recovery_actions` planner the real sweep uses, so the preview can never drift from the actual run.
- If the journal does not exist or has no entries, the command reports that there is nothing to recover and exits successfully.
- Transient filesystem errors during the sweep (permissions, disk full) surface as a clean error message, not a stack trace.

---

<a id="cli-history"></a>
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

### `benchmark` — Performance Benchmarking

Measure file processing performance with statistical output, warmup exclusion,
suite selection, and baseline comparison with regression detection.

#### `benchmark run`

Run a performance benchmark on a directory of files.

**Usage:**

```bash
file-organizer benchmark run [INPUT_PATH] [OPTIONS]
```

**Arguments:**

- `INPUT_PATH` — Path to files to benchmark (default: `tests/fixtures/`)

**Options:**

- `--iterations INTEGER, -i INTEGER` — Number of measured iterations (default: `10`, min: `1`)
- `--warmup INTEGER, -w INTEGER` — Warmup iterations excluded from statistics (default: `3`, min: `0`)
- `--suite TEXT, -s TEXT` — Benchmark suite to run: `io`, `text`, `vision`, `audio`, `pipeline`, `e2e` (default: `io`)
  - `io`: file stat/read overhead baseline
  - `text`: `TextProcessor.process_file()` path with deterministic benchmark model stubs
  - `vision`: `VisionProcessor.process_file()` path with deterministic benchmark model stubs
  - `audio`: audio metadata extraction + rule-based classification path (uses synthetic metadata only when optional extractor dependencies are unavailable)
  - `pipeline`: `PipelineOrchestrator.process_batch()` staged path
  - `e2e`: full `FileOrganizer.organize()` pass with real writes in an isolated temp workspace
- `--json` — Output results as JSON instead of a Rich table
- `--compare PATH` — Path to baseline JSON file for regression comparison
- `--transcribe-smoke` — Run a single end-to-end audio transcription smoke test

**Output Metrics (JSON schema):**

- `suite` — Suite name that was run
- `effective_suite` — Effective suite semantics used for execution (for example, `audio` may degrade to `io` semantics when no audio candidates are available)
- `degraded` — `true` when the run used degraded semantics (skip/fallback), otherwise `false`
- `degradation_reasons` — Stable machine-readable degradation reason codes; empty when `degraded` is `false`
- `runner_profile_version` — Benchmark runner semantics profile version for baseline compatibility checks
- `files_count` — Number of files actually processed by the selected suite semantics
- `hardware_profile` — Hardware detection info (CPU, memory, GPU)
- `results.median_ms` — Median iteration time in milliseconds
- `results.p95_ms` — 95th percentile iteration time
- `results.p99_ms` — 99th percentile iteration time
- `results.stddev_ms` — Standard deviation of iteration times
- `results.throughput_fps` — Throughput in files per second (based on median)
- `results.iterations` — Number of measured iterations

When `--compare` is used, JSON also includes:

- `comparison.deltas_pct.*` — Percentage delta versus the baseline for each metric
- `comparison.regression` — `true` if current p95 crossed the regression threshold
- `comparison.threshold` — Threshold multiplier used for regression detection — fixed at `1.2` for the CLI (not user-configurable; emitted in the JSON for consumer reference)
- `comparison_profile_warning` — Present when comparing against a baseline built with a different `runner_profile_version`

**Regression Detection:**

When `--compare` is provided, compares current results against a baseline JSON
file. Flags a regression if p95 exceeds 120% of the baseline p95.

**Examples:**

```bash
# Benchmark files in Downloads with default settings
file-organizer benchmark run ~/Downloads

# Run with 5 iterations, no warmup, JSON output
file-organizer benchmark run ~/Documents --iterations 5 --warmup 0 --json

# Run text suite and compare against baseline
file-organizer benchmark run tests/fixtures/ --suite text --json --compare baseline.json

# Save baseline for future comparison
file-organizer benchmark run tests/fixtures/ --json > baseline.json
```

Audio suite behavior note:
- `audio` intentionally differs from `text`/`vision`: it exercises real metadata extraction + classification and only falls back to synthetic metadata when optional extractor dependencies are unavailable.

---

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

**Arguments:**
- `NAME` — Model name to download (e.g. `qwen2.5:3b-instruct-q4_K_M`)

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

<a id="cli-copilot"></a>
### `copilot` — AI Assistant

Interactive AI copilot for file organisation.

**Workflow entry point:** Start with `copilot chat --dir <DIR>` for scoped guidance, then run suggested concrete commands from other sections (for example `dedupe`, `rules`, or `organize`).

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

#### `copilot status`

Show the status of the AI copilot engine and available models.

```bash
file-organizer copilot status
```

Displays:
- Number of available Ollama models
- Model names (first 5)
- Copilot readiness status

**Examples:**

```bash
file-organizer copilot status
fo copilot status
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

Watch a directory for file events and stream them in real-time.

**Usage:** file-organizer daemon watch WATCH_DIR [OPTIONS]

Arguments:
- `WATCH_DIR` — Directory to watch for file events

Options:
- `--poll-interval FLOAT` — Seconds between polls (default: 1.0)

**Examples:**

```bash
file-organizer daemon watch ~/Inbox
file-organizer daemon watch ~/Documents --poll-interval 2.0
```

#### `daemon process`

One-shot: organize files in a directory and display a summary.

```bash
file-organizer daemon process INPUT_DIR OUTPUT_DIR [OPTIONS]
```

Arguments:
- `INPUT_DIR` — Directory containing files to process
- `OUTPUT_DIR` — Destination directory for organized files

Options:
- `--dry-run` — Preview changes without moving files

**Examples:**

```bash
file-organizer daemon process ~/Inbox ~/Organized

# Preview without moving
file-organizer daemon process ~/Downloads ~/Organized --dry-run
```

Displays a summary table with:
- Total files processed
- Number of files organized
- Skipped and failed counts
- Folder structure created

**Examples:**

```bash
file-organizer daemon start --watch-dir ~/Inbox --output-dir ~/Organized
file-organizer daemon status
file-organizer daemon stop
```

---

<a id="cli-dedupe"></a>
### `dedupe` — Duplicate File Management

Find and manage duplicate files.

**Workflow entry point:** Use `scan` -> `report` -> `resolve` in that order so you can review before changing anything.

#### `dedupe scan`

Scan a directory for duplicate files.

```bash
file-organizer dedupe scan DIRECTORY [OPTIONS]
```

#### `dedupe report`

Generate a duplication report.

```bash
file-organizer dedupe report DIRECTORY [OPTIONS]
```

**Arguments:**
- `DIRECTORY` — Directory to scan

#### `dedupe resolve`

Interactively or automatically resolve duplicates.

```bash
file-organizer dedupe resolve DIRECTORY [OPTIONS]
```

**Arguments:**
- `DIRECTORY` — Directory to scan for duplicates

**Behavior notes:**

- Automatic strategies prompt for confirmation unless batch mode is enabled.
- Manual selection and confirmation prompts propagate `Ctrl+C` cleanly.
- Dry runs report actual simulated removals and estimated space savings without deleting files.
- Successful-removal summaries reflect what was actually removed rather than the original selection count.

**Examples:**

```bash
file-organizer dedupe scan ~/Images
file-organizer dedupe report ~/Images
file-organizer dedupe resolve ~/Images
```

---

<a id="cli-rules"></a>
### `rules` — Organisation Rules

Manage copilot organisation rules and rule sets.

**Workflow entry point:** Use `rules preview <DIR>` for batch review first, then `rules apply <DIR>` when the dry run matches expectations.

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

**Arguments:**
- `NAME` — Rule name

**Options:**
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

**Arguments:**
- `NAME` — Rule name to remove

#### `rules toggle`

Enable or disable a rule.

```bash
file-organizer rules toggle RULE_NAME [--set RULE_SET]
```

**Arguments:**
- `NAME` — Rule name to toggle

#### `rules preview`

Preview what rules would do against a directory (dry-run).

```bash
file-organizer rules preview DIRECTORY [OPTIONS]
```

Options:
- `--set, -s TEXT` — Rule set to evaluate (default: `default`)
- `--recursive/--no-recursive` — Recurse into subdirectories (default: true)
- `--max-files INTEGER` — Maximum files to scan (default: 500)

#### `rules apply`

Apply enabled rules to files in a directory.

```bash
file-organizer rules apply DIRECTORY [OPTIONS]
```

**Arguments:**
- `DIRECTORY` — Directory to apply rules against

**Options:**
- `--set, -s TEXT` — Rule set to evaluate (default: `default`)
- `--recursive/--no-recursive` — Recurse into subdirectories (default: true)
- `--max-files INTEGER` — Maximum files to scan (default: 500)
- `--dry-run` — Preview actions only

#### `rules watch`

Continuously apply enabled rules to a directory.

```bash
file-organizer rules watch DIRECTORY [OPTIONS]
```

**Arguments:**
- `DIRECTORY` — Directory to watch/apply rules against

**Options:**
- `--set, -s TEXT` — Rule set to evaluate (default: `default`)
- `--recursive/--no-recursive` — Recurse into subdirectories (default: true)
- `--max-files INTEGER` — Maximum files to scan (default: 500)
- `--interval FLOAT` — Seconds between apply runs (default: `10.0`)
- `--once` — Run one watch cycle and exit
- `--dry-run` — Preview actions only

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

**Arguments:**
- `FILE` — YAML file to import

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
file-organizer suggest apply DIRECTORY [OPTIONS]
```

**Arguments:**
- `DIRECTORY` — Directory to organize

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

<a id="cli-marketplace"></a>
### `marketplace` — Plugin Marketplace

Browse and manage plugins from the marketplace.

**Workflow entry point:** `marketplace list/search` -> `marketplace info` -> `marketplace install` -> `marketplace installed/updates`.

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

**Arguments:**
- `NAME` — Plugin name

#### `marketplace install`

Install a plugin.

```bash
file-organizer marketplace install PLUGIN_NAME [--version VERSION]
```

**Arguments:**
- `NAME` — Plugin to install

#### `marketplace uninstall`

Remove an installed plugin.

```bash
file-organizer marketplace uninstall PLUGIN_NAME
```

**Arguments:**
- `NAME` — Plugin to uninstall

#### `marketplace review`

Add or update a review for a plugin.

```bash
file-organizer marketplace review PLUGIN_NAME [OPTIONS]
```

Arguments:
- `PLUGIN_NAME` — Name of the plugin to review

Options:
- `--user TEXT` — Reviewer ID (required)
- `--rating INTEGER` — Rating from 1 to 5 (required)
- `--title TEXT` — Review title (required)
- `--content TEXT` — Review text (required)

**Examples:**

```bash
file-organizer marketplace review awesome-plugin \
  --user john_doe \
  --rating 5 \
  --title "Great plugin!" \
  --content "This plugin has saved me hours of work!"
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

**Arguments:**
- `NAME` — Plugin to update

---

### `api` — Remote API Client

Interact with a running File Organizer API server.

Organization commands accept `--token` or `--api-key`, `--base-url`,
`--timeout`, and `--json`. Run `file-organizer api COMMAND --help` for the
complete canonical option surface.

Every `fo api ... --json` success and failure emits the same versioned
top-level envelope as local organization commands: `schema_version`,
`outcome`, `command`, and either normalized result fields or `error`.
Connection, DNS, TLS, and timeout failures use `transport_error` with
`retryable: true`. Exit code `2` covers invalid or missing requests, exit code
`3` covers conflicts, plan mismatches, and recovery-required outcomes, and
other failures exit `1`.

#### `api capabilities`

Show which remote capabilities are available through `fo api`, exposed only
through an official SDK, or unavailable.

```bash
file-organizer api capabilities [OPTIONS]
```

**Options:**
- `--json` — Print deterministic machine-readable output

#### `api health`

Check API server health.

```bash
file-organizer api health [OPTIONS]
```

**Options:**
- `--base-url TEXT` — API base URL (default: `http://localhost:8000`)
- `--timeout FLOAT` — Request timeout in seconds (default: `30.0`)
- `--json` — Print JSON output

#### `api login`

Authenticate and store access tokens.

```bash
file-organizer api login [OPTIONS]
```

**Options:**
- `--username TEXT` — Login username (required; prompted interactively)
- `--password TEXT` — Login password (required; prompted securely)
- `--base-url TEXT` — API base URL (default: `http://localhost:8000`)
- `--timeout FLOAT` — Request timeout in seconds (default: `30.0`)
- `--save-token PATH` — Optional path to save token JSON
- `--json` — Print JSON output

#### `api me`

Show current authenticated user.

```bash
file-organizer api me [OPTIONS]
```

**Options:**
- `--token TEXT` — Bearer token (required)
- `--base-url TEXT` — API base URL (default: `http://localhost:8000`)
- `--timeout FLOAT` — Request timeout in seconds (default: `30.0`)
- `--json` — Print JSON output

#### `api logout`

Invalidate the current session token.

```bash
file-organizer api logout [OPTIONS]
```

**Options:**
- `--token TEXT` — Bearer token (required)
- `--refresh-token TEXT` — Refresh token to revoke (required)
- `--base-url TEXT` — API base URL (default: `http://localhost:8000`)
- `--timeout FLOAT` — Request timeout in seconds (default: `30.0`)

#### `api files`

List files via the API.

```bash
file-organizer api files PATH [OPTIONS]
```

**Arguments:**
- `PATH` — Directory to list

**Options:**
- `--token TEXT` — Bearer token
- `--api-key TEXT` — API key
- `--base-url TEXT` — API base URL (default: `http://localhost:8000`)
- `--recursive/--no-recursive` — Include nested files (default: `--no-recursive`)
- `--include-hidden/--no-include-hidden` — Include hidden files (default: `--no-include-hidden`)
- `--limit INTEGER` — Maximum rows (default: `100`)
- `--timeout FLOAT` — Request timeout in seconds (default: `30.0`)
- `--json` — Print JSON output

#### `api scan`

Scan a server-side directory with canonical recursion and hidden-file policy.

```bash
file-organizer api scan INPUT_DIR [OPTIONS]
```

**Arguments:**
- `INPUT_DIR` — Server-side directory to scan

#### `api preview`

Build a canonical remote organization plan without applying it.

```bash
file-organizer api preview INPUT_DIR OUTPUT_DIR [OPTIONS]
```

**Arguments:**
- `INPUT_DIR` — Server-side source directory
- `OUTPUT_DIR` — Server-side destination directory

Use `--save-plan PATH` to persist the reviewed plan. The command accepts the
same recursion, hidden-file, collision, transfer, methodology, media, model,
provider, and performance options as local organization.

#### `api organize`

Execute a canonical remote request or an exact reviewed plan.

```bash
file-organizer api organize INPUT_DIR OUTPUT_DIR [OPTIONS]
```

**Arguments:**
- `INPUT_DIR` — Server-side source directory
- `OUTPUT_DIR` — Server-side destination directory

Organization queues a background job by default. Use `--foreground` to wait
for a result, `--plan PATH` to execute a reviewed plan, and
`--idempotency-key TEXT` to deduplicate background submissions.

#### `api job`

Inspect one remote organization job.

```bash
file-organizer api job JOB_ID [OPTIONS]
```

**Arguments:**
- `JOB_ID` — Organization job identifier

#### `api jobs`

List recent remote organization jobs, optionally filtered by status.

```bash
file-organizer api jobs [OPTIONS]
```

#### `api cancel`

Cancel a queued or scheduled organization job.

```bash
file-organizer api cancel JOB_ID [OPTIONS]
```

**Arguments:**
- `JOB_ID` — Organization job identifier

Use `--expected-revision INTEGER` for optimistic concurrency control.

#### `api rollback`

Roll back a completed remote organization job.

```bash
file-organizer api rollback JOB_ID [OPTIONS]
```

**Arguments:**
- `JOB_ID` — Organization job identifier

Use `--expected-revision INTEGER` for optimistic concurrency control.

#### `api suggest`

Request a non-mutating single-file organization suggestion.

```bash
file-organizer api suggest FILENAME [OPTIONS]
```

**Arguments:**
- `FILENAME` — File name to classify remotely

#### `api system-status`

Show system status from the API server.

```bash
file-organizer api system-status [PATH] [OPTIONS]
```

**Arguments:**
- `PATH` — Path to inspect (default: `.`)

**Options:**
- `--token TEXT` — Bearer token
- `--api-key TEXT` — API key
- `--base-url TEXT` — API base URL (default: `http://localhost:8000`)
- `--timeout FLOAT` — Request timeout in seconds (default: `30.0`)
- `--json` — Print JSON output

#### `api system-stats`

Show system statistics from the API server.

```bash
file-organizer api system-stats [PATH] [OPTIONS]
```

**Arguments:**
- `PATH` — Directory to analyze (default: `.`)

**Options:**
- `--token TEXT` — Bearer token
- `--api-key TEXT` — API key
- `--base-url TEXT` — API base URL (default: `http://localhost:8000`)
- `--max-depth INTEGER` — Optional max depth
- `--use-cache/--no-use-cache` — Use server-side cache (default: `--use-cache`)
- `--timeout FLOAT` — Request timeout in seconds (default: `30.0`)
- `--json` — Print JSON output

**Default base URL:** `http://localhost:8000`

**Examples:**

```bash
file-organizer api health
file-organizer api health --base-url http://myserver:8000
file-organizer api login
file-organizer api system-status
```

---

### `api-keys` — Local API Key Generation

Generate and store local API keys.

#### `api-keys generate`

Generate a secure API key and print its bcrypt hash.

```bash
file-organizer api-keys generate --output PATH [--prefix PREFIX]
```

**Options:**
- `--output, -o PATH` — Path to safely store the generated API key
- `--prefix TEXT` — API key prefix (default: `fo`)

**Examples:**

```bash
file-organizer api-keys generate -o api-key.txt
file-organizer api-keys generate -o api-key.txt --prefix fo
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

<a id="cli-profile"></a>
### `profile` — Legacy compatibility shim

`profile` is currently a compatibility command that prints guidance and exits.
Use `file-organizer config show --profile <name>` and
`file-organizer config edit --profile <name>` for named configuration profiles.

If your runtime exposes `profile` subcommands, check availability first:

```bash
file-organizer --help
file-organizer profile --help
```

In the current default runtime wiring, `file-organizer profile` is a compatibility shim and does not expose export/import/merge subcommands. Use named config profiles (`config show/edit --profile`) and settings import/export in the Web UI.

```bash
file-organizer profile
```

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
file-organizer autotag apply FILE_PATH TAG...
```

**Arguments:**
- `FILE_PATH` — File to tag
- `TAGS` — One or more tags to apply

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

## `desktop` — Native Desktop Window

Launch the File Organizer desktop application as a native OS window powered by
pywebview.

**Usage:**

```bash
file-organizer desktop [OPTIONS]
# Or using the short alias:
fo desktop [OPTIONS]
```

**Options:**

- `--title TEXT` — Window title bar text (default: `File Organizer`)
- `--width INTEGER` — Initial window width in logical pixels (default: `1280`)
- `--height INTEGER` — Initial window height in logical pixels (default: `800`)

The command starts the FastAPI web UI on a random free port in a background
thread, waits up to 10 seconds for the server to become ready, then opens a
native OS window pointing at the local server.

The process exits cleanly when the window is closed; no background server is
left running.

**Prerequisites:**

- `pip install "local-file-organizer[desktop]"` (installs pywebview + uvicorn)
- Ollama running with at least one model pulled
- Linux: `sudo apt-get install -y libgirepository1.0-dev gir1.2-webkit2-4.1`

!!! note
    The legacy standalone `file-organizer-desktop` entry point is still supported as a backward-compatibility alias, but the unified `fo desktop` subcommand is preferred.

**Examples:**

```bash
# Start the desktop window with default settings
fo desktop

# Start with a custom title and window dimensions
fo desktop --title "My Personal Organizer" --width 1024 --height 768
```

See [Desktop App Guide](desktop-app.md) for full documentation.

---

## `docs` — Project Documentation

Build or serve the local project documentation using mkdocs.

**Usage:**

```bash
file-organizer docs [OPTIONS]
# Or using the short alias:
fo docs [OPTIONS]
```

**Options:**

- `--build, -b` — Compile the documentation to HTML instead of starting the live-reload server (default: false)
- `--host TEXT` — Bind address for the docs server (default: `127.0.0.1`)
- `--port INTEGER` — Port number for the docs server (default: `8001`)

**Prerequisites:**

- `pip install "local-file-organizer[docs]"` (installs mkdocs + mkdocs-material)

**Examples:**

```bash
# Start the live-reload documentation server at http://127.0.0.1:8001/
fo docs

# Start the server on a custom port and bind address
fo docs --host 0.0.0.0 --port 9000

# Build the static HTML documentation to the site/ directory
fo docs --build
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
