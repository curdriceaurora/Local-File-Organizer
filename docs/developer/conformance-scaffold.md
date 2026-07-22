# Conformance Scaffold

The conformance scaffold (`tests/conformance/`) is the executable behavioral
oracle for the cross-surface parity epic. The direct
`OrganizationService` defines canonical behavior; every surface adapter must
reproduce the same normalized outputs when driven over the shared fixture
corpus. Golden expectations always come from canonical service semantics,
never from any adapter.

## Layout

| Module | Role |
| --- | --- |
| `tests/conformance/corpus.py` | Deterministic fixture corpus: pinned bytes and mtimes, tagged cases |
| `tests/conformance/normalize.py` | Strips presentation-only differences while preserving executable ordering and complete source fingerprints |
| `tests/conformance/driver.py` | Driver protocol, direct-service oracle, and CLI/REST/Python SDK adapters |
| `tests/conformance/test_direct_service_conformance.py` | Golden expectations for canonical semantics |

## Fixture corpus

Each `CorpusCase` materializes an identical tree on every run: file content is
fixed, and mtimes are pinned with `os.utime` so source fingerprints and
year-based image folders never drift. Cases are tagged (`traversal`, `hidden`,
`collision`, `duplicates`, `symlink`, `media`, `methodology`, `plan`,
`recovery`) so adapter suites can select the divergence classes they migrate.
Symlink cases are POSIX-only.

Audio and video byte parsing (mutagen/cv2) varies by environment, so the
corpus contract pins per-filename metadata in
`driver.AUDIO_METADATA_BY_NAME` / `driver.VIDEO_METADATA_BY_NAME`. The
canonical classifier and path-generation policy still run unmodified; only
the byte-level extraction seam is stubbed. Adapter drivers must install the
same stubs.

REST plus the synchronous and asynchronous Python SDKs run this same corpus
through in-process HTTP transports. This verifies traversal, complete option
mapping, executable-plan round trips, stable errors, execution results, and
audit effects against the direct-service oracle without relying on route
construction alone.

## Writing an adapter driver

Implement the protocol for your transport and return the same normalized
envelopes:

```python
from tests.conformance.driver import OrganizationConformanceDriver

class CliDriver:
    name = "cli"

    def scan(self, request): ...      # {"outcome": "ok", "scan": {...}} | error envelope
    def preview(self, request): ...   # {"outcome": "ok", "plan": ..., "result": ..., "plan_payload": ...}
    def execute(self, request, plan_payload=None): ...  # adds "audit_events"
```

Rules for adapter drivers (#1595–#1598):

- Map surface inputs onto `OrganizeRequest` / `OrganizeOptions`; never add
  surface-specific defaults to pass a scenario.
- `plan_payload` is the transport-neutral `OrganizationPlan.to_dict()` form —
  the reviewed-plan handoff must cross your surface as serialized data.
- Normalize with `tests/conformance/normalize.py` helpers; do not hand-roll
  comparisons.
- Preserve plan operation order. Return audit events in chronological
  execution order; identifiers and timestamps are removed, but ordering is
  part of the conformance contract.
- Reuse the corpus and the golden expectations unchanged. A mismatch is
  either an adapter bug or a contract decision that belongs in the parity
  epic — not a reason to fork expectations.

## Extension points

- Transfer semantics and methodologies (#1602) define the `methodology` fixture and canonical
  copy/hardlink expectations. Adapter suites reuse these assertions as they migrate.
- Errors, jobs, scheduling, and recovery (#1604) define stable domain error envelopes,
  ordered lifecycle events, recovery actions, and transaction-specific rollback expectations.
- Required gates (#1606) promote adapter suites from advisory to blocking
  per the gate-promotion policy in the
  [parity execution plan](../architecture/cross-surface-parity-execution.md).

## Running

```bash
pytest tests/conformance -m conformance --override-ini="addopts="
```

CI runs the suite as the advisory `conformance-advisory` job in the
dedicated `Conformance` workflow — which, unlike the main CI workflow, also
triggers for pushes and pull requests on `feature/cross-surface-parity` — and
inside the full-suite shards. It stays advisory until #1606 promotes required
gates.
