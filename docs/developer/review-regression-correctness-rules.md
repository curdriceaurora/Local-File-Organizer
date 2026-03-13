# Legacy Review Regression Correctness Rules

These rules codify the first-wave correctness findings from the PR-review
audit. They intentionally target explicit runtime invariants that previously
regressed in reviewed code, rather than broad style or maintainability smells.

## Rule Class Coverage

This detector pack owns two patterns:

1. Direct `object.__setattr__` writes to validated `StageContext` fields that
   bypass assignment-time path-component validation.
1. Primitive-like values written into `ModelManager._active_models`, which
   breaks the invariant that `get_active_model()` returns a live model instance
   or `None`.

## Invariants Protected

### `validated-field-setattr-bypass`

`StageContext.category` and `StageContext.filename` are validated on every
assignment by `StageContext.__setattr__`. Code that writes those fields via
`object.__setattr__` bypasses that guard and can reintroduce path-traversal
values after context construction.

Safe shape:

```python
context.category = category
context.filename = filename
```

Unsafe shape:

```python
object.__setattr__(context, "category", category)
```

### `primitive-active-model-store`

`ModelManager._active_models` is the live-instance registry. It must never
store model IDs or other primitive sentinels, because `get_active_model()`
would then return the wrong type.

Safe shape:

```python
if new_model is not None:
    self._active_models[model_type] = new_model
else:
    self._active_models.pop(model_type, None)
```

Unsafe shape:

```python
self._active_models[model_type] = new_model_id
```
