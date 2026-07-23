# Canonical Organization Service

Cross-surface adapters must map their inputs into `OrganizeRequest` and call the direct
`OrganizationService`. The service is transport-neutral: it does not import CLI, FastAPI,
Textual, Jinja, or desktop bridge code.

```python
from pathlib import Path

from file_organizer.core.organize_options import OrganizeOptions, OrganizeRequest
from file_organizer.core.organization_service import OrganizationService

request = OrganizeRequest(
    input_path=Path("Downloads"),
    output_path=Path("Organized"),
    options=OrganizeOptions(
        recursive=True,
        include_hidden=False,
        skip_existing=True,
        enable_vision=True,
    ),
)

service = OrganizationService()
scan = service.scan(request)
preview = service.preview(request)
result = service.execute(request, preview.plan)
```

`scan()` and `preview()` use the same secure collection policy. `execute()` applies the exact
reviewed operations and rejects plans whose roots or resolved options differ from the request.
Adapters may format results differently, but they must not reinterpret these inputs or rebuild
plans themselves.

## Canonical options

`OrganizeOptions` contains traversal, hidden-file, collision, media, model-selection, and runtime
controls. Defaults are validated once before work begins. The direct service resolves configured
text and vision model names/providers before placing the options in a plan, so a plan records the
behavioral inputs used to produce it rather than an unstable “current default.”

`transfer_mode` is the canonical transfer selector and supports `copy` and `hardlink`.
`use_hardlinks` remains an input-only compatibility alias and is not emitted in canonical options.

- `copy` preserves the source and creates an independent destination file.
- `hardlink` preserves the source and creates a destination sharing the same inode. Preview
  execution is rejected if source and destination are on different filesystems.
- Undo removes the created destination for either mode and never removes the source.

True move is intentionally unsupported. Crash-safe source deletion and cross-device recovery must
be specified by the job/recovery contract before a move mode can be added.

`methodology` selects `none`, `para`, or `jd`. The domain organizer applies the selected policy
before collision handling and plan construction. PARA routing uses the existing PARA category
primitives; Johnny Decimal routing uses the repository's default area scheme and numbering
primitives. Presentation adapters must not rewrite destinations after a plan is built.

### Johnny Decimal category allocation

Johnny Decimal requires distinct categories within an area, so `10.01 Taxes` and `10.01 Receipts`
are not a valid pair even though the two paths do not collide.

`apply_organization_methodology` therefore allocates category numbers across the whole batch rather
than per file. It collects the distinct classifier folders routed to each area, sorts them, and
numbers them from `01`. Sorting is what makes the result depend only on the set of classifiers an
area receives and not on the order files were traversed, so the same corpus and options always
produce the same numbering.

Two cases are held constant by design:

- a folder that already carries a valid Johnny Decimal prefix is passed through untouched and
  consumes no category number;
- an area receiving a single classifier still numbers it `01`, so the common case is unchanged.

When an area receives more distinct classifiers than it has category numbers, the tail collapses
into a shared catch-all category (`99 Other`) and each classifier survives as a plain folder beneath
it. Numbering stays valid and the grouping is preserved. Refusing the plan was the alternative and
was rejected deliberately: this organizes files, and an area with a hundred classifier folders is a
pathological input rather than a reason to fail the run.

Allocation runs before collision handling, which is unchanged and still applies to the destinations
this produces.

### Methodology vocabulary

`OrganizationMethodology` in `file_organizer.core.organize_options` is the single authoritative
value model. No adapter defines its own. `file_organizer.config.methodology` derives every constant
from that enum and adds the two things the domain deliberately does not carry:

- **display labels**, a presentation concern that may legitimately differ per surface;
- **legacy aliases** (`content_based` → `none`, `johnny_decimal` → `jd`), accepted only at
  configuration and transport boundaries.

The two layers differ in strictness on purpose. `config.methodology.normalize()` is lenient and
falls back to a caller-supplied default, because it reads persisted configuration and user-supplied
form fields where a stale value must not crash the surface. `OrganizeOptions` is strict and rejects
anything non-canonical, including aliases: an alias reaching the domain means an adapter skipped
normalization, which should fail loudly rather than be quietly understood.

Five adapters cannot derive their vocabulary and are pinned by
`tests/core/test_methodology_vocabulary.py` instead. The REST and Python SDK models and the
TypeScript union stay literal because deriving them would change the emitted OpenAPI schema and the
generated client surface for no behavioral gain. The TUI view's `BINDINGS` and `action_set_*`
handlers stay literal because Textual resolves both at class-definition time and dispatches actions
by name. In each case the guard proves the duplication cannot drift rather than removing it.

Adding a methodology therefore means updating `OrganizationMethodology` and then, by hand:

| Site | Change |
| --- | --- |
| `api/models.py` | add the value to the `methodology` `Literal` |
| `client/models.py` | add the value to the `methodology` `Literal` |
| `client/typescript/types.ts` | add the value to the `methodology` union |
| `tui/methodology_view.py` | add a `Binding` and a matching `action_set_<value>` handler |
| `tui/methodology_view.py` | add the value to `MethodologySelectorPanel._METHODS` and `_SHORTCUTS` |
| `config/methodology.py` | add a display label to `LABELS` |

Everything else — `ORDER`, `DEFAULT`, the CLI validator, the CLI setup prompt, the CLI help text,
and the domain error message — derives automatically. The vocabulary guard fails until every manual
site above agrees with the enum, so an incomplete addition cannot ship.

## Plan compatibility

Organization plan schema 3 records canonical `transfer_mode` and `methodology` options. Schema-1
and schema-2 plans remain loadable and are upgraded in memory using their legacy
`skip_existing`, `use_hardlinks`, and metadata fields. Unknown schema versions are rejected with
an actionable error. Current plans reject conflicting legacy and canonical values and reject
operation types that disagree with `transfer_mode`.

Legacy-plan compatibility is load/inspect compatibility. The direct service requires callers to
re-preview before execution because legacy plans do not record the complete canonical contract and
cannot match a fully resolved schema-3 request safely.

The REST plan payload exposes schema-3 options. Updating the Python SDK's mirrored plan model is
owned by the REST/SDK adapter migration in #1596.

Operations are ordered by source path before serialization. Existing `SourceFingerprint`
validation remains the authority for detecting changed sources between preview and execution.

Run the focused contract tests with:

```bash
pytest tests/core/test_organize_options.py \
  tests/core/test_organization_service.py \
  tests/core/test_organization_plan.py \
  -q --override-ini=addopts=
```
