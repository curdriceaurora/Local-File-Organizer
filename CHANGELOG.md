# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.2] - 2026-07-10

Release recovery patch for the interrupted `2.0.1` publishing flow. This release republishes the `2.0.1` code state under a fresh PyPI version because PyPI does not allow re-uploading a deleted or previously published version. No runtime behavior changes.

## [2.0.1] - 2026-07-09

Post-GA hardening and UX release. Tightens unsafe-by-default settings, makes the plugin sandbox deny-by-default, and broadens the TUI Settings view into a single run-configuration surface. Part of the post-GA hardening & UX epic (#1501). Install/upgrade with `pip install -U local-file-organizer` (or `pipx upgrade local-file-organizer`).

### Security

- **Plugins are now deny-by-default (#1488)** — completed across #1502 and #1533. The unrestricted and implicit read-only sandbox fallbacks were removed (#1502), and a plugin's own `plugin.json` can no longer self-grant blanket access: `_build_sandbox_from_manifest` ignores `allow_all_operations`/`allow_all_paths`, building a policy only from the specific `allowed_paths`/`allowed_operations` it enumerates (#1533). Blanket grants are host-only — a host that trusts a plugin must pass an explicit `policy=` (e.g. `PluginSecurityPolicy.unrestricted()`) to `load_plugin()`. Manifests that previously relied on implicit access now need to enumerate their grants. Phase 2 (signed-manifest / repo-pinning trust) remains scoped in #1488.
- **Safe-by-default API/web binding and auth (#1502, closes #1490, #1491)** — local API/web runs now bind to `127.0.0.1` instead of `0.0.0.0`, and enabling authentication with a placeholder JWT secret (`change-me`) fails fast instead of starting insecurely.
- **GitHub Actions supply-chain defaults hardened (#1502)** — workflow permissions and pinning tightened.

### Added

- **TUI Settings broadened into a full run-configuration surface (#1495)** — beyond the parallelism controls, Settings now manages default input/output directories, organization methodology (none / PARA / Johnny Decimal), text-model choice, and update/privacy toggles, all persisted to the canonical `AppConfig` (new `default_input_dir` / `default_output_dir` fields). New keybindings cycle methodology/model and toggle the update/pre-release flags.
- **TUI preview → apply (#1503, closes #1492)** — the organization-preview Confirm is a real apply action that runs the organize and navigates to History, so the undo path is immediately visible.
- **"Defer setup" flow (#1503, closes #1493)** — persisted `setup_deferred` state with a web defer route and a home-screen reminder, cleared automatically when setup completes via the API, TUI, or core setup.
- **Ollama next-step guidance (#1503, closes #1498)** — prints the exact install/start/pull commands without automatically downloading models.
- **pip/pipx-aware updater fallback (#1502, closes #1497)** — suggests a `pip`/`pipx` upgrade path on macOS/Windows when no native release asset exists.

### Changed

- **Persisted, profile-based `/config` API (#1502, closes #1499)** — the in-memory config store is replaced with `ConfigManager` wiring, and `ServiceFacade` reads from the same source. The `/config` response shape is now the persisted `AppConfig` profile shape (intentional breaking change to the API response).
- **Package version single-sourced from `version.py` (#1502, closes #1485)** — package metadata now resolves the version from `file_organizer.version.__version__` in one place.
- **Directory picking clarified as browser-only where unavailable (#1503, closes #1494)** — browser-only picker fallbacks are disabled and users are guided toward typed absolute paths, with better macOS cancel/unavailable handling.
- **Dependency & CI maintenance** — Renovate bumps across the toolchain: pytest 9.1, rich 15, aiofiles 25, diff-cover 10, opencv-python 5, pre-commit 4, isort 8, pytest-randomly 4, and several Docker/action updates (#1505–#1526). `mypy` is pinned `<1.20` to avoid a flaky 1.20.x compiled-build lint crash (#1533).
- **Docs** — repo landing page cleanup (#1486).

### Fixed

- **POSIX-only CI/smoke tests guarded on Windows (#1529)** — tests that assume POSIX filesystem semantics are now skipped on Windows instead of failing.

## [2.0.0] - 2026-07-05

First stable **2.0.0** release. Promotes the `2.0.0-beta.1` surface to GA after stabilizing the executable-build and release pipelines and closing the last write-path symlink-hardening gap. Installable from PyPI: `pip install local-file-organizer` (or `pipx install local-file-organizer`).

### Security

- **Legacy organize copy paths hardened (#1481, closes #1479)** — `pipeline.orchestrator._organize_file` and `core.file_ops.organize_files` now route their file copies through the shared SafeDir helper (`O_NOFOLLOW` fd-based copy with symlinked-destination/ancestor/source refusal and full `copy2` metadata parity) instead of raw `shutil.copy2`. This closes the last two unhardened copy call sites left as follow-up debt after the WP-2.2 writer-stage work, so a symlink swapped in between path validation and the copy can no longer redirect the write out of the output tree. Falls back to `shutil.copy2` on Windows.

### Changed

- **Correct version labeling on build artifacts** — `scripts/build_config.py` resolves the real package version via `importlib.metadata` (with an in-tree `version.py` fallback) instead of a regex that used a literal `\s` and always fell back to `0.0.0`. The Linux/macOS packaging scripts (`build_linux.sh`, `build_macos.sh`) carried the same broken regex and now reuse the shared resolver, so the CLI/desktop executables **and** the AppImage/tarball/DMG all carry the true `2.0.0` version in their filenames.
- **Release workflows consolidated to remove a race** — `release.yml` now owns PyPI publishing only (with `skip-existing` for safety), and `build.yml` is the sole owner of the GitHub Release. Previously both workflows created/updated the same release on a tag push, making the attached assets and notes nondeterministic.
- **Release binaries are Linux-only** — the GitHub Release ships the Linux CLI + desktop executables and an AppImage, plus the sdist/wheel and `SHA256SUMS`. macOS and Windows remain **supported and CI-verified** (the full suite runs on macOS/Windows in `ci-full.yml`, plus the `python-probe` matrix), and install via `pip`/`pipx`.
- **GitHub release notes come from the CHANGELOG** — the release body is now the curated CHANGELOG section for the tag (via `scripts/extract_changelog.py`), with the auto-generated PR list appended after it.
- **Install & platform docs** — README and docs now lead with `pipx`/`pip install local-file-organizer` (with `pip install -e .` kept as a from-source note); the "macOS (DMG), Windows (installer)" wording is corrected to reflect that only a Linux AppImage is produced and macOS/Windows are pip/pipx installs; the auto-update description is scoped to the Linux AppImage, with pip self-update on macOS/Windows.
- Package metadata `Development Status` promoted from `4 - Beta` to `5 - Production/Stable`.
- **Docs & API-version cleanup for GA** — removed stale "beta1" phrasing from the architecture/API reference pages, and the `system`/`health`/`config` API routers now source their version from `__version__` instead of hardcoded strings — including `ConfigResponse.version`/`app_version`, whose defaults were returned verbatim by `GET /config` and would otherwise drift on every bump (#1483, #1484).

### Removed

- **Unsigned macOS/Windows executables are no longer attached to releases** — they carried Gatekeeper/SmartScreen friction with no code signing or notarization and offered no benefit over `pip`/`pipx` for a CLI tool. Signed `.dmg`/`.app` and installer packaging is deferred as a post-GA follow-up.

### Fixed

- **Executable build/release lane stabilized (#1473–#1478)** — resolved the executable-build workflow blockers, narrowed and stabilized the build test-lane selection, and fixed macOS executable verification that had failed on the `2.0.0-beta.1` tag.

## [2.0.0-beta.1] - 2026-07-04

### Added

- **AudioModel implemented — Whisper transcription behind the shared model lifecycle (#44)** — `models.audio_model.AudioModel` is no longer a Phase 3 `NotImplementedError` placeholder; it wraps the service-level `AudioTranscriber` (faster-whisper) behind the `BaseModel` initialize/generate/cleanup contract. `generate(audio_path)` returns transcript text; a new `transcribe(audio_path)` convenience returns the full `TranscriptionResult` with segments intact, which the dispatcher prefers so the audio classifier's segment-based heuristics (speaker count, narrative length) receive real segments. This makes `--transcribe-audio` actually transcribe (previously the placeholder's `NotImplementedError` — a `RuntimeError` subclass — was silently swallowed by the dispatcher's best-effort path, degrading every file to metadata-only categorization) and lets `fo benchmark --transcribe-smoke` pass end-to-end. Model names accept bare sizes (`tiny`…`large-v3`) or registry-style `whisper:` prefixes; device resolution is CUDA-else-CPU with an explicit MPS→CPU fallback (faster-whisper's CTranslate2 backend has no MPS support, so Apple Silicon no longer degrades via a load error); compute type defaults to float16 on CUDA / int8 on CPU, overridable via `extra_params["compute_type"]`. New `--whisper-model` CLI option on `organize`/`preview` selects the model size (default `tiny`), threaded through `FileOrganizer(whisper_model=...)` (previously hardcoded to `tiny`). The audio model registry gains `whisper:tiny`/`whisper:medium`/`whisper:large-v3` entries, and `fo model list` now reports Whisper install status from the faster-whisper import + HuggingFace cache instead of always showing "No" (Whisper models are not Ollama models). Placeholder tests replaced with a real suite (lifecycle, size parsing, device/compute selection, graceful `[audio]`-extra degradation); user-facing messages that pointed at a nonexistent `[media]` extra now reference the real `[audio]` extra; docs updated (`docs/cli-reference.md`, `docs/setup/audio-video.md`).

- **CI-rail framework + scaffolding for the fo-core pull-back (WP-0.1, #1222)** — mechanical Phase 0 prep, zero runtime/behavior change. Stood up an **advisory** CI-rail framework so later work packages (WP-6.x) can author rails now (warn, don't block) and flip them to enforce once the code they guard merges: a registry (`scripts/ci/rails.toml`), a runner (`scripts/ci/ci_rails.py` — advisory failures warn, enforce failures fail; `--list`/`--enforce-all`), an advisory `ci-rails` pre-commit hook, and framework tests (`tests/ci/test_ci_rails_framework.py`). Added the `tests/security/`, `tests/smoke/`, `tests/extras/` test-package skeletons (with `security`/`extras` pytest markers registered alongside the existing `smoke`). Package root stays `src/file_organizer/`.

### Security

- **Writer-stage anchored-traversal hardening — symlinked output *ancestors* refused (WP-2.2 follow-up, #1268)** — closes the symlinked-ancestor TOCTOU left open by the leaf-only write-path hardening (#1266). `SafeDir.open_root(destination.parent)` only applies `O_NOFOLLOW` to the *final* path component, and `Path.mkdir(parents=True)` follows symlinks, so a symlinked *intermediate* output directory (e.g. an attacker swaps `output/Docs` for a symlink to `~/.ssh`) could still redirect the organize copy outside the output tree. New primitive `SafeDir.open_anchored_writer(relative_path)` (write-side counterpart to `open_anchored_reader`) descends the destination one component at a time from a trusted root — `mkdir` + `open_subdir` per step, each `O_NOFOLLOW` — so a symlinked ancestor is refused with `SymlinkRejected` rather than traversed; the leaf is opened `O_WRONLY|O_CREAT|O_NONBLOCK` (no `O_TRUNC`) and validated by the same regular-file / same-inode checks before truncation. `StageContext` gains an `output_root` field that the postprocessor populates from its output directory (the trusted anchor `destination` is always built under, with `category`/`filename` already traversal-validated by `StageContext`); `WriterStage` routes through `open_anchored_writer` when `output_root` is set and `destination` lives under it, falling back to the existing parent-rooted leaf-protected copy otherwise (custom pipelines, or a `destination` outside the declared root). A `SymlinkRejected` from the anchored walk is **not** retried via the parent-rooted fallback (which could follow the very symlink it refused). The copy-helper internals were refactored into shared `_open_source_nofollow` / `_finish_copy` helpers used by both the anchored and parent-rooted paths, preserving the full `shutil.copy2` parity contract (mode bits, atime/mtime, xattrs, `SpecialFileError`/`SameFileError` refusals) on both. The two legacy unhardened copy paths (`pipeline.orchestrator._organize_file` and `core.file_ops.organize_files`, both still on raw `shutil.copy2`) are unchanged and remain follow-up debt — they lack even leaf protection, so retrofitting SafeDir there is a separate task.
- **Crash-safe cross-device durable move + race-safe trash GC (WP-1.2b, #1248)** — landed `undo.durable_move` (atomic same-device `os.replace`; cross-device EXDEV copy+fsync+replace+unlink guarded by a JSONL write-ahead journal with a startup `sweep` that completes or rolls back interrupted moves) and `undo.trash_gc.TrashGC.safe_delete` (in-flight check + deletion under one journal `LOCK_EX`, with directories pivoted via an atomic rename into a `.pending-delete-<uuid>` staging path so the slow `rmtree` runs unlocked), plus a new `fo recover` CLI command that replays/sweeps the journal on demand (`--dry-run` reports planned actions via the same pure planner sweep uses). Five crash-safety fixes hardened on top of the restored baseline: **(1, P1)** the cross-device `started` in-flight marker is now journaled under `LOCK_EX` *before* the temp file is created/fsynced, closing a file-loss race where a concurrent `TrashGC.safe_delete` could take the lock, see no active entry, and unlink the source out from under the move (which would then strand only the temp for sweep to delete); **(2, P2)** journal compaction now loops on `os.write` until every byte lands (and raises on no-progress) instead of ignoring a short write and `os.replace`-ing a truncated journal that drops retained entries; **(3, P2)** the EXDEV copy now fsyncs the data through a writable handle *before* `copystat` stamps the source mode bits, so a read-only (`0444`) source no longer triggers `EACCES` on the fsync reopen for a non-root caller while still preserving `copystat` mode parity on the destination; **(4, P2)** the in-flight predicate now protects *descendants* of an in-flight `dir_move` directory via separator-anchored path-prefix containment (not just the exact directory path), so a GC can no longer delete a child of a directory mid-restore; and **(5)** every journal read (`_read_journal`, the locked `sweep` reopen) now decodes `encoding="utf-8"` to match the UTF-8 writers, so non-ASCII journal paths can't mojibake under a non-UTF-8 platform default and silently break the in-flight check. The 8 WP-2.2-deferred integration tests (undo call-site adoption, inode-capture history, rollback composition) remain skipped pending #1227 follow-through.
- **Config save-side guard for unsupported schema versions (#1276)** — `config.manager.ConfigManager.save` now refuses to overwrite an on-disk profile whose schema `version` is unsupported, raising `UnsupportedConfigVersionError` (pass `force=True` to migrate deliberately). This closes the gap left by the read-side migration-safety gate (#1230): `load()` degrades an unsupported-version profile to defaults, so a load-mutate-save flow — `api.routers.system.update_config` (now returns **409**) and `cli.config_cli.config_edit` (now exits non-zero with a clear message) — would otherwise silently clobber the incompatible file with default/current-schema data. New profiles and supported-version overwrites are unaffected. The **setup/recovery flows** that legitimately rewrite a config — `core.setup_wizard.SetupWizard.save_config`, `api.routers.setup` completion, and the TUI wizard — pass `force=True` so completing setup *migrates* an unsupported-version profile (the intended repair path) instead of crashing on the guard. The API 409 is returned in the project's `ApiError` shape (`{error, message}`) and documented in the route's OpenAPI `responses`.

### Fixed

- **CI failures after Dependabot Redis 8 + Starlette 1.3 bumps (#1282)** — two fixes so the suite is green under the merged dependency updates: **(1) Redis 8 `setex` deprecation** — `api.cache.RedisCache.set` and `api.auth_store.RedisTokenStore.store_refresh`/`revoke_access` now call `set(key, value, ex=ttl)` instead of the deprecated `setex(key, ttl, value)` (CI runs warnings-as-errors, so the `DeprecationWarning` failed shard 1 + the integration coverage gate); the `>=1s` TTL clamp and `RedisError` handling are preserved. **(2) Starlette 1.3 route introspection** — `tests/web/test_router.py::TestSubRouterInclusion` no longer inspects the bare `APIRouter.routes` (which now exposes only `/` for an unmounted router, superseding the #1279 recursive-traversal approach); it mounts `router` into a fresh `FastAPI()` app at `/ui` and asserts the assembled, flattened `app.routes` contain `/ui/files`, `/ui/organize`, `/ui/profile`, `/ui/settings`, `/ui/marketplace` — a runtime-faithful check. Test/dep-compat only; no runtime behavior change.
- **`tests/web/test_router.py` robustness on newer FastAPI/Starlette (#1279)** — `TestSubRouterInclusion` flattened `router.routes` via `[r.path for r in router.routes]`, which raises `AttributeError: '_IncludedRouter' object has no attribute 'path'` when `include_router` leaves nested route containers (no `.path`) in `routes` — failing the full test matrix (py3.11 + py3.12) independently of any product change. (Superseded by #1282's app-mount approach once Starlette 1.3 landed.) Test-only.

### Changed

- **Extracted `ResourceAwareExecutor` from the pipeline orchestrator (WP-4.3, #1233)** — faithful port of the fork's D2 refactor. The prefetch + I/O-compute-overlap loop (previously the inline `PipelineOrchestrator._process_batch_prefetch` method) now lives in a dedicated `pipeline.resource_aware_executor.ResourceAwareExecutor`, which owns the shared `BufferPool` (lazy init), per-file buffer acquire/release, memory-pressure-driven buffer-pool rebalancing, and the prefetch batch loop. The executor takes the orchestrator's collaborators (`_run_stages`, `_make_context`, `_finalize_result`) as callbacks via `run_prefetched_batch(...)`, so it stays agnostic of `ProcessingResult` and the orchestrator's statistics. `PipelineOrchestrator` constructs the executor from the same resource collaborators it holds (shared buffer pool, memory limiter, resource monitor) and `_process_batch_prefetch` is now a thin delegation. `stop()` gains a SafeDir-style stage-close loop — after the existing cleanup it iterates the configured stages and calls `stage.close()` when present (guarded by `getattr` + `contextlib.suppress`, a safe no-op for stages that hold no file descriptors) to release any stage-held fds. The orchestrator's public API and the internal attributes/methods existing tests reference (`_executor`, `_buffer_pool`, `_resource_monitor`, `_safe_file_size`, `_safe_current_rss`, `_rebalance_buffer_pool`, `_acquire_buffer`/`_release_buffer`, the `_BUFFER_KEY` module constant) are preserved unchanged; `_BUFFER_KEY` is now re-exported from the new module as the single source of truth. No behavior change to `process_file`/`process_batch`. New unit + integration tests in `tests/pipeline/test_resource_aware_executor.py` lock the executor contract.
- **Deterministic offline text processing — vendored stopwords + snowballstemmer (WP-4.4, #1234)** — `utils.text_processing` no longer depends on the optional NLTK runtime. The `import nltk` / `stopwords` / `WordNetLemmatizer` / `word_tokenize` machinery, the `NLTK_AVAILABLE` flag, and the entire `ensure_nltk_data()` `nltk.download()` corpus-fetch path (which could touch the network or raise `LookupError` on a missing corpus) are removed. Stopwords are now vendored in-module as `_ENGLISH_STOPWORDS` (the standard ~179-word NLTK English list, unioned with the existing hand-curated set in `get_unwanted_words`), stemming uses the pure-Python `snowballstemmer` package (the `clean_text(..., lemmatize=True)` flag now drives deterministic Snowball stemming), and tokenization uses a deterministic ASCII regex tokenizer (ASCII-only is an accepted trade-off). `ensure_nltk_data()` is retained as a no-op backward-compat shim (still called by `services.text_processor.TextProcessor`) — it performs no network access and never raises. `pyproject.toml` drops `nltk~=3.8` and adds `snowballstemmer>=2.2`. Result: text processing is fully offline and reproducible.

### Security (Phase 3 — fo-core pull-back)

- **Archive reader decompression-bomb guard + size-cap parity (WP-3.1, pull-back from fo-core, #1229)** — `utils.readers.archives` (ZIP/7Z/TAR/RAR) now refuses decompression bombs via a new `_base._check_decompression_bomb`: an archive whose *declared* uncompressed total exceeds an absolute cap (2 GB), or whose uncompressed/compressed ratio exceeds 1000:1 once expansion passes a 64 MB floor, raises `FileTooLargeError` before the metadata is emitted or any downstream consumer extracts it — closing the gap where a bomb's tiny compressed size sailed past the existing 500 MB on-disk `MAX_FILE_SIZE_BYTES` cap. Each archive reader's **path branch** now also calls `_check_file_size` (parity with the fileobj branch and the scientific/document/ebook readers), and `FileTooLargeError` propagates out of all four readers instead of being wrapped in `FileReadError`. Metadata extraction reads only the central directory (no decompression), so ordinary archives are unaffected; the tar branch applies the absolute cap only (no per-entry compressed size). (The scientific/document/ebook readers already carried the on-disk size caps from earlier WP-1.1/WP-2.1 work.)

- **Config schema-version gating + atomic/migration-safe writes (WP-3.2, pull-back from fo-core, #1230)** — `config.schema` now defines schema-version constants (`CURRENT_SCHEMA_VERSION`, `SUPPORTED_SCHEMA_VERSIONS`); `AppConfig.version` defaults to `CURRENT_SCHEMA_VERSION`. `config.manager.ConfigManager` persists via `utils.atomic_write.atomic_write_text` in both `save()` and `delete_profile()`, so a mid-write crash leaves the prior config intact instead of a truncated/corrupt file. `load()` gains a **migration-safe version gate (F6)**: a profile whose on-disk `version` is not in `SUPPORTED_SCHEMA_VERSIONS` (e.g. a newer/older or hand-edited config) falls back to defaults and **leaves the file untouched** so it can be inspected/migrated rather than silently clobbered (`str()`-normalized so an unquoted YAML float `version: 1.0` is still recognized). Field-level bounds (temperature, max_tokens, …) intentionally remain in `core.setup_wizard.SetupWizard.validate_config`'s construct-then-validate flow — the schema stays a plain dataclass (no raising `__post_init__`), so the wizard's user-facing error messages and the web layer's broader methodology vocabulary keep working.
- **Undo/rollback move-path hardening (WP-2.2 partial, pull-back from fo-core, #1227)** — `undo.rollback.RollbackExecutor` now routes every rollback/redo file move (`rollback_move`/`rollback_rename`/`rollback_delete`/`redo_move`/`redo_rename` and the trash mover) through a new `_durable_move` helper instead of `shutil.move`: the source is `lstat`-ed and a **symlink is refused** (anti-swap — a recorded file swapped for a symlink between the operation and the rollback can no longer redirect the restore into an out-of-root target), the move uses `os.replace` for an atomic same-filesystem rename (cross-device falls back to `shutil.move`), a same-filesystem rename's **inode is verified** to be preserved (a mid-move swap is detected and refused), and the destination directory is `fsync`-ed for crash durability. `undo.undo_manager.UndoManager` makes the post-rollback status flip **transactional/idempotent** (race B3): the undo/redo status transition is now a single conditional `UPDATE ... WHERE id = ? AND status …` + commit, and a zero-row result (a concurrent undo/redo already flipped it) returns `False` instead of double-counting or clearing the redo stack twice. (Full cross-device crash-safe `durable_move` and journal-backed crash recovery remain WP-1.2b, #1248, which this path will adopt once landed.)
- **Watcher event symlink/containment hardening (WP-2.3, pull-back from fo-core, #1228)** — `watcher.handler.FileEventHandler` now screens every event through a fail-closed guard (`_is_event_path_allowed`) before debounce/enqueue: the path is canonicalized with `Path.resolve()` and must live inside one of the resolved watch roots, every component from the matched root down to the leaf is `os.lstat`-checked so a symlink at *any* level is refused (not just the leaf — a symlinked ancestor that resolves back under the root would otherwise be enqueued as a TOCTOU foothold), and any resolution/stat failure (symlink loop, OS error) is treated as unsafe and skipped. For `MOVED` events the **destination** is used as the effective path for filtering, containment, debounce, and `FileEvent.path`, since the destination is the live, to-be-organized file (the source no longer exists); the source is used only when no destination is supplied. This stops a symlink planted in (or a move targeting outside) the watched tree from driving a downstream read/organize of out-of-root content (fo-core#322). When no watch roots are configured the guard is inert (a standalone handler keeps working). `watcher.monitor.FileMonitor.add_directory` now keeps `config.watch_directories` in sync when a directory is added mid-run, so dynamically-added roots are reflected in the containment boundary (and re-watched on restart).
- **Runtime adoption of safety primitives (WP-1.x/WP-2.1 follow-up, #1269)** — three merged-but-dormant hardening primitives are now active at production boundaries:
  - **Credential-redaction installed at startup** — `utils.log_redact.install_on_root()` is now invoked from the CLI callback (`cli.main`), API logging setup (`api.main.configure_logging`), and the desktop launcher (`desktop.app.launch`), so stdlib + loguru output is scrubbed of token/key shapes process-wide instead of relying on each caller to install the filter. Tests assert redaction through the real CLI/API/desktop startup paths.
  - **CLI path validation wired in** — `cli.organize.organize`/`preview` now route their path arguments through `cli.path_validation.resolve_cli_path` (missing / non-directory / symlink-loop → `typer.BadParameter`, exit 2) and `validate_pair` (identical, output-inside-input, input-inside-output rejected) before any filesystem work. The input root is resolved with `reject_symlink=True` so a symlinked input directory is refused rather than canonicalized to its target (which would bypass the `safe_walk` root-symlink rejection).
  - **Dedup extractor anchored traversal** — `DocumentDeduplicator.find_duplicates`/`compare_documents` → `DocumentExtractor.extract_batch`/`extract_text` → `_open_binary` accept an optional trusted `scan_root`; when supplied, reads use `SafeDir.open_anchored_reader` so a symlinked *ancestor* swapped in between enumeration and extraction is refused (`..`/out-of-root paths rejected before any legacy fallback), closing the nested-ancestor TOCTOU the parent-rooted path left open (#286). `scan_root=None` preserves the existing parent-rooted leaf-safe behaviour.

### Fixed

- **Test mocks for the `scan_root` read-path contract (WP-2.1 follow-up)** — integration/parallel test doubles that replace `TextProcessor.process_file` (`test_organize_text_workflow`, `test_dedupe_flow`, `test_parallel_execution`, `test_undo_workflow`) now accept the keyword-only `scan_root` argument the dispatcher forwards since the SafeDir text-processor hardening (#1259). Previously these mocks raised `TypeError: got an unexpected keyword argument 'scan_root'`, so every file was marked failed — failing the full sharded `main` suite (and silently degrading `test_undo_workflow`, whose restore-state assertions passed trivially when nothing organized). No production-code change.

### Security

- **Pipeline writer-stage destination/source symlink hardening (WP-2.2, pull-back from fo-core)** — `pipeline.stages.writer.WriterStage` now copies through a new `_copy_via_safedir` helper instead of `shutil.copy2`. On POSIX the **destination** is opened under `SafeDir.open_root(destination.parent).open_child(..., O_WRONLY|O_CREAT|O_TRUNC)` (`open_child` always adds `O_NOFOLLOW`): a symlink pre-planted at the destination (e.g. `output/Docs/report.txt -> ~/.ssh/authorized_keys`) is refused with `SymlinkRejected` instead of followed, so the write cannot escape the output tree (fo-core#322); an existing *regular* file is still truncated/overwritten (copy2 parity). The **source** is opened `O_NOFOLLOW` too, so a symlinked source swapped in after enumeration is refused rather than dereferenced into the output (fo-core#354). `copy2`'s permission-bit + atime/mtime contract is replicated via fd-based `os.fchmod`/`os.utime` (the source is re-`fstat`-ed *after* the read so `relatime` atime matches `copy2`). copy2's other guards are preserved too: non-regular sources/destinations (FIFO/device/socket) are refused with `SpecialFileError` (the source is opened `O_NONBLOCK` so a swapped-in FIFO can't hang the worker), a same-inode copy (identical path or a hard link to the source) is detected race-free via a post-open `fstat` before truncation and refused with `SameFileError`, and extended attributes (`user.*`, SELinux labels) are copied best-effort to match `copystat`. Falls back to `shutil.copy2` on Windows / where SafeDir is unavailable. (Leaf-symlink protection; anchored traversal closing the symlinked-*ancestor* vector is tracked as a follow-up, #1268.)
- **Organize-pipeline traversal symlink hardening (WP-2.2, pull-back from fo-core)** — `core.file_ops.collect_files` now enumerates the scan tree via `core.path_guard.safe_walk` (skips symlinked files/dirs and hidden entries) instead of a raw `os.walk`: a symlink planted in the input tree (e.g. `escape -> /etc/passwd`) is no longer collected, organized, or read downstream, closing the symlink-exfiltration surface at the entry point of the organize pipeline (fo-core#270, WP-2.2 #1227). A directly provided symlinked input file is also rejected (`is_file()` follows symlinks, so it would otherwise be copied by `shutil.copy2`, exfiltrating its target). `core.file_ops.cleanup_empty_dirs` likewise switches its `rglob("*")` walk to `safe_walk(only_files=False, include_hidden=True)` so empty-directory cleanup never descends through a directory symlink while still removing empty hidden dirs. Behaviour for ordinary files is unchanged. `safe_walk` filters symlinks and hidden entries on every platform.
- **Dedup text-extractor read-path symlink hardening (WP-2.1, pull-back from fo-core)** — `services.deduplication.extractor.DocumentExtractor` now opens every format (PDF/DOCX/TXT/RTF/ODT) through a new `_open_binary` helper that on POSIX reads via `SafeDir.open_root(parent).open_for_reader(name)` (`O_NOFOLLOW`): a symlinked leaf swapped in between dedup enumeration and extraction is refused (`SymlinkRejected` → handled → empty text, file skipped) rather than dereferenced (WP-2.1, #1261/#1226). Falls back to a plain binary `open` on Windows / where SafeDir is unavailable. Also broadens `_extract_docx` error handling to catch `BadZipFile` from the fileobj branch. (Parent-rooted; the nested-ancestor anchored variant is a follow-up.)
- **Text-processor read-path symlink hardening (WP-2.1, pull-back from fo-core)** — `services.text_processor.TextProcessor.process_file` gained an opt-in `scan_root` keyword that routes content reads through `read_file_via_safedir_anchored` on POSIX: a symlink swapped in between the organize-time scan and the classification read is refused (`SymlinkRejected` → error result, file not organized) rather than dereferenced, closing the LLM-exfiltration vector in the main text-organize path (#264/#286, WP-2.1 #1226). `core.organizer` threads the trusted `input_path` through `dispatcher.process_text_files`; `scan_root=None` keeps the legacy path-based read, so existing behaviour is unchanged. Falls back to the legacy reader on Windows.
- **Dedup ODT extractor XXE hardening (WP-2.1, pull-back from fo-core)** — `services.deduplication.extractor.DocumentExtractor._extract_odt` now parses the untrusted `content.xml` pulled from an ODT archive via `defusedxml.ElementTree.fromstring` instead of the stdlib parser, refusing internal/external-entity and entity-expansion (billion-laughs) payloads (raised as `EntitiesForbidden`/`DTDForbidden`, caught → empty text) rather than processing them (WP-2.1, #1226). `defusedxml` is added as a core dependency so the hardening is always active.
- **Content-dedup hash read-path symlink hardening (WP-2.1, pull-back from fo-core)** — `core.organizer`'s content-based deduplication now computes the SHA-256 digest via a new `_sha256_via_safedir` helper that reads through `SafeDir` on POSIX: a symlink swapped in between organize-time enumeration and the hash read is refused (`SymlinkRejected` → `None` hash, file kept) rather than dereferenced, closing the symlink-exfiltration vector in the dedup hash path (WP-2.1, #1226). An optional `scan_root` enables anchored traversal (`SafeDir.open_anchored_reader`) closing the nested-ancestor TOCTOU. Falls back to the legacy reader on Windows.
- **PARA classification read-path symlink hardening (WP-2.1, pull-back from fo-core)** — `methodologies.para.detection.heuristics._extract_content` now reads the file preview via a new `_read_content_bytes` helper that routes through `SafeDir` on POSIX: a symlink swapped in between detection and the content read is refused (`SymlinkRejected` → metadata-only fallback) rather than dereferenced, closing the symlink-exfiltration vector in the PARA classification path (WP-2.1, #1226). A defensive non-positive-`limit` guard preserves the preview cap. Falls back to the legacy reader on Windows.
- **SafeDir reader dispatch (WP-2.1, pull-back from fo-core)** — added `utils.readers.read_file_via_safedir` (parent-rooted) and `read_file_via_safedir_anchored` (anchored traversal closing the nested-ancestor TOCTOU), which open a file through `SafeDir`'s `O_NOFOLLOW` fd and dispatch to the format readers via a new `fileobj=` entry point. All readers (`documents`/`archives`/`ebook`/`scientific`/`cad`) gained fileobj support plus an `os.fstat`-based `_check_fd_size` cap, and a scientific stub keeps the dispatch importable when those optional deps are absent. This is the read primitive the remaining WP-2.1 call sites (text_processor, dedup extractor) build on; existing path-based `read_file` behaviour is unchanged (#1226). Resource-cap optimizations (lazy-PDF streaming, STEP byte-cap) are left to WP-3.1.
- **Search corpus read-path symlink hardening (WP-2.1, pull-back from fo-core)** —
  `services.search.hybrid_retriever.read_text_safe` now reads corpus files via `SafeDir` on POSIX:
  a symlink swapped in between corpus enumeration and the content read is refused (`SymlinkRejected`
  → empty string) rather than dereferenced, closing the LLM-exfiltration vector (#264). A new
  optional `scan_root` argument switches to `SafeDir.open_anchored_reader`, validating every
  intermediate directory with `O_NOFOLLOW` to also close the nested-ancestor TOCTOU window
  (#286/#325). A defensive `limit<=0` clamp prevents bypassing the corpus byte cap. Falls back to
  the legacy reader on Windows.
- **Image-dedup read-path symlink hardening (WP-2.1, pull-back from fo-core)** — added
  `services.deduplication.image_utils.safedir_image_open`, a context manager that routes
  `PIL.Image.open` through a `SafeDir`-opened fd on POSIX (refusing a symlink swapped into the
  organize root with `SymlinkRejected`), with optional `trusted_root=` anchored traversal
  (`open_subdir` per component) to close the nested-ancestor TOCTOU. All `image_utils` readers and
  `ImageDeduplicator` now use it; `get_image_hash` converts the SafeDir-opened image to a numpy array
  and calls `imagededup.encode_image(image_array=...)` to bypass imagededup's path-based open, threads
  `trusted_root` from `find_duplicates`, and the directory walk now skips symlinked entries (#264/#286).
  Falls back to the legacy reader on Windows.

- **EPUB read-path symlink hardening (WP-2.1, pull-back from fo-core)** — `utils.epub_enhanced` now
  reads EPUBs via `SafeDir` (`_read_epub_safedir`): on POSIX the file is opened with
  `O_NOFOLLOW`/`dir_fd` and a symlink swapped in after the directory walk is refused with
  `SymlinkRejected` instead of being dereferenced, closing the symlink-following surface in the
  enhanced-EPUB ingestion path (#264). Falls back to the legacy reader on Windows. Requires
  `ebooklib>=0.20` for the fileobj branch.

### Added

- **Atomic write primitive (WP-1.2, pull-back from fo-core)** — added
  `file_organizer.utils.atomic_write` (crash-safe temp+fsync+`os.replace` writers:
  `atomic_write_text` / `atomic_write_bytes` / `atomic_write_with`, plus `append_durable` for
  log-style files; preserves prior file mode on overwrite and fsyncs the parent directory on POSIX
  for rename durability). The durable-move / trash-GC crash-safety modules are split into a dedicated
  hardening work package (they need concurrency-protocol fixes found in review before landing).
- **Diagnostics primitives (WP-1.3, pull-back from fo-core)** — added
  `file_organizer.utils.log_redact` (`CredentialRedactingFilter`, `install_on_root`, fail-closed
  credential redaction of log messages / format args / exceptions for stdlib + loguru logging),
  `file_organizer.utils.cli_errors` (`format_validation_error` with difflib "did you mean"), and
  `file_organizer.services.inference_timer` (`time_inference` context manager). Modules only;
  process-wide install wiring deferred to the CLI wiring follow-up. (`error_taxonomy` deferred to
  WP-4.1, where it is wired against the dispatcher's real result shapes and error strings.)
- **Path-safety primitives (WP-1.1, pull-back from fo-core)** — added `file_organizer.utils.safedir`
  (`SafeDir`, a POSIX `dir_fd`+`O_NOFOLLOW` primitive that rejects symlink traversal and path-component
  injection, raising `SymlinkRejected`), `file_organizer.core.path_guard` (`validate_within_roots`,
  `safe_walk`, `PathTraversalError`), and `file_organizer.cli.path_validation` (`resolve_cli_path`,
  `validate_pair`). Foundation for the symlink/TOCTOU hardening series; not yet wired into call sites.

### Changed

- **Desktop app consolidated on pywebview** — removed the Tauri v2 / Rust / sidecar architecture
  in favour of a pure-Python approach: a single `file-organizer-desktop` process starts uvicorn in
  a daemon thread and displays the web UI in a native OS window via pywebview. No Rust toolchain,
  no npm, no sidecar renaming steps required.
- **Build pipeline** — `python scripts/build.py --desktop` now produces a standalone pywebview
  desktop binary (`file-organizer-desktop-{version}-{platform}-{arch}`) via PyInstaller, in
  addition to the existing CLI binary.
- **CI** — `build.yml` no longer requires the Rust toolchain or `cargo test`; the `test-rust`
  job has been removed and `release` now depends only on `build`.

### Removed

- `desktop/src-tauri/` — Rust source, Cargo.toml, tauri.conf.json, capabilities, build.rs
- `desktop/package.json` — npm/Tauri dev scripts
- Sidecar copy steps from `scripts/build_linux.sh`, `scripts/build_macos.sh`,
  `scripts/build_windows.ps1`, and `scripts/build_windows.iss`
- `TAURI_SIGNING_*` environment variables from CI workflow

### Security

- Accepted risk for `ecdsa` (GHSA-wj6h-64fc-37mp, HIGH): transitive via `python-jose`; JWT algorithm is HS256 so `ecdsa` is never invoked
- Accepted risk for `diskcache` (GHSA-w8v5-vhqr-4h9v, MODERATE): transitive via `llama-cpp-python`; never imported by application code

## [2.0.0-alpha.3] - 2026-03-26

### Quality & Stability Summary

This release contains **zero new user-facing features**—it is a pure quality and stability release covering 50 commits between March 9-26, 2026. The focus is on test infrastructure hardening, bug fixes, dependency updates, and security improvements that raise the project's reliability floor.

### Changed

- **Core Module Complexity Reduction** (#977): Refactored core modules to reduce cognitive complexity and improve maintainability
- **Test Parametrization** (#965, #966): Converted repetitive test cases to parametrized tests, reducing code duplication and improving coverage
- **Test Organization** (#964): Moved private helper tests to dedicated unit module for better test suite organization

### Fixed

- **Test Failures** (#969): Addressed 7 test failures across main test suite
- **pytest-timeout Compatibility** (#970): Pinned `pytest-timeout<2.4.0` to fix Windows CI crash
- **Path Keyword Matching** (f9ff398): Fixed feature extractor to match path keywords as exact components, not substrings
- **File Count Accuracy** (#937): Fixed deduplicated file counting in `OrganizationResult`
- **Threading Synchronization** (507cb35): Replaced busy-wait loop with `threading.Event().wait()` in test_warmup
- **Integration Test Stability** (#945): Fixed 5 failing integration tests on main branch
- **Flaky Assertions** (5b25653): Widened caplog scope to fix flaky cache-hit log assertion on Python 3.12

### Added

#### Testing & CI Improvements

- **Coverage Expansion**: Increased test coverage from 30% to 60% with ~4,500 new tests across integration, branch-coverage, and unit test suites
- **Branch Coverage** (#915): Enabled branch coverage tracking and established ratcheting coverage floors
- **Diff-Cover Gate** (#940): Added diff-cover gate to pre-commit validation to enforce coverage on changed lines
- **CI Guardrails**: Added 5 new guardrail categories:
  - T10 predicate negative-case guardrail (#939, #942)
  - MECE-hardened correctness, memory-lifecycle, and security guardrails (#935)
  - Search S1/S2 AST matching for corpus safety (#928, #929)
  - Phase 4 pre-commit hooks for threshold drift detection (#927)
  - isinstance assertion detection and enforcement (#926)
- **Integration Test Infrastructure** (#954): Added AsyncClient, CliRunner, and FakeTextModel fixtures
- **Integration Test Suites**:
  - 211 tests for methodologies, events, parallel processing (#963)
  - 4,112 integration tests ratcheting coverage 45%→60% (#961)
  - Web + plugins integration tests (#960)
  - API + web integration tests (#958)
  - CLI + models integration tests (#957)
  - 212 branch-coverage tests (#953, #949)
  - Branch-coverage tests for low-coverage modules (#947)

### Security

- **PyPDF2 Migration** (#848): Migrated PDF extraction from `PyPDF2` to `pypdf` (successor package) to resolve GHSA moderate vulnerability in `PyPDF2 3.0.1`
- **GitHub Actions Updates**: Bumped 6 GitHub Actions to latest versions:
  - `actions/upload-artifact` from 4 to 7 (#974)
  - `codecov/codecov-action` from 4.6.0 to 5.5.3 (#973)
  - `docker/metadata-action` from 5 to 6 (#975)
  - `docker/login-action` from 3 to 4 (#972)
  - `github/codeql-action` from 3 to 4 (#971)
  - `actions/checkout` from 5 to 6 (#875)
- **Rust Dependencies**: Updated 2 Rust dependencies:
  - `rustls-webpki` (#932)
  - `tar` (#923)
- **Risk Acceptance**:
  - Accepted risk for `ecdsa` (GHSA-wj6h-64fc-37mp, HIGH): transitive via `python-jose`; JWT algorithm is HS256 so `ecdsa` is never invoked
  - Accepted risk for `diskcache` (GHSA-w8v5-vhqr-4h9v, MODERATE): transitive via `llama-cpp-python`; never imported by application code

## [2.0.0-alpha.2] - 2026-03-09

### Added

- **Copilot Chat Interface** (#26): Natural-language AI assistant for file organisation
  - Interactive REPL and single-shot CLI modes
  - Intent parsing with 11 intent types (organize, move, rename, find, undo, redo, preview, suggest, status, help, chat)
  - Multi-turn conversation management with sliding-window context
  - TUI panel accessible via key `8`
- **Copilot Rules System** (#29): Automated file organisation rules
  - CRUD operations with YAML persistence
  - 8 condition types (extension, name pattern, size, content, date, path)
  - 7 action types (move, copy, rename, tag, categorize, archive, delete)
  - Preview engine for dry-run evaluation
  - CLI commands: list, sets, add, remove, toggle, preview, export, import
- **Auto-Update Mechanism** (#23): Self-updating from GitHub Releases
  - Version checking against GitHub Releases API
  - SHA256-verified downloads
  - Atomic binary replacement with backup/rollback
  - CLI commands: check, install, rollback
- **PyInstaller Build Pipeline** (#28): Cross-platform executable packaging
  - Build script with platform detection and spec generation
  - GitHub Actions CI for macOS (arm64/x86_64), Windows, Linux
- **macOS Packaging** (#14): DMG installer with optional code signing/notarization
- **Windows Packaging** (#16): Inno Setup installer with PATH integration
- **Linux Packaging** (#20): AppImage and tarball distribution
- **Integration Tests** (#12): 192 new tests across copilot, rules, updater, TUI, CLI, config, and build
- **User Documentation** (#13): User guide, CLI reference, configuration guide, troubleshooting

### Phase 2 Completion Summary

- Phase 2 (Enhanced UX) is now 100% complete: 24/24 tasks done
- TUI with 8 navigable views (Files, Organized, Analytics, Methodology, Audio, History, Settings, Copilot)
- Full CLI with 30+ sub-commands across 8 command groups
- 3,146 tests passing across Python 3.11-3.12
- ~54,000 LOC across 184 modules

## [2.0.0-alpha.1] - 2026-01-15

### Added

- Phase 1: Core text and image processing with Ollama
- Phase 3: Audio processing, PARA/JD methodologies, CAD/archive/scientific formats
- Phase 4: Deduplication, user preference learning, undo/redo, analytics
- Phase 5: Event system, daemon, Docker, CI/CD pipeline
