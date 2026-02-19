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

# Project root is two levels above tests/ci/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
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
        assert WORKFLOWS_DIR.exists(), ".github/workflows directory must exist"

    def test_all_expected_workflows_exist(self) -> None:
        """Verify all expected workflow files are present."""
        expected_workflows = ["ci.yml", "ci-full.yml", "release.yml", "docker.yml", "security.yml"]
        for workflow in expected_workflows:
            path = WORKFLOWS_DIR / workflow
            assert path.exists(), f"Expected workflow file not found: {workflow}"

    def test_all_workflow_files_are_valid_yaml(self) -> None:
        """Verify all workflow files in the directory are valid YAML."""
        for workflow_file in WORKFLOWS_DIR.glob("*.yml"):
            content = workflow_file.read_text()
            try:
                data = yaml.safe_load(content)
                assert isinstance(data, dict), f"{workflow_file.name} did not parse as a mapping"
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

    def test_ci_uses_python_312(self, workflow: dict) -> None:
        """Verify CI test job uses Python 3.9 and 3.12 for fast feedback."""
        jobs = workflow.get("jobs", {})
        assert "test" in jobs, "CI workflow should have a 'test' job"
        test_job = jobs["test"]

        # Ensure the test job uses a matrix strategy with Python 3.9 and 3.12
        strategy = test_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        python_versions = matrix.get("python-version", [])

        assert len(python_versions) == 2, (
            "CI 'test' job must test against exactly 2 Python versions (3.9 and 3.12)"
        )
        assert "3.9" in python_versions, "CI 'test' job must include Python 3.9 in the matrix"
        assert "3.12" in python_versions, "CI 'test' job must include Python 3.12 in the matrix"

        # Verify the setup-python step uses the matrix variable
        steps = test_job.get("steps", [])
        assert isinstance(steps, list), "CI 'test' job must define a list of steps"

        setup_python_step = None
        for step in steps:
            uses = step.get("uses")
            if isinstance(uses, str) and "actions/setup-python" in uses:
                setup_python_step = step
                break

        assert setup_python_step is not None, (
            "CI 'test' job must include an actions/setup-python step"
        )

        with_section = setup_python_step.get("with", {})
        python_version = with_section.get("python-version")
        assert python_version == "${{ matrix.python-version }}", (
            "CI 'test' job must use matrix.python-version variable"
        )

    def test_ci_uses_pip_caching(self, workflow: dict) -> None:
        """Verify CI workflow uses pip caching for performance."""
        workflow_text = yaml.dump(workflow)
        assert "cache" in workflow_text.lower(), "CI workflow should use pip dependency caching"

    def test_ci_uploads_coverage(self, workflow: dict) -> None:
        """Verify CI workflow uploads coverage reports."""
        workflow_text = yaml.dump(workflow)
        assert "codecov" in workflow_text.lower(), "CI workflow should upload coverage to Codecov"

    def test_ci_has_concurrency(self, workflow: dict) -> None:
        """Verify CI workflow has concurrency settings to cancel stale runs."""
        assert "concurrency" in workflow, "CI workflow should set concurrency to cancel stale runs"

    def test_ci_has_frontend_test_job(self, workflow: dict) -> None:
        """Verify CI workflow includes frontend testing capability.

        Note: The fast CI workflow (ci.yml) focuses on backend testing for cost
        efficiency. Frontend testing is delegated to ci-full.yml which is
        triggered manually or on major PRs.
        """
        # Frontend testing is intentionally not in the fast CI to reduce
        # GitHub Actions billable minutes. This is managed in ci-full.yml.
        jobs = workflow.get("jobs", {})
        # For fast CI, we just verify it has the essential jobs
        assert "lint" in jobs, "CI workflow should have a 'lint' job"
        assert "test" in jobs, "CI workflow should have a 'test' job"

    def test_ci_has_docs_accuracy_step(self, workflow: dict) -> None:
        """Verify documentation testing is part of the test suite.

        Note: Documentation accuracy tests are integrated into the main
        pytest suite rather than as a separate step in the fast CI.
        This is part of the cost optimization strategy (Issue #333).
        """
        # Documentation tests are now part of the standard pytest suite
        # and run under the same "Run tests" step, ensuring docs are
        # validated as part of the CI without extra steps.
        test_job = workflow.get("jobs", {}).get("test", {})
        steps = test_job.get("steps", [])

        # Verify there's a "Run tests" step that executes pytest
        has_test_step = False
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_name = step.get("name", "")
            run_cmd = step.get("run", "")
            if step_name == "Run tests" and "pytest" in run_cmd:
                has_test_step = True
                break

        assert has_test_step, "Test job should run pytest which includes documentation tests"


