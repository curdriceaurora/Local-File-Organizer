# Troubleshooting

## Common Issues

### Ollama Not Running

**Symptom**: `ConnectionRefusedError` or "Ollama unavailable"

**Fix**:
```bash
# Start Ollama
ollama serve

# Verify it's running
ollama list
```

### Model Not Found

**Symptom**: `Model not found` error

**Fix**:
```bash
# Pull the required models
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M

# Verify
ollama list
```

### Out of Memory

**Symptom**: Process killed or `OOM` error

**Fix**:
- Close other applications to free RAM
- Use CPU mode: `file-organizer config edit --device cpu`
- Use a smaller model if available
- Minimum: 8 GB RAM, recommended: 16 GB

### Slow Processing

**Causes and fixes**:
1. **No GPU acceleration**: Set device to `mps` (Mac) or `cuda` (NVIDIA)
   ```bash
   file-organizer config edit --device mps
   ```
2. **Large files**: Processing time scales with file size
3. **Too many files**: Process in smaller batches

### Permission Denied

**Symptom**: `PermissionError` when organizing files

**Fix**:
- Check file permissions: `ls -la <file>`
- Run with appropriate permissions
- Ensure output directory is writable

### TUI Display Issues

**Symptom**: Garbled or missing characters in the terminal UI

**Fix**:
- Use a modern terminal emulator (iTerm2, Windows Terminal, Alacritty)
- Ensure terminal supports Unicode and 256 colors
- Try: `TERM=xterm-256color file-organizer tui`

### Update Fails

**Symptom**: `file-organizer update install` fails

**Fix**:
```bash
# Check connectivity
file-organizer update check

# Try with verbose output
file-organizer --verbose update install

# Rollback if update broke something
file-organizer update rollback
```

**If using AppImage**:
- Ensure the AppImage file is writable (e.g., stored in your home directory).
- Re-run the update after moving the AppImage to a writable location.

### Rules Not Matching

**Symptom**: Preview shows 0 matches

**Debug steps**:
```bash
# Check rules are enabled
file-organizer rules list

# Verify rule conditions
file-organizer rules export

# Preview with verbose output
file-organizer --verbose rules preview ~/Downloads
```

## Getting Help

```bash
# General help
file-organizer --help

# Command-specific help
file-organizer organize --help
file-organizer copilot chat --help
file-organizer rules add --help
```

## Reporting Bugs

File issues at: https://github.com/curdriceaurora/Local-File-Organizer/issues

Include:
- OS and version
- Python version (`python --version`)
- File Organizer version (`file-organizer version`)
- Error message or traceback
- Steps to reproduce
