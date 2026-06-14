"""CLI-layer path validation — the user-input boundary for fo commands.

Epic A.cli (hardening roadmap #154, §2.5) wires every path-taking CLI
command through this helper before any filesystem operation. Two public
surfaces:

- ``resolve_cli_path(path, *, must_exist, must_be_dir)`` — resolve a single
  argument, surface existence / type errors as ``typer.BadParameter``
  (so typer prints a usage-level error rather than a traceback).
- ``validate_pair(input_dir, output_dir)`` — cross-argument coherence
  for commands that take both an input and an output directory. Rejects
  the classic ``organize IN IN/sub`` footgun where output sits inside
  input, plus the mirror case and the identity case.

Neither helper uses ``core.path_guard.validate_within_roots`` directly:
that helper is for validating *derived* paths against a pre-declared
root set (used inside service-layer walkers). The CLI boundary doesn't
have a pre-declared root — the user's arguments **are** the roots.
This helper exists to resolve + sanity-check those arguments before
they become the allowed roots for downstream code.
"""

from __future__ import annotations

from pathlib import Path

import typer


def _resolve_user_path(path: Path) -> Path:
    """Resolve ``path`` with all resolution failures surfaced as ``BadParameter``.

    ``Path.resolve()`` raises ``RuntimeError`` (Python < 3.13) or ``OSError``
    (Python >= 3.13) on symlink loops and other OS-level resolution failures;
    ``Path.expanduser()`` raises ``RuntimeError`` for unknown ``~user``. The
    CLI contract is to surface these as ``BadParameter`` (typer usage error,
    exit 2) rather than letting a raw traceback escape.
    """
    try:
        return path.expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise typer.BadParameter(f"Unable to resolve path {path!s}: {exc}") from exc


def resolve_cli_path(
    path: Path,
    *,
    must_exist: bool = True,
    must_be_dir: bool = True,
) -> Path:
    """Resolve a CLI path argument and validate it at the argparse boundary.

    Normalises ``..``, resolves symlinks, anchors relatives against the
    current working directory, and — by default — asserts the path exists
    and is a directory. Callers that accept a file (``fo analyze FILE``)
    or a not-yet-created output directory (``fo organize IN OUT`` where
    OUT doesn't exist yet) opt out via the two keyword flags.

    Args:
        path: The typer-delivered ``Path`` argument. May be relative,
            contain ``..``, or be a symlink — all normalised.
        must_exist: If True (default), raise ``typer.BadParameter`` when
            the resolved path is not on disk. Pass False for commands
            that intentionally create the path.
        must_be_dir: If True (default), raise ``typer.BadParameter`` when
            the resolved path exists but is not a directory. Pass False
            for commands that take a file argument.

    Returns:
        The resolved absolute ``Path`` — downstream code can rely on
        ``.is_absolute()`` and a fully-normalised form.

    Raises:
        typer.BadParameter: Missing path (when ``must_exist=True``),
            path-exists-but-not-a-directory (when ``must_be_dir=True``), or
            any OS-level resolution failure (symlink loop, unknown ``~user``).
            Typer renders these as ``Usage: ... Invalid value ...`` rather
            than a Python traceback.
    """
    resolved = _resolve_user_path(path)

    if must_exist and not resolved.exists():
        raise typer.BadParameter(f"Path does not exist: {path!s} (resolved to {resolved!s})")
    if must_be_dir and resolved.exists() and not resolved.is_dir():
        raise typer.BadParameter(
            f"Path exists but is not a directory: {path!s} (resolved to {resolved!s})"
        )
    return resolved


def validate_pair(input_dir: Path, output_dir: Path) -> None:
    """Reject incoherent input/output directory pairs at the CLI boundary.

    Three cases are flagged:

    - **output inside input**: ``fo organize ~/docs ~/docs/sorted`` would
      have the organizer write destination files into the same tree it's
      reading. User almost certainly meant a sibling directory.
    - **input inside output**: mirror image — the organizer could walk
      into the output tree while scanning the input.
    - **identical paths**: ``fo organize X X`` is never legitimate —
      read-and-write on the same tree.

    All three resolve both paths before comparing, so a symlink pointing
    back into the sibling tree is caught just like a literal nested path.

    Args:
        input_dir: Input directory — resolved defensively even though callers
            typically pass an already-resolved path from ``resolve_cli_path``.
            The re-resolve is load-bearing for symlink-based evasion: a caller
            that passed ``Path("out_link")`` pointing at ``in_dir/subdir``
            would slip past the ``relative_to`` comparison without it.
        output_dir: Output directory — resolved defensively (same reasoning).

    Raises:
        typer.BadParameter: When the pair is incoherent by any of the
            three rules above, OR when resolution itself fails (symlink
            loop, unknown ``~user``). The message names the specific
            violation so the user can spot the argument ordering mistake.
    """
    in_resolved = _resolve_user_path(input_dir)
    out_resolved = _resolve_user_path(output_dir)

    if in_resolved == out_resolved:
        raise typer.BadParameter(
            f"Input and output refer to the same path: {in_resolved!s}. Pass different directories."
        )
    try:
        out_resolved.relative_to(in_resolved)
    except ValueError:
        pass
    else:
        raise typer.BadParameter(
            f"Output directory {output_dir!s} (resolved to {out_resolved!s}) "
            f"is inside the input directory {input_dir!s}. The organizer "
            "would write to the same tree it's reading."
        )
    try:
        in_resolved.relative_to(out_resolved)
    except ValueError:
        pass
    else:
        raise typer.BadParameter(
            f"Input directory {input_dir!s} (resolved to {in_resolved!s}) "
            f"is inside the output directory {output_dir!s}. The organizer "
            "would walk the output tree while scanning the input."
        )
