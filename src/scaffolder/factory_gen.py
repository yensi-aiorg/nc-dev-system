"""Test data factory generation for all database entities.

Generates:
- Python factory functions for backend pytest tests
- TypeScript factory functions for frontend Vitest tests

Factories produce valid, randomised documents/objects for each MongoDB
collection defined in the project's architecture.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class FactoryGenerator:
    """Generates test data factory functions for all database entities."""

    async def generate(
        self,
        output_dir: Path,
        db_collections: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[Path]:
        """Generate factory functions for all collections.

        Args:
            output_dir: Project root directory.
            db_collections: List of collection dicts with ``name`` and
                ``fields`` keys.  Each field has ``name``, ``type``,
                ``required``, and optionally ``default``.
            context: Template rendering context (for project_name, etc.).

        Returns:
            List of written file paths.
        """
        written: list[Path] = []

        # Python factories (for backend tests)
        py_path = await self._generate_python_factories(
            output_dir, db_collections, context
        )
        written.append(py_path)

        # TypeScript factories (for frontend tests)
        ts_path = await self._generate_typescript_factories(
            output_dir, db_collections, context
        )
        written.append(ts_path)

        return written

    # -- Python factories --------------------------------------------------

    async def _generate_python_factories(
        self,
        output_dir: Path,
        db_collections: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> Path:
        """Generate Python factory functions for backend tests.

        Writes to ``backend/tests/factories.py``.
        """
        content = _build_python_factories(db_collections, context)
        out = output_dir / "backend" / "tests" / "factories.py"
        await asyncio.to_thread(_write_file, out, content)
        return out

    # -- TypeScript factories ----------------------------------------------

    async def _generate_typescript_factories(
        self,
        output_dir: Path,
        db_collections: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> Path:
        """Generate TypeScript factory functions for frontend tests.

        Writes to ``frontend/tests/factories.ts``.
        """
        content = _build_typescript_factories(db_collections, context)
        out = output_dir / "frontend" / "tests" / "factories.ts"
        await asyncio.to_thread(_write_file, out, content)
        return out


# ---------------------------------------------------------------------------
# Python factory builder
# ---------------------------------------------------------------------------

def _build_python_factories(
    db_collections: list[dict[str, Any]],
    context: dict[str, Any],
) -> str:
    """Build the full ``factories.py`` content."""
    lines = [
        '"""Auto-generated test data factories.',
        "",
        "Each factory function returns a valid document dict for its collection,",
        "with optional overrides for any field.",
        '"""',
        "",
        "import random",
        "import string",
        "from datetime import datetime, timezone",
        "from typing import Any",
        "",
        "",
        "def _random_string(length: int = 10) -> str:",
        '    """Generate a random alphanumeric string."""',
        '    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))',
        "",
        "",
        "def _random_int(low: int = 1, high: int = 1000) -> int:",
        '    """Generate a random integer within a range."""',
        "    return random.randint(low, high)",
        "",
        "",
        "def _random_float(low: float = 0.0, high: float = 1000.0) -> float:",
        '    """Generate a random float within a range."""',
        "    return round(random.uniform(low, high), 2)",
        "",
        "",
        "def _utc_now() -> datetime:",
        '    """Return the current UTC datetime."""',
        "    return datetime.now(timezone.utc)",
        "",
    ]

    for collection in db_collections:
        coll_name = collection.get("name", "unknown")
        fields = collection.get("fields", [])
        func_name = f"make_{coll_name}"
        model_name = _to_pascal(coll_name)

        lines.append("")
        lines.append(f"def {func_name}(**overrides: Any) -> dict[str, Any]:")
        lines.append(f'    """Create a valid {model_name} document dict."""')
        lines.append(f"    data: dict[str, Any] = {{")

        if fields:
            for field in fields:
                fname = field.get("name", "field")
                ftype = field.get("type", "string")
                default_expr = _python_default_for_type(ftype, fname)
                lines.append(f'        "{fname}": {default_expr},')
        else:
            lines.append(f'        "name": f"Test {model_name} {{_random_string(6)}}",')
            lines.append(f'        "description": f"Auto-generated {coll_name} for testing",')

        lines.append(f'        "created_at": _utc_now(),')
        lines.append(f'        "updated_at": _utc_now(),')
        lines.append(f"    }}")
        lines.append(f"    data.update(overrides)")
        lines.append(f"    return data")
        lines.append("")

    # Batch factory
    lines.append("")
    lines.append("def make_batch(factory_fn, count: int = 5, **overrides: Any) -> list[dict[str, Any]]:")
    lines.append('    """Create a batch of documents using the given factory function."""')
    lines.append("    return [factory_fn(**overrides) for _ in range(count)]")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TypeScript factory builder
# ---------------------------------------------------------------------------

