"""Integration tests for plugin security, BM25 index, and plugin SDK decorators.

Covers:
  - plugins/security.py       — PluginSecurityPolicy, PluginSandbox
  - services/search/bm25_index.py — BM25Index, _tokenise
  - plugins/sdk/decorators.py — hook, command, get_hook_metadata, get_command_metadata
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.plugins.errors import PluginPermissionError
from file_organizer.plugins.sdk.decorators import (
    command,
    get_command_metadata,
    get_hook_metadata,
    hook,
)
from file_organizer.plugins.security import PluginSandbox, PluginSecurityPolicy
from file_organizer.services.search.bm25_index import BM25Index, _tokenise

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# PluginSecurityPolicy
# ---------------------------------------------------------------------------


class TestPluginSecurityPolicyUnrestricted:
    def test_created(self) -> None:
        p = PluginSecurityPolicy.unrestricted()
        assert p is not None

    def test_allow_all_paths(self) -> None:
        p = PluginSecurityPolicy.unrestricted()
        assert p.allow_all_paths is True

    def test_allow_all_operations(self) -> None:
        p = PluginSecurityPolicy.unrestricted()
        assert p.allow_all_operations is True


class TestPluginSecurityPolicyFromPermissions:
    def test_empty_permissions(self) -> None:
        p = PluginSecurityPolicy.from_permissions()
        assert isinstance(p, PluginSecurityPolicy)

    def test_allowed_paths_normalized(self, tmp_path: Path) -> None:
        p = PluginSecurityPolicy.from_permissions(allowed_paths=[tmp_path])
        assert len(p.allowed_paths) == 1

    def test_allowed_operations_lowercased(self) -> None:
        p = PluginSecurityPolicy.from_permissions(allowed_operations=["READ", "Write"])
        assert "read" in p.allowed_operations
        assert "write" in p.allowed_operations

    def test_allow_all_paths_flag(self) -> None:
        p = PluginSecurityPolicy.from_permissions(allow_all_paths=True)
        assert p.allow_all_paths is True

    def test_allow_all_operations_flag(self) -> None:
        p = PluginSecurityPolicy.from_permissions(allow_all_operations=True)
        assert p.allow_all_operations is True

    def test_path_string_input(self, tmp_path: Path) -> None:
        p = PluginSecurityPolicy.from_permissions(allowed_paths=[str(tmp_path)])
        assert len(p.allowed_paths) == 1


class TestPluginSecurityPolicyDefault:
    def test_default_frozen(self) -> None:
        p = PluginSecurityPolicy()
        assert isinstance(p, PluginSecurityPolicy)
        assert p.allow_all_paths is False
        assert p.allow_all_operations is False

    def test_empty_frozensets(self) -> None:
        p = PluginSecurityPolicy()
        assert len(p.allowed_paths) == 0
        assert len(p.allowed_operations) == 0


# ---------------------------------------------------------------------------
# PluginSandbox
# ---------------------------------------------------------------------------


class TestPluginSandboxInit:
    def test_created(self) -> None:
        sb = PluginSandbox("my_plugin")
        assert sb is not None

    def test_default_policy_unrestricted(self) -> None:
        sb = PluginSandbox("my_plugin")
        assert sb.policy.allow_all_paths is True

    def test_custom_policy_stored(self) -> None:
        p = PluginSecurityPolicy()
        sb = PluginSandbox("my_plugin", policy=p)
        assert sb.policy is p

    def test_plugin_name_stored(self) -> None:
        sb = PluginSandbox("test_plugin")
        assert sb.plugin_name == "test_plugin"


class TestPluginSandboxValidateFileAccess:
    def test_allow_all_paths_permits_any(self, tmp_path: Path) -> None:
        sb = PluginSandbox("plug", policy=PluginSecurityPolicy.unrestricted())
        assert sb.validate_file_access(tmp_path / "anything.txt") is True

    def test_no_allowed_paths_denies_all(self, tmp_path: Path) -> None:
        p = PluginSecurityPolicy.from_permissions()
        sb = PluginSandbox("plug", policy=p)
        assert sb.validate_file_access(tmp_path / "file.txt") is False

    def test_exact_path_allowed(self, tmp_path: Path) -> None:
        target = tmp_path / "safe.txt"
        p = PluginSecurityPolicy.from_permissions(allowed_paths=[target])
        sb = PluginSandbox("plug", policy=p)
        assert sb.validate_file_access(target) is True

    def test_child_path_allowed(self, tmp_path: Path) -> None:
        p = PluginSecurityPolicy.from_permissions(allowed_paths=[tmp_path])
        sb = PluginSandbox("plug", policy=p)
        assert sb.validate_file_access(tmp_path / "sub" / "file.txt") is True

    def test_outside_path_denied(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        p = PluginSecurityPolicy.from_permissions(allowed_paths=[allowed])
        sb = PluginSandbox("plug", policy=p)
        assert sb.validate_file_access(outside / "file.txt") is False


class TestPluginSandboxValidateOperation:
    def test_allow_all_operations_permits_any(self) -> None:
        sb = PluginSandbox("plug", policy=PluginSecurityPolicy.unrestricted())
        assert sb.validate_operation("delete") is True

    def test_permitted_operation(self) -> None:
        p = PluginSecurityPolicy.from_permissions(allowed_operations=["read"])
        sb = PluginSandbox("plug", policy=p)
        assert sb.validate_operation("read") is True

    def test_forbidden_operation(self) -> None:
        p = PluginSecurityPolicy.from_permissions(allowed_operations=["read"])
        sb = PluginSandbox("plug", policy=p)
        assert sb.validate_operation("delete") is False

    def test_operation_case_insensitive(self) -> None:
        p = PluginSecurityPolicy.from_permissions(allowed_operations=["READ"])
        sb = PluginSandbox("plug", policy=p)
        assert sb.validate_operation("read") is True


class TestPluginSandboxRequireMethods:
    def test_require_file_access_raises_on_denied(self, tmp_path: Path) -> None:
        p = PluginSecurityPolicy.from_permissions()
        sb = PluginSandbox("plug", policy=p)
        with pytest.raises(PluginPermissionError):
            sb.require_file_access(tmp_path / "file.txt")

    def test_require_file_access_passes_on_allowed(self, tmp_path: Path) -> None:
        p = PluginSecurityPolicy.from_permissions(allowed_paths=[tmp_path])
        sb = PluginSandbox("plug", policy=p)
        sb.require_file_access(tmp_path / "file.txt")

    def test_require_operation_raises_on_denied(self) -> None:
        p = PluginSecurityPolicy.from_permissions(allowed_operations=["read"])
        sb = PluginSandbox("plug", policy=p)
        with pytest.raises(PluginPermissionError):
            sb.require_operation("write")

    def test_require_operation_passes_on_allowed(self) -> None:
        p = PluginSecurityPolicy.from_permissions(allowed_operations=["write"])
        sb = PluginSandbox("plug", policy=p)
        sb.require_operation("write")


# ---------------------------------------------------------------------------
# _tokenise
# ---------------------------------------------------------------------------


class TestTokenise:
    @pytest.fixture(autouse=True)
    def _require_rank_bm25(self) -> None:
        pytest.importorskip("rank_bm25")

    def test_basic_split(self) -> None:
        assert _tokenise("hello world") == ["hello", "world"]

    def test_lowercase(self) -> None:
        assert _tokenise("HELLO WORLD") == ["hello", "world"]

    def test_non_alphanumeric_stripped(self) -> None:
        result = _tokenise("file-name.txt")
        assert "file" in result
        assert "name" in result
        assert "txt" in result

    def test_empty_string(self) -> None:
        assert _tokenise("") == []

    def test_digits_preserved(self) -> None:
        result = _tokenise("report2024")
        assert "report2024" in result

    def test_multiple_separators(self) -> None:
        result = _tokenise("  hello   world  ")
        assert result == ["hello", "world"]


# ---------------------------------------------------------------------------
# BM25Index
# ---------------------------------------------------------------------------


class TestBM25IndexInit:
    @pytest.fixture(autouse=True)
    def _require_rank_bm25(self) -> None:
        pytest.importorskip("rank_bm25")

    def test_created(self) -> None:
        idx = BM25Index()
        assert idx is not None

    def test_initially_empty(self) -> None:
        idx = BM25Index()
        assert idx.size == 0

    def test_search_before_index_returns_empty(self) -> None:
        idx = BM25Index()
        assert idx.search("anything") == []


class TestBM25IndexIndex:
    @pytest.fixture(autouse=True)
    def _require_rank_bm25(self) -> None:
        pytest.importorskip("rank_bm25")

    def test_index_sets_size(self, tmp_path: Path) -> None:
        idx = BM25Index()
        paths = [tmp_path / f"f{i}.txt" for i in range(3)]
        idx.index(["doc one", "doc two", "doc three"], paths)
        assert idx.size == 3

    def test_mismatched_lengths_raises(self, tmp_path: Path) -> None:
        idx = BM25Index()
        with pytest.raises(ValueError, match="equal length"):
            idx.index(["a", "b"], [tmp_path / "only_one.txt"])

    def test_single_document(self, tmp_path: Path) -> None:
        idx = BM25Index()
        idx.index(["only one doc"], [tmp_path / "one.txt"])
        assert idx.size == 1

    def test_reindex_replaces_old(self, tmp_path: Path) -> None:
        idx = BM25Index()
        idx.index(["old doc"], [tmp_path / "old.txt"])
        idx.index(["new doc one", "new doc two"], [tmp_path / "a.txt", tmp_path / "b.txt"])
        assert idx.size == 2


class TestBM25IndexSearch:
    @pytest.fixture(autouse=True)
    def _require_rank_bm25(self) -> None:
        pytest.importorskip("rank_bm25")

    def test_returns_list(self, tmp_path: Path) -> None:
        idx = BM25Index()
        idx.index(["finance quarterly report"], [tmp_path / "report.txt"])
        result = idx.search("finance")
        # 1 indexed doc matching the query → 1 result tuple
        assert len(result) == 1
        path, score = result[0]
        assert path == tmp_path / "report.txt"

    def test_relevant_doc_returned(self, tmp_path: Path) -> None:
        paths = [tmp_path / f"d{i}.txt" for i in range(6)]
        docs = [
            "quarterly finance invoice payment",
            "cooking pasta dinner recipes",
            "project management planning",
            "music concerts events",
            "sports news results",
            "travel destinations tourism",
        ]
        idx = BM25Index()
        idx.index(docs, paths)
        results = idx.search("finance")
        assert len(results) >= 1
        result_paths = [p for p, _ in results]
        assert paths[0] in result_paths

    def test_top_k_limit(self, tmp_path: Path) -> None:
        paths = [tmp_path / f"doc{i}.txt" for i in range(10)]
        docs = [f"finance report document {i}" for i in range(10)]
        idx = BM25Index()
        idx.index(docs, paths)
        results = idx.search("finance", top_k=3)
        assert len(results) == 3

    def test_scores_are_floats(self, tmp_path: Path) -> None:
        idx = BM25Index()
        idx.index(["finance report"], [tmp_path / "f.txt"])
        results = idx.search("finance")
        assert len(results) >= 1
        for _, score in results:
            assert isinstance(score, float)

    def test_empty_query_returns_empty(self, tmp_path: Path) -> None:
        idx = BM25Index()
        idx.index(["finance report"], [tmp_path / "f.txt"])
        assert idx.search("") == []

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        idx = BM25Index()
        idx.index(["finance report"], [tmp_path / "f.txt"])
        result = idx.search("xyzzy")
        assert result == []

    def test_results_sorted_descending(self, tmp_path: Path) -> None:
        paths = [tmp_path / f"d{i}.txt" for i in range(5)]
        docs = [
            "finance finance finance report",
            "finance invoice",
            "meeting notes project",
            "finance",
            "cooking recipe",
        ]
        idx = BM25Index()
        idx.index(docs, paths)
        results = idx.search("finance", top_k=5)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Plugin SDK decorators — hook
# ---------------------------------------------------------------------------


class TestHookDecorator:
    def test_marks_function(self) -> None:
        @hook("file.created")
        def my_handler() -> None:
            pass

        assert get_hook_metadata(my_handler) is not None

    def test_event_stored(self) -> None:
        @hook("file.created")
        def my_handler() -> None:
            pass

        event, _ = get_hook_metadata(my_handler)  # type: ignore[misc]
        assert event == "file.created"

    def test_default_priority(self) -> None:
        @hook("file.created")
        def my_handler() -> None:
            pass

        _, priority = get_hook_metadata(my_handler)  # type: ignore[misc]
        assert priority == 10

    def test_custom_priority(self) -> None:
        @hook("file.created", priority=5)
        def my_handler() -> None:
            pass

        _, priority = get_hook_metadata(my_handler)  # type: ignore[misc]
        assert priority == 5

    def test_negative_priority_raises(self) -> None:
        with pytest.raises(ValueError, match="priority"):

            @hook("file.created", priority=-1)
            def my_handler() -> None:
                pass

    def test_empty_event_raises(self) -> None:
        with pytest.raises(ValueError, match="event"):

            @hook("")
            def my_handler() -> None:
                pass

    def test_returns_function_unchanged(self) -> None:
        def my_handler() -> str:
            return "hello"

        decorated = hook("event")(my_handler)
        assert decorated() == "hello"


# ---------------------------------------------------------------------------
# Plugin SDK decorators — command
# ---------------------------------------------------------------------------


class TestCommandDecorator:
    def test_marks_function(self) -> None:
        @command("organize")
        def do_organize() -> None:
            pass

        assert get_command_metadata(do_organize) is not None

    def test_name_stored(self) -> None:
        @command("organize")
        def do_organize() -> None:
            pass

        name, _ = get_command_metadata(do_organize)  # type: ignore[misc]
        assert name == "organize"

    def test_description_stored(self) -> None:
        @command("organize", description="Organize files")
        def do_organize() -> None:
            pass

        _, desc = get_command_metadata(do_organize)  # type: ignore[misc]
        assert desc == "Organize files"

    def test_empty_description_default(self) -> None:
        @command("organize")
        def do_organize() -> None:
            pass

        _, desc = get_command_metadata(do_organize)  # type: ignore[misc]
        assert desc == ""

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="name"):

            @command("")
            def do_something() -> None:
                pass

    def test_whitespace_name_raises(self) -> None:
        with pytest.raises(ValueError, match="name"):

            @command("   ")
            def do_something() -> None:
                pass

    def test_returns_function_unchanged(self) -> None:
        def do_something() -> int:
            return 42

        decorated = command("do")(do_something)
        assert decorated() == 42


# ---------------------------------------------------------------------------
# get_hook_metadata / get_command_metadata — unmarked functions
# ---------------------------------------------------------------------------


class TestGetMetadataUnmarked:
    def test_hook_metadata_none_for_plain_function(self) -> None:
        def plain() -> None:
            pass

        assert get_hook_metadata(plain) is None

    def test_command_metadata_none_for_plain_function(self) -> None:
        def plain() -> None:
            pass

        assert get_command_metadata(plain) is None

    def test_hook_metadata_none_for_command_decorated(self) -> None:
        @command("do_it")
        def do_it() -> None:
            pass

        assert get_hook_metadata(do_it) is None

    def test_command_metadata_none_for_hook_decorated(self) -> None:
        @hook("event.fired")
        def on_event() -> None:
            pass

        assert get_command_metadata(on_event) is None
