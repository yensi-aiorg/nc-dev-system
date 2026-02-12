"""Unit tests for pipeline orchestrator (src.pipeline).

Tests cover:
- PipelineError exception
- _infer_project_name from markdown headings
- _generate_build_prompt for Codex builders
- Pipeline.__init__ and state initialization
- Pipeline._save_state / _load_state persistence
- Pipeline.phase1_understand (parse requirements)
- Pipeline.phase2_scaffold (scaffold project)
- Pipeline.run phase selection (only selected phases)
- Pipeline.run error handling (phase fails gracefully)
- Pipeline._require_artefact (missing / corrupt files)
- Pipeline._print_final_summary output
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Config
from src.pipeline import (
    Pipeline,
    PipelineError,
    _generate_build_prompt,
    _infer_project_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path, phases: list[int] | None = None) -> Config:
    """Create a Config pointing at tmp_path with sensible test defaults."""
    return Config(
        output_dir=tmp_path,
        phases=phases or [1, 2, 3, 4, 5, 6],
        project_name="test-project",
    )


def _make_requirements_file(tmp_path: Path, content: str = "# My Project\n\nBuild a task app.") -> Path:
    req = tmp_path / "requirements.md"
    req.write_text(content)
    return req


# ---------------------------------------------------------------------------
# PipelineError
# ---------------------------------------------------------------------------

class TestPipelineError:
    @pytest.mark.unit
    def test_includes_phase_number(self):
        err = PipelineError(1, "Requirements file not found")
        assert err.phase == 1
        assert "Phase 1" in str(err)
        assert "Requirements file not found" in str(err)

    @pytest.mark.unit
    def test_includes_phase_name(self):
        err = PipelineError(3, "Build failed")
        assert "Phase 3" in str(err)


# ---------------------------------------------------------------------------
# _infer_project_name
# ---------------------------------------------------------------------------

class TestInferProjectName:
    @pytest.mark.unit
    def test_from_h1_heading(self):
        text = "# Task Management App\n\nBuild a task app."
        assert _infer_project_name(text) == "task-management-app"

    @pytest.mark.unit
    def test_from_h2_heading(self):
        text = "## My Cool Project\n\nStuff."
        assert _infer_project_name(text) == "my-cool-project"

    @pytest.mark.unit
    def test_special_chars_stripped(self):
        text = "# My App: (v2.0) Edition!\nDescription."
        result = _infer_project_name(text)
        assert ":" not in result
        assert "(" not in result
        assert "!" not in result

    @pytest.mark.unit
    def test_no_heading_returns_default(self):
        text = "Build a task management system."
        assert _infer_project_name(text) == "nc-dev-project"

    @pytest.mark.unit
    def test_empty_string(self):
        assert _infer_project_name("") == "nc-dev-project"


# ---------------------------------------------------------------------------
# _generate_build_prompt
# ---------------------------------------------------------------------------

class TestGenerateBuildPrompt:
    @pytest.mark.unit
    def test_includes_feature_name(self, tmp_path: Path):
        config = _make_config(tmp_path)
        feature = {"name": "Task CRUD", "description": "CRUD for tasks"}
        prompt = _generate_build_prompt(feature, config)

        assert "Task CRUD" in prompt
        assert "CRUD for tasks" in prompt

    @pytest.mark.unit
    def test_includes_technical_requirements(self, tmp_path: Path):
        config = _make_config(tmp_path)
        feature = {"name": "test"}
        prompt = _generate_build_prompt(feature, config)

        assert "FastAPI" in prompt
        assert "MongoDB" in prompt
        assert "React 19" in prompt
        assert "Zustand" in prompt

    @pytest.mark.unit
    def test_includes_port_allocations(self, tmp_path: Path):
        config = _make_config(tmp_path)
        feature = {"name": "test"}
        prompt = _generate_build_prompt(feature, config)

        assert "23001" in prompt  # backend port
        assert "23000" in prompt  # frontend port
        assert "23002" in prompt  # mongodb port

    @pytest.mark.unit
    def test_includes_api_endpoints(self, tmp_path: Path):
        config = _make_config(tmp_path)
        feature = {
            "name": "tasks",
            "api_endpoints": [
                {"method": "GET", "path": "/api/v1/tasks", "description": "List tasks"},
            ],
        }
        prompt = _generate_build_prompt(feature, config)
        assert "GET /api/v1/tasks" in prompt

    @pytest.mark.unit
    def test_includes_acceptance_criteria(self, tmp_path: Path):
        config = _make_config(tmp_path)
        feature = {
            "name": "auth",
            "acceptance_criteria": ["User can register", "User can login"],
        }
        prompt = _generate_build_prompt(feature, config)
        assert "User can register" in prompt
        assert "User can login" in prompt

    @pytest.mark.unit
    def test_includes_ui_routes(self, tmp_path: Path):
        config = _make_config(tmp_path)
        feature = {
            "name": "tasks",
            "ui_routes": [
                {"path": "/tasks", "name": "Task list", "description": "Main task view"},
            ],
        }
        prompt = _generate_build_prompt(feature, config)
        assert "/tasks" in prompt
        assert "Task list" in prompt

    @pytest.mark.unit
    def test_no_description_fallback(self, tmp_path: Path):
        config = _make_config(tmp_path)
        feature = {"name": "test"}
        prompt = _generate_build_prompt(feature, config)
        assert "No description provided" in prompt


# ---------------------------------------------------------------------------
# Pipeline.__init__
# ---------------------------------------------------------------------------

class TestPipelineInit:
    @pytest.mark.unit
    def test_initial_state(self, tmp_path: Path):
        config = _make_config(tmp_path)
        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        assert pipeline.config == config
        assert pipeline.state["phases_completed"] == []
        assert pipeline.state["phases_failed"] == []
        assert pipeline.state["success"] is False
        assert "started_at" in pipeline.state


# ---------------------------------------------------------------------------
# Pipeline._save_state / _load_state
# ---------------------------------------------------------------------------

class TestPipelineStatePersistence:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_and_load_state(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        pipeline.state["phases_completed"] = [1, 2]
        pipeline.state["custom_key"] = "custom_value"

        await pipeline._save_state()
        assert config.state_path.exists()

        # Load into a new pipeline
        with patch("src.pipeline.OllamaClient"):
            pipeline2 = Pipeline(config)

        await pipeline2._load_state()
        assert pipeline2.state["phases_completed"] == [1, 2]
        assert pipeline2.state["custom_key"] == "custom_value"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_missing_state_no_error(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        # Should not raise even if state file does not exist
        await pipeline._load_state()
        assert pipeline.state["success"] is False


# ---------------------------------------------------------------------------
# Pipeline.phase1_understand
# ---------------------------------------------------------------------------

class TestPipelinePhase1:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_requirements_success(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path, "# Task App\n\nBuild a task management app.")

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        # Prevent attempting the real parser import
        with patch.dict("sys.modules", {"src.parser.models": None, "src.parser": None}):
            result = await pipeline.phase1_understand(str(req_file))

        assert result["project_name"] is not None
        assert result["features_count"] == 0  # No parser => no features
        assert config.architecture_path.exists() or "architecture_path" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_requirements_file_raises(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with pytest.raises(PipelineError, match="not found"):
            await pipeline.phase1_understand(str(tmp_path / "missing.md"))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_requirements_file_raises(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        empty_file = tmp_path / "empty.md"
        empty_file.write_text("")

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with pytest.raises(PipelineError, match="empty"):
            await pipeline.phase1_understand(str(empty_file))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_infers_project_name_from_heading(self, tmp_path: Path):
        config = Config(output_dir=tmp_path, phases=[1])
        config.ensure_directories()

        req = _make_requirements_file(tmp_path, "# My Awesome App\n\nDesc.")

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.dict("sys.modules", {"src.parser.models": None, "src.parser": None}):
            result = await pipeline.phase1_understand(str(req))

        assert "my-awesome-app" in result["project_name"]


# ---------------------------------------------------------------------------
# Pipeline.phase2_scaffold
# ---------------------------------------------------------------------------

class TestPipelinePhase2:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_scaffold_creates_directories(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        # Write architecture artefact from phase 1
        arch = {"project_name": "test-project", "port_allocation": {}}
        config.architecture_path.parent.mkdir(parents=True, exist_ok=True)
        config.architecture_path.write_text(json.dumps(arch))

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        result = await pipeline.phase2_scaffold()

        assert result["project_name"] == "test-project"
        assert "output_dir" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_scaffold_missing_architecture_raises(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with pytest.raises(PipelineError, match="Required artefact missing"):
            await pipeline.phase2_scaffold()


# ---------------------------------------------------------------------------
# Pipeline.run (phase selection)
# ---------------------------------------------------------------------------

class TestPipelineRun:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_runs_only_selected_phases(self, tmp_path: Path):
        config = _make_config(tmp_path, phases=[1])
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(pipeline, "_preflight", new=AsyncMock()):
            with patch.object(pipeline, "phase1_understand", new=AsyncMock(return_value={"features_count": 0, "project_name": "test"})):
                result = await pipeline.run(str(req_file))

        assert 1 in result["phases_completed"]
        assert 2 not in result.get("phases_completed", [])

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase_failure_stops_pipeline(self, tmp_path: Path):
        config = _make_config(tmp_path, phases=[1, 2])
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(pipeline, "_preflight", new=AsyncMock()):
            with patch.object(pipeline, "phase1_understand", new=AsyncMock(side_effect=PipelineError(1, "Parse failed"))):
                result = await pipeline.run(str(req_file))

        assert result["success"] is False
        assert 1 in result["phases_failed"]
        assert 2 not in result.get("phases_completed", [])

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unexpected_exception_stops_pipeline(self, tmp_path: Path):
        config = _make_config(tmp_path, phases=[1, 2])
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(pipeline, "_preflight", new=AsyncMock()):
            with patch.object(pipeline, "phase1_understand", new=AsyncMock(side_effect=RuntimeError("boom"))):
                result = await pipeline.run(str(req_file))

        assert result["success"] is False
        assert 1 in result["phases_failed"]
        assert "phase1_error" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_success_true_when_all_pass(self, tmp_path: Path):
        config = _make_config(tmp_path, phases=[1])
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(pipeline, "_preflight", new=AsyncMock()):
            with patch.object(pipeline, "phase1_understand", new=AsyncMock(return_value={"ok": True})):
                result = await pipeline.run(str(req_file))

        assert result["success"] is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_state_persisted_after_each_phase(self, tmp_path: Path):
        config = _make_config(tmp_path, phases=[1])
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path)

        save_calls = []

        async def _track_save():
            save_calls.append(True)
            # Write real state file for pipeline completion
            state_path = config.state_path
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({"saved": True}))

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(pipeline, "_preflight", new=AsyncMock()):
            with patch.object(pipeline, "phase1_understand", new=AsyncMock(return_value={"ok": True})):
                with patch.object(pipeline, "_save_state", side_effect=_track_save):
                    await pipeline.run(str(req_file))

        assert len(save_calls) >= 1  # At least once after phase + once at end

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unknown_phase_skipped(self, tmp_path: Path):
        config = _make_config(tmp_path, phases=[99])
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(pipeline, "_preflight", new=AsyncMock()):
            result = await pipeline.run(str(req_file))

        assert result["success"] is True
        assert result["phases_completed"] == []


# ---------------------------------------------------------------------------
# Pipeline._require_artefact
# ---------------------------------------------------------------------------

class TestRequireArtefact:
    @pytest.mark.unit
    def test_missing_file_raises(self, tmp_path: Path):
        config = _make_config(tmp_path)
        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with pytest.raises(PipelineError, match="Required artefact missing"):
            pipeline._require_artefact(tmp_path / "missing.json", "test artefact")

    @pytest.mark.unit
    def test_valid_json_loaded(self, tmp_path: Path):
        config = _make_config(tmp_path)
        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        data_file = tmp_path / "data.json"
        data_file.write_text(json.dumps({"key": "value"}))

        result = pipeline._require_artefact(data_file, "test data")
        assert result == {"key": "value"}

    @pytest.mark.unit
    def test_corrupt_json_raises(self, tmp_path: Path):
        config = _make_config(tmp_path)
        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json{{{")

        with pytest.raises(PipelineError, match="Failed to load"):
            pipeline._require_artefact(bad_file, "corrupt data")


# ---------------------------------------------------------------------------
# Pipeline._preflight
# ---------------------------------------------------------------------------

class TestPipelinePreflight:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_preflight_creates_directories(self, tmp_path: Path):
        config = _make_config(tmp_path)

        with patch("src.pipeline.OllamaClient") as MockOllama:
            mock_ollama = MockOllama.return_value
            mock_ollama.is_available = AsyncMock(return_value=False)
            pipeline = Pipeline(config)

        with patch("src.pipeline.check_ports_available", new=AsyncMock(return_value={23000: True, 23001: True})):
            await pipeline._preflight()

        assert config.nc_dev_path.exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_preflight_warns_busy_ports(self, tmp_path: Path):
        config = _make_config(tmp_path)

        with patch("src.pipeline.OllamaClient") as MockOllama:
            mock_ollama = MockOllama.return_value
            mock_ollama.is_available = AsyncMock(return_value=False)
            pipeline = Pipeline(config)

        busy = {p: False for p in config.ports.all_ports()}
        with patch("src.pipeline.check_ports_available", new=AsyncMock(return_value=busy)):
            # Should not raise, just print a warning
            await pipeline._preflight()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_preflight_ollama_available(self, tmp_path: Path):
        config = _make_config(tmp_path)

        with patch("src.pipeline.OllamaClient") as MockOllama:
            mock_ollama = MockOllama.return_value
            mock_ollama.is_available = AsyncMock(return_value=True)
            mock_ollama.list_models = AsyncMock(return_value=["qwen3:8b", "qwen3-coder:30b"])
            pipeline = Pipeline(config)

        with patch("src.pipeline.check_ports_available", new=AsyncMock(return_value={})):
            await pipeline._preflight()


# ---------------------------------------------------------------------------
# Pipeline._load_state with corrupt file
# ---------------------------------------------------------------------------

class TestPipelineLoadStateCorrupt:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_corrupt_state_starts_fresh(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        # Write corrupt state file
        config.state_path.write_text("not valid json{{{")

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        await pipeline._load_state()
        # Should silently recover; original state intact
        assert pipeline.state["success"] is False
        assert pipeline.state["phases_completed"] == []


# ---------------------------------------------------------------------------
# Pipeline.phase1_understand (additional edge cases)
# ---------------------------------------------------------------------------

class TestPipelinePhase1Additional:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase1_saves_raw_requirements(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        content = "# Test Project\n\nBuild something cool."
        req_file = _make_requirements_file(tmp_path, content)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.dict("sys.modules", {"src.parser.models": None, "src.parser": None}):
            await pipeline.phase1_understand(str(req_file))

        raw_path = config.nc_dev_path / "requirements.md"
        assert raw_path.exists()
        assert raw_path.read_text(encoding="utf-8") == content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase1_saves_config_snapshot(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.dict("sys.modules", {"src.parser.models": None, "src.parser": None}):
            await pipeline.phase1_understand(str(req_file))

        config_json_path = config.nc_dev_path / "config.json"
        assert config_json_path.exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase1_whitespace_only_raises(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        ws_file = tmp_path / "ws.md"
        ws_file.write_text("   \n\n  \t  ")

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with pytest.raises(PipelineError, match="empty"):
            await pipeline.phase1_understand(str(ws_file))


# ---------------------------------------------------------------------------
# Pipeline.phase2_scaffold (additional)
# ---------------------------------------------------------------------------

class TestPipelinePhase2Additional:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_scaffold_minimal_creates_dirs(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        result = await pipeline._scaffold_minimal("test-proj", {"project_name": "test-proj"})
        assert result["directories_created"] > 0
        assert (tmp_path / "backend" / "app" / "api" / "v1" / "endpoints").exists()
        assert (tmp_path / "frontend" / "src" / "stores").exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ensure_git_repo_existing_git(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        # Simulate existing .git dir
        (tmp_path / ".git").mkdir()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        result = await pipeline._ensure_git_repo()
        assert result is False  # Already exists, returns False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ensure_git_repo_creates_new(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch("src.pipeline.run_command", new=AsyncMock(return_value=(0, "", ""))):
            result = await pipeline._ensure_git_repo()

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ensure_git_repo_failure(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch("src.pipeline.run_command", new=AsyncMock(return_value=(1, "", "git init failed"))):
            result = await pipeline._ensure_git_repo()

        assert result is False


# ---------------------------------------------------------------------------
# Pipeline.phase3_build
# ---------------------------------------------------------------------------

class TestPipelinePhase3:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase3_no_features_skips(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        # Write empty features list
        config.features_path.parent.mkdir(parents=True, exist_ok=True)
        config.features_path.write_text("[]")

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        result = await pipeline.phase3_build()
        assert result["features_built"] == 0
        assert result["features_failed"] == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase3_missing_features_raises(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with pytest.raises(PipelineError, match="Required artefact missing"):
            await pipeline.phase3_build()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase3_builds_features(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        features = [
            {"name": "auth", "description": "Authentication"},
            {"name": "tasks", "description": "Task CRUD"},
        ]
        config.features_path.parent.mkdir(parents=True, exist_ok=True)
        config.features_path.write_text(json.dumps(features))

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(
            pipeline, "_build_single_feature",
            new=AsyncMock(return_value={"success": True, "feature": "test"})
        ):
            result = await pipeline.phase3_build()

        assert result["features_built"] == 2
        assert result["features_failed"] == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase3_counts_failures(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        features = [
            {"name": "auth", "description": "Authentication"},
            {"name": "tasks", "description": "Task CRUD"},
        ]
        config.features_path.parent.mkdir(parents=True, exist_ok=True)
        config.features_path.write_text(json.dumps(features))

        call_count = 0

        async def mock_build(feature):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"success": True, "feature": feature["name"]}
            return {"success": False, "feature": feature["name"], "error": "failed"}

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(pipeline, "_build_single_feature", side_effect=mock_build):
            result = await pipeline.phase3_build()

        assert result["features_built"] == 1
        assert result["features_failed"] == 1


# ---------------------------------------------------------------------------
# Pipeline.phase4_verify
# ---------------------------------------------------------------------------

class TestPipelinePhase4:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase4_all_pass_first_iteration(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(
            pipeline, "_run_tests",
            new=AsyncMock(return_value={"unit_passed": True, "e2e_passed": True})
        ), patch.object(
            pipeline, "_run_visual_verification",
            new=AsyncMock(return_value={"passed": True})
        ):
            result = await pipeline.phase4_verify()

        assert result["all_passed"] is True
        assert result["iterations"] == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase4_fails_max_iterations(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.build.max_fix_iterations = 1
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(
            pipeline, "_run_tests",
            new=AsyncMock(return_value={"unit_passed": False, "e2e_passed": True})
        ), patch.object(
            pipeline, "_run_visual_verification",
            new=AsyncMock(return_value={"passed": True})
        ), patch.object(
            pipeline, "_attempt_auto_fix",
            new=AsyncMock()
        ):
            result = await pipeline.phase4_verify()

        assert result["all_passed"] is False


# ---------------------------------------------------------------------------
# Pipeline.phase5_harden
# ---------------------------------------------------------------------------

class TestPipelinePhase5:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase5_basic_hardening(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        # Call _basic_hardening directly to test the fallback path
        result = await pipeline._basic_hardening()
        assert "issues_found" in result
        assert "issues_fixed" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase5_detects_missing_env_example(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        result = await pipeline._basic_hardening()
        # No .env.example should be detected as issue
        issue_types = [i["type"] for i in result.get("issues", [])]
        assert "missing_env_example" in issue_types

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase5_detects_missing_health_endpoint(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        # Create backend dir but no health.py
        (tmp_path / "backend" / "app" / "api" / "v1" / "endpoints").mkdir(parents=True)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        result = await pipeline._basic_hardening()
        issue_types = [i["type"] for i in result.get("issues", [])]
        assert "missing_health_endpoint" in issue_types


# ---------------------------------------------------------------------------
# Pipeline.phase6_deliver
# ---------------------------------------------------------------------------

class TestPipelinePhase6:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase6_basic_delivery(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        pipeline.state["phases_completed"] = [1, 2]
        pipeline.state["phases_failed"] = []

        # Call _basic_delivery directly to avoid DeliveryEngine import issues
        result = await pipeline._basic_delivery()
        assert "build_report" in result
        assert "docs_count" in result
        assert config.build_report_path.exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase6_basic_delivery_report_content(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        pipeline.state["phases_completed"] = [1, 2, 3]
        pipeline.state["phases_failed"] = [4]
        pipeline.state["phase4_error"] = "Tests failed"

        result = await pipeline._basic_delivery()
        report_text = config.build_report_path.read_text(encoding="utf-8")
        assert "PASSED" in report_text
        assert "FAILED" in report_text

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase6_counts_screenshots(self, tmp_path: Path):
        config = _make_config(tmp_path)
        config.ensure_directories()

        # Create some fake screenshots
        screenshots = config.screenshots_dir
        screenshots.mkdir(parents=True, exist_ok=True)
        (screenshots / "login-desktop.png").write_text("fake")
        (screenshots / "login-mobile.png").write_text("fake")

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        result = await pipeline._basic_delivery()
        assert result["screenshots_count"] == 2


# ---------------------------------------------------------------------------
# Pipeline._print_final_summary
# ---------------------------------------------------------------------------

class TestPrintFinalSummary:
    @pytest.mark.unit
    def test_success_summary(self, tmp_path: Path):
        config = _make_config(tmp_path)
        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        pipeline.state["success"] = True
        pipeline.state["phases_completed"] = [1, 2, 3]
        pipeline.state["phases_failed"] = []
        # Should not raise
        pipeline._print_final_summary(42.5)

    @pytest.mark.unit
    def test_failure_summary(self, tmp_path: Path):
        config = _make_config(tmp_path)
        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        pipeline.state["success"] = False
        pipeline.state["phases_completed"] = [1]
        pipeline.state["phases_failed"] = [2]
        # Should not raise
        pipeline._print_final_summary(100.0)


# ---------------------------------------------------------------------------
# Pipeline.run multi-phase
# ---------------------------------------------------------------------------

class TestPipelineRunMultiPhase:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_phases_sequential(self, tmp_path: Path):
        config = _make_config(tmp_path, phases=[1, 2])
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(pipeline, "_preflight", new=AsyncMock()):
            with patch.object(
                pipeline, "phase1_understand",
                new=AsyncMock(return_value={"features_count": 0, "project_name": "test"})
            ):
                with patch.object(
                    pipeline, "phase2_scaffold",
                    new=AsyncMock(return_value={"project_name": "test"})
                ):
                    result = await pipeline.run(str(req_file))

        assert 1 in result["phases_completed"]
        assert 2 in result["phases_completed"]
        assert result["success"] is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_run_stores_requirements_path(self, tmp_path: Path):
        config = _make_config(tmp_path, phases=[1])
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(pipeline, "_preflight", new=AsyncMock()):
            with patch.object(pipeline, "phase1_understand", new=AsyncMock(return_value={"ok": True})):
                result = await pipeline.run(str(req_file))

        assert "requirements_path" in pipeline.state

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_run_records_total_duration(self, tmp_path: Path):
        config = _make_config(tmp_path, phases=[1])
        config.ensure_directories()

        req_file = _make_requirements_file(tmp_path)

        with patch("src.pipeline.OllamaClient"):
            pipeline = Pipeline(config)

        with patch.object(pipeline, "_preflight", new=AsyncMock()):
            with patch.object(pipeline, "phase1_understand", new=AsyncMock(return_value={"ok": True})):
                result = await pipeline.run(str(req_file))

        assert "total_duration" in result
        assert "finished_at" in result
