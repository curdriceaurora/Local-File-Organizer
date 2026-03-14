# Performance Tuning Guide

This guide covers tunable parameters across model inference, parallel processing,
memory management, and caching. Use it to optimize File Organizer for your
hardware and workload.

## Overview

Performance-sensitive components:

| Component | Purpose | Source Module |
|-----------|---------|---------------|
| ModelConfig | Inference parameters | `src/file_organizer/models/base.py` |
| ParallelConfig | Worker pool and timeouts | `src/file_organizer/parallel/config.py` |
| AdaptiveBatchSizer | Memory-aware batch sizing | `src/file_organizer/optimization/batch_sizer.py` |
| ModelCache | LRU model caching with TTL | `src/file_organizer/optimization/model_cache.py` |
| ModelWarmup | Background model pre-loading | `src/file_organizer/optimization/warmup.py` |
| ResourceMonitor | Memory and GPU monitoring | `src/file_organizer/optimization/resource_monitor.py` |
| MemoryLimiter | Hard memory caps | `src/file_organizer/optimization/memory_limiter.py` |

## Model Configuration

`ModelConfig` controls inference behavior for all AI models (text, vision, audio).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `name` | (required) | Model identifier (e.g., `qwen2.5:3b-instruct-q4_K_M`) |
| `model_type` | (required) | `TEXT`, `VISION`, `AUDIO`, or `VIDEO` |
| `quantization` | `q4_k_m` | Quantization level (lower = faster, less accurate) |
| `device` | `AUTO` | Inference device: `AUTO`, `CPU`, `CUDA`, `MPS`, `METAL` |
| `temperature` | `0.5` | Sampling temperature (lower = more deterministic) |
| `max_tokens` | `3000` | Maximum tokens in generated response |
| `top_k` | `3` | Top-K sampling (fewer candidates = faster) |
| `top_p` | `0.3` | Nucleus sampling threshold |
| `context_window` | `4096` | Maximum context length in tokens |
| `batch_size` | `1` | Batch size for inference |
| `framework` | `ollama` | Backend framework: `ollama`, `llama_cpp`, `mlx` |

### Device Selection

```python
from file_organizer.models.base import DeviceType

# Automatic (recommended) - detects best available device
DeviceType.AUTO

# Force CPU (universal, slower)
DeviceType.CPU

# NVIDIA GPU (fastest for supported models)
DeviceType.CUDA

# Apple Silicon GPU
DeviceType.MPS

# Apple Metal via MLX
DeviceType.METAL
```

### Tuning Tips

- Lower `max_tokens` to 200-500 for classification tasks that only need short
  responses (folder names, filenames)
- Reduce `temperature` to 0.1-0.3 for more consistent naming
- Reduce `context_window` if processing only small files to save memory
- Use `q4_k_m` quantization for the best speed/quality tradeoff

## Parallel Processing

`ParallelConfig` controls how files are processed concurrently.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_workers` | `None` (CPU count) | Maximum worker threads or processes |
| `executor_type` | `THREAD` | `THREAD` (I/O-bound) or `PROCESS` (CPU-bound) |
| `prefetch_depth` | `2` | Queue-ahead depth per worker for task scheduling (`0` = no prefetch queueing). |
| `chunk_size` | `10` | Files submitted per scheduling round |
| `timeout_per_file` | `60.0` | Seconds before a file processing times out |
| `retry_count` | `2` | Retry attempts for failed files |

### Tuning Tips

- For Ollama-based inference (I/O-bound), use `THREAD` executor
- For local model inference with GPU, `max_workers=1` prevents GPU contention
- Lower `prefetch_depth` (or use `0`) to reduce queued work and memory pressure
- Increase `timeout_per_file` for large PDFs or videos (120-300s)
- Increase `chunk_size` for many small files (50-100)
- Set `retry_count=0` to fail fast during bulk operations

```python
from file_organizer.parallel.config import ParallelConfig, ExecutorType

