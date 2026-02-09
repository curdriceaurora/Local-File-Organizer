# API Reference

This document provides a reference for the public APIs of the Phase 5
packages: events, watcher, pipeline, parallel, optimization, and daemon.

## events/ Package

### EventType

```python
from file_organizer.events import EventType
```

Enum of event types emitted by the system.

| Member           | Value              | Description                      |
|------------------|--------------------|----------------------------------|
| `FILE_CREATED`   | `"file.created"`   | A new file was detected          |
| `FILE_MODIFIED`  | `"file.modified"`  | An existing file was changed     |
| `FILE_DELETED`   | `"file.deleted"`   | A file was removed               |
| `FILE_ORGANIZED` | `"file.organized"` | A file was organized/moved       |
| `SCAN_STARTED`   | `"scan.started"`   | A scan operation began           |
| `SCAN_COMPLETED` | `"scan.completed"` | A scan operation finished        |
| `ERROR`          | `"error"`          | An error occurred                |

### FileEvent

```python
from file_organizer.events import FileEvent
```

Frozen dataclass representing a file system event.

| Field        | Type                | Default                      |
|--------------|---------------------|------------------------------|
| `event_type` | `EventType`        | (required)                   |
| `file_path`  | `str`              | (required)                   |
| `metadata`   | `dict[str, Any]`   | `{}`                         |
| `timestamp`  | `datetime`         | `datetime.now(timezone.utc)` |

Methods:
- `to_dict() -> dict[str, str]` -- Serialize for Redis Streams.
- `from_dict(data: dict[str, str]) -> FileEvent` -- Deserialize (classmethod).

### ScanEvent

```python
from file_organizer.events import ScanEvent
```

Frozen dataclass representing a scan operation event.

| Field       | Type              | Default                      |
|-------------|-------------------|------------------------------|
| `scan_id`   | `str`             | (required)                   |
| `status`    | `str`             | (required)                   |
| `stats`     | `dict[str, Any]`  | `{}`                         |
| `timestamp` | `datetime`        | `datetime.now(timezone.utc)` |

Methods:
- `to_dict() -> dict[str, str]` -- Serialize for Redis Streams.
- `from_dict(data: dict[str, str]) -> ScanEvent` -- Deserialize (classmethod).

### EventConfig

```python
from file_organizer.events import EventConfig
```

Configuration dataclass for the event system.

| Field               | Type         | Default                      |
|---------------------|--------------|------------------------------|
| `redis_url`         | `str`        | `"redis://localhost:6379/0"` |
| `stream_prefix`     | `str`        | `"fileorg"`                  |
| `consumer_group`    | `str`        | `"file-organizer"`           |
| `max_retries`       | `int`        | `3`                          |
| `retry_delay`       | `float`      | `1.0`                        |
| `block_ms`          | `int`        | `5000`                       |
| `max_stream_length` | `int | None` | `10000`                      |
| `batch_size`        | `int`        | `10`                         |

Methods:
- `get_stream_name(name: str) -> str` -- Prefix a stream name (e.g., `"fileorg:file-events"`).

### EventPublisher

```python
from file_organizer.events import EventPublisher
```

High-level publisher for file and scan events. Supports context manager
protocol.

```python
with EventPublisher() as publisher:
    publisher.publish_file_event(
        EventType.FILE_CREATED,
        "path/to/file.txt",
        {"size": 1024},
    )
    publisher.publish_scan_event("scan-001", "started")
```

| Method                                        | Returns        | Description                    |
|-----------------------------------------------|----------------|--------------------------------|
| `connect(redis_url=None)`                     | `bool`         | Connect to Redis               |
| `disconnect()`                                | `None`         | Disconnect                     |
| `publish_file_event(event_type, file_path, metadata=None)` | `str | None` | Publish a file event |
| `publish_scan_event(scan_id, status, stats=None)` | `str | None` | Publish a scan event      |

Properties: `is_connected`, `event_count`.

### EventConsumer

```python
from file_organizer.events import EventConsumer
```

Async event consumer with handler registration.

