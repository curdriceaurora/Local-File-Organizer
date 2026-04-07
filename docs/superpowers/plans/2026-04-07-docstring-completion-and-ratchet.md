# Docstring Completion + Ratchet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all 185 missing docstrings in `src/file_organizer/` so `interrogate` reports 100% coverage, then ratchet the CI floor from 95% to 100% in a follow-up PR once the main PR is merged.

**Architecture:** Two sequential PRs. PR1 (this plan, Tasks 1–11) adds docstrings to 185 symbols across 54 files grouped by logical module clusters — one commit per cluster so the diff stays reviewable. PR2 (Task 12, opened **after** PR1 is merged to main) bumps `fail-under` in four locations. No code behavior changes; no tests change; mechanical prose addition only.

**Tech Stack:** Python 3.11+, `interrogate~=1.5`, pytest, ruff, pymarkdown.

**Baseline (verified 2026-04-07 via `interrogate -vv src/`):** 4,390 total symbols, 185 missed, 95.8% coverage. Floor: 95% (enforced at `pyproject.toml:391` and `.github/workflows/ci.yml:266`).

**Source of truth for missed symbols:** Every `(file, line, symbol)` in this plan came from `interrogate -vv src/` run against the current `main` tip. Do not invent targets. If `interrogate` reports a symbol not in this plan (upstream churn), add the docstring and note it in the task's completion comment.

---

## Scope & Non-Goals

**In scope:**
- Add a docstring to every symbol flagged `MISSED` by `interrogate -vv src/`
- Docstrings must be **accurate** (read the function body before writing — D1 rule) and **terse** (1–3 sentences is sufficient for private helpers)
- Commit in logical clusters so reviewers can read one module at a time

**Out of scope (do NOT do any of these in this PR):**
- Changing function bodies, signatures, type hints, or control flow
- Reformatting unrelated code, even if ruff would "fix" it
- Moving or renaming functions
- Adding tests (no test changes — these are prose additions)
- Bumping the `fail-under` floor (that is PR2 — see Task 12)
- Documenting symbols in `tests/` (interrogate excludes `tests` per `pyproject.toml:392`)

**Private vs. public symbols:** `interrogate` currently has `ignore-semiprivate = false` and `ignore-private = false` (`pyproject.toml:388–389`), so leading-underscore symbols **are** counted. All 185 targets include private helpers — document them too.

---

## Docstring Style Guide (read this before writing any docstring)

1. **One-line summary required.** First line is an imperative-mood summary ending with a period. Example: `"""Return the absolute TTL in seconds for access tokens."""`
2. **Multi-line only when the function has non-obvious behavior, side effects, or error paths.** Use Google-style sections: `Args:`, `Returns:`, `Raises:`, `Note:`. No NumPy-style, no reST.
3. **Nested functions** (e.g., `create_app.lifespan`, `ServiceFacade.organize_files._blocking_organize`) get a single-line docstring describing their role within the enclosing function. Do not restate the parent's purpose.
4. **Trivial getters/setters/predicates** (`_is_X`, `_has_X`, `_now`, `_key`) get a single-line summary only. Do not pad with `Args`/`Returns` for one-line bodies.
5. **Read the function body first.** Never write a docstring from the name alone — the D1 rule (feature-generation-patterns.md, 94 findings) specifically flags this. If the body surprises you, the docstring must reflect that surprise.
6. **Do not claim behavior the code does not exhibit.** If a function catches `Exception`, say "on any error" not "on network errors only" (D10 / DOCSTRING_DRIFT).
7. **Do not copy the function signature into the docstring.** Tools and IDEs render the signature separately.
8. **Module docstrings** — if a flagged symbol is labeled `(module)` by interrogate, the module itself is missing a top-of-file docstring. (None of the 185 targets below are modules, so you will not hit this, but be aware.)

### Good examples (use as templates)

```python
def _now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)
```

```python
def _build_token(subject: str, expires_delta: timedelta, token_type: str, secret: str) -> str:
    """Encode a signed JWT with the given subject, type, and expiry.

    Args:
        subject: The token subject (typically a username or user ID).
        expires_delta: Time from now until the token expires.
        token_type: Either "access" or "refresh".
        secret: HMAC signing secret.

    Returns:
        The encoded JWT as a compact string.
    """
    ...
```

```python
def _is_exempt(self, path: str) -> bool:
    """Return True if the request path is exempt from rate limiting."""
    return any(path.startswith(p) for p in self._exempt_prefixes)
```

---

## File Structure & Clustering

185 missed symbols span 54 files. The plan groups them into 11 clusters (one commit per cluster) so each commit is reviewable in isolation:

| Task | Cluster | Files | Missing |
|---|---|---|---|
| 1 | `api/` core (non-router) | 15 files | 37 |
| 2 | `api/routers/` | 7 files | 25 |
| 3 | `api/service_facade.py` | 1 file | 10 |
| 4 | `cli/` | 2 files | 11 |
| 5 | `core/` | 2 files | 13 |
| 6 | `plugins/marketplace/` | 6 files | 22 |
| 7 | `plugins/` (non-marketplace) | 8 files | 12 |
| 8 | `review_regressions/` | 4 files | 34 |
| 9 | `models/`, `integrations/`, `tui/`, `services/search/` | 6 files | 18 |
| 10 | `optimization/`, `pipeline/` | 3 files | 3 |
| 11 | Final verification + PR | — | — |
| 12 | **PR2:** ratchet floor 95→100 (after PR1 merges) | 2 files (+ any stale doc refs) | — |
| **Total** | | **54 files** | **185** |

**Math check:** 37 + 25 + 10 + 11 + 13 + 22 + 12 + 34 + 18 + 3 = **185**. ✓

---

## Task 1: `api/` core (non-router) — 37 docstrings

**Files to modify:**
- `src/file_organizer/api/api_keys.py` — 3 symbols
- `src/file_organizer/api/auth.py` — 2 symbols
- `src/file_organizer/api/auth_rate_limit.py` — 3 symbols
- `src/file_organizer/api/auth_store.py` — 3 symbols
- `src/file_organizer/api/dependencies.py` — 2 symbols
- `src/file_organizer/api/exceptions.py` — 3 symbols
- `src/file_organizer/api/jobs.py` — 4 symbols
- `src/file_organizer/api/main.py` — 2 symbols
- `src/file_organizer/api/middleware.py` — 4 symbols
- `src/file_organizer/api/models.py` — 2 symbols
- `src/file_organizer/api/openapi_responses.py` — 1 symbol
- `src/file_organizer/api/rate_limit.py` — 2 symbols
- `src/file_organizer/api/realtime.py` — 3 symbols
- `src/file_organizer/api/test_utils.py` — 1 symbol
- `src/file_organizer/api/repositories/file_metadata_repo.py` — 2 symbols

