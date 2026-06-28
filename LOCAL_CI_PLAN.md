# Replicating CI Locally (No GitHub-Hosted Runners)

Goal: reproduce the checks currently run by `.github/workflows/ci.yml`,
`ci-full.yml`, and `build.yml` without paying for GitHub-hosted runner minutes.

## Key facts that shape the plan

- Every *check* uses open-source tooling (ruff, mypy, pytest, deptry, interrogate,
  pymarkdown, playwright, pyinstaller). Nothing requires GitHub's hosted infra.
- The only GitHub-specific glue is orchestration: matrix, test sharding,
  `upload`/`download-artifact`, Codecov, `GITHUB_TOKEN`, and the PR-comment steps.
  None of that is part of the actual validation.
- Cross-OS testing is the one thing that genuinely needs that OS:
  Linux replicates anywhere, macOS replicates on your Mac, Windows needs Windows.
- `act` only runs Linux containers — it cannot reproduce the macOS or Windows legs.

## Strategy: three layers

1. **Linux + macOS**: run natively in local scripts (fast daily feedback).
2. **Windows**: register a real Windows box (or VM) as a **free self-hosted runner**.
3. **Branch protection**: adjust required checks so merges aren't blocked forever.

---

## Phase 0 — One-time environment setup (Mac)

```bash
cd /path/to/Local-File-Organizer

# Primary interpreter matches the test jobs (3.11 for PR suite, 3.12 for cross-platform).
python3.11 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev,search]" pre-commit
pip install "pytest-asyncio>=0.23.0" faker

# NLTK corpora the test suite imports at runtime
python -c "import nltk; [nltk.download(p, quiet=True) for p in ('stopwords','punkt','punkt_tab','wordnet')]"

# Only needed if you run the Playwright E2E job locally
python -m playwright install --with-deps chromium firefox webkit
```

If you want true matrix parity (py3.11 **and** 3.12), install both with `pyenv` or
`uv` and run the suite under each.

---

## Phase 1 — Linux jobs (`ci.yml`) as a local script

Create `scripts/local-ci.sh` that runs each job in order. Job → command mapping:

| CI job | Local command |
|---|---|
| `lint` | `pre-commit run --all-files` |
| `unused-deps` | `deptry src/` |
| `type-check` | `mypy src/file_organizer/models/` |
| `link-integrity` | the inline link-check bash block from `ci.yml` |
| `test` (PR suite) | `pytest tests/ --strict-markers -m "ci and not benchmark" --cov=file_organizer --cov-report=xml --timeout=30 -n=auto --override-ini="addopts="` |
| diff-cover gate | `diff-cover coverage.xml --compare-branch=origin/main --fail-under=80` |
| `test-full` | drop sharding: `pytest tests/ -m "not benchmark and not e2e" --cov=file_organizer -n=auto --override-ini="addopts="` |
| `coverage-gate` | `coverage report --fail-under=93` then `interrogate -v src/ --fail-under 95` |
| `test-integration` | `pytest tests/ -m integration --cov-branch --cov-fail-under=72.0 --override-ini="addopts="` then `python scripts/coverage/check-integration-floors.py` |
| `test-benchmark` | `pytest tests/ -m benchmark --benchmark-only --override-ini="addopts="` |
| `playwright` | loop `--browser chromium|firefox|webkit` over `pytest tests/playwright/ ...` |

Drop or adapt (not real checks):

- **Sharding / artifacts** — local coverage files are on disk; `coverage combine` reads
  them directly, no upload/download needed.
- **Codecov** — drop (it is `fail_ci_if_error: false` in CI anyway).
- **`GITHUB_TOKEN` + PR-comment / benchmark-baseline-comparison** — PR-only advisory,
  needs real GitHub; skip locally.

You already have ~70% of this in `scripts/dev/pre-commit-validation.sh` — reuse it.

Add a `make ci` target that calls `scripts/local-ci.sh`, and a git `pre-push` hook so
nothing broken reaches GitHub.

---

## Phase 2 — macOS jobs (run natively on your Mac)

### `ci-full.yml › test-macos`

Same venv as Phase 0 (Python 3.12), then:

```bash
PYTHONUTF8=1 pytest tests/ --strict-markers --timeout=30 -n=auto \
  --override-ini="addopts=" -m "ci or smoke"
```