```python
consumer = EventConsumer(consumer_name="worker-1")
consumer.connect()
consumer.register_handler(EventType.FILE_CREATED, handle_new_file)
await consumer.start_consuming("file-events")
```

| Method                                        | Returns       | Description                     |
|-----------------------------------------------|---------------|---------------------------------|
| `connect(redis_url=None)`                     | `bool`        | Connect to Redis                |
| `disconnect()`                                | `None`        | Stop consuming and disconnect   |
| `register_handler(event_type, handler)`       | `None`        | Register handler for event type |
| `unregister_handler(event_type, handler)`     | `bool`        | Remove a handler                |
| `start_consuming(stream_name, group_name=None)` | `None` (async) | Start consuming (blocks)     |
| `stop()`                                      | `None`        | Signal stop                     |

Properties: `is_connected`, `is_running`, `events_processed`, `registered_handlers`.

### RedisStreamManager

```python
from file_organizer.events import RedisStreamManager
```

Low-level Redis Streams operations. Supports context manager protocol.

| Method                                                 | Returns         | Description                  |
|--------------------------------------------------------|-----------------|------------------------------|
| `connect(redis_url=None)`                              | `bool`          | Establish Redis connection   |
| `disconnect()`                                         | `None`          | Close connection             |
| `publish(stream_name, event_data, max_len=None)`      | `str | None`    | Write to stream              |
| `create_consumer_group(stream_name, group_name=None, start_id="0")` | `bool` | Create consumer group |
| `read_group(stream_name, group_name=None, consumer_name="worker-1", count=None, block_ms=None)` | `list[Event]` | Read pending messages |
| `acknowledge(stream_name, group_name=None, message_id="")` | `bool`    | ACK a message                |
| `subscribe(stream_name, group_name=None, consumer_name="worker-1")` | `AsyncIterator[Event]` | Async stream subscription |
| `get_stream_length(stream_name)`                       | `int`           | Number of entries            |
| `get_pending_count(stream_name, group_name=None)`      | `int`           | Unacknowledged messages      |

### PubSubManager

```python
from file_organizer.events import PubSubManager
```

Topic-based pub/sub with wildcard matching. Supports context manager protocol.

```python
with PubSubManager() as pubsub:
    pubsub.subscribe("file.*", on_file_event)
    pubsub.publish("file.created", {"path": "tmp/hello.txt"})
```

| Method                                           | Returns              | Description                      |
|--------------------------------------------------|----------------------|----------------------------------|
| `connect(redis_url=None)`                        | `bool`               | Connect to Redis                 |
| `disconnect()`                                   | `None`               | Disconnect and clear subs        |
| `subscribe(topic, handler, filter_fn=None)`      | `Subscription`       | Register handler for topic       |
| `unsubscribe(topic, handler)`                    | `bool`               | Remove handler                   |
| `publish(topic, data)`                           | `str | None`         | Publish event to topic           |
| `get_subscriptions(topic)`                       | `list[Subscription]` | Active subs matching topic       |

Properties: `is_connected`, `registry`, `pipeline`, `publish_count`.

Topic patterns support `*` (single segment) and `**` (multiple segments)
wildcards:
- `"file.*"` matches `"file.created"`, `"file.deleted"`, etc.
- `"file.**"` matches `"file.created"`, `"file.scan.started"`, etc.

### MiddlewarePipeline

```python
from file_organizer.events import MiddlewarePipeline, LoggingMiddleware
```

Onion-model middleware chain. `before_*` hooks run in order; `after_*` hooks
run in reverse order.

```python
pipeline = MiddlewarePipeline()
pipeline.add(LoggingMiddleware())
pipeline.add(MetricsMiddleware())
```

Built-in middleware:
- `LoggingMiddleware` -- Logs all publish/consume at INFO level.
- `MetricsMiddleware` -- Tracks publish/consume counts and latency.
- `RetryMiddleware(max_retries=3)` -- Cooperative retry for failed handlers.

### ServiceBus