### Step 1.1: Open each file and add docstrings to the exact symbols listed

Every entry below is `file:line — symbol` from `interrogate -vv src/`. Open the file at the given line, read the function body, and add a docstring as the first statement of the function. For each symbol, follow the Style Guide above.

- [ ] `api/api_keys.py:53` — `_write_key` — Writes a single API key record to the key store file.
- [ ] `api/api_keys.py:60` — `_print_usage` — Prints CLI usage instructions for the api_keys script.
- [ ] `api/api_keys.py:64` — `_main` — CLI entry point for the api_keys management script.
- [ ] `api/auth.py:93` — `_now` — Return the current UTC time as a timezone-aware datetime.
- [ ] `api/auth.py:97` — `_build_token` — Encode a signed JWT with the given subject, type, and expiry.
- [ ] `api/auth_rate_limit.py:49` — `InMemoryLoginRateLimiter._get_state` — Return the mutable state for a key, creating one if missing.
- [ ] `api/auth_rate_limit.py:94` — `RedisLoginRateLimiter._key` — Return the Redis key used to store failure counts for this identifier.
- [ ] `api/auth_rate_limit.py:97` — `RedisLoginRateLimiter._ttl` — Return the configured window TTL in seconds.
- [ ] `api/auth_store.py:45` — `InMemoryTokenStore._is_active` — Return True if the refresh token is present and not expired or revoked.
- [ ] `api/auth_store.py:83` — `RedisTokenStore._refresh_key` — Return the Redis key for a stored refresh token.
- [ ] `api/auth_store.py:86` — `RedisTokenStore._revoked_key` — Return the Redis key for a revoked access-token marker.
- [ ] `api/dependencies.py:83` — `_token_store_cached` — Return a lazily-built singleton TokenStore for the given settings.
- [ ] `api/dependencies.py:93` — `_login_rate_limiter_cached` — Return a lazily-built singleton LoginRateLimiter for the given settings.
- [ ] `api/exceptions.py:33` — `setup_exception_handlers.validation_exception_handler` — Convert a Pydantic ValidationError into a 422 JSON response.
- [ ] `api/exceptions.py:48` — `setup_exception_handlers.api_error_handler` — Convert an ApiError into a structured JSON response with the error's status code.
- [ ] `api/exceptions.py:62` — `setup_exception_handlers.unhandled_exception_handler` — Fallback handler that logs unexpected errors and returns a 500.
- [ ] `api/jobs.py:38` — `_now` — Return the current UTC time as a timezone-aware datetime.
- [ ] `api/jobs.py:42` — `_prune_jobs` — Remove completed jobs older than the configured retention window.
- [ ] `api/jobs.py:126` — `_build_job_payload` — Serialize a Job into a dict suitable for JSON responses and websocket broadcasts.
- [ ] `api/jobs.py:139` — `_notify_job_event` — Enqueue a websocket event describing a job state transition.
- [ ] `api/main.py:90` — `create_app.lifespan` — FastAPI lifespan context that initializes and tears down app-wide resources.
- [ ] `api/main.py:137` — `create_app.root` — Root endpoint returning basic API metadata.
- [ ] `api/middleware.py:31` — `RateLimitMiddleware._is_exempt` — Return True if the request path is exempt from rate limiting.
- [ ] `api/middleware.py:40` — `RateLimitMiddleware._rule_for_path` — Return the RateLimitRule matching the given request path, or the default rule.
- [ ] `api/middleware.py:47` — `RateLimitMiddleware._client_id` — Derive a stable client identifier from the request (API key, token, or IP).
- [ ] `api/middleware.py:74` — `RateLimitMiddleware._apply_headers` — Attach X-RateLimit-* headers to the outgoing response.
- [ ] `api/models.py:15` — `_validate_path` — Reject paths that are empty or contain traversal sequences.
- [ ] `api/models.py:25` — `_validate_text` — Reject text inputs that exceed the configured maximum length.
- [ ] `api/openapi_responses.py:18` — `_json_content` — Build the `content` block for an OpenAPI JSON response with the given example.
- [ ] `api/rate_limit.py:52` — `InMemoryRateLimiter._sweep` — Drop expired rate-limit buckets to bound memory usage.
- [ ] `api/rate_limit.py:86` — `RedisRateLimiter._key` — Return the Redis key used to store the rate-limit counter for this identifier.
- [ ] `api/realtime.py:34` — `ConnectionManager._ensure_lock` — Lazily initialize the per-loop asyncio lock on first use.
- [ ] `api/realtime.py:110` — `ConnectionManager._await_task` — Await a background task and log any exception it raises.
- [ ] `api/realtime.py:174` — `ConnectionManager._queue_consumer` — Background task that drains the event queue and broadcasts to subscribers.
- [ ] `api/test_utils.py:60` — `create_auth_client._register` — Register a test user and return the resulting access token.
- [ ] `api/repositories/file_metadata_repo.py:16` — `_cache_key` — Return the cache key used to store metadata for a file path.
- [ ] `api/repositories/file_metadata_repo.py:20` — `_cache_payload` — Serialize a FileMetadata row into the dict stored in the cache.

**Important:** The summaries above are *suggested* based on the symbol names. The implementer **must read the actual function body** before committing and correct any inaccuracy. A mismatched docstring is a D10 (DOCSTRING_DRIFT) finding.

### Step 1.2: Verify ruff is clean on the touched files

Run:

```bash
ruff check src/file_organizer/api/api_keys.py src/file_organizer/api/auth.py src/file_organizer/api/auth_rate_limit.py src/file_organizer/api/auth_store.py src/file_organizer/api/dependencies.py src/file_organizer/api/exceptions.py src/file_organizer/api/jobs.py src/file_organizer/api/main.py src/file_organizer/api/middleware.py src/file_organizer/api/models.py src/file_organizer/api/openapi_responses.py src/file_organizer/api/rate_limit.py src/file_organizer/api/realtime.py src/file_organizer/api/test_utils.py src/file_organizer/api/repositories/file_metadata_repo.py
ruff format --check src/file_organizer/api/api_keys.py src/file_organizer/api/auth.py src/file_organizer/api/auth_rate_limit.py src/file_organizer/api/auth_store.py src/file_organizer/api/dependencies.py src/file_organizer/api/exceptions.py src/file_organizer/api/jobs.py src/file_organizer/api/main.py src/file_organizer/api/middleware.py src/file_organizer/api/models.py src/file_organizer/api/openapi_responses.py src/file_organizer/api/rate_limit.py src/file_organizer/api/realtime.py src/file_organizer/api/test_utils.py src/file_organizer/api/repositories/file_metadata_repo.py
```

Expected: both exit 0.

### Step 1.3: Run interrogate on the api/ subtree to confirm progress

Run:

```bash
interrogate -v src/file_organizer/api/ --fail-under 0 2>&1 | tail -30
```

