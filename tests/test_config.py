"""Unit tests for Config and related Pydantic models (src.config).

Tests cover:
- PortConfig defaults, as_dict, all_ports, validation
- OllamaConfig defaults
- BuildConfig defaults
- Config defaults, derived paths (properties), save/load, from_env
- Config.ensure_directories
- Config phase control
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config import BuildConfig, Config, OllamaConfig, PortConfig


# ---------------------------------------------------------------------------
# PortConfig
# ---------------------------------------------------------------------------


class TestPortConfig:
    @pytest.mark.unit
    def test_default_ports(self):
        ports = PortConfig()
        assert ports.frontend == 23000
        assert ports.backend == 23001
        assert ports.mongodb == 23002
        assert ports.redis == 23003
        assert ports.keycloak == 23004
        assert ports.keycloak_postgres == 23005

    @pytest.mark.unit
    def test_as_dict(self):
        ports = PortConfig()
        d = ports.as_dict()
        assert isinstance(d, dict)
        assert d["frontend"] == 23000
        assert d["backend"] == 23001
        assert d["mongodb"] == 23002
        assert d["redis"] == 23003
        assert d["keycloak"] == 23004
        assert d["keycloak_postgres"] == 23005

    @pytest.mark.unit
    def test_all_ports(self):
        ports = PortConfig()
        all_p = ports.all_ports()
        assert len(all_p) == 6
        assert 23000 in all_p
        assert 23005 in all_p

    @pytest.mark.unit
    def test_custom_ports(self):
        ports = PortConfig(frontend=24000, backend=24001)
        assert ports.frontend == 24000
        assert ports.backend == 24001
        assert ports.mongodb == 23002  # Other ports stay default

    @pytest.mark.unit
    def test_port_below_23000_rejected(self):
        with pytest.raises(ValidationError):
            PortConfig(frontend=3000)

    @pytest.mark.unit
    def test_port_exactly_23000_accepted(self):
        ports = PortConfig(frontend=23000)
        assert ports.frontend == 23000

    @pytest.mark.unit
    def test_all_ports_returns_list(self):
        ports = PortConfig()
        result = ports.all_ports()
        assert isinstance(result, list)
        assert all(isinstance(p, int) for p in result)


# ---------------------------------------------------------------------------
# OllamaConfig
# ---------------------------------------------------------------------------


class TestOllamaConfig:
    @pytest.mark.unit
    def test_defaults(self):
        ollama = OllamaConfig()
        assert ollama.url == "http://localhost:11434"
        assert ollama.code_model == "qwen3-coder:30b"
        assert ollama.code_model_fallback == "qwen3-coder:30b"
        assert ollama.vision_model == "qwen2.5vl:7b"
        assert ollama.bulk_model == "qwen3:8b"
        assert ollama.timeout == 120

    @pytest.mark.unit
    def test_custom_values(self):
        ollama = OllamaConfig(url="http://my-ollama:11434", timeout=60)
        assert ollama.url == "http://my-ollama:11434"
        assert ollama.timeout == 60

    @pytest.mark.unit
    def test_timeout_below_minimum_rejected(self):
        with pytest.raises(ValidationError):
            OllamaConfig(timeout=5)

    @pytest.mark.unit
    def test_timeout_exactly_minimum_accepted(self):
        ollama = OllamaConfig(timeout=10)
        assert ollama.timeout == 10


# ---------------------------------------------------------------------------
# BuildConfig
# ---------------------------------------------------------------------------


class TestBuildConfig:
    @pytest.mark.unit
    def test_defaults(self):
        build = BuildConfig()
        assert build.max_codex_attempts == 2
        assert build.codex_timeout == 600
        assert build.max_parallel_builders == 3
        assert build.max_fix_iterations == 3

    @pytest.mark.unit
    def test_custom_values(self):
        build = BuildConfig(
            max_codex_attempts=5,
            codex_timeout=1200,
            max_parallel_builders=6,
            max_fix_iterations=10,
        )
        assert build.max_codex_attempts == 5
        assert build.codex_timeout == 1200
        assert build.max_parallel_builders == 6
        assert build.max_fix_iterations == 10

    @pytest.mark.unit
    def test_codex_attempts_minimum(self):
        with pytest.raises(ValidationError):
            BuildConfig(max_codex_attempts=0)

    @pytest.mark.unit
    def test_codex_timeout_minimum(self):
        with pytest.raises(ValidationError):
            BuildConfig(codex_timeout=30)


# ---------------------------------------------------------------------------
# Config - Defaults and basic properties
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    @pytest.mark.unit
    def test_default_values(self):
        config = Config()
        assert config.project_name == ""
        assert config.output_dir == Path("./output")
        assert config.nc_dev_dir == ".nc-dev"
        assert config.worktrees_dir == ".worktrees"
        assert config.phases == [1, 2, 3, 4, 5, 6]

    @pytest.mark.unit
    def test_custom_project_name(self):
        config = Config(project_name="my-app")
        assert config.project_name == "my-app"

    @pytest.mark.unit
    def test_nested_configs_default(self):
        config = Config()
        assert isinstance(config.ports, PortConfig)
        assert isinstance(config.ollama, OllamaConfig)
        assert isinstance(config.build, BuildConfig)


# ---------------------------------------------------------------------------
# Config - Derived paths (computed properties)
# ---------------------------------------------------------------------------


class TestConfigDerivedPaths:
    @pytest.mark.unit
    def test_nc_dev_path(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        assert config.nc_dev_path == tmp_path / ".nc-dev"

    @pytest.mark.unit
    def test_features_path(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        assert config.features_path == tmp_path / ".nc-dev" / "features.json"

    @pytest.mark.unit
    def test_architecture_path(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        assert config.architecture_path == tmp_path / ".nc-dev" / "architecture.json"

    @pytest.mark.unit
    def test_test_plan_path(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        assert config.test_plan_path == tmp_path / ".nc-dev" / "test-plan.json"

    @pytest.mark.unit
    def test_prompts_dir(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        assert config.prompts_dir == tmp_path / ".nc-dev" / "prompts"

    @pytest.mark.unit
    def test_results_dir(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        assert config.results_dir == tmp_path / ".nc-dev" / "codex-results"

    @pytest.mark.unit
    def test_screenshots_dir(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        assert config.screenshots_dir == tmp_path / "docs" / "screenshots"

    @pytest.mark.unit
    def test_worktrees_path(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        assert config.worktrees_path == tmp_path / ".worktrees"

    @pytest.mark.unit
    def test_state_path(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        assert config.state_path == tmp_path / ".nc-dev" / "pipeline-state.json"

    @pytest.mark.unit
    def test_build_report_path(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        assert config.build_report_path == tmp_path / "docs" / "build-report.md"

    @pytest.mark.unit
    def test_custom_nc_dev_dir(self, tmp_path: Path):
        config = Config(output_dir=tmp_path, nc_dev_dir=".custom-dev")
        assert config.nc_dev_path == tmp_path / ".custom-dev"
        assert config.features_path == tmp_path / ".custom-dev" / "features.json"


# ---------------------------------------------------------------------------
# Config.save / Config.load
# ---------------------------------------------------------------------------


class TestConfigSaveLoad:
    @pytest.mark.unit
    def test_save_default_path(self, tmp_path: Path):
        config = Config(output_dir=tmp_path, project_name="test-save")
        saved_path = config.save()
        assert saved_path.exists()
        assert saved_path == config.nc_dev_path / "config.json"

    @pytest.mark.unit
    def test_save_custom_path(self, tmp_path: Path):
        config = Config(output_dir=tmp_path, project_name="test-save")
        custom_path = tmp_path / "custom-config.json"
        saved_path = config.save(path=custom_path)
        assert saved_path == custom_path
        assert custom_path.exists()

    @pytest.mark.unit
    def test_load_roundtrip(self, tmp_path: Path):
        config = Config(
            output_dir=tmp_path,
            project_name="roundtrip-test",
            phases=[1, 2, 3],
        )
        config.ports = PortConfig(frontend=25000, backend=25001)
        config.ollama = OllamaConfig(timeout=60)
        config.build = BuildConfig(max_codex_attempts=4)

        saved_path = config.save()

        loaded = Config.load(saved_path)
        assert loaded.project_name == "roundtrip-test"
        assert loaded.phases == [1, 2, 3]
        assert loaded.ports.frontend == 25000
        assert loaded.ports.backend == 25001
        assert loaded.ollama.timeout == 60
        assert loaded.build.max_codex_attempts == 4

    @pytest.mark.unit
    def test_save_creates_parent_dirs(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        deep_path = tmp_path / "deep" / "nested" / "config.json"
        config.save(path=deep_path)
        assert deep_path.exists()


# ---------------------------------------------------------------------------
# Config.from_env
# ---------------------------------------------------------------------------


class TestConfigFromEnv:
    @pytest.mark.unit
    def test_defaults_when_no_env(self):
        env = {}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        assert config.project_name == ""
        assert config.output_dir == Path("./output")
        assert config.phases == [1, 2, 3, 4, 5, 6]

    @pytest.mark.unit
    def test_project_name_from_env(self):
        env = {"NC_PROJECT_NAME": "env-project"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        assert config.project_name == "env-project"

    @pytest.mark.unit
    def test_output_dir_from_env(self):
        env = {"NC_OUTPUT_DIR": "/custom/output"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        assert config.output_dir == Path("/custom/output")

    @pytest.mark.unit
    def test_phases_from_env(self):
        env = {"NC_PHASES": "1,3,5"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        assert config.phases == [1, 3, 5]

    @pytest.mark.unit
    def test_ollama_url_from_env(self):
        env = {"NC_OLLAMA_URL": "http://remote:11434"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        assert config.ollama.url == "http://remote:11434"

    @pytest.mark.unit
    def test_ollama_code_model_from_env(self):
        env = {"NC_OLLAMA_CODE_MODEL": "custom-model:7b"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        assert config.ollama.code_model == "custom-model:7b"

    @pytest.mark.unit
    def test_ollama_timeout_from_env(self):
        env = {"NC_OLLAMA_TIMEOUT": "60"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        assert config.ollama.timeout == 60

    @pytest.mark.unit
    def test_build_config_from_env(self):
        env = {
            "NC_MAX_CODEX_ATTEMPTS": "5",
            "NC_CODEX_TIMEOUT": "900",
            "NC_MAX_PARALLEL_BUILDERS": "6",
            "NC_MAX_FIX_ITERATIONS": "10",
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        assert config.build.max_codex_attempts == 5
        assert config.build.codex_timeout == 900
        assert config.build.max_parallel_builders == 6
        assert config.build.max_fix_iterations == 10


# ---------------------------------------------------------------------------
# Config.ensure_directories
# ---------------------------------------------------------------------------


class TestConfigEnsureDirectories:
    @pytest.mark.unit
    def test_creates_all_directories(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        config.ensure_directories()

        assert config.nc_dev_path.exists()
        assert config.prompts_dir.exists()
        assert config.results_dir.exists()
        assert config.screenshots_dir.exists()
        assert (config.output_dir / "docs").exists()

    @pytest.mark.unit
    def test_idempotent(self, tmp_path: Path):
        config = Config(output_dir=tmp_path)
        config.ensure_directories()
        config.ensure_directories()  # Should not raise
        assert config.nc_dev_path.exists()


# ---------------------------------------------------------------------------
# Config phase control
# ---------------------------------------------------------------------------


class TestConfigPhaseControl:
    @pytest.mark.unit
    def test_default_all_phases(self):
        config = Config()
        assert config.phases == [1, 2, 3, 4, 5, 6]

    @pytest.mark.unit
    def test_custom_phases(self):
        config = Config(phases=[1, 2])
        assert config.phases == [1, 2]

    @pytest.mark.unit
    def test_single_phase(self):
        config = Config(phases=[3])
        assert config.phases == [3]

    @pytest.mark.unit
    def test_empty_phases(self):
        config = Config(phases=[])
        assert config.phases == []


# ---------------------------------------------------------------------------
# Config model_dump_json
# ---------------------------------------------------------------------------


class TestConfigSerialization:
    @pytest.mark.unit
    def test_json_serialization(self, tmp_path: Path):
        config = Config(output_dir=tmp_path, project_name="serial-test")
        json_str = config.model_dump_json(indent=2)
        data = json.loads(json_str)

        assert data["project_name"] == "serial-test"
        assert "ports" in data
        assert "ollama" in data
        assert "build" in data
        assert data["ports"]["frontend"] == 23000
