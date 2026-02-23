"""Test that CLI documentation matches actual command registration.

Introspects all Typer/Click commands registered in the app and verifies
that ``docs/cli-reference.md`` documents every command, required argument,
and required option.

This test was created to prevent the doc drift caught in PR #432 (11 review
comments across two rounds).  See GitHub issue #440 for context.
"""

from __future__ import annotations

import re
from typing import NamedTuple

import click
import pytest
import typer

from tests.docs.conftest import DOCS_DIR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLI_REFERENCE = DOCS_DIR / "cli-reference.md"

# Commands intentionally excluded from doc-coverage checks.
# Each entry should have a comment explaining *why* it is excluded.
EXCLUDED_COMMANDS: set[str] = {
    # Hidden / internal aliases that duplicate other commands
}


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------


class _Param(NamedTuple):
    """A required CLI parameter (argument or option)."""

    name: str
    kind: str  # "argument" or "option"
    metavar: str | None = None  # Click's rendered metavar (e.g., PROFILE_NAME)


class _Command(NamedTuple):
    """A CLI command with its full path and required params."""

    path: str  # e.g. "api logout", "profile template apply"
    required_params: list[_Param]


def _get_click_app() -> click.Group:
    """Import the main Typer app and return the underlying Click group."""
    from file_organizer.cli.main import app as typer_app

    return typer.main.get_group(typer_app)


def _get_profile_group() -> click.Group:
    """Import the profile Click group (registered via Click interop)."""
    from file_organizer.cli.profile import profile_command

    return profile_command


def _collect_commands(
    group: click.Group,
    prefix: str = "",
) -> list[_Command]:
    """Recursively walk a Click group and collect every leaf command."""
    results: list[_Command] = []
    for name in sorted(group.commands):
        cmd = group.commands[name]
        full = f"{prefix} {name}".strip() if prefix else name

        if isinstance(cmd, click.Group):
            # Recurse into sub-groups
            results.extend(_collect_commands(cmd, prefix=full))
        else:
            # Leaf command — collect required params
            params: list[_Param] = []
            for p in cmd.params:
                if not p.required:
                    continue
                # Skip the implicit --help flag
                if p.name == "help":
                    continue
                kind = "argument" if isinstance(p, click.Argument) else "option"
                # Get Click's rendered metavar (e.g., PROFILE_NAME vs NAME)
                metavar = p.metavar if hasattr(p, "metavar") else None
                params.append(_Param(name=p.name, kind=kind, metavar=metavar))
            results.append(_Command(path=full, required_params=params))

    return results


# ---------------------------------------------------------------------------
# Fixture: all registered commands
# ---------------------------------------------------------------------------


def _all_registered_commands() -> list[_Command]:
    """Return every CLI command registered in the app."""
    click_app = _get_click_app()

    # Collect commands from the main Typer app
    commands = _collect_commands(click_app)

    # Note: "profile" prefix commands are typically auto-registered via Click
    # interop in main.py, but if they're missing (e.g., due to import errors),
    # manually add them here.
    profile_paths = {c.path for c in commands if c.path.startswith("profile")}
    if not profile_paths:
        try:
            profile_group = _get_profile_group()
            commands.extend(_collect_commands(profile_group, prefix="profile"))
        except ImportError:
            # Profile module may fail to import if optional dependencies
            # (e.g., intelligence services) are not installed; degrade gracefully.
            pass

    return commands


# Cache the result so introspection runs once per session.
_COMMANDS: list[_Command] | None = None


def _get_commands() -> list[_Command]:
    global _COMMANDS
    if _COMMANDS is None:
        _COMMANDS = _all_registered_commands()
    return _COMMANDS


# ---------------------------------------------------------------------------
# Docs parsing helpers
# ---------------------------------------------------------------------------


def _read_docs() -> str:
    """Read cli-reference.md and return its contents."""
    if not CLI_REFERENCE.exists():
        pytest.skip(f"cli-reference.md not found at {CLI_REFERENCE}")
    return CLI_REFERENCE.read_text(encoding="utf-8")