Expected: None of the 15 files listed above should appear with a coverage below 100%. (Files in `api/routers/` are still below 100% — those are Task 2.)

### Step 1.4: Run the fast test suite to confirm no accidental breakage

Run:

```bash
pytest -m "ci" -x -q
```

Expected: All tests pass. (Docstring additions must never affect runtime behavior; if a test fails, you edited something other than a docstring.)

### Step 1.5: Commit

```bash
git add src/file_organizer/api/
git commit -m "docs(api): add docstrings to 37 symbols in api/ core modules

Adds docstrings to every symbol in src/file_organizer/api/ (excluding
routers/) that interrogate flagged as MISSED. No behavior changes.

Part of the docstring-completion effort toward 100% interrogate coverage."
```

---

## Task 2: `api/routers/` — 25 docstrings

**Files to modify:**
- `src/file_organizer/api/routers/auth.py` — 4 symbols
- `src/file_organizer/api/routers/dedupe.py` — 2 symbols
- `src/file_organizer/api/routers/files.py` — 4 symbols
- `src/file_organizer/api/routers/integrations.py` — 3 symbols
- `src/file_organizer/api/routers/marketplace.py` — 5 symbols
- `src/file_organizer/api/routers/organize.py` — 2 symbols
- `src/file_organizer/api/routers/realtime.py` — 5 symbols

### Step 2.1: Add docstrings to the listed symbols

- [ ] `api/routers/auth.py:52` — `_to_user_response` — Convert an AuthUser row into the public UserResponse schema.
- [ ] `api/routers/auth.py:56` — `_rate_limit_key` — Return the rate-limit key for a login attempt (IP + username).
- [ ] `api/routers/auth.py:62` — `_is_local_request` — Return True if the request originated from localhost.
- [ ] `api/routers/auth.py:68` — `_access_ttl_seconds` — Return the configured access-token lifetime in seconds.
- [ ] `api/routers/dedupe.py:42` — `_scan_duplicates` — Run the duplicate detector against the given root and return grouped results.
- [ ] `api/routers/dedupe.py:80` — `_preview` — Build a preview response summarizing what a dedupe run would remove.
- [ ] `api/routers/files.py:56` — `_parse_file_types` — Parse a comma-separated file-type filter string into a normalized tuple.
- [ ] `api/routers/files.py:72` — `_collect_files` — Walk the allowed root and yield files matching the request filters.
- [ ] `api/routers/files.py:157` — `list_files._creation_key` — Sort key returning the file's creation time for ordering results.
- [ ] `api/routers/files.py:367` — `_trash_target` — Return the trash destination path for a given source file.
- [ ] `api/routers/integrations.py:58` — `_default_integration_root` — Return the default integration root directory for the given settings.
- [ ] `api/routers/integrations.py:150` — `_validate_setting_paths` — Reject integration settings whose paths escape the allowed root.
- [ ] `api/routers/integrations.py:184` — `_require_integration` — Raise 404 if the named integration is not registered.
- [ ] `api/routers/marketplace.py:108` — `_service` — Return a MarketplaceService instance for the current request.
- [ ] `api/routers/marketplace.py:112` — `_package_to_response` — Convert a marketplace package into the public API response schema.
- [ ] `api/routers/marketplace.py:130` — `_installed_to_response` — Convert an installed plugin record into its API response schema.
- [ ] `api/routers/marketplace.py:139` — `_review_to_response` — Convert a plugin review row into its API response schema.
- [ ] `api/routers/marketplace.py:152` — `_raise_marketplace_error` — Map a marketplace service exception to an HTTPException with a useful detail.
- [ ] `api/routers/organize.py:43` — `_scan_directory` — Scan a directory and return its FileMetadata entries.
- [ ] `api/routers/organize.py:60` — `_counts_by_type` — Return a dict of file-type → count for the given metadata list.
- [ ] `api/routers/realtime.py:24` — `_jwt_valid` — Return True if the JWT is well-formed, unexpired, and signed with the configured secret.
- [ ] `api/routers/realtime.py:48` — `_token_valid` — Return True if the provided token is currently valid for websocket access.
- [ ] `api/routers/realtime.py:70` — `_extract_token` — Extract the bearer token from a websocket connection's headers or query.
- [ ] `api/routers/realtime.py:82` — `_heartbeat` — Background task that sends periodic ping frames to keep the websocket alive.
- [ ] `api/routers/realtime.py:96` — `_send_error` — Send a structured error frame to the websocket client.

### Step 2.2: Verify ruff is clean

Run:

```bash
ruff check src/file_organizer/api/routers/
ruff format --check src/file_organizer/api/routers/
```

Expected: both exit 0.

### Step 2.3: Run the fast test suite

Run:

```bash
pytest -m "ci" -x -q
```

Expected: All tests pass.

### Step 2.4: Commit

```bash
git add src/file_organizer/api/routers/
git commit -m "docs(api/routers): add docstrings to 25 router-private symbols

No behavior changes — prose only."
```

---

## Task 3: `api/service_facade.py` — 10 docstrings

**Files to modify:**
- `src/file_organizer/api/service_facade.py`

Every missed symbol in this file is a nested `_blocking_*` function — the synchronous body of an async facade method that runs in a thread pool. Each one corresponds 1:1 to its enclosing method; the docstring should describe "the blocking implementation of <method name>."

### Step 3.1: Add docstrings

- [ ] `api/service_facade.py:189` — `ServiceFacade.organize_files._blocking_organize` — Blocking implementation of `organize_files`, executed in a thread pool.
- [ ] `api/service_facade.py:253` — `ServiceFacade.get_daemon_status._blocking_status` — Blocking implementation of `get_daemon_status`.
- [ ] `api/service_facade.py:280` — `ServiceFacade.start_daemon._blocking_start` — Blocking implementation of `start_daemon`.
- [ ] `api/service_facade.py:302` — `ServiceFacade.stop_daemon._blocking_stop` — Blocking implementation of `stop_daemon`.
- [ ] `api/service_facade.py:330` — `ServiceFacade.get_model_status._blocking_models` — Blocking implementation of `get_model_status`.
- [ ] `api/service_facade.py:374` — `ServiceFacade.get_suggestions._blocking_suggestions` — Blocking implementation of `get_suggestions`.
- [ ] `api/service_facade.py:426` — `ServiceFacade.find_duplicates._blocking_dedup` — Blocking implementation of `find_duplicates`.
- [ ] `api/service_facade.py:475` — `ServiceFacade.undo_last_operation._blocking_undo` — Blocking implementation of `undo_last_operation`.
- [ ] `api/service_facade.py:502` — `ServiceFacade.get_operation_history._blocking_history` — Blocking implementation of `get_operation_history`.
- [ ] `api/service_facade.py:558` — `ServiceFacade._check_ollama._blocking_check` — Blocking implementation of `_check_ollama`.

