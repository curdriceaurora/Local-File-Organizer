# File Organizer v2.0 🚀

> **Status**: Alpha - Active Development (Week 2 Complete!)
>
> AI-powered local file management with state-of-the-art models. Privacy-first, runs 100% on your device.

## What's New in v2.0

### Core Improvements
- ✅ **Better AI Models**: Qwen2.5 3B (+15-20% accuracy over Llama3.2)
- ✅ **Enhanced Vision**: Qwen2.5-VL 7B (+15% DocVQA, 125K context)
- ✅ **Modern Framework**: Ollama for better performance and ease of use
- ✅ **Model Abstraction**: Clean architecture with pluggable models
- ✅ **Image Support**: Full image processing with vision AI (Week 2 ✅)
- ✅ **Video Support**: Basic video processing (Week 2 ✅)
- 🚧 **Audio Support**: Coming in Phase 3 (Distil-Whisper)
- 🚧 **Modern UI**: Textual TUI coming in Phase 2

### Architecture
- Event-driven microservices (Phase 5)
- Multiple interfaces: CLI, TUI, Web, GUI
- PARA + Johnny Decimal methodology (Phase 3)
- Deduplication support (Phase 4)
- User preference learning (Phase 4)

## 🚀 Quick Start (End-to-End Demo)

**Try the demo with sample files in under 1 minute:**

```bash
# 1. Demo with sample files (safe - dry run to preview)
python3 demo.py --sample --dry-run

# 2. Actually organize the samples
python3 demo.py --sample

# 3. Check the results
ls -R demo_organized/
```

**Organize your own files:**

```bash
# Dry run first (recommended)
python3 demo.py --input ~/Downloads --output ~/Organized --dry-run

# Actually organize
python3 demo.py --input ~/Downloads --output ~/Organized
```

See [DEMO_COMPLETE.md](DEMO_COMPLETE.md) for full text processing documentation.
See [WEEK2_IMAGE_PROCESSING.md](WEEK2_IMAGE_PROCESSING.md) for image/video processing.

---

## Prerequisites

1. **Python 3.12+**
   ```bash
   python --version  # Should be 3.12 or higher
   ```

2. **Ollama** (for AI models)
   ```bash
   # macOS/Linux
   curl -fsSL https://ollama.com/install.sh | sh

   # Or visit https://ollama.com for other platforms
   ```

### Installation

1. **Install the package**
   ```bash
   cd file_organizer_v2
   pip install -e .
   ```

2. **Pull AI models** (first time only)
   ```bash
   # Text model (~2 GB) - required
   ollama pull qwen2.5:3b-instruct-q4_K_M

   # Vision model (~6 GB) - required for images/videos
   ollama pull qwen2.5vl:7b-q4_K_M
   ```

3. **Verify installation**
   ```bash
   python -c "from file_organizer.models import TextModel; print('✓ Installation successful!')"
   ```

## Development Setup

### For Contributors

1. **Clone and setup**
   ```bash
   git clone <repo-url>
   cd file_organizer_v2
   pip install -e ".[dev]"
   ```

2. **Install pre-commit hooks**
   ```bash
   pre-commit install
   ```

3. **Run tests**
   ```bash
   pytest
   ```

4. **Type checking**
   ```bash
   mypy src/file_organizer
   ```

5. **Linting**
   ```bash
   ruff check src/
   ```

## Usage

### Python API (Current Phase 1)

```python
from file_organizer.models import TextModel, VisionModel
from file_organizer.models.base import ModelConfig, ModelType

# Initialize text model
text_config = TextModel.get_default_config()
text_model = TextModel(text_config)

with text_model:
    # Generate summary
    summary = text_model.generate(
        "Summarize this text: The quick brown fox jumps over the lazy dog."
    )
    print(summary)

# Initialize vision model
vision_config = VisionModel.get_default_config()
vision_model = VisionModel(vision_config)

with vision_model:
    # Analyze image
    description = vision_model.analyze_image(
        "path/to/image.jpg",
        task="describe"
    )
    print(description)
```

### CLI (Phase 2+)

**Basic Organization:**
```bash
# Quick organization
file-organizer organize /path/to/files --mode content

# Preview changes
file-organizer preview /path/to/files

# Interactive TUI
file-organizer tui
```

**Phase 4 Features (Available Now):**
```bash
# Deduplication
python -m file_organizer.cli.dedupe ~/Downloads --strategy oldest --dry-run

# Analytics Dashboard
python -m file_organizer.cli.analytics ~/Documents --export report.json

# Profile Management
python -m file_organizer.cli.profile export my-profile.json
python -m file_organizer.cli.profile import shared-profile.json

# Undo/Redo Operations
python -m file_organizer.cli.undo_redo --list
python -m file_organizer.cli.undo_redo --undo

# Auto-tagging
python -m file_organizer.cli.autotag ~/Documents --model qwen2.5:3b
```

See [Phase 4 Documentation](docs/phase4/) for complete CLI reference.

## Project Structure

```
file_organizer_v2/
├── src/
│   └── file_organizer/
│       ├── core/              # Core business logic
│       ├── models/            # AI model interfaces ✅
│       │   ├── base.py       # Base model abstraction
│       │   ├── text_model.py # Text generation
│       │   ├── vision_model.py # Image/video analysis
│       │   └── audio_model.py # Audio transcription (Phase 3)
│       ├── services/          # Microservices (Phase 5)
│       ├── interfaces/        # CLI, TUI, Web (Phase 2+)
│       ├── methodologies/     # PARA, Johnny Decimal (Phase 3)
│       ├── utils/             # Utilities
│       └── config/            # Configuration
├── tests/                     # Test suite
├── docs/                      # Documentation
├── scripts/                   # Utility scripts
├── pyproject.toml            # Project configuration
└── README.md                 # This file
```

