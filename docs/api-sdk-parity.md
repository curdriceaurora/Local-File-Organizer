# REST and SDK parity contract

The public HTTP inventory is defined in
`file_organizer.client.endpoint_spec.PUBLIC_ENDPOINTS`. Every entry maps one
versioned REST operation to its canonical capability ID and to equivalent
synchronous Python, asynchronous Python, and TypeScript methods.

CI compares that specification with the generated OpenAPI document and the
three client surfaces. TypeScript inventory uses the compiler API rather than
format-sensitive source matching, and the client is compiled under strict
settings before its transport tests run. Adding, removing, or renaming a
public route therefore requires an intentional SDK mapping in the same change.

## Organization behavior

Organization preview and execution accept a nested `options` object containing
the complete canonical `OrganizeOptions` contract. The legacy
`skip_existing` and `use_hardlinks` fields remain compatibility aliases and are
rejected when they contradict `options`. Reviewed schema-3 plans and their
resolved options round-trip through every official SDK.

Background submissions may include an `idempotency_key`. Repeated submissions
return the original job and do not schedule duplicate work. Jobs support
polling, history, revision-guarded cancellation, and rollback through all three
SDKs.

The shared conformance corpus runs through REST and both Python SDK clients in
addition to the direct service and CLI. TypeScript transport tests assert the
canonical organization payload, ordered scan results, and typed error
envelopes using a mocked Fetch implementation.

## Errors and operation IDs

Public errors use the stable `{error, message, details?}` envelope, including
framework `HTTPException`, validation, rate-limit, domain, and unexpected
server failures. OpenAPI operation IDs are generated from the route tag and
handler name so they remain readable and independent of source module paths.

## Intentional transport exclusion

`WS /api/v1/ws/{client_id}` is not represented by OpenAPI. The HTTP SDKs expose
job polling as the portable event alternative. A native WebSocket client will
require a separately versioned realtime protocol and is explicitly tracked as
an exclusion in `INTENTIONAL_EXCLUSIONS`.