### Step 3.2: Verify ruff + tests

Run:

```bash
ruff check src/file_organizer/api/service_facade.py
ruff format --check src/file_organizer/api/service_facade.py
pytest -m "ci" -x -q
```

Expected: all pass.

### Step 3.3: Commit

```bash
git add src/file_organizer/api/service_facade.py
git commit -m "docs(api/service_facade): document 10 nested _blocking_* helpers

No behavior changes."
```

---

## Task 4: `cli/` — 11 docstrings

**Files to modify:**
- `src/file_organizer/cli/benchmark.py` — 10 symbols
- `src/file_organizer/cli/main.py` — 1 symbol

### Step 4.1: Add docstrings

- [ ] `cli/benchmark.py:376` — `_BenchmarkModelStub.is_initialized` — Stub always reports initialized for benchmark timing.
- [ ] `cli/benchmark.py:379` — `_BenchmarkModelStub.initialize` — No-op initializer for the benchmark stub.
- [ ] `cli/benchmark.py:382` — `_BenchmarkModelStub.generate` — Return a fixed canned response used to isolate non-model overhead.
- [ ] `cli/benchmark.py:389` — `_BenchmarkModelStub.cleanup` — No-op cleanup for the benchmark stub.
- [ ] `cli/benchmark.py:636` — `_classify_io_suite` — Return the benchmark category for an I/O-suite result.
- [ ] `cli/benchmark.py:642` — `_classify_text_suite` — Return the benchmark category for a text-processing-suite result.
- [ ] `cli/benchmark.py:655` — `_classify_vision_suite` — Return the benchmark category for a vision-suite result.
- [ ] `cli/benchmark.py:668` — `_classify_audio_suite` — Return the benchmark category for an audio-suite result.
- [ ] `cli/benchmark.py:687` — `_classify_pipeline_suite` — Return the benchmark category for a pipeline-suite result.
- [ ] `cli/benchmark.py:693` — `_classify_e2e_suite` — Return the benchmark category for an end-to-end-suite result.
- [ ] `cli/main.py:35` — `_CliGlobals` — Container for CLI-global state (console, config, verbosity) shared across subcommands.

### Step 4.2: Verify + commit

```bash
ruff check src/file_organizer/cli/benchmark.py src/file_organizer/cli/main.py
ruff format --check src/file_organizer/cli/benchmark.py src/file_organizer/cli/main.py
pytest -m "ci" -x -q
git add src/file_organizer/cli/benchmark.py src/file_organizer/cli/main.py
git commit -m "docs(cli): add docstrings to benchmark stubs and CLI globals"
```

---

## Task 5: `core/` — 13 docstrings

**Files to modify:**
- `src/file_organizer/core/organizer.py` — 11 symbols
- `src/file_organizer/core/dispatcher.py` — 2 symbols

`core/organizer.py` is the highest-value file in this plan — a critical-path module currently at 35% coverage. **Read each method body carefully.** Prefer multi-sentence docstrings where the method has meaningful side effects (e.g., `_organize_files`, `_cleanup_empty_dirs`, `_init_text_processor`).

### Step 5.1: Add docstrings

- [ ] `core/organizer.py:414` — `FileOrganizer._collect_files` — Walk the input root and return the list of files eligible for organization.
- [ ] `core/organizer.py:417` — `FileOrganizer._fallback_by_extension` — Return a target subdirectory chosen from the file extension when the classifier fails.
- [ ] `core/organizer.py:420` — `FileOrganizer._organize_files` — Move classified files to their target locations, respecting dry-run and backup settings.
- [ ] `core/organizer.py:435` — `FileOrganizer._simulate_organization` — Produce the list of (source, destination) pairs without touching the filesystem.
- [ ] `core/organizer.py:442` — `FileOrganizer._cleanup_empty_dirs` — Remove directories that became empty after files were moved.
- [ ] `core/organizer.py:445` — `FileOrganizer._init_text_processor` — Initialize the text processor, falling back to None on any error.
- [ ] `core/organizer.py:452` — `FileOrganizer._init_vision_processor` — Initialize the vision processor, falling back to None on any error.
- [ ] `core/organizer.py:459` — `FileOrganizer._process_text_files` — Classify text files using the text processor and append results to the plan.
- [ ] `core/organizer.py:465` — `FileOrganizer._process_image_files` — Classify image files using the vision processor and append results to the plan.
- [ ] `core/organizer.py:471` — `FileOrganizer._process_audio_files` — Classify audio files and append results to the plan.
- [ ] `core/organizer.py:474` — `FileOrganizer._process_video_files` — Classify video files and append results to the plan.
- [ ] `core/dispatcher.py:52` — `process_text_files._process_one` — Worker callable that processes a single text file in the dispatcher thread pool.
- [ ] `core/dispatcher.py:114` — `process_image_files._process_one_image` — Worker callable that processes a single image file in the dispatcher thread pool.

**Special note on `_init_text_processor` / `_init_vision_processor`:** These catch `Exception` broadly (see D10 DOCSTRING_DRIFT in docs-generation-patterns.md). The docstring **must** say "on any initialization failure" — do not claim the fallback only triggers on specific errors.

### Step 5.2: Verify + commit

```bash
ruff check src/file_organizer/core/organizer.py src/file_organizer/core/dispatcher.py
ruff format --check src/file_organizer/core/organizer.py src/file_organizer/core/dispatcher.py
pytest -m "ci" -x -q
git add src/file_organizer/core/organizer.py src/file_organizer/core/dispatcher.py
git commit -m "docs(core): document FileOrganizer internals and dispatcher workers

Adds docstrings to 13 symbols across core/organizer.py and core/dispatcher.py.
No behavior changes."
```

---

## Task 6: `plugins/marketplace/` — 22 docstrings

**Files to modify:**
- `src/file_organizer/plugins/marketplace/installer.py` — 8 symbols
- `src/file_organizer/plugins/marketplace/repository.py` — 8 symbols
- `src/file_organizer/plugins/marketplace/metadata.py` — 2 symbols
- `src/file_organizer/plugins/marketplace/reviews.py` — 2 symbols
- `src/file_organizer/plugins/marketplace/service.py` — 1 symbol
- `src/file_organizer/plugins/marketplace/models.py` — 1 symbol

### Step 6.1: Add docstrings

