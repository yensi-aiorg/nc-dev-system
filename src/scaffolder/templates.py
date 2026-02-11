"""Jinja2 template rendering for project scaffolding.

Provides the TemplateRenderer class which loads Jinja2 templates from the
``src/scaffolder/templates/`` directory and renders them with project-specific
context data.  Supports single-file rendering, batch tree rendering, and
string-based rendering for inline template content.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


# ---------------------------------------------------------------------------
# Template directory discovery
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"


# ---------------------------------------------------------------------------
# TemplateRenderer
# ---------------------------------------------------------------------------


class TemplateRenderer:
    """Renders Jinja2 templates for project scaffolding.

    The renderer discovers ``.j2`` template files under a configurable
    template directory.  Templates are rendered with a context dictionary that
    typically contains project metadata (name, ports, features, etc.).
    """

    def __init__(self, template_dir: str | Path | None = None) -> None:
        if template_dir is None:
            template_dir = _DEFAULT_TEMPLATE_DIR
        self.template_dir = Path(template_dir)
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape([]),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Register custom filters
        self.env.filters["slugify"] = _slugify_filter
        self.env.filters["pascal_case"] = _pascal_case_filter
        self.env.filters["snake_case"] = _snake_case_filter
        self.env.filters["camel_case"] = _camel_case_filter

    # -- Single template rendering -----------------------------------------

    def render(self, template_path: str, context: dict[str, Any]) -> str:
        """Render a single template with the provided context.

        Args:
            template_path: Path relative to the template directory (e.g.
                ``"backend/app/main.py.j2"``).
            context: Dictionary of variables available inside the template.

        Returns:
            The rendered template content as a string.
        """
        template = self.env.get_template(template_path)
        return template.render(**context)

    def render_string(self, template_string: str, context: dict[str, Any]) -> str:
        """Render an inline template string with the provided context.

        Useful for rendering small template fragments that are not stored as
        files (e.g. dynamically constructed content).
        """
        template = self.env.from_string(template_string)
        return template.render(**context)

    # -- File-based rendering (async) --------------------------------------

    async def render_to_file(
        self,
        template_path: str,
        output_path: str | Path,
        context: dict[str, Any],
    ) -> Path:
        """Render a template and write the result to *output_path*.

        Parent directories are created automatically.  Returns the resolved
        output path.
        """
        content = self.render(template_path, context)
        out = Path(output_path)
        await asyncio.to_thread(_write_file, out, content)
        return out

    async def render_tree(
        self,
        template_prefix: str,
        output_dir: str | Path,
        context: dict[str, Any],
        *,
        skip_patterns: list[str] | None = None,
    ) -> list[Path]:
        """Render every ``*.j2`` file under *template_prefix* to *output_dir*.

        The directory structure is preserved: a template at
        ``backend/app/main.py.j2`` rendered with ``template_prefix="backend"``
        and ``output_dir="/tmp/project/backend"`` writes to
        ``/tmp/project/backend/app/main.py``.

        Args:
            template_prefix: Subdirectory inside the template root to scan.
            output_dir: Target directory where rendered files are written.
            context: Template context variables.
            skip_patterns: Optional list of filename substrings to skip
                (e.g. ``["feature_endpoint", "feature_model"]`` to skip
                per-feature templates that are rendered separately).

        Returns:
            List of written file paths.
        """
        skip_patterns = skip_patterns or []
        prefix_path = self.template_dir / template_prefix
        if not prefix_path.is_dir():
            return []

        written: list[Path] = []
        out_base = Path(output_dir)

        for template_file in sorted(prefix_path.rglob("*.j2")):
            rel = template_file.relative_to(prefix_path)
            rel_str = str(rel)

            # Skip templates that match any skip pattern
            if any(pat in rel_str for pat in skip_patterns):
                continue

            # Strip the .j2 extension for the output filename
            output_name = str(rel)[: -len(".j2")] if rel_str.endswith(".j2") else str(rel)
            output_file = out_base / output_name

            template_key = f"{template_prefix}/{rel_str}"
            path = await self.render_to_file(template_key, output_file, context)
            written.append(path)

        return written

    # -- Utility -----------------------------------------------------------

    def list_templates(self, prefix: str = "") -> list[str]:
        """Return a sorted list of all ``.j2`` template paths under *prefix*.

        Paths are relative to the template root directory.
        """
        search_dir = self.template_dir / prefix if prefix else self.template_dir
        if not search_dir.is_dir():
            return []
        return sorted(
            str(p.relative_to(self.template_dir))
            for p in search_dir.rglob("*.j2")
        )


# ---------------------------------------------------------------------------
# Jinja2 custom filters
# ---------------------------------------------------------------------------

def _slugify_filter(value: str) -> str:
    """Convert a string to a URL/filename-safe slug."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().strip())
    return slug.strip("-")


def _pascal_case_filter(value: str) -> str:
    """Convert ``some-thing`` or ``some_thing`` to ``SomeThing``."""
    import re

    parts = re.split(r"[-_\s]+", value)
    return "".join(word.capitalize() for word in parts if word)


def _snake_case_filter(value: str) -> str:
    """Convert ``SomeThing`` or ``some-thing`` to ``some_thing``."""
    import re

    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return re.sub(r"[-\s]+", "_", s2).lower()


def _camel_case_filter(value: str) -> str:
    """Convert ``some-thing`` or ``some_thing`` to ``someThing``."""
    pascal = _pascal_case_filter(value)
    if pascal:
        return pascal[0].lower() + pascal[1:]
    return ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_file(path: Path, content: str) -> None:
    """Synchronous helper: create parent dirs and write content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
