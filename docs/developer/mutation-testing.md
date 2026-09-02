# Mutation Testing

Mutation testing changes the source, reruns the tests, and asks whether
anything noticed. A test suite can have high coverage and still assert
nothing; a surviving mutant is proof of exactly that, found without knowing
the failure mode in advance.

This is a **pilot** (#1684, epic #1678), not suite-wide adoption. Mutation
runtime is test runtime multiplied by mutant count, and this suite is ~22.5k
tests. Three small modules are covered — the ones the epic's repair waves
touched most, so the score answers "did those repairs actually catch
anything".

## Running it

```bash
pip install --no-deps "mutmut==3.7.0" libcst
python scripts/ci/mutation_pilot.py --list          # show profiles
python scripts/ci/mutation_pilot.py batch-sizer     # one profile
python scripts/ci/mutation_pilot.py                 # all of them
```

`--no-deps` is required. mutmut declares `textual>=1.0` and this project pins
`textual~=0.50` for the TUI; letting pip resolve mutmut's dependencies
upgrades textual and breaks the TUI suite. `run`, `results` and
`export-cicd-stats` all work against the pinned version — only `mutmut browse`
needs the newer API, so use `mutmut results` instead.

In CI this runs nightly via `.github/workflows/mutation.yml`, which also
accepts a manual dispatch. It never runs on a pull request.

## Reading the output

```text
-- batch-sizer: mutating 1 module(s)
   killed  129  survived   65  no-tests    0  score 66.5%
```

- **killed** — the mutant broke a test. Good.
- **survived** — the source changed and every test still passed. Either a
  missing assertion or an equivalent mutant.
- **no-tests** — no test exercises that line at all. That is a coverage
  question, gated separately, and it is excluded from the score so a coverage
  change cannot move the mutation number on its own.

Score is `killed / (killed + survived)`.

!!! warning "mutmut's emoji legend is easy to invert"
    In the live progress line `🙁` is **survived** and `🫥` is **no tests**.
    Reading them the other way round turns a 66.5% score into a reported
    100%. Prefer the driver script's wording, or
    `mutmut export-cicd-stats`, over the progress bar.

## Three things that make the numbers meaningless if you skip them

These are encoded in `scripts/ci/mutation_pilot.py`. They are recorded here
because each one fails quietly, producing a confident number that measures
the wrong thing.

**1. Coverage must be off.** The project's pytest `addopts` carry
`--cov-fail-under=93`. Under mutation that gate fails for nearly every mutant,
pytest exits non-zero, and mutmut reads a non-zero exit as "the suite caught
it". Leaving coverage on reports a ~100% mutation score that reflects the
coverage gate and nothing else.

**2. Test selection must be narrow, and one module per profile.** mutmut
forks a process per mutant, and forking this test environment is fragile in
two distinct ways. Both are properties of the **test files** selected, not of
the module being mutated — adding one test file that reaches non-fork-safe
state to an otherwise clean profile is enough to break it:

- *Segfaults.* The fork crashes, and mutmut records the crash as a mutant
  verdict — so a profile can report a perfect score built entirely on
  corpses. The pilot's own first run showed the grouped optimization profile
  and `organizer` at 100% with 268 and 432 mutants segfaulted. The driver
  treats any `segfault` in the stats as a hard error.
- *Deadlocks.* Thread-heavy test files (for example
  `tests/parallel/test_processor_thread_safety.py`) make the forked children
  sit asleep forever, consuming no CPU. mutmut's own per-mutant timeout never
  fires because the child never starts. The driver imposes a per-profile
  wall-clock `--timeout` and reaps the strays.

Both are why profiles are one module with its own test files, rather than one
profile per package. Grouping three optimization modules with the whole
`tests/optimization` directory segfaulted; splitting them into three profiles
of one module and two test files each runs clean.

**3. Config lives in a generated `setup.cfg`.** mutmut reads `[tool.mutmut]`
from `pyproject.toml` when that section exists and only falls back to
`setup.cfg` otherwise. Keeping `pyproject.toml` free of it is what lets the
driver vary `only_mutate` and test paths per profile. The generated file is
temporary and removed after each run — do not commit one.

## Baselines

Measured 2026-08-08. Floors sit ~3 points below the baseline: scores here are
deterministic (`pytest-randomly` is disabled for these runs), so the margin
absorbs test additions changing the denominator, not run-to-run noise.

| Profile | Killed | Survived | Score | Floor |
| :--- | ---: | ---: | ---: | ---: |
| `batch-sizer` | 129 | 65 | 66.5% | 63% |
| `memory-limiter` | 67 | 17 | 79.8% | 76% |
| `memory-profiler` | 96 | 23 | 80.7% | 77% |
| `parallel` | 233 | 291 | 44.5% | blocked |
| `organizer` | — | — | blocked | — |

Two of the five targets are blocked, for different reasons. Blocked profiles
are skipped in a default run — announced, never silently — and still run when
named explicitly, so progress on the blocker stays measurable.

**`parallel` deadlocks intermittently.** It completed twice (44.5% against
`test_processor.py` alone) and hung twice, forked children asleep at zero CPU
until `--timeout` reaped them. A gate that hangs half the time is worse than
no gate. Its 44.5% is also the weakest score in the pilot and understates the
problem further, since `test_processor_thread_safety.py` and
`test_concurrency_fixes.py` — the tests most worth mutating — are exactly the
ones that trigger the hang.

**`organizer` segfaults**, 432 mutants — and the cause is the *test files*,
not the module. Two controlled runs establish it:

- Mutating the known-clean `batch_sizer.py` while merely adding
  `tests/core/test_organizer.py` to the selection produces 42 segfaults, where
  that profile is otherwise 129 killed / 65 survived / 0 crashed.
- `--max-children 1` changes nothing (42 either way), so it is the fork
  itself, not concurrency between children.

### Confirmed root cause (Darwin only)

The crash is **not** about thread count, and it is **not** portable. macOS
records it as `EXC_BAD_ACCESS` with this faulting stack:

```
libsystem_trace   _os_log_find          <- fault
libsystem_trace   os_log_create
libsqlite3        __sqlite3GetLog_block_invoke
libdispatch       _dispatch_once_callout
libsqlite3        openDatabase
_sqlite3.so       pysqlite_connection_init
```

Darwin's `fork(2)` contract is the blocker: after `fork`, the child must not
call into frameworks or libraries unless they are async-signal-safe or
explicitly documented as safe after fork. mutmut's execution model forks a
child for each mutant and does not `exec`; the child depends on the parent's
warmed interpreter and collected test state. That makes the affected profiles
outside the documented platform contract on macOS, independent of whether a
specific Apple crash changes in a future release.

Apple's system `libsqlite3` is the confirmed mechanism for the organizer
profile. It lazily builds its log handle via `dispatch_once` ->
`os_log_create`, and libdispatch is not fork-safe — so any child that opens a
database can fault. The organizer tests reach sqlite3 through `execute_plan` ->
`UndoManager` -> `HistoryTracker`, which is why adding that file is what
triggers it.

Three predictions confirm the mechanism:

- Pre-opening a connection in the *parent* makes the crash **deterministic**
  (20/20 rather than an intermittent ~0-or-10/10), because the child inherits
  the "already initialised" `dispatch_once` flag and skips re-initialising a
  handle that is invalid post-fork. Pre-warming is the wrong fix.
- Within one process the outcome is all-or-nothing; it varies *between*
  processes, which is why per-run counts looked erratic.
- **Linux is immune**: 0/20 with and without pre-warm on `python:3.12-slim`,
  versus 20/20 on macOS.

`.github/workflows/mutation.yml` runs on `ubuntu-latest`, so the Darwin block
does not apply where the nightly actually runs. Both profiles still need Linux
measurement before floors are set (#1740), but the macOS guidance is not to
wait for an upstream fix: run the affected profiles in a Linux container or on
Linux CI.

Two earlier explanations on this page are **retracted**:

- *Module-scope `av`/`torch` imports.* Making them lazy cut the module's import
  from 2,839 to 1,665 modules and removed av/torch entirely, and the segfault
  count did not move by one.
- *"Those tests create threads."* Only one Python thread is alive at fork time.
  The relevant call is `sqlite3.connect()` in the child, not thread count.

### How blocks are scoped

`Profile.blocked` records *why* a target is skipped; `Profile.blocked_platforms`
records *where* that reason applies, as `sys.platform` values. A block with no
platform set applies everywhere, so existing entries keep their meaning.

`organizer` and `parallel` are scoped to `{"darwin"}`. They are permanently
skipped by default on a developer's Mac — loudly, with the reason — and run
normally on the `ubuntu-latest` nightly. `--list` distinguishes the two states
rather than printing a bare "BLOCKED", because a profile that is blocked
*somewhere* should not read as blocked *here*:

```
parallel   floor=not gated  BLOCKED here (darwin) — deadlocks intermittently ON macOS: ...
organizer  floor=not gated  BLOCKED here (darwin) — 432 mutants segfault ON macOS ONLY: ...
```

Naming a profile explicitly still runs it regardless of platform, so anyone
working on the blocker can measure progress.

**Both profiles are deliberately ungated** (`floor=None`). There is no measured
Linux baseline for either, and a guessed floor would fail the first nightly
that ran it. The sequence is: re-derive the Linux test selection, let the
nightly report scores, read two or three runs, then set floors ~3pp below the
observed value as the other profiles do. `scripts/ci/mutation_pilot.py
--enforce` ignores a profile whose floor is `None`, so this is report-only
until someone sets one.

## Validating the harness before trusting a score

A mutation score is only evidence if the harness can tell killed from
survived. Check it the same way you would check any other guard — break
something and confirm the number moves:

```bash
# neuter the assertions in a profile's test file, rerun, and compare
python scripts/ci/mutation_pilot.py batch-sizer
```

On the `batch_sizer` baseline, replacing every `assert X` with `_ = X` moved
16 mutants from killed to survived (66.5% → 58.2%). A harness that reports the
same score either way is measuring nothing, and that is the failure mode this
whole page exists to prevent.

## Adding a profile

Add a `Profile` to `PROFILES` in `scripts/ci/mutation_pilot.py` with the
modules to mutate and the test files that exercise them. Leave `floor` as
`None` until there is a measured baseline — a floor invented before the first
run is a number people route around rather than a bar they clear.
