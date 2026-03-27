# AI Provider Setup Guide

Complete setup guide for File Organizer's AI provider support: 5 native providers plus 2 OpenAI-compatible services.

---

## Overview

File Organizer supports **5 native AI providers** for text analysis, plus **2 OpenAI-compatible services** (Groq, LM Studio) that use the `openai` provider with custom endpoints. Three of the native providers (Ollama, OpenAI, Claude) also support vision analysis; LLaMA.cpp and MLX are text-only for now.

**Native Providers:**
- **Ollama** (default)
- **OpenAI**
- **Claude** (Anthropic)
- **LLaMA.cpp**
- **MLX** (Apple Silicon only)

**OpenAI-Compatible Services:** (use `FO_PROVIDER=openai` with custom `FO_OPENAI_BASE_URL`)
- **Groq** - Fast cloud inference
- **LM Studio** - Local GUI model management

**Quick comparison:**

- **Local-only privacy**: Ollama, LLaMA.cpp, MLX, LM Studio
- **Cloud-based**: OpenAI, Claude, Groq
- **Best for beginners**: Ollama (default, zero config)
- **Best for Apple Silicon**: MLX or Ollama
- **Best for NVIDIA GPUs**: LLaMA.cpp or Ollama

---

## Provider Comparison

### Native Providers

| Provider | `FO_PROVIDER` Value | Local/Cloud | Cost | Setup Difficulty | GPU Required | Vision Support | Best For |
|----------|---------------------|-------------|------|------------------|--------------|----------------|----------|
| **Ollama** | `ollama` | Local | Free | Easy | No (CPU works) | ✅ Yes | Default choice, beginners, general use |
| **OpenAI** | `openai` | Cloud | Paid (API) | Easy | No | ✅ Yes | Production quality, vision tasks, cloud OK |
| **Claude** | `claude` | Cloud | Paid (API) | Easy | No | ✅ Yes | Strong reasoning, vision analysis, cloud OK |
| **LLaMA.cpp** | `llama_cpp` | Local | Free | Medium | No (CPU works) | ⏳ Phase 2 | Advanced users, GGUF models, offline use |
| **MLX** | `mlx` | Local | Free | Medium | Apple Silicon only | ⏳ Phase 3 | Mac users with M1/M2/M3 chips |

### OpenAI-Compatible Services

These services use `FO_PROVIDER=openai` with a custom `FO_OPENAI_BASE_URL`:

| Service | Local/Cloud | Cost | Setup Difficulty | Vision Support | Best For |
|---------|-------------|------|------------------|----------------|----------|
| **Groq** | Cloud | Free/Paid | Easy | ❌ Not yet | Fast inference, low latency |
| **LM Studio** | Local | Free | Medium | Varies | GUI model management, local control |

---

## Native Provider Setup Guides

### 1. Ollama (Default)

**Best for:** Beginners, local-first users, general purpose

Ollama is the default provider, installed with File Organizer. No additional dependencies required.

#### Installation

Ollama is included in the base installation:

```bash
pip install local-file-organizer
```

#### Setup

