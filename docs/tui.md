# Terminal User Interface (TUI)

> **Version**: 2.1.0

The Textual framework builds the TUI. You start the TUI from the CLI.

## Start the TUI

```bash
file-organizer tui
# or
fo tui
```

## Quick workflow

1. Start the TUI. Wait for the main layout. Complete the setup wizard if necessary.
2. Press `1` to `8` to change main views. You can see files, results, history, settings, and copilot.
3. Press `Tab` to change focus. Press `?` to see active keyboard shortcuts.
4. Press `4` to open the Methodology view. Verify your strategy before you start large organization jobs.

## Overview

The Files view shows the directory tree, the metadata panel, and a live preview of the selected file.

![TUI Overview](assets/tui-overview.svg)

This is a quick demonstration of the main views:

![TUI Demo](assets/tui-demo.gif)

## View gallery

### Organized (`2`)

This view shows a preview. It shows how the software will organize the current directory.

![Organization Preview](assets/organization-preview.svg)

### Analytics (`3`)

This dashboard shows storage data, file types, quality scores, and duplicate statistics for the current directory.

![Analytics Dashboard](assets/analytics-dashboard.svg)

### Methodology (`4`)

Select a flat, PARA, or Johnny Decimal organization system.

![Methodology View](assets/methodology-view.svg)

### Audio (`5`)

The software searches the directory for audio files. It shows tag metadata and classification for the selected file.

![Audio Panel](assets/audio-panel.svg)

### History (`6`)

This view shows recent operations. It includes undo and redo options.

![History View](assets/history-view.svg)

### Copilot (`8`)

The local intent engine lets you manage files with natural language.

![Copilot Chat](assets/copilot-chat.svg)

## Keyboard shortcuts

These are the global keyboard shortcuts from `FileOrganizerApp.BINDINGS`.

### Global

| Key | Action |
|-----|--------|
| `q` / `Ctrl+c` | Stop the application |
| `?` | Show or hide help |
| `Tab` | Focus the next panel |
| `1`–`8` | Change the main view |
| `Ctrl+w` | Complete the setup wizard |

### View map (`1`–`8`)

| Key | View |
|-----|------|
| `1` | Files |
| `2` | Organized |
| `3` | Analytics |
| `4` | Methodology |
| `5` | Audio |
| `6` | History |
| `7` | Settings |
| `8` | Copilot |

## Local keyboard shortcuts

The TUI also has local keyboard shortcuts for specific views.

Examples:

- The file browser supports vim-style navigation keys (`h`, `j`, `k`, `l`).
- Press `/` to toggle the file browser filter.
- Other views have their own `BINDINGS` properties for local controls.

## Setup wizard

If you did not complete the setup, the TUI shows the setup wizard. After setup, the main layout shows.

## Troubleshooting

### Incorrect colors or broken display

**Symptom**: The display shows raw escape codes. Colors are missing. The layout is broken.

**Cause**: The `TERM` environment variable is incorrect. The terminal does not support colors correctly.

**Solution**:

```bash
# Force 256-color or true-color mode
export TERM=xterm-256color
file-organizer tui

# If colors are incorrect, disable color
export NO_COLOR=1
file-organizer tui

# Force color output
export FORCE_COLOR=1
file-organizer tui
```

If you use a multiplexer (tmux, screen), configure it to allow true-color sequences:

```bash
# In ~/.tmux.conf
set -g default-terminal "tmux-256color"
set -ag terminal-overrides ",xterm-256color:RGB"
```

### Blank screen

**Symptom**: The TUI opens but shows a blank window. It stays blank or recovers after a delay.

**Cause**: The terminal size is too small. The terminal reports incorrect dimensions.

**Solution**:

```bash
# Make the terminal window larger than 80x24
file-organizer tui

# If the screen stays blank, reset the terminal
reset
file-organizer tui
```

### Setup wizard does not complete

**Symptom**: The setup wizard does not continue. Keyboard inputs have no effect.

**Cause**: You did not fill a required field. The terminal captures your keyboard inputs.

**Solution**:

- Press `Ctrl+W` to complete the wizard.
- Make sure the wizard panel has focus. Click the panel or press `Tab`.
- If the problem continues, restart the TUI:

```bash
file-organizer tui
```

### Multiplexer captures keyboard shortcuts

**Symptom**: Global shortcuts (`Ctrl+C`, `Ctrl+W`) do not work in tmux or screen.

**Cause**: The multiplexer captures the key sequences.

**Solution**:

In **tmux**, use `send-keys` to send the keys to the application:

```bash
# Send Ctrl+W to the TUI pane
tmux send-keys C-w
```

Remove conflicting tmux bindings:

```bash
# In ~/.tmux.conf
unbind -T copy-mode C-w
```

In **GNU screen**, press `Ctrl+a` then `a` to send `Ctrl+a`. Use `stuff` to send keys:

```bash
# From the screen command line (Ctrl+a :)
:stuff ^W
```

If problems continue, use a standard terminal window instead of a multiplexer.

## Related documents

- [CLI Reference](cli-reference.md)
- [Desktop App Guide](desktop-app.md)
- [Web UI Guide](web-ui/index.md)
