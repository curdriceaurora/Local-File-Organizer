---

issue: 577
title: CLI Command Tests
analyzed: 2026-03-06T17:45:30Z
estimated_hours: 22
parallelization_factor: 2.5
---

# Parallel Work Analysis: Issue #577

## Overview

Write ~9 missing test modules for CLI commands in `src/file_organizer/cli/`. Target module coverage from ~61% to 80%.

## Parallel Streams

### Stream A: Core CLI Tests

**Scope**: Test main entrypoint and help/completion functionality
**Files**:

- `tests/cli/test_main.py` - Main CLI app, --help, --version output

- `tests/cli/test_completion.py` - Shell completion: bash, zsh, fish output
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 4
**Dependencies**: none

### Stream B: File Operation Commands

**Scope**: Test commands that manipulate files directly
**Files**:

- `tests/cli/test_dedupe.py` - Dedupe: scan, report, resolve, --dry-run

- `tests/cli/test_autotag.py` - Autotag: tag files, list tags, remove tags

- `tests/cli/test_suggest.py` - Suggest: for file, for directory
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 9
**Dependencies**: none

### Stream C: System & Config Commands

**Scope**: Test commands that manage daemon, updates, rules, and analytics
**Files**:

- `tests/cli/test_daemon.py` - Daemon: start, stop, status, --foreground

- `tests/cli/test_update.py` - Update: check, install, rollback

- `tests/cli/test_rules.py` - Rules: list, add, remove, enable/disable

- `tests/cli/test_analytics.py` - Analytics: generate report, show stats

- `tests/cli/test_copilot.py` - Copilot: ask, suggest, explain (if exists)
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 9
**Dependencies**: none

## Coordination Points

### Shared Files

- `tests/cli/conftest.py` - Shared CLI runner fixture and helpers
  - CliRunner instantiation

  - Temp directory fixtures for file operations

  - Mock app configurations

  - All streams need to import from this

### Sequential Requirements

None—all streams are independent

## Conflict Risk Assessment

- **Low Risk**: Different test modules for different commands

- **Low Risk**: All use standard `typer.testing.CliRunner` pattern

- **Mitigation**: Create shared `conftest.py` early with standard fixtures

## Parallelization Strategy

**Recommended Approach**: Hybrid parallel execution

1. **Setup** (1-2 hours): Create `conftest.py` with CliRunner and common fixtures
2. **Streams A, B, C parallel** (18-20 hours): All run simultaneously after setup

   - Stream A fastest (4h) - finish early

   - Streams B & C medium (9h each) - finish together

## Expected Timeline

With parallel execution:

- Wall time: 11-12 hours (setup + parallel execution)

- Total work: 22 hours

- Efficiency gain: 45%

Without parallel execution:

- Wall time: 22 hours

## Notes

- Use `typer.testing.CliRunner` for all CLI tests—NOT subprocess

- Test exit codes: 0 for success, non-zero for errors

- Test stdout format and stderr for error messages

- Test each command for: success path, error path, --help output

- Test flags where applicable: --dry-run, --verbose, --quiet

- File operation tests: Use isolated temp directories (no shared state between tests)

- Daemon tests: Mock the daemon subprocess (don't actually start daemon)

- Update tests: Mock HTTP calls for version checks

- Analytics tests: May depend on real file scanning—use small temp structure

- Each test file must have module-level docstring

- Use fixtures for common setup: mock configs, temp directories, CliRunner

- Tag all tests with `@pytest.mark.unit`

- Performance: no single test > 5s

- Consider using parameterization for testing multiple subcommands with similar patterns
