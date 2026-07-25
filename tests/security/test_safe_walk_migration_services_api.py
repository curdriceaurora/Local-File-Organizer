"""Traversal-safety tests for the services/, api/ and plugins/ ``safe_walk`` migration (#1671).

Each migrated call site is asserted on two axes: a symlink whose target lives
outside the walked root is never reached, and dot-prefixed entries appear only
where that site deliberately wants them.

Sites deliberately *not* covered here, and why:

- ``services/copilot/rules/preview.py`` — blocked on #1674. Its ``PreviewResult.errors``
  reports "Permission denied" to the user, and ``safe_walk`` cannot surface OSError.
- ``api/routers/search.py`` — both walks meter a ``max_files`` traversal budget on
  *raw* entries. ``safe_walk`` pre-filters, so the same number would bound a larger
  walk, loosening a DoS guard on a remote-reachable endpoint.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from file_organizer.api.routers.files import _collect_files as api_collect_files
from file_organizer.plugins.api.endpoints import _collect_files as plugin_collect_files
from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer
from file_organizer.services.copilot.executor import CommandExecutor
from file_organizer.services.copilot.intent_parser import Intent, IntentType
from file_organizer.services.misplacement_detector import MisplacementDetector
from file_organizer.services.pattern_analyzer import PatternAnalyzer

pytestmark = [pytest.mark.security, pytest.mark.unit, pytest.mark.ci]

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink hardening is POSIX-focused"
)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A scan root holding a real file, a dotfile, and a symlink escaping the root."""
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("sensitive data outside the scan root")

    root = tmp_path / "root"
    root.mkdir()
    (root / "report.txt").write_text("real content")
    (root / ".hidden.txt").write_text("dotfile content")
    (root / "escape.txt").symlink_to(outside)
    return root


