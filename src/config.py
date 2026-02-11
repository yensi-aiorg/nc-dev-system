"""NC Dev System configuration.

Centralised, typed configuration for the entire pipeline. All settings use
Pydantic v2 models so they can be validated at construction time and serialised
to/from JSON or environment variables without boiler-plate.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PortConfig(BaseModel):
    """Port allocation for all services.

    All ports start at 23000 and are sequential. The default ports MUST never
    collide with common development ports (3000, 5000, 8000, 8080, 27017, 5432).
    """

    frontend: int = Field(default=23000, ge=23000)
    backend: int = Field(default=23001, ge=23000)
    mongodb: int = Field(default=23002, ge=23000)
    redis: int = Field(default=23003, ge=23000)
    keycloak: int = Field(default=23004, ge=23000)
    keycloak_postgres: int = Field(default=23005, ge=23000)

    def as_dict(self) -> dict[str, int]:
        """Return a plain ``{service: port}`` mapping."""
        return {
            "frontend": self.frontend,
            "backend": self.backend,
            "mongodb": self.mongodb,
            "redis": self.redis,
            "keycloak": self.keycloak,
            "keycloak_postgres": self.keycloak_postgres,
        }

    def all_ports(self) -> list[int]:
        """Return every allocated port as a flat list."""
        return list(self.as_dict().values())


class OllamaConfig(BaseModel):
    """Configuration for the local Ollama server."""

    url: str = Field(default="http://localhost:11434")
    code_model: str = Field(default="qwen2.5-coder:32b")
    code_model_fallback: str = Field(default="qwen2.5-coder:14b")
    vision_model: str = Field(default="qwen2.5vl:7b")
    bulk_model: str = Field(default="llama3.1:8b")
    timeout: int = Field(default=120, ge=10, description="Per-request timeout in seconds")


class BuildConfig(BaseModel):
    """Tuning knobs for the build pipeline."""

    max_codex_attempts: int = Field(
        default=2, ge=1, description="How many times to retry Codex before falling back to Sonnet"
    )
    codex_timeout: int = Field(default=600, ge=60, description="Codex process timeout in seconds")
    max_parallel_builders: int = Field(
        default=3, ge=1, description="Maximum concurrent Codex builders"
    )
    max_fix_iterations: int = Field(
        default=3, ge=1, description="Maximum fix-retest cycles in Phase 4"
    )


class Config(BaseModel):
    """Global NC Dev System configuration.

    Holds every tuneable parameter and derived path used by the pipeline.
    Instances are typically created once by ``Pipeline`` or by the CLI entry
    point and then passed through the rest of the system.
    """

    project_name: str = Field(default="")
    output_dir: Path = Field(default=Path("./output"))
    nc_dev_dir: str = Field(default=".nc-dev")
    worktrees_dir: str = Field(default=".worktrees")
    ports: PortConfig = Field(default_factory=PortConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    build: BuildConfig = Field(default_factory=BuildConfig)

    # Phase control — which pipeline phases to execute (1-6).
    phases: list[int] = Field(default=[1, 2, 3, 4, 5, 6])

    # ------------------------------------------------------------------
    # Derived paths (read-only properties)
    # ------------------------------------------------------------------

    @property
    def nc_dev_path(self) -> Path:
        """Root of the ``.nc-dev/`` metadata directory inside the output."""
        return self.output_dir / self.nc_dev_dir

    @property
    def features_path(self) -> Path:
        """Path to the extracted ``features.json``."""
        return self.nc_dev_path / "features.json"

    @property
    def architecture_path(self) -> Path:
        """Path to the generated ``architecture.json``."""
        return self.nc_dev_path / "architecture.json"

    @property
    def test_plan_path(self) -> Path:
        """Path to the generated ``test-plan.json``."""
        return self.nc_dev_path / "test-plan.json"

    @property
    def prompts_dir(self) -> Path:
        """Directory that stores per-feature build prompts."""
        return self.nc_dev_path / "prompts"

    @property
    def results_dir(self) -> Path:
        """Directory that stores Codex builder result files."""
        return self.nc_dev_path / "codex-results"

    @property
    def screenshots_dir(self) -> Path:
        """Directory for captured screenshots."""
        return self.output_dir / "docs" / "screenshots"

    @property
    def worktrees_path(self) -> Path:
        """Root directory for git worktrees."""
        return self.output_dir / self.worktrees_dir

    @property
    def state_path(self) -> Path:
        """Path to the persisted pipeline state JSON file."""
        return self.nc_dev_path / "pipeline-state.json"

    @property
    def build_report_path(self) -> Path:
        """Path to the final build report."""
        return self.output_dir / "docs" / "build-report.md"

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def save(self, path: Path | None = None) -> Path:
        """Persist the configuration to a JSON file.

        Args:
            path: Destination file. Defaults to ``<nc_dev_path>/config.json``.

        Returns:
            The resolved path where the file was written.
        """
        target = path or (self.nc_dev_path / "config.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: Path) -> "Config":
        """Load a previously-saved configuration from JSON.

        Args:
            path: The JSON file to read.

        Returns:
            A validated ``Config`` instance.
        """
        raw = Path(path).read_text(encoding="utf-8")
        return cls.model_validate_json(raw)

    @classmethod
    def from_env(cls) -> "Config":
        """Build a ``Config`` from environment variables.

        Recognised variables (all optional):
            NC_PROJECT_NAME, NC_OUTPUT_DIR, NC_PHASES,
            NC_OLLAMA_URL, NC_OLLAMA_CODE_MODEL, NC_OLLAMA_TIMEOUT,
            NC_MAX_CODEX_ATTEMPTS, NC_CODEX_TIMEOUT, NC_MAX_PARALLEL_BUILDERS,
            NC_MAX_FIX_ITERATIONS.
        """
        ollama_kwargs: dict[str, Any] = {}
        if os.environ.get("NC_OLLAMA_URL"):
            ollama_kwargs["url"] = os.environ["NC_OLLAMA_URL"]
        if os.environ.get("NC_OLLAMA_CODE_MODEL"):
            ollama_kwargs["code_model"] = os.environ["NC_OLLAMA_CODE_MODEL"]
        if os.environ.get("NC_OLLAMA_TIMEOUT"):
            ollama_kwargs["timeout"] = int(os.environ["NC_OLLAMA_TIMEOUT"])

        build_kwargs: dict[str, Any] = {}
        if os.environ.get("NC_MAX_CODEX_ATTEMPTS"):
            build_kwargs["max_codex_attempts"] = int(os.environ["NC_MAX_CODEX_ATTEMPTS"])
        if os.environ.get("NC_CODEX_TIMEOUT"):
            build_kwargs["codex_timeout"] = int(os.environ["NC_CODEX_TIMEOUT"])
        if os.environ.get("NC_MAX_PARALLEL_BUILDERS"):
            build_kwargs["max_parallel_builders"] = int(os.environ["NC_MAX_PARALLEL_BUILDERS"])
        if os.environ.get("NC_MAX_FIX_ITERATIONS"):
            build_kwargs["max_fix_iterations"] = int(os.environ["NC_MAX_FIX_ITERATIONS"])

        phases_str = os.environ.get("NC_PHASES", "1,2,3,4,5,6")
        phases = [int(p.strip()) for p in phases_str.split(",") if p.strip()]

        return cls(
            project_name=os.environ.get("NC_PROJECT_NAME", ""),
            output_dir=Path(os.environ.get("NC_OUTPUT_DIR", "./output")),
            ollama=OllamaConfig(**ollama_kwargs),
            build=BuildConfig(**build_kwargs),
            phases=phases,
        )

    def ensure_directories(self) -> None:
        """Create all derived directories that must exist before the pipeline runs."""
        for directory in (
            self.nc_dev_path,
            self.prompts_dir,
            self.results_dir,
            self.screenshots_dir,
            self.output_dir / "docs",
        ):
            directory.mkdir(parents=True, exist_ok=True)