```python
from file_organizer.events import ServiceBus, ServiceRequest, ServiceResponse
```

Request/response and broadcast messaging between services.

```python
bus = ServiceBus(name="gateway")
bus.register_service("echo", lambda req: {"echo": req.payload})
response = bus.send_request("echo", "ping", {"msg": "hello"})
assert response.success
```

| Method                                              | Returns                         | Description                 |
|-----------------------------------------------------|---------------------------------|-----------------------------|
| `register_service(name, handler)`                   | `None`                          | Register a service handler  |
| `deregister_service(name)`                          | `bool`                          | Remove a service            |
| `has_service(name)`                                 | `bool`                          | Check if service exists     |
| `send_request(target, action, payload=None, timeout=5.0)` | `ServiceResponse`       | Send request, get response  |
| `broadcast(action, payload=None)`                   | `dict[str, ServiceResponse]`    | Send to all services        |
| `list_services()`                                   | `list[str]`                     | Sorted service names        |

---

## watcher/ Package

### WatcherConfig

```python
from file_organizer.watcher import WatcherConfig
```

| Field               | Type              | Default                            |
|---------------------|-------------------|------------------------------------|
| `watch_directories` | `list[Path]`      | `[]`                               |
| `recursive`         | `bool`            | `True`                             |
| `exclude_patterns`  | `list[str]`       | `["*.tmp", ".git/*", ...]`         |
| `debounce_seconds`  | `float`           | `2.0`                              |
| `batch_size`        | `int`             | `10`                               |
| `file_types`        | `list[str] | None`| `None` (all types)                 |

Methods:
- `should_include_file(path: Path) -> bool` -- Check filters.

### EventType (watcher)

```python
from file_organizer.watcher import EventType
```

StrEnum: `CREATED`, `MODIFIED`, `DELETED`, `MOVED`.

### FileEvent (watcher)

```python
from file_organizer.watcher import FileEvent
```

| Field          | Type           | Default   |
|----------------|----------------|-----------|
| `event_type`   | `EventType`    | (required)|
| `path`         | `Path`         | (required)|
| `timestamp`    | `datetime`     | (required)|
| `is_directory` | `bool`         | `False`   |
| `dest_path`    | `Path | None`  | `None`    |

### EventQueue

```python
from file_organizer.watcher import EventQueue
```

Thread-safe event queue.

| Method                                    | Returns          | Description                      |
|-------------------------------------------|------------------|----------------------------------|
| `enqueue(event)`                          | `None`           | Add event (thread-safe)          |
| `dequeue_batch(max_size=10)`              | `list[FileEvent]`| Non-blocking batch dequeue       |
| `dequeue_batch_blocking(max_size=10, timeout=None)` | `list[FileEvent]` | Blocking batch dequeue |
| `peek()`                                  | `FileEvent | None` | View next without removing     |
| `clear()`                                 | `int`            | Remove all, return count         |

Properties: `size`, `is_empty`.

### FileMonitor

```python
from file_organizer.watcher import FileMonitor
```

Real-time directory monitor.

```python
config = WatcherConfig(watch_directories=[Path("tmp/watched")])
monitor = FileMonitor(config)
monitor.start()
events = monitor.get_events(max_size=5)
monitor.stop()
```

| Method                                        | Returns          | Description                     |
|-----------------------------------------------|------------------|---------------------------------|
| `start()`                                     | `None`           | Start watching                  |
| `stop()`                                      | `None`           | Stop watching                   |
| `add_directory(path, recursive=True)`         | `None`           | Add directory dynamically       |
| `remove_directory(path)`                      | `None`           | Remove directory                |
| `get_events(max_size=None)`                   | `list[FileEvent]`| Non-blocking batch              |
| `get_events_blocking(max_size=None, timeout=None)` | `list[FileEvent]` | Blocking batch          |
| `on_created(callback)`                        | `None`           | Register creation callback      |
| `on_modified(callback)`                       | `None`           | Register modification callback  |
| `on_deleted(callback)`                        | `None`           | Register deletion callback      |
| `on_moved(callback)`                          | `None`           | Register move callback          |

