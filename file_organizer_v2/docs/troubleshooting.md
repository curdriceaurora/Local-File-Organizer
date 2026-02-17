# Troubleshooting Guide

Common issues and solutions.

## Installation Issues

### Ollama Connection Failed

**Error**: `ConnectionRefusedError` or "Ollama unavailable"

**Solution**:

```bash
# Start Ollama
ollama serve

# Verify it's running
curl http://localhost:11434/api/version
```

### Model Not Found

**Error**: "Model not found"

**Solution**:

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
ollama list  # Verify they're installed
```

### Port Already in Use

**Error**: "Port 8000 is already in use"

**Solution**:

```bash
# Use different port
file-organizer serve --port 8001

# Or find process using 8000
lsof -i :8000
kill -9 <PID>
```

## Getting Help

If you can't find a solution:

1. **Check documentation**: [Full docs](index.md)
1. **Review logs**: `docker-compose logs`
1. **GitHub Issues**: [Report issue](https://github.com/curdriceaurora/Local-File-Organizer/issues)
1. **Discussions**: [Ask questions](https://github.com/curdriceaurora/Local-File-Organizer/discussions)
1. **FAQ**: [Frequently Asked Questions](faq.md)
