---
name: file-organizer-v2
description: AI-powered local file management system with privacy-first architecture
status: in-progress
created: 2026-01-20T23:40:00Z
updated: 2026-01-20T23:40:00Z
---

# File Organizer v2.0 - Product Requirements Document

## Vision

Make digital file organization effortless, intelligent, and privacy-respecting through state-of-the-art local AI models.

## Problem Statement

Knowledge workers spend an average of 9.3 hours per week searching for files and organizing their digital workspace. Existing solutions either:
1. Rely on cloud services (privacy concerns)
2. Use simple rule-based organization (limited intelligence)
3. Require manual categorization (time-consuming)

## Solution

File Organizer v2.0 uses state-of-the-art AI models (Qwen2.5 text + vision) running 100% locally to:
- Understand file content intelligently
- Generate meaningful folder structures
- Create descriptive filenames
- Organize 15+ file types automatically
- Preserve complete privacy (zero cloud dependencies)

## Current Status (Phase 1 Complete)

### What's Working ✅
- **Text Processing**: 9 formats (PDF, DOCX, TXT, MD, CSV, XLSX, PPT, PPTX, EPUB)
- **Image Processing**: 6 formats (JPG, PNG, GIF, BMP, TIFF) with OCR
- **Video Processing**: 5 formats (basic first-frame analysis)
- **Quality**: 100% meaningful names on tested files
- **Architecture**: Modern Python 3.12+, modular, type-safe
- **Performance**: ~7s/text file, ~4min/image

### Known Issues ⚠️
- **Critical**: Image processing speed (240s/image needs optimization)
- Vision model loading occasionally fails (restart Ollama)
- Video only analyzes first frame (multi-frame planned Phase 3)

## Target Users

1. **Sarah - Freelance Designer**: Thousands of project files, client assets
2. **David - PhD Researcher**: Hundreds of papers, datasets, notes
3. **Emily - Small Business Owner**: Invoices, receipts, product photos
4. **Alex - Privacy Advocate**: Wants local-only solution

## Success Metrics

- **Adoption**: 1,000 active users by Month 6
- **Quality**: >95% meaningful file names
- **Time Saved**: >9 hours/week per user
- **Satisfaction**: >4.5/5 stars
- **Processing**: Text <10s, Images <30s (Phase 2 target)

## Roadmap Overview

### Phase 2: Enhanced UX (Weeks 3-4) 🎯
**Priority Features**:
- **Copilot Mode**: Chat with AI for custom organization ("organize all PDFs by date")
- **CLI Model Switching**: Dynamic model selection
- **Interactive TUI**: Terminal UI with file browser
- **Configuration System**: YAML-based preferences
- **Cross-Platform Executables**: macOS, Windows, Linux binaries

**Success Criteria**:
- Setup time <10 minutes
- User satisfaction >4.0/5
- TUI fully functional
- Executables available

### Phase 3: Feature Expansion (Weeks 5-7) 📚
**Key Features**:
- **Audio Support**: MP3, WAV, FLAC with transcription (Distil-Whisper)
- **Advanced Video**: Multi-frame analysis, scene detection
- **PARA Methodology**: Projects/Areas/Resources/Archive organization
- **Johnny Decimal**: Hierarchical numbering system
- **Enhanced Ebooks**: Chapter analysis, metadata extraction

**Success Criteria**:
- 20+ file types supported
- Audio transcription >90% accuracy
- Video quality significantly improved

### Phase 4: Intelligence (Weeks 8-10) 🧠
**Key Features**:
- **Deduplication**: Hash-based + perceptual (images)
- **Preference Learning**: Adapt to user corrections
- **Undo/Redo**: Complete operation history
- **Smart Suggestions**: AI-powered recommendations

**Success Criteria**:
- Duplicate detection >99% accurate
- Storage savings >20% average
- Undo works 100% reliably

### Phase 5: Architecture (Weeks 11-13) 🏗️
**Key Features**:
- **Event-Driven**: Redis Streams, microservices
- **Real-Time Watching**: Auto-organize new files
- **Batch Optimization**: 3x speed improvement
- **Docker Deployment**: Containerized with Compose
- **CI/CD Pipeline**: Automated testing, releases

**Success Criteria**:
- Handle 100,000+ files
- Real-time latency <1s
- Processing 3x faster
- Docker images published

### Phase 6: Web Interface (Weeks 14-16) 🌐
**Key Features**:
- **FastAPI Backend**: RESTful API
- **HTMX Frontend**: Modern web UI
- **WebSocket Updates**: Real-time progress
- **Multi-User**: Team collaboration
- **Plugin System**: Extensibility framework

**Success Criteria**:
- Web UI feature parity with CLI
- 10+ community plugins
- Multi-user works smoothly

