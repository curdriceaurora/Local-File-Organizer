# AI Model Configuration

## Defaults

- Text model: `qwen2.5:3b-instruct-q4_K_M`
- Vision model: `qwen2.5vl:7b-q4_K_M`
- Default provider mode: `ollama`

## Provider-driven model settings

Model names can come from:

1. Environment provider settings (when `FO_PROVIDER` is set)
2. Saved config profile (`FO_PROFILE` / `file-organizer config ...`)
3. Built-in defaults

See [AI Provider Setup](ai-providers.md) for provider-specific variables and examples.

## Config profile model fields

```yaml
models:
  text_model: "qwen2.5:3b-instruct-q4_K_M"
  vision_model: "qwen2.5vl:7b-q4_K_M"
  temperature: 0.5
  max_tokens: 3000
  device: "auto"     # auto, cpu, cuda, mps, metal
  framework: "ollama"  # ollama, llama_cpp, mlx
```

## Device support

```python
from file_organizer.models.base import DeviceType

DeviceType.AUTO
DeviceType.CPU
DeviceType.CUDA
DeviceType.MPS
DeviceType.METAL
```