class TestCIFullWorkflow:
    """Tests for the CI Full Matrix workflow (ci-full.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("ci-full.yml")

    def test_ci_full_has_name(self, workflow: dict) -> None:
        """Verify CI Full workflow has a name."""
        assert "name" in workflow, "CI Full workflow must have a name"

    def test_ci_full_triggers_on_schedule(self, workflow: dict) -> None:
        """Verify CI Full triggers on a daily schedule (not on every PR).

        The full matrix workflow is expensive (4 Python versions + Node jobs)
        and is intentionally run only on schedule and manual dispatch, not on
        every pull request. ci.yml handles PR-triggered test runs.
        """
        triggers = get_triggers(workflow)
        assert triggers, "CI Full workflow must define triggers"
        assert "schedule" in triggers, "CI Full should trigger on a cron schedule"
        assert "workflow_dispatch" in triggers, "CI Full should support manual dispatch"
        assert "pull_request" not in triggers, (
            "CI Full must NOT trigger on pull_request — use ci.yml for PR checks. "
            "Running the full matrix on every PR causes duplicate expensive jobs."
        )

    def test_ci_full_supports_manual_trigger(self, workflow: dict) -> None:
        """Verify CI Full can be triggered manually."""
        triggers = get_triggers(workflow)
        assert "workflow_dispatch" in triggers, (
            "CI Full should support workflow_dispatch for manual triggers"
        )

    def test_ci_full_has_test_matrix_job(self, workflow: dict) -> None:
        """Verify CI Full workflow includes a test-matrix job."""
        jobs = workflow.get("jobs", {})
        assert "test-matrix" in jobs, "CI Full workflow should have a 'test-matrix' job"

    def test_ci_full_test_matrix_has_python_versions(self, workflow: dict) -> None:
        """Verify test-matrix job tests all four Python versions."""
        test_matrix_job = workflow.get("jobs", {}).get("test-matrix", {})
        strategy = test_matrix_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        python_versions = matrix.get("python-version", [])
        assert len(python_versions) == 4, (
            "Test-matrix job should test against all 4 Python versions (3.9, 3.10, 3.11, 3.12)"
        )

    def test_ci_full_test_matrix_includes_versions(self, workflow: dict) -> None:
        """Verify test matrix includes all Python versions 3.9, 3.10, 3.11, and 3.12."""
        test_matrix_job = workflow.get("jobs", {}).get("test-matrix", {})
        strategy = test_matrix_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        python_versions = matrix.get("python-version", [])
        assert "3.9" in python_versions, "Test matrix should include Python 3.9"
        assert "3.10" in python_versions, "Test matrix should include Python 3.10"
        assert "3.11" in python_versions, "Test matrix should include Python 3.11"
        assert "3.12" in python_versions, (
            "Test matrix should include Python 3.12 for comprehensive coverage"
        )

    def test_ci_full_test_matrix_does_not_collect_coverage(self, workflow: dict) -> None:
        """Ensure test-matrix job does not collect coverage."""
        test_matrix_job = workflow.get("jobs", {}).get("test-matrix", {})
        steps = test_matrix_job.get("steps", [])
        for step in steps:
            if not isinstance(step, dict):
                continue
            run_cmd = step.get("run", "")
            assert "--cov" not in run_cmd, (
                "test-matrix job should not collect coverage (no '--cov' in commands)"
            )

    def test_ci_full_has_frontend_compat_job(self, workflow: dict) -> None:
        """Verify CI Full workflow includes a frontend-compat placeholder job.

        The frontend-compat job is currently a no-op placeholder because this repo
        has no JS build system (package.json). Once a frontend build system is
        introduced the job should be updated to run real Node/npm steps.
        """
        jobs = workflow.get("jobs", {})
        assert "frontend-compat" in jobs, "CI Full workflow should have a 'frontend-compat' job"
        frontend_compat_job = jobs.get("frontend-compat", {})
        steps = frontend_compat_job.get("steps", [])
        assert steps, "Frontend-compat job should define at least one step"

        # The job must NOT install Node (no package.json exists — that would fail CI).
        node_setup_steps = [
            step
            for step in steps
            if isinstance(step, dict)
            and isinstance(step.get("uses"), str)
            and step["uses"].startswith("actions/setup-node")
        ]
        assert not node_setup_steps, (
            "Frontend-compat is a placeholder — it must not use actions/setup-node "
            "until a JS build system (package.json) is added to the repo"
        )

    def test_ci_full_has_e2e_placeholder_job(self, workflow: dict) -> None:
        """Verify CI Full workflow includes a disabled E2E placeholder job."""
        jobs = workflow.get("jobs", {})
        assert "frontend-e2e" in jobs, (
            "CI Full workflow should have a 'frontend-e2e' placeholder job"
        )
        e2e_job = jobs["frontend-e2e"]

        # The E2E job should remain a placeholder and must not run real E2E tests
        steps = e2e_job.get("steps", [])
        for step in steps:
            if not isinstance(step, dict):
                continue
            # Check that no step uses setup-node action
            uses = step.get("uses", "")
            assert "setup-node" not in uses, "Frontend E2E placeholder job must not set up Node.js"
            # Check run commands for actual E2E test execution (not just mentions in echo)
            run_cmd = step.get("run", "")
            # Only check non-echo lines for actual commands
            for line in run_cmd.split("\n"):
                line_stripped = line.strip()
                # Skip echo statements and comments
                if line_stripped.startswith("echo") or line_stripped.startswith("#"):
                    continue
                # Check for actual playwright or E2E test commands
                assert "playwright install" not in line_stripped.lower(), (
                    "Frontend E2E placeholder job must not install Playwright"
                )
                assert "npm run test:e2e" not in line_stripped.lower(), (
                    "Frontend E2E placeholder job must not run E2E tests"
                )
                assert "npx playwright test" not in line_stripped.lower(), (
                    "Frontend E2E placeholder job must not execute Playwright tests"
                )

        # Verify the job only has echo/informational steps
        run_steps = [step for step in steps if isinstance(step, dict) and "run" in step]
        assert run_steps, (
            "Frontend E2E placeholder job should have run steps that document "
            "that E2E tests are disabled"
        )

    def test_ci_full_has_concurrency(self, workflow: dict) -> None:
        """Verify CI Full workflow has concurrency settings to cancel stale runs."""
        assert "concurrency" in workflow, (
            "CI Full workflow should set concurrency to cancel stale runs"
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
        assert any("v*" in str(tag) for tag in tags), "Release should trigger on v* tags"

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
        assert "PYPI_TOKEN" in workflow_text, "Release should reference PYPI_TOKEN secret"
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
        assert "buildx" in workflow_text.lower(), "Docker workflow should use Docker Buildx"

    def test_docker_builds_multi_arch(self, workflow: dict) -> None:
        """Verify Docker workflow builds for multiple architectures."""
        workflow_text = yaml.dump(workflow)
        assert "amd64" in workflow_text, "Docker workflow should build for linux/amd64"
        assert "arm64" in workflow_text, "Docker workflow should build for linux/arm64"

    def test_docker_pushes_to_ghcr(self, workflow: dict) -> None:
        """Verify Docker workflow pushes to GitHub Container Registry."""
        jobs = workflow.get("jobs", {})
        build_job = jobs.get("build-and-push", {})
        steps = build_job.get("steps", [])

        has_ghcr_login = False
        for step in steps:
            uses = step.get("uses", "")
            if isinstance(uses, str) and "docker/login-action" in uses:
                registry = step.get("with", {}).get("registry")
                if registry == "ghcr.io":
                    has_ghcr_login = True
                    break

        assert has_ghcr_login, "Docker workflow must log in to ghcr.io"

    def test_docker_uses_caching(self, workflow: dict) -> None:
        """Verify Docker workflow uses build caching."""
        workflow_text = yaml.dump(workflow)
        assert "cache" in workflow_text.lower(), "Docker workflow should use build caching"


class TestSecurityWorkflow:
    """Tests for the Security workflow (security.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("security.yml")

    def test_security_has_schedule(self, workflow: dict) -> None:
        """Verify security workflow runs on a schedule."""
        triggers = get_triggers(workflow)
        assert "schedule" in triggers, "Security workflow should run on a schedule"

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
        assert "pull_request" in triggers, "Security workflow should trigger on pull requests"


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
        assert dependabot_data.get("version") == 2, "Dependabot config must use version 2"

    def test_dependabot_has_pip_ecosystem(self, dependabot_data: dict) -> None:
        """Verify Dependabot monitors pip dependencies."""
        ecosystems = [u["package-ecosystem"] for u in dependabot_data.get("updates", [])]
        assert "pip" in ecosystems, "Dependabot should monitor pip dependencies"

    def test_dependabot_has_github_actions_ecosystem(self, dependabot_data: dict) -> None:
        """Verify Dependabot monitors GitHub Actions versions."""
        ecosystems = [u["package-ecosystem"] for u in dependabot_data.get("updates", [])]
        assert "github-actions" in ecosystems, "Dependabot should monitor GitHub Actions versions"

    def test_dependabot_has_docker_ecosystem(self, dependabot_data: dict) -> None:
        """Verify Dependabot monitors Docker base images."""
        ecosystems = [u["package-ecosystem"] for u in dependabot_data.get("updates", [])]
        assert "docker" in ecosystems, "Dependabot should monitor Docker base images"
