# AI Model Configuration

## Supported Models

- `qwen2.5:3b-instruct-q4_K_M` — Default text model (~1.9 GB)
- `qwen2.5vl:7b-q4_K_M` — Default vision model (~6.0 GB)
- `faster-whisper` — Audio transcription (local, multi-language)

## Device Support

```python
from file_organizer.models.base import DeviceType

DeviceType.AUTO    # Automatic detection (recommended)
DeviceType.CPU     # CPU inference (universal)
DeviceType.CUDA    # NVIDIA GPU (fastest)
DeviceType.MPS     # Apple Silicon (fast)
DeviceType.METAL   # Apple Silicon (MLX)
```

---

