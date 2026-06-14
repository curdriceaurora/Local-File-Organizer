"""Unit tests for src/cli/path_validation.py (Epic A.cli, hardening roadmap #154).

The helper wraps ``core.path_guard.validate_within_roots`` with CLI-specific
ergonomics: human-readable errors via ``typer.BadParameter`` (so argparse/typer
surfaces them at the usage boundary rather than bubbling a raw
``PathTraversalError`` up to an end user), plus default-on existence and
directory-type checks for commands that take a directory argument.

Covered contracts:

- ``resolve_cli_path(path, *, must_exist, must_be_dir)`` normalises ``..``,
  resolves symlinks in the root, and returns a canonical absolute ``Path``.
- Raises ``typer.BadParameter`` when the path doesn't exist (``must_exist``)
  or isn't a directory (``must_be_dir``) — **not** ``FileNotFoundError``
  so typer prints the usage-level error rather than a Python traceback.
- ``validate_pair(input_dir, output_dir)`` catches the classic footgun
  where ``output_dir`` sits inside ``input_dir`` (the organizer would then
  write into the tree it's reading). Raises ``typer.BadParameter``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import typer

from file_organizer.cli.path_validation import resolve_cli_path, validate_pair

# --------------------------------------------------------------------------
# resolve_cli_path — happy paths
# --------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.integration
class TestResolveCliPath:
    def test_existing_directory_is_returned_resolved(self, tmp_path: Path) -> None:
        """A plain existing directory passes through and comes back resolved."""
        result = resolve_cli_path(tmp_path)
        assert result == tmp_path.resolve()
        assert result.is_absolute()

    def test_dotdot_traversal_is_normalized(self, tmp_path: Path) -> None:
        """``/a/b/../c`` must resolve to ``/a/c``. Same security property the
        A.foundation walker sweep relied on, but re-checked at the CLI layer
        so downstream code sees a canonical path.
        """
        nested = tmp_path / "sub"
        nested.mkdir()
        weird = tmp_path / "sub" / ".." / "sub"
        result = resolve_cli_path(weird)
        assert result == nested.resolve()

    def test_relative_path_resolved_against_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Typer delivers plain ``Path(arg)`` which is relative. The helper
        anchors it to the current working directory so all downstream
        validation works on an absolute form.
        """
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sub").mkdir()
        result = resolve_cli_path(Path("sub"))
        assert result == (tmp_path / "sub").resolve()

    def test_must_exist_false_allows_missing_path(self, tmp_path: Path) -> None:
        """Commands that *create* their output dir (e.g. ``organize OUTPUT``
        when OUTPUT doesn't exist yet) pass ``must_exist=False`` — the
        helper still resolves ``..`` but doesn't require the path on disk.
        """
        missing = tmp_path / "will_be_created"
        result = resolve_cli_path(missing, must_exist=False)
        assert result == missing.resolve()

    def test_must_be_dir_false_allows_file_argument(self, tmp_path: Path) -> None:
        """Commands that take a file (``fo analyze FILE``) pass
        ``must_be_dir=False`` — directory check doesn't apply.
        """
        file_path = tmp_path / "target.txt"
        file_path.write_text("x")
        result = resolve_cli_path(file_path, must_be_dir=False)
        assert result == file_path.resolve()


