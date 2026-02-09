# Troubleshooting

## Common Issues

### Ollama Not Running

**Symptom**: `ConnectionRefusedError` or "Ollama unavailable".

**Fix**:

```bash
# Start Ollama
ollama serve

# Verify it's running
ollama list
```

### Model Not Found

**Symptom**: `Model not found`.

**Fix**:

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

### Audio View Empty

**Symptom**: Audio panel shows no files or metadata.

**Fix**:

- Install audio extras: `pip install -e ".[audio]"`
- Ensure FFmpeg is installed and on your PATH
- Rescan with `r` in the Audio view

### Deduplication Is Slow

**Fixes**:

- Limit scope: `file-organizer dedupe scan ./Documents --min-size 1000000`
- Use include/exclude patterns
- Start with a smaller directory and expand

### Daemon Won't Start

**Symptoms**: PID file missing, status says stopped.

**Fix**:

- Start in foreground to view errors:
  ```bash
  file-organizer daemon start --foreground --watch-dir ./inbox --output-dir ./organized
  ```
- Check that the output directory is writable.

### Watcher Not Seeing Changes

**Fixes**:

- Confirm the watch directory exists
- Increase poll interval: `file-organizer daemon watch ./inbox --poll-interval 2`
- Remove overly aggressive `exclude_patterns` in config

### Update Fails

**Fix**:

```bash
file-organizer update check
file-organizer --verbose update install
file-organizer update rollback
```

If you are running a packaged build, ensure the executable or AppImage is in a writable location.

### TUI Display Issues

**Symptom**: Garbled or missing characters.

**Fix**:

- Use a modern terminal emulator (iTerm2, Windows Terminal, Alacritty)
- Ensure terminal supports Unicode and 256 colors
- Try: `TERM=xterm-256color file-organizer tui`

### Rules Not Matching

**Debug steps**:

```bash
file-organizer rules list
file-organizer rules export
file-organizer --verbose rules preview ./Downloads
```

### Analytics or History Empty

**Fix**:

- Run an organize or preview command first
- Refresh Analytics (`r`) or History (`r`) in the TUI

### Permission Denied

**Symptom**: `PermissionError` when organizing files.

**Fix**:

- Check file permissions
- Ensure output directory is writable
- Avoid running from read-only locations

## Getting Help

```bash
file-organizer --help
file-organizer organize --help
file-organizer copilot chat --help
file-organizer rules add --help
```

## Reporting Bugs

File issues at the [GitHub Issues page](https://github.com/curdriceaurora/Local-File-Organizer/issues).

Include:

- OS and version
- Python version (`python --version`)
- File Organizer version (`file-organizer version`)
- Error message or traceback
- Steps to reproduce
