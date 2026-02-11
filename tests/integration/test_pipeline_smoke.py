"""Pipeline smoke tests for the NC Dev System.

These tests exercise the pipeline orchestrator (phases 1 and 2) using the
real parser and scaffolder modules against the sample requirements fixture.

External service dependencies (Ollama, Docker, databases) are mocked at the
boundary so the tests can run in any CI environment without infrastructure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_preflight():
    """Return a context manager that stubs out preflight checks.

    The Pipeline._preflight method probes ports and the Ollama server.
    Neither is available in CI, so we stub the method to a no-op.
    """
    async def _noop_preflight(self: Any) -> None:  # noqa: ANN001
        pass

    return patch("src.pipeline.Pipeline._preflight", _noop_preflight)


def _patch_git_init():
    """Stub out git init during scaffolding so the test does not depend on git."""
    async def _noop_git(self: Any) -> bool:  # noqa: ANN001
        return False

    return patch("src.pipeline.Pipeline._ensure_git_repo", _noop_git)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPipelineSmoke:
    """Test the pipeline orchestrator with phases 1-2."""

    async def test_pipeline_phases_1_2(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Run phases 1 and 2 and verify output artefacts."""
        from src.config import Config
        from src.pipeline import Pipeline

        config = Config(
            output_dir=tmp_path,
            phases=[1, 2],
        )
        pipeline = Pipeline(config)

        with _patch_preflight(), _patch_git_init():
            result = await pipeline.run(sample_requirements)

        # Pipeline should report success
        assert result.get("success") is True, (
            f"Pipeline did not succeed: {result}"
        )
        assert 1 in result.get("phases_completed", []), (
            "Phase 1 not in completed list"
        )
        assert 2 in result.get("phases_completed", []), (
            "Phase 2 not in completed list"
        )

        # Check .nc-dev artefacts created by phase 1
        nc_dev = tmp_path / ".nc-dev"
        assert nc_dev.is_dir(), "Missing .nc-dev directory"

        features_path = nc_dev / "features.json"
        assert features_path.exists(), "Missing .nc-dev/features.json"

        architecture_path = nc_dev / "architecture.json"
        assert architecture_path.exists(), "Missing .nc-dev/architecture.json"

        test_plan_path = nc_dev / "test-plan.json"
        assert test_plan_path.exists(), "Missing .nc-dev/test-plan.json"

        # Verify features.json content
        features_raw = features_path.read_text(encoding="utf-8")
        features = json.loads(features_raw)
        assert isinstance(features, list), (
            f"features.json should be a list, got {type(features).__name__}"
        )
        assert len(features) >= 4, (
            f"Expected at least 4 features, got {len(features)}"
        )

        # Verify each feature has required keys
        required_feature_keys = {"name", "priority", "complexity"}
        for feat in features:
            missing = required_feature_keys - set(feat.keys())
            assert not missing, (
                f"Feature '{feat.get('name', '?')}' missing keys: {missing}"
            )

        # Verify architecture.json content
        arch_raw = architecture_path.read_text(encoding="utf-8")
        arch = json.loads(arch_raw)
        assert isinstance(arch, dict), (
            f"architecture.json should be a dict, got {type(arch).__name__}"
        )
        assert "project_name" in arch, (
            "architecture.json missing 'project_name'"
        )
        assert arch.get("auth_required") is True, (
            "architecture.json should have auth_required=True for the "
            "sample requirements"
        )

        # Verify test-plan.json content
        tp_raw = test_plan_path.read_text(encoding="utf-8")
        tp = json.loads(tp_raw)
        assert isinstance(tp, dict), (
            f"test-plan.json should be a dict, got {type(tp).__name__}"
        )
        assert "scenarios" in tp, "test-plan.json missing 'scenarios'"
        assert len(tp["scenarios"]) >= 1, (
            "test-plan.json should contain at least one scenario"
        )

        # Verify raw requirements were saved
        raw_req_path = nc_dev / "requirements.md"
        assert raw_req_path.exists(), "Missing .nc-dev/requirements.md"

        # Verify config was saved
        config_json = nc_dev / "config.json"
        assert config_json.exists(), "Missing .nc-dev/config.json"

        # Verify pipeline state was saved
        state_path = nc_dev / "pipeline-state.json"
        assert state_path.exists(), "Missing .nc-dev/pipeline-state.json"

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state.get("success") is True, (
            "pipeline-state.json should show success=True"
        )

        # Verify phase 2 created scaffold-result.json
        scaffold_result_path = nc_dev / "scaffold-result.json"
        assert scaffold_result_path.exists(), (
            "Missing .nc-dev/scaffold-result.json (phase 2 artefact)"
        )

    async def test_pipeline_phase_1_only(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Run only phase 1 and verify parse output without scaffolding."""
        from src.config import Config
        from src.pipeline import Pipeline

        config = Config(
            output_dir=tmp_path,
            phases=[1],
        )
        pipeline = Pipeline(config)

        with _patch_preflight():
            result = await pipeline.run(sample_requirements)

        # Pipeline should succeed with just phase 1
        assert result.get("success") is True, (
            f"Pipeline phase 1 did not succeed: {result}"
        )
        assert 1 in result.get("phases_completed", [])
        assert 2 not in result.get("phases_completed", []), (
            "Phase 2 should not have run"
        )

        # Phase 1 artefacts should exist
        nc_dev = tmp_path / ".nc-dev"
        assert (nc_dev / "features.json").exists()
        assert (nc_dev / "architecture.json").exists()
        assert (nc_dev / "test-plan.json").exists()

        # Phase 1 result should have feature count
        phase1_result = result.get("phase1", {})
        assert phase1_result.get("features_count", 0) >= 4, (
            f"Expected at least 4 features in phase1 result, "
            f"got {phase1_result.get('features_count')}"
        )

        # Project name should have been auto-detected
        assert phase1_result.get("project_name"), (
            "Phase 1 did not auto-detect project name"
        )

    async def test_pipeline_auto_detects_project_name(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify the pipeline auto-detects the project name from the H1 header."""
        from src.config import Config
        from src.pipeline import Pipeline

        config = Config(
            output_dir=tmp_path,
            phases=[1],
        )
        pipeline = Pipeline(config)

        with _patch_preflight():
            result = await pipeline.run(sample_requirements)

        assert result.get("success") is True

        phase1 = result.get("phase1", {})
        project_name = phase1.get("project_name", "")
        # The sample requirements H1 is "Task Management App"
        assert project_name, "Project name was not auto-detected"
        assert "task" in project_name.lower(), (
            f"Project name '{project_name}' does not contain 'task' -- "
            f"expected auto-detection from the sample requirements H1"
        )

    async def test_pipeline_persists_state_between_phases(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify pipeline state is persisted after each phase."""
        from src.config import Config
        from src.pipeline import Pipeline

        config = Config(
            output_dir=tmp_path,
            phases=[1, 2],
        )
        pipeline = Pipeline(config)

        with _patch_preflight(), _patch_git_init():
            result = await pipeline.run(sample_requirements)

        state_path = tmp_path / ".nc-dev" / "pipeline-state.json"
        assert state_path.exists(), "Pipeline state file not found"

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert "started_at" in state, "State missing 'started_at'"
        assert "finished_at" in state, "State missing 'finished_at'"
        assert "total_duration" in state, "State missing 'total_duration'"
        assert state.get("success") is True

    async def test_pipeline_phase1_missing_file_raises(
        self, tmp_path: Path
    ) -> None:
        """Verify the pipeline raises an error for a nonexistent requirements file."""
        from src.config import Config
        from src.pipeline import Pipeline, PipelineError

        config = Config(
            output_dir=tmp_path,
            phases=[1],
        )
        pipeline = Pipeline(config)

        nonexistent = str(tmp_path / "does-not-exist.md")

        with _patch_preflight():
            result = await pipeline.run(nonexistent)

        # The pipeline catches errors and records failure
        assert result.get("success") is False, (
            "Pipeline should fail for missing requirements file"
        )
        assert 1 in result.get("phases_failed", []), (
            "Phase 1 should be in the failed list"
        )

    async def test_pipeline_scaffolded_project_structure(
        self, sample_requirements: str, tmp_path: Path
    ) -> None:
        """Verify phases 1+2 produce a complete project directory structure."""
        from src.config import Config
        from src.pipeline import Pipeline

        config = Config(
            output_dir=tmp_path,
            phases=[1, 2],
        )
        pipeline = Pipeline(config)

        with _patch_preflight(), _patch_git_init():
            result = await pipeline.run(sample_requirements)

        assert result.get("success") is True

        # The scaffolder creates a subdirectory named after the project
        # Determine the project name from the state
        phase1 = result.get("phase1", {})
        project_name = phase1.get("project_name", "")
        assert project_name, "Project name not detected"

        # The scaffold result should contain the project path
        phase2 = result.get("phase2", {})
        project_path_str = phase2.get("project_path", "")
        assert project_path_str, (
            "Phase 2 result missing 'project_path'"
        )

        project_path = Path(project_path_str)
        assert project_path.exists(), (
            f"Scaffolded project directory does not exist: {project_path}"
        )

        # Verify key files exist
        assert (project_path / "docker-compose.yml").exists()
        assert (project_path / "backend" / "requirements.txt").exists()
        assert (project_path / "frontend" / "package.json").exists()
        assert (project_path / "Makefile").exists()
        assert (project_path / "README.md").exists()

    async def test_pipeline_config_serialization_roundtrip(
        self, tmp_path: Path
    ) -> None:
        """Verify the Config can be saved and loaded correctly."""
        from src.config import Config

        config = Config(
            project_name="roundtrip-test",
            output_dir=tmp_path,
            phases=[1, 2],
        )

        # Ensure the .nc-dev directory exists for saving
        nc_dev_dir = tmp_path / ".nc-dev"
        nc_dev_dir.mkdir(parents=True, exist_ok=True)

        saved_path = config.save()
        assert saved_path.exists(), "Config file was not saved"

        loaded = Config.load(saved_path)
        assert loaded.project_name == "roundtrip-test"
        assert loaded.phases == [1, 2]
        assert loaded.ports.frontend == 23000
        assert loaded.ports.backend == 23001
        assert loaded.ports.mongodb == 23002
