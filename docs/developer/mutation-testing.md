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
the module being mutated — adding one thread-using test file to an otherwise
clean profile is enough to break it:

- *Segfaults.* Broad test paths drag in ~240 native extension modules (torch,
  av, scipy) and the fork crashes. mutmut records the crash as a mutant
  verdict, so a profile can report a perfect score built entirely on
  corpses — the pilot's own first run showed the grouped optimization profile
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

Those tests create threads, and mutmut forks a process per mutant. This is the
same root cause as `parallel`'s hang — one surfaces as a crash, the other as a
deadlock — so neither is fixable by narrowing imports or tuning workers. It
needs a non-forking runner (#1726).

An earlier version of this page blamed the organizer module's module-scope
`av`/`torch` imports. That was wrong: making them lazy cut the module's import
from 2,839 to 1,665 modules and removed av/torch entirely, and the segfault
count did not move by one.

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
