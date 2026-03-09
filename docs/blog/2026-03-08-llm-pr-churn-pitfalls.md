# PR Churn Pitfalls When Using LLM Tools — A Data-Driven Post-Mortem

*Published: 2026-03-08 | ~2,800 words | Tags: LLM, code-generation, PR-review, engineering-process*

---

## 1. The Setup

This project is unusual: **every line of production code was written by an AI**.
No human authored a function, test, or configuration file — Claude (Anthropic's
coding assistant) produced all of it across 115 pull requests covering
features, tests, documentation, CI pipelines, and refactors.

That makes this repository a controlled laboratory. When automated reviewers
(CodeRabbit and GitHub Copilot) flag problems, those findings are not noise from
an inconsistent human team. They are systematic gaps in AI code generation,
repeatable patterns that surface across every work type.

We ran a full audit: **1,830 reviewer findings across 115 PRs**, classified into
26 named anti-patterns across six work categories. This post shares what we
found and what it cost us.

---

## 2. The Problem: What Is PR Churn?

**PR churn** is the iterative back-and-forth between code generation and review
feedback that follows a predictable loop:

```text
generate → review → fix → re-review → fix again → ...
```

Each cycle carries a real cost:

- **Latency**: Every round trip adds minutes-to-hours of clock time.
- **Context loss**: LLMs don't remember previous sessions. Each fix cycle
  risks reintroducing problems that were already fixed, because the model no
  longer has the context of why a change was made.
- **Compounding errors**: A fix in one place can break something adjacent
  if the surrounding context is no longer in the model's active window.
- **Review fatigue**: Automated reviewers re-flag the same class of issue
  repeatedly, drowning signal in noise.

The worst outcome is not a bug — it is a pattern of bugs that never stops
appearing, because the root cause is in the *generation process* rather than
any specific piece of code.

---

## 3. The Data

### Overall Distribution

| Work Type | Findings | Share |
|-----------|----------|-------|
| TEST      | 634      | 34%   |
| FEATURE   | 590      | 32%   |
| DOCS      | 343      | 18%   |
| FIX       | 142      | 8%    |
| CI        | 84       | 5%    |
| REFACTOR  | 35       | 2%    |
| **Total** | **1,830**| 100%  |

Tests and features together account for two-thirds of all reviewer feedback.
This matters: the generation prompt for a test PR and the generation prompt for
a feature PR are very different, yet both produce roughly equal volumes of
churn.

### Top Anti-Patterns by Frequency

| Rank | ID  | Pattern              | Count | Work Type |
|------|-----|----------------------|-------|-----------|
| 1    | D5  | WRONG_FORMAT         | 139   | DOCS      |
| 2    | D1  | INACCURATE_CLAIM     | 94    | DOCS      |
| 3    | T2  | MISSING_CALL_VERIFY  | 93    | TEST      |
| 4    | F4  | SECURITY_VULN        | 74    | FEATURE   |
| 5    | D2  | STALE_REFERENCE      | 65    | DOCS      |
| 6    | F3  | THREAD_SAFETY        | 64    | FEATURE   |
| 7    | F2  | TYPE_ANNOTATION      | 63    | FEATURE   |
| 8    | T1  | WEAK_ASSERTION       | 54    | TEST      |
| 9    | F1  | MISSING_ERROR_HANDLING| 53   | FEATURE   |
| 10   | G1  | ABSOLUTE_PATH        | 53    | ALL       |

The single most common finding — D5·WRONG_FORMAT with 139 hits — is also the
most *preventable*. It is a markdown lint failure. The model generates
documentation without running a lint pass before committing.

---

## 4. Root Causes by Category

### 4.1 Test Generation

**The core failure**: tests written to achieve *coverage line-count* rather than
to verify *contracts*.

#### T2 · MISSING_CALL_VERIFY (93 findings)

A mock is set up and a function is called, but the test never asserts that the
mock received the right arguments. A facade forwarding the wrong payload still
passes.

```python
# Bad: proves the code ran, not that it called the right thing
def test_send_notification(mock_notifier):
    service.notify_user(user_id=42, message="hello")
    mock_notifier.send.assert_called_once()  # ← only checks call count


# Good: verifies the exact payload was forwarded
def test_send_notification(mock_notifier):
    service.notify_user(user_id=42, message="hello")
    mock_notifier.send.assert_called_once_with(
        recipient=42,
        body="hello",
    )
```

