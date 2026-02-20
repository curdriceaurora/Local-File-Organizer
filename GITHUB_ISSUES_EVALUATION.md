# GitHub Issues Evaluation — Next Steps

**Date:** 2026-02-20
**Open Issues:** 37
**Evaluation Scope:** All open issues in curdriceaurora/Local-File-Organizer

---

## Executive Summary

The repository has 37 open issues spanning 4 EPICs, 10 active testing stories, 8 deferred testing stories, and 15 individual issues (bugs, features, docs, CI). The project is mature with phases 2 and 5 fully complete, and phases 3, 4, and 6 at 94-96% completion. The primary bottlenecks are: (1) testing infrastructure gaps blocking CI reliability, (2) a critical image processing performance problem, and (3) the last-mile completion of three near-done phases.

---

## Issue Inventory (37 Open)

### EPICs (4)
| # | Title | Priority | Progress |
|---|-------|----------|----------|
| #2 | Phase 3: Feature Expansion | Medium | 94% (15/16 tasks) |
| #6 | Testing & Quality Assurance | High | 65% |
| #7 | Documentation & User Guides | Low | In Progress |
| #8 | Performance Optimization (Image Processing) | **Critical** | Planned |

### Bugs (2)
| # | Title | Severity | Effort |
|---|-------|----------|--------|
| #106 | fix(para): Replace hardcoded 0.75 threshold | Low | Done (PR #376 merged, may need closing) |
| #331 | Playwright E2E tests fail in CI | Medium | 4-6 hours |

### Feature Enhancements (3)
| # | Title | Priority | Effort |
|---|-------|----------|--------|
| #44 | Audio content-based organization | Medium | 16 hours |
| #108 | PARA category string validation in rules engine | Low | 2-3 hours |
| #335 | Request to Add OpenAI support | **Declined** | N/A (conflicts with privacy-first architecture) |

### Security (1)
| # | Title | Priority | Effort |
|---|-------|----------|--------|
| #351 | Plugin metadata import isolation | Medium | Significant (architectural) |

### CI/Infrastructure (3)
| # | Title | Priority | Effort |
|---|-------|----------|--------|
| #369 | Add `act` for local CI simulation via Docker | Low | 4-8 hours |
| #370 | Add macOS runner to CI matrix | Medium | 2-4 hours |
| #371 | Add Windows runner to CI matrix | Medium | 2-4 hours |

### Documentation (5)
| # | Title | Priority | Effort |
|---|-------|----------|--------|
| #13 | Update documentation and create user guide | Medium | 8-16 hours |
| #100 | Fix markdown link fragments in rule-examples.md | Low | 1 hour |
| #103 | Add CUDA/cuDNN/FFmpeg install requirements to README | Low | 1-2 hours |
| #255 | Add real screenshots + demo GIF for Phase 2 docs | Low | 2-4 hours |
| #322 | Complete file format support documentation | Low | 4-8 hours |
| #325 | Add performance tuning and optimization guide | Low | 4-8 hours |

### Testing Stories — Active (10)
| # | Title | Priority |
|---|-------|----------|
| #378 | Story 1: Test Infrastructure Hardening | **High** |
| #379 | Story 2: File Readers Test Coverage | High |
| #380 | Story 3: Core Organizer Test Coverage | High |
| #381 | Story 4: Text Processing Utils Test Coverage | High |
| #382 | Story 5: Text Model & Model Manager Test Coverage | High |
| #383 | Story 6: Text Processor Service Test Coverage | High |
| #384 | Story 7: Integration Tests for Text Workflows | Medium |
| #385 | Story 8: CLI & API Test Coverage | Medium |
| #386 | Story 9: Ratchet Coverage Threshold to 45% | Medium |
| #387 | Story 10: Multi-Platform CI (macOS + Windows) | Low |

### Testing Stories — Deferred (8)
| # | Title | Notes |
|---|-------|-------|
| #388 | D1: Audio Transcriber Test Coverage | Requires audio hardware/models |
| #389 | D2: Vision Model Test Coverage | Requires vision models |
| #390 | D3: Vision Processor Service Test Coverage | Requires vision models |
| #391 | D4: Audio Service Tests | Requires audio models |
| #392 | D5: Video Service Tests | Requires video processing deps |
| #393 | D6: E2E / Playwright Tests | Blocked by #331 |
| #394 | D7: Image File Reader Tests | Requires vision deps |
| #395 | D8: Coverage Push to 80% (Long Tail) | Depends on D1-D7 |

---

## Prioritized Next Steps

### Tier 1 — Do Now (High Impact, Unblocks Other Work)

#### 1. Close stale/completed issues
- **#106** appears resolved (PR #376 merged, 3,759 tests passing). Verify and close.
- **#335** (OpenAI support) — maintainer has stated this conflicts with the privacy-first architecture. Close as `wontfix` or convert to a discussion.

