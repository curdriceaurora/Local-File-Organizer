"""Unit/behavioral tests for scripts/dev/run_diff_cover.py (issue #1767 PR review).

Covers the file-mapping logic directly (no git needed) and the git-facing
pieces (merge-base resolution, changed-file listing, and the full skip/scope
decisions in main()) against small real git repos built in tmp_path.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev" / "run_diff_cover.py"

_spec = importlib.util.spec_from_file_location("run_diff_cover", SCRIPT)
assert _spec is not None and _spec.loader is not None
run_diff_cover = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_diff_cover)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# placeholder\n")


@pytest.mark.unit
class TestMapToTests:
    def test_maps_src_file_to_directory_scoped_test_match(self, tmp_path: Path) -> None:
        _touch(tmp_path / "tests" / "services" / "deduplication" / "test_dedup_extractor.py")
        _touch(tmp_path / "tests" / "services" / "deduplication" / "test_dedup_extractor_xxe.py")
        # A same-named test file elsewhere in the tree must NOT match --
        # directory scoping matters, not a whole-tree substring search.
        _touch(tmp_path / "tests" / "services" / "video" / "test_metadata_extractor.py")

        test_paths, unmapped = run_diff_cover.map_to_tests(
            ["src/file_organizer/services/deduplication/extractor.py"], repo_root=tmp_path
        )

        assert test_paths == {
            "tests/services/deduplication/test_dedup_extractor.py",
            "tests/services/deduplication/test_dedup_extractor_xxe.py",
        }
        assert unmapped == []

    def test_changed_test_file_is_directly_in_scope(self, tmp_path: Path) -> None:
        test_paths, unmapped = run_diff_cover.map_to_tests(
            ["tests/api/test_auth.py"], repo_root=tmp_path
        )
        assert test_paths == {"tests/api/test_auth.py"}
        assert unmapped == []

    def test_unmapped_when_no_directory_or_stem_match(self, tmp_path: Path) -> None:
        _touch(tmp_path / "tests" / "services" / "deduplication" / "test_dedup_extractor.py")

        test_paths, unmapped = run_diff_cover.map_to_tests(
            ["src/file_organizer/_compat.py"], repo_root=tmp_path
        )
        assert test_paths == set()
        assert unmapped == ["src/file_organizer/_compat.py"]

    def test_skips_dunder_init(self, tmp_path: Path) -> None:
        test_paths, unmapped = run_diff_cover.map_to_tests(
            ["src/file_organizer/services/__init__.py"], repo_root=tmp_path
        )
        assert test_paths == set()
        assert unmapped == []

    def test_partial_mapping_across_multiple_files(self, tmp_path: Path) -> None:
        _touch(tmp_path / "tests" / "api" / "test_auth.py")

        test_paths, unmapped = run_diff_cover.map_to_tests(
            ["src/file_organizer/api/auth.py", "src/file_organizer/_compat.py"],
            repo_root=tmp_path,
        )
        assert test_paths == {"tests/api/test_auth.py"}
        assert unmapped == ["src/file_organizer/_compat.py"]


@pytest.mark.unit
class TestMappedSrcFiles:
    def test_excludes_unmapped_and_non_src_files(self) -> None:
        changed = [
            "src/file_organizer/api/auth.py",
            "src/file_organizer/_compat.py",
            "tests/api/test_auth.py",
        ]
        result = run_diff_cover.mapped_src_files(
            changed, unmapped=["src/file_organizer/_compat.py"]
        )
        assert result == ["src/file_organizer/api/auth.py"]


def _init_repo_with_origin_main(tmp_path: Path) -> Path:
    """A repo with one commit, and refs/remotes/origin/main pointing at it --
    enough for `git merge-base HEAD origin/main` to resolve without a real
    remote."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    _touch(repo / "src" / "file_organizer" / "existing.py")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", base_sha], cwd=repo, check=True
    )
    return repo


@pytest.mark.unit
class TestGitFacingHelpers:
    def test_merge_base_resolves_against_crafted_origin_main(self, tmp_path: Path) -> None:
        repo = _init_repo_with_origin_main(tmp_path)
        assert run_diff_cover.merge_base(repo_root=repo) is not None

    def test_merge_base_none_without_origin(self, tmp_path: Path) -> None:
        repo = tmp_path / "norepo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        assert run_diff_cover.merge_base(repo_root=repo) is None

    def test_changed_python_files_excludes_deletions(self, tmp_path: Path) -> None:
        repo = _init_repo_with_origin_main(tmp_path)
        (repo / "src" / "file_organizer" / "existing.py").unlink()
        _touch(repo / "src" / "file_organizer" / "added.py")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "delete + add"], cwd=repo, check=True)

        base = run_diff_cover.merge_base(repo_root=repo)
        assert base is not None
        changed = run_diff_cover.changed_python_files(base, repo_root=repo)

        assert "src/file_organizer/added.py" in changed
        assert "src/file_organizer/existing.py" not in changed


@pytest.mark.unit
class TestMainEndToEnd:
    def test_noop_when_nothing_changed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo_with_origin_main(tmp_path)
        monkeypatch.setattr(run_diff_cover, "REPO_ROOT", repo)
        monkeypatch.chdir(repo)
        assert run_diff_cover.main() == 0

    def test_skips_when_no_test_matches_any_changed_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo_with_origin_main(tmp_path)
        _touch(repo / "src" / "file_organizer" / "orphan.py")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "orphan"], cwd=repo, check=True)

        monkeypatch.setattr(run_diff_cover, "REPO_ROOT", repo)
        monkeypatch.chdir(repo)
        result = run_diff_cover.main()
        assert result == 0

    def test_diff_cover_include_scopes_out_unmapped_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The core P2 fix: with one mapped and one unmapped changed src file,
        diff-cover must only be asked to judge the mapped one -- not fail the
        push over a file it never had local test evidence for."""
        repo = _init_repo_with_origin_main(tmp_path)
        _touch(repo / "tests" / "api" / "test_auth.py")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "add test dir"], cwd=repo, check=True)

        changed = ["src/file_organizer/api/auth.py", "src/file_organizer/_compat.py"]
        test_paths, unmapped = run_diff_cover.map_to_tests(changed, repo_root=repo)
        include = run_diff_cover.mapped_src_files(changed, unmapped)

        assert test_paths == {"tests/api/test_auth.py"}
        assert unmapped == ["src/file_organizer/_compat.py"]
        assert include == ["src/file_organizer/api/auth.py"]
        assert "src/file_organizer/_compat.py" not in include
