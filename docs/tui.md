# Terminal User Interface (TUI)

> **Version**: 2.0.0-alpha.3

The TUI is built with Textual and launched from the unified CLI.

## Launch

```bash
file-organizer tui
# or
fo tui
```

## Overview

![TUI Overview](assets/tui-overview.svg)

![TUI Demo](assets/tui-demo.gif)

## Keyboard shortcuts

These are the global app-level bindings from `FileOrganizerApp.BINDINGS`.

### Global

| Key | Action |
|-----|--------|
| `q` / `Ctrl+c` | Quit |
| `?` | Toggle help |
| `Tab` | Focus next panel |
| `1`–`8` | Switch main view |
| `Ctrl+w` | Complete setup wizard (wizard flow) |

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

## View-local bindings (examples)

The TUI also defines view-local bindings across modules (for example in `file_browser.py`, `organization_preview.py`, `settings_view.py`, `copilot_view.py`, and other view files).

Examples:

- File browser tree supports vim-style navigation (`h`, `j`, `k`, `l`)
- File browser filter toggle: `/`
- Other views expose local controls through their own `BINDINGS` declarations

## Setup wizard behavior

If setup is not completed, the TUI opens the setup wizard first and then transitions to the main app layout.

## Related docs

- [CLI Reference](cli-reference.md)
- [Desktop App Guide](desktop-app.md)
- [Web UI Guide](web-ui/index.md)
