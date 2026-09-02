# Guardrail Promotion Backlog

This backlog converts recurring PR-review anti-patterns into remediation and
enforcement issues. Each issue should follow the same shape as #1369: current
state, representative examples, remediation guidance, and acceptance criteria.

## Promotion Rules

- Promote only repeated, objective patterns with a low-noise detector path.
- Put fast changed-file checks in pre-commit or `ci-rails`.
- Put semantic, repository-wide, or high-context checks in `tests/ci` first.
- Keep existing enforced rails enforced; hardening work should improve their
  reliability, not reopen enforcement.

## MECE Issue Drafts

| Issue | Anti-pattern | Canonical home | Enforcement target |
|---|---|---|---|
| [#1405](https://github.com/curdriceaurora/Local-File-Organizer/issues/1405) Guardrail suppression bypasses | Broad `noqa`, string-literal suppressions, or unrelated suppression codes disable rails | `scripts/ci/guardrails` shared suppression parser | `ci-rails` enforced |
| [#1406](https://github.com/curdriceaurora/Local-File-Organizer/issues/1406) CLI file-kind validation gaps | CLI paths are resolved but directories pass where files are required | `cli-path-validation` | `ci-rails` enforced |
| [#1408](https://github.com/curdriceaurora/Local-File-Organizer/issues/1408) Subprocess return-code gaps | `subprocess.run` success is reported without checking non-zero exits | `check_subprocess_returncode.py` | `ci-rails` enforced |
| [#1409](https://github.com/curdriceaurora/Local-File-Organizer/issues/1409) PID lifecycle races | PID files are signaled/unlinked after stale checks without ownership revalidation | daemon regression tests plus `tests/ci` | CI-only first |
| [#1410](https://github.com/curdriceaurora/Local-File-Organizer/issues/1410) Filesystem link/copy races | Symlink, hardlink, copy, move, or unlink operations mutate without identity/root validation | protected-module semantic check | CI-only first |
| [#1411](https://github.com/curdriceaurora/Local-File-Organizer/issues/1411) Raw persistence writes | Production writes bypass atomic helpers | existing `atomic-write` rail | `ci-rails` enforced |
| [#1412](https://github.com/curdriceaurora/Local-File-Organizer/issues/1412) SafeDir bypasses | Caller-controlled reads/copies/moves bypass SafeDir or swallow its `ValueError` | existing `safedir-required` and `safedir-valueerror` rails | `ci-rails` enforced |
| [#1413](https://github.com/curdriceaurora/Local-File-Organizer/issues/1413) Weak mock assertions | Tests assert only `mock.called` or bare `mock.call_count` | existing `called-attribute-assertion` rail | `ci-rails` enforced |
| [#1369](https://github.com/curdriceaurora/Local-File-Organizer/issues/1369) Generic `pytest.raises` | Built-in/generic exception assertions omit `match=` | existing `pytest-raises-hygiene` rail | enforced by #1404 |
| [#1414](https://github.com/curdriceaurora/Local-File-Organizer/issues/1414) Test environment leakage | Tests mutate globals, class attributes, or `sys.modules` without scoped restoration | `test-environment-leakage` | `ci-rails` enforced |
| [#1415](https://github.com/curdriceaurora/Local-File-Organizer/issues/1415) Test path portability | Tests hardcode absolute paths or separators | existing `test-hardcoded-paths` and `test-separator-paths` rails | `ci-rails` enforced |
| [#1416](https://github.com/curdriceaurora/Local-File-Organizer/issues/1416) xdist shared state | Tests use xdist-wide temp state without grouping | existing `xdist-loadgroup` rail | `ci-rails` enforced |
| [#1417](https://github.com/curdriceaurora/Local-File-Organizer/issues/1417) XML parser fallback gaps | XML parsing falls back unsafely or mishandles missing `defusedxml` | existing `defusedxml-fallback` rail | `ci-rails` enforced |
| [#1418](https://github.com/curdriceaurora/Local-File-Organizer/issues/1418) Guardrail docs drift | Docs, registry, and expected rail modes disagree | `tests/ci/test_guardrail_governance.py` | pre-commit via `pytest-ci-lint` |

## Issue Acceptance Template

Use this checklist when opening one of the issues above:

- Current rail/check reports the measured number of findings, or the issue
  states that the new checker starts advisory because the count is not yet zero.
- Representative examples include file paths and line numbers.
- Findings are classified as true positive, accepted exception, or detector
  overreach before broad cleanup.
- Direct rail/check command exits 0 before enforcement.
- `scripts/ci/rails.toml`, guardrail docs, `SECURITY.md`, and
  `tests/ci/test_ci_rails_framework.py` are updated when enforcement changes.
- `pytest tests/ci -q --override-ini="addopts="` passes.
- `pre-commit run --all-files` passes before the PR is marked ready.
