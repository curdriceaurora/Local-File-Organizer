# Feature Generation Anti-Patterns

Reference ruleset for writing feature code that passes PR review without correction.
Sourced from CodeRabbit and Copilot review comments across 590 feature-type findings (115 PRs, issues #84–#655).

**Frequency baseline**: 590 classified findings — ~17 findings per feature PR average.

---

## Pre-Generation Security Boundary Checklist

**Complete BEFORE writing any feature code touching auth, paths, or external input:**

- [ ] Auth tokens passed via query string? → Move to `Authorization: Bearer` header instead
- [ ] User input used in file paths? → Validate against `ConfigManager.get_allowed_dirs()`
- [ ] Any secrets logged? → Audit all `logger.*` calls in new code
- [ ] API boundary validated? → Add `pydantic` model or manual validation at route handler entry
- [ ] Existing config system consulted? → Check `ConfigManager` before hardcoding any path

---

## Pattern F1: MISSING_ERROR_HANDLING — 53 findings

**What it is**: Error paths not implemented — exception raised by a dependency propagates unhandled to the caller, with no wrapping or user-facing message.

**Bad**:
```python
# BAD — exception from dependency propagates raw to caller
def process_file(path: Path) -> ProcessResult:
    content = self.reader.read(path)  # raises FileNotFoundError if missing
    return self._analyze(content)
```

**Good**:
```python
# GOOD — wrap with context and handle gracefully
def process_file(path: Path) -> ProcessResult:
    try:
        content = self.reader.read(path)
    except FileNotFoundError:
        logger.warning("File not found: %s", path)
        return ProcessResult(success=False, error=f"File not found: {path}")
    except PermissionError as e:
        logger.error("Permission denied reading %s: %s", path, e)
        raise ProcessingError(f"Cannot read {path}") from e
    return self._analyze(content)
```

**Pre-generation check**: For every external call (file I/O, DB, network, subprocess), ask: *"What exception can this raise, and does my code handle it?"*

---

## Pattern F2: TYPE_ANNOTATION — 63 findings

**What it is**: Missing or incorrect type hints; `Any` used where a concrete type is known; return type not declared. Mypy strict mode rejects these.

**Bad**:
```python
# BAD — no type hints, Any used implicitly
def get_metadata(file_path, config=None):
    result = self.processor.analyze(file_path)
    return result
```

**Good**:
```python
# GOOD — concrete types, explicit return
def get_metadata(
    file_path: Path,
    config: Optional[ProcessorConfig] = None,
) -> FileMetadata:
    result: FileMetadata = self.processor.analyze(file_path)
    return result
```

**Pre-generation check**: Every function signature needs `->` return type. Every parameter needs a type annotation. `Any` is only acceptable at external system boundaries (e.g., JSON deserialization before validation).

---

## Pattern F3: THREAD_SAFETY — 64 findings

**What it is**: Race conditions, unprotected shared state, missing locks, non-atomic read-modify-write on shared data.

**Bad**:
```python
# BAD — 'w' truncates file before flock; race window between truncate and lock
with open(cache_file, 'w') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    json.dump(data, f)

# BAD — non-atomic read-modify-write on shared counter
self.count += 1  # read, increment, write — not atomic across threads
```

**Good**:
```python
# GOOD — atomic write via temp file + rename
import tempfile, os
with tempfile.NamedTemporaryFile(
    mode='w', dir=cache_file.parent, delete=False, suffix='.tmp'
) as f:
    json.dump(data, f)
    tmp_path = f.name
os.replace(tmp_path, cache_file)  # atomic on POSIX

# GOOD — threading lock for shared counter
self._lock = threading.Lock()
with self._lock:
    self.count += 1
```

**Pre-generation checklist for shared state**:
- [ ] Is this variable accessed from multiple threads? → Lock required
- [ ] Is this a read-modify-write sequence? → Must be atomic (lock or atomic op)
- [ ] Is this a file write? → Use temp file + `os.replace()` pattern
- [ ] Does `@lru_cache` decorate a function reading env vars? → Remove cache (env can change between calls)

---

## Pattern F4: SECURITY_VULN — 74 findings (highest-frequency feature pattern)

**What it is**: Auth tokens in query strings (log exposure), unsanitized path inputs (directory traversal), secrets in logs, missing input validation at API boundary.

**Bad**:
```python
# BAD — token in query string; appears in access logs, browser history, proxies
@router.get("/api/files")
async def list_files(token: str = Query(...)):
    user = authenticate(token)
    ...

# BAD — user-controlled path used directly → directory traversal
@router.get("/api/download")
async def download(path: str = Query(...)):
    return FileResponse(path)  # attacker passes "../../../etc/passwd"

# BAD — calling get_settings() directly, ignoring injected instance
def health(settings: ApiSettings = Depends(get_settings)):
    cfg = get_settings()  # ignores injected instance, reads fresh from env
```

**Good**:
```python
# GOOD — token in Authorization header
@router.get("/api/files")
async def list_files(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    user = authenticate(token)
    ...

# GOOD — validate path against allowed roots
@router.get("/api/download")
async def download(path: str = Query(...), settings: ApiSettings = Depends(get_api_settings)):
    requested = Path(path).resolve()
    allowed_root = settings.files_root.resolve()
    if not str(requested).startswith(str(allowed_root)):
        raise HTTPException(status_code=403, detail="Access denied")
    return FileResponse(requested)

# GOOD — use the injected instance
def health(settings: ApiSettings = Depends(get_api_settings)):
    return {"status": "ok", "version": settings.version}
```

**Security boundary checklist** (run before every new route/endpoint):
- [ ] Auth via query string? → Must use Authorization header or cookie (httpOnly)
- [ ] Path parameter? → Must validate against `allowed_root` before file ops
- [ ] User input in SQL? → Must use parameterized query, never f-string
- [ ] Secret in any log statement? → Remove or mask
- [ ] Using injected dependency correctly? → Don't call `get_settings()` directly inside routes

---

## Pattern F5: HARDCODED_VALUE — 36 findings

**What it is**: Magic strings/numbers inline; paths like `~/.config/file-organizer/trash` hardcoded instead of using the config system.

**Bad**:
```python
# BAD — hardcoded path, hardcoded magic number
TRASH_DIR = Path("~/.config/file-organizer/trash").expanduser()
MAX_RETRIES = 3  # scattered throughout codebase

# BAD — hardcoded model name
model = OllamaModel("qwen2.5:3b-instruct-q4_K_M")
```

**Good**:
```python
# GOOD — use ConfigManager for paths, settings for tunables
from file_organizer.config import ConfigManager
trash_dir = ConfigManager.get_path("trash")
max_retries = settings.max_retries  # from ApiSettings/AppConfig

# GOOD — model from config
model = OllamaModel(settings.text_model)
```

**Pre-generation check**: Before hardcoding any string/number, ask: *"Does `ConfigManager`, `AppConfig`, or `ApiSettings` already own this value?"*

---

## Pattern F6: API_CONTRACT_BROKEN — ~12 findings

**What it is**: Implemented API shape diverges from documented schema; field names inconsistent with actual plugin base class; response model doesn't match the Pydantic model.

**Bad**:
```python
# BAD — plugin uses get_info()/run() but base class defines get_metadata()/execute()
class MyPlugin(PluginBase):
    def get_info(self) -> dict:  # wrong method name
        ...
```

**Good**:
```python
# GOOD — always read the base class before implementing
# Read: src/file_organizer/plugins/base.py → PluginBase
class MyPlugin(PluginBase):
    def get_metadata(self) -> PluginMetadata:  # correct method from base
        ...
    def execute(self, context: PluginContext) -> PluginResult:  # correct
        ...
```

**Pre-generation check**: Read the base class/interface definition BEFORE implementing. Run `grep "def " src/file_organizer/plugins/base.py` first.

---

## Pattern F7: RESOURCE_NOT_CLOSED — ~10 findings

**What it is**: File handles, DB connections, or async generators not wrapped in context managers; missing `finally` blocks.

**Bad**:
```python
# BAD — connection not closed on exception
conn = db.connect()
results = conn.execute(query)
conn.close()  # never called if execute() raises
```

**Good**:
```python
# GOOD — context manager guarantees close
with db.connect() as conn:
    results = conn.execute(query)

# GOOD — async generator with cleanup
async def stream_results():
    async with db.session() as session:
        async for row in session.stream(query):
            yield row
        # session closed automatically
```

---

## Pattern F8: WRONG_ABSTRACTION — ~8 findings

**What it is**: Mixed concerns in a single module; business logic in route handler instead of service layer; presentation logic in data layer.

**Bad**:
```python
# BAD — route handler doing business logic + DB access + formatting
@router.post("/organize")
async def organize_files(request: OrganizeRequest):
    files = db.query(File).filter(File.status == "pending").all()
    for f in files:
        new_name = generate_name(f.content)  # business logic in route
        f.name = new_name
    db.commit()
    return {"organized": len(files)}
```

**Good**:
```python
# GOOD — route delegates to service
@router.post("/organize")
async def organize_files(
    request: OrganizeRequest,
    service: OrganizeService = Depends(get_organize_service),
):
    result = await service.organize(request)
    return result

# Service owns business logic
class OrganizeService:
    async def organize(self, request: OrganizeRequest) -> OrganizeResult:
        files = await self.repo.get_pending()
        ...
```

---

## Pattern F9: DYNAMIC_IMPORT_ANTIPATTERN — 11 findings (Phase 1 triage — PR #562)

**What it is**: `__import__()` used inline (e.g., in `default_factory` lambdas) instead of top-level `import` statements. Makes code harder to analyze, breaks static analysis tools, and creates subtle behavior differences. Most common in `dataclasses.field(default_factory=lambda: __import__("module").something)`.

**Bad**:
```python
# BAD — dynamic import in default_factory; mypy can't analyze; no tree-shaking
@dataclass
class Config:
    dirs: Any = field(default_factory=lambda: __import__("platformdirs").user_data_dir("app"))
```

**Good**:
```python
# GOOD — top-level import; analyzable; explicit
import platformdirs

@dataclass
class Config:
    dirs: str = field(default_factory=lambda: platformdirs.user_data_dir("app"))
```

**Pre-generation check**: Never use `__import__()` outside of true dynamic loading scenarios (plugin systems, optional dependency guards). Use `try/except ImportError` for optional deps instead.

---

## Rule of Thumb

For every new feature, ask:
1. **F4**: *"Does this touch auth, paths, or user input? Have I applied the security boundary checklist?"*
2. **F3**: *"Is this shared state? Is the read-modify-write atomic?"*
3. **F1**: *"For every external call, what exception can it raise and do I handle it?"*
4. **F2**: *"Does every function have a concrete return type annotation?"*
5. **F5**: *"Does ConfigManager already own this value?"*
6. **F9**: *"Am I using `__import__()` inline? If yes — move to top-level import."*