class TestApiCollectFiles:
    """api/routers/files.py::_collect_files — hidden threading must survive."""

    @posix_only
    def test_symlink_is_not_collected(self, tree: Path) -> None:
        names = {p.name for p in api_collect_files(tree, recursive=True, include_hidden=True)}
        assert "report.txt" in names
        assert "escape.txt" not in names

    def test_include_hidden_false_excludes_dotfiles(self, tree: Path) -> None:
        names = {p.name for p in api_collect_files(tree, recursive=True, include_hidden=False)}
        assert names == {"report.txt"}

    def test_include_hidden_true_includes_dotfiles(self, tree: Path) -> None:
        names = {p.name for p in api_collect_files(tree, recursive=True, include_hidden=True)}
        assert ".hidden.txt" in names

    def test_non_recursive_stays_top_level(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        (root / "nested").mkdir(parents=True)
        (root / "top.txt").write_text("t")
        (root / "nested" / "deep.txt").write_text("d")

        names = {p.name for p in api_collect_files(root, recursive=False, include_hidden=False)}
        assert names == {"top.txt"}


class TestPluginCollectFiles:
    """plugins/api/endpoints.py::_collect_files — same contract, plus sorting."""

    @posix_only
    def test_symlink_is_not_collected(self, tree: Path) -> None:
        names = {p.name for p in plugin_collect_files(tree, recursive=True, include_hidden=True)}
        assert "report.txt" in names
        assert "escape.txt" not in names

    def test_include_hidden_is_threaded(self, tree: Path) -> None:
        without = {p.name for p in plugin_collect_files(tree, recursive=True, include_hidden=False)}
        with_hidden = {
            p.name for p in plugin_collect_files(tree, recursive=True, include_hidden=True)
        }
        assert ".hidden.txt" not in without
        assert ".hidden.txt" in with_hidden

    def test_results_remain_sorted_by_name(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        for name in ("zulu.txt", "alpha.txt", "mike.txt"):
            (root / name).write_text("x")

        collected = plugin_collect_files(root, recursive=True, include_hidden=False)
        assert [p.name for p in collected] == ["alpha.txt", "mike.txt", "zulu.txt"]


class TestStorageAnalyzerTraversal:
    """Analytics must not count symlinks, but must still count dotfiles."""

    @posix_only
    def test_size_distribution_excludes_symlinks(self, tree: Path) -> None:
        distribution = StorageAnalyzer().calculate_size_distribution(tree)
        # report.txt + .hidden.txt, but not the escaping symlink
        assert distribution.total_files == 2

    def test_size_distribution_counts_hidden_files(self, tmp_path: Path) -> None:
        """include_hidden=True here: disk usage that omits dotfiles is simply wrong."""
        root = tmp_path / "root"
        root.mkdir()
        (root / "visible.txt").write_text("x")
        (root / ".hidden.txt").write_text("y")

        distribution = StorageAnalyzer().calculate_size_distribution(root)
        assert distribution.total_files == 2

    @posix_only
    def test_identify_large_files_excludes_symlinks(self, tmp_path: Path) -> None:
        big_outside = tmp_path / "big_outside.bin"
        big_outside.write_bytes(b"x" * 5000)

        root = tmp_path / "root"
        root.mkdir()
        (root / "big_inside.bin").write_bytes(b"y" * 5000)
        (root / "link.bin").symlink_to(big_outside)

        large = StorageAnalyzer().identify_large_files(root, threshold=1000)
        assert [f.path.name for f in large] == ["big_inside.bin"]


class TestPatternAnalyzerTraversal:
    """get_location_patterns walks directories — not through links."""

    @posix_only
    def test_symlinked_directory_is_not_analyzed(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.pdf").write_text("x")

        root = tmp_path / "root"
        real = root / "real"
        real.mkdir(parents=True)
        (real / "doc.pdf").write_text("x")
        (root / "linked").symlink_to(outside, target_is_directory=True)

        patterns = PatternAnalyzer().get_location_patterns(root)
        analyzed = {p.directory.name for p in patterns}
        assert "real" in analyzed
        assert "linked" not in analyzed

    def test_hidden_directory_is_not_analyzed(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        (root / "real").mkdir(parents=True)
        (root / "real" / "doc.pdf").write_text("x")
        (root / ".hidden").mkdir()
        (root / ".hidden" / "doc.pdf").write_text("x")

        patterns = PatternAnalyzer().get_location_patterns(root)
        analyzed = {p.directory.name for p in patterns}
        assert "real" in analyzed
        assert ".hidden" not in analyzed

    def test_directory_nested_under_hidden_parent_is_not_analyzed(self, tmp_path: Path) -> None:
        """safe_walk excludes any path with a dot component relative to the root.

        Stricter than the previous leaf-only ``name.startswith(".")`` check: a
        visible directory inside ``.cache/`` was analysed before and is not now.
        """
        root = tmp_path / "root"
        buried = root / ".cache" / "visible"
        buried.mkdir(parents=True)
        (buried / "doc.pdf").write_text("x")

        patterns = PatternAnalyzer().get_location_patterns(root)
        assert [p.directory.name for p in patterns] == []


class TestCopilotFindTraversal:
    """_handle_find's filename scan must not surface links or dotfiles."""

    @posix_only
    def test_find_does_not_match_symlinks(self, tree: Path) -> None:
        intent = Intent(
            intent_type=IntentType.FIND,
            confidence=0.9,
            parameters={"query": "escape", "paths": [str(tree)]},
        )
        result = CommandExecutor().execute(intent)
        assert all("escape.txt" not in f for f in result.affected_files)

    def test_find_does_not_match_hidden_files(self, tree: Path) -> None:
        intent = Intent(
            intent_type=IntentType.FIND,
            confidence=0.9,
            parameters={"query": "hidden", "paths": [str(tree)]},
        )
        result = CommandExecutor().execute(intent)
        assert all(".hidden.txt" not in f for f in result.affected_files)

    def test_find_still_matches_ordinary_files(self, tree: Path) -> None:
        """Characterization guard: the migration must not break finding real files."""
        intent = Intent(
            intent_type=IntentType.FIND,
            confidence=0.9,
            parameters={"query": "report", "paths": [str(tree)]},
        )
        result = CommandExecutor().execute(intent)
        assert any("report.txt" in f for f in result.affected_files)


class TestMisplacementDetectorTraversal:
    """detect_misplaced walks a user-supplied root — unblocked once #1673 merged."""

    @posix_only
    def test_symlinked_file_is_not_analyzed(self, tmp_path: Path) -> None:
        """A symlink pointing outside the scanned tree is never a misplacement candidate."""
        outside = tmp_path / "outside.jpg"
        outside.write_bytes(b"\xff\xd8\xff")

        root = tmp_path / "root"
        root.mkdir()
        for i in range(5):
            (root / f"report_{i}.txt").write_text("content")
        (root / "linked.jpg").symlink_to(outside)

        detector = MisplacementDetector(min_mismatch_score=50.0)
        misplaced = detector.detect_misplaced(root)

        assert all(m.file_path.name != "linked.jpg" for m in misplaced)

    def test_file_under_hidden_directory_is_not_analyzed(self, tmp_path: Path) -> None:
        """safe_walk excludes any dot component relative to the root.

        Stricter than the previous leaf-only ``name.startswith(".")`` filter: a
        visible file inside ``.cache/`` was analysed before and is not now.
        """
        root = tmp_path / "root"
        buried = root / ".cache"
        buried.mkdir(parents=True)
        for i in range(5):
            (buried / f"report_{i}.txt").write_text("content")
        (buried / "photo.jpg").write_bytes(b"\xff\xd8\xff")

        detector = MisplacementDetector(min_mismatch_score=50.0)
        misplaced = detector.detect_misplaced(root)

        assert misplaced == []

    def test_ordinary_outlier_is_still_detected(self, tmp_path: Path) -> None:
        """Characterization guard carried over from #1670."""
        root = tmp_path / "root"
        root.mkdir()
        for i in range(5):
            (root / f"report_{i}.txt").write_text("content")
        outlier = root / "photo.jpg"
        outlier.write_bytes(b"\xff\xd8\xff")

        detector = MisplacementDetector(min_mismatch_score=50.0)
        misplaced = detector.detect_misplaced(root)

        assert outlier in [m.file_path for m in misplaced]
