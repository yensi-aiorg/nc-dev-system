"""Codex prompt generation for builder agents.

Generates comprehensive, structured prompts that Codex builders use to
implement features. Prompts include feature specs, architecture context,
API contracts, code conventions, and test requirements.
"""

import json
import textwrap
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

console = Console()

# Project conventions extracted from CLAUDE.md, embedded directly so prompt
# generation works without needing to re-parse the file at runtime.
_BACKEND_CONVENTIONS = textwrap.dedent("""\
    - Python 3.12+, FastAPI, Pydantic v2
    - Type hints on all function signatures
    - All API endpoints must have Pydantic v2 validation (schemas/ directory)
    - Use the BaseService pattern (ABC, Generic[T]) for all services
    - Use dependency injection via deps.py (get_db, get_current_active_user)
    - API endpoints under api/v1/endpoints/ with Annotated + Depends
    - Custom exceptions: AppException, NotFoundException, UnauthorizedException, ForbiddenException
    - Health endpoints: /health (basic) and /ready (with DB ping)
    - Structured JSON logging in production, human-readable in dev
    - Database indexes created on startup via db/indexes.py
    - Rate limiting via slowapi on sensitive endpoints
    - Graceful shutdown via FastAPI lifespan context manager
    - Security headers: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection
    """)

_FRONTEND_CONVENTIONS = textwrap.dedent("""\
    - React 19, TypeScript strict mode, no `any` types
    - Tailwind CSS for styling, no inline styles
    - Components NEVER call APIs directly - all API calls go through Zustand stores
    - Zustand stores use devtools middleware, manage isLoading/error state
    - HTTP client: Axios with interceptors (api/index.ts), NOT raw fetch
    - Types in src/types/, hooks in src/hooks/, utils in src/utils/
    - Components in src/components/ui/ (reusable), src/components/features/ (feature-specific)
    - Pages in src/pages/
    - State management: Zustand (MANDATORY), no Redux, no Context for server state
    """)

_MOCK_CONVENTIONS = textwrap.dedent("""\
    - Frontend: MSW (Mock Service Worker) intercepts Axios calls in browser
    - Backend: httpx MockTransport + pytest fixtures
    - Data: Factory functions for domain-specific test data
    - Environment: MOCK_APIS=true/false switches between mock and real APIs
    - Coverage: Every external API mocked with success, error, and empty responses
    """)

_PROHIBITED_PATTERNS = textwrap.dedent("""\
    - NO TODO comments
    - NO placeholder implementations (pass, return True)
    - NO "coming soon" or "not yet implemented" text
    - NO empty exception handlers (except: pass)
    - NO commented-out code blocks
    - NO hardcoded test data in production code
    - NO console.log debugging statements
    - NO disabled functionality
    """)


def _format_file_list(files: list[dict]) -> str:
    """Format a list of file dicts into a readable markdown list.

    Each dict should have 'path' and optionally 'action' (create/modify)
    and 'description'.
    """
    if not files:
        return "No specific files listed. Follow existing project structure."

    lines = []
    for f in files:
        path = f.get("path", "unknown")
        action = f.get("action", "create")
        desc = f.get("description", "")
        icon = "+" if action == "create" else "~"
        line = f"  {icon} `{path}`"
        if desc:
            line += f" - {desc}"
        lines.append(line)
    return "\n".join(lines)


def _format_api_contracts(contracts: list[dict]) -> str:
    """Format API contract specifications into readable markdown.

    Each dict should have 'method', 'path', 'description', and optionally
    'request_body', 'response', 'status_codes'.
    """
    if not contracts:
        return "No API contracts specified. Infer from feature description."

    sections = []
    for contract in contracts:
        method = contract.get("method", "GET").upper()
        path = contract.get("path", "/")
        desc = contract.get("description", "")
        lines = [f"### {method} {path}", ""]
        if desc:
            lines.append(desc)
            lines.append("")

        if "request_body" in contract:
            lines.append("**Request Body:**")
            lines.append("```json")
            lines.append(json.dumps(contract["request_body"], indent=2))
            lines.append("```")
            lines.append("")

        if "response" in contract:
            lines.append("**Response:**")
            lines.append("```json")
            lines.append(json.dumps(contract["response"], indent=2))
            lines.append("```")
            lines.append("")

        if "status_codes" in contract:
            lines.append("**Status Codes:**")
            for code, meaning in contract["status_codes"].items():
                lines.append(f"- `{code}`: {meaning}")
            lines.append("")

        sections.append("\n".join(lines))

    return "\n".join(sections)


