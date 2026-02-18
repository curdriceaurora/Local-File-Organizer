"""Tests for Docker configuration files and docker_utils module.

Validates Dockerfiles, docker-compose files, .dockerignore patterns,
and the docker_utils helper functions.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest
import yaml

# Project root is three levels above file_organizer_v2/tests/ci/
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Import the docker_utils module
sys.path.insert(0, str(PROJECT_ROOT / "file_organizer_v2" / "scripts"))

docker_utils = importlib.import_module("docker_utils")
get_image_size_estimate = docker_utils.get_image_size_estimate
parse_docker_compose = docker_utils.parse_docker_compose
validate_dockerfile = docker_utils.validate_dockerfile


# =============================================================================
# Dockerfile Tests
# =============================================================================


class TestDockerfileStructure:
    """Tests for Dockerfile structural validity and best practices."""

    @pytest.fixture
    def dockerfile_path(self) -> Path:
        """Return path to the production Dockerfile."""
        return PROJECT_ROOT / "Dockerfile"

    @pytest.fixture
    def dockerfile_content(self, dockerfile_path: Path) -> str:
        """Read the Dockerfile content."""
        assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"
        return dockerfile_path.read_text()

    def test_dockerfile_exists(self, dockerfile_path: Path) -> None:
        """Verify Dockerfile exists in project root."""
        assert dockerfile_path.exists(), "Dockerfile must exist in project root"

    def test_dockerfile_has_multi_stage_build(self, dockerfile_content: str) -> None:
        """Verify Dockerfile uses multi-stage build with at least 2 FROM stages."""
        from_lines = [
            line
            for line in dockerfile_content.splitlines()
            if line.strip().upper().startswith("FROM ")
        ]
        assert len(from_lines) >= 2, (
            "Dockerfile should use multi-stage build (at least 2 FROM instructions)"
        )

    def test_dockerfile_builder_stage_exists(self, dockerfile_content: str) -> None:
        """Verify Dockerfile has a named builder stage."""
        assert re.search(r"FROM\s+\S+\s+AS\s+builder", dockerfile_content, re.IGNORECASE), (
            "Dockerfile should have a 'builder' stage"
        )

    def test_dockerfile_runtime_stage_exists(self, dockerfile_content: str) -> None:
        """Verify Dockerfile has a named runtime stage."""
        assert re.search(r"FROM\s+\S+\s+AS\s+runtime", dockerfile_content, re.IGNORECASE), (
            "Dockerfile should have a 'runtime' stage"
        )

    def test_dockerfile_uses_python_311_slim(self, dockerfile_content: str) -> None:
        """Verify Dockerfile uses python:3.11-slim base image."""
        assert "python:3.11-slim" in dockerfile_content, (
            "Dockerfile should use python:3.11-slim base image"
        )

    def test_dockerfile_builder_installs_build_deps(self, dockerfile_content: str) -> None:
        """Verify builder stage installs build dependencies."""
        assert "build-essential" in dockerfile_content, (
            "Builder stage should install build-essential"
        )

    def test_dockerfile_installs_to_opt_venv(self, dockerfile_content: str) -> None:
        """Verify dependencies are installed into /opt/venv."""
        assert "/opt/venv" in dockerfile_content, "Dependencies should be installed to /opt/venv"

    def test_dockerfile_runtime_installs_ffmpeg(self, dockerfile_content: str) -> None:
        """Verify runtime stage installs ffmpeg."""
        assert "ffmpeg" in dockerfile_content, (
            "Runtime stage should install ffmpeg for media processing"
        )

    def test_dockerfile_runtime_installs_libmagic(self, dockerfile_content: str) -> None:
        """Verify runtime stage installs libmagic."""
        assert "libmagic" in dockerfile_content, (
            "Runtime stage should install libmagic for file type detection"
        )

    def test_dockerfile_has_non_root_user(self, dockerfile_content: str) -> None:
        """Verify Dockerfile creates and switches to non-root user."""
        has_useradd = "useradd" in dockerfile_content or "adduser" in dockerfile_content
        has_user_switch = "USER " in dockerfile_content
        assert has_useradd, "Dockerfile must create a non-root user"
        assert has_user_switch, "Dockerfile must switch to non-root user"

    def test_dockerfile_user_is_organizer(self, dockerfile_content: str) -> None:
        """Verify the non-root user is named 'organizer' with UID 1000."""
        assert "organizer" in dockerfile_content, "Non-root user should be named 'organizer'"
        assert "1000" in dockerfile_content, "User should have UID/GID 1000"

    def test_dockerfile_has_healthcheck(self, dockerfile_content: str) -> None:
        """Verify Dockerfile includes a HEALTHCHECK instruction."""
        assert "HEALTHCHECK" in dockerfile_content, (
            "Dockerfile should include a HEALTHCHECK instruction"
        )

    def test_dockerfile_exposes_port_8000(self, dockerfile_content: str) -> None:
        """Verify Dockerfile exposes port 8000."""
        assert "EXPOSE 8000" in dockerfile_content, (
            "Dockerfile should expose port 8000 for the web API"
        )

    def test_dockerfile_has_data_volume(self, dockerfile_content: str) -> None:
        """Verify Dockerfile declares /data volume."""
        assert "VOLUME" in dockerfile_content, (
            "Dockerfile should declare a VOLUME for data persistence"
        )
        assert "/data" in dockerfile_content, "Volume should be at /data"

    def test_dockerfile_has_oci_labels(self, dockerfile_content: str) -> None:
        """Verify Dockerfile includes OCI-compliant labels."""
        required_labels = [
            "org.opencontainers.image.title",
            "org.opencontainers.image.description",
            "org.opencontainers.image.version",
        ]
        for label in required_labels:
            assert label in dockerfile_content, f"Dockerfile should include OCI label: {label}"

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

    def test_dockerfile_cleans_apt_lists(self, dockerfile_content: str) -> None:
        """Verify apt-get install is followed by cleanup."""
        if "apt-get update" in dockerfile_content:
            assert "rm -rf /var/lib/apt/lists" in dockerfile_content, (
                "apt-get update should be followed by 'rm -rf /var/lib/apt/lists/*'"
            )

    def test_dockerfile_copies_venv_from_builder(self, dockerfile_content: str) -> None:
        """Verify runtime stage copies venv from builder."""
        assert "COPY --from=builder /opt/venv /opt/venv" in dockerfile_content, (
            "Runtime stage should copy /opt/venv from builder stage"
        )


# =============================================================================
# Dockerfile.dev Tests
# =============================================================================


class TestDockerfileDev:
    """Tests for development Dockerfile."""

    @pytest.fixture
    def dockerfile_dev_path(self) -> Path:
        """Return path to the development Dockerfile."""
        return PROJECT_ROOT / "Dockerfile.dev"

    @pytest.fixture
    def dockerfile_dev_content(self, dockerfile_dev_path: Path) -> str:
        """Read the Dockerfile.dev content."""
        assert dockerfile_dev_path.exists(), f"Dockerfile.dev not found at {dockerfile_dev_path}"
        return dockerfile_dev_path.read_text()

    def test_dockerfile_dev_exists(self, dockerfile_dev_path: Path) -> None:
        """Verify Dockerfile.dev exists in project root."""
        assert dockerfile_dev_path.exists(), "Dockerfile.dev must exist in project root"

    def test_dockerfile_dev_uses_full_python(self, dockerfile_dev_content: str) -> None:
        """Verify dev Dockerfile uses full Python image (not slim)."""
        from_lines = [
            line
            for line in dockerfile_dev_content.splitlines()
            if line.strip().upper().startswith("FROM ")
        ]
        assert len(from_lines) >= 1
        # The dev image should use full python (not slim) for dev tools
        assert "python:3.11" in from_lines[0], "Dev Dockerfile should use python:3.11 base image"

    def test_dockerfile_dev_includes_dev_tools(self, dockerfile_dev_content: str) -> None:
        """Verify dev Dockerfile installs development tools."""
        dev_tools = ["git", "vim"]
        for tool in dev_tools:
            assert tool in dockerfile_dev_content, f"Dev Dockerfile should install {tool}"

    def test_dockerfile_dev_exposes_debug_port(self, dockerfile_dev_content: str) -> None:
        """Verify dev Dockerfile exposes debug port 5678."""
        assert "5678" in dockerfile_dev_content, (
            "Dev Dockerfile should expose debug port 5678 (debugpy)"
        )

    def test_dockerfile_dev_has_reload(self, dockerfile_dev_content: str) -> None:
        """Verify dev Dockerfile enables live reload."""
        assert "--reload" in dockerfile_dev_content, (
            "Dev Dockerfile should enable live reload for development"
        )


# =============================================================================
# docker-compose.yml Tests
# =============================================================================


class TestDockerCompose:
    """Tests for docker-compose.yml validity and structure."""

    @pytest.fixture
    def compose_path(self) -> Path:
        """Return path to docker-compose.yml."""
        return PROJECT_ROOT / "docker-compose.yml"

    @pytest.fixture
    def compose_data(self, compose_path: Path) -> dict:
        """Parse docker-compose.yml."""
        assert compose_path.exists(), f"docker-compose.yml not found at {compose_path}"
        content = compose_path.read_text()
        return yaml.safe_load(content)

    def test_docker_compose_exists(self, compose_path: Path) -> None:
        """Verify docker-compose.yml exists in project root."""
        assert compose_path.exists(), "docker-compose.yml must exist in project root"

    def test_docker_compose_valid_yaml(self, compose_path: Path) -> None:
        """Verify docker-compose.yml is valid YAML."""
        content = compose_path.read_text()
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            pytest.fail(f"docker-compose.yml is not valid YAML: {e}")

    def test_docker_compose_has_services(self, compose_data: dict) -> None:
        """Verify docker-compose.yml defines services."""
        assert "services" in compose_data, "docker-compose.yml must define services"
        assert len(compose_data["services"]) >= 1

    def test_docker_compose_has_file_organizer_service(self, compose_data: dict) -> None:
        """Verify file-organizer service is defined."""
        assert "file-organizer" in compose_data["services"], (
            "docker-compose.yml must define a 'file-organizer' service"
        )

    def test_docker_compose_has_redis_service(self, compose_data: dict) -> None:
        """Verify redis service is defined."""
        assert "redis" in compose_data["services"], (
            "docker-compose.yml must define a 'redis' service"
        )

    def test_docker_compose_redis_uses_alpine(self, compose_data: dict) -> None:
        """Verify redis uses alpine-based image."""
        redis_svc = compose_data["services"]["redis"]
        assert "image" in redis_svc
        assert "alpine" in redis_svc["image"], "Redis should use alpine image"

    def test_docker_compose_redis_version_7(self, compose_data: dict) -> None:
        """Verify redis uses version 7."""
        redis_svc = compose_data["services"]["redis"]
        assert "7" in redis_svc["image"], "Redis should use version 7"

    def test_docker_compose_redis_healthcheck(self, compose_data: dict) -> None:
        """Verify redis service has a healthcheck."""
        redis_svc = compose_data["services"]["redis"]
        assert "healthcheck" in redis_svc, "Redis service should have a healthcheck"
        assert "test" in redis_svc["healthcheck"]

    def test_docker_compose_has_named_volumes(self, compose_data: dict) -> None:
        """Verify docker-compose.yml defines named volumes."""
        assert "volumes" in compose_data, "docker-compose.yml must define named volumes"
        assert len(compose_data["volumes"]) >= 1

    def test_docker_compose_has_custom_network(self, compose_data: dict) -> None:
        """Verify docker-compose.yml defines a custom network."""
        assert "networks" in compose_data, "docker-compose.yml should define a custom network"

    def test_docker_compose_file_organizer_depends_on_redis(self, compose_data: dict) -> None:
        """Verify file-organizer depends on redis."""
        fo_svc = compose_data["services"]["file-organizer"]
        assert "depends_on" in fo_svc, "file-organizer should depend on redis"

    def test_docker_compose_no_secrets(self, compose_path: Path) -> None:
        """Verify docker-compose.yml does not contain hardcoded secrets."""
        content = compose_path.read_text()
        secret_patterns = [
            r"password:\s*['\"][^$]",
            r"POSTGRES_PASSWORD:\s*['\"][^$]",
            r"SECRET_KEY:\s*['\"][^$]",
        ]
        for pattern in secret_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            assert not matches, (
                f"docker-compose.yml should not contain hardcoded secrets: {matches}"
            )


# =============================================================================
# docker-compose.dev.yml Tests
# =============================================================================


class TestDockerComposeDev:
    """Tests for docker-compose.dev.yml override file."""

    @pytest.fixture
    def compose_dev_path(self) -> Path:
        """Return path to docker-compose.dev.yml."""
        return PROJECT_ROOT / "docker-compose.dev.yml"

    @pytest.fixture
    def compose_dev_data(self, compose_dev_path: Path) -> dict:
        """Parse docker-compose.dev.yml."""
        assert compose_dev_path.exists(), f"docker-compose.dev.yml not found at {compose_dev_path}"
        content = compose_dev_path.read_text()
        return yaml.safe_load(content)

    def test_docker_compose_dev_exists(self, compose_dev_path: Path) -> None:
        """Verify docker-compose.dev.yml exists."""
        assert compose_dev_path.exists(), "docker-compose.dev.yml must exist in project root"

    def test_docker_compose_dev_uses_dev_dockerfile(self, compose_dev_data: dict) -> None:
        """Verify dev compose uses Dockerfile.dev."""
        fo_svc = compose_dev_data["services"]["file-organizer"]
        assert fo_svc["build"]["dockerfile"] == "Dockerfile.dev", (
            "Dev compose should use Dockerfile.dev"
        )

    def test_docker_compose_dev_mounts_source(self, compose_dev_data: dict) -> None:
        """Verify dev compose mounts source code as volume."""
        fo_svc = compose_dev_data["services"]["file-organizer"]
        volumes = fo_svc.get("volumes", [])
        source_mounted = any("src" in str(v) for v in volumes)
        assert source_mounted, "Dev compose should mount source code for live reload"

    def test_docker_compose_dev_debug_mode(self, compose_dev_data: dict) -> None:
        """Verify dev compose enables debug mode."""
        fo_svc = compose_dev_data["services"]["file-organizer"]
        env = fo_svc.get("environment", [])
        env_str = str(env)
        assert "DEBUG" in env_str, "Dev compose should enable debug mode"

    def test_docker_compose_dev_has_test_runner(self, compose_dev_data: dict) -> None:
        """Verify dev compose includes a test runner service."""
        assert "test-runner" in compose_dev_data["services"], (
            "Dev compose should define a test-runner service"
        )

    def test_docker_compose_dev_exposes_debug_port(self, compose_dev_data: dict) -> None:
        """Verify dev compose exposes debug port."""
        fo_svc = compose_dev_data["services"]["file-organizer"]
        ports = fo_svc.get("ports", [])
        port_str = str(ports)
        assert "5678" in port_str, "Dev compose should expose debug port 5678"


# =============================================================================
# .dockerignore Tests
# =============================================================================


class TestDockerignore:
    """Tests for .dockerignore file completeness."""

    @pytest.fixture
    def dockerignore_path(self) -> Path:
        """Return path to .dockerignore."""
        return PROJECT_ROOT / ".dockerignore"

    @pytest.fixture
    def dockerignore_content(self, dockerignore_path: Path) -> str:
        """Read .dockerignore content."""
        assert dockerignore_path.exists(), f".dockerignore not found at {dockerignore_path}"
        return dockerignore_path.read_text()

    def test_dockerignore_exists(self, dockerignore_path: Path) -> None:
        """Verify .dockerignore exists."""
        assert dockerignore_path.exists(), ".dockerignore must exist in project root"

    def test_dockerignore_excludes_git(self, dockerignore_content: str) -> None:
        """Verify .dockerignore excludes .git directory."""
        assert ".git" in dockerignore_content, ".dockerignore should exclude .git"

    def test_dockerignore_excludes_venv(self, dockerignore_content: str) -> None:
        """Verify .dockerignore excludes virtual environments."""
        has_venv = any(pattern in dockerignore_content for pattern in [".venv", "venv", "env"])
        assert has_venv, ".dockerignore should exclude virtual environments"

    def test_dockerignore_excludes_pycache(self, dockerignore_content: str) -> None:
        """Verify .dockerignore excludes __pycache__."""
        assert "__pycache__" in dockerignore_content

    def test_dockerignore_excludes_test_artifacts(self, dockerignore_content: str) -> None:
        """Verify .dockerignore excludes test artifacts."""
        has_test_artifacts = any(
            pattern in dockerignore_content for pattern in [".pytest_cache", ".coverage", "htmlcov"]
        )
        assert has_test_artifacts

    def test_dockerignore_excludes_ide_files(self, dockerignore_content: str) -> None:
        """Verify .dockerignore excludes IDE configuration files."""
        has_ide = any(pattern in dockerignore_content for pattern in [".vscode", ".idea"])
        assert has_ide, ".dockerignore should exclude IDE files"

    def test_dockerignore_excludes_node_modules(self, dockerignore_content: str) -> None:
        """Verify .dockerignore excludes node_modules."""
        assert "node_modules" in dockerignore_content


# =============================================================================
# docker_utils.py Tests
# =============================================================================


class TestValidateDockerfile:
    """Tests for the validate_dockerfile utility function."""

    def test_validate_production_dockerfile(self) -> None:
        """Validate the production Dockerfile returns no errors."""
        issues = validate_dockerfile(PROJECT_ROOT / "Dockerfile")
        errors = [i for i in issues if i.startswith("ERROR")]
        assert not errors, f"Production Dockerfile has errors: {errors}"

    def test_validate_dev_dockerfile(self) -> None:
        """Validate the dev Dockerfile returns no errors."""
        issues = validate_dockerfile(PROJECT_ROOT / "Dockerfile.dev")
        errors = [i for i in issues if i.startswith("ERROR")]
        assert not errors, f"Dev Dockerfile has errors: {errors}"

    def test_validate_nonexistent_file(self) -> None:
        """Verify FileNotFoundError for missing Dockerfile."""
        with pytest.raises(FileNotFoundError):
            validate_dockerfile("/nonexistent/Dockerfile")

    def test_validate_detects_no_from(self, tmp_path: Path) -> None:
        """Verify detection of missing FROM instruction."""
        df = tmp_path / "Dockerfile"
        df.write_text("RUN echo hello\n")
        issues = validate_dockerfile(df)
        assert any("No FROM instruction" in i for i in issues)

    def test_validate_detects_latest_tag(self, tmp_path: Path) -> None:
        """Verify detection of :latest tag usage."""
        df = tmp_path / "Dockerfile"
        df.write_text("FROM python:latest\nRUN echo hello\n")
        issues = validate_dockerfile(df)
        assert any("latest" in i.lower() for i in issues)

    def test_validate_detects_no_user(self, tmp_path: Path) -> None:
        """Verify detection of missing USER instruction."""
        df = tmp_path / "Dockerfile"
        df.write_text("FROM python:3.11-slim\nRUN echo hello\n")
        issues = validate_dockerfile(df)
        assert any("root" in i.lower() or "USER" in i for i in issues)

    def test_validate_detects_apt_without_cleanup(self, tmp_path: Path) -> None:
        """Verify detection of apt-get update without cleanup."""
        df = tmp_path / "Dockerfile"
        df.write_text(
            "FROM python:3.11-slim\nRUN apt-get update && apt-get install -y curl\nUSER nobody\n"
        )
        issues = validate_dockerfile(df)
        assert any("apt" in i.lower() and "cleanup" in i.lower() for i in issues)


class TestParseDockerCompose:
    """Tests for the parse_docker_compose utility function."""

    def test_parse_production_compose(self) -> None:
        """Parse the production docker-compose.yml successfully."""
        data = parse_docker_compose(PROJECT_ROOT / "docker-compose.yml")
        assert "services" in data
        assert "file-organizer" in data["services"]

    def test_parse_dev_compose(self) -> None:
        """Parse the dev docker-compose.dev.yml successfully."""
        data = parse_docker_compose(PROJECT_ROOT / "docker-compose.dev.yml")
        assert "services" in data

    def test_parse_nonexistent_file(self) -> None:
        """Verify FileNotFoundError for missing compose file."""
        with pytest.raises(FileNotFoundError):
            parse_docker_compose("/nonexistent/docker-compose.yml")

    def test_parse_invalid_yaml(self, tmp_path: Path) -> None:
        """Verify ValueError for invalid YAML content."""
        bad_file = tmp_path / "docker-compose.yml"
        bad_file.write_text(":\n  :\n    - : :\n  {invalid")
        with pytest.raises(ValueError, match="Invalid YAML"):
            parse_docker_compose(bad_file)

    def test_parse_returns_dict(self) -> None:
        """Verify parse returns a dictionary."""
        data = parse_docker_compose(PROJECT_ROOT / "docker-compose.yml")
        assert isinstance(data, dict)


class TestGetImageSizeEstimate:
    """Tests for the get_image_size_estimate utility function."""

    def test_estimate_production_dockerfile(self) -> None:
        """Estimate size for production Dockerfile returns reasonable value."""
        size = get_image_size_estimate(PROJECT_ROOT / "Dockerfile")
        # Production image should be between 100MB and 2GB
        assert 100 * 1024 * 1024 <= size <= 2 * 1024 * 1024 * 1024, (
            f"Estimated size {size / 1024 / 1024:.0f}MB seems unreasonable"
        )

    def test_estimate_dev_dockerfile(self) -> None:
        """Estimate size for dev Dockerfile is larger than production."""
        prod_size = get_image_size_estimate(PROJECT_ROOT / "Dockerfile")
        dev_size = get_image_size_estimate(PROJECT_ROOT / "Dockerfile.dev")
        assert dev_size > prod_size, "Dev image should be larger than production image"

    def test_estimate_nonexistent_file(self) -> None:
        """Verify FileNotFoundError for missing Dockerfile."""
        with pytest.raises(FileNotFoundError):
            get_image_size_estimate("/nonexistent/Dockerfile")

    def test_estimate_returns_positive_int(self) -> None:
        """Verify estimate returns a positive integer."""
        size = get_image_size_estimate(PROJECT_ROOT / "Dockerfile")
        assert isinstance(size, int)
        assert size > 0

    def test_estimate_slim_vs_full_base(self, tmp_path: Path) -> None:
        """Verify slim base results in smaller estimate than full base."""
        slim_df = tmp_path / "Dockerfile.slim"
        slim_df.write_text("FROM python:3.11-slim\nRUN echo hello\n")

        full_df = tmp_path / "Dockerfile.full"
        full_df.write_text("FROM python:3.11\nRUN echo hello\n")

        slim_size = get_image_size_estimate(slim_df)
        full_size = get_image_size_estimate(full_df)
        assert slim_size < full_size, "Slim base should estimate smaller than full"
