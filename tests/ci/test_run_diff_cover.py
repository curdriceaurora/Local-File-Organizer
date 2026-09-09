"""Unit/behavioral tests for scripts/dev/run_diff_cover.py (issue #1767 PR review).

Covers the file-mapping logic directly (no git needed) and the git-facing
pieces (merge-base resolution, changed-file listing, and the full skip/scope
decisions in main()) against small real git repos built in tmp_path.
"""

from __future__ import annotations

import importlib.util
import os
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


def _clean_git_env() -> dict[str, str]:
    """Return os.environ without git hook variables that would poison nested repos.

    When git invokes hooks (e.g. pre-commit), it sets GIT_DIR, GIT_WORK_TREE,
    and GIT_INDEX_FILE pointing at the outer repo.  These leak into
    subprocess.run(["git", ...]) calls that create or operate on tmp_path repos,
    causing "fatal: this operation must be run in a work tree" failures.
    """
    env = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(key, None)
    return env


def _git_run(
    *args: str, cwd: Path, check: bool = True, capture_output: bool = False, text: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run a git command with a sanitized environment."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=capture_output,
        text=text,
        env=_clean_git_env(),
    )


def _init_repo_with_origin_main(tmp_path: Path) -> Path:
    """A repo with one commit, and refs/remotes/origin/main pointing at it --
    enough for `git merge-base HEAD origin/main` to resolve without a real
    remote."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_run("init", "-q", cwd=repo)
    _git_run("config", "user.email", "test@example.com", cwd=repo)
    _git_run("config", "user.name", "Test", cwd=repo)
    _touch(repo / "src" / "file_organizer" / "existing.py")
    _git_run("add", "-A", cwd=repo)
    _git_run("commit", "-q", "-m", "initial", cwd=repo)
    base_sha = _git_run(
        "rev-parse",
        "HEAD",
        cwd=repo,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git_run("update-ref", "refs/remotes/origin/main", base_sha, cwd=repo)
    return repo


@pytest.mark.unit
class TestGitFacingHelpers:
    @pytest.fixture(autouse=True)
    def _strip_git_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prevent GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE from leaking into
        the run_diff_cover module's own subprocess calls (e.g. inside pre-commit)."""
        for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            monkeypatch.delenv(var, raising=False)

    def test_merge_base_resolves_against_crafted_origin_main(self, tmp_path: Path) -> None:
        repo = _init_repo_with_origin_main(tmp_path)
        assert run_diff_cover.merge_base(repo_root=repo) is not None

    def test_merge_base_none_without_origin(self, tmp_path: Path) -> None:
        repo = tmp_path / "norepo"
        repo.mkdir()
        _git_run("init", "-q", cwd=repo)
        assert run_diff_cover.merge_base(repo_root=repo) is None

    def test_changed_python_files_excludes_deletions(self, tmp_path: Path) -> None:
        repo = _init_repo_with_origin_main(tmp_path)
        (repo / "src" / "file_organizer" / "existing.py").unlink()
        _touch(repo / "src" / "file_organizer" / "added.py")
        _git_run("add", "-A", cwd=repo)
        _git_run("commit", "-q", "-m", "delete + add", cwd=repo)

        base = run_diff_cover.merge_base(repo_root=repo)
        assert base is not None
        changed = run_diff_cover.changed_python_files(base, repo_root=repo)

        assert "src/file_organizer/added.py" in changed
        assert "src/file_organizer/existing.py" not in changed

    def test_uses_pre_commit_to_ref_for_a_non_head_push(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PR review (issue #1767): pre-commit's pre-push hook sets
        PRE_COMMIT_TO_REF to the revision actually being pushed, which isn't
        always HEAD (e.g. `git push origin HEAD~1:branch`). merge_base()/
        changed_python_files() must diff against that ref, not a hardcoded
        HEAD, or they'd report coverage for the wrong revision."""
        repo = _init_repo_with_origin_main(tmp_path)

        _touch(repo / "src" / "file_organizer" / "at_b.py")
        _git_run("add", "-A", cwd=repo)
        _git_run("commit", "-q", "-m", "commit B", cwd=repo)
        commit_b = _git_run(
            "rev-parse",
            "HEAD",
            cwd=repo,
            capture_output=True,
            text=True,
        ).stdout.strip()

        _touch(repo / "src" / "file_organizer" / "at_c.py")
        _git_run("add", "-A", cwd=repo)
        _git_run("commit", "-q", "-m", "commit C (HEAD)", cwd=repo)

        # Without PRE_COMMIT_TO_REF, HEAD (commit C) is used -- both files show up.
        monkeypatch.delenv("PRE_COMMIT_TO_REF", raising=False)
        base = run_diff_cover.merge_base(repo_root=repo)
        assert base is not None
        changed_at_head = run_diff_cover.changed_python_files(base, repo_root=repo)
        assert "src/file_organizer/at_b.py" in changed_at_head
        assert "src/file_organizer/at_c.py" in changed_at_head

        # Simulating `git push origin HEAD~1:branch`: pushing commit B, not C.
        monkeypatch.setenv("PRE_COMMIT_TO_REF", commit_b)
        base_for_push = run_diff_cover.merge_base(repo_root=repo)
        assert base_for_push is not None
        changed_for_push = run_diff_cover.changed_python_files(base_for_push, repo_root=repo)
        assert "src/file_organizer/at_b.py" in changed_for_push
        assert "src/file_organizer/at_c.py" not in changed_for_push


@pytest.mark.unit
class TestMainEndToEnd:
    @pytest.fixture(autouse=True)
    def _strip_git_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prevent GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE from leaking into
        the run_diff_cover module's own subprocess calls (e.g. inside pre-commit)."""
        for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            monkeypatch.delenv(var, raising=False)

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
        _git_run("add", "-A", cwd=repo)
        _git_run("commit", "-q", "-m", "orphan", cwd=repo)

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
        _git_run("add", "-A", cwd=repo)
        _git_run("commit", "-q", "-m", "add test dir", cwd=repo)

        changed = ["src/file_organizer/api/auth.py", "src/file_organizer/_compat.py"]
        test_paths, unmapped = run_diff_cover.map_to_tests(changed, repo_root=repo)
        include = run_diff_cover.mapped_src_files(changed, unmapped)

        assert test_paths == {"tests/api/test_auth.py"}
        assert unmapped == ["src/file_organizer/_compat.py"]
        assert include == ["src/file_organizer/api/auth.py"]
        assert "src/file_organizer/_compat.py" not in include
