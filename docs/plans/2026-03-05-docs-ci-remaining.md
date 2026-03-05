# Docs CI Remaining Issues Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close issues #597, #598, #599 — improve test precision and pin CI actions to SHAs.

**Architecture:** Two independent changes: (A) add section-anchored matching to `test_pyproject_sync.py` so word-boundary checks only search within the relevant doc section, and (B) pin all GitHub Actions in docs-ci workflows to immutable commit SHAs with least-privilege permissions.

**Tech Stack:** Python 3.11+, pytest, GitHub Actions YAML

---

## Setup

### Task 0: Create feature branch

**Step 1: Create branch from main**

```bash
git checkout main && git pull origin main
git checkout -b feature/docs-ci-597-598-599
```

**Step 2: Commit the design doc**

```bash
git add docs/plans/2026-03-05-docs-ci-remaining-design.md docs/plans/2026-03-05-docs-ci-remaining.md
git commit -m "docs: add design and plan for docs-ci issues #597, #598, #599"
```

---

## Work Item A: Section-anchored matching (#597 + #599)

### Task 1: Write failing test for `_extract_section` helper

**Files:**
- Modify: `tests/docs/test_pyproject_sync.py`

**Step 1: Add test for `_extract_section`**

Add this test at the bottom of the file:

```python
class TestExtractSection:
    """Tests for _extract_section helper."""

    def test_extracts_target_section(self) -> None:
        content = "# Title\n\nIntro\n\n## Section A\n\nA content\n\n## Section B\n\nB content\n"
        result = _extract_section(content, "Section A")
        assert "A content" in result
        assert "B content" not in result

    def test_extracts_to_eof_when_last_section(self) -> None:
        content = "# Title\n\n## Only Section\n\nContent here\n"
        result = _extract_section(content, "Only Section")
        assert "Content here" in result

    def test_raises_when_heading_not_found(self) -> None:
        content = "# Title\n\nNo matching section\n"
        with pytest.raises(ValueError, match="Heading 'Missing' not found"):
            _extract_section(content, "Missing")
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/docs/test_pyproject_sync.py::TestExtractSection -v
```

Expected: FAIL with `NameError: name '_extract_section' is not defined`

**Step 3: Commit failing test**

```bash
git add tests/docs/test_pyproject_sync.py
git commit -m "test(#597): add failing tests for _extract_section helper"
```

---

### Task 2: Implement `_extract_section` helper

**Files:**
- Modify: `tests/docs/test_pyproject_sync.py`

**Step 1: Add the helper function** (after the existing helpers, before the test functions)

```python
def _extract_section(content: str, heading: str) -> str:
    """Extract markdown content under a heading up to the next same-level heading.

    Raises ValueError if the heading is not found, so callers know the section
    anchor is missing rather than silently searching the full document.
    """
    pattern = rf"^(#{{1,6}})\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        raise ValueError(f"Heading '{heading}' not found in document")
    level = match.group(1)  # e.g. "##"
    start = match.end()
    # Find next heading at same or higher level
    next_heading = re.search(
        rf"^#{{1,{len(level)}}}\s", content[start:], re.MULTILINE
    )
    if next_heading:
        return content[start : start + next_heading.start()]
    return content[start:]
```

**Step 2: Run tests to verify they pass**

```bash
pytest tests/docs/test_pyproject_sync.py::TestExtractSection -v
```

Expected: 5 PASS

**Step 3: Commit**

```bash
git add tests/docs/test_pyproject_sync.py
git commit -m "feat(#597): add _extract_section helper for section-anchored matching"
```

---

### Task 3: Update `test_extra_documented` to use section-anchored search

**Files:**
- Modify: `tests/docs/test_pyproject_sync.py`

**Step 1: Modify `test_extra_documented`**

Replace the existing function with:

```python
@pytest.mark.parametrize("extra", _get_extras())
def test_extra_documented(extra: str) -> None:
    """Each pyproject.toml optional-dependency group must appear in dependencies.md."""
    content = DEPS_DOC.read_text(encoding="utf-8")
    section = _extract_section(content, "Optional Dependencies")
    assert re.search(rf"\b{re.escape(extra)}\b", section), (
        f"Optional extra '{extra}' not found in 'Optional Dependencies' section "
        f"of {DEPS_DOC.relative_to(REPO_ROOT)}"
    )
```

