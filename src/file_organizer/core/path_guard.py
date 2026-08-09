"""Path-validation and safe-walk helpers for CLI commands.

Epic A.foundation (hardening roadmap #154). Provides two primitives:

- `validate_within_roots(path, allowed_roots)` — assert `path` resolves inside
  one of the supplied roots and return its canonical absolute form. Raises
  `PathTraversalError` otherwise. A.cli wires this into every CLI command
  that accepts a path argument (see Appendix A.4 of the roadmap spec for
  the full command surface).
- `safe_walk(root, *, follow_symlinks=False, include_hidden=False)` — yield
  files under `root`, filtering symlinks and hidden entries by default.
  Replaces raw `rglob("*")` / `glob("*")` in the **user-input walker
  surfaces** migrated by A.foundation: analytics, pattern analysis,
  misplacement detection, dedup detection, copilot, JD/PARA scans, and
  the `cli/{benchmark,doctor,suggest,utilities}` search/scan commands.
  System-managed walkers that operate on app-owned state are deliberately
  out of scope (see *Scope note* below) and continue to use `glob`/`rglob`
  until they cross a user-input boundary.

Scope note — system-managed paths that *don't* need `safe_walk`:

- `undo/validator.py` (trash directory, system-managed)
- `services/copilot/rules/rule_manager.py` (app-shipped rule yamls)
- `services/intelligence/profile_{manager,migrator}.py` (profile/backup dir)
- `config/path_migration.py` (legacy XDG migration, run once)
- `parallel/persistence.py` (job-queue state, internal only)
- `methodologies/para/migration_manager.py` (internal migration helper)
- `core/file_ops.py::collect_files` (called on a pre-validated organize
  root; safe_walk adoption here tracked as a follow-up)

Design invariants:

- `validate_within_roots()` returns/compares **resolved** paths: input and
  roots are normalized via `Path.resolve()` before any comparison or
  traversal-check, so callers get the canonical form back and don't need
  to re-resolve. `safe_walk()` yields the *lexical* paths produced by
  `Path.glob()` / `Path.rglob()` after applying its filters — callers
  that need canonical paths should resolve them explicitly.
- `PathTraversalError` is a `ValueError` subclass so existing
  `except ValueError` handlers keep working.
- `safe_walk`'s hidden-file filter applies to the path **relative to `root`**
  — if the caller explicitly walks a hidden directory (e.g. scanning
  `.git/` intentionally), the root component doesn't veto every descendant.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class PathTraversalError(ValueError):
    """Raised when a path escapes the declared set of allowed roots.

    Subclasses `ValueError` so callers that want to catch this specifically
    can do so, while generic `except ValueError` paths continue to work.
    """


def validate_within_roots(path: Path, allowed_roots: Iterable[Path]) -> Path:
    """Resolve `path` and assert it lives inside one of `allowed_roots`.

    Returns the resolved absolute path. Raises `PathTraversalError` if:

    - `allowed_roots` is empty (no roots = nothing is allowed).
    - The resolved path is outside every resolved root.

    Each root is resolved before comparison, so symlinked roots are handled
    correctly. A resolved path exactly equal to a root is allowed (e.g.
    `fo analyze DIR` where the directory itself is the target).

    Args:
        path: The path to validate. May be relative, contain `..`, or be a
            symlink — all normalized by `Path.resolve()`.
        allowed_roots: The set of directories the path must be inside.
            Typically the CLI command's input and output directories plus
            any configured system locations (trash, cache) that the command
            legitimately touches.

    Returns:
        The resolved absolute form of `path`.

    Raises:
        PathTraversalError: If `allowed_roots` is empty, if `path`
            resolves outside every root, or if `path.resolve()` itself
            fails (cyclic symlink, stale handle). Callers expecting
            `PathTraversalError` / `ValueError` shouldn't have to also
            handle `RuntimeError` from the resolver.
    """
    try:
        roots = [r.resolve() for r in allowed_roots]
    except (RuntimeError, OSError) as exc:
        raise PathTraversalError(f"Failed to resolve allowed roots: {exc}") from exc
    if not roots:
        raise PathTraversalError(f"No allowed roots declared; cannot validate {path!r}")
    try:
        resolved = path.resolve()
    except (RuntimeError, OSError) as exc:
        raise PathTraversalError(
            f"Failed to resolve {path!r} (likely a symlink cycle or stale handle): {exc}"
        ) from exc
    for root in roots:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return resolved
    raise PathTraversalError(
        f"Path {path!r} (resolved to {resolved!r}) is outside allowed roots: "
        f"{[str(r) for r in roots]}"
    )


@dataclass
class TraversalBudget:
    """A traversal bound shared across several :func:`safe_walk` calls.

    ``max_entries=N`` gives each call its own budget of N. A caller walking
    several roots under one global bound — as the search endpoints do, where
    the bound is a denial-of-service guard on a remote-reachable request —
    needs the count to carry over. Pass one instance to every call:

        budget = TraversalBudget(limit=10_000)
        for root in roots:
            for path in safe_walk(root, max_entries=budget):
                ...

    ``examined`` counts directory entries seen, before the symlink / hidden /
    file-type filters, for the reason given in :func:`safe_walk`.
    """

    limit: int
    examined: int = 0

    @property
    def exhausted(self) -> bool:
        """True once more entries have been examined than the limit allows."""
        return self.examined > self.limit


def _report(
    on_error: Callable[[Path, OSError], None] | None,
    path: Path,
    exc: OSError,
) -> None:
    """Log a skipped path and hand it to *on_error* if the caller wants it.

    The ``logger.debug`` call is unconditional and deliberate. Before the
    #1671 migration, call sites logged their own permission failures; folding
    them into this primitive removed those lines wholesale (see #1674). Logging
    here restores the diagnostic for all of them without touching a single call
    site.

    Exceptions raised by *on_error* are **not** caught. A caller that wants to
    escalate a permission failure into a hard error should be able to, and
    swallowing an exception raised by an error handler would be the same defect
    this function exists to fix.
    """
    logger.debug("safe_walk skipping %s: %s", path, exc)
    if on_error is not None:
        on_error(path, exc)


def _process_walk_entry(
    entry: os.DirEntry,
    *,
    pattern: str,
    recursive: bool,
    only_files: bool,
    follow_symlinks: bool,
    include_hidden: bool,
    walk_fn: Callable[[Path], Iterator[Path]],
    on_error: Callable[[Path, OSError], None] | None = None,
) -> Iterator[Path]:
    """Process a single directory entry during a secure walk."""
    name = entry.name
    if not include_hidden and name.startswith("."):
        return

    entry_path = Path(entry.path)

    # Per-entry OSError (PermissionError, stale NFS handle, etc.) skips
    # that entry instead of aborting the whole walk.
    try:
        is_sym = entry_path.is_symlink()
    except OSError as exc:
        _report(on_error, entry_path, exc)
        return

    if not follow_symlinks and is_sym:
        return

    try:
        is_dir = entry_path.is_dir()
    except OSError as exc:
        _report(on_error, entry_path, exc)
        is_dir = False

    # Note: we do not descend into directory symlinks for recursion (secure)
    if is_dir and not is_sym:
        if recursive:
            yield from walk_fn(entry_path)
        if not only_files:
            if entry_path.match(pattern):
                yield entry_path
    else:
        try:
            is_file = entry_path.is_file()
        except OSError as exc:
            _report(on_error, entry_path, exc)
            is_file = False

        if only_files and not is_file:
            return

        if entry_path.match(pattern):
            yield entry_path


def safe_walk(
    root: Path,
    *,
    pattern: str = "*",
    recursive: bool = True,
    only_files: bool = True,
    follow_symlinks: bool = False,
    include_hidden: bool = False,
    on_error: Callable[[Path, OSError], None] | None = None,
    max_entries: int | TraversalBudget | None = None,
) -> Iterator[Path]:
    """Walk `root` with security filters.

    Drop-in replacement for raw `rglob("*")` / `glob("*")` in every
    user-supplied-root walker.

    Default filters (security-safe):

    - Symlinks (both file and directory symlinks) are skipped — their
      targets may live outside `root` (e.g. a malicious symlink from
      `indexed_dir/escape -> /etc/passwd`).
    - Hidden entries — any path with a component that starts with `.`,
      relative to `root` — are skipped. Catches `.git/`, `.env`,
      `.ssh/authorized_keys`, and similar credential-bearing paths.

    The hidden-file check is relative to `root`: if `root` itself is a
    hidden directory (`.config/fo/…`), descendants with non-hidden parts
    are still yielded. Only components inside the walked subtree are
    filtered.

    Args:
        root: Directory to walk. If it doesn't exist, yields nothing.
        pattern: Glob pattern to match. Default `"*"` (every entry).
        recursive: If True, walk recursively (`rglob`); if False, walk
            only the top level (`glob`). Default True.
        only_files: If True (default), yield files only — directories are
            filtered out. Pass False to yield directories and other
            non-file entries too (used by e.g. empty-directory cleanup).
        follow_symlinks: If True, include symlinked *files* in the output.
            **Does not descend into symlinked directories** on Python
            3.11–3.12 because `Path.rglob()` / `Path.glob()` never
            recurse through directory symlinks on those versions (the
            `recurse_symlinks` parameter only exists in 3.13+). Default
            False (secure — skip symlink entries entirely).
        include_hidden: If True, include dot-prefixed files and descendants
            of dot-prefixed directories. Default False (secure).
        on_error: Called as ``on_error(path, exc)`` for every entry skipped
            because of an ``OSError`` — an unreadable root, an unreadable
            directory, or a per-entry stat failure. The walk continues
            regardless; this only lets the caller *observe* what was skipped
            rather than silently receiving a short list (#1674).

            Reported at every catch site, including per-entry. A caller that
            finds per-entry reports noisy can filter them, whereas one that is
            never told cannot recover the information — and a walk that
            silently returns fewer files is exactly the failure this exists to
            surface.

            Exceptions raised by *on_error* propagate, so a caller can escalate
            a permission failure into a hard error.
        max_entries: If set, stop the walk once this many directory entries
            have been **examined**. Accepts an ``int`` (a budget private to
            this call) or a :class:`TraversalBudget` (shared across calls, for
            a caller walking several roots under one global bound). Counted before the symlink / hidden /
            file-type filters, so it bounds traversal work rather than results
            — a budget on yielded entries would let a tree of dotfiles or
            symlinks traverse arbitrarily far, since each is discarded before
            being counted (#1675). Used by request-scoped walks on
            remote-reachable endpoints, where the bound is a denial-of-service
            guard rather than a UX nicety.

    Yields:
        `Path` objects for each entry under `root` that matches `pattern`
        and passes the filters.
    """
    try:
        if not root.exists():
            return
        # Reject a symlinked root when follow_symlinks=False. Without this,
        # walking on a directory symlink enumerates the target tree —
        # including paths outside the caller's allowed root.
        if not follow_symlinks and root.is_symlink():
            return
    except OSError as exc:
        _report(on_error, root, exc)
        return

    # Entries *examined*, not entries yielded. See the `max_entries` docstring:
    # counting survivors would let a tree of dotfiles or symlinks blow through
    # any budget, because every one of them is discarded before it is yielded.
    budget: TraversalBudget | None
    if isinstance(max_entries, TraversalBudget):
        budget = max_entries  # shared across calls; do not reset `examined`
    elif max_entries is None:
        budget = None
    else:
        budget = TraversalBudget(limit=max_entries)

    def _budget_exhausted() -> bool:
        return budget is not None and budget.exhausted

    def _walk(dir_path: Path) -> Iterator[Path]:
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    if budget is not None:
                        budget.examined += 1
                    if _budget_exhausted():
                        return
                    yield from _process_walk_entry(
                        entry,
                        pattern=pattern,
                        recursive=recursive,
                        only_files=only_files,
                        follow_symlinks=follow_symlinks,
                        include_hidden=include_hidden,
                        walk_fn=_walk,
                        on_error=on_error,
                    )
                    # A nested walk may have exhausted the budget; stop this
                    # level too rather than finishing the current directory.
                    if _budget_exhausted():
                        return
        except OSError as exc:
            _report(on_error, dir_path, exc)
            return

    yield from _walk(root)