The question *"if this mock was called with the wrong argument, would this test
catch it?"* is never asked at generation time.

#### T1 · WEAK_ASSERTION (54 findings)

```python
# Bad: asserts execution completed, not that behavior was correct
def test_process_file(tmp_path):
    result = processor.process(tmp_path / "test.txt")
    assert result["success"] is True  # ← passes even if output is wrong


# Good: asserts the meaningful side-effect
def test_process_file(tmp_path):
    input_file = tmp_path / "test.txt"
    input_file.write_text("raw content")
    result = processor.process(input_file)
    assert result["success"] is True
    assert result["output_path"].exists()
    assert result["output_path"].read_text() == "processed content"
```

#### T9 · RESOURCE_LEAK (~10 findings)

LRU-cached database engines and file-backed fixtures not disposed between tests.
On Windows, `tmp_path` cleanup fails because a cached SQLAlchemy engine holds
the file handle open.

```python
# Bad: cached engine holds file handle across tests
@lru_cache(maxsize=None)
def get_engine(db_url: str):
    return create_engine(db_url)


# Good: clear the cache in a fixture so tmp_path can clean up
import pytest

@pytest.fixture(autouse=True)
def clear_engine_cache():
    get_engine.cache_clear()
    yield
    get_engine.cache_clear()
```

---

### 4.2 Feature Generation

**The core failure**: code generated to the happy path only. Security
boundaries, error paths, and concurrency are afterthoughts.

#### F4 · SECURITY_VULN (74 findings)

This was the most severe pattern in feature PRs. Examples from the dataset:

- Auth tokens passed as `?token=...` query strings — exposed in server access
  logs, browser history, and proxy logs.
- Path inputs accepted without sanitization — directory traversal possible.
- `get_settings()` called directly inside a route handler that was already
  passed an `ApiSettings` instance — bypassing the injected config.
- Secrets echoed in log output.

```python
# Bad: token in URL is visible in every log line
@router.get("/files")
async def list_files(token: str = Query(...)):
    if not verify_token(token):
        raise HTTPException(status_code=401)
    ...


# Good: token in Authorization header, not query string
@router.get("/files")
async def list_files(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if not verify_token(credentials.credentials):
        raise HTTPException(status_code=401)
    ...
```

#### F3 · THREAD_SAFETY (64 findings)

```python
# Bad: file truncated before lock acquired — partial write window
def write_config(path, data):
    with open(path, "w") as f:   # truncates here
        fcntl.flock(f, fcntl.LOCK_EX)   # lock acquired after truncation
        json.dump(data, f)


# Good: open for read-write, lock before truncate
def write_config(path, data):
    with open(path, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        f.truncate()
        json.dump(data, f)
```

#### F1 · MISSING_ERROR_HANDLING (53 findings)

Feature PRs consistently generated happy-path-only code. An exception raised by
a dependency propagates to the caller with no wrapping or user-facing message.
This is not a difficult pattern to detect — but the model generates code as if
every call will succeed.

---

### 4.3 Documentation

**The core failure**: docs written from *memory and intent* rather than from
reading the actual implementation first.

#### D5 · WRONG_FORMAT (139 findings — #1 overall)

Markdown lint failures: heading level skips (`# Title` followed immediately by
`### Section`), nested code fences, missing blank lines around fenced blocks,
table formatting errors. These are generated consistently across *every* docs
PR. The model does not run a lint pass before committing.

#### D1 · INACCURATE_CLAIM (94 findings)

Documented behavior that does not match the implementation:

- Method signatures shown in docs that don't exist in the codebase.
- Parameter names that are wrong.
- File format support claimed (`.doc` via python-docx) that the library does
  not actually provide.
- Plugin API examples inconsistent with the actual base class interface.

The pattern is consistent: the model writes from its training data's
approximation of the API rather than inspecting the real source.

#### D6 · CONTRADICTION (29 findings)

Two sections of the same document disagree. The classic example from our
dataset: a feature described as "complete" in the overview section and as
"planned" in the status table on the same page. Another: coverage described
as 0% in a metrics table and "comprehensive" in the prose.

---

### 4.4 CI / Infrastructure

**The core failure**: CI config generated without reading the existing workflow
to understand what already runs, and thresholds written from memory.

#### C4 · COVERAGE_GATE (25 findings)

The coverage threshold in a PR description did not match the value enforced in
`pyproject.toml` or the workflow YAML. Three different numbers appeared across
the same PR: 70% in the README, 75% in the PR description, and the actual
enforced threshold in configuration.