### `build.yml` macOS legs (pyinstaller)

```bash
pip install -e ".[desktop,dev]" pyinstaller
python scripts/build.py --clean      # CLI executable
python scripts/build.py --desktop    # desktop executable
```

**Architecture catch:** GitHub builds both `macos-latest` (arm64) and
`macos-15-intel` (x86_64). On Apple Silicon a native build only produces arm64.
To keep the Intel artifact, either cross-build under an x86_64 Python
(`arch -x86_64 …` with an x86_64 Homebrew Python) or keep one Intel runner.
No extra system libraries are needed on macOS (the apt packages in `build.yml`
are Linux-only, for pywebview).

---

## Phase 3 — Windows jobs (needs Windows)

`ci-full.yml › test-windows` and the `build.yml` Windows leg cannot run on a Mac
with build parity. Pick one:

### Option A (recommended) — Spare Windows PC as a free self-hosted runner

1. On the Windows machine install Python 3.12 + Git.
2. In the repo: **Settings → Actions → Runners → New self-hosted runner**, choose
   Windows, follow the register/configure commands, run it as a service.
3. In `ci-full.yml`/`build.yml`, change the Windows job `runs-on: windows-latest`
   → `runs-on: [self-hosted, windows]`.
4. Workflows now run unchanged on your hardware — zero hosted minutes.

### Option B — Windows VM on the Mac (UTM/Parallels)

Good enough to run *tests*, but on Apple Silicon you get Windows-on-ARM:
tests run under x86 emulation, while a pyinstaller build produces an **ARM64**
artifact, not the x86_64 one GitHub ships. Use for test validation, not release builds.

### Windows-specific dependency notes (keep these)

- Same deps: Python 3.12, `pip install -e ".[dev,search]"`, NLTK downloads,
  `PYTHONUTF8=1`.
- **Omit `-n=auto`** on Windows — xdist worker shutdown sends `CTRL_C_EVENT` and
  fails an otherwise-green run. The `ci/smoke` subset is small enough that
  parallelism adds no benefit:

  ```bat
  set PYTHONUTF8=1
  pytest tests/ --strict-markers --timeout=30 --override-ini="addopts=" -m "ci or smoke"
  ```

- Build leg: `pip install -e ".[desktop,dev]" pyinstaller`, then `python scripts/build.py`
  produces `.exe` files (x86_64 on a real `windows-latest`-class machine).

---

## Phase 4 — Fix branch protection (do this or merges block forever)

`main-branch-protection.md` lists required status checks. If hosted runners stop
reporting, those checks never go green and **every merge is blocked**. Choose:

- **If you self-host** (Phases 1–3 via self-hosted runners): checks still report —
  leave protection as is.
- **If you gate purely locally**: remove the required-status-check rule and rely on
  the `pre-push` hook + `make ci` as the gate. Update `main-branch-protection.md`
  to match reality.

---

## Phase 5 (optional) — `act` for occasional full-fidelity Linux reruns

To reproduce a Linux CI failure exactly:

```bash
act pull_request -j lint            # run a single job
act pull_request                    # run the PR event
# pass secrets when a step needs them:
act pull_request --secret GITHUB_TOKEN=<token>
```

Needs Docker + large runner images. The `gh api` PR-comment and artifact steps
won't fully work (they need real GitHub). Use occasionally, not for daily feedback.

---

## What to run, when

- **Before every push** (fast): `pre-commit run --all-files` + `make ci` (Phase 1).
- **Before a PR merge**: Phase 1 full + macOS subset (Phase 2 test-macos).
- **Before a release tag**: Phase 2 + Phase 3 build legs to produce all artifacts.
- **Reproducing a specific CI failure**: `act` (Phase 5) or the self-hosted runner.

## Coverage thresholds to preserve (from current config)

- PR diff coverage: **≥80%** of changed lines (`diff-cover --fail-under=80`).
- Full-suite line coverage: **≥93%** (`coverage report --fail-under=93`).
- Docstring coverage: **≥95%** (`interrogate --fail-under 95`).
- Integration combined line+branch floor: **≥72.0%** (`--cov-fail-under=72.0`).
- Default `pyproject.toml` addopts gate: **≥95%** (overridden in job-specific runs).
