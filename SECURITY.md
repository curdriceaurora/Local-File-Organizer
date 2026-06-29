# Security Policy

## Security Architecture

File Organizer processes user-supplied file paths and file contents from
the local filesystem. The primary attack surfaces are path traversal
(a caller-supplied path escaping the intended directory tree via `..`
or a symlink) and resource exhaustion (oversized/malicious archive,
image, or document inputs). The codebase addresses these with three
primitives, all under `src/file_organizer/utils/` and
`src/file_organizer/core/`:

- **`SafeDir`** (`utils/safedir.py`) — the path-safety primitive.
  `open_child()` / `open_for_reader()` / `open_subdir()` /
  `open_anchored_reader()` / `open_anchored_writer()` / `lstat()` /
  `mkdir()` / `unlink()` / `rename_into()` reject any path component
  that would escape the rooted directory, including symlink-based
  escapes, and raise `ValueError` on rejection. Call sites are expected
  to let that `ValueError` propagate or handle it explicitly — see the
  `safedir-valueerror` lint rail below.
- **`atomic_write()` / `durable_move()`** (`utils/atomic_write.py`,
  `undo/durable_move.py`) — crash-safety primitives. Writes go through a
  temp-file-plus-`os.replace()` sequence so a crash mid-write never
  leaves a truncated file in place of a previously-good one; moves
  verify `(st_dev, st_ino)` identity after `os.replace()` to detect a
  symlink swap mid-move.
- **`PidFileManager.claim_pid_file()`** (`daemon/pid.py`) — an
  `O_CREAT|O_EXCL` atomic claim closing the daemon-startup TOCTOU race
  between checking whether a PID file exists and writing one.

Web/API surfaces (`src/file_organizer/web/`, `src/file_organizer/api/`)
additionally rely on FastAPI/Starlette's built-in request validation,
CSRF middleware (`web/csrf.py`), and `defusedxml` for any XML parsing
(see the `defusedxml-fallback` rail below) to avoid XXE.

Static type checking (`mypy`, `strict = true` repo-wide) and linting
(`ruff`) run on every commit; see Lint Rails below for the
project-specific AST checks layered on top of both.

## CI-Enforced Lint Rails

The rails below are AST-based static checks run via
`scripts/ci/ci_rails.py` (registry: `scripts/ci/rails.toml`),
either as a pre-commit hook or in CI. Rails with no current violations
are **enforced**; rails with pre-existing violation backlogs remain
**advisory** until their cleanup issues are resolved.

| Rail | What it flags | Status |
|---|---|---|
| `safedir-required` | Raw `open()`/`Path.open()`/`shutil.copy*`/`shutil.move` outside the `SafeDir` primitives themselves | advisory |
| `atomic-write` | Raw file-write operations bypassing `atomic_write()` | advisory |
| `cli-path-validation` | A CLI command's `Path` parameter not wrapped in `resolve_cli_path()` | advisory |
| `defusedxml-fallback` | Importing from stdlib `xml` instead of `defusedxml` | enforced |
| `test-hardcoded-paths` | Hardcoded absolute paths in tests (use `tmp_path`) | advisory |
| `test-separator-paths` | Hardcoded path separators in `Path(...)` calls in tests | advisory |
| `pytest-raises-hygiene` | `pytest.raises()` without a `match=` regex on a generic/built-in exception | advisory |
| `safedir-valueerror` | A broad `except Exception`/bare `except` around a `SafeDir` call that doesn't re-raise or catch `ValueError` explicitly | enforced |
| `textiowrapper-detach` | An `io.TextIOWrapper` that is never `.detach()`-ed before going out of scope (use-after-close risk on the wrapped buffer/fd) | enforced |
| `called-attribute-assertion` | Weak `assert mock.called` / bare `assert mock.call_count` test assertions | advisory |
| `xdist-loadgroup` | A test using the xdist-wide `tmp_path_factory.getbasetemp()` without an `xdist_group` marker | enforced |

Per-file coverage floors (`check-integration-floors.py` for the
integration suite, `check_module_coverage_floor.py` for the unit suite)
are wired as direct CI workflow steps in `ci.yml` — run immediately
after the pytest step that produces their input coverage JSON — rather
than through the rail registry above, since `ci_rails.py` has no
step-ordering concept and both checks depend on a coverage artifact
from an earlier step in the same job.

Lint/type config (separate from the AST rails above, enforced
unconditionally, not advisory):

| Check | What it does |
|---|---|
| `ruff check` (incl. `PT012`/`PT017`/`PT022`) | Style, correctness, and pytest-hygiene lint, including pytest.raises()-block hygiene |
| `mypy src/file_organizer/` | Strict type checking across the whole package (see Known Limitations for the ratchet exemption) |

Supply-chain scanning (run in `.github/workflows/security.yml`):

| Check | What it does | Status |
|---|---|---|
| `pip-audit` | Scans installed dependencies against the OSV database | **enforced** via `scripts/security/pip_audit_gate.py`, findings suppressible only via a documented entry in `.github/accepted-risks.yml` |
| `bandit` | Static analysis for common Python security anti-patterns | advisory (`\|\| true`) — see Known Limitations |
| `codeql-analysis` | GitHub's semantic code-scanning | enforced |

## Known Limitations

- **`bandit -r src/` is not gated.** After triaging and annotating the
  non-cryptographic weak-hash call sites, the remaining findings are
  low/medium severity and still need review before this job can become
  blocking. Tracked as
  [#1344](https://github.com/curdriceaurora/Local-File-Organizer/issues/1344).
- **mypy's `strict = true` config is repo-wide, but 41 files are
  exempted** via a dated `[[tool.mypy.overrides]] ignore_errors = true`
  ratchet baseline (see `pyproject.toml`, "WP-6.4 ratchet baseline").
  New files get full enforcement; the 41 existing ones are fixed
  incrementally — remove an entry as its file is cleaned up.
- **Most lint rails above are advisory, not enforced.** Each advisory
  rail still has pre-existing violations that predate the rail's
  enforcement. Flipping a rail to `enforce` requires first reducing its
  violation count to zero (or to an explicitly accepted/`noqa`-tagged
  remainder). The remaining advisory rails are tracked individually in
  #1363 through #1370.

## Reporting a Vulnerability

We take the security of Local-File-Organizer seriously. If you believe
you have found a security vulnerability in this project, please report
it via a private GitHub Security Advisory on this repository rather
than a public issue:

<https://github.com/curdriceaurora/Local-File-Organizer/security/advisories/new>

Please include:

- Type of vulnerability (e.g., path traversal, XXE, symlink race, etc.)
- Full details of the environment (OS, Python version, etc.)
- A detailed description of the vulnerability including steps to reproduce
- Any proof-of-concept code or screenshots

### Response Timeline

You should receive an acknowledgment of your report within 48 hours. We
will do our best to triage and address the issue within a reasonable
timeframe (typically 7-14 days). Once the issue is resolved and a patch
is released, we will publicly acknowledge your contribution (if desired).

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| v2.0.x  | :white_check_mark: |
| < 2.0   | :x:                |
