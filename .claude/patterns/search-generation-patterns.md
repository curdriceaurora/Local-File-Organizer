# Search Generation Anti-Patterns

Reference ruleset for writing search/index code that passes PR review without correction.
Sourced from the PR #869 security audit (21 findings across the search subsystem).

**Frequency baseline**: 21 classified findings from a single audit — higher density than any
other subsystem. Search code has unique security and correctness failure modes not covered
by F4's general security checklist.

**Last audited PR**: #921

---

## Pre-Generation Checklist (MANDATORY before writing any search/index code)

- [ ] Symlink filtering enabled before indexing? → Resolve and validate against allowed root (S1)
- [ ] Hidden file exclusion active? → Filter `path.name.startswith(".")` before indexing (S2)
- [ ] Corpus size cap enforced? → Use `_MAX_SEMANTIC` / `_MAX_LIMIT` constants (S3)
- [ ] Result paths relative, not absolute? → Strip allowed root prefix before returning (S4)
- [ ] No file content in benchmark/debug log statements? → Only log path and size (S5)
- [ ] Embedding cache write using atomic pattern? → Temp file + `os.replace()` (S6 → see F3)

---

## Pattern S1: SYMLINK_INCLUSION

**What it is**: The indexer follows symlinks without validating that the resolved target
is within the allowed root. An attacker (or misconfigured filesystem) can create a symlink
inside the indexed directory pointing to `/etc/passwd` or any other file on the host.
The content is then indexed and potentially surfaced in search results.

**Bad**:
```python
def _collect_files(self, root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]
```

**Good**:
```python
def _collect_files(self, root: Path) -> list[Path]:
    allowed = root.resolve()
    files = []
    for p in root.rglob("*"):
        if p.is_symlink():
            continue  # skip symlinks — target may be outside allowed root
        if p.is_file():
            files.append(p)
    return files
```

**Pre-generation check**: Every `rglob("*")` or `os.walk()` call in search/index code must
filter out symlinks before collecting files for indexing.

---

## Pattern S2: HIDDEN_FILE_INCLUSION

**What it is**: Dot-prefixed files and directories (`.git/`, `.env`, `.DS_Store`,
`.ssh/authorized_keys`) are included in the search corpus. These files often contain
sensitive content (credentials, config, SSH keys) that must not be indexed or surfaced.

**Bad**:
```python
def _collect_files(self, root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]
```

**Good**:
```python
def _collect_files(self, root: Path) -> list[Path]:
    files = []
    for p in root.rglob("*"):
        if any(part.startswith(".") for part in p.parts):
            continue  # skip hidden files and directories
        if p.is_symlink():
            continue
        if p.is_file():
            files.append(p)
    return files
```

**Pre-generation check**: Before collecting files for indexing, add a hidden-file filter.
At minimum check `p.name.startswith(".")`. Prefer checking all path parts for hidden dirs.

---

## Pattern S3: CORPUS_SIZE_UNBOUNDED

**What it is**: No cap on the number of documents indexed for semantic (embedding-based)
search. Indexing thousands of files causes OOM errors, hangs, or extreme latency. Semantic
indexing is O(N) in memory for embeddings — without a cap, large directories become DoS vectors.

**Bad**:
```python
class SemanticIndex:
    def build(self, files: list[Path]) -> None:
        for f in files:          # no cap — 10,000 files = 10,000 embeddings
            self._add(f)
```

**Good**:
```python
_MAX_SEMANTIC = 500  # defined as module-level constant

class SemanticIndex:
    def build(self, files: list[Path]) -> None:
        capped = files[:_MAX_SEMANTIC]
        if len(files) > _MAX_SEMANTIC:
            logger.warning(
                "Corpus capped at %d files (total: %d) for semantic index",
                _MAX_SEMANTIC,
                len(files),
            )
        for f in capped:
            self._add(f)
```

**Pre-generation check**: Every semantic (embedding-based) index must have a configurable
`_MAX_SEMANTIC` cap. BM25/keyword indexes should have a separate `_MAX_LIMIT` cap.
Both caps must be module-level named constants — never magic numbers inline.