Properties: `is_running`, `watched_directories`, `event_count`.

---

## pipeline/ Package

### PipelineConfig

```python
from file_organizer.pipeline import PipelineConfig
```

| Field                   | Type                             | Default                 |
|-------------------------|----------------------------------|-------------------------|
| `watch_config`          | `WatcherConfig | None`           | `None`                  |
| `output_directory`      | `Path`                           | `Path("organized_files")` |
| `dry_run`               | `bool`                           | `True`                  |
| `auto_organize`         | `bool`                           | `False`                 |
| `notification_callback` | `Callable[[Path, bool], None] | None` | `None`           |
| `supported_extensions`  | `set[str] | None`                | `None` (uses defaults)  |
| `max_concurrent`        | `int`                            | `4`                     |

Properties: `effective_extensions`, `should_move_files`.
Methods: `is_supported(file_path: Path) -> bool`.

### ProcessorType

```python
from file_organizer.pipeline import ProcessorType
```

StrEnum: `TEXT`, `IMAGE`, `VIDEO`, `AUDIO`, `UNKNOWN`.

### FileRouter

```python
from file_organizer.pipeline import FileRouter
```

Routes files by extension or custom rules.

```python
router = FileRouter()
router.route(Path("doc.pdf"))     # ProcessorType.TEXT
router.route(Path("photo.jpg"))   # ProcessorType.IMAGE
```

| Method                                    | Returns         | Description                       |
|-------------------------------------------|-----------------|-----------------------------------|
| `route(file_path)`                        | `ProcessorType` | Determine processor type          |
| `add_extension(extension, processor_type)`| `None`          | Register extension mapping        |
| `remove_extension(extension)`             | `None`          | Remove mapping                    |
| `add_custom_rule(predicate, processor_type)` | `None`      | Add predicate-based rule          |
| `clear_custom_rules()`                    | `None`          | Remove all custom rules           |
| `get_extension_map()`                     | `dict`          | Copy of extension map             |

### ProcessorPool

```python
from file_organizer.pipeline import ProcessorPool, BaseProcessor
```

Factory-based lazy initialization pool.

```python
pool = ProcessorPool()
pool.register_factory(ProcessorType.TEXT, lambda: MyTextProcessor())
processor = pool.get_processor(ProcessorType.TEXT)
pool.cleanup()
```

| Method                                  | Returns               | Description                   |
|-----------------------------------------|-----------------------|-------------------------------|
| `register_factory(processor_type, factory)` | `None`           | Register factory callable     |
| `get_processor(processor_type)`         | `BaseProcessor | None`| Get or create processor       |
| `has_processor(processor_type)`         | `bool`                | Check availability            |
| `is_initialized(processor_type)`        | `bool`                | Check if created              |
| `cleanup()`                             | `None`                | Clean up all processors       |

Properties: `active_count`, `registered_types`.

`BaseProcessor` is a `Protocol` with two methods: `initialize()` and
`cleanup()`.

### PipelineOrchestrator

```python
from file_organizer.pipeline import PipelineOrchestrator, ProcessingResult
```

Coordinates the full route-process-organize pipeline.

```python
config = PipelineConfig(output_directory=Path("tmp/organized"))
pipeline = PipelineOrchestrator(config)
result = pipeline.process_file(Path("document.pdf"))
print(result.category, result.destination)
```

| Method                    | Returns                | Description                          |
|---------------------------|------------------------|--------------------------------------|
| `start()`                 | `None`                 | Start pipeline (and watch mode)      |
| `stop()`                  | `None`                 | Stop pipeline                        |
| `process_file(file_path)` | `ProcessingResult`     | Process single file                  |
| `process_batch(files)`    | `list[ProcessingResult]` | Process list of files              |

Properties: `is_running`.

### ProcessingResult

Frozen dataclass with:
- `file_path`, `success`, `category`, `destination`, `duration_ms`, `error`,
  `processor_type`, `dry_run`.

---

## parallel/ Package

### ParallelConfig

