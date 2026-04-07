# PR Monitoring Protocol

Detailed companion to `pr-workflow-master.md` MONITORING state. Check this when you need unique diagnostic scenarios not covered by the master state definitions.

## Monitoring Checklist (run on each cycle)

- [ ] **CI**: Passing / failing / still running / rate limited?
- [ ] **Comments**: New comments posted? CodeRabbit/Copilot finished reviewing?
- [ ] **Approval**: Approved / requested changes / still reviewing?

## Rate Limit Handling

If CodeRabbit/Copilot hit rate limits:
- Continue monitoring, don't trigger additional API calls
- Watch for manual reviewer activity via GitHub UI
- Resume normal tool usage when limit resets

## Issue Resolution Playbook

| Issue | Detection | Action |
|-------|-----------|--------|
| **CI Timeout** | Still running after 30+ min | Check CI logs; may need to restart job |
| **Flaky Test** | Test passes then fails then passes | Document + create follow-up issue; don't chase |
| **Rate Limit** | Copilot/CodeRabbit not reviewing | Continue monitoring; wait for reset |
| **Reviewer Unresponsive** | No activity 24+ hours | Post friendly reminder; escalate if needed |
| **Merge Conflict** | Merge blocked by conflict | `git fetch origin main && git rebase origin/main`, resolve, run pre-commit, `git push --force-with-lease` |
| **Approval + CI Fail** | Approved but new CI failure | Treat as new finding → PR Review Response Protocol |
| **Protected ref error** | "Cannot update protected ref" on merge | See `pr-merge-troubleshooting.md` (branch is behind main) |

## CI Failure Investigation Flow

1. Read failure log — don't guess
2. Reproduce locally if possible
3. Treat as a new finding → invoke PR Review Response Protocol
4. Fix, run quality gates, commit, push → fresh CI

## Merge Conditions Checklist

Before merging, verify ALL:

- [ ] CI passing (all status checks green)
- [ ] All comments addressed (APPLY fixed, SKIP/CLARIFY/DEFER replied)
- [ ] 1 reviewer approval
- [ ] No outstanding "requested changes"

---
**See also**: `pr-workflow-master.md` for state machine navigation, `pr-review-response-protocol.md` for finding remediation steps, `pr-merge-troubleshooting.md` for blocked-merge diagnosis.