#### 2. Testing Stories #378-#383 (Infrastructure + Core Coverage)
These 6 stories form the testing foundation. They should be worked **sequentially starting with #378** (infrastructure hardening), then #379-#383 in order. This directly advances the Testing QA epic (#6) from 65% toward completion and builds confidence for the near-complete phases.

**Why now:** Without solid test coverage, the 94-96% complete phases can't be confidently shipped.

#### 3. Fix #331 — Playwright E2E CI failure
The agreed solution (mock Ollama + Redis as service containers, fix port mismatch) is well-scoped at 4-6 hours. This unblocks:
- Deferred testing story #393 (E2E/Playwright tests)
- Reliable CI for the Phase 6 web interface
- Removal of `continue-on-error: true` from CI config

### Tier 2 — Do Next (Complete Near-Done Phases)

#### 4. Complete Phase 3 (#2) — Finish #44 (Audio content-based organization)
Phase 3 is at 94% with one task remaining. The `AudioTranscriber` is already built; the remaining work is the classification pipeline and organization strategies. ~16 hours of effort to close out an entire phase.

#### 5. Testing Stories #384-#386 (Integration, CLI/API, Coverage Ratchet)
After core coverage (#378-#383), these stories extend coverage to integration tests and establish an automated coverage threshold. #386 (ratchet to 45%) creates a floor that prevents regression.

#### 6. #108 — PARA category string validation
Small enhancement (2-3 hours) that improves data integrity in the rules engine. Low risk, easy win.

### Tier 3 — Plan & Schedule

#### 7. Performance Optimization (#8) — Image Processing
This is the project's biggest technical challenge: 240s per image needs to drop to <30s. This requires dedicated investigation:
- Profile with cProfile/py-spy to find the actual bottleneck
- Test GPU acceleration (CUDA/Metal)
- Evaluate model quantization options
- Consider alternative vision models

**Recommendation:** Create a time-boxed spike (1-2 days) to profile and identify the top 3 optimization opportunities before committing to a full implementation plan.

#### 8. CI Matrix Expansion (#370, #371, #387)
Adding macOS and Windows runners strengthens cross-platform confidence. Should be done after the core test infrastructure (#378) is solid. These three issues overlap — #387 is the testing story that encompasses #370 and #371.

#### 9. Plugin Security Hardening (#351)
The current in-process metadata import is a known limitation. The fix (static manifest file or sandboxed subprocess) is architectural and should be planned as a focused effort after higher-priority items are resolved.

### Tier 4 — Backlog (Do When Convenient)

#### 10. Documentation issues (#13, #100, #103, #255, #322, #325)
Six documentation issues of varying size. These don't block any development work. Batch them into a documentation sprint or address incrementally.

**Quick wins:** #100 (fix link fragments, ~1h) and #103 (add install requirements, ~1-2h) can be done in spare cycles.

#### 11. Local CI simulation (#369)
`act` for Docker-based local CI is a nice developer experience improvement but doesn't block anything.

#### 12. Deferred testing stories (#388-#395)
These require specialized hardware/models (audio, vision, video). They should remain deferred until the infrastructure to support them in CI exists or can be mocked effectively.

---

## Recommended Execution Order

```
Week 1:  Housekeeping (#106 close, #335 close)
         + Testing #378 (Infrastructure Hardening)
         + Testing #379-#381 (File Readers, Core Organizer, Text Utils)

Week 2:  Testing #382-#383 (Text Model, Text Processor)
         + Fix #331 (Playwright CI)
         + #108 (PARA validation)

Week 3:  #44 (Audio content-based org) → Close Phase 3
         + Testing #384-#386 (Integration, CLI/API, Coverage Ratchet)

Week 4:  Performance spike for #8 (Image processing profiling)
         + CI matrix expansion (#370, #371)
         + Documentation quick wins (#100, #103)
```

---

## Issues That Can Be Closed

| # | Reason |
|---|--------|
| #106 | Already fixed in PR #376 |
| #335 | Conflicts with privacy-first architecture (maintainer confirmed) |

## Issues That Should Be Consolidated

| Issues | Consolidation |
|--------|---------------|
| #370, #371, #387 | #387 (Multi-Platform CI) encompasses both #370 and #371 |
| #331, #393 | #393 (E2E tests) is blocked by #331 — fixing #331 enables #393 |

---

## Key Risks

1. **Performance (#8)** — 8x improvement target is ambitious. May require model architecture changes, not just configuration tuning.
2. **Testing depth** — 8 deferred testing stories represent significant coverage gaps in audio/vision/video. These gaps persist until mocking strategies or model stubs exist in CI.
3. **Phase 4 blocked tasks** — 6 tasks in the Intelligence epic are blocked on sequential dependencies. The dependency chain should be reviewed to see if any can be parallelized.
4. **Phase 5 defects** — 5 post-completion defects (#291-#295) identified but not tracked as open issues. These should be triaged.

---

*Generated from analysis of 37 open GitHub issues and CCPM epic tracking data.*
