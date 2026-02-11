"""Main scaffolding orchestrator.

Takes a ``ProjectConfig`` (or raw architecture dict) and generates a complete
project directory with React 19 + FastAPI + MongoDB + Docker, following the
mandatory structure defined in the NC Dev System specification.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .docker_gen import DockerGenerator
from .factory_gen import FactoryGenerator
from .mock_gen import MockGenerator
from .playwright_gen import PlaywrightGenerator
from .templates import TemplateRenderer


# ---------------------------------------------------------------------------
# Port allocation defaults (from CLAUDE.md)
# ---------------------------------------------------------------------------

DEFAULT_PORTS: dict[str, int] = {
    "frontend": 23000,
    "backend": 23001,
    "mongodb": 23002,
    "redis": 23003,
    "keycloak": 23004,
    "keycloak_postgres": 23005,
}


# ---------------------------------------------------------------------------
# Configuration model
# ---------------------------------------------------------------------------


class ProjectConfig(BaseModel):
    """Pydantic model describing the project to scaffold."""

    name: str = Field(..., description="Project name (used in filenames/package names)")
    description: str = Field(default="", description="Short project description")
    auth_required: bool = Field(default=False, description="Whether KeyCloak auth is needed")
    features: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Feature definitions with name, fields, and routes",
    )
    db_collections: list[dict[str, Any]] = Field(
        default_factory=list,
        description="MongoDB collection definitions with name, fields, and indexes",
    )
    api_contracts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="API contract definitions with name, path, and endpoints",
    )
    external_apis: list[dict[str, Any]] = Field(
        default_factory=list,
        description="External API dependencies with name, base_url, and endpoints",
    )
    ports: dict[str, int] = Field(
        default_factory=lambda: dict(DEFAULT_PORTS),
        description="Port allocation for each service",
    )


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


class ProjectGenerator:
    """Main scaffolding orchestrator.

    Given a ``ProjectConfig``, generates a complete directory tree containing:
    - React 19 frontend with Zustand, Axios, Tailwind, MSW mocks
    - FastAPI backend with Motor, Pydantic, service layer
    - Docker Compose files (dev, prod, test)
    - Playwright E2E tests and config
    - Pytest fixtures and test factories
    - CI/CD GitHub Actions workflow
    - Makefile, env files, README, and shell scripts
    """

    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self.renderer = TemplateRenderer()
        self.docker_gen = DockerGenerator(self.renderer)
        self.playwright_gen = PlaywrightGenerator(self.renderer)
        self.mock_gen = MockGenerator(self.renderer)
        self.factory_gen = FactoryGenerator()

    # -- Public API --------------------------------------------------------

    async def generate(self, output_dir: str | Path) -> Path:
        """Generate the complete project structure.

        Args:
            output_dir: Parent directory where the project folder will be
                created.  A subdirectory named after the project is created
                inside it.

        Returns:
            Path to the generated project root.
        """
        project_root = Path(output_dir) / self.config.name
        await asyncio.to_thread(project_root.mkdir, parents=True, exist_ok=True)

        context = self._build_context()

        # 1. Create the skeleton directory structure
        await self._create_directory_structure(project_root)

        # 2. Render backend templates (static files)
        await self._render_backend(project_root, context)

        # 3. Render per-feature backend files (endpoints, models, schemas, services, tests)
        await self._render_feature_backends(project_root, context)

        # 4. Render frontend templates (static files)
        await self._render_frontend(project_root, context)

        # 5. Render per-feature frontend files (stores, pages)
        await self._render_feature_frontends(project_root, context)

        # 6. Generate Docker Compose files
        await self.docker_gen.generate_all(project_root, context)
        await self.docker_gen.generate_backend_dockerfiles(
            project_root / "backend", context
        )
        await self.docker_gen.generate_frontend_dockerfiles(
            project_root / "frontend", context
        )

        # 7. Generate KeyCloak config (if auth required)
        if self.config.auth_required:
            await self.docker_gen.generate_keycloak(
                project_root / "keycloak", context
            )

        # 8. Generate Playwright config and E2E tests
        routes = self._collect_routes()
        await self.playwright_gen.generate(project_root, routes, context)

        # 9. Generate MSW handlers and pytest fixtures
        await self.mock_gen.generate_all(
            project_root,
            self.config.api_contracts,
            self.config.external_apis,
            context,
        )

        # 10. Generate test data factories
        await self.factory_gen.generate(
            project_root, self.config.db_collections, context
        )

        # 11. Generate shell scripts
        await self._render_scripts(project_root, context)

        # 12. Generate CI/CD config
        await self._render_ci(project_root, context)

        # 13. Generate Makefile
        await self.renderer.render_to_file(
            "Makefile.j2", project_root / "Makefile", context
        )

        # 14. Generate env files
        await self._render_env_files(project_root, context)

        # 15. Generate README
        await self.renderer.render_to_file(
            "README.md.j2", project_root / "README.md", context
        )

        return project_root

    async def generate_from_architecture(
        self, architecture: dict[str, Any], output_dir: str | Path
    ) -> Path:
        """Generate a project from an ``architecture.json`` dict.

        Extracts ``ProjectConfig`` fields from the architecture payload and
        delegates to :meth:`generate`.
        """
        config = _extract_config_from_architecture(architecture)
        self.config = config
        # Re-create sub-generators with new config context
        self.renderer = TemplateRenderer()
        self.docker_gen = DockerGenerator(self.renderer)
        self.playwright_gen = PlaywrightGenerator(self.renderer)
        self.mock_gen = MockGenerator(self.renderer)
        self.factory_gen = FactoryGenerator()
        return await self.generate(output_dir)

    # -- Context building --------------------------------------------------

    def _build_context(self) -> dict[str, Any]:
        """Build the Jinja2 template context from the project config."""
        slug = _slugify(self.config.name)
        enriched_features = [
            _enrich_feature(f, self.config.auth_required)
            for f in self.config.features
        ]
        enriched_collections = [
            _enrich_collection(c) for c in self.config.db_collections
        ]
        enriched_contracts = [
            _enrich_api_contract(c) for c in self.config.api_contracts
        ]

        return {
            "project_name": self.config.name,
            "project_name_slug": slug,
            "description": self.config.description,
            "auth_required": self.config.auth_required,
            "ports": self.config.ports,
            "features": enriched_features,
            "db_collections": enriched_collections,
            "api_contracts": enriched_contracts,
            "external_apis": self.config.external_apis,
        }

    # -- Directory structure -----------------------------------------------

    async def _create_directory_structure(self, root: Path) -> None:
        """Create the mandatory project directory tree."""
        dirs = [
            "backend/app/api/v1/endpoints",
            "backend/app/core",
            "backend/app/db/migrations",
            "backend/app/models",
            "backend/app/schemas",
            "backend/app/services",
            "backend/tests/unit/test_services",
            "backend/tests/integration/test_api",
            "backend/tests/e2e/test_workflows",
            "frontend/src/api",
            "frontend/src/components/ui",
            "frontend/src/components/layout",
            "frontend/src/components/features",
            "frontend/src/hooks",
            "frontend/src/mocks",
            "frontend/src/pages",
            "frontend/src/stores",
            "frontend/src/styles",
            "frontend/src/types",
            "frontend/src/utils",
            "frontend/e2e",
            "frontend/tests/unit",
            "frontend/tests/integration",
            "frontend/tests/e2e",
            "frontend/public",
            "scripts",
            "docs/screenshots",
            ".github/workflows",
        ]
        if self.config.auth_required:
            dirs.append("keycloak/themes")

        async def _mkdir(d: str) -> None:
            p = root / d
            p.mkdir(parents=True, exist_ok=True)

        await asyncio.gather(*[_mkdir(d) for d in dirs])

    # -- Backend rendering -------------------------------------------------

    async def _render_backend(self, root: Path, ctx: dict[str, Any]) -> None:
        """Render all static backend templates."""
        skip = [
            "feature_endpoint",
            "feature_model",
            "feature_schema",
            "feature_service",
            "test_feature",
        ]
        await self.renderer.render_tree(
            "backend", root / "backend", ctx, skip_patterns=skip
        )

    async def _render_feature_backends(
        self, root: Path, ctx: dict[str, Any]
    ) -> None:
        """Render per-feature backend files (endpoints, models, schemas, services, tests)."""
        features = ctx.get("features", [])
        for feature in features:
            feature_ctx = {**ctx, "feature": feature}
            slug = feature["name_slug"]

            # Endpoint
            await self.renderer.render_to_file(
                "backend/app/api/v1/endpoints/feature_endpoint.py.j2",
                root / "backend" / "app" / "api" / "v1" / "endpoints" / f"{slug}.py",
                feature_ctx,
            )

            # Model
            await self.renderer.render_to_file(
                "backend/app/models/feature_model.py.j2",
                root / "backend" / "app" / "models" / f"{slug}.py",
                feature_ctx,
            )

            # Schema
            await self.renderer.render_to_file(
                "backend/app/schemas/feature_schema.py.j2",
                root / "backend" / "app" / "schemas" / f"{slug}.py",
                feature_ctx,
            )

            # Service
            await self.renderer.render_to_file(
                "backend/app/services/feature_service.py.j2",
                root / "backend" / "app" / "services" / f"{slug}_service.py",
                feature_ctx,
            )

            # Unit tests
            await self.renderer.render_to_file(
                "backend/tests/unit/test_feature.py.j2",
                root / "backend" / "tests" / "unit" / f"test_{slug}.py",
                feature_ctx,
            )

    # -- Frontend rendering ------------------------------------------------

    async def _render_frontend(self, root: Path, ctx: dict[str, Any]) -> None:
        """Render all static frontend templates."""
        skip = ["FeaturePage", "featureStore"]
        await self.renderer.render_tree(
            "frontend", root / "frontend", ctx, skip_patterns=skip
        )

    async def _render_feature_frontends(
        self, root: Path, ctx: dict[str, Any]
    ) -> None:
        """Render per-feature frontend files (Zustand stores, pages)."""
        features = ctx.get("features", [])
        for feature in features:
            feature_ctx = {**ctx, "feature": feature}
            ts_type_name = feature["ts_type_name"]

            # Zustand store
            await self.renderer.render_to_file(
                "frontend/src/stores/featureStore.ts.j2",
                root / "frontend" / "src" / "stores" / f"use{ts_type_name}Store.ts",
                feature_ctx,
            )

            # Page component
            await self.renderer.render_to_file(
                "frontend/src/pages/FeaturePage.tsx.j2",
                root / "frontend" / "src" / "pages" / f"{ts_type_name}Page.tsx",
                feature_ctx,
            )

    # -- Scripts -----------------------------------------------------------

    async def _render_scripts(self, root: Path, ctx: dict[str, Any]) -> None:
        """Render shell scripts and set executable permissions."""
        scripts = [
            ("scripts/setup.sh.j2", "scripts/setup.sh"),
            ("scripts/seed-data.sh.j2", "scripts/seed-data.sh"),
            ("scripts/run-tests.sh.j2", "scripts/run-tests.sh"),
            ("scripts/validate-system.sh.j2", "scripts/validate-system.sh"),
        ]
        for template_name, output_name in scripts:
            out = root / output_name
            await self.renderer.render_to_file(template_name, out, ctx)
            # Set executable permission
            await asyncio.to_thread(_make_executable, out)

    # -- CI/CD -------------------------------------------------------------

    async def _render_ci(self, root: Path, ctx: dict[str, Any]) -> None:
        """Render GitHub Actions CI workflow."""
        await self.renderer.render_to_file(
            ".github/workflows/ci.yml.j2",
            root / ".github" / "workflows" / "ci.yml",
            ctx,
        )

    # -- Env files ---------------------------------------------------------

    async def _render_env_files(self, root: Path, ctx: dict[str, Any]) -> None:
        """Render .env.example, .env.development, and .env.test."""
        env_templates = [
            (".env.example.j2", ".env.example"),
            (".env.development.j2", ".env.development"),
            (".env.test.j2", ".env.test"),
        ]
        for template_name, output_name in env_templates:
            await self.renderer.render_to_file(
                template_name, root / output_name, ctx
            )

    # -- Route collection --------------------------------------------------

    def _collect_routes(self) -> list[dict[str, Any]]:
        """Collect all frontend routes from features for E2E generation."""
        routes: list[dict[str, Any]] = [{"path": "/", "name": "Home"}]
        for feature in self.config.features:
            name = feature.get("name", "")
            slug = _slugify(name)
            routes.append({"path": f"/{slug}", "name": name})
        if self.config.auth_required:
            routes.append({"path": "/login", "name": "Login"})
        return routes


# ---------------------------------------------------------------------------
# Architecture -> ProjectConfig extraction
# ---------------------------------------------------------------------------

def _extract_config_from_architecture(arch: dict[str, Any]) -> ProjectConfig:
    """Convert an ``architecture.json`` dict into a ``ProjectConfig``.

    Handles both the ``Architecture`` pydantic model dict format (from the
    parser module) and a simplified flat dict format.
    """
    name = arch.get("project_name", arch.get("name", "untitled-project"))
    description = arch.get("description", "")
    auth_required = arch.get("auth_required", False)

    # Ports
    ports = arch.get("port_allocation", arch.get("ports", dict(DEFAULT_PORTS)))

    # Features
    raw_features = arch.get("features", [])
    features = []
    for f in raw_features:
        if isinstance(f, dict):
            features.append(f)
        else:
            # Assume it's a pydantic model with model_dump
            features.append(f.model_dump() if hasattr(f, "model_dump") else dict(f))

    # DB collections
    raw_collections = arch.get("db_collections", [])
    db_collections = []
    for c in raw_collections:
        if isinstance(c, dict):
            db_collections.append(c)
        else:
            db_collections.append(c.model_dump() if hasattr(c, "model_dump") else dict(c))

    # API contracts
    raw_contracts = arch.get("api_contracts", [])
    api_contracts = []
    for c in raw_contracts:
        if isinstance(c, dict):
            api_contracts.append(c)
        else:
            api_contracts.append(c.model_dump() if hasattr(c, "model_dump") else dict(c))

    # External APIs
    raw_external = arch.get("external_apis", [])
    external_apis = []
    for e in raw_external:
        if isinstance(e, dict):
            external_apis.append(e)
        else:
            external_apis.append(e.model_dump() if hasattr(e, "model_dump") else dict(e))

    return ProjectConfig(
        name=name,
        description=description,
        auth_required=auth_required,
        features=features,
        db_collections=db_collections,
        api_contracts=api_contracts,
        external_apis=external_apis,
        ports=ports,
    )


# ---------------------------------------------------------------------------
# Feature / collection enrichment
# ---------------------------------------------------------------------------

_PYTHON_TYPE_MAP: dict[str, str] = {
    "str": "str",
    "string": "str",
    "string (email)": "str",
    "string (password)": "str",
    "string (url)": "str",
    "int": "int",
    "integer": "int",
    "float": "float",
    "number": "float",
    "bool": "bool",
    "boolean": "bool",
    "datetime": "datetime",
    "date": "datetime",
    "array": "list",
    "list": "list",
    "dict": "dict",
    "object": "dict",
}

_TS_TYPE_MAP: dict[str, str] = {
    "str": "string",
    "string": "string",
    "string (email)": "string",
    "string (password)": "string",
    "string (url)": "string",
    "int": "number",
    "integer": "number",
    "float": "number",
    "number": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "datetime": "string",
    "date": "string",
    "array": "string[]",
    "list": "string[]",
    "dict": "Record<string, unknown>",
    "object": "Record<string, unknown>",
}


def _enrich_feature(
    feature: dict[str, Any], auth_required: bool
) -> dict[str, Any]:
    """Enrich a feature dict with computed template variables.

    Adds ``name_slug``, ``model_name``, ``entity_plural``, ``ts_type_name``,
    ``display_name``, ``display_name_singular``, ``route_path``,
    ``sample_create_payload``, ``sample_create_keys``, and per-field
    ``python_type``/``default_value`` mappings.
    """
    name = feature.get("name", "Unknown")
    slug = _python_slugify(name)
    url_slug = _slugify(name)
    entity_plural = _infer_entity_plural(name)
    model_name = _to_pascal(name)
    ts_type_name = _to_pascal(name)

    # Singular display name
    singular = name
    if name.lower().endswith("s") and len(name) > 1:
        singular = name[:-1]

    # Enrich fields
    raw_fields = feature.get("fields", [])
    enriched_fields = []
    for field in raw_fields:
        field_type = field.get("type", "string")
        enriched_fields.append({
            **field,
            "python_type": _PYTHON_TYPE_MAP.get(field_type.lower(), "str"),
            "ts_type": _TS_TYPE_MAP.get(field_type.lower(), "string"),
            "default_value": _python_default_literal(field_type, field.get("default")),
        })

    # Build sample create payload for tests
    sample_payload = {}
    if enriched_fields:
        for f in enriched_fields:
            if f.get("required", True):
                sample_payload[f["name"]] = _sample_value_for_type(f.get("type", "string"), f["name"])
    else:
        sample_payload = {"name": f"Test {model_name}", "description": "Test description"}

    sample_keys = list(sample_payload.keys())

    return {
        **feature,
        "name_slug": slug,
        "url_slug": url_slug,
        "model_name": model_name,
        "ts_type_name": ts_type_name,
        "entity_plural": entity_plural,
        "display_name": name,
        "display_name_singular": singular,
        "route_path": f"/{url_slug}",
        "fields": enriched_fields,
        "sample_create_payload": repr(sample_payload),
        "sample_create_keys": sample_keys,
        "auth_required": auth_required,
    }


def _enrich_collection(collection: dict[str, Any]) -> dict[str, Any]:
    """Enrich a DB collection dict with computed template variables."""
    name = collection.get("name", "unknown")
    raw_fields = collection.get("fields", [])
    enriched_fields = []
    for field in raw_fields:
        ftype = field.get("type", "string")
        enriched_fields.append({
            **field,
            "python_type": _PYTHON_TYPE_MAP.get(ftype.lower(), "str"),
            "ts_type": _TS_TYPE_MAP.get(ftype.lower(), "string"),
            "default_value": _python_default_literal(ftype, field.get("default")),
            "seed_value": _mongo_seed_value(ftype, field.get("name", "field"), 1),
            "seed_value_alt": _mongo_seed_value(ftype, field.get("name", "field"), 2),
        })

    return {
        **collection,
        "fields": enriched_fields,
        "indexes": collection.get("indexes", []),
    }


def _enrich_api_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Enrich an API contract dict with computed template variables."""
    name = contract.get("name", contract.get("base_path", "/unknown").strip("/").split("/")[-1])
    path = contract.get("path", contract.get("base_path", f"/{name}").strip("/").split("v1/")[-1] if "v1/" in contract.get("base_path", "") else name)

    return {
        **contract,
        "name": name,
        "path": path,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert text to a URL/filename-safe slug (hyphenated)."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
    return slug.strip("-")


def _python_slugify(text: str) -> str:
    """Convert text to a Python-identifier-safe slug (underscored).

    E.g. ``'Task Management'`` -> ``'task_management'``.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower().strip())
    return slug.strip("_")


def _to_pascal(name: str) -> str:
    """Convert ``some-thing`` or ``some_thing`` to ``SomeThing``."""
    parts = re.split(r"[-_\s]+", name)
    return "".join(word.capitalize() for word in parts if word)


def _infer_entity_plural(feature_name: str) -> str:
    """Infer the plural entity name from a feature name.

    E.g. ``'Task CRUD'`` -> ``'tasks'``, ``'User Management'`` -> ``'users'``.
    """
    cleaned = re.sub(
        r"\b(crud|management|system|module|feature|dashboard|"
        r"authentication|authorization|settings|configuration)\b",
        "",
        feature_name,
        flags=re.IGNORECASE,
    ).strip()
    words = [w for w in cleaned.split() if len(w) > 1]
    if not words:
        words = feature_name.lower().split()[:1]
    entity = words[0].lower().rstrip("s")
    if entity.endswith("y") and not entity.endswith("ey"):
        return entity[:-1] + "ies"
    if entity.endswith(("s", "sh", "ch", "x", "z")):
        return entity + "es"
    return entity + "s"


def _python_default_literal(type_str: str, default: Any = None) -> str:
    """Return a Python default literal for a Pydantic Field."""
    if default is not None:
        return repr(default)
    return "None"


def _sample_value_for_type(type_str: str, field_name: str) -> Any:
    """Return a sample JSON-serializable value for use in test payloads."""
    lower = type_str.lower()
    fname = field_name.lower()
    if "email" in fname:
        return "test@example.com"
    if "password" in fname:
        return "TestPassword123!"
    if "url" in fname or "link" in fname or "image" in fname:
        return "https://example.com/test"
    if lower in ("int", "integer"):
        return 42
    if lower in ("float", "number"):
        return 99.99
    if lower in ("bool", "boolean"):
        return True
    if lower in ("datetime", "date"):
        return "2025-01-01T00:00:00Z"
    if lower in ("array", "list"):
        return ["item1", "item2"]
    return f"test-{field_name}"


def _mongo_seed_value(type_str: str, field_name: str, variant: int) -> str:
    """Return a JavaScript expression for MongoDB seed data."""
    lower = type_str.lower()
    fname = field_name.lower()
    suffix = str(variant)
    if "email" in fname:
        return f'"user{suffix}@example.com"'
    if "password" in fname:
        return f'"hashed_password_{suffix}"'
    if lower in ("int", "integer"):
        return str(variant * 10)
    if lower in ("float", "number"):
        return f"{variant * 10.5}"
    if lower in ("bool", "boolean"):
        return "true" if variant == 1 else "false"
    if lower in ("datetime", "date"):
        return "new Date()"
    if lower in ("array", "list"):
        return f'["tag-{suffix}a", "tag-{suffix}b"]'
    return f'"Sample {field_name} {suffix}"'


def _make_executable(path: Path) -> None:
    """Set the executable bit on a file."""
    import stat

    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
