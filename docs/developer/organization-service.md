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

`use_hardlinks` is deliberately retained as the existing transfer selector in this slice. The
transfer-semantics work in #1602 owns its replacement with an explicit copy/hardlink/move model.

## Plan compatibility

Organization plan schema 2 adds the canonical `options` object. Schema-1 plans remain loadable and
are upgraded in memory using their legacy `skip_existing`, `use_hardlinks`, and metadata fields.
Unknown schema versions are rejected with an actionable error. Schema-2 plans reject conflicting
legacy and canonical values rather than silently choosing one.

Schema-1 compatibility is load/inspect compatibility. The direct service requires callers to
re-preview before execution because legacy plans do not record resolved model identity and cannot
match a fully resolved schema-2 request safely.

The REST plan payload exposes schema-2 options. Updating the Python SDK's mirrored plan model is
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
