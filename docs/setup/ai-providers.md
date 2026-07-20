# AI Provider Setup Guide

This guide shows how to set up the AI providers for File Organizer. File Organizer has 5 native providers. It also has 2 OpenAI-compatible services.

---

## Overview

File Organizer supports 5 native AI providers for text analysis. It supports 2 OpenAI-compatible services (Groq and LM Studio). These services use the `openai` provider with custom endpoints. Ollama, OpenAI, and Claude support vision analysis. LLaMA.cpp and MLX only support text analysis.

## Select a provider

If you do not know which provider to select, use Ollama first. Ollama is the local default provider. It needs the least setup.

Select a different provider if you need:

- Cloud models (OpenAI, Claude, Groq)
- A local OpenAI-compatible endpoint (LM Studio)
- Advanced local model runtimes (LLaMA.cpp, MLX)

Read [Getting Started](../getting-started.md) for initial setup instructions.

**Native Providers:**
- **Ollama** (default)
- **OpenAI**
- **Claude** (Anthropic)
- **LLaMA.cpp**
- **MLX** (Apple Silicon only)

**OpenAI-Compatible Services:**
Set `FO_PROVIDER=openai`. Set a custom `FO_OPENAI_BASE_URL`.
- **Groq** - Fast cloud inference
- **LM Studio** - Local GUI model management

**Comparison:**

- **Local privacy**: Ollama, LLaMA.cpp, MLX, LM Studio
- **Cloud models**: OpenAI, Claude, Groq
- **Best for beginners**: Ollama
- **Best for Apple Silicon**: MLX or Ollama
- **Best for NVIDIA GPUs**: LLaMA.cpp or Ollama

---

## Provider Comparison

### Native Providers

| Provider | `FO_PROVIDER` Value | Local or Cloud | Cost | Setup | GPU | Vision | Best For |
|----------|---------------------|----------------|------|-------|-----|--------|----------|
| **Ollama** | `ollama` | Local | Free | Easy | Optional | Yes | Beginners |
| **OpenAI** | `openai` | Cloud | Paid | Easy | No | Yes | Production tasks |
| **Claude** | `claude` | Cloud | Paid | Easy | No | Yes | Reasoning tasks |
| **LLaMA.cpp** | `llama_cpp` | Local | Free | Medium | Optional | No | Advanced users |
| **MLX** | `mlx` | Local | Free | Medium | Apple Silicon | No | Mac users |

### OpenAI-Compatible Services

Set `FO_PROVIDER=openai`. Set a custom `FO_OPENAI_BASE_URL`.

| Service | Local or Cloud | Cost | Setup | Vision | Best For |
|---------|----------------|------|-------|--------|----------|
| **Groq** | Cloud | Free or Paid | Easy | Varies | Fast inference |
| **LM Studio** | Local | Free | Medium | Varies | Local control |

---

## Native Provider Setup Guides

### 1. Ollama (Default)

**Best for:** Beginners and local users.

Ollama is the default provider. File Organizer installs it automatically. You do not need extra dependencies.

#### Installation

The base installation includes Ollama.

```bash
pip install local-file-organizer
```

#### Setup

