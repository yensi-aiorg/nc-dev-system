"""Phase B — Charter generator.

Replaces the legacy 9-artifact discovery pipeline with a single Claude session
that reads the PRD (and optionally an existing repo) and emits three
artifacts:

    target-project-contract.json   # stack, language, DB, auth, ports — the hard constraints
    verification-contract.json     # what "done" means
    feature-queue.json             # ordered FeatureStep list

The Claude session is pointed at the ``writing-plans`` skill and constrained
to the :data:`ncdev.claude_session.DEFAULT_PLAN_TOOLS` allowlist — it can
read files and write JSON, but cannot edit code or invoke Codex. It produces
the three files directly into ``run_dir/outputs/``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import (
    DEFAULT_PLAN_TOOLS,
    ClaudeSessionResult,
)
from ncdev.core.config import NCDevConfig
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureQueueDoc,
    TargetProjectContract,
    VerificationContract,
)


CHARTER_PROMPT_TEMPLATE = """You are producing the project charter for NC Dev's
sequential verified sprint engine. Your job is PLANNING only — do NOT write
application code, do NOT scaffold, do NOT run tests.

Use the `writing-plans` skill to structure your work.

## Input
- PRD file: {prd_path}
- Target repository (may be empty for greenfield, existing for brownfield):
  {target_repo}
- Project type detected: {project_type_hint}

## Required deliverables

Write exactly three JSON files into the directory:

  {output_dir}

### 1. target-project-contract.json

The hard architectural constraints for this project. These are the
invariants that must not change across future runs. Schema:

{contract_schema}

Rules:
- For greenfield, infer sane defaults from the PRD.
- For brownfield, DETECT from the existing repo — do not override what
  is there. Read package.json / pyproject.toml / docker-compose.yml etc.
- `design_archetype` must be one of: Cinematic Minimalism, Technical
  Elegance, Opinionated Darkness, Warm Playfulness, Developer Brutalism,
  Bold Brand Photography. Pick the one best matching the PRD's tone.
- `design_system_source` is "stitch" for new UIs unless the brownfield
  repo already has docs/design-system/ populated.
- `ports` should not collide with existing ports in the repo.

### 2. verification-contract.json

What "done" means for every feature built against this project. Schema:

{verification_schema}

Rules:
- `backend_test_command` / `frontend_test_command` — use the commands
  native to the detected frameworks (pytest, vitest, jest, etc.)
- `required_files` — the minimum file list that MUST exist after all
  features are built (Dockerfile, .env.example, README, etc.)
- `required_screenshots` — list the key pages/routes that must have a
  screenshot captured.
- Keep `prohibited_patterns` as-is unless the PRD explicitly calls out
  additions.

### 3. feature-queue.json

The ordered build list. Schema:

{feature_queue_schema}

Rules:
- Each feature must be independently verifiable (it has tests that run
  and pass in isolation).
- `feature_id` format: `fNN-slug` (f01-scaffold, f02-auth, ...).
- First feature is always `f01-scaffold` — boot skeleton + health check.
- `depends_on_features` must only reference earlier feature_ids.
- For BROWNFIELD with design tokens at docs/design-system/, feature f01
  may be "baseline verification" instead of scaffolding.
- Target 4–12 features for most PRDs. If the PRD is huge, group into
  logical features rather than listing every sub-task.

## Output format

Use the `Write` tool to create each file. Validate with `Read` that you
produced valid JSON. Return a one-sentence summary in your final
response. Do not output the JSON content in your response — just write
the files and confirm.
"""


def _schema_excerpt(model_cls) -> str:
    """Render a compact JSON-schema hint for a pydantic model."""
    schema = model_cls.model_json_schema()
    props = schema.get("properties", {})
    lines = []
    for key, spec in props.items():
        t = spec.get("type", "?")
        if t == "array":
            items = spec.get("items", {})
            t = f"array<{items.get('type', '?')}>"
        default = spec.get("default")
        desc = spec.get("description", "")
        tail = f"  # {desc}" if desc else ""
        if default is not None and not isinstance(default, (list, dict)):
            lines.append(f"  {key}: {t} = {default!r}{tail}")
        else:
            lines.append(f"  {key}: {t}{tail}")
    return "{\n" + "\n".join(lines) + "\n}"


def _feature_queue_schema_excerpt() -> str:
    return """{
  project_name: str
  features: array<FeatureStep>
}

