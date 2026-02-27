"""Tests for Docker configuration files.

Validates Dockerfile syntax, docker-compose schema, and .dockerignore patterns.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# Project root is two levels above tests/ci/
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
class TestDockerfile:
    """Tests for Dockerfile validity and best practices."""

    @pytest.fixture
    def dockerfile_content(self) -> str:
        """Read the Dockerfile content."""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"
        return dockerfile_path.read_text()

    def test_dockerfile_exists(self) -> None:
        """Verify Dockerfile exists in project root."""
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        assert dockerfile_path.exists(), "Dockerfile must exist in project root"

    def test_dockerfile_has_from_instruction(self, dockerfile_content: str) -> None:
        """Verify Dockerfile has at least one FROM instruction."""
        from_lines = [
            line
            for line in dockerfile_content.splitlines()
            if line.strip().upper().startswith("FROM ")
        ]
        assert len(from_lines) >= 1, "Dockerfile must have at least one FROM instruction"

    def test_dockerfile_uses_multi_stage_build(self, dockerfile_content: str) -> None:
        """Verify Dockerfile uses multi-stage build pattern."""
        from_lines = [
            line
            for line in dockerfile_content.splitlines()
            if line.strip().upper().startswith("FROM ")
        ]
        assert len(from_lines) >= 2, (
            "Dockerfile should use multi-stage build (at least 2 FROM instructions)"
        )

    def test_dockerfile_uses_slim_base(self, dockerfile_content: str) -> None:
        """Verify Dockerfile uses slim base image for smaller size."""
        assert "slim" in dockerfile_content.lower(), (
            "Dockerfile should use a slim base image (e.g., python:3.11-slim)"
        )

    def test_dockerfile_has_non_root_user(self, dockerfile_content: str) -> None:
        """Verify Dockerfile creates and uses a non-root user."""
        has_useradd = "useradd" in dockerfile_content or "adduser" in dockerfile_content
        has_user_switch = "USER " in dockerfile_content
        assert has_useradd and has_user_switch, (
            "Dockerfile must create a non-root user and switch to it"
        )

    def test_dockerfile_has_healthcheck(self, dockerfile_content: str) -> None:
        """Verify Dockerfile includes a HEALTHCHECK instruction."""
        assert "HEALTHCHECK" in dockerfile_content, (
            "Dockerfile should include a HEALTHCHECK instruction"
        )

    def test_dockerfile_exposes_port(self, dockerfile_content: str) -> None:
        """Verify Dockerfile exposes the expected port."""
        assert "EXPOSE 8000" in dockerfile_content, (
            "Dockerfile should expose port 8000 for the web API"
        )

    def test_dockerfile_has_volume(self, dockerfile_content: str) -> None:
        """Verify Dockerfile declares data volume."""
        assert "VOLUME" in dockerfile_content, (
            "Dockerfile should declare a VOLUME for data persistence"
        )

    def test_dockerfile_no_secrets(self, dockerfile_content: str) -> None:
        """Verify Dockerfile does not contain hardcoded secrets."""
        secret_patterns = [
            r"password\s*=\s*['\"]",
            r"secret\s*=\s*['\"]",
            r"api_key\s*=\s*['\"]",
            r"token\s*=\s*['\"](?!.*\$\{)",
        ]
        for pattern in secret_patterns:
            matches = re.findall(pattern, dockerfile_content, re.IGNORECASE)
            assert not matches, f"Dockerfile should not contain hardcoded secrets. Found: {matches}"

    def test_dockerfile_has_labels(self, dockerfile_content: str) -> None:
        """Verify Dockerfile includes OCI labels."""
        assert "LABEL" in dockerfile_content, (
            "Dockerfile should include LABEL instructions for image metadata"
        )


@pytest.mark.unit
class TestDockerCompose:
    """Tests for docker-compose.yml validity."""

    @pytest.fixture
    def compose_data(self) -> dict:
        """Parse docker-compose.yml."""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        assert compose_path.exists(), f"docker-compose.yml not found at {compose_path}"
        content = compose_path.read_text()
        return yaml.safe_load(content)

    def test_docker_compose_exists(self) -> None:
        """Verify docker-compose.yml exists in project root."""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        assert compose_path.exists(), "docker-compose.yml must exist in project root"

    def test_docker_compose_valid_yaml(self) -> None:
        """Verify docker-compose.yml is valid YAML."""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        content = compose_path.read_text()
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            pytest.fail(f"docker-compose.yml is not valid YAML: {e}")

    def test_docker_compose_has_services(self, compose_data: dict) -> None:
        """Verify docker-compose.yml defines services."""
        assert "services" in compose_data, "docker-compose.yml must define services"
        assert len(compose_data["services"]) >= 1, (
            "docker-compose.yml must define at least one service"
        )

    def test_docker_compose_has_file_organizer_service(self, compose_data: dict) -> None:
        """Verify file-organizer service is defined."""
        assert "file-organizer" in compose_data["services"], (
            "docker-compose.yml must define a 'file-organizer' service"
        )

    def test_docker_compose_has_redis_service(self, compose_data: dict) -> None:
        """Verify redis service is defined for event system."""
        assert "redis" in compose_data["services"], (
            "docker-compose.yml must define a 'redis' service"
        )

    def test_docker_compose_redis_healthcheck(self, compose_data: dict) -> None:
        """Verify redis service has a healthcheck."""
        redis_svc = compose_data["services"]["redis"]
        assert "healthcheck" in redis_svc, "Redis service should have a healthcheck"

    def test_docker_compose_has_volumes(self, compose_data: dict) -> None:
        """Verify docker-compose.yml defines named volumes for persistence."""
        assert "volumes" in compose_data, (
            "docker-compose.yml must define volumes for data persistence"
        )

    def test_docker_compose_has_networks(self, compose_data: dict) -> None:
        """Verify docker-compose.yml defines a network."""
        assert "networks" in compose_data, "docker-compose.yml should define a custom network"

    def test_docker_compose_no_secrets(self) -> None:
        """Verify docker-compose.yml does not contain hardcoded secrets."""
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        content = compose_path.read_text()
        secret_patterns = [
            r"password:\s*['\"][^$]",
            r"POSTGRES_PASSWORD:\s*['\"][^$]",
            r"SECRET_KEY:\s*['\"][^$]",
        ]
        for pattern in secret_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            assert not matches, (
                f"docker-compose.yml should not contain hardcoded secrets. Found: {matches}"
            )


@pytest.mark.unit
class TestDockerignore:
    """Tests for .dockerignore file."""

    @pytest.fixture
    def dockerignore_content(self) -> str:
        """Read the .dockerignore content."""
        path = PROJECT_ROOT / ".dockerignore"
        assert path.exists(), f".dockerignore not found at {path}"
        return path.read_text()

    def test_dockerignore_exists(self) -> None:
        """Verify .dockerignore exists in project root."""
        path = PROJECT_ROOT / ".dockerignore"
        assert path.exists(), ".dockerignore must exist in project root"

    def test_dockerignore_excludes_git(self, dockerignore_content: str) -> None:
        """Verify .dockerignore excludes .git directory."""
        assert ".git" in dockerignore_content, ".dockerignore should exclude .git"

    def test_dockerignore_excludes_venv(self, dockerignore_content: str) -> None:
        """Verify .dockerignore excludes virtual environments."""
        has_venv = any(pattern in dockerignore_content for pattern in [".venv", "venv", "env"])
        assert has_venv, ".dockerignore should exclude virtual environments"

    def test_dockerignore_excludes_pycache(self, dockerignore_content: str) -> None:
        """Verify .dockerignore excludes Python cache."""
        assert "__pycache__" in dockerignore_content, ".dockerignore should exclude __pycache__"

    def test_dockerignore_excludes_tests(self, dockerignore_content: str) -> None:
        """Verify .dockerignore excludes test artifacts."""
        has_test_artifacts = any(
            pattern in dockerignore_content for pattern in [".pytest_cache", ".coverage", "htmlcov"]
        )
        assert has_test_artifacts, ".dockerignore should exclude test artifacts"
