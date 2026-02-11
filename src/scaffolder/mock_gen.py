"""MSW handler and pytest fixture generation.

Generates:
- ``frontend/src/mocks/handlers.ts``  -- MSW request handlers for all API endpoints
- ``frontend/src/mocks/browser.ts``   -- Browser MSW worker setup
- ``frontend/src/mocks/server.ts``    -- Node MSW server setup (for Vitest)
- ``backend/tests/conftest.py``       -- Pytest fixtures for backend tests

The generators use the existing Jinja2 templates where available and fall
back to programmatic content builders for dynamic per-feature fixtures.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .templates import TemplateRenderer


class MockGenerator:
    """Generates MSW handlers for frontend and pytest fixtures for backend."""

    def __init__(self, renderer: TemplateRenderer) -> None:
        self.renderer = renderer

    # -- Frontend MSW mocks ------------------------------------------------

    async def generate_msw_handlers(
        self,
        output_dir: Path,
        api_contracts: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[Path]:
        """Generate MSW request handlers for all API endpoints.

        Renders the handlers, browser worker, and server setup templates
        into ``frontend/src/mocks/``.

        Args:
            output_dir: Project root directory.
            api_contracts: List of API contract dicts with ``name``, ``path``,
                and optional ``fields`` keys.
            context: Template rendering context.

        Returns:
            List of written file paths.
        """
        msw_context = {**context, "api_contracts": api_contracts}
        mocks_dir = output_dir / "frontend" / "src" / "mocks"
        written: list[Path] = []

        for template_name, filename in (
            ("frontend/src/mocks/handlers.ts.j2", "handlers.ts"),
            ("frontend/src/mocks/browser.ts.j2", "browser.ts"),
            ("frontend/src/mocks/server.ts.j2", "server.ts"),
        ):
            path = await self.renderer.render_to_file(
                template_name, mocks_dir / filename, msw_context
            )
            written.append(path)

        return written

    # -- Backend pytest fixtures -------------------------------------------

    async def generate_pytest_fixtures(
        self,
        output_dir: Path,
        api_contracts: list[dict[str, Any]],
        external_apis: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[Path]:
        """Generate pytest fixtures for backend tests.

        Renders the main ``conftest.py`` from its template, then generates
        per-feature test fixtures for services that need mocked collections.

        Args:
            output_dir: Project root directory.
            api_contracts: List of API contract dicts.
            external_apis: List of external API dicts with ``name``,
                ``base_url``, and ``endpoints`` keys.
            context: Template rendering context.

        Returns:
            List of written file paths.
        """
        fixture_context = {
            **context,
            "api_contracts": api_contracts,
            "external_apis": external_apis,
        }
        written: list[Path] = []

        # Main conftest.py
        conftest_path = await self.renderer.render_to_file(
            "backend/tests/conftest.py.j2",
            output_dir / "backend" / "tests" / "conftest.py",
            fixture_context,
        )
        written.append(conftest_path)

        # Per-external-API mock fixtures
        if external_apis:
            ext_fixtures = _build_external_api_fixtures(external_apis)
            ext_path = output_dir / "backend" / "tests" / "external_mocks.py"
            await asyncio.to_thread(_write_file, ext_path, ext_fixtures)
            written.append(ext_path)

        return written

    # -- Combined generation -----------------------------------------------

    async def generate_all(
        self,
        output_dir: Path,
        api_contracts: list[dict[str, Any]],
        external_apis: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[Path]:
        """Generate both MSW handlers and pytest fixtures.

        Convenience method that calls :meth:`generate_msw_handlers` and
        :meth:`generate_pytest_fixtures` and returns all written paths.
        """
        msw_paths = await self.generate_msw_handlers(
            output_dir, api_contracts, context
        )
        pytest_paths = await self.generate_pytest_fixtures(
            output_dir, api_contracts, external_apis, context
        )
        return msw_paths + pytest_paths


# ---------------------------------------------------------------------------
# Content builders
# ---------------------------------------------------------------------------

def _build_external_api_fixtures(
    external_apis: list[dict[str, Any]],
) -> str:
    """Build pytest fixtures that mock external API calls using httpx.

    Each external API gets a fixture that patches ``httpx.AsyncClient`` to
    return predetermined responses for the documented endpoints.
    """
    lines = [
        '"""Auto-generated mock fixtures for external API dependencies."""',
        "",
        "from unittest.mock import AsyncMock, patch",
        "",
        "import httpx",
        "import pytest",
        "",
        "",
    ]

    for api in external_apis:
        name = api.get("name", "unknown")
        base_url = api.get("base_url", "https://api.example.com")
        fixture_name = _to_fixture_name(name)
        endpoints = api.get("endpoints", [])

        lines.append(f"@pytest.fixture")
        lines.append(f"def mock_{fixture_name}():")
        lines.append(f'    """Mock fixture for the {name} API ({base_url})."""')
        lines.append(f"    responses = {{")

        for ep in endpoints:
            path = ep.get("path", "/")
            method = ep.get("method", "GET").upper()
            status = ep.get("status", 200)
            body = ep.get("response_body", {"status": "ok"})
            lines.append(
                f'        ("{method}", "{path}"): '
                f"httpx.Response({status}, json={body!r}),"
            )

        if not endpoints:
            lines.append(
                f'        ("GET", "/"): httpx.Response(200, json={{"status": "ok"}}),'
            )

        lines.append(f"    }}")
        lines.append(f"")
        lines.append(f"    async def mock_request(method, url, **kwargs):")
        lines.append(f"        from urllib.parse import urlparse")
        lines.append(f"        parsed = urlparse(str(url))")
        lines.append(f"        key = (method.upper(), parsed.path)")
        lines.append(f"        if key in responses:")
        lines.append(f"            return responses[key]")
        lines.append(f'        return httpx.Response(404, json={{"detail": "Not mocked"}})')
        lines.append(f"")
        lines.append(f"    mock_client = AsyncMock(spec=httpx.AsyncClient)")
        lines.append(f"    mock_client.request = AsyncMock(side_effect=mock_request)")
        lines.append(f"    mock_client.get = AsyncMock(")
        lines.append(f'        side_effect=lambda url, **kw: mock_request("GET", url, **kw)')
        lines.append(f"    )")
        lines.append(f"    mock_client.post = AsyncMock(")
        lines.append(f'        side_effect=lambda url, **kw: mock_request("POST", url, **kw)')
        lines.append(f"    )")
        lines.append(f"    mock_client.put = AsyncMock(")
        lines.append(f'        side_effect=lambda url, **kw: mock_request("PUT", url, **kw)')
        lines.append(f"    )")
        lines.append(f"    mock_client.delete = AsyncMock(")
        lines.append(f'        side_effect=lambda url, **kw: mock_request("DELETE", url, **kw)')
        lines.append(f"    )")
        lines.append(f"    return mock_client")
        lines.append(f"")
        lines.append(f"")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_fixture_name(name: str) -> str:
    """Convert an API name like ``Stripe`` to a fixture name ``stripe``."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "_", name.lower().strip())
    return slug.strip("_")


def _write_file(path: Path, content: str) -> None:
    """Synchronous helper: create parent dirs and write content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