## Technical Architecture

### Current Stack
```yaml
Core:
  Language: Python 3.12+
  Framework: Ollama (model serving)

AI Models:
  Text: Qwen2.5 3B Instruct Q4_K_M (1.9 GB)
  Vision: Qwen2.5-VL 7B Q4_K_M (6.0 GB)

Libraries:
  File Processing: PyMuPDF, python-docx, pandas, python-pptx, ebooklib
  NLP: NLTK
  UI: Rich (terminal)
  Logging: loguru
```

### Planned Additions
- **Phase 2**: Typer (CLI), Textual (TUI), PyYAML (config), PyInstaller (executables)
- **Phase 3**: faster-whisper (audio), ffmpeg-python (video)
- **Phase 4**: imagededup (perceptual hashing), scikit-learn (similarity)
- **Phase 5**: Redis, watchdog, Docker
- **Phase 6**: FastAPI, HTMX, websockets

## Key Differentiators

1. **Privacy-First**: 100% local processing, no cloud
2. **State-of-the-Art AI**: Qwen2.5 > GPT-3.5 for file organization
3. **Multi-Modal**: Text + images + videos (audio coming)
4. **Open Source**: Transparent, auditable, customizable
5. **Quality**: 100% meaningful names vs generic patterns

## Constraints & Assumptions

### Technical Constraints
- Minimum 16 GB RAM (8 GB works but constrained)
- 10 GB storage for AI models
- Python 3.12+ required
- macOS/Linux (Windows Phase 2)

### Business Constraints
- Open source commitment (core features free)
- Privacy-first (no telemetry without opt-in)
- Single developer initially (community later)

### Assumptions
- Users want automated organization
- Privacy is a key differentiator
- Current file types cover 90% of use cases
- Ollama is stable enough for production

## Risk Mitigation

### Critical Risks
1. **Image Processing Speed** (HIGH)
   - **Mitigation**: Phase 2 optimization (model tuning, GPU support, batch processing)

2. **Low User Adoption** (MEDIUM)
   - **Mitigation**: Strong marketing, video tutorials, clear value proposition

3. **Memory Constraints** (MEDIUM)
   - **Mitigation**: Batch processing, smaller model options, streaming

4. **Ollama Instability** (LOW)
   - **Mitigation**: Restart procedures documented, fallback to llama.cpp

## Dependencies

### External
- **Ollama**: Model serving (can fallback to llama.cpp)
- **PyPI**: Distribution (can use GitHub)
- **GitHub**: Issue tracking, code hosting

### Internal
- Phase 2 depends on Phase 1 ✅
- Phase 3 depends on Phase 2
- Phases 4-6 depend on Phase 3

## Documentation

### Existing ✅
- README.md (comprehensive)
- BRD (20,000+ words)
- PROJECT_STATUS.md (detailed metrics)
- DEMO_COMPLETE.md (Week 1 summary)
- WEEK2_IMAGE_PROCESSING.md (Week 2 summary)
- REBUILD_PLAN.md (26-week plan)
- SOTA_2026_RESEARCH.md (research analysis)

### Needed 📅
- User installation guide (Phase 2)
- Video tutorials (Phase 2)
- Architecture diagrams (Phase 2)
- Contributing guide (Phase 2)
- API documentation (Phase 6)

## GitHub Issues

Epic issues created for tracking:
- #1: Phase 2 - Enhanced UX
- #2: Phase 3 - Feature Expansion
- #3: Phase 4 - Intelligence & Learning
- #4: Phase 5 - Architecture & Performance
- #5: Phase 6 - Web Interface & Plugin Ecosystem
- #6: Testing & Quality Assurance
- #7: Documentation & User Guides
- #8: Performance Optimization (Critical)

## Next Steps

**Immediate (Current Sprint)**:
1. Address critical performance issue (#8)
2. Begin Phase 2 planning
3. Set up automated testing (#6)
4. Create user installation guide (#7)

**Short Term (Phase 2)**:
1. Implement Copilot Mode
2. Build interactive TUI
3. Create cross-platform executables
4. Optimize image processing speed

**Long Term (Phases 3-6)**:
1. Expand file type support
2. Add intelligence features
3. Refactor to event-driven architecture
4. Build web interface

## Success Definition

File Organizer v2.0 will be considered successful when:
1. 1,000+ active users organizing files regularly
2. >95% quality score on file naming
3. >4.5/5 user satisfaction
4. Processing speed targets met (<10s text, <30s images)
5. Thriving open-source community
6. Recognized as the privacy-focused file organizer

---

**Status**: Phase 1 Complete, Phase 2 Planning
**Version**: 2.0.0-alpha.2
**Last Updated**: 2026-01-20
