---
created: 2026-03-08T23:57:34Z
last_updated: 2026-03-08T23:57:34Z
version: 1.0
author: Claude Code PM System
---

# Project Style Guide

> **Rule files**: Before generating any code, read these first:
> - `.claude/rules/quick-validation-checklist.md` — G1-G5 patterns, pre-commit checklist
> - `.claude/rules/code-quality-validation.md` — full validation patterns with examples
> - `.claude/rules/feature-generation-patterns.md` — F1-F9 feature anti-patterns
> - `.claude/rules/test-execution.md` — always use Agent(test-runner), never raw pytest

## Python Code Style

| Rule | Standard |
|------|---------|
| Formatter | Black, 100-char line length |
| Linter | Ruff (strict) |
| Type checker | mypy (strict) — all `src/` files |
| Import sorter | isort (via Ruff) |
| Docstrings | Google style |

## Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Files/modules | `snake_case.py` | `text_processor.py` |
| Classes | `PascalCase` | `VisionProcessor` |
| Functions/variables | `snake_case` | `process_file()` |
| Constants | `UPPER_SNAKE_CASE` | `SHORT_CLIP_THRESHOLD` |
| Private | `_single_underscore` | `_try_ffprobe()` |
| Type aliases | `PascalCase` | `VideoPath = Path` |

## Commit Message Format

```
<type>(<scope>): <subject>

[optional body]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`

Examples:
```
feat(audio): add podcast chapter detection
fix(#392): address Copilot review — ci marker, weak assertions
test(#394): add image file reader tests with magic-byte stubs
refactor(#392): extract _make_mock_cv2() helper, remove duplication
```

## Test Style

```python
@pytest.mark.unit
@pytest.mark.ci
class TestVideoMetadataExtractor:
    def test_extracts_fps_from_rational_string(
        self, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        """r_frame_rate '30000/1001' should parse to ~29.97."""
        # Arrange
        mock_run.return_value = MagicMock(returncode=0, stdout=_ffprobe_output(fps="30000/1001"))
        # Act
        metadata = extractor.extract(sample_video)
        # Assert
        assert metadata.fps is not None
        assert abs(metadata.fps - 29.97) < 0.01
```

Rules:
- All test classes marked `@pytest.mark.unit` + `@pytest.mark.ci` (for PR CI coverage)
- Use `@pytest.mark.smoke` on 1-2 fast path tests per module
- Type annotations on all test method signatures
- Use `tmp_path` fixture, never `/tmp/` hardcoded paths
- Use helper factories (`_make_metadata()`, `_make_mock_cv2()`) instead of repeated setup
- Assert mock calls when testing delegation, not just return values

## Anti-Patterns (From PR Review Learnings)

```python
# ❌ G1: Hardcoded path
path = Path("/tmp/test.jpg")
# ✅ Use tmp_path fixture
path = tmp_path / "test.jpg"

# ❌ G2: f-string in logger
logger.debug(f"Processing {file_path}")
# ✅ Lazy % format
logger.debug("Processing %s", file_path)

# ❌ G4: Unused constant at module level
_BMP_STUB = b"BM..."   # never used
# ✅ Remove or use it

# ❌ Tautological assertion
assert "unknown" not in desc.lower() or "unknown" not in desc
# ✅ Single clear assertion
assert "unknown" not in desc.lower()

# ❌ Explicit None for dataclass defaults
VideoMetadata(path=p, size=512, format="mp4", duration=None, width=None, ...)
# ✅ Let defaults apply
VideoMetadata(path=p, size=512, format="mp4")

# ❌ Redundant per-class marker when pytestmark covers module
pytestmark = [pytest.mark.unit, pytest.mark.ci]
@pytest.mark.unit   # redundant
class TestFoo: ...
# ✅ Remove per-class decorator
class TestFoo: ...
```

## Import Order

```python
from __future__ import annotations

# Standard library
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

# Third-party
import pytest
from unittest.mock import MagicMock, patch

# First-party (absolute only)
from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor
```
