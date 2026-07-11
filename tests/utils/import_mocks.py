"""Helpers for simulating missing optional dependencies in tests."""

from __future__ import annotations

import builtins
from collections.abc import Callable, Mapping, Sequence
from typing import Any

ImportCallable = Callable[[str, object | None, object | None, tuple[str, ...], int], Any]


def _matches_module(name: str, candidate: str) -> bool:
    """Return True when *name* is *candidate* or one of its dotted submodules."""
    return name == candidate or name.startswith(f"{candidate}.")


def make_fake_import(
    *,
    missing_names: Sequence[str] = (),
    missing_substrings: Sequence[str] = (),
    module_overrides: Mapping[str, Any] | None = None,
    original_import: ImportCallable | None = None,
) -> ImportCallable:
    """Build a safe ``__import__`` side effect for optional-dependency tests.

    The returned callable raises ``ImportError`` for configured missing modules,
    returns explicit overrides for configured module names, and delegates every
    other import to the real importer by construction.
    """
    real_import = builtins.__import__ if original_import is None else original_import
    overrides = dict(module_overrides or {})

    def fake_import(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        for module_name, module_value in overrides.items():
            if _matches_module(name, module_name):
                return module_value

        if any(_matches_module(name, module_name) for module_name in missing_names):
            raise ImportError(f"no {name}")

        if any(substring in name for substring in missing_substrings):
            raise ImportError(f"no {name}")

        return real_import(name, globals, locals, fromlist, level)

    return fake_import
