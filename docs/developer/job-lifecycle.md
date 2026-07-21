# Organization Job Lifecycle

Every adapter represents background organization work with the contracts in
`file_organizer.core.lifecycle`. HTTP status codes, CLI exit codes, UI banners, and SDK exceptions
are translations of this contract; they do not define additional lifecycle states.

## States and transitions

| From | Allowed next states |
|---|---|
| `scheduled` | `running`, `cancelled`, `failed` |
| `queued` | `running`, `completed`, `failed`, `cancelled` |
| `running` | `completed`, `partial`, `failed`, `recovery_required` |
| `partial` | `queued`, `rolling_back`, `recovery_required` |
| `failed` | `queued`, `rolling_back`, `recovery_required` |
| `recovery_required` | `queued`, `rolling_back`, `failed` |
| `completed` | `rolling_back` |
| `rolling_back` | `rolled_back`, `recovery_required`, `failed` |
| `cancelled`, `rolled_back` | none |

Duplicate and illegal transitions fail with `invalid_job_transition`. Mutations may include an
`expected_revision`; a concurrent winner increments the revision and stale writers fail with
`stale_job_revision`. Adapters should retry only after re-reading the current snapshot.

Progress counters are monotonic. `completed + failed + skipped` cannot exceed `total`, and a later
revision cannot reduce any completed counter.

## Idempotency

Callers may supply an idempotency key when creating a job. The key is scoped by job type. Repeated
or concurrent creation with the same `(job_type, idempotency_key)` returns the original job rather
than scheduling duplicate work. Persistent stores enforce the same pair as a unique constraint and
recover a concurrent insert conflict by reading and returning the winning job.

## Scheduling ownership

Delayed organization is a canonical one-shot schedule represented by `status=scheduled` and a
timezone-aware `scheduled_for` timestamp. The adapter hosting the worker owns the timer or queue,
but must perform the canonical transition before execution. Scheduling metadata is serialized in
the job snapshot and persisted by the organization-job repository.

Daemon and watcher automation are separate capabilities. They may create organization jobs, but
their recurring watches and task definitions are not organization-job lifecycle states.

Cancellation is currently guaranteed before work starts (`scheduled` or `queued`). Running file
operations are not advertised as cancellable until a cooperative cancellation boundary exists.
A cancelled job uses `cancelled`, never `failed`.

## Completion and recovery

- `completed`: all executable operations succeeded. If a history transaction exists, the job may
  transition to `rolling_back`.
- `partial`: at least one operation failed and at least one may have committed. The job records its
  exact history transaction and exposes retry or rollback as its recovery action.
- `failed`: execution did not produce a successful result. Retry is the default recovery action.
- `recovery_required`: automatic rollback or recovery could not establish a safe final state;
  manual inspection is required.
- `rolled_back`: the transaction associated with that job—not the globally latest operation—was
  undone successfully.

Recovery transitions preserve the error that caused recovery, so observers retain the original
structured evidence while rollback is in progress and after its outcome is recorded. A retry
transition clears the old error before the next execution attempt.

Copy and hardlink rollback both remove only destinations and preserve sources. Crash recovery for
durable moves remains separate because true move is not a supported organization transfer mode.

## Errors

`file_organizer.core.errors.DomainError` carries a stable `code`, message, retryability flag, and
optional structured details. Known optional-dependency failures use
`optional_feature_unavailable`; adapters must not turn them into a generic internal error.

The REST layer maps domain codes to HTTP status codes while preserving the code and retryability.
Other adapters should make equivalent translations appropriate to their transport.

## Shared persistence

The API/Web in-memory store serializes mutations under one lock, returns copies rather than mutable
store objects, and uses revision checks to prevent lost updates. The SQL organization-job model
persists revision, idempotency, schedule, transaction, recovery, and error-code fields.

History uses one re-entrant lock per database manager across connection creation, cursor reads, and
commit/rollback boundaries. Transaction status changes and undo/redo status flips are committed as
single database transactions so concurrent surfaces cannot interleave them silently.