def _command_is_documented(doc_content: str, command_path: str) -> bool:
    """Check whether *command_path* appears in a docs section header.

    Looks for patterns like:
      ### `organize`
      #### `config show`
      #### `profile template apply`
      | `autotag suggest FILE...` | ...
    """
    # Escape for regex
    escaped = re.escape(command_path)

    # Pattern 1: markdown header with backtick-quoted command (primary requirement)
    # e.g. ### `organize`  or  #### `config show`
    header_pattern = rf"#{2,4}\s+`{escaped}`"
    if re.search(header_pattern, doc_content):
        return True

    # Pattern 2: command in a markdown table row (e.g., command reference tables)
    # e.g. | `autotag suggest FILE...` |
    # Use multiline mode to check if the line starts with |
    table_pattern = rf"(?m)^\s*\|\s*`{escaped}\b"
    if re.search(table_pattern, doc_content):
        return True

    # Pattern 3: in a code block as a usage line
    # e.g. file-organizer organize INPUT_DIR OUTPUT_DIR
    usage_pattern = rf"file-organizer\s+{escaped}\b"
    if re.search(usage_pattern, doc_content):
        return True

    return False


def _get_command_section(doc_content: str, command_path: str) -> str:
    """Extract the docs section for a given command.

    Returns text from the command's header to the next header of equal or
    higher level, or to EOF.
    """
    escaped = re.escape(command_path)
    # Find the header
    header_match = re.search(
        rf"(#{2,4})\s+`{escaped}`",
        doc_content,
    )
    if not header_match:
        return ""

    level = len(header_match.group(1))  # number of '#' chars
    start = header_match.start()

    # Find the next header of equal or higher level
    rest = doc_content[header_match.end() :]
    next_header = re.search(rf"^#{{{2},{level}}}\s", rest, re.MULTILINE)
    if next_header:
        end = header_match.end() + next_header.start()
    else:
        end = len(doc_content)

    return doc_content[start:end]


def _param_name_variants(param: _Param) -> list[str]:
    """Generate likely doc representations of a parameter name.

    For an option named ``refresh_token``, we check:
      --refresh-token, --refresh_token, REFRESH_TOKEN
    For an argument named ``input_dir``, we check:
      INPUT_DIR, input_dir, input-dir

    For arguments only: includes Click's explicit metavar if set (e.g., PROFILE_NAME vs NAME).
    For options: omits metavar to avoid false positives from generic Click defaults (TEXT, INTEGER, etc.)
    which may appear in docs without the option itself being documented.
    """
    base = param.name
    variants = [base, base.replace("_", "-"), base.upper(), base.replace("_", "-").upper()]

    # Add Click's explicit metavar ONLY for arguments (not options)
    # Options often have generic metvars (TEXT, INTEGER) that appear in docs unrelated to this option
    if param.kind == "argument" and param.metavar:
        variants.insert(0, param.metavar)

    if param.kind == "option":
        variants.extend([f"--{base}", f"--{base.replace('_', '-')}"])
    return list(dict.fromkeys(variants))  # dedupe, preserve order


def _param_is_documented(section: str, param: _Param) -> bool:
    """Check whether a required parameter appears in the command's doc section.

    Prefers backticked tokens (e.g., `--option`, `ARGUMENT`) over plain text
    to avoid false positives from prose containing parameter names.

    For backticked matches, allows any trailing content within the backticks
    (e.g., `--option TEXT`, `--verbose, -v`, `--output, -o TEXT`) since docs
    may include type info, short-flag aliases, or other annotations.
    """
    variants = _param_name_variants(param)

    # First pass: look for backticked variants (higher confidence)
    # Allow trailing content like types, commas, short flags, e.g.
    # `--user TEXT`, `--verbose, -v`, `FILE_PATH`
    for variant in variants:
        escaped = re.escape(variant)
        # Match a backticked chunk that starts with the variant and may include
        # additional non-backtick characters (types, commas, short flags, etc.)
        if re.search(rf"`{escaped}[^`]*`", section):
            return True

    # Second pass: look for word-boundary matches (lower confidence, but still valid)
    # Only use for non-generic terms to avoid matching English words (e.g., "name" in prose)
    for variant in variants:
        escaped = re.escape(variant)
        # Prefer multi-word or option-format variants (PROFILE_NAME, --option)
        # to avoid matching generic single-word names (NAME, FILE) in prose
        if len(variant) > 4 or variant.startswith("--") or "_" in variant:
            if variant.startswith("--"):
                # \b does not work for leading hyphens (- is \W, so \b before --
                # requires a \w char which is absent at whitespace/SOL).  Use
                # whitespace/start boundary and whitespace/punctuation/end boundary.
                pattern = rf"(?<!\S){escaped}(?=$|\s|[,.)\]])"
            else:
                pattern = rf"\b{escaped}\b"
            if re.search(pattern, section):
                return True

    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAllCommandsDocumented:
    """Every registered CLI command must have a section in cli-reference.md."""

    def test_commands_exist(self) -> None:
        """Verify all registered commands are documented."""
        doc_content = _read_docs()
        commands = _get_commands()

        undocumented = []
        for cmd in commands:
            if cmd.path in EXCLUDED_COMMANDS:
                continue
            if not _command_is_documented(doc_content, cmd.path):
                undocumented.append(cmd.path)

        assert not undocumented, (
            f"{len(undocumented)} CLI command(s) missing from docs/cli-reference.md:\n"
            + "\n".join(f"  - `{p}`" for p in sorted(undocumented))
            + "\n\nFix: Add a section for each missing command."
        )


