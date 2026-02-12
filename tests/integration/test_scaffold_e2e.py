"""Integration tests for the parse-then-scaffold pipeline.

These tests run the real parser and scaffolder end-to-end against the
sample requirements fixture and verify that the generated project directory
contains valid, well-formed configuration files.

No external services (Docker, Ollama, databases) are required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _parse_and_scaffold(
    sample_requirements: str, output_dir: Path
) -> Path:
    """Run the parser on the sample requirements, then scaffold a project.

    Returns the path to the generated project root.
    """
    from src.parser.extractor import parse_requirements
    from src.scaffolder import ProjectConfig, ProjectGenerator

    result = await parse_requirements(sample_requirements)

    arch = result.architecture
    config = ProjectConfig(
        name=arch.project_name,
        description=arch.description,
        auth_required=arch.auth_required,
        features=[f.model_dump() for f in result.features],
        db_collections=[c.model_dump() for c in arch.db_collections],
        api_contracts=[c.model_dump() for c in arch.api_contracts],
        external_apis=[e.model_dump() for e in arch.external_apis],
    )
    gen = ProjectGenerator(config)
    project_path = await gen.generate(output_dir)
    return project_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestScaffoldValidation:
    """Test that the scaffolder generates valid projects."""

    async def test_parse_then_scaffold(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Run parser on sample requirements, then scaffold a project."""
        from src.parser.extractor import parse_requirements
        from src.scaffolder import ProjectConfig, ProjectGenerator

        # Parse requirements
        result = await parse_requirements(sample_requirements)
        assert len(result.features) >= 4, (
            f"Expected at least 4 features, got {len(result.features)}"
        )

        # Generate project
        arch = result.architecture
        config = ProjectConfig(
            name=arch.project_name,
            description=arch.description,
            auth_required=arch.auth_required,
            features=[f.model_dump() for f in result.features],
            db_collections=[c.model_dump() for c in arch.db_collections],
            api_contracts=[c.model_dump() for c in arch.api_contracts],
            external_apis=[e.model_dump() for e in arch.external_apis],
        )
        gen = ProjectGenerator(config)
        project_path = await gen.generate(tmp_path)

        # Verify top-level structure
        assert project_path.exists(), "Project root directory was not created"
        assert (project_path / "docker-compose.yml").exists(), (
            "Missing docker-compose.yml"
        )
        assert (project_path / "docker-compose.dev.yml").exists(), (
            "Missing docker-compose.dev.yml"
        )
        assert (project_path / "docker-compose.test.yml").exists(), (
            "Missing docker-compose.test.yml"
        )
        assert (project_path / "frontend" / "package.json").exists(), (
            "Missing frontend/package.json"
        )
        assert (project_path / "backend" / "requirements.txt").exists(), (
            "Missing backend/requirements.txt"
        )
        assert (project_path / "Makefile").exists(), "Missing Makefile"
        assert (project_path / "README.md").exists(), "Missing README.md"

        # Verify backend directory structure
        assert (project_path / "backend" / "app" / "main.py").exists(), (
            "Missing backend/app/main.py"
        )
        assert (project_path / "backend" / "app" / "config.py").exists(), (
            "Missing backend/app/config.py"
        )
        assert (project_path / "backend" / "app" / "api" / "v1" / "endpoints").is_dir(), (
            "Missing backend/app/api/v1/endpoints/"
        )
        assert (project_path / "backend" / "app" / "models").is_dir(), (
            "Missing backend/app/models/"
        )
        assert (project_path / "backend" / "app" / "schemas").is_dir(), (
            "Missing backend/app/schemas/"
        )
        assert (project_path / "backend" / "app" / "services").is_dir(), (
            "Missing backend/app/services/"
        )
        assert (project_path / "backend" / "app" / "db").is_dir(), (
            "Missing backend/app/db/"
        )

        # Verify frontend directory structure
        assert (project_path / "frontend" / "src" / "api").is_dir(), (
            "Missing frontend/src/api/"
        )
        assert (project_path / "frontend" / "src" / "stores").is_dir(), (
            "Missing frontend/src/stores/"
        )
        assert (project_path / "frontend" / "src" / "pages").is_dir(), (
            "Missing frontend/src/pages/"
        )
        assert (project_path / "frontend" / "src" / "components").is_dir(), (
            "Missing frontend/src/components/"
        )

        # Verify infrastructure files
        assert (project_path / ".env.example").exists(), "Missing .env.example"
        assert (project_path / ".env.development").exists(), (
            "Missing .env.development"
        )
        assert (project_path / ".env.test").exists(), "Missing .env.test"
        assert (project_path / ".github" / "workflows" / "ci.yml").exists(), (
            "Missing .github/workflows/ci.yml"
        )
        assert (project_path / "scripts" / "setup.sh").exists(), (
            "Missing scripts/setup.sh"
        )

    async def test_generated_docker_compose_valid_yaml(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify generated docker-compose.yml is valid YAML with services."""
        project_path = await _parse_and_scaffold(sample_requirements, tmp_path)

        for compose_file in [
            "docker-compose.yml",
            "docker-compose.dev.yml",
            "docker-compose.test.yml",
        ]:
            file_path = project_path / compose_file
            assert file_path.exists(), f"Missing {compose_file}"

            content = file_path.read_text(encoding="utf-8")
            assert content.strip(), f"{compose_file} is empty"

            parsed = yaml.safe_load(content)
            assert parsed is not None, f"{compose_file} parsed to None"
            assert isinstance(parsed, dict), (
                f"{compose_file} is not a YAML mapping"
            )

            # Every compose file should define services
            assert "services" in parsed, (
                f"{compose_file} does not define 'services'"
            )
            services = parsed["services"]
            assert isinstance(services, dict), (
                f"{compose_file} 'services' is not a mapping"
            )
            assert len(services) >= 1, f"{compose_file} has no services defined"

    async def test_generated_package_json_has_dependencies(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify package.json includes required frontend dependencies."""
        project_path = await _parse_and_scaffold(sample_requirements, tmp_path)

        pkg_path = project_path / "frontend" / "package.json"
        assert pkg_path.exists(), "Missing frontend/package.json"

        content = pkg_path.read_text(encoding="utf-8")
        pkg = json.loads(content)

        # Collect all dependency names across deps and devDeps
        all_deps: set[str] = set()
        for key in ("dependencies", "devDependencies"):
            if key in pkg and isinstance(pkg[key], dict):
                all_deps.update(pkg[key].keys())

        # Core dependencies that the NC Dev System mandates
        required_deps = ["react", "zustand", "axios"]
        for dep in required_deps:
            assert dep in all_deps, (
                f"Required dependency '{dep}' not found in package.json. "
                f"Found: {sorted(all_deps)}"
            )

    async def test_generated_requirements_txt_has_dependencies(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify requirements.txt includes required backend packages."""
        project_path = await _parse_and_scaffold(sample_requirements, tmp_path)

        req_path = project_path / "backend" / "requirements.txt"
        assert req_path.exists(), "Missing backend/requirements.txt"

        content = req_path.read_text(encoding="utf-8").lower()
        assert content.strip(), "requirements.txt is empty"

        required_packages = ["fastapi", "uvicorn", "motor", "pydantic"]
        for pkg in required_packages:
            assert pkg in content, (
                f"Required package '{pkg}' not found in requirements.txt"
            )

    async def test_msw_handlers_generated(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify MSW handlers are generated for all API endpoints."""
        project_path = await _parse_and_scaffold(sample_requirements, tmp_path)

        handlers_path = project_path / "frontend" / "src" / "mocks" / "handlers.ts"
        assert handlers_path.exists(), (
            "Missing frontend/src/mocks/handlers.ts"
        )

        content = handlers_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, "handlers.ts is empty"

        # The handlers file should reference msw
        assert "msw" in content.lower() or "http" in content.lower(), (
            "handlers.ts does not appear to use MSW (missing 'msw' or 'http' reference)"
        )

    async def test_ports_use_custom_allocation(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify all configs use 23000+ ports, not default ports."""
        project_path = await _parse_and_scaffold(sample_requirements, tmp_path)

        # Forbidden default ports that must NOT appear in generated configs
        forbidden_ports = {"3000", "5000", "8000", "8080", "27017", "5432"}

        # Check docker-compose files for port mappings
        for compose_file in [
            "docker-compose.yml",
            "docker-compose.dev.yml",
            "docker-compose.test.yml",
        ]:
            file_path = project_path / compose_file
            if not file_path.exists():
                continue

            content = file_path.read_text(encoding="utf-8")
            parsed = yaml.safe_load(content)
            if not parsed or "services" not in parsed:
                continue

            for svc_name, svc_config in parsed["services"].items():
                if not isinstance(svc_config, dict):
                    continue
                ports = svc_config.get("ports", [])
                for port_mapping in ports:
                    port_str = str(port_mapping)
                    # Extract the host port (before the colon in "host:container")
                    host_port = port_str.split(":")[0].strip().strip('"').strip("'")
                    assert host_port not in forbidden_ports, (
                        f"Service '{svc_name}' in {compose_file} uses "
                        f"forbidden default port {host_port}. "
                        f"Expected 23000+ range."
                    )

        # Check .env files for port references
        for env_file in [".env.example", ".env.development", ".env.test"]:
            env_path = project_path / env_file
            if not env_path.exists():
                continue

            content = env_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Check for port-like patterns using forbidden defaults
                for port in forbidden_ports:
                    # Match patterns like ":27017" or "=27017" but not in
                    # documentation text
                    if f":{port}" in line or f"={port}" in line:
                        assert False, (
                            f"{env_file} contains forbidden default port "
                            f"{port} in line: {line}"
                        )

    async def test_backend_has_health_endpoint(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify the backend includes a health endpoint module."""
        project_path = await _parse_and_scaffold(sample_requirements, tmp_path)

        health_path = (
            project_path / "backend" / "app" / "api" / "v1" / "endpoints" / "health.py"
        )
        assert health_path.exists(), (
            "Missing backend/app/api/v1/endpoints/health.py"
        )

        content = health_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, "health.py is empty"

    async def test_keycloak_scaffolded_when_auth_required(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify keycloak directory is created when auth is required.

        The sample requirements include a User Authentication feature, so the
        parser should set auth_required=True and the scaffolder should create
        the keycloak directory.
        """
        from src.parser.extractor import parse_requirements

        result = await parse_requirements(sample_requirements)
        # The sample requirements include authentication
        assert result.architecture.auth_required is True, (
            "Parser should detect auth_required=True from the sample requirements"
        )

        project_path = await _parse_and_scaffold(sample_requirements, tmp_path)
        assert (project_path / "keycloak").is_dir(), (
            "Missing keycloak/ directory when auth is required"
        )

    async def test_per_feature_backend_files_generated(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify per-feature backend files (endpoint, model, schema, service)
        are generated for each parsed feature."""
        from src.parser.extractor import parse_requirements

        result = await parse_requirements(sample_requirements)
        project_path = await _parse_and_scaffold(sample_requirements, tmp_path)

        for feature in result.features:
            # The scaffolder uses _python_slugify on the feature name
            import re
            slug = re.sub(r"[^a-z0-9]+", "_", feature.name.lower().strip()).strip("_")

            endpoints_dir = (
                project_path / "backend" / "app" / "api" / "v1" / "endpoints"
            )
            models_dir = project_path / "backend" / "app" / "models"
            schemas_dir = project_path / "backend" / "app" / "schemas"
            services_dir = project_path / "backend" / "app" / "services"
            tests_dir = project_path / "backend" / "tests" / "unit"

            assert (endpoints_dir / f"{slug}.py").exists(), (
                f"Missing endpoint file for feature '{feature.name}': "
                f"endpoints/{slug}.py"
            )
            assert (models_dir / f"{slug}.py").exists(), (
                f"Missing model file for feature '{feature.name}': "
                f"models/{slug}.py"
            )
            assert (schemas_dir / f"{slug}.py").exists(), (
                f"Missing schema file for feature '{feature.name}': "
                f"schemas/{slug}.py"
            )
            assert (services_dir / f"{slug}_service.py").exists(), (
                f"Missing service file for feature '{feature.name}': "
                f"services/{slug}_service.py"
            )
            assert (tests_dir / f"test_{slug}.py").exists(), (
                f"Missing test file for feature '{feature.name}': "
                f"tests/unit/test_{slug}.py"
            )

    async def test_scripts_are_executable(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify generated shell scripts have the executable bit set.

        On Windows (NTFS) there are no Unix permission bits, so we only
        verify the scripts exist and have content.
        """
        import os
        import stat
        import sys

        project_path = await _parse_and_scaffold(sample_requirements, tmp_path)

        script_names = [
            "setup.sh",
            "seed-data.sh",
            "run-tests.sh",
            "validate-system.sh",
        ]

        for script_name in script_names:
            script_path = project_path / "scripts" / script_name
            assert script_path.exists(), f"Missing scripts/{script_name}"

            if sys.platform != "win32":
                mode = script_path.stat().st_mode
                assert mode & stat.S_IXUSR, (
                    f"scripts/{script_name} is not executable (user execute bit missing)"
                )

    async def test_ci_workflow_valid_yaml(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify the GitHub Actions CI workflow is valid YAML."""
        project_path = await _parse_and_scaffold(sample_requirements, tmp_path)

        ci_path = project_path / ".github" / "workflows" / "ci.yml"
        assert ci_path.exists(), "Missing .github/workflows/ci.yml"

        content = ci_path.read_text(encoding="utf-8")
        assert content.strip(), "ci.yml is empty"

        parsed = yaml.safe_load(content)
        assert parsed is not None, "ci.yml parsed to None"
        assert isinstance(parsed, dict), "ci.yml is not a YAML mapping"

        # A valid GitHub Actions workflow should have 'name' or 'on' keys
        assert "name" in parsed or "on" in parsed, (
            "ci.yml missing 'name' or 'on' key -- not a valid GitHub Actions workflow"
        )