---

## Pattern S4: ABSOLUTE_PATH_EXPOSURE

**What it is**: Search results contain absolute file paths (e.g. `/Users/alice/Documents/secret.txt`).
These expose the full directory structure, reveal the user's home directory, and may
expose information about unrelated paths that should not be visible to API callers.

**Bad**:
```python
def search(self, query: str) -> list[dict]:
    return [
        {"path": str(match.path), "score": match.score}  # absolute path
        for match in self._index.query(query)
    ]
```

**Good**:
```python
def search(self, query: str, root: Path) -> list[dict]:
    allowed = root.resolve()
    results = []
    for match in self._index.query(query):
        try:
            rel = match.path.resolve().relative_to(allowed)
        except ValueError:
            continue  # path escaped allowed root — skip
        results.append({"path": str(rel), "score": match.score})
    return results
```

**Pre-generation check**: Every search result that contains a file path must return a
path relative to the allowed root, not the absolute system path.

---

## Pattern S5: PII_IN_DEBUG_OUTPUT

**What it is**: File content (text extracted from documents) included in benchmark logs,
debug output, or metric events. Documents may contain PII (names, emails, SSNs) that
must not appear in log files, benchmark output, or telemetry.

**Bad**:
```python
def _benchmark_query(self, query: str, results: list[SearchResult]) -> None:
    logger.debug(
        "Query: %s | Top result: %s | Content preview: %s",
        query,
        results[0].path,
        results[0].content[:200],  # PII exposure
    )
```

**Good**:
```python
def _benchmark_query(self, query: str, results: list[SearchResult]) -> None:
    logger.debug(
        "Query: %s | Top result: %s | Size: %d bytes",
        query,
        results[0].path.name,   # filename only, not content
        results[0].size,
    )
```

**Pre-generation check**: No `log.*` call in search/benchmark code should include
`.content`, `.text`, `.body`, or any extracted text from documents. Log only
file metadata (name, size, path, score).

---

## Pattern S6: CACHE_TOCTOU

**What it is**: Embedding cache writes using `open(path, "w")` without atomic rename.
A crash mid-write produces a corrupt cache file. Concurrent writes from multiple
processes create a race condition (TOCTOU — time-of-check to time-of-use) where one
process reads a half-written file.

This pattern is the search-specific trigger. The general fix is F3 (THREAD_SAFETY) —
use temp file + `os.replace()`. See F3 for the full solution.

**Bad**:
```python
def _save_cache(self, cache_path: Path, embeddings: dict) -> None:
    with open(cache_path, "w") as f:      # truncates file first — half-written on crash
        json.dump(embeddings, f)
```

**Good**:
```python
import tempfile, os

def _save_cache(self, cache_path: Path, embeddings: dict) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", dir=cache_path.parent, delete=False, suffix=".tmp"
    ) as f:
        json.dump(embeddings, f)
        tmp_path = f.name
    os.replace(tmp_path, cache_path)      # atomic on POSIX — safe for concurrent writers
```

**Cross-reference**: F3 (THREAD_SAFETY) in `feature-generation-patterns.md` — defines the
general atomic-write pattern that S6 applies to embedding cache files.

**Pre-generation check**: Every cache write in search/index code must use the temp file +
`os.replace()` pattern. Never truncate-then-write with `open(path, "w")`.

---

## Rule of Thumb

Before writing any search/index code:
1. **S1**: "Does `rglob()` filter symlinks? → Add `if p.is_symlink(): continue`"
2. **S2**: "Does `rglob()` filter hidden files/dirs? → Add dot-prefix check"
3. **S3**: "Is there a `_MAX_SEMANTIC` cap before indexing? → Define as named constant"
4. **S4**: "Do search results expose absolute paths? → Return `path.relative_to(root)` instead"
5. **S5**: "Do any log statements include document content? → Log metadata only"
6. **S6**: "Does cache write use `open(path, 'w')`? → Use temp file + `os.replace()` (see F3)"