```python
from file_organizer.parallel import ParallelConfig, ExecutorType
```

| Field               | Type                | Default                |
|---------------------|---------------------|------------------------|
| `max_workers`       | `int | None`        | `None` (cpu_count())   |
| `executor_type`     | `ExecutorType`      | `ExecutorType.THREAD`  |
| `chunk_size`        | `int`               | `10`                   |
| `timeout_per_file`  | `float`             | `60.0`                 |
| `retry_count`       | `int`               | `2`                    |
| `progress_callback` | `Callable | None`   | `None`                 |

`ExecutorType` is a StrEnum: `THREAD`, `PROCESS`.

### ParallelProcessor

```python
from file_organizer.parallel import ParallelProcessor
```

Concurrent file processing with retries.

```python
processor = ParallelProcessor(ParallelConfig(max_workers=4))
result = processor.process_batch(file_list, process_fn)
print(f"{result.succeeded}/{result.total} succeeded")
```

| Method                                  | Returns                     | Description                    |
|-----------------------------------------|-----------------------------|--------------------------------|
| `process_batch(files, process_fn)`      | `BatchResult`               | Process with retries           |
| `process_batch_iter(files, process_fn)` | `Iterator[FileResult]`      | Stream results as completed    |
| `shutdown()`                            | `None`                      | Clean up resources             |

### BatchResult

| Field               | Type               | Description                     |
|---------------------|--------------------|---------------------------------|
| `total`             | `int`              | Total files submitted           |
| `succeeded`         | `int`              | Successful count                |
| `failed`            | `int`              | Failed count                    |
| `results`           | `list[FileResult]` | Per-file results                |
| `total_duration_ms` | `float`            | Total processing time           |
| `files_per_second`  | `float`            | Throughput                      |

### FileResult

| Field         | Type          | Description                      |
|---------------|---------------|----------------------------------|
| `path`        | `Path`        | File that was processed          |
| `success`     | `bool`        | Whether processing succeeded     |
| `result`      | `Any`         | Processor return value           |
| `error`       | `str | None`  | Error message on failure         |
| `duration_ms` | `float`       | Processing time                  |

### TaskScheduler

```python
from file_organizer.parallel import TaskScheduler, PriorityStrategy
```

Reorders files before parallel processing.

```python
scheduler = TaskScheduler()
ordered = scheduler.schedule(files, PriorityStrategy.SIZE_ASC)
```

Strategies:
- `SIZE_ASC` -- Smallest files first.
- `SIZE_DESC` -- Largest files first.
- `TYPE_GROUPED` -- Group by extension.
- `CUSTOM` -- Use a caller-provided `priority_fn`.

### Additional Components

- `CheckpointManager` -- Save/restore batch progress for resumable jobs.
- `ResumableProcessor` -- Resume interrupted processing from checkpoints.
- `ResourceManager` / `ResourceConfig` -- System resource allocation.
- `RateThrottler` / `ThrottleStats` -- Rate limiting.
- `PriorityQueue` / `QueueItem` -- Priority-based task queue.
- `JobPersistence` -- Persistent job state storage.
- `JobState`, `JobStatus`, `JobSummary` -- Job tracking models.

---

## optimization/ Package

### ModelCache

```python
from file_organizer.optimization import ModelCache, CacheStats
```

LRU model cache with TTL-based expiration and thread safety. Caches loaded
AI models to avoid repeated initialization.

### ConnectionPool

```python
from file_organizer.optimization import ConnectionPool, PoolStats
```

Thread-safe SQLite connection pool with configurable size and timeout.

```python
pool = ConnectionPool(db_path="organizer.db", pool_size=5, timeout=10.0)
with pool.get_connection() as conn:
    conn.execute("SELECT ...")
pool.close()
```

### ResourceMonitor

```python
from file_organizer.optimization import ResourceMonitor, MemoryInfo, GpuMemoryInfo
```

Query system memory (RSS, VMS, percent) and GPU memory usage.

### AdaptiveBatchSizer