**Step 2: Run test to verify it passes**

```bash
pytest tests/docs/test_pyproject_sync.py::test_extra_documented -v
```

Expected: all extras PASS

**Step 3: Commit**

```bash
git add tests/docs/test_pyproject_sync.py
git commit -m "fix(#597): scope extra matching to Optional Dependencies section"
```

---

### Task 4: Update `test_marker_documented` to use section-anchored search

**Files:**
- Modify: `tests/docs/test_pyproject_sync.py`

**Step 1: Modify `test_marker_documented`**

Replace the existing function with:

```python
@pytest.mark.parametrize("marker", _get_markers())
def test_marker_documented(marker: str) -> None:
    """Each pytest marker must appear in testing-strategy.md."""
    content = TESTING_DOC.read_text(encoding="utf-8")
    section = _extract_section(content, "Test Markers")
    assert re.search(rf"\b{re.escape(marker)}\b", section), (
        f"Pytest marker '{marker}' not found in 'Test Markers' section "
        f"of {TESTING_DOC.relative_to(REPO_ROOT)}"
    )
```

**Step 2: Run full test file to verify everything passes**

```bash
pytest tests/docs/test_pyproject_sync.py -v
```

Expected: all tests PASS

**Step 3: Run ruff checks**

```bash
ruff check tests/docs/test_pyproject_sync.py && ruff format tests/docs/test_pyproject_sync.py --check
```

**Step 4: Commit**

```bash
git add tests/docs/test_pyproject_sync.py
git commit -m "fix(#599): scope marker matching to Test Markers section"
```

---

## Work Item B: Pin GitHub Actions SHAs (#598)

### Task 5: Pin actions in docs-lint.yml

**Files:**
- Modify: `.github/workflows/docs-lint.yml`

**Step 1: Replace the file content with pinned versions**

```yaml
name: Lint Markdown

on: [push, pull_request]

permissions:
  contents: read

jobs:
  markdownlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5  # v4.3.1
      - uses: DavidAnson/markdownlint-cli2-action@db43aef879112c3119a410d69f66701e0d530809  # v17.0.0
        with:
          globs: |
            docs/**/*.md
            *.md
```

**Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/docs-lint.yml'))"
```

**Step 3: Commit**

```bash
git add .github/workflows/docs-lint.yml
git commit -m "fix(#598): pin GitHub Actions to commit SHAs in docs-lint workflow"
```

---

### Task 6: Pin actions in docs-link-check.yml

**Files:**
- Modify: `.github/workflows/docs-link-check.yml`

**Step 1: Replace the file content with pinned versions**

```yaml
name: Check Markdown Links

on: [push, pull_request]

permissions:
  contents: read

jobs:
  link-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5  # v4.3.1
      - uses: lycheeverse/lychee-action@8646ba30535128ac92d33dfc9133794bfdd9b411  # v2.8.0
        with:
          args: --no-progress --offline 'docs/**/*.md' '*.md'
          fail: true
```

**Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/docs-link-check.yml'))"
```

**Step 3: Commit**

```bash
git add .github/workflows/docs-link-check.yml
git commit -m "fix(#598): pin GitHub Actions to commit SHAs in docs-link-check workflow"
```

---

## Finalization

### Task 7: Full validation and PR

**Step 1: Run full pre-commit validation**

```bash
ruff check . && ruff format tests/docs/test_pyproject_sync.py --check
pytest tests/docs/test_pyproject_sync.py -v --no-cov
```

**Step 2: Push and create PR**

```bash
git push -u origin feature/docs-ci-597-598-599
gh pr create --base main --title "fix(docs-ci): section-anchored test matching and pin Actions SHAs" --body "$(cat <<'EOF'
## Summary
- Scope word-boundary matching in `test_pyproject_sync.py` to relevant doc sections instead of full document (closes #597, closes #599)
- Pin all GitHub Actions to immutable commit SHAs and add `permissions: contents: read` (closes #598)

## Test plan
- [ ] `_extract_section` helper tests pass
- [ ] `test_extra_documented` passes with section-scoped matching
- [ ] `test_marker_documented` passes with section-scoped matching
- [ ] CI workflows run successfully with pinned SHAs
- [ ] `ruff check` and `ruff format` pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
