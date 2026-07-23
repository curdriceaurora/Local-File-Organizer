# Capability Registry

The canonical capability registry is the source of truth for cross-surface product intent and
current parity evidence. It lives in
`src/file_organizer/core/capability_registry.json` and is validated through the transport-neutral
types in `file_organizer.core.capabilities`.

The registry covers the CLI, REST API, Python SDK, TypeScript SDK, Web/Desktop, and TUI. It does
not include developer-only utilities such as documentation serving or benchmarks unless they are
deliberately promoted to public product capabilities.

## Status dimensions

Do not collapse these fields:

- `target_support` records the intended support decision: `full`, `read-only`,
  `redirect/deep-link`, or `not-applicable`.
- `implementation_status` records whether that target currently exists: `implemented`, `partial`,
  `not-implemented`, or `not-applicable`.
- `conformance_status` records whether executable parity evidence exists: `verified`, `unverified`,
  or `not-applicable`.

For example, a surface can target full support while remaining not implemented and unverified.
That is planned work, not a shipped claim.

`execution_scopes` records the modes available for the capability. `local-only` means at least one
adapter executes locally without a remote service. `remote` means a service-backed path exists or
is intended. `auth-gated` qualifies remote execution and therefore must appear with `remote`.

## Adding or changing a capability

1. Reuse an existing stable ID when behavior is evolving without changing its product meaning.
2. Add a new namespaced ID only for a distinct user-visible capability.
3. Declare all six surfaces. Omitting a surface is a validation error.
4. Set the target decision before recording current implementation state.
5. Add concrete public entry points for `implemented` and `partial` surfaces. Planned,
   not-implemented surfaces have no entry points.
6. List relevant project extras in `optional_dependencies` and restrict `platforms` when support is
   not cross-platform.
7. Leave conformance `unverified` until executable, surface-appropriate evidence proves every entry
   point declared for that capability and surface.
8. Update tests when a public client method or surface entry point changes.

Never mark a capability verified because a route, command, view, or method exists. Verification is
owned by the conformance workstream and requires behavior-level evidence. A shared corpus driver
is the preferred evidence for adapters that can invoke the canonical application-service vectors.
For surfaces that cannot host that corpus directly, equivalent executable evidence can combine
compiler checks, contract inventory, and transport behavior tests. `verified` therefore means the
declared behavior has suitable executable evidence; it does not imply that every surface uses the
same harness or that its workflow has already been promoted from advisory to required.

Generated capability matrices must preserve that distinction. Link each verified cell to its
evidence and identify the evidence shape instead of flattening all verified cells into a claim that
one common harness ran everywhere.

## Validation and serialization

Run the focused CI validation with:

```bash
pytest tests/core/test_capabilities.py -q --override-ini=addopts=
```

Consumers load a validated immutable registry and can serialize it deterministically:

```python
from file_organizer.core.capabilities import get_capability_registry

registry = get_capability_registry()
payload = registry.to_json()
```

The packaged JSON is stored in that canonical serialized form. The registry tests compare the
file byte-for-byte with `to_json()`, so edits must preserve canonical key and capability ordering
as well as the explicit defaults emitted by the serializer.

The serialization schema is versioned independently through
`CAPABILITY_REGISTRY_SCHEMA_VERSION`. Change that version only when consumers cannot safely read
the prior shape.

## Capability matrix generation

The product-wide matrix artifact is rendered at [capability-matrix.md](capability-matrix.md).

Generate or check the matrix document using:

```bash
python scripts/generate_capability_matrix.py         # Update docs/developer/capability-matrix.md
python scripts/generate_capability_matrix.py --check # Verify document matches registry state
```

Changes to `capability_registry.json` require re-running the generator script. CI enforces document freshness via `test_capability_matrix_up_to_date` in `tests/core/test_capabilities.py`.

