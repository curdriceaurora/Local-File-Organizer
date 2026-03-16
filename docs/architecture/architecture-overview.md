# Architecture Overview

## Design Principles

1. **Privacy-First**: 100% local processing, zero cloud dependencies
2. **Model Abstraction**: Abstract AI model interface for framework flexibility
3. **Service Layer Pattern**: Business logic separate from models
4. **Strategy Pattern**: Different processors for different file types
5. **Event-Driven**: Event bus for loosely-coupled inter-component communication
6. **Plugin Architecture**: Extensible via plugin marketplace
7. **Type Safety**: Full type hints with strict mypy configuration
8. **Resource Management**: Context managers for automatic cleanup

## Core Components

| Component | Purpose | Location | Status |
|-----------|---------|----------|--------|
| **BaseModel** | Abstract AI model interface | `models/base.py` | ✅ Core |
| **ModelManager** | Model lifecycle + hot-swap | `models/model_manager.py` | ✅ Active |
| **TextModel** | Ollama text generation | `models/text_model.py` | ✅ Active |
| **VisionModel** | Vision-language wrapper | `models/vision_model.py` | ✅ Active |
| **AudioModel** | Audio transcription | `models/audio_model.py` | ✅ Active |
| **DomainRegistries** | Text/Vision/Audio model metadata | `models/{text,vision,audio}_registry.py` | ✅ Active |
| **PipelineStage** | Composable processing protocol | `interfaces/pipeline.py` | ✅ Active |
| **Pipeline Stages** | Preprocessor/Analyzer/Postprocessor/Writer | `pipeline/stages/` | ✅ Active |
| **TextProcessor** | Text file pipeline | `services/text_processor.py` | ✅ Active |
| **VisionProcessor** | Image/video pipeline | `services/vision_processor.py` | ✅ Active |
| **FileOrganizer** | Main orchestrator | `src/file_organizer/core/organizer.py` | ✅ Active |
| **PatternAnalyzer** | Naming pattern detection | `services/pattern_analyzer.py` | ✅ Active |
| **SuggestionEngine** | Placement suggestions | `services/smart_suggestions.py` | ✅ Active |
| **Intelligence** | User preference learning | `services/intelligence/` | ✅ Active |
| **Deduplication** | Duplicate detection | `services/deduplication/` | ✅ Active |
| **OperationHistory** | Operation tracking | `history/` | ✅ Active |
| **UndoManager** | Undo/redo system | `undo/` | ✅ Active |
| **EventBus** | Inter-component events | `events/` | ✅ Active |
| **Daemon** | Background file watching | `daemon/` | ✅ Active |
| **API Server** | FastAPI REST endpoints | `api/` | ✅ Active |
| **Web UI** | Browser-based interface | `web/` | ✅ Active |
| **TUI** | Textual terminal UI | `tui/` | ✅ Active |
| **PluginSystem** | Extension marketplace | `plugins/` | ✅ Active |
| **Methodologies** | PARA, Johnny Decimal | `methodologies/` | ✅ Active |

## Data Flow

```text
Input File → FileOrganizer → ParallelProcessor (current default path)

Stage-Based Pipeline via PipelineOrchestrator (composable, double-buffered):
  PreprocessorStage → File validation + metadata extraction  (prefetched in I/O thread pool; default prefetch_stages=1)
  AnalyzerStage → FileRouter → Processor (Text/Vision/Audio) (runs on calling thread by default)
  PostprocessorStage → Destination path computation          (runs on calling thread by default)
  WriterStage → File copy/move (skipped in dry-run)         (runs on calling thread by default)

Legacy Pipeline (backward compatible):
  File Type Detection → TextProcessor / VisionProcessor / AudioModel
  → PatternAnalyzer → SuggestionEngine

All Paths → Intelligence Services → User Preference Learning
EventBus → Daemon / Web UI / TUI notifications

Final Output: Organized files + Operation history
```

---
