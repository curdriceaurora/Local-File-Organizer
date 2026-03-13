# Legacy Review Regression Security Rules

These rules codify the first-wave security findings from the PR-review audit.
They are intentionally narrow: the goal is to catch repeated, review-derived
path-safety mistakes without turning the detector pack into a generic security
linter.

## Rule Class Coverage

This detector pack owns two patterns:

1. Unguarded direct `Path(...)` construction in API and web code that normally
   sits behind an allow-root enforcement boundary.
1. Validation bypasses where a route handler validates request path fields with
   `resolve_path()` and then later passes the raw request object or raw request
   path fields downstream.

## Approved Safe Patterns

The detector pack treats the following path-handling shapes as approved:

1. Module-local path constants derived from `__file__`, such as
   `BASE_DIR = Path(__file__).resolve().parent`.
1. Basename extraction from untrusted names, such as
   `Path(upload.filename).name.strip()`.
1. Configuration-controlled roots that are paired with an explicit
   `codeql[py/path-injection]` review note.
1. Wrapping an already-reviewed path-like model field for metadata helpers, such
   as `file_info_from_path(Path(info.path))`.
1. Returning `Path(...)` from the path-validation boundary itself, such as the
   final `return Path(resolved_str)` inside `resolve_path()`.
1. Service-layer wrappers that explicitly document their string path parameters
   as pre-validated at the API boundary.

Everything else in guarded API/web contexts should either:

1. call `resolve_path()` before the value is used, or
1. be documented as a reviewed exception in the relevant path-safety contract.

## Validation Bypass Rule

Once a route handler has produced validated aliases such as:

```python
input_path = resolve_path(request.input_dir, settings.allowed_paths)
output_path = resolve_path(request.output_dir, settings.allowed_paths)
```

downstream calls must use those validated aliases or a copied sanitized request
object. Two common safe shapes are:

```python
organizer.organize(input_path=str(input_path), output_path=str(output_path))
```

and:

```python
safe_request = request.model_copy(
    update={"input_dir": str(input_path), "output_dir": str(output_path)}
)
background_tasks.add_task(run_job, "job-1", safe_request)
```

The detector intentionally flags the opposite pattern:

```python
background_tasks.add_task(run_job, "job-1", request)
organizer.organize(input_path=request.input_dir, output_path=request.output_dir)
```

because the path validation happened, but the validated values were not the ones
that reached the downstream sink.
