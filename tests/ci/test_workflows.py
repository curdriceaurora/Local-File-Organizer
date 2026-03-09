"""Tests for GitHub Actions workflow files.

Validates YAML structure, required fields, and best practices for all workflow files.

Note: PyYAML parses the YAML key ``on`` as the Python boolean ``True``
because ``on`` is a boolean literal in YAML 1.1.  The helper
``get_triggers`` accounts for this.
"""

from __future__ import annotations

import json
import re
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
    wf: dict[Any, Any] = workflow
    triggers = wf.get("on", wf.get(True, {}))
    if not isinstance(triggers, dict):
        return {}
    return triggers


@pytest.mark.unit
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


@pytest.mark.unit
class TestCIWorkflow:
    """Tests for the CI workflow (ci.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("ci.yml")

    def test_ci_has_name(self, workflow: dict[str, Any]) -> None:
        """Verify CI workflow has a name."""
        assert "name" in workflow, "CI workflow must have a name"

    def test_ci_triggers_on_push_and_pr(self, workflow: dict[str, Any]) -> None:
        """Verify CI triggers on push to main and pull requests."""
        triggers = get_triggers(workflow)
        assert triggers, "CI workflow must define triggers"
        assert "push" in triggers, "CI should trigger on push"
        assert "pull_request" in triggers, "CI should trigger on pull_request"

    def test_ci_has_lint_job(self, workflow: dict[str, Any]) -> None:
        """Verify CI workflow includes a lint job."""
        jobs = workflow.get("jobs", {})
        assert "lint" in jobs, "CI workflow should have a 'lint' job"

    def test_ci_has_test_job(self, workflow: dict[str, Any]) -> None:
        """Verify CI workflow includes a test job."""
        jobs = workflow.get("jobs", {})
        assert "test" in jobs, "CI workflow should have a 'test' job"

    def test_ci_uses_python_312(self, workflow: dict[str, Any]) -> None:
        """Verify CI test job dynamically selects Python versions by event type.

        The test matrix uses a GitHub Actions expression to select versions:
        - Pull requests: 3.11 only (faster feedback)
        - Full runs (push): 3.11 and 3.12 (comprehensive testing)
        """
        jobs = workflow.get("jobs", {})
        assert "test" in jobs, "CI workflow should have a 'test' job"
        test_job = jobs["test"]

        # Ensure the test job uses a matrix strategy with Python versions
        strategy = test_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        python_versions_value = matrix.get("python-version", [])

        # Handle both static lists and GitHub Actions expressions
        if isinstance(python_versions_value, str):
            # This is a GitHub Actions expression like:
            # ${{ github.event_name == 'pull_request' && fromJson('["3.11"]') || fromJson('["3.11", "3.12"]') }}
            assert python_versions_value.startswith("${{"), (
                "python-version should be a GitHub Actions expression starting with ${{ "
                f"but got: {python_versions_value}"
            )
            # Verify the expression contains pull_request handling
            assert "pull_request" in python_versions_value, (
                "Expression should handle pull_request events differently"
            )

            # Parse the fromJson payloads to validate version arrays
            fromjson_pattern = r"fromJson\('(\[.*?\])'\)"
            matches = re.findall(fromjson_pattern, python_versions_value)
            assert len(matches) == 2, (
                f"Expected 2 fromJson(...) payloads in expression, found {len(matches)}"
            )

            # Parse JSON arrays and validate versions
            arrays = [json.loads(match) for match in matches]
            assert ["3.11"] in arrays, (
                "Expression must include fromJson('[\"3.11\"]') for PR runs"
            )
            assert ["3.11", "3.12"] in arrays, (
                "Expression must include fromJson('[\"3.11\", \"3.12\"]') for full runs"
            )
        else:
            # If it's a static list (shouldn't be in this workflow)
            python_versions = python_versions_value if isinstance(python_versions_value, list) else [python_versions_value]
            assert python_versions == ["3.11", "3.12"], (
                f"CI 'test' job must use exactly [\"3.11\", \"3.12\"], "
                f"got {python_versions}"
            )

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

    def test_ci_uses_pip_caching(self, workflow: dict[str, Any]) -> None:
        """Verify CI workflow uses pip caching for performance."""
        workflow_text = yaml.dump(workflow)
        assert "cache" in workflow_text.lower(), "CI workflow should use pip dependency caching"

    def test_ci_uploads_coverage(self, workflow: dict[str, Any]) -> None:
        """Verify CI workflow uploads coverage reports."""
        workflow_text = yaml.dump(workflow)
        assert "codecov" in workflow_text.lower(), "CI workflow should upload coverage to Codecov"

    def test_ci_has_concurrency(self, workflow: dict[str, Any]) -> None:
        """Verify CI workflow has concurrency settings to cancel stale runs."""
        assert "concurrency" in workflow, "CI workflow should set concurrency to cancel stale runs"

    def test_ci_has_frontend_test_job(self, workflow: dict[str, Any]) -> None:
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

    def test_ci_has_docs_accuracy_step(self, workflow: dict[str, Any]) -> None:
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


@pytest.mark.unit
class TestCIFullWorkflow:
    """Tests for the CI Full Matrix workflow (ci-full.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("ci-full.yml")

    def test_ci_full_has_name(self, workflow: dict[str, Any]) -> None:
        """Verify CI Full workflow has a name."""
        assert "name" in workflow, "CI Full workflow must have a name"

    def test_ci_full_triggers_on_schedule(self, workflow: dict[str, Any]) -> None:
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

    def test_ci_full_supports_manual_trigger(self, workflow: dict[str, Any]) -> None:
        """Verify CI Full can be triggered manually."""
        triggers = get_triggers(workflow)
        assert "workflow_dispatch" in triggers, (
            "CI Full should support workflow_dispatch for manual triggers"
        )

    def test_ci_full_no_linux_matrix_duplication(self, workflow: dict[str, Any]) -> None:
        """Verify ci-full.yml does NOT duplicate the Linux matrix from ci.yml.

        Issue #474: ci.yml owns Linux 3.11/3.12 (push + PR). ci-full.yml covers
        macOS and Windows only to avoid duplicate daily compute.
        """
        jobs = workflow.get("jobs", {})
        assert "test-matrix" not in jobs, (
            "CI Full must NOT have a 'test-matrix' job — Linux matrix belongs to ci.yml. "
            "See Issue #474."
        )

    def test_ci_full_platform_jobs_do_not_collect_coverage(self, workflow: dict[str, Any]) -> None:
        """Ensure macOS and Windows platform jobs do not collect coverage.

        Coverage reporting is owned by ci.yml (Linux 3.12 job) to keep
        a single authoritative source.
        """
        jobs = workflow.get("jobs", {})
        for job_name in ("test-macos", "test-windows"):
            assert job_name in jobs, (
                f"Expected '{job_name}' job in CI Full workflow — "
                "platform jobs must be present for cross-OS coverage"
            )
            job = jobs[job_name]
            steps = job.get("steps", [])
            for step in steps:
                if not isinstance(step, dict):
                    continue
                run_cmd = step.get("run", "")
                assert "--cov" not in run_cmd, (
                    f"{job_name} must not collect coverage — coverage owned by ci.yml"
                )

    def test_ci_full_no_frontend_placeholder_jobs(self, workflow: dict[str, Any]) -> None:
        """Verify frontend placeholder jobs were removed (#369).

        Node.js infrastructure was removed in #372 and E2E tests are deferred (#393).
        The frontend-compat and frontend-e2e placeholder jobs wasted CI minutes
        doing nothing, so they were removed.
        """
        jobs = workflow.get("jobs", {})
        assert "frontend-compat" not in jobs, (
            "frontend-compat placeholder was removed in #369 (Node.js infra removed in #372)"
        )
        assert "frontend-e2e" not in jobs, (
            "frontend-e2e placeholder was removed in #369 (E2E deferred in #393)"
        )

    def test_ci_full_has_macos_job(self, workflow: dict[str, Any]) -> None:
        """Verify CI Full includes a macOS runner (issue #370)."""
        jobs = workflow.get("jobs", {})
        assert "test-macos" in jobs, "CI Full should have a 'test-macos' job (issue #370)"
        macos_job = jobs["test-macos"]
        assert macos_job.get("runs-on") == "macos-latest", "macOS job must use macos-latest runner"

    def test_ci_full_has_windows_job(self, workflow: dict[str, Any]) -> None:
        """Verify CI Full includes a Windows runner (issue #371)."""
        jobs = workflow.get("jobs", {})
        assert "test-windows" in jobs, "CI Full should have a 'test-windows' job (issue #371)"
        windows_job = jobs["test-windows"]
        assert windows_job.get("runs-on") == "windows-latest", (
            "Windows job must use windows-latest runner"
        )

    def test_ci_full_platform_jobs_use_python_312(self, workflow: dict[str, Any]) -> None:
        """Verify macOS and Windows jobs use Python 3.12 only (issue #387 cost constraint)."""
        jobs = workflow.get("jobs", {})
        for job_name in ("test-macos", "test-windows"):
            assert job_name in jobs, f"Expected {job_name} job in CI Full workflow"
            job = jobs[job_name]
            steps = job.get("steps", [])
            for step in steps:
                if not isinstance(step, dict):
                    continue
                uses = step.get("uses", "")
                if isinstance(uses, str) and "actions/setup-python" in uses:
                    python_version = step.get("with", {}).get("python-version")
                    assert python_version == "3.12", (
                        f"{job_name} must use Python 3.12 only per issue #387 cost constraint"
                    )

    def test_ci_full_has_concurrency(self, workflow: dict[str, Any]) -> None:
        """Verify CI Full workflow has concurrency settings to cancel stale runs."""
        assert "concurrency" in workflow, (
            "CI Full workflow should set concurrency to cancel stale runs"
        )


@pytest.mark.unit
class TestReleaseWorkflow:
    """Tests for the Release workflow (release.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("release.yml")

    def test_release_triggers_on_tag(self, workflow: dict[str, Any]) -> None:
        """Verify release triggers on version tags."""
        triggers = get_triggers(workflow)
        push_config = triggers.get("push", {})
        tags = push_config.get("tags", [])
        assert any("v*" in str(tag) for tag in tags), "Release should trigger on v* tags"

    def test_release_has_build_job(self, workflow: dict[str, Any]) -> None:
        """Verify release workflow has a build job."""
        jobs = workflow.get("jobs", {})
        assert "build" in jobs, "Release workflow should have a 'build' job"

    def test_release_has_publish_job(self, workflow: dict[str, Any]) -> None:
        """Verify release workflow has a publish job."""
        jobs = workflow.get("jobs", {})
        has_publish = any("publish" in job_name for job_name in jobs)
        assert has_publish, "Release workflow should have a publish job"

    def test_release_has_github_release_job(self, workflow: dict[str, Any]) -> None:
        """Verify release workflow creates a GitHub release."""
        jobs = workflow.get("jobs", {})
        has_release = any("release" in job_name for job_name in jobs)
        assert has_release, "Release workflow should create a GitHub release"

    def test_release_uses_oidc_for_pypi(self, workflow: dict[str, Any]) -> None:
        """Verify release uses OIDC trusted publishing for PyPI (no API token needed)."""
        jobs = workflow.get("jobs", {})
        publish_job = jobs.get("publish-pypi", {})
        permissions = publish_job.get("permissions", {})
        assert permissions.get("id-token") == "write", (
            "publish-pypi job must have id-token: write for OIDC trusted publishing"
        )
        environment = publish_job.get("environment")
        if isinstance(environment, dict):
            environment_name = environment.get("name")
        else:
            environment_name = environment
        assert environment_name == "pypi", (
            "publish-pypi job must use the 'pypi' GitHub environment for OIDC"
        )


@pytest.mark.unit
class TestDockerWorkflow:
    """Tests for the Docker workflow (docker.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("docker.yml")

    def test_docker_triggers(self, workflow: dict[str, Any]) -> None:
        """Verify Docker workflow triggers on push and tags."""
        triggers = get_triggers(workflow)
        assert "push" in triggers, "Docker workflow should trigger on push"

    def test_docker_uses_buildx(self, workflow: dict[str, Any]) -> None:
        """Verify Docker workflow uses Buildx for multi-arch builds."""
        workflow_text = yaml.dump(workflow)
        assert "buildx" in workflow_text.lower(), "Docker workflow should use Docker Buildx"

    def test_docker_builds_multi_arch(self, workflow: dict[str, Any]) -> None:
        """Verify Docker workflow builds for multiple architectures."""
        workflow_text = yaml.dump(workflow)
        assert "amd64" in workflow_text, "Docker workflow should build for linux/amd64"
        assert "arm64" in workflow_text, "Docker workflow should build for linux/arm64"

    def test_docker_pushes_to_ghcr(self, workflow: dict[str, Any]) -> None:
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

    def test_docker_uses_caching(self, workflow: dict[str, Any]) -> None:
        """Verify Docker workflow uses build caching."""
        workflow_text = yaml.dump(workflow)
        assert "cache" in workflow_text.lower(), "Docker workflow should use build caching"


@pytest.mark.unit
class TestSecurityWorkflow:
    """Tests for the Security workflow (security.yml)."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        return load_workflow("security.yml")

    def test_security_has_schedule(self, workflow: dict[str, Any]) -> None:
        """Verify security workflow runs on a schedule."""
        triggers = get_triggers(workflow)
        assert "schedule" in triggers, "Security workflow should run on a schedule"

    def test_security_has_dependency_audit(self, workflow: dict[str, Any]) -> None:
        """Verify security workflow includes dependency auditing."""
        jobs = workflow.get("jobs", {})
        has_audit = any("audit" in job_name.lower() for job_name in jobs)
        assert has_audit, "Security workflow should include dependency auditing"

    def test_security_has_bandit(self, workflow: dict[str, Any]) -> None:
        """Verify security workflow includes bandit scanning."""
        jobs = workflow.get("jobs", {})
        has_bandit = any("bandit" in job_name.lower() for job_name in jobs)
        assert has_bandit, "Security workflow should include bandit scanning"

    def test_security_has_codeql(self, workflow: dict[str, Any]) -> None:
        """Verify security workflow includes CodeQL analysis."""
        jobs = workflow.get("jobs", {})
        has_codeql = any("codeql" in job_name.lower() for job_name in jobs)
        assert has_codeql, "Security workflow should include CodeQL analysis"

    def test_security_triggers_on_pr(self, workflow: dict[str, Any]) -> None:
        """Verify security workflow also triggers on pull requests."""
        triggers = get_triggers(workflow)
        assert "pull_request" in triggers, "Security workflow should trigger on pull requests"


@pytest.mark.unit
class TestDependabotConfig:
    """Tests for the Dependabot configuration."""

    @pytest.fixture
    def dependabot_data(self) -> dict[str, Any]:
        path = PROJECT_ROOT / ".github" / "dependabot.yml"
        assert path.exists(), f"dependabot.yml not found at {path}"
        content = path.read_text()
        data = yaml.safe_load(content)
        assert isinstance(data, dict), "dependabot.yml did not parse as a dict"
        return data

    def test_dependabot_exists(self) -> None:
        """Verify dependabot.yml exists."""
        path = PROJECT_ROOT / ".github" / "dependabot.yml"
        assert path.exists(), "dependabot.yml must exist in .github/"

    def test_dependabot_version(self, dependabot_data: dict[str, Any]) -> None:
        """Verify Dependabot config uses version 2."""
        assert dependabot_data.get("version") == 2, "Dependabot config must use version 2"

    def test_dependabot_has_pip_ecosystem(self, dependabot_data: dict[str, Any]) -> None:
        """Verify Dependabot monitors pip dependencies."""
        ecosystems = [u["package-ecosystem"] for u in dependabot_data.get("updates", [])]
        assert "pip" in ecosystems, "Dependabot should monitor pip dependencies"

    def test_dependabot_has_github_actions_ecosystem(self, dependabot_data: dict[str, Any]) -> None:
        """Verify Dependabot monitors GitHub Actions versions."""
        ecosystems = [u["package-ecosystem"] for u in dependabot_data.get("updates", [])]
        assert "github-actions" in ecosystems, "Dependabot should monitor GitHub Actions versions"

    def test_dependabot_has_docker_ecosystem(self, dependabot_data: dict[str, Any]) -> None:
        """Verify Dependabot monitors Docker base images."""
        ecosystems = [u["package-ecosystem"] for u in dependabot_data.get("updates", [])]
        assert "docker" in ecosystems, "Dependabot should monitor Docker base images"