config = ParallelConfig(
    max_workers=4,
    executor_type=ExecutorType.THREAD,
    prefetch_depth=2,
    chunk_size=20,
    timeout_per_file=120.0,
    retry_count=1,
)
```

## Pipeline Prefetch (I/O-Compute Overlap)

`PipelineOrchestrator` supports double-buffered processing: I/O stages (e.g.
`PreprocessorStage`) run ahead in a thread pool while the compute stage (e.g.
`AnalyzerStage` / LLM inference) runs on the current file. This hides file-read
latency behind LLM inference time.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `prefetch_depth` | `2` | Files to pre-process ahead of current file. `0` disables prefetch. |
| `prefetch_stages` | `1` | Requested number of leading stages to prefetch. The current implementation only supports the first stage; values greater than `1` log a warning and are effectively treated as `1`. |
| `memory_limiter` | `None` | Optional `MemoryLimiter`; gates whether a new prefetch slot opens. |

### Tuning Tips

- Increase `prefetch_depth` (3–5) when files are large and disk I/O is the bottleneck
- Keep `prefetch_depth=2` (default) for typical SSD + Ollama workloads
- Set `prefetch_depth=0` to disable overlap and process files sequentially (useful
  for debugging or on memory-constrained systems)
- Keep `prefetch_stages=1`; higher values are currently capped to the first
  stage for thread-safety
- Pass a `MemoryLimiter` to automatically back off prefetch when RSS approaches
  a configured ceiling
- Note: on `file-organizer organize`, `--no-prefetch` is a backward-compatible
  alias for `--prefetch-depth 0` in the legacy `ParallelProcessor` path. For
  stage-based pipeline overlap, set `prefetch_depth=0` on `PipelineOrchestrator`.

```python
from file_organizer.optimization.memory_limiter import MemoryLimiter, LimitAction
from file_organizer.pipeline.orchestrator import PipelineOrchestrator
from file_organizer.pipeline.stages import PreprocessorStage, AnalyzerStage

# Prefetch depth=3 with a 2 GB memory ceiling
limiter = MemoryLimiter(max_memory_mb=2048, action=LimitAction.WARN)
pipeline = PipelineOrchestrator(
    stages=[PreprocessorStage(), AnalyzerStage()],
    prefetch_depth=3,
    memory_limiter=limiter,
)
results = pipeline.process_batch(files)
```

`PipelineOrchestrator` uses `MemoryLimiter.check()` only to decide whether to
open another prefetch slot, so the `LimitAction` configured on `MemoryLimiter`
in this example does not affect prefetch gating; it only changes what happens
when you call `limiter.enforce()` or use the guarded context manager.

## Adaptive Batch Sizing

`AdaptiveBatchSizer` calculates how many files to process per batch based on
available system memory.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_memory_percent` | `70.0` | Target percentage of available memory to use |
| `min_batch_size` | `1` | Minimum files per batch |
| `max_batch_size` | `1000` | Maximum files per batch |

### How It Works

1. Queries available system memory (Linux `/proc/meminfo`, macOS `sysctl`)
2. Calculates a memory budget from `target_memory_percent`
3. Estimates per-file cost from average file size plus overhead
4. Returns the number of files that fit in the budget
5. Accepts runtime feedback via `adjust_from_feedback()` to refine estimates

### Tuning Tips

- Lower `target_memory_percent` (50-60%) on systems running other services
- Use `set_bounds(min_size=5, max_size=50)` to constrain batch sizes
- Call `adjust_from_feedback()` after each batch to let the sizer learn

```python
from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

sizer = AdaptiveBatchSizer(target_memory_percent=60.0)
sizer.set_bounds(min_size=5, max_size=100)
batch_size = sizer.calculate_batch_size(file_sizes, overhead_per_file=1024)
```

## Model Cache

`ModelCache` keeps loaded models in memory using an LRU eviction policy with
TTL expiration.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_models` | `3` | Maximum models kept in cache simultaneously |
| `ttl_seconds` | `300.0` | Time-to-live before a cached model expires (seconds) |

### How It Works

- On `get_or_load()`: returns cached model if present and not expired
- Expired models are evicted on next access
- When cache is full, the least-recently-used model is evicted
- Thread-safe via internal lock (safe for parallel processing)
- Calls `cleanup()` on evicted models to release resources

### Tuning Tips

- Increase `max_models` if you frequently switch between text, vision, and
  audio models (set to 3-5)
- Increase `ttl_seconds` for long-running batch jobs (600-3600s)
- Decrease `max_models` to 1 on memory-constrained systems
- Use `cache.stats()` to monitor hit/miss ratios

```python
from file_organizer.optimization.model_cache import ModelCache

cache = ModelCache(max_models=3, ttl_seconds=600)
model = cache.get_or_load("qwen2.5:3b", loader_fn)
stats = cache.stats()
```

## Model Warmup

`ModelWarmup` pre-loads models in background threads to eliminate cold-start
latency on first use.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_workers` | `2` | Maximum parallel model loading threads |

### How It Works

- Accepts a list of model names to pre-load
- Skips models already present in the cache
- Loads models in parallel using a thread pool
- Supports both synchronous (`warmup()`) and async (`warmup_async()`) modes