1. Install the Ollama server from [ollama.com](https://ollama.com).
2. Download the default models.

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
```

#### Configuration

You do not need environment variables. File Organizer uses Ollama by default.

You can set the Ollama server URL. This is an optional step.

```bash
export OLLAMA_HOST=http://localhost:11434
```

#### Model Selection

Change your configuration file. Run `file-organizer config show` to find the file location.

```yaml
models:
  text_model: "qwen2.5:3b-instruct-q4_K_M"
  vision_model: "qwen2.5vl:7b-q4_K_M"
  framework: "ollama"
```

You can also use the CLI.

```bash
file-organizer config edit --text-model "qwen2.5:3b-instruct-q4_K_M"
```

#### Verification

```bash
# Test the text inference
echo "Test" > test.txt
file-organizer analyze test.txt

# Examine the Ollama status
ollama list
```

#### Known Limitations

- You must run the Ollama server.
- You must download models before you use them.
- You need 8 GB of RAM minimum. We recommend 16 GB of RAM.

---

### 2. OpenAI

**Best for:** Cloud deployments and vision tasks.

OpenAI gives you GPT-4 and other models through an API.

#### Installation

Install the cloud dependency.

```bash
# PyPI
pip install "local-file-organizer[cloud]"

# Source
pip install -e ".[cloud]"
```

#### Setup

1. Get an API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
2. Set the environment variables.

```bash
export FO_PROVIDER=openai
export FO_OPENAI_API_KEY=sk-...
export FO_OPENAI_MODEL=gpt-4o-mini
```

#### Configuration

Set these environment variables.

| Variable | Description | Default |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `openai` | `ollama` |
| `FO_OPENAI_API_KEY` | OpenAI API key | Required |
| `FO_OPENAI_BASE_URL` | Custom endpoint URL | `https://api.openai.com/v1` |
| `FO_OPENAI_MODEL` | Text model name | `gpt-4o-mini` |
| `FO_OPENAI_VISION_MODEL` | Vision model name | `FO_OPENAI_MODEL` |

#### Model Selection

We recommend these models:

- **Text and Vision**: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`
- **Text only**: `gpt-3.5-turbo`

```bash
export FO_OPENAI_MODEL=gpt-4o
```

#### Verification

```bash
FO_PROVIDER=openai \
FO_OPENAI_API_KEY=sk-... \
FO_OPENAI_MODEL=gpt-4o-mini \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- You need an internet connection.
- You must pay API costs.
- The provider sends file data to OpenAI servers.

---

### 3. Claude (Anthropic)

**Best for:** Reasoning tasks and vision analysis.

Claude gives you reasoning and vision models through an API.

#### Installation

Install the Claude dependency.

```bash
# PyPI
pip install "local-file-organizer[claude]"

# Source
pip install -e ".[claude]"
```

#### Setup

1. Get an API key from [console.anthropic.com](https://console.anthropic.com).
2. Set the environment variables.

```bash
export FO_PROVIDER=claude
export FO_CLAUDE_API_KEY=sk-ant-...
export FO_CLAUDE_MODEL=claude-3-5-sonnet-20241022
```

#### Configuration

Set these environment variables.

| Variable | Description | Default |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `claude` | `ollama` |
| `FO_CLAUDE_API_KEY` | Anthropic API key | Required |
| `FO_CLAUDE_MODEL` | Text model name | `claude-3-5-sonnet-20241022` |
| `FO_CLAUDE_VISION_MODEL` | Vision model name | `FO_CLAUDE_MODEL` |

#### Model Selection

We recommend these models:

- **Claude 3.5 Sonnet**: `claude-3-5-sonnet-20241022`
- **Claude 3 Opus**: `claude-3-opus-20240229`
- **Claude 3 Haiku**: `claude-3-haiku-20240307`

```bash
export FO_CLAUDE_MODEL=claude-3-5-sonnet-20241022
```

#### Verification

```bash
FO_PROVIDER=claude \
FO_CLAUDE_API_KEY=sk-ant-... \
FO_CLAUDE_MODEL=claude-3-5-sonnet-20241022 \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- You need an internet connection.
- You must pay API costs.
- The provider sends file data to Anthropic servers.

---

### 4. LLaMA.cpp

**Best for:** Advanced users and offline work.

LLaMA.cpp reads GGUF model files directly. You do not need a server.

#### Installation

Install the LLaMA.cpp dependency.

```bash
# PyPI
pip install "local-file-organizer[llama]"

# Source
pip install -e ".[llama]"
```

#### Setup

1. Download a GGUF model file.
2. Set the environment variables.

```bash
export FO_PROVIDER=llama_cpp
export FO_LLAMA_CPP_MODEL_PATH=/path/to/model.gguf
```

You can set optional GPU acceleration.

```bash
export FO_LLAMA_CPP_N_GPU_LAYERS=35
```

#### Configuration

Set these environment variables.

| Variable | Description | Default |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `llama_cpp` | `ollama` |
| `FO_LLAMA_CPP_MODEL_PATH` | Path to the .gguf file | Required |
| `FO_LLAMA_CPP_N_GPU_LAYERS` | Number of GPU layers | CPU only |

#### Model Selection

Download GGUF models. We recommend these models:

- **Qwen 2.5 3B**: Good speed and quality.
- **Llama 3 8B**: Good general model.
- **Mistral 7B**: Good reasoning capabilities.

#### Verification

```bash
FO_PROVIDER=llama_cpp \
FO_LLAMA_CPP_MODEL_PATH=/path/to/model.gguf \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- The provider supports text only.
- You must download GGUF files manually.

---

### 5. MLX

**Best for:** Mac users with Apple Silicon.

MLX runs models efficiently on Apple Silicon.

#### Installation

This provider operates on macOS with Apple Silicon only.

```bash
# PyPI
pip install "local-file-organizer[mlx]"

# Source
pip install -e ".[mlx]"
```

#### Setup

Set the model path.

```bash
export FO_PROVIDER=mlx
export FO_MLX_MODEL_PATH=mlx-community/Qwen2.5-3B-Instruct-4bit
```

File Organizer downloads the model automatically.

#### Configuration

Set these environment variables.

| Variable | Description | Default |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `mlx` | `ollama` |
| `FO_MLX_MODEL_PATH` | Hugging Face path | Required |

#### Model Selection

We recommend these models:

- **Qwen2.5-3B-Instruct-4bit**: Recommended default.
- **Llama-3-8B-Instruct-4bit**: Good general model.
- **Mistral-7B-Instruct-v0.3-4bit**: Good reasoning.

#### Verification

```bash
FO_PROVIDER=mlx \
FO_MLX_MODEL_PATH=mlx-community/Qwen2.5-3B-Instruct-4bit \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- The provider operates on macOS with Apple Silicon only.
- The provider supports text only.
- You need 8 GB of RAM minimum.

---

## OpenAI-Compatible Service Setup

These services use the `openai` provider. You must set `FO_PROVIDER=openai` and `FO_OPENAI_BASE_URL`.

### 6. Groq

**Best for:** Fast cloud inference.

Groq gives you fast inference through LPU hardware.

#### Installation

Install the cloud dependency.

```bash
# PyPI
pip install "local-file-organizer[cloud]"

# Source
pip install -e ".[cloud]"
```

#### Setup

1. Get an API key from [console.groq.com](https://console.groq.com).
2. Set the environment variables.

```bash
export FO_PROVIDER=openai
export FO_OPENAI_API_KEY=gsk_...
export FO_OPENAI_BASE_URL=https://api.groq.com/openai/v1
export FO_OPENAI_MODEL=llama-3.1-70b-versatile
```

#### Configuration

Set these environment variables.

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

#### Verification

```bash
FO_PROVIDER=openai \
FO_OPENAI_API_KEY=gsk_... \
FO_OPENAI_BASE_URL=https://api.groq.com/openai/v1 \
FO_OPENAI_MODEL=llama-3.1-70b-versatile \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- You need an internet connection.
- The free plan has rate limits.
- The provider sends file data to Groq servers.
- The provider does not support vision models.

---

### 7. LM Studio

**Best for:** Local inference and GUI management.

LM Studio gives you a GUI for local models.

#### Installation

1. Install LM Studio from [lmstudio.ai](https://lmstudio.ai).
2. Install the cloud dependency.

```bash
# PyPI
pip install "local-file-organizer[cloud]"

# Source
pip install -e ".[cloud]"
```

#### Setup

1. Download a model in LM Studio.
2. Start the local server in LM Studio.
3. Read the server URL.
4. Set the environment variables.

```bash
export FO_PROVIDER=openai
export FO_OPENAI_BASE_URL=http://localhost:1234/v1
export FO_OPENAI_MODEL=your-model-name
```

#### Configuration

Set these environment variables.

| Variable | Description | Example |
|----------|-------------|---------|
| `FO_PROVIDER` | Set to `openai` | `openai` |
| `FO_OPENAI_BASE_URL` | LM Studio endpoint | `http://localhost:1234/v1` |
| `FO_OPENAI_MODEL` | Model name | Varies |

#### Verification

```bash
FO_PROVIDER=openai \
FO_OPENAI_BASE_URL=http://localhost:1234/v1 \
FO_OPENAI_MODEL=your-model-name \
file-organizer analyze ~/Downloads
```

#### Known Limitations

- You must run the LM Studio application.
- You must write the exact model name.

---

## Switch Providers

### Use Environment Variables

Use environment variables to switch providers quickly.

```bash
# Switch to OpenAI
export FO_PROVIDER=openai
export FO_OPENAI_API_KEY=sk-...

# Switch to Claude
export FO_PROVIDER=claude
export FO_CLAUDE_API_KEY=sk-ant-...

# Switch to Ollama
unset FO_PROVIDER
```

### Use Configuration File

Change your configuration file.

```yaml
models:
  framework: "ollama"
  text_model: "qwen2.5:3b-instruct-q4_K_M"
  vision_model: "qwen2.5vl:7b-q4_K_M"
```

### Priority Order

File Organizer uses this priority order:

1. Programmatic parameters
2. Environment variables
3. Configuration profile
4. Default values

---

## Troubleshooting

### Provider Not Found

```text
Unknown provider 'openai'.
```

**Solution:** Install the correct dependency.

```bash
pip install "local-file-organizer[cloud]"
```

### API Key Not Set

```text
FO_PROVIDER=openai but neither FO_OPENAI_API_KEY nor FO_OPENAI_BASE_URL is set.
```

**Solution:** Set the correct environment variables.

### Model Path Not Set

```text
FO_PROVIDER=llama_cpp but FO_LLAMA_CPP_MODEL_PATH is not set.
```

**Solution:** Set the model path variable.

```bash
export FO_LLAMA_CPP_MODEL_PATH=/path/to/model.gguf
```

### Connection Errors

**Ollama:**

```bash
ollama list
ollama serve
```

**LM Studio:**

- Start the LM Studio server.
- Verify the server URL.
- Verify the model name.

### Vision Not Supported

Some providers do not support vision models.

- **LLaMA.cpp**: No vision support.
- **MLX**: No vision support.
- **Groq**: No vision support.

File Organizer uses file extensions for images.

---

## Related Documentation

- [Configuration Reference](../CONFIGURATION.md)
- [Getting Started](../getting-started.md)
- [Model Configuration](models.md)
- [CLI Reference](../cli-reference.md)