#### C3 · CACHE_MISCONFIG

`@lru_cache` applied to functions that read environment variables at call time.
The cache holds the value from the first call; if the env var changes between
invocations (common in tests), the cache returns a stale value.

```python
# Bad: env var read once and cached forever
@lru_cache(maxsize=None)
def get_config_manager():
    config_dir = os.environ.get("FO_CONFIG_DIR", "~/.config/file-organizer")
    return ConfigManager(config_dir)


# Good: pass the value in, cache the constructed object separately
def get_config_manager(config_dir: str | None = None) -> ConfigManager:
    resolved = config_dir or os.environ.get("FO_CONFIG_DIR", "~/.config/file-organizer")
    return _build_manager(resolved)


@lru_cache(maxsize=None)
def _build_manager(config_dir: str) -> ConfigManager:
    return ConfigManager(config_dir)
```

---

## 5. Patterns Unique to LLMs vs. Human Authors

These patterns appear across every work type and are structural to how LLMs
generate code — not specific to any particular model or task.

### 5.1 Context Window Limitations Cause Repeated Mistakes

A human engineer who fixed a threading bug on Monday will not reintroduce it on
Tuesday because they remember writing the fix. An LLM has no persistent memory
across sessions. The same class of bug — THREAD_SAFETY, MISSING_CALL_VERIFY,
SECURITY_VULN — appears again in the next PR of the same type.

This is not a model quality problem. It is an architectural property: without
explicit memory or rules that travel with each generation prompt, the model
reverts to its base behavior.

### 5.2 "Success-Only" Thinking

The model generates tests that demonstrate the code executes without error. It
does not reliably generate tests that demonstrate the code produces the *correct*
output when given adversarial or edge-case input, because the generation prompt
asks "write a test for this function" — not "write a test that would catch
a regression in this function's contract."

Humans who have debugged production failures write tests defensively. LLMs
write tests to satisfy the stated requirement.

### 5.3 Overconfident Documentation

The model writes documentation from its training data's approximation of the
API. It does not read the source file before documenting it. When an API
changed after training cutoff — or was never in the training data at all — the
documentation is confidently wrong rather than absent.

Humans would not document a method they haven't read. LLMs document what they
believe the method should look like.

### 5.4 Security Boundary Blindness

The model generates logic without considering trust boundaries. It does not ask
"who controls this input?" before accepting it or "where does this value end up?"
before logging it. Auth token placement, input sanitization, and secret handling
require reasoning about the deployment context — information the model infers
poorly from a function signature alone.

---

## 6. What Actually Works

After 115 PRs of data, these interventions produced measurable reductions in
churn rate:

### 6.1 Pre-Generation Checklists

The most effective intervention was adding mandatory checklist steps to the
generation workflow *before* the model writes any code:

- **Source-first docs**: "Read the implementation file before writing any docs
  claim." Reduced D1·INACCURATE_CLAIM incidents in subsequent doc PRs.
- **Mock verification rule**: "Every generated test that uses a mock must assert
  the mock's arguments, not just its call count." Directly targets T2.
- **Security boundary check**: "Before implementing any input handling, identify
  the trust boundary: is this input user-controlled?" Targets F4.
- **Lint before commit**: "Run `markdownlint` before committing any `.md` file."
  The highest-ROI intervention for D5·WRONG_FORMAT (139 hits from a simple
  format error).

### 6.2 Persistent Memory Across Sessions

Rule files committed to the repository (e.g. `.claude/rules/feature-generation-patterns.md`,
`.claude/rules/test-execution.md`) travel with the generation prompt
automatically. Unlike a one-time instruction in a chat session, they are
present for every subsequent generation.

The key insight: the model will not remember a correction from session N in
session N+1. The correction must be written down and loaded at the start of
every session.

### 6.3 Single-Pass Review Response

Instead of addressing one reviewer comment at a time — the natural instinct —
the protocol is:

1. Extract **all** reviewer findings upfront in one operation.
2. Verify each against current code.
3. Apply all valid fixes locally in a single pass.
4. Push once.

Iterative comment-by-comment responses cause compounding context loss:
the model fixes comment #3 without the full context of comments #1 and #2,
introducing inconsistencies that generate new review findings.

### 6.4 Automated Pre-Commit Validation

A pre-commit hook that runs lint, type-checking, and pattern validation before
any commit catches the highest-frequency, lowest-severity findings (D5, G4,
G2) before they reach review. This compresses the feedback loop from
hours (waiting for automated review) to seconds.

