"""Phase C — Design system phase.

For any web / UI project, produces a design system in ``docs/design-system/``
and a summary :class:`DesignSystemDoc` artifact. Three paths:

    * ``source="stitch"``   — invoke a Claude session with the Stitch MCP
                              server exposed; Claude creates a Stitch
                              project, generates the design system, and
                              downloads tokens + screen HTML.
    * ``source="existing"`` — brownfield case: ``docs/design-system/`` is
                              already populated; Claude reads it and
                              summarises into the artifact.
    * ``source="claude_generated"`` — fallback when Stitch is
                              unavailable AND the project is brownfield.
                              Claude's ``frontend-design`` skill produces
                              the tokens itself.

Hard-fail rule (enforces the user's ask):

    Greenfield UI project + no Stitch available + no existing design
    system on disk → fail the run with an actionable error. We will NOT
    let a build proceed without defined designs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import ClaudeSessionResult
from ncdev.v2.config import NCDevV2Config
from ncdev.v3.models import (
    DesignSystemDoc,
    TargetProjectContract,
)


# Tools for the Stitch / claude_generated branches — Claude needs to
# write tokens, invoke the frontend-design skill, and potentially shell
# to a Stitch CLI. Stitch MCP tools come through as ``mcp__stitch__*``
# names (environment-specific).
STITCH_DESIGN_TOOLS: tuple[str, ...] = (
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "Skill",
    "Task",
)

# Tools for the brownfield summariser — Claude reads the existing
# design system and writes ONE JSON artifact. No editing / shelling out.
SUMMARISE_DESIGN_TOOLS: tuple[str, ...] = (
    "Read",
    "Glob",
    "Grep",
    "Write",   # must write design-system.json — nothing else
)

# Backward-compat alias; older callers / tests may import this name.
DESIGN_TOOLS = STITCH_DESIGN_TOOLS


@dataclass
class DesignPhaseResult:
    """Outcome of the design phase."""
    skipped: bool = False           # non-UI project
    hard_failed: bool = False       # greenfield UI without designs and no Stitch
    design_doc: DesignSystemDoc | None = None
    session: ClaudeSessionResult | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Environment probes
# ---------------------------------------------------------------------------


def stitch_available() -> bool:
    """Return True if a Stitch MCP server appears to be configured.

    Claude Code reads MCP server definitions from several locations,
    depending on version and install style. We check each of them
    in order:

    1. ``$NCDEV_STITCH_MCP_CONFIG`` — explicit override path (for tests
       or non-standard setups).
    2. ``~/.claude/mcp.json`` — Claude Code's dedicated MCP file.
    3. ``~/.claude/settings.json`` — older/alternate layout where MCP
       servers live under ``mcpServers`` in the main settings.
    4. ``~/.claude/.claude.json`` — some installs keep a project /
       user-scoped file here with MCP entries.
    5. Project-local ``.mcp.json`` or ``.claude/mcp.json`` in CWD or
       its ancestors — per-project MCP registrations.

    Any file with an ``mcpServers`` map containing a key whose name
    includes ``"stitch"`` (case-insensitive) counts as configured.

    This is a lightweight probe — we do NOT actually start the MCP
    server. A healthy ``mcp.json`` entry with a missing binary won't
    fail here, it'll fail at Claude-session time, which is the right
    place to report it.
    """
    import os
    import json

    override = os.environ.get("NCDEV_STITCH_MCP_CONFIG")
    if override:
        p = Path(override)
        if p.exists() and _has_stitch_entry(p):
            return True
        # Explicit override that doesn't exist / doesn't list stitch
        # is a clear "no" — don't fall back silently.
        if p.exists():
            return False
        # If override path is missing entirely, treat as no override.

    candidates: list[Path] = [
        Path.home() / ".claude" / "mcp.json",
        Path.home() / ".claude" / "settings.json",
        Path.home() / ".claude" / ".claude.json",
    ]

    # Project-local MCP configs — walk up from CWD looking for .mcp.json
    # or .claude/mcp.json. This matches how Claude Code itself discovers
    # per-project MCP definitions.
    cwd = Path.cwd()
    for ancestor in [cwd, *cwd.parents]:
        candidates.append(ancestor / ".mcp.json")
        candidates.append(ancestor / ".claude" / "mcp.json")
        if ancestor == ancestor.parent:
            break

    seen: set[Path] = set()
    for path in candidates:
        path = path.resolve() if path.exists() else path
        if path in seen or not path.exists():
            continue
        seen.add(path)
        if _has_stitch_entry(path):
            return True
    return False


def _has_stitch_entry(path: Path) -> bool:
    """True if the JSON file at ``path`` has an MCP server whose key
    contains ``stitch`` (case-insensitive)."""
    import json
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    # Accept either top-level ``mcpServers`` or nested under a profile.
    mcp_maps: list[dict] = []
    if isinstance(data, dict):
        top = data.get("mcpServers")
        if isinstance(top, dict):
            mcp_maps.append(top)
        # Some configs nest under "projects" / project-path → mcpServers
        projects = data.get("projects")
        if isinstance(projects, dict):
            for v in projects.values():
                if isinstance(v, dict):
                    nested = v.get("mcpServers")
                    if isinstance(nested, dict):
                        mcp_maps.append(nested)
    for servers in mcp_maps:
        for key in servers.keys():
            if isinstance(key, str) and "stitch" in key.lower():
                return True
    return False


_TOKEN_FILE_NAMES: tuple[str, ...] = (
    "tokens.css",
    "tokens.scss",
    "tokens.json",
    "design-tokens.json",
    "tailwind.config.js",
    "tailwind.config.ts",
    "tailwind.config.cjs",
    "theme.ts",
    "theme.js",
    "theme.json",
    "colors.css",
    "colors.scss",
    "variables.css",
    "variables.scss",
    "_tokens.scss",
    "globals.css",
)


def existing_design_system_present(target_path: Path) -> bool:
    """True if ``target_path/docs/design-system/`` has real token files.

    A non-empty file is not sufficient — we check for known token file
    names so an accidental README or stray image doesn't count. Prevents
    silent acceptance of junk as a design system.
    """
    ds = target_path / "docs" / "design-system"
    if not ds.exists() or not ds.is_dir():
        return False
    for f in ds.rglob("*"):
        if not f.is_file():
            continue
        if f.name.lower() in _TOKEN_FILE_NAMES and f.stat().st_size > 0:
            return True
    return False


def is_ui_project(contract: TargetProjectContract) -> bool:
    return contract.project_type.lower() in ("web", "webapp", "frontend", "spa", "saas")


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _stitch_prompt(contract: TargetProjectContract, target_path: Path, output_dir: Path) -> str:
    return f"""You are producing the design system for a new web project using Stitch