FeatureStep = {
  feature_id: str            # "fNN-slug"
  title: str
  description: str
  acceptance_criteria: array<str>
  test_requirements: array<str>
  depends_on_features: array<str>
  priority: int
  estimated_complexity: "low" | "medium" | "high"
}"""


def build_charter_prompt(
    prd_path: Path,
    target_repo: Path | None,
    output_dir: Path,
    project_type_hint: str = "web",
) -> str:
    return CHARTER_PROMPT_TEMPLATE.format(
        prd_path=str(prd_path),
        target_repo=str(target_repo) if target_repo else "(none — greenfield)",
        output_dir=str(output_dir),
        project_type_hint=project_type_hint,
        contract_schema=_schema_excerpt(TargetProjectContract),
        verification_schema=_schema_excerpt(VerificationContract),
        feature_queue_schema=_feature_queue_schema_excerpt(),
    )


def generate_charter(
    prd_path: Path,
    output_dir: Path,
    *,
    target_repo: Path | None = None,
    project_type_hint: str = "web",
    model: str | None = None,
    timeout: int = 900,
    max_budget_usd: float | None = None,
    log_path: Path | None = None,
    config: NCDevConfig | None = None,
) -> tuple[CharterBundle | None, ClaudeSessionResult]:
    """Run the charter Claude session and load the produced artifacts.

    Returns ``(bundle, session_result)``. ``bundle`` is None if the
    session failed, produced invalid JSON, or wrote a ``charter-error.json``
    (enforced hard-fail for greenfield UI without design system).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_charter_prompt(prd_path, target_repo, output_dir, project_type_hint)

    session = run_ai_session(
        prompt,
        cwd=output_dir,
        config=config,
        tools=DEFAULT_PLAN_TOOLS,
        model=model,
        timeout=timeout,
        include_codex_protocol=False,   # planning only — no Codex shell-out
        max_budget_usd=max_budget_usd,
        log_path=log_path,
    )

    # Hard-fail: greenfield UI without design system writes this file.
    error_path = output_dir / "charter-error.json"
    if error_path.exists():
        return None, session

    if not session.success:
        return None, session

    try:
        bundle = load_charter(output_dir)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None, session

    return bundle, session


def load_charter(output_dir: Path) -> CharterBundle:
    """Load the three charter artifacts from disk. Raises on missing/invalid."""
    contract_path = output_dir / "target-project-contract.json"
    verification_path = output_dir / "verification-contract.json"
    feature_queue_path = output_dir / "feature-queue.json"

    for p in (contract_path, verification_path, feature_queue_path):
        if not p.exists():
            raise FileNotFoundError(f"Charter artifact missing: {p}")

    contract = TargetProjectContract.model_validate_json(
        contract_path.read_text(encoding="utf-8"),
    )
    verification = VerificationContract.model_validate_json(
        verification_path.read_text(encoding="utf-8"),
    )
    feature_queue = FeatureQueueDoc.model_validate_json(
        feature_queue_path.read_text(encoding="utf-8"),
    )

    return CharterBundle(
        contract=contract,
        verification=verification,
        feature_queue=feature_queue,
    )


def write_charter(bundle: CharterBundle, output_dir: Path) -> None:
    """Persist a charter bundle as three JSON files. Useful for tests."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "target-project-contract.json").write_text(
        bundle.contract.model_dump_json(indent=2), encoding="utf-8",
    )
    (output_dir / "verification-contract.json").write_text(
        bundle.verification.model_dump_json(indent=2), encoding="utf-8",
    )
    (output_dir / "feature-queue.json").write_text(
        bundle.feature_queue.model_dump_json(indent=2), encoding="utf-8",
    )
