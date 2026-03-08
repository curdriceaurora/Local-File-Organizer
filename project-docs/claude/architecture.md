# System Architecture

## Core Principles
1. **Privacy-First**: Zero cloud dependencies.
2. **Strategy Pattern**: Different processors for different file types.
3. **Service Layer**: Business logic separated from AI models.

## Data Flow
Input File -> FileOrganizer -> Type Detection
    |-> Text: TextProcessor -> TextModel (Qwen 2.5 3B)
    |-> Image: VisionProcessor -> VisionModel (Qwen 2.5-VL)
    |-> Audio: AudioModel -> Whisper (Phase 3)
    V
PatternAnalyzer -> SmartSuggestions -> Intelligence -> Output

## Key Models
- **BaseModel**: Abstract interface (`models/base.py`)
- **TextModel**: Ollama wrapper (`models/text_model.py`)
- **VisionModel**: Multi-modal wrapper (`models/vision_model.py`)

## Model Configuration

@dataclass
class ModelConfig:
    name: str                      # Model identifier
    model_type: ModelType          # TEXT, VISION, AUDIO, VIDEO
    quantization: str = "q4_k_m"   # Quantization level
    device: DeviceType = AUTO      # CPU, CUDA, MPS, METAL
    framework: str = "ollama"      # Inference framework
