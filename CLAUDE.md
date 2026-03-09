# Claude Code Project Instructions

## Project: File Organizer v2.0

AI-powered local file management. Privacy-first, 100% local LLMs. Python 3.11+ | ~78,800 LOC | 314 modules | 237 test files | v2.0.0-alpha.1

---

## Code Review Exclusions

`.claude/` and `CLAUDE.md` are excluded from CodeRabbit/Copilot automated review.
See `.coderabbit.yaml` and `.github/copilot-instructions.md`.

---

## MANDATORY SESSION START — DO THESE FIRST, EVERY TIME

```
1. git branch --show-current          # Confirm NOT on main
2. cat memory/MEMORY.md               # What issue, what state, what branch
3. Read .claude/context/workflow.md   # Rules index — which rule to load for this task
4. Skill("pm:issue-start", N)         # Register CCPM before touching anything
```

If resuming after context break:
```
5. git log --oneline -5               # Confirm branch state
6. cat .claude/epics/*/updates/N/progress.md  # Re-establish CCPM context
```

---

## MANDATORY PRE-COMMIT — RUN EVERY TIME, NO EXCEPTIONS

```bash
# 1. Stage your files
git add <specific files>

# 2. Run this — it blocks commit if anything fails
bash .claude/scripts/pre-commit-validation.sh

# 3. Only commit if it passes
git commit -m "type(scope): message"
```

**Never use `--no-verify`. Never skip the script.**

---

## MANDATORY QUALITY GATES — IN THIS ORDER

After significant code changes (>50 lines), before committing:

```
1. Agent(subagent_type="code-reviewer")    # Catches logic errors, API contracts
2. Skill("simplify")                        # Catches duplication, dead code
3. bash .claude/scripts/pre-commit-validation.sh  # Catches lint, format, tests
4. git commit
5. Skill("pm:issue-sync", N)               # Update CCPM after commit
```

---

## MANDATORY CODE PATTERNS — CHECK BEFORE EVERY COMMIT

These patterns cause PR review churn. Grep for them before staging:

```bash
# G1 — No hardcoded /tmp/ paths in tests (use tmp_path fixture)
git diff --cached | grep -E '/tmp/'

# G2 — No f-strings in logger calls (lazy % format only)
git diff --cached | grep -E 'logger\.(debug|info|warning|error)\(f"'

# G4 — No unused module-level constants or imports
ruff check --select F401 . && grep -n "^_[A-Z].*=.*b\"" tests/ -r

# Tautological assertions (always pass regardless of code)
git diff --cached | grep -E 'assert.*or.*assert'

# Absolute paths in non-test code
git diff --cached | grep -E '(/Users/|/home/|expanduser)'
```

If any match: **fix before committing**.

---

## MANDATORY TEST PATTERNS

```python
# ✅ Use tmp_path, never /tmp/
def test_foo(tmp_path: Path) -> None:
    p = tmp_path / "file.jpg"

# ✅ Extract repeated setup into helpers
def _make_mock_img() -> MagicMock:  ...   # not inline 4x

# ✅ Both markers on new test classes
@pytest.mark.unit
@pytest.mark.ci   # ← required so pytest -m "ci" (PR CI) covers it
class TestFoo: ...

# ✅ Module-level pytestmark removes per-class redundancy
pytestmark = [pytest.mark.unit, pytest.mark.ci]
class TestFoo: ...   # no decorator needed

# ✅ Exact assertions, not permissive ones
assert desc == "Video"          # ✅
assert "Video" in desc          # ❌ passes "Video unknown 0s" too

# ✅ Use existing helpers before creating inline dicts
mock_run.return_value = MagicMock(stdout=_ffprobe_output(fps="30/0"))  # ✅
mock_run.return_value = MagicMock(stdout=json.dumps({...}))            # ❌ duplicate

# ✅ Run tests via agent, never raw pytest
Agent(subagent_type="test-runner", prompt="Run tests/services/video/...")
```

---

## GIT WORKFLOW

1. **Always on a feature branch.** Never commit to `main`.
2. **Branch naming:** `feature/issue-N-description` or `fix/issue-N-description`
3. **Commit immediately** after changes with conventional commit message.
4. **Push after every commit** without waiting.
5. **Full flow:** branch → implement → quality gates → commit → push → PR → review → merge

```bash
git checkout main && git pull origin main
git checkout -b feature/issue-N-description
# ... make changes, run quality gates ...
git add <files>
bash .claude/scripts/pre-commit-validation.sh
git commit -m "feat(scope): description"
git push origin feature/issue-N-description
gh pr create --title "..." --body "..."
```

---