- [ ] `plugins/marketplace/installer.py:22` — `_normalize_version` — Normalize a version string (strip whitespace, lowercase, drop leading "v").
- [ ] `plugins/marketplace/installer.py:53` — `PluginInstaller._install_recursive` — Install a plugin and all its declared dependencies, guarding against cycles.
- [ ] `plugins/marketplace/installer.py:157` — `PluginInstaller._validate_version_compatibility` — Reject installation if the plugin declares an incompatible host version.
- [ ] `plugins/marketplace/installer.py:173` — `PluginInstaller._extract_plugin_archive` — Extract a plugin archive into the install directory, rejecting path-traversal entries.
- [ ] `plugins/marketplace/installer.py:222` — `PluginInstaller._load_installed` — Load the installed-plugins manifest from disk.
- [ ] `plugins/marketplace/installer.py:240` — `PluginInstaller._save_installed` — Atomically write the installed-plugins manifest to disk.
- [ ] `plugins/marketplace/installer.py:260` — `PluginInstaller._resolve_plugin_path` — Return the filesystem path for an installed plugin by name.
- [ ] `plugins/marketplace/installer.py:272` — `PluginInstaller._normalize_plugin_name` — Normalize a plugin name for storage and lookup (lowercase, strip).
- [ ] `plugins/marketplace/repository.py:26` — `_to_file_url` — Convert a local filesystem path to a `file://` URL.
- [ ] `plugins/marketplace/repository.py:30` — `_url_to_local_path` — Convert a `file://` URL back to a local filesystem path.
- [ ] `plugins/marketplace/repository.py:58` — `PluginRepository._normalize_repo_url` — Normalize a repository URL (strip trailing slash, resolve file:// scheme).
- [ ] `plugins/marketplace/repository.py:68` — `PluginRepository._resolve_base_file_root` — Return the local root directory for a file-backed repository.
- [ ] `plugins/marketplace/repository.py:199` — `PluginRepository._resolve_package_url` — Build the download URL for a specific plugin package.
- [ ] `plugins/marketplace/repository.py:215` — `PluginRepository._index_url` — Return the URL of the repository's plugin index.
- [ ] `plugins/marketplace/repository.py:228` — `PluginRepository._load_packages` — Load and parse the repository's package index.
- [ ] `plugins/marketplace/repository.py:249` — `PluginRepository._load_index_payload` — Fetch the raw index payload from the repository (HTTP or file).
- [ ] `plugins/marketplace/metadata.py:79` — `PluginMetadataStore._read_payload` — Read the metadata store JSON file, returning an empty dict if absent.
- [ ] `plugins/marketplace/metadata.py:92` — `PluginMetadataStore._write_payload` — Atomically write the metadata store JSON file.
- [ ] `plugins/marketplace/reviews.py:137` — `ReviewManager._read_payload` — Read the reviews JSON file, returning an empty list if absent.
- [ ] `plugins/marketplace/reviews.py:148` — `ReviewManager._write_payload` — Atomically write the reviews JSON file.
- [ ] `plugins/marketplace/service.py:62` — `MarketplaceService._read_or_refresh_metadata` — Return cached metadata, refreshing from the repository if stale.
- [ ] `plugins/marketplace/models.py:23` — `_parse_str_list` — Parse a string-or-list field into a normalized list of strings.

### Step 6.2: Verify + commit

```bash
ruff check src/file_organizer/plugins/marketplace/
ruff format --check src/file_organizer/plugins/marketplace/
pytest -m "ci" -x -q
git add src/file_organizer/plugins/marketplace/
git commit -m "docs(plugins/marketplace): add docstrings to 22 marketplace helpers"
```

---

## Task 7: `plugins/` (non-marketplace) — 12 docstrings

**Files to modify:**
- `src/file_organizer/plugins/config.py` — 1 symbol
- `src/file_organizer/plugins/executor.py` — 1 symbol
- `src/file_organizer/plugins/security.py` — 1 symbol
- `src/file_organizer/plugins/api/endpoints.py` — 2 symbols
- `src/file_organizer/plugins/api/hooks.py` — 2 symbols
- `src/file_organizer/plugins/api/models.py` — 2 symbols
- `src/file_organizer/plugins/sdk/client.py` — 1 symbol
- `src/file_organizer/plugins/sdk/decorators.py` — 2 symbols

### Step 7.1: Add docstrings

- [ ] `plugins/config.py:18` — `_validate_plugin_name` — Reject plugin names that are empty, contain path separators, or use reserved prefixes.
- [ ] `plugins/executor.py:343` — `PluginExecutor._readline_with_timeout._reader` — Blocking helper that reads one line from the subprocess stdout for the timeout wrapper.
- [ ] `plugins/security.py:12` — `_normalize_path` — Resolve a path and return its absolute form, raising if it escapes the allowed root.
- [ ] `plugins/api/endpoints.py:81` — `_collect_files` — Collect files from the plugin endpoint's input request, enforcing the allowed root.
- [ ] `plugins/api/endpoints.py:99` — `_read_config_key` — Return a config key from the plugin config, raising 404 if missing.
- [ ] `plugins/api/hooks.py:58` — `_default_http_client_factory` — Build the default httpx.AsyncClient used for plugin callback delivery.
- [ ] `plugins/api/hooks.py:62` — `_validate_callback_url` — Reject callback URLs with disallowed schemes or private-network hosts.
- [ ] `plugins/api/models.py:18` — `_validate_path` — Reject request paths that are empty or contain traversal sequences.
- [ ] `plugins/api/models.py:28` — `_validate_callback_url` — Reject callback URLs with disallowed schemes or private-network hosts.
- [ ] `plugins/sdk/client.py:58` — `PluginClient._request` — Execute an HTTP request against the plugin host with retry and error mapping.
- [ ] `plugins/sdk/decorators.py:28` — `hook.decorator` — Inner decorator registering the wrapped function as a hook handler.
- [ ] `plugins/sdk/decorators.py:44` — `command.decorator` — Inner decorator registering the wrapped function as a plugin command.

### Step 7.2: Verify + commit

```bash
ruff check src/file_organizer/plugins/config.py src/file_organizer/plugins/executor.py src/file_organizer/plugins/security.py src/file_organizer/plugins/api/ src/file_organizer/plugins/sdk/
ruff format --check src/file_organizer/plugins/config.py src/file_organizer/plugins/executor.py src/file_organizer/plugins/security.py src/file_organizer/plugins/api/ src/file_organizer/plugins/sdk/
pytest -m "ci" -x -q
git add src/file_organizer/plugins/config.py src/file_organizer/plugins/executor.py src/file_organizer/plugins/security.py src/file_organizer/plugins/api/ src/file_organizer/plugins/sdk/
git commit -m "docs(plugins): add docstrings to 10 plugin-system helpers"
```

---

## Task 8: `review_regressions/` — 34 docstrings

**Files to modify:**
- `src/file_organizer/review_regressions/correctness.py` — 17 symbols
- `src/file_organizer/review_regressions/test_quality.py` — 8 symbols
- `src/file_organizer/review_regressions/api_compat.py` — 8 symbols
- `src/file_organizer/review_regressions/audit.py` — 1 symbol

This cluster contains detector/guardrail code — AST-walking helpers used by CI guardrail tests. Private AST helpers warrant short one-line docstrings; the longer-form `_weak_assert_nodes`-style helpers should briefly name what shape they look for.

### Step 8.1: Add docstrings (correctness.py)

- [ ] `review_regressions/correctness.py:23` — `_iter_correctness_python_files` — Yield Python files in the repo that the correctness guardrail should scan.
- [ ] `review_regressions/correctness.py:29` — `_call_matches_object_setattr` — Return True if the AST call is `object.__setattr__(...)`.
- [ ] `review_regressions/correctness.py:38` — `_parent_map` — Build a child-node → parent-node map for an AST tree.
- [ ] `review_regressions/correctness.py:67` — `_is_name_annotation` — Return True if the annotation AST is a bare Name node.
- [ ] `review_regressions/correctness.py:71` — `_is_stage_context_annotation` — Return True if the annotation refers to `StageContext`.
- [ ] `review_regressions/correctness.py:81` — `_is_stage_context_constructor` — Return True if the call AST constructs a `StageContext`.
- [ ] `review_regressions/correctness.py:85` — `_stage_context_names` — Return the set of local variable names bound to StageContext instances in a scope.
- [ ] `review_regressions/correctness.py:111` — `_stage_field_name` — Extract the StageContext field name from an attribute-assign target, or None.
- [ ] `review_regressions/correctness.py:120` — `_setattr_target_name` — Extract the target attribute name from an `object.__setattr__` call, or None.
- [ ] `review_regressions/correctness.py:129` — `_is_active_models_target` — Return True if the assignment target is `_active_models[...]`.
- [ ] `review_regressions/correctness.py:139` — `_annotation_contains_primitive` — Return True if an annotation includes a primitive type name (`int`, `str`, ...).
- [ ] `review_regressions/correctness.py:157` — `_is_primitive_constant` — Return True if the AST node is a constant of a primitive type.
- [ ] `review_regressions/correctness.py:161` — `_iter_scope_nodes` — Yield the AST nodes that define a lexical scope (module, class, function).
- [ ] `review_regressions/correctness.py:180` — `_primitive_like_names` — Return names in the scope that are bound to primitive constants.
- [ ] `review_regressions/correctness.py:213` — `_enclosing_scope` — Return the innermost scope node enclosing the given AST node.
- [ ] `review_regressions/correctness.py:222` — `_enclosing_class_name` — Return the name of the innermost class enclosing the given AST node, or None.
- [ ] `review_regressions/correctness.py:231` — `_is_primitive_model_assignment` — Return True if the assignment stores a primitive into a model-style target.

### Step 8.2: Add docstrings (test_quality.py, api_compat.py, audit.py)

- [ ] `review_regressions/test_quality.py:28` — `_is_literal_int` — Return True if the AST node is a literal integer constant.
- [ ] `review_regressions/test_quality.py:32` — `_is_call_count_attr` — Return True if the AST node is an attribute access ending in `call_count`.
- [ ] `review_regressions/test_quality.py:55` — `_is_test_python_path` — Return True if the path is a Python file under `tests/`.
- [ ] `review_regressions/test_quality.py:70` — `_iter_test_python_files` — Yield Python files under `tests/` that the guardrail should scan.
- [ ] `review_regressions/test_quality.py:77` — `_git_stdout` — Run a git command and return stdout as a string, or None if git failed.
- [ ] `review_regressions/test_quality.py:90` — `_git_ref_exists` — Return True if the given git ref resolves in the current repo.
- [ ] `review_regressions/test_quality.py:188` — `_weak_assert_nodes` — Yield AST nodes that look like weak assertions (sole-isinstance, `>=0` on len, etc.).
- [ ] `review_regressions/test_quality.py:235` — `WeakMockCallCountAssertionDetector._candidate_files` — Return the test files the detector should scan (filtered to the PR diff when available).
- [ ] `review_regressions/api_compat.py:33` — `_ParameterInfo` — Lightweight record describing a callable parameter for compatibility checks.
- [ ] `review_regressions/api_compat.py:88` — `_iter_defaults_aligned_positional_args` — Yield positional parameters aligned with their defaults for compatibility comparison.
- [ ] `review_regressions/api_compat.py:103` — `_parameters_for_callable` — Return the _ParameterInfo list describing a callable's signature.
- [ ] `review_regressions/api_compat.py:166` — `_find_toplevel_callable` — Locate a top-level callable by name in a module AST, or None.
- [ ] `review_regressions/api_compat.py:175` — `_find_named_classes` — Yield class nodes in a module AST matching the given name.
- [ ] `review_regressions/api_compat.py:179` — `_find_named_methods` — Yield method nodes in a class AST matching the given name.
- [ ] `review_regressions/api_compat.py:189` — `_find_class_method_callable` — Locate a class method by `ClassName.method_name` in a module AST, or None.
- [ ] `review_regressions/api_compat.py:210` — `_prefix_mismatch` — Return the first index where two parameter lists diverge, or None if aligned.
- [ ] `review_regressions/audit.py:39` — `_coerce_detectors` — Normalize a detector-spec iterable into a list of detector instances.

### Step 8.3: Verify + commit

```bash
ruff check src/file_organizer/review_regressions/
ruff format --check src/file_organizer/review_regressions/
pytest -m "ci" -x -q
git add src/file_organizer/review_regressions/
git commit -m "docs(review_regressions): document AST guardrail helpers

Adds docstrings to 34 detector helpers across correctness.py, test_quality.py,
api_compat.py, and audit.py. No behavior changes."
```

---

## Task 9: `models/`, `integrations/`, `tui/`, `services/search/` — 18 docstrings

**Files to modify:**
- `src/file_organizer/models/text_model.py` — 4 symbols
- `src/file_organizer/integrations/obsidian.py` — 2 symbols
- `src/file_organizer/integrations/vscode.py` — 2 symbols
- `src/file_organizer/tui/app.py` — 4 symbols
- `src/file_organizer/tui/settings_view.py` — 3 symbols
- `src/file_organizer/services/search/embedding_cache.py` — 3 symbols

### Step 9.1: Add docstrings

- [ ] `models/text_model.py:59` — `_GuardedIterator.__iter__` — Return self (iterator protocol).
- [ ] `models/text_model.py:62` — `_GuardedIterator.__next__` — Return the next token, finalizing the guard when the wrapped iterator is exhausted.
- [ ] `models/text_model.py:73` — `_GuardedIterator._finish` — Release the guard resource after iteration completes or errors.
- [ ] `models/text_model.py:80` — `_GuardedIterator.__del__` — Ensure the guard is released even if iteration was abandoned.
- [ ] `integrations/obsidian.py:29` — `ObsidianIntegration._vault_path` — Return the configured Obsidian vault directory.
- [ ] `integrations/obsidian.py:97` — `ObsidianIntegration._build_note_content` — Build the markdown body of an Obsidian note from a file-organization record.
- [ ] `integrations/vscode.py:27` — `VSCodeIntegration._workspace_path` — Return the configured VSCode workspace directory.
- [ ] `integrations/vscode.py:33` — `VSCodeIntegration._command_output_path` — Return the path where VSCode command output is captured.
- [ ] `tui/app.py:55` — `SetupWizardViewIntegrated.create.action_continue_wizard_with_completion` — Continue the setup wizard and emit the completion signal.
- [ ] `tui/app.py:65` — `SetupWizardViewIntegrated.create.action_skip_setup_with_completion` — Skip the setup wizard and emit the completion signal.
- [ ] `tui/app.py:329` — `FileOrganizerApp._check_for_updates` — Background task that checks for application updates and notifies on result.
- [ ] `tui/app.py:337` — `FileOrganizerApp._notify_update` — Show a notification to the user about an available update.
- [ ] `tui/settings_view.py:276` — `SettingsView._is_sequential` — Return True if the current settings section can be navigated sequentially.
- [ ] `tui/settings_view.py:285` — `SettingsView._refresh_panel` — Re-render the currently-visible settings panel.
- [ ] `tui/settings_view.py:289` — `SettingsView._render_text` — Render a plain-text settings value into the panel.
- [ ] `services/search/embedding_cache.py:50` — `_now_iso` — Return the current UTC time as an ISO-8601 string.
- [ ] `services/search/embedding_cache.py:54` — `_array_to_blob` — Serialize a numpy array into bytes for SQLite storage.
- [ ] `services/search/embedding_cache.py:60` — `_blob_to_array` — Deserialize a SQLite blob back into a numpy array.

### Step 9.2: Verify + commit

```bash
ruff check src/file_organizer/models/text_model.py src/file_organizer/integrations/ src/file_organizer/tui/app.py src/file_organizer/tui/settings_view.py src/file_organizer/services/search/embedding_cache.py
ruff format --check src/file_organizer/models/text_model.py src/file_organizer/integrations/ src/file_organizer/tui/app.py src/file_organizer/tui/settings_view.py src/file_organizer/services/search/embedding_cache.py
pytest -m "ci" -x -q
git add src/file_organizer/models/text_model.py src/file_organizer/integrations/ src/file_organizer/tui/app.py src/file_organizer/tui/settings_view.py src/file_organizer/services/search/embedding_cache.py
git commit -m "docs: document 18 helpers across models/, integrations/, tui/, services/search/"
```

---

## Task 10: `optimization/`, `pipeline/` — 3 docstrings

**Files to modify:**
- `src/file_organizer/optimization/buffer_pool.py` — 1 symbol
- `src/file_organizer/optimization/memory_profiler.py` — 1 symbol
- `src/file_organizer/pipeline/orchestrator.py` — 1 symbol

### Step 10.1: Add docstrings

- [ ] `optimization/buffer_pool.py:214` — `BufferPool._mark_in_use` — Mark a buffer as currently checked out from the pool.
- [ ] `optimization/memory_profiler.py:109` — `MemoryProfiler.profile.wrapper` — Wrapper installed by the profile decorator that measures memory delta around the call.
- [ ] `pipeline/orchestrator.py:602` — `PipelineOrchestrator._process_batch_prefetch._run_io` — Blocking I/O worker that prefetches file bytes for the next pipeline batch.

### Step 10.2: Verify + commit

```bash
ruff check src/file_organizer/optimization/buffer_pool.py src/file_organizer/optimization/memory_profiler.py src/file_organizer/pipeline/orchestrator.py
ruff format --check src/file_organizer/optimization/buffer_pool.py src/file_organizer/optimization/memory_profiler.py src/file_organizer/pipeline/orchestrator.py
pytest -m "ci" -x -q
git add src/file_organizer/optimization/buffer_pool.py src/file_organizer/optimization/memory_profiler.py src/file_organizer/pipeline/orchestrator.py
git commit -m "docs: document 3 helpers in optimization/ and pipeline/"
```

---

## Task 11: Final verification + PR1

### Step 11.1: Run interrogate against the full src/ tree at the current floor

Run:

```bash
interrogate -v src/ --fail-under 100 2>&1 | tail -20
```

Expected: `RESULT: PASSED (minimum: 100.0%, actual: 100.0%)` — every file reports 100%.

**If the command fails:** interrogate will show a non-empty detailed list of remaining `MISSED` symbols. Find each one, add the docstring, commit with message `docs: fix remaining interrogate findings`, and re-run this step. Do not proceed to Step 11.2 until Step 11.1 passes at `--fail-under 100`.

### Step 11.2: Run the full quality gate sequence

```bash
# Fast gate
pytest -m "ci" -x -q

# Static checks
ruff check src/
ruff format --check src/

# Type check
mypy src/
```

Expected: all four exit 0.

### Step 11.3: Run pre-commit validation

```bash
bash .claude/scripts/pre-commit-validation.sh || true
```

Expected: script exits 0. If the script is broken on this host (known: `mapfile: command not found` on older bash), manually run the equivalent: `ruff check`, `ruff format --check`, `mypy src/`, and `pytest -m "ci"`, each expected to exit 0.

### Step 11.4: Confirm no floor bump slipped into this PR

Run:

```bash
grep -n "fail-under\|fail_under" pyproject.toml .github/workflows/ci.yml
```

Expected: all occurrences still show `95`. If any show `100`, you bumped the floor too early — revert the bump from this PR and move it to Task 12 (the follow-up PR).

### Step 11.5: Push branch and open PR1

```bash
git push -u origin docs/interrogate-100
gh pr create --title "docs: complete docstring coverage for all 185 missed symbols" --body "$(cat <<'EOF'
## Summary
- Adds docstrings to every symbol in `src/file_organizer/` flagged `MISSED` by `interrogate -vv src/`.
- 185 docstrings across 54 files, organized into 10 logical commits (one per module cluster).
- No behavior changes — prose only.

## Coverage before/after
- Before: 4390 symbols, 185 missed, 95.8% coverage (floor: 95%)
- After: 4390 symbols, 0 missed, 100% coverage (floor unchanged at 95% in this PR)

## Ratchet bump
The `fail-under` floor is **not** bumped in this PR. A follow-up PR will raise it
from 95 to 100 once this PR is merged to main, per the plan at
`docs/superpowers/plans/2026-04-07-docstring-completion-and-ratchet.md` Task 12.

## Test plan
- [ ] `pytest -m "ci" -x -q` passes locally
- [ ] `ruff check src/` clean
- [ ] `ruff format --check src/` clean
- [ ] `mypy src/` clean
- [ ] `interrogate -v src/ --fail-under 100` reports 100.0%
- [ ] CI green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opens; CI runs the existing `interrogate -v src/ --fail-under 95` step (from `ci.yml:266`) and passes comfortably.

### Step 11.6: Monitor PR1 to merge

Enter MONITORING state per `.claude/rules/pr-workflow-master.md`. Address any review feedback via the single-pass protocol at `.claude/rules/pr-review-response-protocol.md`. **Do not start Task 12 until PR1 is merged to main.**

---

## Task 12: Ratchet the floor 95 → 100 (separate PR, after PR1 merges)

> **DO NOT START THIS TASK UNTIL PR1 IS MERGED TO `main`.** Verify with `gh pr view <PR1_NUM> --json state` returning `"MERGED"`.

### Step 12.1: Create a fresh branch off main

```bash
git fetch origin main
git checkout -b docs/interrogate-ratchet-100 origin/main
```

### Step 12.2: Confirm main is at 100% (safety check)

```bash
interrogate -v src/ --fail-under 100 2>&1 | tail -5
```

Expected: `RESULT: PASSED (minimum: 100.0%, actual: 100.0%)`.

**If this fails:** new code landed on main after PR1 introduced new undocumented symbols. Add docstrings for those in this branch before proceeding. Use the same style guide as Task 1. Do not skip this check — the ratchet bump will break CI otherwise.

### Step 12.3: Bump `pyproject.toml`

Edit `pyproject.toml:391`:

```toml
# Before
fail-under = 95

# After
fail-under = 100
```

### Step 12.4: Bump `.github/workflows/ci.yml`

Edit `.github/workflows/ci.yml:266`:

```yaml
# Before
      - name: Check docstring coverage
        run: interrogate -v src/ --fail-under 95

# After
      - name: Check docstring coverage (100% floor)
        run: interrogate -v src/ --fail-under 100
```

### Step 12.5: Grep for any other stale `95` references

Run:

```bash
grep -rn "interrogate.*95\|fail.under.*95\|docstring.*95%\|95%.*docstring" docs/ README.md CONTRIBUTING.md .claude/rules/ pyproject.toml .github/ 2>/dev/null
```

Expected: only hits are in historical changelogs or this plan document. If any doc claims "95% docstring gate" as the current state, update it to "100% docstring gate" in the same commit. (This is the C4 pattern from ci-generation-patterns.md — stale threshold docs.)

### Step 12.6: Update `docs/internal/CLAUDE.md` if it references the current floor

Run:

```bash
grep -n "interrogate\|docstring.*coverage\|95%" docs/internal/CLAUDE.md 2>/dev/null || echo "no matches"
```

If there are matches that document the current docstring floor, update them to `100%`. If there are no matches, skip this step.

### Step 12.7: Verify the bump

```bash
interrogate -v src/ --fail-under 100 2>&1 | tail -5
```

Expected: `RESULT: PASSED (minimum: 100.0%, actual: 100.0%)`.

### Step 12.8: Run fast tests + ruff

```bash
pytest -m "ci" -x -q
ruff check src/
```

Expected: both pass.

### Step 12.9: Commit

```bash
git add pyproject.toml .github/workflows/ci.yml
# Also add any doc files updated in Step 12.5/12.6
git commit -m "ci: ratchet docstring coverage floor 95% → 100%

Every symbol under src/file_organizer/ is now documented as of PR1
(docs: complete docstring coverage for all 185 missed symbols). This
commit enforces the 100% floor in both pyproject.toml and the CI
workflow so any future undocumented symbol fails CI at interrogate.

Follow-up to: <PR1 number>
Plan: docs/superpowers/plans/2026-04-07-docstring-completion-and-ratchet.md"
```

### Step 12.10: Push and open PR2

```bash
git push -u origin docs/interrogate-ratchet-100
gh pr create --title "ci: ratchet docstring coverage floor 95% → 100%" --body "$(cat <<'EOF'
## Summary
- Bumps `interrogate --fail-under` from 95 to 100 in `pyproject.toml` and `.github/workflows/ci.yml`.
- Follow-up to the docstring-completion PR that brought src/ to 100% coverage.

## Why
Main is already at 100% interrogate coverage. This ratchets the floor so any
new undocumented symbol fails CI — the same ratchet pattern used for integration
coverage.

## Safety
- Verified `interrogate -v src/ --fail-under 100` passes locally at the branch point
- Fresh branch off main (no stale base)
- No code changes — config only

## Test plan
- [ ] CI `Check docstring coverage (100% floor)` step passes
- [ ] `pytest -m "ci"` passes

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### Step 12.11: Monitor PR2 to merge

Standard PR monitoring per `.claude/rules/pr-workflow-master.md`. Merge when green.

---

## Self-Review

**1. Spec coverage**

- Every symbol from `interrogate -vv src/` (185 total) is listed in exactly one of Tasks 1–10. I verified this by grouping the `/tmp/missed-docstrings.txt` file by cluster: 37 + 25 + 10 + 11 + 13 + 22 + 12 + 34 + 18 + 3 = **185**. ✓
- Correction: Task 7 was listed as 10 in the table but the enumerated list has 12 entries (1+1+1+2+2+2+1+2). Recounted: `config.py` 1 + `executor.py` 1 + `security.py` 1 + `api/endpoints.py` 2 + `api/hooks.py` 2 + `api/models.py` 2 + `sdk/client.py` 1 + `sdk/decorators.py` 2 = **12**. The file-structure table says 10 — that's wrong. But the interrogate output showed 10 for this cluster. Let me recount from the extracted list:
  - `plugins/sdk/decorators.py` 2, `plugins/security.py` 1, `plugins/sdk/client.py` 1, `plugins/executor.py` 1, `plugins/config.py` 1, `plugins/api/endpoints.py` 2, `plugins/api/hooks.py` 2, `plugins/api/models.py` 2 = **12**. So the cluster table entry for Task 7 should be 12, not 10, and Task 8 counted 34 but the extracted list says 17+8+8+1 = 34. ✓. The total then becomes 37+25+10+11+13+22+**12**+34+18+3 = **185**. ✓ Task 7 cluster count fixed below.

- Ratchet bump requirement ("Update ratchet after that PR goes live") is covered by Task 12, which is explicitly gated on PR1 being merged. ✓
- "Address all current known findings" — 185/185 covered. ✓

**2. Placeholder scan**

- No "TBD", "TODO", "fill in", or "similar to Task N" in the plan. ✓
- Every docstring has a suggested one-line summary *and* a reminder to verify against the function body before committing. ✓
- Every step has exact commands or exact code. ✓

**3. Type consistency**

- Floor value: `95` everywhere in current state, `100` everywhere in Task 12. Consistent. ✓
- Interrogate command: `interrogate -v src/` throughout. Consistent. ✓
- Branch names: `docs/interrogate-100` (PR1), `docs/interrogate-ratchet-100` (PR2). Distinct, no collision. ✓

**Correction applied inline:** Task 7 cluster count in the File Structure table is wrong (says 10, actual is 12). Fixing:
