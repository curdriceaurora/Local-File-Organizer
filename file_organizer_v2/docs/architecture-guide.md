# Architecture Guide

This document describes the Phase 5 architecture of the File Organizer v2
system, covering the event-driven backbone, file watching pipeline, parallel
processing, optimization layer, and daemon mode.

## High-Level Overview

```
+-------------------+      +------------------+      +-------------------+
|                   |      |                  |      |                   |
|  File Watcher     +----->+  Pipeline        +----->+  Parallel         |
|  (watcher/)       |      |  (pipeline/)     |      |  Processor        |
|                   |      |                  |      |  (parallel/)      |
+--------+----------+      +--------+---------+      +--------+----------+
         |                          |                          |
         |  events                  |  events                  |  results
         v                          v                          v
+-------------------+      +------------------+      +-------------------+
|                   |      |                  |      |                   |
|  Event System     |      |  Optimization    |      |  Daemon Service   |
|  (events/)        |      |  (optimization/) |      |  (daemon/)        |
|                   |      |                  |      |                   |
+-------------------+      +------------------+      +-------------------+
```

## Component Interaction Diagram

```
                           +------------------------+
                           |     DaemonService      |
                           |  (lifecycle, signals,  |
                           |   PID, scheduling)     |
                           +------+-----+-----------+
                                  |     |
                    +-------------+     +-------------+
                    |                                 |
                    v                                 v
         +-------------------+             +-------------------+
         |   FileMonitor     |             | DaemonScheduler   |
         |  (watchdog-based  |             | (periodic tasks:  |
         |   dir watcher)    |             |  health, stats)   |
         +--------+----------+             +-------------------+
                  |
                  | FileEvent (created/modified/deleted/moved)
                  v
         +-------------------+
         | PipelineOrchestrator |
         |  (route, process, |
         |   organize)       |
         +--------+----------+
                  |
        +---------+---------+
        |                   |
        v                   v
+---------------+  +------------------+
|  FileRouter   |  |  ProcessorPool   |
| (extension    |  | (lazy-init,      |
|  mapping)     |  |  factory-based)  |
+---------------+  +--------+---------+
                            |
                            v
               +------------------------+
               |   BaseProcessor        |
               |  (text/image/video/    |
               |   audio processors)    |
               +------------------------+
                            |
                            v
               +------------------------+
               | ParallelProcessor      |
               | (thread/process pool,  |
               |  retries, progress)    |
               +------------------------+

         +-------------------------------------------+
         |          Event System (events/)            |
         |                                           |
         |  EventPublisher --> RedisStreamManager     |
         |  EventConsumer <-- RedisStreamManager     |
         |  PubSubManager (topic routing, wildcards) |
         |  ServiceBus (request/response messaging)  |
         |  MiddlewarePipeline (logging, metrics,    |
         |    retry)                                 |
         +-------------------------------------------+

         +-------------------------------------------+
         |        Optimization Layer                  |
         |                                           |
         |  ModelCache (LRU + TTL)                   |
         |  ConnectionPool (SQLite thread-safe)      |
         |  ResourceMonitor (RAM + GPU)              |
         |  AdaptiveBatchSizer (memory-aware)        |
         |  MemoryLimiter (guard / evict / raise)    |
         |  LazyModelLoader (deferred init)          |
         |  QueryCache (result caching)              |
         +-------------------------------------------+
```

## Package Details

### events/ -- Event-Driven Architecture

The `events` package provides a Redis Streams-based event system for
decoupled communication between components. If Redis is unavailable, all
operations degrade gracefully to no-ops.

**Core components:**

| Module | Class | Purpose |
|-----------------|-----------------------|-------------------------------------------------|
| `types.py` | `EventType` | Enum of event types (FILE_CREATED, SCAN_STARTED, etc.) |
| `types.py` | `FileEvent` | Frozen dataclass representing a file event |
| `types.py` | `ScanEvent` | Frozen dataclass representing a scan event |
| `config.py` | `EventConfig` | Redis URL, stream prefix, batch size, etc. |
| `stream.py` | `RedisStreamManager` | Low-level Redis Streams operations |
| `stream.py` | `Event` | Generic event read from a stream |
| `publisher.py` | `EventPublisher` | High-level typed event publishing |
| `consumer.py` | `EventConsumer` | Async event consuming with handler dispatch |
| `pubsub.py` | `PubSubManager` | Topic-based pub/sub with wildcard matching |
| `middleware.py` | `MiddlewarePipeline` | Onion-model middleware chain for events |
| `middleware.py` | `LoggingMiddleware` | Logs all publish/consume operations |
| `middleware.py` | `MetricsMiddleware` | Tracks counts and latency |
| `middleware.py` | `RetryMiddleware` | Cooperative retry logic for failed handlers |
| `service_bus.py` | `ServiceBus` | Request/response and broadcast messaging |
| `service_bus.py` | `ServiceRequest` | Typed request with source, target, action |
| `service_bus.py` | `ServiceResponse` | Response with success/error and timing |
| `subscription.py`| `SubscriptionRegistry`| Manages subscriptions with wildcard matching |
| `monitor.py` | `EventMonitor` | Stream stats and consumer lag tracking |
| `audit.py` | `AuditLogger` | Persistent audit trail for events |
| `replay.py` | `EventReplayManager` | Replay historical events from streams |
| `discovery.py` | `ServiceDiscovery` | Service registration and lookup |
| `health.py` | `HealthChecker` | Service health monitoring |

**Data flow:**

1. A component creates a `FileEvent` or `ScanEvent`.
1. `EventPublisher.publish_file_event()` serializes it and writes to a Redis
   Stream.
1. `EventConsumer` reads from the stream via a consumer group, dispatches to
   registered handlers by `EventType`.
1. Alternatively, `PubSubManager` provides topic-based routing with wildcard
   subscriptions (e.g., `file.*`).

### watcher/ -- File System Monitoring

The `watcher` package provides real-time directory monitoring using the
`watchdog` library. It detects file creation, modification, deletion, and
move events, applies configurable filtering and debouncing, and queues events
for batch retrieval.

**Core components:**

| Module | Class | Purpose |
|--------------|--------------------|---------------------------------------------------|
| `config.py` | `WatcherConfig` | Watch directories, exclude patterns, debounce, batch size |
| `queue.py` | `EventQueue` | Thread-safe queue with batch dequeue and blocking |
| `queue.py` | `FileEvent` | Frozen dataclass: event_type, path, timestamp |
| `queue.py` | `EventType` | StrEnum: CREATED, MODIFIED, DELETED, MOVED |
| `handler.py` | `FileEventHandler` | Watchdog handler with debounce and filter logic |
| `monitor.py` | `FileMonitor` | Manages observers, dynamic directory add/remove |

**Data flow:**

1. `FileMonitor.start()` creates a `watchdog.Observer` and schedules watches.
1. `FileEventHandler` receives raw watchdog events, applies exclude-pattern
   filtering (e.g., `*.tmp`, `.git/*`) and file-type filtering.
1. Events within the debounce window (default 2 seconds) are collapsed.
1. Surviving events are enqueued as `FileEvent` instances.
1. Downstream code calls `monitor.get_events()` or
   `monitor.get_events_blocking()` to retrieve batches.

### pipeline/ -- Auto-Organization Pipeline

The `pipeline` package connects file discovery to processing and organization.
It routes files to the correct processor, manages processor lifecycles, and
optionally moves files to organized directories.

**Core components:**

| Module | Class | Purpose |
|--------------------|----------------------|------------------------------------------------|
| `config.py` | `PipelineConfig` | Output dir, dry_run, auto_organize, extensions |
| `router.py` | `FileRouter` | Extension-based routing with custom rules |
| `router.py` | `ProcessorType` | StrEnum: TEXT, IMAGE, VIDEO, AUDIO, UNKNOWN |
| `processor_pool.py`| `ProcessorPool` | Lazy-init factory pool for processors |
| `processor_pool.py`| `BaseProcessor` | Protocol: initialize(), cleanup() |
| `orchestrator.py` | `PipelineOrchestrator` | Coordinates route -> process -> organize |
| `orchestrator.py` | `ProcessingResult` | Per-file result with category and destination |
| `orchestrator.py` | `PipelineStats` | Cumulative success/failure/skip counts |

**Data flow:**

1. `PipelineOrchestrator` receives a file path (batch mode) or a `FileEvent`
   from the watcher (watch mode).
1. `FileRouter.route()` checks custom rules first, then extension mapping,
   returning a `ProcessorType`.
1. `ProcessorPool.get_processor()` lazily creates and initializes the
   processor.
1. The processor analyzes the file and returns a category and filename.
1. If `should_move_files` is true (dry_run=False and auto_organize=True),
   the file is copied to `output_directory/<category>/<filename>`.
1. A `ProcessingResult` is returned with timing, category, and status.

**Safety defaults:** Dry-run mode is enabled by default. Files are only moved
when both `dry_run=False` and `auto_organize=True`.

### parallel/ -- Parallel File Processing

The `parallel` package provides concurrent file processing using
`concurrent.futures`, with configurable thread or process pools, scheduling
strategies, retry logic, and progress reporting.

**Core components:**

| Module | Class | Purpose |
|---------------------|--------------------|--------------------------------------------------|
| `config.py` | `ParallelConfig` | Workers, executor type, chunk size, timeout, retries |
| `config.py` | `ExecutorType` | StrEnum: THREAD, PROCESS |
| `processor.py` | `ParallelProcessor`| Batch processing with retries and progress |
| `scheduler.py` | `TaskScheduler` | File ordering (size_asc, type_grouped, custom) |
| `scheduler.py` | `PriorityStrategy` | StrEnum scheduling strategies |
| `result.py` | `BatchResult` | Aggregated results with timing and throughput |
| `result.py` | `FileResult` | Per-file success/failure with duration |
| `priority_queue.py` | `PriorityQueue` | Priority-based task queue |
| `checkpoint.py` | `CheckpointManager`| Save/restore processing progress |
| `resume.py` | `ResumableProcessor`| Resume interrupted batch jobs |
| `resource_manager.py`| `ResourceManager` | System resource allocation and tracking |
| `throttle.py` | `RateThrottler` | Rate limiting for processing throughput |
| `persistence.py` | `JobPersistence` | Persistent job state storage |
| `models.py` | `JobState`, `JobStatus`, `JobSummary` | Job tracking data models |