(Google's design tool, available via MCP).

## Project
- Name: {contract.project_name}
- Design archetype: {contract.design_archetype}
- Frontend framework: {contract.frontend_framework}
- Target repository: {target_path}

## Required workflow

1. Use the Stitch MCP tools to create a new Stitch project for
   "{contract.project_name}".
2. Generate a design system (colors, typography, spacing, corner
   rounding) aligned with the "{contract.design_archetype}" archetype.
3. Generate the key screens listed in
   ``{output_dir}/feature-queue.json`` (at least the ones marked as
   having UI).
4. Download the design tokens (CSS variables, Tailwind config, or the
   equivalent for {contract.frontend_framework}) into:
     {target_path}/docs/design-system/
5. Download HTML exports for each screen into:
     {target_path}/docs/design-system/screens/
6. Write a summary artifact at:
     {output_dir}/design-system.json
   Schema (DesignSystemDoc):
     {{
       "project_name": "{contract.project_name}",
       "design_archetype": "{contract.design_archetype}",
       "source": "stitch",
       "tokens_dir": "docs/design-system",
       "tokens_files": ["..."],
       "colors": {{ ... }},
       "typography": {{ ... }},
       "spacing": {{ ... }},
       "screens": [{{ "name": "...", "html_path": "...", "screenshot_path": "..." }}],
       "stitch_project_id": "..."
     }}

## Rules

- Do NOT write any application code. Tokens and HTML only.
- Prefer downloading real HTML from Stitch over screenshots — it
  preserves animations and layout metadata.
- If Stitch MCP tools are unavailable or fail, STOP and write
  ``{output_dir}/design-phase-error.json`` with an actionable message.
  Do not fall back to generating tokens yourself.

Return a one-sentence summary when done.
"""


def _brownfield_prompt(contract: TargetProjectContract, target_path: Path, output_dir: Path) -> str:
    return f"""This is a brownfield project. A design system already exists at:
  {target_path}/docs/design-system/

## Your job

1. Read the existing design system files.
2. Summarise them into ``{output_dir}/design-system.json`` using schema:
     {{
       "project_name": "{contract.project_name}",
       "design_archetype": "{contract.design_archetype}",
       "source": "existing",
       "tokens_dir": "docs/design-system",
       "tokens_files": ["..."],   # actual filenames found
       "colors": {{ ... }},         # extracted palette
       "typography": {{ ... }},     # font families / sizes found
       "spacing": {{ ... }},
       "screens": [{{ "name": "...", "html_path": "..." }}]
     }}

## Rules

- Do NOT modify any files under docs/design-system/ — you are only
  reading and summarising.
- Do not invoke Codex. Do not write implementation code.

Return a one-sentence summary when done.
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_design_phase(
    contract: TargetProjectContract,
    target_path: Path,
    output_dir: Path,
    *,
    model: str | None = None,
    timeout: int = 1200,
    max_budget_usd: float | None = None,
    log_path: Path | None = None,
    stitch_probe: callable = stitch_available,
    config: NCDevV2Config | None = None,
) -> DesignPhaseResult:
    """Resolve the design system for this project.

    Returns a :class:`DesignPhaseResult`. The caller MUST check
    ``hard_failed`` and abort the pipeline when True.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Non-UI projects skip the design phase entirely.
    if not is_ui_project(contract):
        return DesignPhaseResult(skipped=True)

    has_existing = existing_design_system_present(target_path)
    has_stitch = stitch_probe()

    # --- Hard-fail: greenfield UI, no existing designs, no Stitch ----------
    if not contract.is_brownfield and not has_existing and not has_stitch:
        err_path = output_dir / "design-phase-error.json"
        err_path.write_text(
            '{"error": "greenfield UI project requires a design system",'
            ' "fix": "install and configure the Stitch MCP server, or '
            'supply docs/design-system/ with design tokens and sample pages"}',
            encoding="utf-8",
        )
        return DesignPhaseResult(
            hard_failed=True,
            error="greenfield UI project requires a design system (Stitch or docs/design-system)",
        )

    # --- Brownfield with existing design system ----------------------------
    if has_existing:
        prompt = _brownfield_prompt(contract, target_path, output_dir)
        session = run_ai_session(
            prompt,
            cwd=target_path,
            config=config,
            tools=SUMMARISE_DESIGN_TOOLS,   # read-only + write the summary JSON
            model=model,
            timeout=timeout,
            include_codex_protocol=False,
            max_budget_usd=max_budget_usd,
            log_path=log_path,
        )
        return _finalise_design_phase(session, output_dir)

    # --- Greenfield (or brownfield without designs) + Stitch available ----
    if has_stitch:
        prompt = _stitch_prompt(contract, target_path, output_dir)
        session = run_ai_session(
            prompt,
            cwd=target_path,
            config=config,
            tools=STITCH_DESIGN_TOOLS,
            model=model,
            timeout=timeout,
            include_codex_protocol=False,   # design phase does not build code
            max_budget_usd=max_budget_usd,
            log_path=log_path,
        )
        return _finalise_design_phase(session, output_dir)

    # --- Brownfield without existing designs and no Stitch: Claude decides --
    # Per the user's ruling: "brownfield or design-provided → Claude makes
    # the call". We spawn Claude with the frontend-design skill; it may
    # generate tokens itself.
    prompt = (
        f"This is a brownfield project '{contract.project_name}' without "
        f"a pre-existing design system and without Stitch MCP available. "
        f"Use the `frontend-design` skill to produce minimal design tokens "
        f"aligned with the '{contract.design_archetype}' archetype, "
        f"write them into {target_path}/docs/design-system/, and "
        f"summarise in {output_dir}/design-system.json with source='claude_generated'. "
        f"If you determine the project genuinely needs Stitch or external "
        f"designs to proceed, write design-phase-error.json instead."
    )
    session = run_ai_session(
        prompt,
        cwd=target_path,
        config=config,
        tools=STITCH_DESIGN_TOOLS,
        model=model,
        timeout=timeout,
        include_codex_protocol=False,
        max_budget_usd=max_budget_usd,
        log_path=log_path,
    )
    return _finalise_design_phase(session, output_dir)


def _finalise_design_phase(session, output_dir: Path) -> DesignPhaseResult:
    """Enforce success + artifact presence for every non-skip branch.

    Required for a pass: the AI session must have exited cleanly AND a
    parseable design-system.json must exist on disk. A design-phase-error
    file written by the session is always a hard fail.
    """
    err_path = output_dir / "design-phase-error.json"
    if err_path.exists():
        return DesignPhaseResult(
            hard_failed=True,
            session=session,
            error=f"Design phase wrote error artifact at {err_path}",
        )
    if not session.success:
        return DesignPhaseResult(
            hard_failed=True,
            session=session,
            error=f"Design session exited unsuccessfully: {session.error or 'no detail'}",
        )
    doc = _load_design_doc(output_dir)
    if doc is None:
        return DesignPhaseResult(
            hard_failed=True,
            session=session,
            error=(
                "Design session reported success but no valid "
                f"{output_dir}/design-system.json was produced."
            ),
        )
    return DesignPhaseResult(design_doc=doc, session=session)


def _load_design_doc(output_dir: Path) -> DesignSystemDoc | None:
    path = output_dir / "design-system.json"
    if not path.exists():
        return None
    try:
        return DesignSystemDoc.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
