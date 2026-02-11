"""NC Dev System scaffolder -- generates complete project structures.

This module takes an ``architecture.json`` (or a ``ProjectConfig``) as input
and renders a production-ready project directory with React 19 + FastAPI +
MongoDB + Docker, following the mandatory structure defined in CLAUDE.md.

Quick usage::

    from src.scaffolder import ProjectGenerator, ProjectConfig

    config = ProjectConfig(
        name="my-project",
        description="A sample project",
        features=[...],
        db_collections=[...],
    )
    generator = ProjectGenerator(config)
    project_path = await generator.generate("/tmp/output")
"""

from src.scaffolder.generator import ProjectConfig, ProjectGenerator
from src.scaffolder.templates import TemplateRenderer

__all__ = [
    "ProjectConfig",
    "ProjectGenerator",
    "TemplateRenderer",
]
