# File Organizer Configuration Guide

This page documents core app configuration (profiles, model/provider behavior, and paths).

For API/server-only runtime variables, see [Admin Configuration](admin/configuration.md).

## Where configuration is stored

`ConfigManager` persists profile data to `config.yaml` under the platform config directory.

- macOS: `~/Library/Application Support/file-organizer/config.yaml`
- Linux: `~/.config/file-organizer/config.yaml` (or `$XDG_CONFIG_HOME/file-organizer/config.yaml`)
- Windows: `%APPDATA%/file-organizer/config.yaml`

## Profile structure

`config.yaml` stores named profiles under a top-level `profiles` map:

```yaml
profiles:
  default:
    profile_name: default
    version: "1.0"
    default_methodology: none
    setup_completed: false
    models:
      text_model: qwen2.5:3b-instruct-q4_K_M
      vision_model: qwen2.5vl:7b-q4_K_M
      temperature: 0.5
      max_tokens: 3000
      device: auto
      framework: ollama
```

## CLI profile management

```bash
# Show default profile
file-organizer config show

# Show named profile
file-organizer config show --profile work

# List profiles
file-organizer config list

# Edit profile values
file-organizer config edit --profile work --text-model "qwen2.5:3b-instruct-q4_K_M"
file-organizer config edit --profile work --temperature 0.7
file-organizer config edit --profile work --methodology para
```

## Model/provider precedence

Model configs are resolved in this order:

1. Explicit `ModelConfig` parameters passed to `FileOrganizer`.
2. Environment variables (`FO_PROVIDER`, `FO_OPENAI_*`, `FO_LLAMA_CPP_*`, `FO_MLX_*`, `FO_CLAUDE_*`).
3. Profile config loaded from `FO_PROFILE` (or `default`).
4. Built-in defaults.

## Provider environment variables

| Variable | Description | Notes |
|---|---|---|
| `FO_PROVIDER` | Provider mode: `ollama`, `openai`, `llama_cpp`, `mlx`, `claude` | Set this to activate env-based provider override |
| `FO_OPENAI_API_KEY` | OpenAI-compatible API key | Preferred for consistency |
| `FO_OPENAI_BASE_URL` | OpenAI-compatible endpoint URL | Use for LM Studio, vLLM, Groq, etc. |
| `FO_OPENAI_MODEL` | OpenAI-compatible text model | Default: `gpt-4o-mini` |
| `FO_OPENAI_VISION_MODEL` | OpenAI-compatible vision model | Falls back to `FO_OPENAI_MODEL` |
| `FO_CLAUDE_API_KEY` | Claude API key | Preferred for consistency |
| `FO_CLAUDE_MODEL` | Claude text model | Default: `claude-3-5-sonnet-20241022` |
| `FO_CLAUDE_VISION_MODEL` | Claude vision model | Falls back to `FO_CLAUDE_MODEL` |
| `FO_LLAMA_CPP_MODEL_PATH` | Local `.gguf` path | Required for `FO_PROVIDER=llama_cpp` |
| `FO_LLAMA_CPP_N_GPU_LAYERS` | llama.cpp GPU layer offload | Optional |
| `FO_MLX_MODEL_PATH` | MLX model path or HF repo id | Required for `FO_PROVIDER=mlx` |
| `FO_PROFILE` | Profile name to load when `FO_PROVIDER` is unset | Default: `default` |
| `OLLAMA_HOST` | Ollama host URL | Optional override for Ollama client |

SDK-native key fallbacks are supported:

- `OPENAI_API_KEY` (fallback when `FO_PROVIDER=openai`)
- `ANTHROPIC_API_KEY` (fallback when `FO_PROVIDER=claude`)

## Methodology defaults

`default_methodology` supports:

- `none`
- `para`
- `jd`

Set via CLI:

```bash
file-organizer config edit --methodology para
```

## Path and migration notes

File Organizer uses platformdirs/XDG-compatible paths. See:

- [Path Standardization & Migration](config/path-standardization.md)
- [Path Deprecation Notice](config/deprecation-notice.md)

## Related docs

- [AI Provider Setup](setup/ai-providers.md)
- [Dependencies & Optional Extras](setup/dependencies.md)
- [Getting Started](getting-started.md)
