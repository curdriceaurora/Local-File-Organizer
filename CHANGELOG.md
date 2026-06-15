# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

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
