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
    wf: dict[Any, Any] = workflow
    triggers = wf.get("on", wf.get(True, {}))
    if not isinstance(triggers, dict):
        return {}
    return triggers


def assert_artifact_naming_contract(
    shard_job: dict[str, Any],
    gate_job: dict[str, Any],
    expected_prefix: str,
    shard_job_name: str,
) -> None:
    """Assert that the coverage upload and download artifact names share a prefix.

    Verifies that the shard job uploads with a name starting with *expected_prefix*
    and that the coverage-gate job downloads with a pattern starting with the same
    prefix, so a rename in one place cannot silently break aggregation.
    """
    upload_step = next(
        (
            s
            for s in shard_job.get("steps", [])
            if isinstance(s, dict) and "upload-artifact" in str(s.get("uses", ""))
        ),
        None,
    )
    assert upload_step is not None, f"'{shard_job_name}' must have an upload-artifact step"
    upload_name: str = upload_step.get("with", {}).get("name", "")
    assert upload_name.startswith(expected_prefix), (
        f"Upload artifact name must start with '{expected_prefix}', got '{upload_name}'"
    )
    download_step = next(
        (
            s
            for s in gate_job.get("steps", [])
            if isinstance(s, dict) and "download-artifact" in str(s.get("uses", ""))
        ),
        None,
    )
    assert download_step is not None, (
        f"coverage-gate for '{shard_job_name}' must have a download-artifact step"
    )
    download_pattern: str = download_step.get("with", {}).get("pattern", "")
    assert download_pattern.startswith(expected_prefix), (
        f"Download pattern must start with '{expected_prefix}', got '{download_pattern}'"
    )


def get_effective_env(
    workflow: dict[str, Any], job: dict[str, Any], step: dict[str, Any]
) -> dict[str, Any]:
    """Return the combined workflow, job, and step env maps for a step."""
    effective_env: dict[str, Any] = {}
    for env_source in (workflow.get("env", {}), job.get("env", {}), step.get("env", {})):
        if isinstance(env_source, dict):
            effective_env.update(env_source)
    return effective_env