### Tuning Tips

- Pre-warm only models you will actually use in the session
- Set `max_workers=1` if loading models is GPU-bound (prevents contention)
- Use `warmup_async()` to load models while the application starts up

```python
from file_organizer.optimization.warmup import ModelWarmup

warmup = ModelWarmup(cache, loader_factory, max_workers=2)
result = warmup.warmup(["qwen2.5:3b", "qwen2.5vl:7b"])
```

## Resource Monitor

`ResourceMonitor` provides real-time memory and GPU usage to inform cache
eviction and model loading decisions.

### Memory Monitoring

- Uses `psutil` if available, falls back to `/proc/meminfo` (Linux) or
  `sysctl` (macOS) and the `resource` module
- Returns `MemoryInfo` with RSS, VMS, and percent of total memory

### GPU Monitoring

- Queries NVIDIA GPUs via `nvidia-smi`
- Returns `GpuMemoryInfo` with total, used, free bytes and device name
- Returns `None` if no NVIDIA GPU is detected

### Eviction Threshold

| Parameter | Default | Description |
|-----------|---------|-------------|
| `threshold_percent` | `85.0` | Memory usage percentage that triggers eviction |

```python
from file_organizer.optimization.resource_monitor import ResourceMonitor

monitor = ResourceMonitor()
mem = monitor.get_memory_usage()

if monitor.should_evict(threshold_percent=80.0):
    cache.clear()
```

## Memory Limiter

`MemoryLimiter` enforces hard memory caps on the process, taking configurable
actions when limits are exceeded.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_memory_mb` | (required) | Maximum allowed RSS in megabytes |
| `action` | `WARN` | Enforcement action when limit is exceeded |

### Enforcement Actions

| Action | Behavior |
|--------|----------|
| `WARN` | Logs a warning, continues execution |
| `BLOCK` | Logs a warning; caller should check `check()` before proceeding |
| `EVICT_CACHE` | Calls the registered eviction callback to free memory |
| `RAISE` | Raises `MemoryLimitError` exception |

### Usage

```python
from file_organizer.optimization.memory_limiter import MemoryLimiter, LimitAction

limiter = MemoryLimiter(max_memory_mb=4096, action=LimitAction.EVICT_CACHE)
limiter.set_evict_callback(cache.clear)

# Check before heavy operations
if limiter.check():
    process_large_file()

# Or use as context manager
with limiter.guarded():
    process_batch()
```

## Hardware Recommendations

### Small Workloads (< 100 files)

- RAM: 8 GB minimum
- CPU: Any modern multi-core
- GPU: Optional (CPU inference works)
- Recommended config: default settings

### Medium Workloads (100-1,000 files)

- RAM: 16 GB recommended
- CPU: 4+ cores
- GPU: Recommended for vision/audio models
- Recommended config:
  - `max_workers=4`, `chunk_size=20`
  - `target_memory_percent=60.0`
  - `max_models=2`, `ttl_seconds=600`

### Large Workloads (1,000+ files)

- RAM: 32 GB recommended
- CPU: 8+ cores
- GPU: NVIDIA with 8+ GB VRAM or Apple Silicon
- Recommended config:
  - `max_workers=8`, `chunk_size=50`
  - `target_memory_percent=50.0`
  - `max_memory_mb=8192`, `action=EVICT_CACHE`
  - `max_models=3`, `ttl_seconds=1800`
  - `timeout_per_file=180.0`

## Benchmarking

Use the benchmark CLI to profile specific processing surfaces:

```bash
# Baseline file-system overhead
file-organizer benchmark run ~/test-files --suite io --json

# Text and vision processor paths
file-organizer benchmark run ~/test-files --suite text --json
file-organizer benchmark run ~/test-files --suite vision --json

# Pipeline and full organizer passes
file-organizer benchmark run ~/test-files --suite pipeline --json
file-organizer benchmark run ~/test-files --suite e2e --json
```

Why this matters:
- `io` gives a floor for disk-only overhead.
- `text`/`vision`/`audio` isolate processor-stack latency without requiring live model backends.
- `pipeline` and `e2e` capture orchestration overhead and write-path behavior.
- Baseline JSON now includes `runner_profile_version`; treat baseline comparisons as valid only when this version matches.

## Environment Variables

For environment-variable-based configuration (e.g., `FO_CONFIG_DIR`,
`FO_API_HOST`, `FO_API_PORT`), see the
[Configuration Guide](configuration.md).