## PR REVIEW RESPONSE — 6 STEPS

When a PR has review comments:

```
1. Extract ALL findings via GraphQL (not gh CLI — it misses threads)
   TOKEN=$(gh auth token)
   curl -s -X POST https://api.github.com/graphql -H "Authorization: token $TOKEN" \
     -d '{"query":"{ repository(owner:\"...\",name:\"...\") { pullRequest(number:N) { reviewThreads(first:30) { nodes { id isResolved comments(first:2) { nodes { body } } } } } } }"}'

2. Categorize each finding: APPLY / SKIP / CLARIFY / DEFER
   APPLY = fix it. SKIP = reply why not. DEFER = create issue, reply link.

3. Apply ALL APPLY fixes locally — no push between fixes

4. Run quality gates (code-reviewer → simplify → pre-commit-validation.sh)

5. Single commit, single push

6. Resolve threads:
   .claude/scripts/resolve-pr-threads.sh <PR> --replies replies.json
```

**Never push between individual fixes. One pass, one push.**

---

## CCPM TRACKING — MANDATORY

```bash
Skill("pm:issue-start", N)   # Before touching anything
Skill("pm:issue-sync", N)    # After each commit
Skill("pm:issue-close", N)   # When task complete
```

**Never create/update GitHub issues or PRs without PM skills.**
**Never post GitHub comments with `gh issue comment` directly.**

---

## FEATURE CODE ANTI-PATTERNS (top causes of PR review findings)

```python
# F1 — Every external call needs error handling
try:
    content = reader.read(path)
except FileNotFoundError:
    return ProcessResult(success=False, error=str(e))

# F2 — All functions need type annotations
def process(path: Path, config: Config | None = None) -> Result: ...

# F4 — Auth tokens in headers, not query strings
authorization: str = Header(...)  # ✅
token: str = Query(...)            # ❌ leaks to logs

# F4 — Validate paths against allowed roots
if not str(requested).startswith(str(allowed_root)):
    raise HTTPException(403)

# F5 — Use ConfigManager, not hardcoded paths
from file_organizer.config import ConfigManager
path = ConfigManager.get_path("trash")  # ✅
path = Path("~/.config/file-organizer/trash")  # ❌
```

---

## CI PATTERNS

```bash
# C4 — Always verify coverage threshold before documenting it
grep "cov-fail-under" pyproject.toml   # → 95

# C2 — Guard external writes to main-push only
if: github.event_name == 'push' && github.ref == 'refs/heads/main'

# C3 — Remove @lru_cache from functions that read env vars
rg "@lru_cache" src/ -A5 | grep -B3 "environ"
```

---

## DOCUMENTATION ANTI-PATTERNS

```bash
# D5 — Run pymarkdown before committing any .md file
pymarkdown scan <file>.md   # must show 0 violations

# D1 — Verify every method before documenting it
grep "def method_name" src/   # confirm it exists

# D6 — Can't be "complete" AND "0% coverage"
```

---

## SECURITY BOUNDARY (run before any new route/endpoint)

- [ ] Auth via query string? → Move to `Authorization: Bearer` header
- [ ] Path from user input? → Validate against `settings.files_root.resolve()`
- [ ] Secret in any log statement? → Remove
- [ ] Using injected dependency? → Don't call `get_settings()` inside route

---

## MULTI-TASK / PARALLEL PR RULES

Before creating multiple PRs, verify MECE (Mutually Exclusive, Collectively Exhaustive):

```bash
# List files each PR touches — zero overlap required
git diff --name-only main...branch-A
git diff --name-only main...branch-B
# Any shared files = sequence, not parallelize
```

Merge order: dependencies first, then independents.

---

## QUICK REFERENCE

| What | Where |
|------|-------|
| Full rules index | `.claude/context/workflow.md` |
| PR workflow master | `.claude/rules/pr-workflow-master.md` |
| Pre-commit checklist | `.claude/rules/quick-validation-checklist.md` |
| Feature anti-patterns | `.claude/rules/feature-generation-patterns.md` |
| Test execution | `.claude/rules/test-execution.md` |
| All rules | `.claude/rules/` (31 files) |
| Project context | `.claude/context/` (10 files) |
| Session memory | `memory/MEMORY.md` |

---

## PROJECT SETUP

```bash
pip install -e .
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M
file-organizer --help
pytest tests/ -m smoke -x -q
```

**Coverage gate:** 95% on main push. PR CI: `pytest -m "ci"` (no gate).
**Supported formats:** 48+ types — documents, images, video, audio, archives, scientific, CAD.

---

**Last Updated**: 2026-03-09 | **Version**: 2.0.0-alpha.1
