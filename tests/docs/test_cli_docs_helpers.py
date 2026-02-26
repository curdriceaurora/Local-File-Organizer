"""Unit tests for CLI docs accuracy helper functions.

Tests the introspection and doc-parsing helpers defined in
``test_cli_docs_accuracy.py`` to ensure their regex patterns and logic
are correct in isolation — independent of the actual CLI reference docs.

Created for GitHub issue #444 (semantic validation for test logic).
"""

from __future__ import annotations

import click
import pytest

from tests.docs.test_cli_docs_accuracy import (
    _collect_commands,
    _command_is_documented,
    _get_command_section,
    _Param,
    _param_is_documented,
    _param_name_variants,
)

# ---------------------------------------------------------------------------
# Test _command_is_documented
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCommandIsDocumented:
    """Verify _command_is_documented matches the right patterns."""

    # -- Positive matches (should return True) --

    def test_header_pattern_h3(self) -> None:
        doc = "### `organize`\nOrganizes files.\n"
        assert _command_is_documented(doc, "organize") is True

    def test_header_pattern_h4(self) -> None:
        doc = "#### `config show`\nShows config.\n"
        assert _command_is_documented(doc, "config show") is True

    def test_header_pattern_h2(self) -> None:
        doc = "## `profile template apply`\nApply a template.\n"
        assert _command_is_documented(doc, "profile template apply") is True

    def test_table_row_pattern(self) -> None:
        doc = "| `autotag suggest FILE...` | Suggest tags |\n"
        assert _command_is_documented(doc, "autotag suggest") is True

    def test_usage_pattern(self) -> None:
        doc = "```\nfile-organizer organize INPUT_DIR OUTPUT_DIR\n```\n"
        assert _command_is_documented(doc, "organize") is True

    def test_table_row_with_leading_spaces(self) -> None:
        doc = "  | `dedupe scan` | Scan for dupes |\n"
        assert _command_is_documented(doc, "dedupe scan") is True

    # -- Negative matches (should return False) --

    def test_not_present(self) -> None:
        doc = "### `organize`\nOrganizes files.\n"
        assert _command_is_documented(doc, "nonexistent") is False

    def test_substring_no_match_in_header(self) -> None:
        """'list' should NOT match a header '### `playlist`'."""
        doc = "### `playlist`\nLists songs.\n"
        assert _command_is_documented(doc, "list") is False

    def test_substring_no_match_in_table(self) -> None:
        """'list' should NOT match table row '| `playlist` |'."""
        doc = "| `playlist` | Lists songs |\n"
        assert _command_is_documented(doc, "list") is False

    def test_plain_text_not_matched(self) -> None:
        """Command name in prose (no backticks/header) should not match."""
        doc = "The organize command is useful.\n"
        assert _command_is_documented(doc, "organize") is False

    def test_partial_table_row_no_pipe_start(self) -> None:
        """Table cell without leading pipe should not match table pattern."""
        doc = "`organize` | Organizes files |\n"
        # No leading |, so table_pattern won't match. But check usage/header too.
        # This should NOT match because there's no header and no 'file-organizer' usage.
        assert _command_is_documented(doc, "organize") is False


# ---------------------------------------------------------------------------
# Test _get_command_section
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCommandSection:
    """Verify _get_command_section extracts the right text range."""

    SAMPLE_DOC = (
        "## Commands\n\n"
        "### `organize`\n"
        "Organize your files.\n\n"
        "Options:\n"
        "- `--dry-run`\n\n"
        "### `dedupe`\n"
        "Deduplicate.\n"
    )

    def test_extracts_section(self) -> None:
        section = _get_command_section(self.SAMPLE_DOC, "organize")
        assert "Organize your files." in section
        assert "`--dry-run`" in section

    def test_stops_at_next_header(self) -> None:
        section = _get_command_section(self.SAMPLE_DOC, "organize")
        assert "Deduplicate." not in section

    def test_missing_command_returns_empty(self) -> None:
        section = _get_command_section(self.SAMPLE_DOC, "nonexistent")
        assert section == ""

    def test_last_command_to_eof(self) -> None:
        section = _get_command_section(self.SAMPLE_DOC, "dedupe")
        assert "Deduplicate." in section

    def test_nested_header_levels(self) -> None:
        """h4 section stops at the next h4 or h3, not at h5."""
        doc = (
            "### Parent\n\n"
            "#### `child`\n"
            "Child content.\n\n"
            "##### Details\n"
            "Extra details.\n\n"
            "#### `sibling`\n"
            "Sibling content.\n"
        )
        section = _get_command_section(doc, "child")
        assert "Child content." in section
        assert "Extra details." in section
        assert "Sibling content." not in section


