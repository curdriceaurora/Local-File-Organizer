"""Tests for build.yml CI/CD pipeline (pywebview desktop build pipeline)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "build.yml"

pytestmark = pytest.mark.ci


def _load_workflow() -> dict:
    """Load and parse build.yml as a YAML dict."""
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _build_step_names() -> list[str]:
    """Return the list of step names from the build job."""
    jobs = _load_workflow().get("jobs", {})
    return [s.get("name", "") for s in jobs.get("build", {}).get("steps", [])]


def _build_step_run_text() -> str:
    """Return all run-script text from build job steps concatenated."""
    jobs = _load_workflow().get("jobs", {})
    return " ".join(s.get("run", "") for s in jobs.get("build", {}).get("steps", []))


class TestWorkflowFile:
    def test_workflow_file_exists(self) -> None:
        """build.yml must exist."""
        assert WORKFLOW_PATH.exists()

    def test_workflow_is_valid_yaml(self) -> None:
        """build.yml must be valid YAML with a jobs key."""
        wf = _load_workflow()
        assert "jobs" in wf


class TestNoRustOrTauriSteps:
    def test_no_test_rust_job(self) -> None:
        """test-rust job must be absent — Rust/Tauri removed in #1114."""
        jobs = _load_workflow().get("jobs", {})
        assert "test-rust" not in jobs

    def test_no_rust_toolchain_step(self) -> None:
        """No step should reference a Rust toolchain action."""
        raw = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "dtolnay/rust-toolchain" not in raw
        assert "Swatinem/rust-cache" not in raw

    def test_no_cargo_commands(self) -> None:
        """No run: block should invoke cargo or rustc."""
        raw = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "cargo " not in raw
        assert "rustc " not in raw

    def test_no_tauri_steps(self) -> None:
        """No step should reference Tauri build or src-tauri paths."""
        raw_lower = WORKFLOW_PATH.read_text(encoding="utf-8").lower()
        assert ("tauri" not in raw_lower) and ("src-tauri" not in raw_lower)

    def test_no_tauri_signing_secrets(self) -> None:
        """TAURI_SIGNING_* env vars must not appear."""
        raw = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "TAURI_SIGNING" not in raw

    def test_no_combined_artifacts(self) -> None:
        """combined-artifacts directory must not be referenced."""
        raw = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "combined-artifacts" not in raw


class TestDesktopBuildStep:
    def test_desktop_build_step_present(self) -> None:
        """A step building the pywebview desktop executable must exist."""
        names = _build_step_names()
        assert any("Desktop" in name or "desktop" in name for name in names), (
            f"No desktop build step found in: {names}"
        )

    def test_desktop_build_uses_desktop_flag(self) -> None:
        """The desktop build step must invoke build.py with --desktop."""
        run_text = _build_step_run_text()
        assert "--desktop" in run_text

    def test_cli_build_step_present(self) -> None:
        """A step building the CLI executable must also exist."""
        run_text = _build_step_run_text()
        assert "python scripts/build.py --clean" in run_text

    def test_build_test_command_targets_build_ci_suite(self) -> None:
        """Build workflow should run deterministic build-focused CI tests."""
        run_text = _build_step_run_text()
        assert "tests/ci/test_build_artifacts.py" in run_text
        assert "tests/ci/test_build_workflow.py" in run_text
        assert "tests/ci/test_build_workflows.py" in run_text


class TestPywebviewLinuxDeps:
    def test_pywebview_linux_deps_step(self) -> None:
        """A Linux-conditional step must install GTK/WebKit pywebview deps."""
        jobs = _load_workflow().get("jobs", {})
        steps = jobs.get("build", {}).get("steps", [])
        linux_dep_steps = [
            s
            for s in steps
            if "libgirepository" in s.get("run", "") or "gir1.2-webkit2" in s.get("run", "")
        ]
        assert linux_dep_steps, "No pywebview GTK/WebKit Linux dependency step found"

    def test_linux_deps_are_platform_conditional(self) -> None:
        """The GTK/WebKit dep step must be guarded by a linux platform condition."""
        jobs = _load_workflow().get("jobs", {})
        steps = jobs.get("build", {}).get("steps", [])
        found = False
        for step in steps:
            if "libgirepository" in step.get("run", "") or "gir1.2-webkit2" in step.get("run", ""):
                found = True
                cond = step.get("if", "")
                assert "linux" in cond, (
                    f"GTK/WebKit dep step must be linux-conditional, got if: {cond!r}"
                )
                break
        assert found, "GTK/WebKit dep step not found"