## Development Roadmap

### ✅ Phase 1: Foundation (Weeks 1-2) - COMPLETE!
- [x] Project structure and dependencies
- [x] Model abstraction layer
- [x] Ollama integration
- [x] Text model (Qwen2.5 3B)
- [x] Vision model (Qwen2.5-VL 7B)
- [x] Text processing service (Week 1)
- [x] Vision processing service (Week 2)
- [x] Image and video support (Week 2)
- [x] End-to-end demo
- [ ] Benchmarking vs v1 (optional)

### 🚧 Phase 2: Enhanced UX (Weeks 4-6)
- [ ] Typer CLI framework
- [ ] Rich output formatting
- [ ] Textual TUI interface
- [ ] Better error handling

### 📅 Phase 3: Feature Expansion (Weeks 7-10)
- [ ] Audio support (Distil-Whisper)
- [ ] Video support
- [ ] Ebook formats
- [ ] PARA + Johnny Decimal methodology

### ✅ Phase 4: Intelligence (Weeks 11-13) - COMPLETE!
- [x] Hash-based deduplication (#46)
- [x] Perceptual image deduplication (#47)
- [x] Semantic document deduplication (#48)
- [x] Pattern learning system (#49)
- [x] User preference tracking (#50)
- [x] Profile management (#51)
- [x] Smart suggestions (#52)
- [x] Operation history tracking (#53)
- [x] Auto-tagging (#54)
- [x] Undo/redo functionality (#55)
- [x] Analytics dashboard (#56)

**New Features:**
- **Deduplication**: Hash, perceptual, and semantic duplicate detection
- **Intelligence**: Learns from your organization patterns and preferences
- **History & Undo**: Full operation history with undo/redo support
- **Smart Features**: Auto-suggestions, auto-tagging, profile management
- **Analytics**: Comprehensive storage and quality metrics

See [Phase 4 Documentation](docs/phase4/) for detailed guides.

### 📅 Phase 5: Architecture (Weeks 14-17)
- [ ] Event-driven microservices
- [ ] Redis Streams
- [ ] Real-time file watching

### 📅 Phase 6: Web Interface (Weeks 18-21)
- [ ] FastAPI backend
- [ ] HTMX frontend
- [ ] WebSocket updates
- [ ] Multi-user support

## Testing

### Run Tests
```bash
# All tests
pytest

# Unit tests only
pytest -m unit

# Integration tests
pytest -m integration

# With coverage
pytest --cov=file_organizer --cov-report=html
```

### Manual Testing
```bash
# Test text model
python scripts/test_text_model.py

# Test vision model
python scripts/test_vision_model.py

# Benchmark performance
python scripts/benchmark.py
```

## Configuration

### Environment Variables
```bash
# Ollama settings
OLLAMA_HOST=http://localhost:11434

# Logging
LOG_LEVEL=INFO
LOG_FILE=~/.local/share/file-organizer/logs/app.log

# Model settings
TEXT_MODEL=qwen2.5:3b-instruct-q4_K_M
VISION_MODEL=qwen2.5-vl:7b-q4_K_M
```

### Configuration File
`~/.config/file-organizer/config.yaml` (Coming in Phase 2)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

### Development Workflow
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Run type checking (`mypy src/`)
6. Run linting (`ruff check src/`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## Hardware Requirements

### Minimum (Basic functionality)
- CPU: 4 cores
- RAM: 8 GB
- Storage: 20 GB

### Recommended (Optimal performance)
- CPU: 8+ cores
- RAM: 16 GB
- Storage: 50 GB SSD
- GPU: 8GB VRAM or Apple Silicon M1+

## Troubleshooting

### Ollama Connection Issues
```bash
# Check if Ollama is running
ollama list

# Start Ollama service
ollama serve

# Check Ollama version
ollama --version
```

### Model Not Found
```bash
# List installed models
ollama list

# Pull missing model
ollama pull qwen2.5:3b-instruct-q4_K_M
```

### Import Errors
```bash
# Reinstall in development mode
pip install -e ".[dev]"

# Verify Python version
python --version  # Must be 3.12+
```

## License

Dual-licensed under MIT OR Apache-2.0. Choose whichever works best for you.

## Links

- **v1 Documentation**: See parent directory
- **SOTA Research**: [SOTA_2026_RESEARCH.md](../SOTA_2026_RESEARCH.md)
- **Rebuild Plan**: [REBUILD_PLAN.md](../REBUILD_PLAN.md)
- **Issues**: [GitHub Issues](https://github.com/yourusername/file-organizer/issues)

## Support

- 📖 [Documentation](docs/)
- 💬 [Discussions](https://github.com/yourusername/file-organizer/discussions)
- 🐛 [Bug Reports](https://github.com/yourusername/file-organizer/issues/new?template=bug_report.md)
- ✨ [Feature Requests](https://github.com/yourusername/file-organizer/issues/new?template=feature_request.md)

---

**Status**: Alpha | **Version**: 2.0.0-alpha.1 | **Last Updated**: 2026-01-20