# ---------------------------------------------------------------------------
# Test _param_name_variants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParamNameVariants:
    """Verify _param_name_variants generates the right representations."""

    def test_option_variants(self) -> None:
        param = _Param(name="refresh_token", kind="option")
        variants = _param_name_variants(param)
        assert "--refresh-token" in variants
        assert "--refresh_token" in variants
        assert "refresh_token" in variants
        assert "REFRESH_TOKEN" in variants

    def test_argument_variants(self) -> None:
        param = _Param(name="input_dir", kind="argument")
        variants = _param_name_variants(param)
        assert "INPUT_DIR" in variants
        assert "input_dir" in variants
        assert "input-dir" in variants

    def test_argument_metavar_first(self) -> None:
        """Explicit metavar should be first for arguments."""
        param = _Param(name="name", kind="argument", metavar="PROFILE_NAME")
        variants = _param_name_variants(param)
        assert variants[0] == "PROFILE_NAME"

    def test_option_metavar_excluded(self) -> None:
        """Options should NOT include metavar to avoid false positives."""
        param = _Param(name="output", kind="option", metavar="TEXT")
        variants = _param_name_variants(param)
        assert "TEXT" not in variants

    def test_no_duplicates(self) -> None:
        param = _Param(name="name", kind="argument", metavar="NAME")
        variants = _param_name_variants(param)
        # "NAME" appears both as metavar and as name.upper() — should be deduped
        assert len(variants) == len(set(variants))


# ---------------------------------------------------------------------------
# Test _param_is_documented
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParamIsDocumented:
    """Verify _param_is_documented matching logic."""

    def test_backtick_option_match(self) -> None:
        section = "Use `--output TEXT` to specify."
        param = _Param(name="output", kind="option")
        assert _param_is_documented(section, param) is True

    def test_backtick_argument_match(self) -> None:
        section = "Provide `PROFILE_NAME` as the first argument."
        param = _Param(name="name", kind="argument", metavar="PROFILE_NAME")
        assert _param_is_documented(section, param) is True

    def test_word_boundary_option_match(self) -> None:
        section = "The --refresh-token option is required."
        param = _Param(name="refresh_token", kind="option")
        assert _param_is_documented(section, param) is True

    def test_missing_param(self) -> None:
        section = "This section has no relevant params."
        param = _Param(name="secret_key", kind="option")
        assert _param_is_documented(section, param) is False

    def test_short_name_not_matched_in_prose(self) -> None:
        """Short generic names like 'name' should not match prose words."""
        section = "The name of the command is organize."
        param = _Param(name="name", kind="argument")
        # "name" is 4 chars — below the >4 threshold for word-boundary fallback
        # No backtick match either. Should fail UNLESS metavar provides a longer form.
        assert _param_is_documented(section, param) is False

    def test_short_name_matched_via_metavar(self) -> None:
        """Short names rescued by explicit metavar."""
        section = "Provide `PROFILE_NAME` to identify the profile."
        param = _Param(name="name", kind="argument", metavar="PROFILE_NAME")
        assert _param_is_documented(section, param) is True

    def test_option_with_trailing_type(self) -> None:
        """Backticked option with trailing type info should match."""
        section = "Specify `--strategy confident` to use confidence."
        param = _Param(name="strategy", kind="option")
        assert _param_is_documented(section, param) is True

    def test_option_with_short_flag_in_backticks(self) -> None:
        """Backticked option with short flag alias should match."""
        section = "Use `--force, -f` to skip confirmation."
        param = _Param(name="force", kind="option")
        assert _param_is_documented(section, param) is True


