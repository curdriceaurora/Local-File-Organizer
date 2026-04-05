# Module Diagrams

This page captures the current alpha3 runtime flow for the highest-churn subsystems referenced in issue `#1025`.

## Parallel Processing

The parallel layer centers on `ParallelProcessor`, which batches file work onto either thread or process executors, collects completion results, and retries retryable failures.

```mermaid
flowchart LR
    A["File batch"] --> B["ParallelProcessor.process_batch()"]
    B --> C["create_executor()"]
    C --> D["ThreadPoolExecutor or ProcessPoolExecutor"]
    B --> E["_run_batch()"]
    E --> F["_execute_with_timing(path, process_fn)"]
    F --> G["FileResult"]
    G --> H["BatchResult aggregation"]
    H --> I{"Retryable failure?"}
    I -- "yes" --> E
    I -- "no" --> J["Final BatchResult"]

    subgraph "Operational controls"
        K["ParallelConfig"]
        L["Timeout handling"]
        M["Retry count"]
        N["Graceful shutdown"]
    end

    K --> B
    L --> E
    M --> I
    N --> D
```

### Prefetch and task distribution

The executor path is selected from `ParallelConfig.executor_type`; the implementation records which pool type actually ran, then feeds work items through completion-order result collection. Retryable failures loop back into `_run_batch()` with only the failed paths.

## Pipeline Orchestration

`PipelineOrchestrator` supports both the composable stage path and the legacy router-plus-processor path. The stage path is the canonical alpha3 flow.

```mermaid
flowchart TD
    A["Discovered file"] --> B["PipelineOrchestrator.process_file()"]
    B --> C{"Custom stages configured?"}
    C -- "yes" --> D["PreprocessorStage"]
    D --> E["AnalyzerStage"]
    E --> F["PostprocessorStage"]
    F --> G["WriterStage"]
    G --> H["ProcessingResult"]

    C -- "no" --> I["FileRouter"]
    I --> J["ProcessorPool"]
    J --> K["Text / Vision / Audio processor"]
    K --> L["Legacy organize helpers"]
    L --> H

    subgraph "Execution controls"
        M["AdaptiveBatchSizer"]
        N["MemoryLimiter"]
        O["BufferPool"]
        P["ResourceMonitor"]
        Q["ThreadPoolExecutor prefetch lane"]
    end

    M --> B
    N --> Q
    O --> D
    P --> O
    Q --> D
```

### Error propagation

```mermaid
flowchart LR
    A["Stage or processor raises"] --> B["PipelineOrchestrator catches error"]
    B --> C["ProcessingResult.success = false"]
    C --> D["PipelineStats.failed += 1"]
    D --> E["Caller receives per-file error payload"]
```

Failures stay attached to the file-level `ProcessingResult` so batch callers can continue processing other files while still surfacing the exact stage or processor failure.

## Intelligence Profile Merge and Conflict Resolution

The intelligence layer combines persisted profiles, preference metadata, and deterministic conflict scoring.

```mermaid
flowchart TD
    A["Requested profile names"] --> B["ProfileMerger.merge_profiles()"]
    B --> C["ProfileManager.get_profile()"]
    C --> D["Loaded Profile objects"]
    D --> E["Merge global preferences"]
    D --> F["Merge directory-specific preferences"]
    D --> G["Merge learned patterns"]
    D --> H["Merge confidence data"]
    E --> I["resolve_conflicts(values, strategy)"]
    F --> I
    G --> I
    H --> J["Merged confidence map"]
    I --> K["ConflictResolver weighting"]
    K --> L["Recency weight"]
    K --> M["Frequency weight"]
    K --> N["Confidence score"]
    L --> O["Deterministic winning value"]
    M --> O
    N --> O
    O --> P["ProfileManager.create/update_profile()"]
    J --> P
    P --> Q["Merged profile snapshot"]
```

### Conflict resolution strategy

`ConflictResolver` normalizes recency, frequency, and confidence weights, computes a combined score for each candidate preference, and uses the most recent candidate as the deterministic tie-breaker when scores match.
