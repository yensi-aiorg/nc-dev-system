"""AI-governed project runbook for process decisions.

The runbook is the project-specific policy layer between the high-level
charter and deterministic Python execution. A model may author it from the
repo + contracts, but Python still validates the JSON and only executes
structured commands from the resulting artifact.
"""

from __future__ import annotations

import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ncdev.ai_session import run_ai_session
from ncdev.core.config import NCDevConfig
from ncdev.pipeline.models import CharterBundle

RUNBOOK_FILENAME = "project-runbook.json"


class TestCommandPolicy(BaseModel):
    """Project-specific test command policy for one workspace area."""

    root: str = ""
    test_command: str = ""
    single_test_command: str = ""
    prefer_project_venv: bool = False
    venv_must_have_pytest: bool = True
    notes: list[str] = Field(default_factory=list)


class ProjectRunbook(BaseModel):
    """Model-authored, schema-validated process policy for one target repo."""

    version: str = "1.0"
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: Literal["ai_model", "deterministic_fallback"] = "deterministic_fallback"
    project_name: str = ""
    backend: TestCommandPolicy = Field(default_factory=TestCommandPolicy)
    frontend: TestCommandPolicy = Field(default_factory=TestCommandPolicy)
    protected_files: list[str] = Field(default_factory=list)
    mandates: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def generate_project_runbook(
    *,
    target_path: Path,
    output_dir: Path,
    bundle: CharterBundle,
    config: NCDevConfig,
    model: str | None = None,
    max_budget_usd: float | None = None,
    log_path: Path | None = None,
) -> ProjectRunbook:
    """Create and persist the project runbook.

    When ``config.process_flow.ai_runbook_enabled`` is true, asks the
    configured model to produce the policy JSON. If that fails validation or
    the model is unavailable, writes a deterministic fallback derived from the
    verification contract. This keeps the pipeline moving while preserving a
    clear artifact trail.
    """

    fallback = build_fallback_runbook(target_path=target_path, bundle=bundle)
    runbook = fallback

    if config.process_flow.ai_runbook_enabled:
        prompt = _runbook_prompt(target_path=target_path, bundle=bundle, fallback=fallback)
        session = run_ai_session(
            prompt,
            cwd=target_path,
            config=config,
            tools=[],
            model=model,
            timeout=config.process_flow.ai_runbook_timeout_seconds,
            permission_mode="default",
            include_codex_protocol=False,
            max_budget_usd=max_budget_usd,
            log_path=log_path,
            enable_ncdev_hooks=False,
        )
        candidate = parse_runbook_response(session.final_text)
        if session.success and candidate is not None:
            runbook = candidate
            runbook.source = "ai_model"
        else:
            runbook.notes.append(
                "AI runbook generation failed or returned invalid JSON; "
                "using deterministic fallback."
            )

    write_project_runbook(runbook, target_path=target_path, output_dir=output_dir)
    return runbook


def build_fallback_runbook(*, target_path: Path, bundle: CharterBundle) -> ProjectRunbook:
    """Build a conservative runbook from the verification contract."""

    verification = bundle.verification
    backend = _policy_from_command(
        verification.backend_test_command,
        default_root="backend" if (target_path / "backend").exists() else "",
        default_single="pytest -q -x {test_path}",
    )
    frontend = _policy_from_command(
        verification.frontend_test_command,
        default_root="frontend" if (target_path / "frontend").exists() else "",
        default_single="npm run test -- --run {test_path}",
    )
    protected_files = [
        "target-project-contract.json",
        "verification-contract.json",
        RUNBOOK_FILENAME,
    ]
    if (target_path / "docs" / "design-system").exists():
        protected_files.append("docs/design-system/tokens.json")

    return ProjectRunbook(
        source="deterministic_fallback",
        project_name=bundle.contract.project_name,
        backend=backend,
        frontend=frontend,
        protected_files=protected_files,
        mandates=[
            "Use this runbook before heuristic verifier command selection.",
            "Treat project-specific verification contract commands as stronger evidence than inferred venv paths.",
            "Python executes only schema-validated commands; the model supplies policy, not unrestricted shell control.",
        ],
    )


def load_project_runbook(target_path: Path) -> ProjectRunbook | None:
    """Load the target-local runbook if present and valid."""

    path = target_path / ".ncdev" / RUNBOOK_FILENAME
    if not path.exists():
        return None
    try:
        return ProjectRunbook.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def command_for_test_from_runbook(
    runbook: ProjectRunbook | None,
    *,
    test_path: Path,
    target_path: Path,
) -> tuple[Path, list[str]] | None:
    """Return ``(cwd, argv)`` for ``test_path`` using runbook policy."""

    if runbook is None:
        return None

    rel_to_target = (
        test_path.relative_to(target_path)
        if test_path.is_relative_to(target_path)
        else test_path
    )
    rel_text = rel_to_target.as_posix()

    policies = [("backend", runbook.backend), ("frontend", runbook.frontend)]
    for area, policy in policies:
        if not policy.root:
            continue
        root = target_path / policy.root
        if not root.exists():
            continue
        try:
            rel_to_root = test_path.relative_to(root).as_posix()
        except ValueError:
            if rel_text != policy.root and not rel_text.startswith(f"{policy.root}/"):
                continue
            rel_to_root = rel_text.removeprefix(f"{policy.root}/")
        template = policy.single_test_command or _single_from_test_command(
            policy.test_command
        )
        if not template:
            continue
        if area == "frontend" and _looks_like_playwright_test(test_path):
            return root, ["npx", "playwright", "test", rel_to_root]
        command = template.format(
            test_path=rel_to_root,
            repo_test_path=rel_text,
            root=policy.root,
        )
        return root, shlex.split(command)

    return None