class TestArtifactUpload:
    def test_artifacts_from_dist(self) -> None:
        """Artifacts must be uploaded from dist/, not combined-artifacts/."""
        jobs = _load_workflow().get("jobs", {})
        steps = jobs.get("build", {}).get("steps", [])
        upload_steps = [s for s in steps if "upload-artifact" in s.get("uses", "")]
        assert upload_steps, "No upload-artifact step found"
        for step in upload_steps:
            path = step.get("with", {}).get("path", "")
            assert path.startswith("dist"), f"Upload path must start with 'dist', got: {path!r}"


class TestReleaseJob:
    def test_release_needs_build_only(self) -> None:
        """release job must depend only on 'build', not 'test-rust'."""
        jobs = _load_workflow().get("jobs", {})
        release = jobs.get("release", {})
        needs = release.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert needs == ["build"], f"release job must need only 'build', got: {needs}"

    def test_release_triggered_on_tags(self) -> None:
        """release job must support tag-triggered publishing."""
        jobs = _load_workflow().get("jobs", {})
        release = jobs.get("release", {})
        cond = release.get("if", "")
        assert "refs/tags/v" in cond, (
            f"release job must be guarded by tag condition, got if: {cond!r}"
        )

    def test_release_can_publish_from_manual_version_dispatch(self) -> None:
        """Manual dispatch with a version should be able to publish release assets."""
        jobs = _load_workflow().get("jobs", {})
        release = jobs.get("release", {})
        cond = str(release.get("if", ""))
        assert "workflow_dispatch" in cond
        assert "inputs.version" in cond

        release_step = next(
            (
                step
                for step in release.get("steps", [])
                if isinstance(step, dict) and step.get("name") == "Create GitHub Release"
            ),
            {},
        )
        run_script = str(release_step.get("run", ""))
        assert "release create" in run_script
        assert "RELEASE_TAG" in run_script, "release step must publish against resolved release tag"

    def test_release_prerelease_detection_handles_pep440_tags(self) -> None:
        """release asset publication should treat hyphen and PEP 440 tags as prereleases."""
        jobs = _load_workflow().get("jobs", {})
        steps = jobs.get("release", {}).get("steps", [])
        release_step = next(
            (
                step
                for step in steps
                if isinstance(step, dict) and step.get("name") == "Create GitHub Release"
            ),
            {},
        )
        run_script = str(release_step.get("run", ""))
        assert "--prerelease" in run_script, "build.yml release step must set prerelease"
        assert "--draft" in run_script, "build.yml release step must set draft for stable releases"
        assert '"${RELEASE_TAG}" != *-*' in run_script
        assert '"${RELEASE_TAG}" != *a*' in run_script
        assert '"${RELEASE_TAG}" != *b*' in run_script
        assert '"${RELEASE_TAG}" != *rc*' in run_script

    def test_release_job_signs_manifest(self) -> None:
        """release job must install pycryptodomex and execute sign_release.py with RELEASE_SIGNING_KEY."""
        jobs = _load_workflow().get("jobs", {})
        steps = jobs.get("release", {}).get("steps", [])

        # Check the signing script's runtime dependencies are installed
        build_step = next(s for s in steps if s.get("name") == "Build sdist and wheel")
        assert "pycryptodomex" in build_step.get("run", "")
        assert "loguru" in build_step.get("run", ""), (
            "sign_release.py imports file_organizer.updater.trust which requires loguru"
        )

        # Check sign step exists and has correct environment
        sign_step = next(s for s in steps if s.get("name") == "Generate and sign release manifest")
        assert "sign_release.py" in sign_step.get("run", "")
        env = sign_step.get("env", {})
        assert env.get("RELEASE_SIGNING_KEY") == "${{ secrets.RELEASE_SIGNING_KEY }}"

    def test_release_job_downloads_artifacts_flat(self) -> None:
        """download-artifact must merge artifacts into a flat directory.

        Without merge-multiple, each artifact lands in its own subdirectory and
        sign_release.py records prefixed paths that never match the flat asset
        names attached to the GitHub release.
        """
        jobs = _load_workflow().get("jobs", {})
        steps = jobs.get("release", {}).get("steps", [])
        download_step = next(s for s in steps if s.get("name") == "Download build artifacts")
        with_block = download_step.get("with", {})
        assert with_block.get("path") == "artifacts"
        assert with_block.get("merge-multiple") is True, (
            "build.yml release job must set merge-multiple: true so manifest "
            "asset names match release asset names"
        )
