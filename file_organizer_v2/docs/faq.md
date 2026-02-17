# Frequently Asked Questions

## General Questions

### What is File Organizer?

File Organizer is an AI-powered local file management system that automatically organizes files using local LLMs (large language models). It supports multiple organization methodologies like PARA and Johnny Decimal, with zero cloud dependencies.

### Is my data safe?

Yes. File Organizer:

- Runs 100% locally
- Never uploads files to cloud
- Uses local AI models
- Keeps all data on your device

### What are the system requirements?

- **Python**: 3.9+
- **RAM**: 8 GB minimum (16 GB recommended)
- **Storage**: 10 GB for AI models
- **Ollama**: Latest version

### Can I use it on Windows/Mac/Linux?

Yes. File Organizer runs on all three platforms.

## Installation Questions

### How do I install File Organizer?

Three options:

1. **Docker** (recommended): `docker-compose up -d`
1. **Python Package**: `pip install file-organizer`
1. **From Source**: Clone repo and `pip install -e .`

See [Installation Guide](admin/installation.md).

### Do I need Ollama?

Yes, Ollama provides the AI models. Install from https://ollama.ai

### Which AI models should I use?

We recommend:

- **Text**: qwen2.5:3b-instruct-q4_K_M (~1.9 GB)
- **Vision**: qwen2.5vl:7b-q4_K_M (~6 GB)

Both are optimized for balance between speed and accuracy.

## Usage Questions

### How do I organize my files?

1. Upload files
1. Click **Organize**
1. Choose methodology (PARA, Johnny Decimal, etc.)
1. Review preview
1. Click **Apply**

See [Organization Guide](web-ui/organization.md).

### What file types does it support?

File Organizer supports 43+ file types:

- Documents: PDF, Word, Excel, PowerPoint, Markdown
- Images: JPEG, PNG, GIF, BMP, TIFF
- Video: MP4, AVI, MKV, MOV, WMV
- Audio: MP3, WAV, FLAC, M4A, OGG
- Archives: ZIP, 7Z, TAR, RAR
- Scientific: HDF5, NetCDF, MATLAB
- CAD: DXF, DWG, STEP, IGES

### How do I undo an organization?

Click **Undo** immediately after organizing (or Ctrl+Z).

Or use **Organize** → **Original Structure** to revert all organization.

### Can I organize files without uploading them?

Yes. Click **Organize** → **Browse Local Folder** to organize files already on your system.

### How do I find duplicate files?

Click **Analysis** → **Detect Duplicates**, choose folder(s) to scan, and wait for results.

## Performance Questions

### Organization is slow

Optimizations:

- Use smaller batches
- Close other applications
- Check available disk space
- Use GPU if available

### Memory usage is high

Solutions:

- Close browser tabs
- Reduce maximum file size
- Limit batch size
- Restart service

### Files aren't being found in search

- Check search syntax
- Try broader search terms
- Verify files aren't excluded
- Refresh browser

## API Questions

### How do I use the API?

1. Generate API key in **Settings** → **API Keys**
1. Include in requests: `Authorization: Bearer YOUR_KEY`
1. See [API Reference](api/index.md) for endpoints

### Can I use API keys from scripts?

Yes. Store in environment variables:

```bash
export FILE_ORGANIZER_API_KEY="fo_your_id_your_token"
```

Then use in your script.

### Is the API rate-limited?

Yes. Free tier: 100 requests/minute.

See [API Reference](api/index.md) for details.

## Configuration Questions

### How do I change the workspace path?

Click **Settings** → **Workspace** → **Path**

**Note**: Service must be restarted.

### How do I enable 2-factor authentication?

Click **Settings** → **Security** → **2FA**

Choose authenticator app or SMS.

### Can I customize organization rules?

Yes. Click **Organize** → **Custom** to create custom rules.

## Deployment Questions

### Can I run this in production?

Yes. See [Deployment Guide](admin/deployment.md) for production setup.

### How do I set up HTTPS?

Configure reverse proxy (nginx, Apache) with SSL/TLS certificate.

See [Deployment Guide](admin/deployment.md).

### How do I backup my data?

```bash
# Backup database
docker-compose exec db pg_dump -U postgres file_organizer > backup.sql

# Backup files
rsync -av /path/to/files /path/to/backup
```

See [Admin Guide](admin/index.md).

## Troubleshooting Questions

### Ollama connection fails

Start Ollama service:

```bash
ollama serve
```

Verify: `curl http://localhost:11434/api/version`

### Port already in use

Use different port:

```bash
file-organizer serve --port 8001
```

### Out of memory

Solutions:

- Increase available RAM
- Process smaller batches
- Reduce upload file size
- Use CPU-only mode

See [Troubleshooting Guide](troubleshooting.md) for more issues.

## Contributing Questions

### How can I contribute?

1. Fork repository
1. Create feature branch
1. Make changes with tests
1. Create pull request

See [GitHub Repository](https://github.com/curdriceaurora/Local-File-Organizer) for contribution guidelines.

### How do I report bugs?

1. Search existing issues
1. Create new issue with:
   - Clear description
   - Steps to reproduce
   - System info
   - Error logs

See [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues).

## Getting Help

Can't find your answer?

- **Documentation**: Browse [full docs](index.md)
- **Issues**: [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions)
- **Troubleshooting**: [Troubleshooting Guide](troubleshooting.md)
