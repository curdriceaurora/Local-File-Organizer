"""Tests for build.yml CI/CD pipeline."""

import unittest
from pathlib import Path

import yaml


class TestBuildWorkflow(unittest.TestCase):
    def setUp(self):
        self.workflow_path = Path(".github/workflows/build.yml")
        content = self.workflow_path.read_text()
        self.workflow = yaml.safe_load(content)
        self.jobs = self.workflow.get("jobs", {})

    def test_workflow_file_exists(self):
        self.assertTrue(self.workflow_path.exists())

    def test_test_rust_job_exists(self):
        self.assertIn("test-rust", self.jobs)

    def test_build_job_has_rust_toolchain(self):
        build_steps = self.jobs["build"]["steps"]
        step_names = [s.get("name", "") for s in build_steps]
        self.assertTrue(
            any("Rust" in name for name in step_names),
            f"No Rust step found in: {step_names}",
        )

    def test_tauri_build_step_present(self):
        build_steps = self.jobs["build"]["steps"]
        step_names = [s.get("name", "") for s in build_steps]
        self.assertTrue(
            any("Tauri" in name for name in step_names),
            f"No Tauri step found in: {step_names}",
        )

    def test_sidecar_rename_step_present(self):
        build_steps = self.jobs["build"]["steps"]
        step_names = [s.get("name", "") for s in build_steps]
        self.assertTrue(
            any("sidecar" in name for name in step_names),
            f"No sidecar step found in: {step_names}",
        )

    def test_release_needs_test_rust(self):
        release_job = self.jobs.get("release", {})
        needs = release_job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        self.assertIn(
            "test-rust",
            needs,
            f"release job should need test-rust, got: {needs}",
        )

    def test_cargo_test_command(self):
        test_rust_steps = self.jobs["test-rust"]["steps"]
        all_run = " ".join(s.get("run", "") for s in test_rust_steps)
        self.assertIn("cargo test", all_run)

    def test_combined_artifacts_collected(self):
        build_steps = self.jobs["build"]["steps"]
        all_run = " ".join(s.get("run", "") for s in build_steps)
        self.assertIn("combined-artifacts", all_run)


if __name__ == "__main__":
    unittest.main()