# --------------------------------------------------------------------------
# resolve_cli_path — error paths (F1 — every external call handled)
# --------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.integration
class TestResolveCliPathErrors:
    def test_missing_path_raises_bad_parameter(self, tmp_path: Path) -> None:
        """Non-existent path with ``must_exist=True`` surfaces as
        ``typer.BadParameter`` — typer renders this as
        ``Usage: ... Error: Invalid value for '...': Path does not exist: ...``
        instead of a Python traceback.
        """
        missing = tmp_path / "nope"
        with pytest.raises(typer.BadParameter, match="does not exist"):
            resolve_cli_path(missing)

    def test_file_when_dir_expected_raises_bad_parameter(self, tmp_path: Path) -> None:
        """``fo organize INPUT`` pointed at a file gets a helpful error
        rather than a later ``NotADirectoryError`` from the service layer.
        """
        file_path = tmp_path / "single.txt"
        file_path.write_text("x")
        with pytest.raises(typer.BadParameter, match="not a directory"):
            resolve_cli_path(file_path, must_be_dir=True)

    def test_error_message_includes_original_input(self, tmp_path: Path) -> None:
        """The user wrote ``../nope``; the error message shows that literal
        (so they can spot the typo) and the resolved form (so they can see
        where `..` led).
        """
        missing = tmp_path / ".." / "nope"
        with pytest.raises(typer.BadParameter) as excinfo:
            resolve_cli_path(missing)
        # T4: both halves must appear — disjunction would pass even if the
        # original literal is ever dropped from the message.
        message = str(excinfo.value)
        assert str(missing) in message
        assert str(missing.resolve()) in message

    def test_resolution_failure_becomes_bad_parameter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``Path.resolve`` can raise ``RuntimeError`` (py<3.13) or ``OSError``
        (py>=3.13) on symlink loops and unresolvable ``~user``. The helper's
        contract is to surface these as ``typer.BadParameter`` so typer emits
        a usage error (exit 2) instead of an internal traceback.
        """

        def _boom(_self: Path, *_: object, **__: object) -> Path:
            raise OSError("ELOOP: synthetic symlink loop")

        # Narrow patch: only Path.resolve calls via file_organizer.cli.path_validation
        # raise — leaves the rest of the test machinery (pytest internals, tmp_path,
        # other imported modules) free to resolve paths normally.
        monkeypatch.setattr("file_organizer.cli.path_validation.Path.resolve", _boom)
        with pytest.raises(typer.BadParameter) as excinfo:
            resolve_cli_path(tmp_path / "anywhere")
        assert "Unable to resolve path" in str(excinfo.value)


# --------------------------------------------------------------------------
# validate_pair — input/output dir coherence
# --------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.integration
class TestValidatePair:
    def test_disjoint_input_output_accepted(self, tmp_path: Path) -> None:
        """The common case — ``fo organize IN OUT`` where the two
        directories are unrelated — must not raise.
        """
        in_dir = tmp_path / "in"
        out_dir = tmp_path / "out"
        in_dir.mkdir()
        out_dir.mkdir()
        # No exception means pass.
        validate_pair(in_dir, out_dir)

    def test_output_inside_input_rejected(self, tmp_path: Path) -> None:
        """``fo organize IN IN/subdir`` would have the organizer write
        destination files into the same tree it's reading from — a
        classic footgun. Reject it at the CLI boundary so the user sees
        a typer usage error, not a partially-corrupted output tree.
        """
        in_dir = tmp_path / "src"
        in_dir.mkdir()
        out_dir = in_dir / "nested_out"
        with pytest.raises(typer.BadParameter, match="inside the input"):
            validate_pair(in_dir, out_dir)

    def test_input_inside_output_rejected(self, tmp_path: Path) -> None:
        """Mirror of the above: if the user declares ``fo organize SRC/a OUT``
        where ``OUT`` is actually the parent of ``SRC/a``, the organizer
        could walk the output tree while scanning the input tree."""
        out_dir = tmp_path / "out"
        in_dir = out_dir / "nested_in"
        out_dir.mkdir()
        in_dir.mkdir()
        with pytest.raises(typer.BadParameter, match="inside the output"):
            validate_pair(in_dir, out_dir)

    def test_identical_input_and_output_rejected(self, tmp_path: Path) -> None:
        """``fo organize X X`` is never a legitimate request — the organizer
        would read + write the same tree. Reject with a clear message.
        """
        same = tmp_path / "same"
        same.mkdir()
        with pytest.raises(typer.BadParameter, match="same path"):
            validate_pair(same, same)

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only symlink semantics")
    def test_symlink_resolution_defeats_attempted_escape(self, tmp_path: Path) -> None:
        """A user passing ``OUT`` that's a symlink to somewhere inside ``IN``
        must still be rejected — the check runs against the resolved path,
        not the surface string.
        """
        in_dir = tmp_path / "in"
        real_out_inside_in = in_dir / "real_out"
        in_dir.mkdir()
        real_out_inside_in.mkdir()
        out_link = tmp_path / "out_link"
        out_link.symlink_to(real_out_inside_in)
        with pytest.raises(typer.BadParameter, match="inside the input"):
            validate_pair(in_dir, out_link)


# --------------------------------------------------------------------------
# Sanity: the helper is cwd-independent so CI and local runs agree
# --------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.integration
def test_resolve_cli_path_works_regardless_of_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The helper resolves absolute paths internally, so changing cwd
    shouldn't change the outcome for an absolute input.
    """
    monkeypatch.chdir(os.sep)  # root of filesystem
    result = resolve_cli_path(tmp_path)
    assert result == tmp_path.resolve()