class TestRequiredArgsDocumented:
    """Required arguments and options for each command must be documented.

    This test checks that all required parameters (both arguments and options)
    appear in the command's documentation section.
    """

    def test_required_arguments(self) -> None:
        """Verify all required arguments and options are mentioned in docs."""
        doc_content = _read_docs()
        commands = _get_commands()

        missing: list[str] = []
        for cmd in commands:
            if cmd.path in EXCLUDED_COMMANDS:
                continue
            if not cmd.required_params:
                continue

            section = _get_command_section(doc_content, cmd.path)
            if not section:
                # Command itself is undocumented — TestAllCommandsDocumented
                # will catch that.  Skip param checks.
                continue

            for param in cmd.required_params:
                if not _param_is_documented(section, param):
                    label = f"--{param.name.replace('_', '-')}" if param.kind == "option" else param.name.upper()
                    missing.append(f"`{cmd.path}` {param.kind} {label}")

        assert not missing, (
            f"{len(missing)} required parameter(s) missing from docs/cli-reference.md:\n"
            + "\n".join(f"  - {m}" for m in sorted(missing))
            + "\n\nFix: Document each required argument/option in the command's section."
        )


class TestNoPhantomCommands:
    """Documented commands should correspond to real registered commands.

    This is the inverse check — commands that appear in docs but don't exist
    in the code.  Lower priority, so only a warning for now.
    """

    def test_documented_commands_exist(self) -> None:
        """Every command documented in a header should be registered."""
        doc_content = _read_docs()
        commands = _get_commands()
        registered = {c.path for c in commands}

        # Also add command groups (e.g., "config" from "config show")
        for cmd_path in list(registered):
            parts = cmd_path.split()
            for i in range(1, len(parts)):
                registered.add(" ".join(parts[:i]))

        # Extract all documented command paths from headers
        # Pattern: ### `cmd` or #### `parent sub`
        header_cmds = re.findall(r"#{2,4}\s+`([^`]+)`", doc_content)

        phantom = []
        for doc_cmd in header_cmds:
            # Normalize: strip trailing options/args shown in header
            clean = doc_cmd.strip()
            # Skip section headers that aren't commands (e.g. "Global Options")
            if " — " in clean:
                clean = clean.split(" — ")[0].strip()
            if clean and clean not in registered:
                phantom.append(clean)

        if phantom:
            pytest.xfail(
                f"{len(phantom)} command(s) in docs/cli-reference.md not found "
                f"in registered CLI:\n"
                + "\n".join(f"  - `{p}`" for p in sorted(phantom))
                + "\n\nThese may be planned/deprecated commands."
            )


# ---------------------------------------------------------------------------
# Summary report (runs as a test but always passes — informational)
# ---------------------------------------------------------------------------


class TestCLIDocsCoverage:
    """Print a coverage summary of CLI docs vs registered commands."""

    def test_coverage_summary(self) -> None:
        """Report CLI documentation coverage stats."""
        if not CLI_REFERENCE.exists():
            pytest.skip("cli-reference.md not found")

        doc_content = CLI_REFERENCE.read_text(encoding="utf-8")
        commands = _get_commands()

        total = len([c for c in commands if c.path not in EXCLUDED_COMMANDS])
        documented = sum(
            1
            for c in commands
            if c.path not in EXCLUDED_COMMANDS
            and _command_is_documented(doc_content, c.path)
        )
        pct = (documented / total * 100) if total else 0

        # This test always passes — it's informational
        print(f"\n\nCLI Docs Coverage: {documented}/{total} commands ({pct:.0f}%)")
        if pct < 100:
            undoc = [
                c.path
                for c in commands
                if c.path not in EXCLUDED_COMMANDS
                and not _command_is_documented(doc_content, c.path)
            ]
            print("Undocumented:")
            for p in sorted(undoc):
                print(f"  - {p}")