def _build_typescript_factories(
    db_collections: list[dict[str, Any]],
    context: dict[str, Any],
) -> str:
    """Build the full ``factories.ts`` content."""
    lines = [
        "/**",
        " * Auto-generated test data factories for frontend tests.",
        " *",
        " * Each factory returns a valid object matching the API response types.",
        " */",
        "",
        "let _counter = 0;",
        "function nextId(): string {",
        "  _counter += 1;",
        "  return `test-id-${_counter}`;",
        "}",
        "",
        "function randomString(length = 8): string {",
        "  return Math.random().toString(36).substring(2, 2 + length);",
        "}",
        "",
    ]

    for collection in db_collections:
        coll_name = collection.get("name", "unknown")
        fields = collection.get("fields", [])
        type_name = _to_pascal(coll_name)
        # Remove trailing 's' for singular if present
        singular = type_name.rstrip("s") if type_name.endswith("s") and len(type_name) > 1 else type_name

        lines.append(f"export function make{singular}(overrides: Partial<Record<string, unknown>> = {{}}) {{")
        lines.append(f"  return {{")
        lines.append(f"    id: nextId(),")

        if fields:
            for field in fields:
                fname = field.get("name", "field")
                ftype = field.get("type", "string")
                ts_default = _typescript_default_for_type(ftype, fname)
                lines.append(f"    {fname}: {ts_default},")
        else:
            lines.append(f"    name: `Test {singular} ${{randomString()}}`,")
            lines.append(f"    description: 'Auto-generated for testing',")

        lines.append(f"    created_at: new Date().toISOString(),")
        lines.append(f"    updated_at: new Date().toISOString(),")
        lines.append(f"    ...overrides,")
        lines.append(f"  }};")
        lines.append(f"}}")
        lines.append(f"")

    # Batch factory
    lines.append("export function makeBatch<T>(")
    lines.append("  factory: (overrides?: Partial<Record<string, unknown>>) => T,")
    lines.append("  count = 5,")
    lines.append("  overrides: Partial<Record<string, unknown>> = {},")
    lines.append("): T[] {")
    lines.append("  return Array.from({ length: count }, () => factory(overrides));")
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Type-to-default-value mapping
# ---------------------------------------------------------------------------

_PYTHON_TYPE_MAP: dict[str, str] = {
    "string": 'f"test-{_random_string()}"',
    "str": 'f"test-{_random_string()}"',
    "string (email)": 'f"user-{_random_string(5)}@test.example.com"',
    "string (password)": '"Test1234!"',
    "string (url)": '"https://example.com/test"',
    "integer": "_random_int()",
    "int": "_random_int()",
    "number": "_random_float()",
    "float": "_random_float()",
    "boolean": "True",
    "bool": "True",
    "datetime": "_utc_now()",
    "array": "[]",
    "list": "[]",
    "dict": "{}",
    "object": "{}",
}

_TS_TYPE_MAP: dict[str, str] = {
    "string": "`test-${randomString()}`",
    "str": "`test-${randomString()}`",
    "string (email)": "`user-${randomString(5)}@test.example.com`",
    "string (password)": "'Test1234!'",
    "string (url)": "'https://example.com/test'",
    "integer": "Math.floor(Math.random() * 1000) + 1",
    "int": "Math.floor(Math.random() * 1000) + 1",
    "number": "Math.round(Math.random() * 1000 * 100) / 100",
    "float": "Math.round(Math.random() * 1000 * 100) / 100",
    "boolean": "true",
    "bool": "true",
    "datetime": "new Date().toISOString()",
    "array": "[]",
    "list": "[]",
    "dict": "{}",
    "object": "{}",
}


def _python_default_for_type(type_str: str, field_name: str) -> str:
    """Return a Python expression that produces a sample value for *type_str*."""
    # Check for known field name patterns first
    lower_name = field_name.lower()
    if "email" in lower_name:
        return 'f"user-{_random_string(5)}@test.example.com"'
    if "password" in lower_name:
        return '"Test1234!"'
    if lower_name in ("url", "link", "image", "avatar"):
        return '"https://example.com/test"'
    if lower_name in ("price", "amount", "cost"):
        return "_random_float(1.0, 500.0)"
    if lower_name in ("quantity", "count"):
        return "_random_int(1, 100)"
    if "date" in lower_name or "time" in lower_name:
        return "_utc_now()"
    if "tag" in lower_name or "label" in lower_name:
        return '["tag-1", "tag-2"]'

    return _PYTHON_TYPE_MAP.get(type_str.lower(), f'f"test-{field_name}-{{_random_string()}}"')


def _typescript_default_for_type(type_str: str, field_name: str) -> str:
    """Return a TypeScript expression that produces a sample value for *type_str*."""
    lower_name = field_name.lower()
    if "email" in lower_name:
        return "`user-${randomString(5)}@test.example.com`"
    if "password" in lower_name:
        return "'Test1234!'"
    if lower_name in ("url", "link", "image", "avatar"):
        return "'https://example.com/test'"
    if lower_name in ("price", "amount", "cost"):
        return "Math.round(Math.random() * 500 * 100) / 100"
    if lower_name in ("quantity", "count"):
        return "Math.floor(Math.random() * 100) + 1"
    if "date" in lower_name or "time" in lower_name:
        return "new Date().toISOString()"
    if "tag" in lower_name or "label" in lower_name:
        return "['tag-1', 'tag-2']"

    return _TS_TYPE_MAP.get(type_str.lower(), f"`test-{field_name}-${{randomString()}}`")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_pascal(name: str) -> str:
    """Convert ``some_name`` or ``some-name`` to ``SomeName``."""
    import re

    parts = re.split(r"[-_\s]+", name)
    return "".join(word.capitalize() for word in parts if word)


def _write_file(path: Path, content: str) -> None:
    """Synchronous helper: create parent dirs and write content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