def _format_db_models(models: list[dict]) -> str:
    """Format database model specifications.

    Each dict should have 'name', 'collection', and 'fields' (list of dicts
    with 'name', 'type', 'required', 'description').
    """
    if not models:
        return "No DB models specified. Infer from feature description."

    sections = []
    for model in models:
        name = model.get("name", "Unknown")
        collection = model.get("collection", name.lower() + "s")
        fields = model.get("fields", [])
        indexes = model.get("indexes", [])

        lines = [f"### {name} (collection: `{collection}`)", ""]
        lines.append("| Field | Type | Required | Description |")
        lines.append("|-------|------|----------|-------------|")

        for field in fields:
            fname = field.get("name", "")
            ftype = field.get("type", "str")
            freq = "Yes" if field.get("required", False) else "No"
            fdesc = field.get("description", "")
            lines.append(f"| {fname} | {ftype} | {freq} | {fdesc} |")

        lines.append("")

        if indexes:
            lines.append("**Indexes:**")
            for idx in indexes:
                idx_fields = idx.get("fields", [])
                unique = " (unique)" if idx.get("unique", False) else ""
                lines.append(f"- `{', '.join(idx_fields)}`{unique}")
            lines.append("")

        sections.append("\n".join(lines))

    return "\n".join(sections)


def _format_acceptance_criteria(criteria: list[str]) -> str:
    """Format acceptance criteria as a numbered list."""
    if not criteria:
        return "No specific acceptance criteria. Implement the full feature as described."

    return "\n".join(f"{i+1}. {c}" for i, c in enumerate(criteria))


def _format_test_requirements(tests: dict) -> str:
    """Format test requirement specifications.

    Expected keys: 'unit' (list), 'integration' (list), 'e2e' (list).
    """
    sections = []

    unit = tests.get("unit", [])
    if unit:
        sections.append("**Unit Tests (pytest / vitest):**")
        for t in unit:
            sections.append(f"- {t}")
        sections.append("")

    integration = tests.get("integration", [])
    if integration:
        sections.append("**Integration Tests:**")
        for t in integration:
            sections.append(f"- {t}")
        sections.append("")

    e2e = tests.get("e2e", [])
    if e2e:
        sections.append("**E2E Tests (Playwright):**")
        for t in e2e:
            sections.append(f"- {t}")
        sections.append("")

    if not sections:
        sections.append(
            "Write comprehensive unit tests for all new code (target 80%+ coverage).\n"
            "Write at least one Playwright E2E test covering the primary user journey."
        )

    return "\n".join(sections)


