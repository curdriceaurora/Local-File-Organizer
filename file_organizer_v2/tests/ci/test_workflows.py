"""Tests for GitHub Actions workflow files.

Validates YAML structure, required fields, and best practices for all workflow files.

Note: PyYAML parses the YAML key ``on`` as the Python boolean ``True``
because ``on`` is a boolean literal in YAML 1.1.  The helper
``get_triggers`` accounts for this.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

# Project root is two levels above file_organizer_v2/tests/ci/
PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS_DIR = PROJECT_ROOT / ".github" / "workflows"


def load_workflow(name: str) -> dict[str, Any]:
    """Load and parse a workflow YAML file."""
    path = WORKFLOWS_DIR / name
    assert path.exists(), f"Workflow file not found: {path}"
    content = path.read_text()
    data = yaml.safe_load(content)
    assert isinstance(data, dict), f"Workflow {name} did not parse as a dict"
    return data


def get_triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    """Extract the trigger configuration from a workflow.

    PyYAML parses the bare ``on`` key as the boolean ``True``, so we
    need to check for both ``"on"`` and ``True`` as dictionary keys.
    """
    triggers = workflow.get("on", workflow.get(True, {}))
    if not isinstance(triggers, dict):
        return {}
    return triggers


class TestWorkflowDirectory:
    """Tests for the workflows directory structure."""

    def test_workflows_directory_exists(self) -> None:
        """Verify .github/workflows directory exists."""
        assert WORKFLOWS_DIR.exists(), (
            ".github/workflows directory must exist"
        )

    def test_all_expected_workflows_exist(self) -> None:
        """Verify all expected workflow files are present."""
        expected_workflows = ["ci.yml", "release.yml", "docker.yml", "security.yml"]
        for workflow in expected_workflows:
            path = WORKFLOWS_DIR / workflow
            assert path.exists(), f"Expected workflow file not found: {workflow}"

    def test_all_workflow_files_are_valid_yaml(self) -> None:
        """Verify all workflow files in the directory are valid YAML."""
        for workflow_file in WORKFLOWS_DIR.glob("*.yml"):
            content = workflow_file.read_text()
            try:
                data = yaml.safe_load(content)
                assert isinstance(data, dict), (
                    f"{workflow_file.name} did not parse as a mapping"
                )
            except yaml.YAMLError as e:
                pytest.fail(f"{workflow_file.name} is not valid YAML: {e}")


class TestCIWorkflow:
    """Tests for the CI workflow (ci.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("ci.yml")

    def test_ci_has_name(self, workflow: dict) -> None:
        """Verify CI workflow has a name."""
        assert "name" in workflow, "CI workflow must have a name"

    def test_ci_triggers_on_push_and_pr(self, workflow: dict) -> None:
        """Verify CI triggers on push to main and pull requests."""
        triggers = get_triggers(workflow)
        assert triggers, "CI workflow must define triggers"
        assert "push" in triggers, "CI should trigger on push"
        assert "pull_request" in triggers, "CI should trigger on pull_request"

    def test_ci_has_lint_job(self, workflow: dict) -> None:
        """Verify CI workflow includes a lint job."""
        jobs = workflow.get("jobs", {})
        assert "lint" in jobs, "CI workflow should have a 'lint' job"

    def test_ci_has_test_job(self, workflow: dict) -> None:
        """Verify CI workflow includes a test job."""
        jobs = workflow.get("jobs", {})
        assert "test" in jobs, "CI workflow should have a 'test' job"

    def test_ci_test_matrix_has_python_versions(self, workflow: dict) -> None:
        """Verify test job uses a Python version matrix."""
        test_job = workflow.get("jobs", {}).get("test", {})
        strategy = test_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        python_versions = matrix.get("python-version", [])
        assert len(python_versions) >= 2, (
            "Test job should test against multiple Python versions"
        )

    def test_ci_test_matrix_includes_target_versions(self, workflow: dict) -> None:
        """Verify test matrix includes key Python versions."""
        test_job = workflow.get("jobs", {}).get("test", {})
        strategy = test_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        python_versions = matrix.get("python-version", [])
        assert "3.12" in python_versions, "Test matrix should include Python 3.12"
        assert "3.9" in python_versions, "Test matrix should include Python 3.9"

    def test_ci_uses_pip_caching(self, workflow: dict) -> None:
        """Verify CI workflow uses pip caching for performance."""
        workflow_text = yaml.dump(workflow)
        assert "cache" in workflow_text.lower(), (
            "CI workflow should use pip dependency caching"
        )

    def test_ci_uploads_coverage(self, workflow: dict) -> None:
        """Verify CI workflow uploads coverage reports."""
        workflow_text = yaml.dump(workflow)
        assert "codecov" in workflow_text.lower(), (
            "CI workflow should upload coverage to Codecov"
        )

    def test_ci_has_concurrency(self, workflow: dict) -> None:
        """Verify CI workflow has concurrency settings to cancel stale runs."""
        assert "concurrency" in workflow, (
            "CI workflow should set concurrency to cancel stale runs"
        )


class TestReleaseWorkflow:
    """Tests for the Release workflow (release.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("release.yml")

    def test_release_triggers_on_tag(self, workflow: dict) -> None:
        """Verify release triggers on version tags."""
        triggers = get_triggers(workflow)
        push_config = triggers.get("push", {})
        tags = push_config.get("tags", [])
        assert any("v*" in str(tag) for tag in tags), (
            "Release should trigger on v* tags"
        )

    def test_release_has_build_job(self, workflow: dict) -> None:
        """Verify release workflow has a build job."""
        jobs = workflow.get("jobs", {})
        assert "build" in jobs, "Release workflow should have a 'build' job"

    def test_release_has_publish_job(self, workflow: dict) -> None:
        """Verify release workflow has a publish job."""
        jobs = workflow.get("jobs", {})
        has_publish = any("publish" in job_name for job_name in jobs)
        assert has_publish, "Release workflow should have a publish job"

    def test_release_has_github_release_job(self, workflow: dict) -> None:
        """Verify release workflow creates a GitHub release."""
        jobs = workflow.get("jobs", {})
        has_release = any("release" in job_name for job_name in jobs)
        assert has_release, "Release workflow should create a GitHub release"

    def test_release_uses_secrets_for_pypi(self, workflow: dict) -> None:
        """Verify release uses secrets reference for PyPI token (not hardcoded)."""
        workflow_text = yaml.dump(workflow)
        assert "PYPI_TOKEN" in workflow_text, (
            "Release should reference PYPI_TOKEN secret"
        )
        assert "secrets.PYPI_TOKEN" in workflow_text, (
            "PYPI_TOKEN must be referenced via secrets context"
        )


class TestDockerWorkflow:
    """Tests for the Docker workflow (docker.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("docker.yml")

    def test_docker_triggers(self, workflow: dict) -> None:
        """Verify Docker workflow triggers on push and tags."""
        triggers = get_triggers(workflow)
        assert "push" in triggers, "Docker workflow should trigger on push"

    def test_docker_uses_buildx(self, workflow: dict) -> None:
        """Verify Docker workflow uses Buildx for multi-arch builds."""
        workflow_text = yaml.dump(workflow)
        assert "buildx" in workflow_text.lower(), (
            "Docker workflow should use Docker Buildx"
        )

    def test_docker_builds_multi_arch(self, workflow: dict) -> None:
        """Verify Docker workflow builds for multiple architectures."""
        workflow_text = yaml.dump(workflow)
        assert "amd64" in workflow_text, (
            "Docker workflow should build for linux/amd64"
        )
        assert "arm64" in workflow_text, (
            "Docker workflow should build for linux/arm64"
        )

    def test_docker_pushes_to_ghcr(self, workflow: dict) -> None:
        """Verify Docker workflow pushes to GitHub Container Registry."""
        workflow_text = yaml.dump(workflow)
        # codeql[py/incomplete-url-substring-sanitization] - Test assertion verifying expected URL pattern, not sanitizing user input
        assert "ghcr.io" in workflow_text, (
            "Docker workflow should push to ghcr.io"
        )

    def test_docker_uses_caching(self, workflow: dict) -> None:
        """Verify Docker workflow uses build caching."""
        workflow_text = yaml.dump(workflow)
        assert "cache" in workflow_text.lower(), (
            "Docker workflow should use build caching"
        )


class TestSecurityWorkflow:
    """Tests for the Security workflow (security.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("security.yml")

    def test_security_has_schedule(self, workflow: dict) -> None:
        """Verify security workflow runs on a schedule."""
        triggers = get_triggers(workflow)
        assert "schedule" in triggers, (
            "Security workflow should run on a schedule"
        )

    def test_security_has_dependency_audit(self, workflow: dict) -> None:
        """Verify security workflow includes dependency auditing."""
        jobs = workflow.get("jobs", {})
        has_audit = any("audit" in job_name.lower() for job_name in jobs)
        assert has_audit, "Security workflow should include dependency auditing"

    def test_security_has_bandit(self, workflow: dict) -> None:
        """Verify security workflow includes bandit scanning."""
        jobs = workflow.get("jobs", {})
        has_bandit = any("bandit" in job_name.lower() for job_name in jobs)
        assert has_bandit, "Security workflow should include bandit scanning"

    def test_security_has_codeql(self, workflow: dict) -> None:
        """Verify security workflow includes CodeQL analysis."""
        jobs = workflow.get("jobs", {})
        has_codeql = any("codeql" in job_name.lower() for job_name in jobs)
        assert has_codeql, "Security workflow should include CodeQL analysis"

    def test_security_triggers_on_pr(self, workflow: dict) -> None:
        """Verify security workflow also triggers on pull requests."""
        triggers = get_triggers(workflow)
        assert "pull_request" in triggers, (
            "Security workflow should trigger on pull requests"
        )


class TestDependabotConfig:
    """Tests for the Dependabot configuration."""

    @pytest.fixture
    def dependabot_data(self) -> dict:
        path = PROJECT_ROOT / ".github" / "dependabot.yml"
        assert path.exists(), f"dependabot.yml not found at {path}"
        content = path.read_text()
        return yaml.safe_load(content)

    def test_dependabot_exists(self) -> None:
        """Verify dependabot.yml exists."""
        path = PROJECT_ROOT / ".github" / "dependabot.yml"
        assert path.exists(), "dependabot.yml must exist in .github/"

    def test_dependabot_version(self, dependabot_data: dict) -> None:
        """Verify Dependabot config uses version 2."""
        assert dependabot_data.get("version") == 2, (
            "Dependabot config must use version 2"
        )

    def test_dependabot_has_pip_ecosystem(self, dependabot_data: dict) -> None:
        """Verify Dependabot monitors pip dependencies."""
        ecosystems = [
            u["package-ecosystem"] for u in dependabot_data.get("updates", [])
        ]
        assert "pip" in ecosystems, "Dependabot should monitor pip dependencies"

    def test_dependabot_has_github_actions_ecosystem(self, dependabot_data: dict) -> None:
        """Verify Dependabot monitors GitHub Actions versions."""
        ecosystems = [
            u["package-ecosystem"] for u in dependabot_data.get("updates", [])
        ]
        assert "github-actions" in ecosystems, (
            "Dependabot should monitor GitHub Actions versions"
        )

    def test_dependabot_has_docker_ecosystem(self, dependabot_data: dict) -> None:
        """Verify Dependabot monitors Docker base images."""
        ecosystems = [
            u["package-ecosystem"] for u in dependabot_data.get("updates", [])
        ]
        assert "docker" in ecosystems, (
            "Dependabot should monitor Docker base images"
        )
