---
issue: 339
title: "Reliability: File Reading Denial of Service Risk (DoS-1)"
epic: technical-debt
analyzed: 2026-02-18T07:35:00Z
estimated_hours: 6
parallelization_factor: 2.0
---

# Parallel Work Analysis: Issue #339

## Overview

`read_file()` and several individual readers in `utils/file_readers.py` have no pre-read file size gate. A zip bomb or multi-GB file can exhaust memory before any content limit kicks in. The fix is a thin `_check_file_size()` guard called at the top of `read_file()` and inside the unbounded readers, plus a documented constant `MAX_FILE_SIZE_BYTES`.

**Root cause**: `read_docx_file`, `read_presentation_file`, `read_ebook_file` open files with no stat check. `read_file()` dispatches without a size gate.

**Fix strategy**: Add `MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024` (500 MB, configurable). `read_file()` calls `_check_file_size(path)` before dispatch. Individual unbounded readers also check. Raise `FileTooLargeError` (new exception) on violation.

---

## Parallel Streams

### Stream A: Size Gate + Exception

**Scope**: Add `MAX_FILE_SIZE_BYTES` constant, `FileTooLargeError` exception, and `_check_file_size()` helper. Patch `read_file()` dispatcher and the four unbounded readers (`read_docx_file`, `read_presentation_file`, `read_ebook_file`, `read_tar_file`).

**Files**:

- `src/file_organizer/utils/file_readers.py` — add constant, exception, helper, patch readers
- `src/file_organizer/utils/__init__.py` — export `FileTooLargeError`

**Can Start**: immediately
**Estimated Hours**: 3

### Stream B: Tests

**Scope**: Unit tests for the size gate using mocked `os.stat` (no real 2 GB files needed). Verify `read_file()` and each patched reader raise `FileTooLargeError` on oversized input. Verify normal-sized files still pass.

**Files**:

- `tests/utils/test_file_size_limit.py` ← new

**Can Start**: immediately (mock-based, no dependency on Stream A code)
**Estimated Hours**: 3

---

## Coordination Points

- Both streams touch `file_readers.py` logically but Stream B uses mocks — **no file conflicts**
- Stream B should import `FileTooLargeError` from `file_organizer.utils` — coordinate the exception name

## Parallelization Strategy

**Parallel**: Launch A and B simultaneously. B mocks `os.stat` so it doesn't need A's code to exist yet — just agree on the exception class name upfront (`FileTooLargeError`).

## Expected Timeline

- Wall time: ~3 hours (parallel)
- Total work: 6 hours
- Efficiency gain: 50%