```python
from file_organizer.optimization import AdaptiveBatchSizer
```

Calculate batch sizes based on available memory and per-file overhead.

```python
sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
batch_size = sizer.calculate_batch_size(file_sizes, overhead_per_file=1024)
```

### MemoryLimiter

```python
from file_organizer.optimization import MemoryLimiter, LimitAction, MemoryLimitError
```

Enforce memory caps with configurable actions.

```python
limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.WARN)
if limiter.check():
    process_files()

with limiter.guarded():
    process_more_files()
```

Actions: `WARN`, `BLOCK`, `EVICT_CACHE`, `RAISE`.

### Additional Components

- `MemoryProfiler`, `MemorySnapshot`, `MemoryTimeline`, `ProfileResult` --
  Memory profiling utilities.
- `LeakDetector`, `LeakSuspect` -- Memory leak detection.
- `LazyModelLoader` -- Deferred model initialization.
- `QueryCache`, `CachedResult` -- Database query result caching.
- `DatabaseOptimizer`, `QueryPlan`, `TableStats` -- Index and query analysis.
- `ModelWarmup`, `WarmupResult` -- Pre-load models at startup.

---

## daemon/ Package

### DaemonConfig

```python
from file_organizer.daemon import DaemonConfig
```

| Field               | Type            | Default                    |
|---------------------|-----------------|----------------------------|
| `watch_directories` | `list[Path]`    | `[]`                       |
| `output_directory`  | `Path`          | `Path("organized_files")`  |
| `pid_file`          | `Path | None`   | `None`                     |
| `log_file`          | `Path | None`   | `None`                     |
| `dry_run`           | `bool`          | `True`                     |
| `poll_interval`     | `float`         | `1.0`                      |
| `max_concurrent`    | `int`           | `4`                        |

### DaemonService

```python
from file_organizer.daemon import DaemonService
```

Long-running daemon combining file watching with auto-organization.

```python
config = DaemonConfig(
    watch_directories=[Path("tmp/incoming")],
    output_directory=Path("tmp/organized"),
    pid_file=Path("tmp/daemon.pid"),
)
daemon = DaemonService(config)
daemon.start_background()
assert daemon.is_running
daemon.stop()
```

| Method                  | Returns | Description                               |
|-------------------------|---------|-------------------------------------------|
| `start()`               | `None`  | Start in foreground (blocking)            |
| `start_background()`    | `None`  | Start in background thread                |
| `stop()`                | `None`  | Graceful shutdown                         |
| `restart()`             | `None`  | Stop + start_background                   |
| `on_start(callback)`    | `None`  | Register startup callback                 |
| `on_stop(callback)`     | `None`  | Register shutdown callback                |

Properties: `is_running`, `uptime_seconds`, `files_processed`, `scheduler`.

### PidFileManager

```python
from file_organizer.daemon import PidFileManager
```

| Method                    | Returns       | Description                       |
|---------------------------|---------------|-----------------------------------|
| `write_pid(pid_file, pid=None)` | `None` | Write PID to file                 |
| `read_pid(pid_file)`     | `int | None`  | Read PID from file                |
| `remove_pid(pid_file)`   | `bool`        | Remove PID file                   |
| `is_running(pid_file)`   | `bool`        | Check if recorded process is alive|

### DaemonScheduler

```python
from file_organizer.daemon import DaemonScheduler
```

Periodic task runner.

```python
scheduler = DaemonScheduler()
scheduler.schedule_task("health", 60.0, check_health)
scheduler.run_in_background()
scheduler.stop()
```

| Method                                   | Returns | Description                     |
|------------------------------------------|---------|---------------------------------|
| `schedule_task(name, interval, callback)`| `None`  | Register periodic task          |
| `cancel_task(name)`                      | `bool`  | Cancel a task                   |
| `run()`                                  | `None`  | Run event loop (blocking)       |
| `run_in_background()`                    | `None`  | Run in daemon thread            |
| `stop()`                                 | `None`  | Stop the scheduler              |

Properties: `is_running`, `task_names`, `task_count`.
