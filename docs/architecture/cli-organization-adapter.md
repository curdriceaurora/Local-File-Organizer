# CLI organization adapter

`fo organize` and `fo preview` are presentation adapters over the canonical
`OrganizationService`. They do not construct `FileOrganizer` or define traversal,
classification, collision, transfer, or methodology policy themselves.

## Reviewed-plan flow

Create and inspect a plan without applying files:

```console
fo preview INPUT --output-dir OUTPUT --save-plan plan.json
```

Apply that exact plan later:

```console
fo organize INPUT OUTPUT --plan plan.json
```

The plan's roots and resolved `OrganizeOptions` are validated again before any
operation runs. When `--plan` is supplied without behavior flags, its embedded
options are authoritative. Supplying behavior flags explicitly causes the
service to compare them with the reviewed plan and reject a mismatch. Schema-1
plans remain load/inspect-only; create a new preview before execution.

The legacy `fo preview INPUT` invocation remains supported and uses `INPUT` as
the display-only destination root. Use `--output-dir` for a plan intended to be
applied.

## Canonical options

Both commands map the same controls into `OrganizeOptions`: recursion, hidden
files, existing-target policy, transfer mode, methodology, vision and audio
processing, worker/prefetch tuning, and model/provider identity. `--text-only`
and `--no-prefetch` remain compatibility aliases. A transcription duration of
`0` means no cap.

## JSON contract

Place global `--json` before the command or use the command-local `--json` flag.
Successful output is one JSON object with `schema_version: 1`, `outcome: "ok"`,
`command`, `mode`, canonical `request`, `result`, and serialized `plan`. Preview
also includes `scan`; fields not produced for a mode are `null` rather than
omitted.

Errors use the same envelope with `outcome: "error"` and a stable domain error
(`code`, `message`, `retryable`, optional `details`) or an unexpected-error
shape (`error_type`, `message`, and plan conflicts when applicable). Domain and
organizer progress rendering is suppressed in JSON mode, so stdout contains
exactly one scriptable JSON document.

Exit codes are:

- `0`: success
- `1`: execution or optional-feature failure
- `2`: invalid request or missing input
- `3`: conflict, reviewed-plan mismatch, or recovery-required state

The CLI driver runs the shared conformance corpus alongside the direct-service
driver. Registry entries for CLI organization and methodology are marked
verified only while that suite remains green.
