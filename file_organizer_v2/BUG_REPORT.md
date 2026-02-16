# Bug Reports for Local-File-Organizer

The following bugs were identified during a code review and verified with reproduction scripts where applicable.

## 1. Bug: Duplicate processing in PriorityQueue due to faulty reordering logic
**Severity:** Critical
**Location:** `src/file_organizer/parallel/priority_queue.py`

**Description:**
The `PriorityQueue` implementation has a logic flaw in how it handles reordering or re-enqueuing items. It uses a `_removed` set to track invalid IDs, but immediately discards the ID from `_removed` after adding a new entry. If a stale entry for that ID is still deeper in the heap, it is now considered "valid" again.

**Reproduction:**
```python
pq = PriorityQueue()
item = QueueItem(id="test", path=Path("..."), priority=10)
pq.enqueue(item)
pq.reorder("test", 20)  # Adds (20, item) and clears "test" from _removed
first = pq.dequeue()    # Returns item with priority 20
second = pq.dequeue()   # Returns item with priority 10 (DUPLICATE!)
```

---

## 2. Performance: O(N^2) overhead in CheckpointManager due to per-file disk IO
**Severity:** High
**Location:** `src/file_organizer/parallel/resume.py`, `checkpoint.py`

**Description:**
The `ResumableProcessor` triggers a full checkpoint update for *every single file* that completes. It reads the entire JSON checkpoint, modifies it, and writes the entire JSON back to disk.
For 10,000 files, this results in significant I/O overhead (approx. 16 minutes of overhead). For 100,000 files, it renders the system unusable.

**Proposed Fix:**
Batch checkpoint updates (e.g., every 100 files or every 5 seconds).

---

## 3. Bug: Unbounded memory usage in `ParallelProcessor.process_batch_iter`
**Severity:** Medium
**Location:** `src/file_organizer/parallel/processor.py`

**Description:**
`process_batch_iter` submits **all** files to the `executor` immediately, regardless of the `max_workers` setting.
If processing a directory with 1 million files, this will create 1 million `Future` objects instantly, potentially exhausting memory or file descriptors before the first file is even processed.

**Proposed Fix:**
Use a bounded semaphore or chunking strategy to limit the number of pending futures.

---

## 4. Bug: Zombie tasks not cancelled on timeout in `ParallelProcessor`
**Severity:** Medium
**Location:** `src/file_organizer/parallel/processor.py`

**Description:**
When a task times out (`TimeoutError`), the `Future` is abandoned, but the underlying thread or process is **not killed**. This leads to "Zombie" processes continuing to run in the background, consuming CPU/IO.

**Proposed Fix:**
Explicitly cancel futures on timeout, or use a mechanism that can interrupt running tasks.

---

## 5. Critical: Non-atomic writes in `JobPersistence` and `CheckpointManager` risk data corruption
**Severity:** Critical
**Location:** `persistence.py`, `checkpoint.py`

**Description:**
File writes (`path.write_text`) are not atomic. If the application crashes or power fails during a write, the JSON file will be corrupted (half-written), causing data loss.

**Proposed Fix:**
Write to a temporary file first, then atomically rename it to the target path.