class PromptGenerator:
    """Generates detailed Codex builder prompts from feature specifications.

    Takes structured feature specs and architecture context, and produces
    comprehensive markdown prompts that Codex builders can execute to
    implement features with tests and proper conventions.
    """

    def __init__(self, project_name: str = "project"):
        self.project_name = project_name

    async def generate(
        self,
        feature: dict,
        architecture: dict,
        project_path: str,
    ) -> str:
        """Create a comprehensive Codex builder prompt.

        Args:
            feature: Feature specification dict with keys:
                - name (str): Feature name
                - description (str): What the feature does
                - acceptance_criteria (list[str]): Definition of done
                - files (list[dict]): Files to create/modify
                - api_contracts (list[dict]): API endpoints to implement
                - db_models (list[dict]): Database models to create
                - tests (dict): Test requirements (unit, integration, e2e)
                - dependencies (list[str]): Other features this depends on
            architecture: Architecture context dict with keys:
                - overview (str): System architecture summary
                - services (list[str]): List of services
                - patterns (dict): Design patterns in use
                - ports (dict): Port allocations
            project_path: Absolute path to the project being built.

        Returns:
            Complete prompt string in markdown format.
        """
        name = feature.get("name", "unnamed-feature")
        description = feature.get("description", "No description provided.")
        acceptance_criteria = feature.get("acceptance_criteria", [])
        files = feature.get("files", [])
        api_contracts = feature.get("api_contracts", [])
        db_models = feature.get("db_models", [])
        tests = feature.get("tests", {})
        dependencies = feature.get("dependencies", [])

        arch_overview = architecture.get("overview", "Standard NC Dev System stack.")
        arch_services = architecture.get("services", [])
        arch_ports = architecture.get("ports", {})

        # Build the dependency note
        dep_note = ""
        if dependencies:
            dep_list = ", ".join(f"`{d}`" for d in dependencies)
            dep_note = (
                f"\n> **Note:** This feature depends on: {dep_list}. "
                f"Assume these are already implemented.\n"
            )

        # Build port allocation table
        port_table = ""
        if arch_ports:
            port_lines = ["| Service | Port |", "|---------|------|"]
            for svc, port in arch_ports.items():
                port_lines.append(f"| {svc} | {port} |")
            port_table = "\n".join(port_lines)
        else:
            port_table = (
                "| Service | Port |\n"
                "|---------|------|\n"
                "| Frontend | 23000 |\n"
                "| Backend | 23001 |\n"
                "| MongoDB | 23002 |\n"
                "| Redis | 23003 |"
            )

        # Build services list
        services_text = ""
        if arch_services:
            services_text = "\n".join(f"- {s}" for s in arch_services)
        else:
            services_text = "- Frontend (React 19 + Vite)\n- Backend (FastAPI)\n- MongoDB\n- Redis"

        prompt = textwrap.dedent(f"""\
            # Builder Task: {name}

            You are a Codex builder for the NC Dev System. Implement the following
            feature completely with production-quality code and comprehensive tests.

            ## Feature Specification

            **Feature:** {name}

            **Description:**
            {description}
            {dep_note}
            ## Acceptance Criteria

            {_format_acceptance_criteria(acceptance_criteria)}

            ## Architecture Context

            {arch_overview}

            **Services:**
            {services_text}

            **Port Allocations:**
            {port_table}

            ## Files to Create/Modify

            Legend: `+` = create new, `~` = modify existing

            {_format_file_list(files)}

            ## API Contracts

            {_format_api_contracts(api_contracts)}

            ## Database Models

            {_format_db_models(db_models)}

            ## Project Conventions

            ### Backend (Python / FastAPI)
            {_BACKEND_CONVENTIONS}
            ### Frontend (React / TypeScript)
            {_FRONTEND_CONVENTIONS}
            ### Mocking Strategy
            {_MOCK_CONVENTIONS}
            ## Test Requirements

            {_format_test_requirements(tests)}

            ## Zustand Store Pattern (MANDATORY for frontend features)

            ```typescript
            import {{ create }} from 'zustand';
            import {{ devtools }} from 'zustand/middleware';
            import {{ api }} from '@/api';

            interface FeatureState {{
              items: Item[];
              isLoading: boolean;
              error: string | null;
              fetchItems: () => Promise<void>;
              createItem: (data: CreateItemDTO) => Promise<Item>;
            }}

            export const useFeatureStore = create<FeatureState>()(
              devtools((set) => ({{
                items: [],
                isLoading: false,
                error: null,
                fetchItems: async () => {{
                  set({{ isLoading: true, error: null }});
                  try {{
                    const response = await api.get<Item[]>('/items');
                    set({{ items: response.data, isLoading: false }});
                  }} catch (error) {{
                    set({{ error: 'Failed to fetch items', isLoading: false }});
                    throw error;
                  }}
                }},
              }}), {{ name: 'feature-store' }})
            );
            ```

            ## Backend Service Pattern (MANDATORY)

            ```python
            from abc import ABC
            from typing import Generic, TypeVar, Optional, List
            from motor.motor_asyncio import AsyncIOMotorCollection

            T = TypeVar("T")

            class BaseService(ABC, Generic[T]):
                def __init__(self, collection: AsyncIOMotorCollection):
                    self.collection = collection

                async def get_by_id(self, id: str) -> Optional[T]: ...
                async def get_all(self, skip: int = 0, limit: int = 100) -> List[T]: ...
                async def create(self, data: dict) -> T: ...
                async def update(self, id: str, data: dict) -> Optional[T]: ...
                async def delete(self, id: str) -> bool: ...
            ```

            ## Strictly Prohibited

            {_PROHIBITED_PATTERNS}
            ## Instructions

            1. Implement the feature code (backend + frontend as applicable)
            2. Write unit tests for all new modules (80%+ coverage target)
            3. Write at least one Playwright E2E test for the primary user flow
            4. Ensure `pytest tests/ -v` passes for backend
            5. Ensure `npm run test` passes for frontend
            6. Commit with message: `feat({name}): implementation with tests`

            Every file you create MUST be fully functional, linted, type-checked, and tested.
            """)

        console.print(
            f"[cyan]Generated prompt for[/cyan] [bold]{name}[/bold] "
            f"({len(prompt)} chars)"
        )

        return prompt

    async def save_prompt(
        self,
        feature_name: str,
        prompt: str,
        output_dir: str,
    ) -> Path:
        """Save a generated prompt to the .nc-dev/prompts/ directory.

        Creates the output directory structure if it doesn't exist.

        Args:
            feature_name: Feature name used in the filename.
            prompt: The prompt content to save.
            output_dir: Base project directory (prompt is saved under
                        .nc-dev/prompts/ relative to this).

        Returns:
            Path to the saved prompt file.
        """
        prompts_dir = Path(output_dir) / ".nc-dev" / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize feature name for filename
        safe_name = feature_name.strip().lower()
        safe_name = safe_name.replace(" ", "-")
        import re
        safe_name = re.sub(r"[^a-z0-9_-]", "-", safe_name)
        safe_name = re.sub(r"-+", "-", safe_name).strip("-")

        filename = f"build-{safe_name}.md"
        filepath = prompts_dir / filename

        filepath.write_text(prompt, encoding="utf-8")

        console.print(
            Panel(
                f"[green]Prompt saved[/green]\n"
                f"  Path: {filepath}\n"
                f"  Size: {len(prompt)} chars\n"
                f"  Feature: {feature_name}",
                title="Prompt Ready",
                border_style="green",
            )
        )

        return filepath

    async def generate_and_save(
        self,
        feature: dict,
        architecture: dict,
        project_path: str,
    ) -> tuple[str, Path]:
        """Generate a prompt and save it in one step.

        Convenience method that calls generate() then save_prompt().

        Args:
            feature: Feature specification dict.
            architecture: Architecture context dict.
            project_path: Absolute path to the project.

        Returns:
            Tuple of (prompt_content, saved_file_path).
        """
        name = feature.get("name", "unnamed-feature")
        prompt = await self.generate(feature, architecture, project_path)
        path = await self.save_prompt(name, prompt, project_path)
        return prompt, path