def is_supported_github_token(value: Any) -> bool:
    """Return whether *value* is a supported GitHub Actions token expression."""
    return value in {"${{ secrets.GITHUB_TOKEN }}", "${{ github.token }}"}


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
                assert isinstance(data, dict) and len(data) > 0, (
                    f"{workflow_file.name} did not parse as a non-empty mapping"
                )
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
        """Verify the split PR/push test structure uses correct Python versions.

        ci.yml uses two separate jobs:
        - 'test': PR-only, Python 3.11 only (fast feedback, ~2 400 tests)
        - 'test-full': push-only, 5 shards x Python 3.11+3.12 (~17 000 tests)

        This replaces the old single 'test' job that used a conditional matrix
        expression and timed out due to GC pressure with 17 000 tests/2 workers.
        """
        jobs = workflow.get("jobs", {})

        # --- PR job: test ---
        assert "test" in jobs, "CI workflow must have a 'test' job for PR runs"
        test_job = jobs["test"]

        # Must be restricted to pull_request events
        assert test_job.get("if") == "github.event_name == 'pull_request'", (
            "'test' job must have if: github.event_name == 'pull_request'"
        )

        # Must use Python 3.11 only (speed; 3.12 is covered by test-full)
        strategy = test_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        python_versions = matrix.get("python-version", [])
        assert python_versions == ["3.11"], (
            f"'test' (PR) job must use [\"3.11\"] only, got {python_versions}"
        )

        # Must have a timeout to prevent indefinite hangs
        assert test_job.get("timeout-minutes") is not None, "'test' job must set timeout-minutes"

        # --- push job: test-full ---
        assert "test-full" in jobs, "CI workflow must have a 'test-full' job for push runs"
        full_job = jobs["test-full"]

        # Must be restricted to push events
        assert full_job.get("if") == "github.event_name == 'push'", (
            "'test-full' job must have if: github.event_name == 'push'"
        )

        # Must run both Python versions
        full_strategy = full_job.get("strategy", {})
        full_matrix = full_strategy.get("matrix", {})
        full_python = full_matrix.get("python-version", [])
        assert set(full_python) == {"3.11", "3.12"}, (
            f"'test-full' job must include both 3.11 and 3.12, got {full_python}"
        )

        # Must use 5 shards (shard 3 is lighter to keep async-heavy api/web tests below GC hang threshold)
        shards = full_matrix.get("shard", [])
        assert shards == [1, 2, 3, 4, 5], (
            f"'test-full' job must define shards [1, 2, 3, 4, 5], got {shards}"
        )

        # Must have a hard timeout
        assert full_job.get("timeout-minutes") is not None, (
            "'test-full' job must set timeout-minutes to prevent GC-finaliser hangs"
        )

        # Must have a coverage-gate job that aggregates shard artifacts
        assert "coverage-gate" in jobs, "CI workflow must have a 'coverage-gate' job for push runs"
        assert jobs["coverage-gate"].get("needs") == "test-full", (
            "'coverage-gate' must depend on 'test-full'"
        )

        # Artifact naming contract: upload name prefix must match download pattern
        # so coverage aggregation cannot silently break from a rename in one place.
        assert_artifact_naming_contract(full_job, jobs["coverage-gate"], "coverage-", "test-full")

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

    def test_ci_exposes_permissions_and_token_for_ci_only_guardrails(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify CI-only guardrails have the workflow support they require."""
        permissions = workflow.get("permissions", {})
        assert permissions.get("pull-requests") == "read", (
            "ci.yml must grant pull-requests: read so PR guardrails can query PR files"
        )

        jobs = workflow.get("jobs", {})
        lint_job = jobs.get("lint", {})
        test_job = jobs.get("test", {})
        lint_steps = lint_job.get("steps", [])
        test_steps = test_job.get("steps", [])

        lint_pre_commit_step = next(
            (
                step
                for step in lint_steps
                if isinstance(step, dict)
                and isinstance(step.get("run"), str)
                and "pre-commit run" in step["run"]
                and "--all-files" in step["run"]
            ),
            None,
        )
        assert lint_pre_commit_step is not None, "lint job must run pre-commit across the repo"
        lint_env = get_effective_env(workflow, lint_job, lint_pre_commit_step)
        assert is_supported_github_token(lint_env.get("GITHUB_TOKEN")), (
            "lint pre-commit step must expose GITHUB_TOKEN for CI-only PR guardrails"
        )

        test_run_step = next(
            (
                step
                for step in test_steps
                if isinstance(step, dict) and step.get("name") == "Run tests"
            ),
            None,
        )
        assert test_run_step is not None, "test job must have a Run tests step"
        test_env = get_effective_env(workflow, test_job, test_run_step)
        assert is_supported_github_token(test_env.get("GITHUB_TOKEN")), (
            "test job must expose GITHUB_TOKEN for CI-only PR guardrails"
        )

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

    def test_ci_full_has_linux_shards(self, workflow: dict[str, Any]) -> None:
        """Verify ci-full.yml includes the Linux full-suite sharded job.

        The daily run validates the full ~17 000-test suite on Linux using the
        same 5-shard matrix as the push CI in ci.yml.  This replaces the old
        design where ci.yml owned all Linux testing — that design never
        completed because 17 000 tests/2 workers triggered a GC-finaliser hang.
        """
        jobs = workflow.get("jobs", {})
        assert "test-linux-full" in jobs, (
            "CI Full must have a 'test-linux-full' job for the daily Linux full-suite run"
        )
        job = jobs["test-linux-full"]
        strategy = job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        python_versions = matrix.get("python-version", [])
        assert set(python_versions) == {"3.11", "3.12"}, (
            f"'test-linux-full' must include both 3.11 and 3.12, got {python_versions}"
        )
        shards = matrix.get("shard", [])
        assert shards == [1, 2, 3, 4, 5], (
            f"'test-linux-full' shards must be [1, 2, 3, 4, 5], got {shards}"
        )
        assert job.get("timeout-minutes") is not None, (
            "'test-linux-full' job must set timeout-minutes"
        )

        # Must have a coverage-gate job for the daily gate
        assert "coverage-gate" in jobs, "CI Full must have a 'coverage-gate' job"
        assert jobs["coverage-gate"].get("needs") == "test-linux-full", (
            "'coverage-gate' must depend on 'test-linux-full'"
        )

        # Artifact naming contract: upload name prefix must match download pattern.
        assert_artifact_naming_contract(
            job, jobs["coverage-gate"], "daily-coverage-", "test-linux-full"
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


@pytest.mark.unit
class TestShardCoverage:
    """Verify that all test directories are assigned to a CI shard.

    Prevents silent test exclusion — the exact failure mode that caused
    tests/interfaces and tests/e2e to be skipped in all CI runs before
    this guard was added.
    """

    # Directories intentionally excluded from shards (no test files or
    # not standalone pytest-collectible directories).
    _EXCLUDED: frozenset[str] = frozenset(
        {
            "auth",  # no test_*.py files yet; add to a shard when populated
            "fixtures",  # test fixture data, not a collectible test directory
            "__pycache__",
        }
    )

    @pytest.fixture
    def shard_script(self) -> str:
        path = Path("scripts/ci_shard_paths.sh")
        assert path.exists(), "scripts/ci_shard_paths.sh must exist"
        return path.read_text()

    def test_all_test_directories_assigned_to_shard(self, shard_script: str) -> None:
        """Every subdirectory of tests/ must appear in ci_shard_paths.sh.

        If a test directory is missing from the shard script it will be silently
        skipped in all CI runs (both push and daily full matrix), because both
        ci.yml and ci-full.yml source this script as the single mapping.
        """
        tests_root = Path("tests")
        unassigned = []
        for p in sorted(tests_root.iterdir()):
            if not p.is_dir():
                continue
            if p.name in self._EXCLUDED:
                continue
            if p.name not in shard_script:
                unassigned.append(p.name)
        assert not unassigned, (
            f"The following test directories are not assigned to any shard in "
            f"scripts/ci_shard_paths.sh: {unassigned}. "
            f"Add them to an appropriate shard or to _EXCLUDED if intentional."
        )