**Data flow:**

1. `TaskScheduler.schedule()` reorders files by the chosen strategy
   (e.g., smallest first for lower average latency).
1. `ParallelProcessor.process_batch()` submits files to a thread or process
   pool via `concurrent.futures`.
1. Each file is processed with timing. Failed files are retried up to
   `retry_count` times.
1. A `BatchResult` is returned with per-file results, throughput, and
   aggregate counts.
1. `process_batch_iter()` yields results as they complete for streaming
   progress.

### optimization/ -- Performance Optimization

The `optimization` package provides memory management, caching, connection
pooling, and resource monitoring to keep the system performant under load.

**Core components:**

| Module | Class | Purpose |
|---------------------|---------------------|------------------------------------------------|
| `model_cache.py` | `ModelCache` | LRU cache with TTL for loaded AI models |
| `model_cache.py` | `CacheStats` | Hit/miss/eviction counts |
| `connection_pool.py`| `ConnectionPool` | Thread-safe SQLite connection pool |
| `connection_pool.py`| `PoolStats` | Active/idle/wait counts |
| `resource_monitor.py`| `ResourceMonitor` | RAM and GPU memory monitoring |
| `resource_monitor.py`| `MemoryInfo` | Process RSS/VMS/percent |
| `resource_monitor.py`| `GpuMemoryInfo` | GPU total/used/free/percent |
| `batch_sizer.py` | `AdaptiveBatchSizer`| Memory-aware dynamic batch sizing |
| `memory_limiter.py` | `MemoryLimiter` | Enforce memory caps (warn/block/evict/raise) |
| `memory_limiter.py` | `LimitAction` | Enum of enforcement actions |
| `memory_profiler.py`| `MemoryProfiler` | Snapshot and timeline memory profiling |
| `leak_detector.py` | `LeakDetector` | Detect memory leak suspects |
| `lazy_loader.py` | `LazyModelLoader` | Deferred model initialization |
| `query_cache.py` | `QueryCache` | Cache database query results |
| `database.py` | `DatabaseOptimizer` | Index and query plan analysis |
| `warmup.py` | `ModelWarmup` | Pre-load models at startup |

### daemon/ -- Background Daemon Mode

The `daemon` package provides a long-running service that combines file
watching with auto-organization, including PID management, signal handling,
and periodic task scheduling.

**Core components:**

| Module | Class | Purpose |
|----------------|------------------|---------------------------------------------------|
| `config.py` | `DaemonConfig` | Watch dirs, output dir, PID file, poll interval |
| `service.py` | `DaemonService` | Full lifecycle management (start/stop/restart) |
| `pid.py` | `PidFileManager` | Write/read/remove PID files, check process alive |
| `scheduler.py` | `DaemonScheduler`| Periodic task runner in background thread |

**Lifecycle:**

1. `DaemonService.start()` writes a PID file, installs signal handlers
   (SIGTERM, SIGINT), and starts the scheduler with default health-check
   and stats-reporting tasks.
1. `start_background()` runs the service in a daemon thread and returns
   immediately once initialization completes.
1. Signal handlers and `stop()` set the stop event, triggering graceful
   shutdown: scheduler stops, PID file is removed, signal handlers are
   restored.
1. `on_start()` and `on_stop()` callbacks allow custom hooks.

## Cross-Cutting Concerns

### Graceful Redis Degradation

All event-system operations check `is_connected` before interacting with
Redis. When Redis is unavailable:

- `EventPublisher` drops events silently (logged at debug level).
- `EventConsumer` returns empty results.
- `PubSubManager` publishes return `None` as message ID.

This allows the system to function without Redis, with events providing
optional observability rather than being a hard dependency.

### Thread Safety

- `EventQueue` uses `threading.Lock` and `threading.Condition` for safe
  concurrent access from watchdog threads and consumer threads.
- `FileMonitor` and `PipelineOrchestrator` use `threading.Lock` for state
  transitions.
- `ConnectionPool` uses a bounded `queue.Queue` for connection checkout.
- `ModelCache` uses `threading.Lock` for LRU operations.

### Configuration Hierarchy

Each package defines its own `*Config` dataclass with sensible defaults.
Configs validate in `__post_init__` and raise `ValueError` for invalid
inputs. The hierarchy is:

```
DaemonConfig
  |-- watch_directories, output_directory, poll_interval
  |
PipelineConfig
  |-- watch_config (WatcherConfig), output_directory, dry_run
  |
WatcherConfig
  |-- watch_directories, exclude_patterns, debounce_seconds
  |
ParallelConfig
  |-- max_workers, executor_type, timeout_per_file, retry_count
  |
EventConfig
  |-- redis_url, stream_prefix, consumer_group, batch_size
```