1. Install Ollama server from [ollama.com](https://ollama.com)
2. Pull the default models:

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

#### Configuration

No environment variables needed. Ollama is used by default.

Optionally, set the Ollama server URL (this is an Ollama-native
environment variable consumed by the Ollama client library, not part of
the `FO_*` configuration namespace):

```bash
export OLLAMA_HOST=http://localhost:11434
```

#### Model Selection

Edit your config file (run `file-organizer config show` to find its location):

```yaml
models:
  text_model: "qwen2.5:3b-instruct-q4_K_M"
  vision_model: "qwen2.5vl:7b-q4_K_M"
  framework: "ollama"
```

Or use the CLI:

```bash
file-organizer config edit --text-model "qwen2.5:3b-instruct-q4_K_M"
```

#### Verification

```bash
# Test text inference
echo "Test" > test.txt
file-organizer analyze test.txt

# Check Ollama status
ollama list
```

#### Known Limitations

- Requires Ollama server running (auto-starts on macOS/Linux)
- Models must be pulled before use
- Performance depends on available RAM (8GB minimum, 16GB recommended)

---

### 2. OpenAI

**Best for:** Cloud-based deployments, production quality, vision tasks

OpenAI provides GPT-4 and other models via their hosted API.

#### Installation

Install the cloud extra dependency:

```bash
# From PyPI
pip install "local-file-organizer[cloud]"

# From source
pip install -e ".[cloud]"
```

#### Setup

1. Get an API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Set environment variables:

```bash
export FO_PROVIDER=openai
export FO_OPENAI_API_KEY=sk-...
export FO_OPENAI_MODEL=gpt-4o-mini  # or gpt-4o, gpt-4-turbo
```

#### Configuration

Environment variables (highest priority):

| Variable | Description | Default |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `openai` | `ollama` |
| `FO_OPENAI_API_KEY` | OpenAI API key | Required when `FO_OPENAI_BASE_URL` is not set. The OpenAI SDK also reads `OPENAI_API_KEY` natively, so either variable works. |
| `FO_OPENAI_BASE_URL` | Custom endpoint URL | `https://api.openai.com/v1` |
| `FO_OPENAI_MODEL` | Text model name | `gpt-4o-mini` |
| `FO_OPENAI_VISION_MODEL` | Vision model name | Falls back to `FO_OPENAI_MODEL` |

#### Model Selection

Recommended models:

- **Text + Vision**: `gpt-4o` (best quality), `gpt-4o-mini` (cost-effective), `gpt-4-turbo`
- **Text-only**: `gpt-3.5-turbo`

```bash
export FO_OPENAI_MODEL=gpt-4o
```

#### Verification

```bash
# Test with environment variables set
FO_PROVIDER=openai \
FO_OPENAI_API_KEY=sk-... \
FO_OPENAI_MODEL=gpt-4o-mini \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- Requires internet connection
- API costs apply (see OpenAI pricing)
- File content is sent to OpenAI's servers
- Rate limits apply based on your plan

---

### 3. Claude (Anthropic)

**Best for:** Strong reasoning tasks, vision analysis, cloud deployments

Claude provides state-of-the-art reasoning and vision capabilities via Anthropic's API.

#### Installation

Install the Claude extra dependency:

```bash
# From PyPI
pip install "local-file-organizer[claude]"

# From source
pip install -e ".[claude]"
```

#### Setup

1. Get an API key from [console.anthropic.com](https://console.anthropic.com)
2. Set environment variables:

```bash
export FO_PROVIDER=claude
export FO_CLAUDE_API_KEY=sk-ant-...
export FO_CLAUDE_MODEL=claude-3-5-sonnet-20241022
```

#### Configuration

Environment variables (highest priority):

| Variable | Description | Default |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `claude` | `ollama` |
| `FO_CLAUDE_API_KEY` | Anthropic API key | Falls back to `ANTHROPIC_API_KEY` |
| `FO_CLAUDE_MODEL` | Text model name | `claude-3-5-sonnet-20241022` |
| `FO_CLAUDE_VISION_MODEL` | Vision model name | Falls back to `FO_CLAUDE_MODEL` |

#### Model Selection

Recommended models:

- **Claude 3.5 Sonnet**: `claude-3-5-sonnet-20241022` (best balance)
- **Claude 3 Opus**: `claude-3-opus-20240229` (highest quality)
- **Claude 3 Haiku**: `claude-3-haiku-20240307` (fastest, cost-effective)

```bash
export FO_CLAUDE_MODEL=claude-3-5-sonnet-20241022
```

Check [Anthropic's model documentation](https://docs.anthropic.com/en/docs/about-claude/models) for the latest available models.

#### Verification

```bash
# Test with environment variables set
FO_PROVIDER=claude \
FO_CLAUDE_API_KEY=sk-ant-... \
FO_CLAUDE_MODEL=claude-3-5-sonnet-20241022 \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- Requires internet connection
- API costs apply (see Anthropic pricing)
- File content (including images) is sent to Anthropic's servers
- Rate limits apply based on your plan

---

### 4. LLaMA.cpp

**Best for:** Advanced users, offline use, direct GGUF model loading

LLaMA.cpp provides direct inference from GGUF model files without requiring a server.

#### Installation

Install the LLaMA.cpp extra dependency:

```bash
# From PyPI
pip install "local-file-organizer[llama]"

# From source
pip install -e ".[llama]"
```

#### Setup

1. Download a GGUF model file (e.g., from [Hugging Face](https://huggingface.co/models?search=gguf))
2. Set environment variables:

```bash
export FO_PROVIDER=llama_cpp
export FO_LLAMA_CPP_MODEL_PATH=/path/to/model.gguf
```

Optional GPU acceleration:

```bash
# Set number of layers to offload to GPU (0 = CPU only)
export FO_LLAMA_CPP_N_GPU_LAYERS=35  # Adjust based on your GPU memory
```

#### Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `llama_cpp` | `ollama` |
| `FO_LLAMA_CPP_MODEL_PATH` | Path to .gguf file | Required |
| `FO_LLAMA_CPP_N_GPU_LAYERS` | Layers to offload to GPU | Not set (CPU only; set higher to offload layers to GPU) |

#### Model Selection

Download GGUF models from Hugging Face. Popular choices:

- **Qwen 2.5 3B**: Recommended for balance of speed and quality
- **Llama 3 8B**: Good general-purpose model
- **Mistral 7B**: Strong reasoning capabilities

Look for quantized versions (Q4_K_M, Q5_K_M) for better performance.

#### Verification

```bash
# Test with environment variables set
FO_PROVIDER=llama_cpp \
FO_LLAMA_CPP_MODEL_PATH=/path/to/model.gguf \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- Text-only support (vision coming in Phase 2)
- Requires manual GGUF model download
- Performance varies by quantization level
- GPU layers must be tuned for your hardware

---

### 5. MLX

**Best for:** Mac users with Apple Silicon (M1/M2/M3)

MLX provides optimized inference on Apple Silicon using Apple's MLX framework.

#### Installation

**macOS with Apple Silicon only:**

```bash
# From PyPI
pip install "local-file-organizer[mlx]"

# From source
pip install -e ".[mlx]"
```

#### Setup

1. Set the model path (Hugging Face repo or local path):

```bash
export FO_PROVIDER=mlx
export FO_MLX_MODEL_PATH=mlx-community/Qwen2.5-3B-Instruct-4bit
```

The model will be downloaded automatically from Hugging Face on first use.

#### Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `mlx` | `ollama` |
| `FO_MLX_MODEL_PATH` | Hugging Face repo or local path | Required |

#### Model Selection

Popular MLX-optimized models from [mlx-community](https://huggingface.co/mlx-community):

- **Qwen2.5-3B-Instruct-4bit**: Recommended default
- **Llama-3-8B-Instruct-4bit**: Good general purpose
- **Mistral-7B-Instruct-v0.3-4bit**: Strong reasoning

```bash
export FO_MLX_MODEL_PATH=mlx-community/Qwen2.5-3B-Instruct-4bit
```

#### Verification

```bash
# Test with environment variables set
FO_PROVIDER=mlx \
FO_MLX_MODEL_PATH=mlx-community/Qwen2.5-3B-Instruct-4bit \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- **macOS with Apple Silicon only** (M1/M2/M3 chips)
- Text-only support (vision coming in Phase 3)
- Requires unified memory (8GB minimum, 16GB recommended)
- Model is downloaded on first use

---

## OpenAI-Compatible Service Setup

The following services are **not separate providers** in the codebase. They use the `openai` provider (`FO_PROVIDER=openai`) with a custom API endpoint configured via `FO_OPENAI_BASE_URL`.

### 6. Groq

**Best for:** Fast cloud inference, OpenAI-compatible API

**Important:** Groq is not a separate provider. It uses `FO_PROVIDER=openai` with Groq's API endpoint.

Groq provides extremely fast inference through their LPU infrastructure.

#### Installation

Install the cloud extra dependency (same as OpenAI):

```bash
# From PyPI
pip install "local-file-organizer[cloud]"

# From source
pip install -e ".[cloud]"
```

#### Setup

1. Get an API key from [console.groq.com](https://console.groq.com)
2. Set environment variables to use Groq's OpenAI-compatible endpoint:

```bash
export FO_PROVIDER=openai
export FO_OPENAI_API_KEY=gsk_...  # Groq API key
export FO_OPENAI_BASE_URL=https://api.groq.com/openai/v1
export FO_OPENAI_MODEL=llama-3.1-70b-versatile
```

#### Configuration

Use OpenAI environment variables with Groq-specific values:

| Variable | Description | Example |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `openai` | `openai` |
| `FO_OPENAI_API_KEY` | Groq API key | `gsk_...` |
| `FO_OPENAI_BASE_URL` | Groq endpoint | `https://api.groq.com/openai/v1` |
| `FO_OPENAI_MODEL` | Model name | `llama-3.1-70b-versatile` |

#### Model Selection

Available Groq models:

- **llama-3.1-70b-versatile**: Best quality
- **llama-3.1-8b-instant**: Fastest
- **mixtral-8x7b-32768**: Long context
- **gemma-7b-it**: Efficient

Model availability changes frequently. See [Groq documentation](https://console.groq.com/docs/models) for current models.

#### Verification

```bash
# Test with Groq
FO_PROVIDER=openai \
FO_OPENAI_API_KEY=gsk_... \
FO_OPENAI_BASE_URL=https://api.groq.com/openai/v1 \
FO_OPENAI_MODEL=llama-3.1-70b-versatile \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- Cloud-based (requires internet)
- Free tier has rate limits
- File content is sent to Groq's servers
- Vision models not yet supported

---

### 7. LM Studio

**Best for:** Local inference with GUI model management

**Important:** LM Studio is not a separate provider. It uses `FO_PROVIDER=openai` with LM Studio's local API endpoint.

LM Studio provides a user-friendly GUI for downloading and running models locally with an OpenAI-compatible API.

#### Installation

1. Install LM Studio from [lmstudio.ai](https://lmstudio.ai)
2. Install the cloud extra dependency for File Organizer:

```bash
# From PyPI
pip install "local-file-organizer[cloud]"

# From source
pip install -e ".[cloud]"
```

#### Setup

1. Open LM Studio and download a model
2. Start the local server (Local Server tab in LM Studio)
3. Note the server URL (default: `http://localhost:1234/v1`)
4. Set environment variables:

```bash
export FO_PROVIDER=openai
export FO_OPENAI_BASE_URL=http://localhost:1234/v1
export FO_OPENAI_MODEL=your-loaded-model-name  # Check LM Studio UI
```

No API key required for local LM Studio server.

#### Configuration

Use OpenAI environment variables with LM Studio endpoint:

| Variable | Description | Example |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `openai` | `openai` |
| `FO_OPENAI_BASE_URL` | LM Studio local endpoint | `http://localhost:1234/v1` |
| `FO_OPENAI_MODEL` | Model name from LM Studio | Varies by loaded model |
| `FO_OPENAI_API_KEY` | Not required for local server | (omit) |

#### Model Selection

1. In LM Studio, browse and download models
2. Load a model in the Local Server tab
3. Use the model name shown in LM Studio UI

Popular model choices:

- **Qwen 2.5 3B**: Fast and efficient
- **Llama 3 8B**: Good general purpose
- **Mistral 7B**: Strong reasoning

#### Verification

```bash
# Start LM Studio server first, then test
FO_PROVIDER=openai \
FO_OPENAI_BASE_URL=http://localhost:1234/v1 \
FO_OPENAI_MODEL=your-model-name \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- Requires LM Studio application running
- Model name must match exactly what's loaded in LM Studio
- Performance depends on your hardware
- Must manually start server before use

---

## Switching Providers

### Via Environment Variables

The fastest way to switch providers:

```bash
# Switch to OpenAI
export FO_PROVIDER=openai
export FO_OPENAI_API_KEY=sk-...

# Switch to Claude
export FO_PROVIDER=claude
export FO_CLAUDE_API_KEY=sk-ant-...

# Switch back to Ollama (default)
unset FO_PROVIDER
```

### Via Configuration File

Edit your config file (run `file-organizer config show` to find its location):

```yaml
models:
  framework: "ollama"  # or "llama_cpp", "mlx"
  text_model: "qwen2.5:3b-instruct-q4_K_M"
  vision_model: "qwen2.5vl:7b-q4_K_M"
```

Note: The config file `framework` field supports `ollama`, `llama_cpp`, and `mlx`.
For `openai` and `claude` providers, use the `FO_PROVIDER` environment variable instead.

### Priority Order

Configuration priority (highest wins):

1. Explicit `ModelConfig` parameters passed to `FileOrganizer` (programmatic use)
2. Environment variables (`FO_PROVIDER`, `FO_OPENAI_*`, etc.)
3. Configuration profile (resolved via `platformdirs.user_config_dir`)
4. Hardcoded defaults (Ollama)

---

## Troubleshooting

### Provider Not Found Error

```text
Unknown provider 'openai'. Registered providers: ['ollama'].
```

**Solution:** Install the required extra dependency:

```bash
pip install "local-file-organizer[cloud]"  # For OpenAI/Groq/LM Studio
pip install "local-file-organizer[claude]"  # For Claude
pip install "local-file-organizer[llama]"   # For LLaMA.cpp
pip install "local-file-organizer[mlx]"     # For MLX
```

### API Key Not Set Warning

```text
FO_PROVIDER=openai but neither FO_OPENAI_API_KEY nor FO_OPENAI_BASE_URL is set
(and OPENAI_API_KEY is also absent).  Requests will likely fail.
For local providers (LM Studio, Ollama OpenAI-compat) set FO_OPENAI_BASE_URL.
```

**Solution:** Set the required environment variables for your provider (see provider-specific sections above).
If you have the standard `OPENAI_API_KEY` env var set, this warning is suppressed automatically.

### Model Path Not Set (LLaMA.cpp / MLX)

```text
FO_PROVIDER=llama_cpp but FO_LLAMA_CPP_MODEL_PATH is not set
```

**Solution:** Set the model path environment variable:

```bash
export FO_LLAMA_CPP_MODEL_PATH=/path/to/model.gguf
# or
export FO_MLX_MODEL_PATH=mlx-community/Qwen2.5-3B-Instruct-4bit
```

### Connection Errors

**Ollama:**

```bash
# Check if Ollama is running
ollama list

# Restart Ollama
ollama serve
```

**LM Studio:**

- Ensure LM Studio Local Server is running
- Check the server URL matches (default: `http://localhost:1234/v1`)
- Verify a model is loaded in LM Studio

### Vision Not Supported

Some providers only support text inference currently:

- **LLaMA.cpp**: Vision support coming in Phase 2
- **MLX**: Vision support coming in Phase 3
- **Groq**: Check Groq docs for vision model availability

Image files will fall back to extension-based organization.

---

## Related Documentation

- [Configuration Reference](../CONFIGURATION.md) - Full configuration options
- [Getting Started](../getting-started.md) - Installation and setup
- [Model Configuration](models.md) - Model-specific settings
- [CLI Reference](../cli-reference.md) - Command-line usage

---

## See Also

- [Ollama Documentation](https://ollama.com/docs)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Anthropic Claude Documentation](https://docs.anthropic.com/claude/docs)
- [llama.cpp Repository](https://github.com/ggerganov/llama.cpp)
- [MLX Examples](https://github.com/ml-explore/mlx-examples)
- [Groq Documentation](https://console.groq.com/docs)
- [LM Studio](https://lmstudio.ai)