The economics matter: a finding caught at commit time costs one second.
The same finding caught in PR review costs one round-trip cycle.

---

## 7. Takeaways for Teams Using LLM Tools

### Automated Review Is Not Optional

If you are using LLMs to write code, you need automated reviewers. Not as a
quality gate at the end, but as a systematic data source. The findings tell you
where your generation process is weak.

Without automated review, you have no data. Without data, you cannot improve
the generation process. You are flying blind across a pattern space that repeats
every PR.

### Rule Files Reduce Repeat Mistakes More Than Prompting

A one-time instruction ("always verify mock arguments") degrades across sessions.
A rule file loaded at the start of every session does not. The cost of
maintaining rule files is low; the benefit compounds with each PR.

The pattern: identify a class of mistake from review data → write a rule →
load the rule automatically → measure whether the mistake recurs.

### Measure Churn Rate Per PR Type

Aggregate churn rate is not actionable. Churn rate by work type is. In this
dataset:

- Docs PRs had the highest *density* of findings (343 findings across fewer PRs,
  dominated by format errors with a simple fix).
- Feature PRs had the highest *severity* findings (security vulnerabilities,
  thread safety, missing error handling).
- Test PRs had the highest *stealth* risk: findings in the 600s that appear to
  pass CI while not actually verifying behavior.

Each work type needs its own intervention. A mock verification rule does not
help with markdown lint failures.

### The Speed Gain Has a Hidden Cost

LLMs are fast. A feature that would take a human two days can be prototyped in
minutes. But if that prototype generates 15 reviewer findings that require
three fix cycles to resolve, the net elapsed time — accounting for review
latency, context re-establishment, and re-testing — may exceed the manual
baseline.

The actual speed gain from LLM code generation only materializes when churn is
low. Investing in pre-generation checklists, rule files, and automated
validation is not overhead — it is what makes the speed gain real.

---

## Appendix: Anti-Pattern Reference

| ID | Name                | Count | Category   |
|----|---------------------|-------|------------|
| D5 | WRONG_FORMAT        | 139   | DOCS       |
| D1 | INACCURATE_CLAIM    | 94    | DOCS       |
| T2 | MISSING_CALL_VERIFY | 93    | TEST       |
| F4 | SECURITY_VULN       | 74    | FEATURE    |
| D2 | STALE_REFERENCE     | 65    | DOCS       |
| F3 | THREAD_SAFETY       | 64    | FEATURE    |
| F2 | TYPE_ANNOTATION     | 63    | FEATURE    |
| T1 | WEAK_ASSERTION      | 54    | TEST       |
| F1 | MISSING_ERROR_HANDLING | 53 | FEATURE    |
| G1 | ABSOLUTE_PATH       | 53    | ALL        |
| G5 | NAMING_CONVENTION   | 43    | ALL        |
| G4 | UNUSED_CODE         | 41    | ALL        |
| D4 | MISSING_SECTION     | 36    | DOCS       |
| F5 | HARDCODED_VALUE     | 36    | FEATURE    |
| D6 | CONTRADICTION       | 29    | DOCS       |
| T6 | PERMISSIVE_FILTER   | 26    | TEST       |
| C4 | COVERAGE_GATE       | 25    | CI         |
| T8 | BRITTLE_ASSERTION   | 23    | TEST       |
| T3 | WRONG_PAYLOAD       | 20    | TEST       |
| D3 | BROKEN_EXAMPLE      | 20    | DOCS       |
| T4 | BROAD_EXCEPTION     | ~15   | TEST       |
| T10| DEAD_TEST_CODE      | ~15   | TEST       |
| G2 | LOGGING_FORMAT      | ~12   | ALL        |
| F6 | API_CONTRACT_BROKEN | ~12   | FEATURE    |
| T9 | RESOURCE_LEAK       | ~10   | TEST       |
| F7 | RESOURCE_NOT_CLOSED | ~10   | FEATURE    |

*Source: curdriceaurora/Local-File-Organizer issue #657 — 1,830 findings across 115 PRs.*

---

## Related

- [Issue #657: Full-project PR review audit](https://github.com/curdriceaurora/Local-File-Organizer/issues/657) — source data for this post
- [Issue #656: Test-generation anti-pattern deep-dive](https://github.com/curdriceaurora/Local-File-Organizer/issues/656) — precursor analysis
