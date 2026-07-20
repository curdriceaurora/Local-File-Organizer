# Frequently Asked Questions

## General Questions

### What is File Organizer?

File Organizer is an AI-powered local file management system. It automatically organizes files. It uses local LLMs (large language models). It supports multiple organization methodologies like PARA and Johnny Decimal. It has zero cloud dependencies.

### Is my data safe?

Yes. File Organizer:

- Runs locally 100% of the time.
- Never uploads files to the cloud.
- Uses local AI models.
- Keeps all data on your device.

### What are the system requirements?

- **Python**: 3.11 or higher
- **RAM**: 8 GB minimum (16 GB recommended)
- **Storage**: 10 GB for AI models
- **Ollama**: Latest version

### Can I use it on Windows, Mac, or Linux?

Yes. File Organizer runs on all three platforms.

## Installation Questions

### How do I install File Organizer?

You have three options:

1. **Docker** (recommended): Run `docker-compose up -d`.
1. **Python Package**: Run `pip install local-file-organizer`.
1. **From Source**: Clone the repository and run `pip install -e .`.

Read the [Installation Guide](admin/installation.md).

### Do I need Ollama?

Yes. Ollama gives the AI models. Install it from <https://ollama.ai>.

### Which AI models should I use?

We recommend:

- **Text**: qwen2.5:3b-instruct-q4_K_M (approximately 1.9 GB)
- **Vision**: qwen2.5vl:7b-q4_K_M (approximately 6 GB)

Both give a good balance between speed and accuracy.

## Usage Questions

### How do I organize my files?

1. Upload your files.
1. Click **Organize**.
1. Choose a methodology (PARA, Johnny Decimal, etc.).
1. Review the preview.
1. Click **Apply**.

Read the [Organization Guide](web-ui/organization.md).

### What file types does it support?

File Organizer supports more than 43 file types:

- Documents: PDF, Word, Excel, PowerPoint, Markdown
- Images: JPEG, PNG, GIF, BMP, TIFF
- Video: MP4, AVI, MKV, MOV, WMV
- Audio: MP3, WAV, FLAC, M4A, OGG
- Archives: ZIP, 7Z, TAR, RAR
- Scientific: HDF5, NetCDF, MATLAB
- CAD: DXF, DWG, STEP, IGES

### How do I undo an organization?

Click **Undo** immediately after you organize files. Or press Ctrl+Z.

Or, click **Organize** and then **Original Structure** to revert all organization.

### Can I organize files without uploading them?

Yes. Click **Organize** and then **Browse Local Folder**. This organizes files that are already on your system.

### How do I find duplicate files?

Click **Analysis** and then **Detect Duplicates**. Choose the folders to scan. Wait for the results.

## Performance Questions

### Organization is slow

How to make it faster:

- Use smaller batches.
- Close other applications.
- Check available disk space.
- Use a GPU if you have one.

### Memory usage is high

How to solve this:

- Close browser tabs.
- Decrease the maximum file size.
- Decrease the batch size.
- Restart the service.

### Files do not show in search

- Check your search syntax.
- Try broader search terms.
- Make sure the files are not excluded.
- Refresh your browser.

## API Questions

### How do I use the API?

1. Go to **Settings** and then **API Keys** to generate an API key.
1. Include the key in your requests: `Authorization: Bearer YOUR_KEY`.
1. Read the [API Reference](api/index.md) to find endpoints.

### Can I use API keys from scripts?

Yes. Store them in environment variables:

```bash
export FILE_ORGANIZER_API_KEY="fo_your_id_your_token"
```

Then, use the variable in your script.

### Is the API rate-limited?

Yes. The free tier allows 100 requests per minute.

Read the [API Reference](api/index.md) to find more data.

## Configuration Questions

### How do I change the workspace path?

Click **Settings**, then **Workspace**, and then **Path**.

**Note**: You must restart the service after you change the path.

### How do I enable two-factor authentication?

Click **Settings**, then **Security**, and then **2FA**.

Choose an authenticator app or SMS.

### Can I customize organization rules?

Yes. Click **Organize** and then **Custom** to make custom rules.

## Deployment Questions

### Can I run this in production?

Yes. Read the [Deployment Guide](admin/deployment.md) to find production setup instructions.

### How do I set up HTTPS?

Configure a reverse proxy (nginx or Apache). Use an SSL or TLS certificate.

Read the [Deployment Guide](admin/deployment.md).

### How do I backup my data?

```bash
# Backup the database
docker-compose exec db pg_dump -U postgres file_organizer > backup.sql

# Backup the files
rsync -av /path/to/files /path/to/backup
```

Read the [Admin Guide](admin/index.md).

## Troubleshooting Questions

### Ollama connection fails

Start the Ollama service:

```bash
ollama serve
```

Verify it: `curl http://localhost:11434/api/version`

### Port already in use

Use a different port:

```bash
file-organizer serve --port 8001
```

### Out of memory

How to solve this:

- Increase available RAM.
- Process smaller batches.
- Decrease the upload file size.
- Use CPU-only mode.

Read the [Troubleshooting Guide](troubleshooting.md) to find solutions for more issues.

## Contributing Questions

### How can I contribute?

1. Fork the repository.
1. Create a feature branch.
1. Make your changes and write tests.
1. Create a pull request.

Read the [GitHub Repository](https://github.com/curdriceaurora/Local-File-Organizer) to find contribution guidelines.

### How do I report bugs?

1. Search existing issues.
1. Create a new issue with:
   - A clear description.
   - Steps to reproduce the bug.
   - System data.
   - Error logs.

Read [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues).

## Getting Help

Can you not find your answer?

- **Documentation**: Read the [full documentation](index.md).
- **Issues**: [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues).
- **Discussions**: [GitHub Discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions).
- **Troubleshooting**: [Troubleshooting Guide](troubleshooting.md).