# ---------------------------------------------------------------------------
# Test _collect_commands
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCollectCommands:
    """Verify _collect_commands recursive Click introspection."""

    @pytest.fixture()
    def sample_group(self) -> click.Group:
        """Build a small Click group for testing."""
        grp = click.Group(name="root")

        @grp.command(name="simple")
        @click.argument("input_file")
        def simple_cmd(input_file: str) -> None:
            pass

        sub = click.Group(name="sub")

        @sub.command(name="leaf")
        @click.argument("name", metavar="PROFILE_NAME")
        @click.option("--force", "-f", is_flag=True)
        def leaf_cmd(name: str, force: bool) -> None:
            pass

        grp.add_command(sub)
        return grp

    def test_finds_leaf_commands(self, sample_group: click.Group) -> None:
        commands = _collect_commands(sample_group)
        paths = [c.path for c in commands]
        assert "simple" in paths
        assert "sub leaf" in paths

    def test_skips_groups(self, sample_group: click.Group) -> None:
        """Groups themselves should not appear as leaf commands."""
        commands = _collect_commands(sample_group)
        paths = [c.path for c in commands]
        assert "sub" not in paths

    def test_collects_required_params(self, sample_group: click.Group) -> None:
        commands = _collect_commands(sample_group)
        simple = next(c for c in commands if c.path == "simple")
        assert len(simple.required_params) == 1
        assert simple.required_params[0].name == "input_file"
        assert simple.required_params[0].kind == "argument"

    def test_extracts_metavar(self, sample_group: click.Group) -> None:
        commands = _collect_commands(sample_group)
        leaf = next(c for c in commands if c.path == "sub leaf")
        arg_params = [p for p in leaf.required_params if p.kind == "argument"]
        assert len(arg_params) == 1
        assert arg_params[0].metavar == "PROFILE_NAME"

    def test_prefix_propagation(self, sample_group: click.Group) -> None:
        commands = _collect_commands(sample_group, prefix="myapp")
        paths = [c.path for c in commands]
        assert "myapp simple" in paths
        assert "myapp sub leaf" in paths

    def test_skips_non_required_params(self, sample_group: click.Group) -> None:
        """Optional params (--force is_flag, no required=True) should be excluded."""
        commands = _collect_commands(sample_group)
        leaf = next(c for c in commands if c.path == "sub leaf")
        param_names = [p.name for p in leaf.required_params]
        assert "force" not in param_names


# ---------------------------------------------------------------------------
# Test extractability gap (bug #446)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractabilityGap:
    """Detect the gap where _command_is_documented returns True via table row
    but _get_command_section returns empty because it only matches headers.

    This is bug #446 — a command can be "documented" in a table but have no
    extractable section, causing param checks to silently skip.
    """

    TABLE_ONLY_DOC = (
        "## CLI Reference\n\n"
        "| Command | Description |\n"
        "| --- | --- |\n"
        "| `organize` | Organizes files |\n"
        "| `dedupe` | Deduplication |\n\n"
        "### `dedupe`\n"
        "Deduplicate files.\n"
    )

    def test_table_documented_but_no_section(self) -> None:
        """'organize' is in the table but has no header section."""
        assert _command_is_documented(self.TABLE_ONLY_DOC, "organize") is True
        section = _get_command_section(self.TABLE_ONLY_DOC, "organize")
        assert section == "", (
            "Expected empty section for table-only documented command. "
            "Bug #446: _get_command_section should return '' when only "
            "table-row match exists."
        )

    def test_header_documented_has_section(self) -> None:
        """'dedupe' has both table entry and header — should have a section."""
        assert _command_is_documented(self.TABLE_ONLY_DOC, "dedupe") is True
        section = _get_command_section(self.TABLE_ONLY_DOC, "dedupe")
        assert "Deduplicate files." in section

    def test_gap_detection_pattern(self) -> None:
        """Demonstrate the detection pattern for the #446 gap:
        command is documented but section is empty → params can't be checked.
        """
        gaps: list[str] = []
        for cmd_path in ["organize", "dedupe"]:
            is_doc = _command_is_documented(self.TABLE_ONLY_DOC, cmd_path)
            section = _get_command_section(self.TABLE_ONLY_DOC, cmd_path)
            if is_doc and not section:
                gaps.append(cmd_path)

        assert gaps == ["organize"], (
            "Expected 'organize' to be the only command with an "
            "extractability gap (documented in table but no section header)."
        )