def _looks_like_playwright_test(test_path: Path) -> bool:
    """True for browser E2E specs that must not be routed through vitest."""

    parts = {part.lower() for part in test_path.parts}
    if "e2e" in parts:
        return True
    try:
        head = test_path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except OSError:
        return False
    return "@playwright/test" in head


def parse_runbook_response(text: str) -> ProjectRunbook | None:
    """Extract and validate a JSON runbook from model text."""

    if not text.strip():
        return None
    for candidate in _json_candidates(text):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and "project_runbook" in data:
                data = data["project_runbook"]
            return ProjectRunbook.model_validate(data)
        except Exception:  # noqa: BLE001
            continue
    return None


def write_project_runbook(
    runbook: ProjectRunbook, *, target_path: Path, output_dir: Path
) -> None:
    """Persist runbook in run outputs and target-local NC Dev metadata."""

    payload = runbook.model_dump_json(indent=2)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / RUNBOOK_FILENAME).write_text(payload, encoding="utf-8")
    target_meta = target_path / ".ncdev"
    target_meta.mkdir(parents=True, exist_ok=True)
    (target_meta / RUNBOOK_FILENAME).write_text(payload, encoding="utf-8")


def _policy_from_command(
    command: str, *, default_root: str, default_single: str
) -> TestCommandPolicy:
    root, remainder = _split_cd_command(command)
    root = root or default_root
    single = _single_from_test_command(remainder) if remainder else ""
    return TestCommandPolicy(
        root=root,
        test_command=remainder or command,
        single_test_command=single or default_single,
        prefer_project_venv=False,
        venv_must_have_pytest=True,
    )


def _split_cd_command(command: str) -> tuple[str, str]:
    stripped = command.strip()
    match = re.match(r"^cd\s+([^&;]+)\s*&&\s*(.+)$", stripped)
    if not match:
        return "", stripped
    return match.group(1).strip(), match.group(2).strip()


def _single_from_test_command(command: str) -> str:
    if not command:
        return ""
    parts = shlex.split(command)
    if not parts:
        return ""
    if "pytest" in parts[0] or parts[:2] == ["python", "-m"] or parts[:2] == ["python3", "-m"]:
        base = list(parts)
        if "-x" not in base:
            base.append("-x")
        return " ".join([*(shlex.quote(part) for part in base), "{test_path}"])
    if "vitest" in parts or ("npm" in parts[:1] and "test" in parts):
        return " ".join([*(shlex.quote(part) for part in parts), "{test_path}"])
    return ""


def _json_candidates(text: str) -> list[str]:
    candidates = [text.strip()]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    candidates.extend(block.strip() for block in fenced)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])
    return candidates


def _runbook_prompt(
    *, target_path: Path, bundle: CharterBundle, fallback: ProjectRunbook
) -> str:
    files = _repo_snapshot(target_path)
    return f"""
You are NC Dev's process-flow policy model.

Goal: produce a project-specific process runbook as strict JSON. Python will
validate the JSON and execute commands; you are choosing policy, not directly
running shell commands.

Mandates:
- Prefer explicit verification-contract commands over inferred environments.
- If a venv exists but cannot run the needed test framework, do not use it.
- Protect design-system files from unrelated scaffold/auth/storage features.
- Return JSON only, no prose.

Required JSON schema:
{{
  "version": "1.0",
  "source": "ai_model",
  "project_name": "...",
  "backend": {{
    "root": "backend",
    "test_command": "pytest -q",
    "single_test_command": "pytest -q -x {{test_path}}",
    "prefer_project_venv": false,
    "venv_must_have_pytest": true,
    "notes": []
  }},
  "frontend": {{
    "root": "frontend",
    "test_command": "npm run test -- --run",
    "single_test_command": "npm run test -- --run {{test_path}}",
    "prefer_project_venv": false,
    "venv_must_have_pytest": true,
    "notes": []
  }},
  "protected_files": ["docs/design-system/tokens.json"],
  "mandates": ["..."],
  "notes": []
}}

Project: {bundle.contract.project_name}
Backend test command from contract: {bundle.verification.backend_test_command!r}
Frontend test command from contract: {bundle.verification.frontend_test_command!r}
Integration test command from contract: {bundle.verification.integration_test_command!r}
E2E test command from contract: {bundle.verification.e2e_test_command!r}
Fallback runbook to improve only if the repo evidence supports it:
{fallback.model_dump_json(indent=2)}

Repo snapshot:
{files}
""".strip()


def _repo_snapshot(target_path: Path) -> str:
    interesting = [
        "pyproject.toml",
        "backend/pyproject.toml",
        "backend/requirements.txt",
        "package.json",
        "frontend/package.json",
        "pnpm-lock.yaml",
        "package-lock.json",
        "uv.lock",
        "backend/.venv/bin/python",
        "docs/design-system/tokens.json",
    ]
    lines = []
    for rel in interesting:
        path = target_path / rel
        if path.exists():
            marker = "dir" if path.is_dir() else "file"
            lines.append(f"- {rel} ({marker})")
    return "\n".join(lines) or "- no common project markers found"
