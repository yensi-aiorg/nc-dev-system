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

### `acceptance` is MANDATORY per feature — no exceptions

Every FeatureStep MUST have a populated `acceptance` block with at
least ONE of `required_files` or `required_tests`, and ideally both.
This is the production-readiness gate the verifier enforces — leaving
it empty silently marks the feature done without proof, which the
charter validator now rejects.

For each feature, populate:
- `required_files`: 1–5 repo-relative paths the feature MUST create or
  meaningfully edit (e.g. `backend/app/routes/auth.py`,
  `frontend/src/pages/Dashboard.tsx`, `docs/design-system/tokens.json`).
- `required_routes`: HTTP routes the app must expose for this feature
  (e.g. `/api/auth/login`, `/dashboard`). Empty for non-web features.
- `required_tests`: 1–3 test files that MUST exist and pass and
  reference the feature_id (e.g. `tests/test_auth_f02.py`).
- `required_screenshots`: short slug per page (e.g. `dashboard`,
  `login-page`). Empty for backend-only features.
- `must_mention_feature_id`: keep `true` unless the feature is shared
  infra that legitimately can't reference its own id.
- `verify_app_boots`: default `false`. Set `true` ONLY for features
  that explicitly bring up the application daemon and leave it
  reachable at the end of their session — typically the f01-scaffold
  feature when it includes a "the app boots and serves /health"
  acceptance criterion. Other features must leave this `false`
  because Claude sessions don't keep daemons up between sessions
  and a True here would always fail the per-feature boot probe.

For non-UI projects (CLI / library), populate `required_files` and
`required_tests` only and leave `required_routes` /
`required_screenshots` empty.

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
  acceptance_criteria: array<str>     # free-form prose for Claude
  test_requirements: array<str>
  depends_on_features: array<str>
  priority: int
  estimated_complexity: "low" | "medium" | "high"
  acceptance: FeatureAcceptance       # REQUIRED — see below
}

FeatureAcceptance = {                 # per-feature production-readiness gate
  required_files: array<str>          # repo-relative paths that MUST exist
                                       #   AND mention <feature_id>
  required_routes: array<str>         # URLs that MUST 200 when app is booted
                                       #   (consumed by integration gate)
  required_tests: array<str>          # repo-relative test files that MUST
                                       #   exist, mention feature_id, and pass
  required_screenshots: array<str>    # filenames under .ncdev/evidence/
  verify_app_boots: bool              # default False — set True ONLY for
                                       #   scaffold/boot features that leave
                                       #   the app reachable at session end.
                                       #   Other features should leave it False.
  must_mention_feature_id: bool       # default True — keep True
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
    max_retries: int = 1,
) -> tuple[CharterBundle | None, ClaudeSessionResult]:
    """Run the charter Claude session and load the produced artifacts.

    Returns ``(bundle, session_result)``. ``bundle`` is None if the
    session failed, produced invalid JSON, wrote a ``charter-error.json``
    (enforced hard-fail), or could not satisfy the completeness validator
    after ``max_retries`` retry attempts.

    On a validator-rejected charter, this function automatically retries
    with an augmented prompt that includes the violation list — so a
    Claude session that almost-correctly produces the charter can
    self-correct in a follow-up pass instead of killing the whole run.
    A bare LLM hallucination of the schema is exactly the failure mode
    this retry exists to absorb. The retry budget is bounded
    (``max_retries`` defaults to 1, so worst case 2 charter sessions).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    base_prompt = build_charter_prompt(prd_path, target_repo, output_dir, project_type_hint)

    last_session: ClaudeSessionResult | None = None
    last_violations: list[str] = []

    for attempt in range(max_retries + 1):
        prompt = base_prompt
        if attempt > 0 and last_violations:
            prompt = base_prompt + _retry_feedback_section(last_violations, attempt)
            # Move attempt-N artifacts aside so the next session starts clean
            # and we keep the failed attempt for postmortem.
            _archive_attempt(output_dir, attempt)

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
        last_session = session

        # Hard-fail: greenfield UI without design system writes this file.
        error_path = output_dir / "charter-error.json"
        if error_path.exists():
            return None, session

        if not session.success:
            return None, session

        try:
            bundle = load_charter(output_dir, strict=True)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            last_violations = _extract_violations(str(exc))
            if attempt < max_retries:
                # Retry — keep going; we'll feed the violations back next loop.
                continue
            # Out of retries: persist charter-error.json with the
            # accumulated violation list for postmortem.
            (output_dir / "charter-error.json").write_text(
                json.dumps(
                    {
                        "error": str(exc),
                        "attempts": attempt + 1,
                        "violations": last_violations,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            return None, session

        return bundle, session

    # Unreachable — the loop returns on every branch — but defensively
    # surface a structured failure if it ever does fall through.
    assert last_session is not None  # noqa: S101
    return None, last_session  # pragma: no cover


def _extract_violations(err_message: str) -> list[str]:
    """Pull bullet-point violations out of a load_charter ValueError.

    The validator formats violations as ``"\\n  - <text>"``. We split on
    that to recover the list so the retry prompt can echo each item.
    """
    if "  - " not in err_message:
        return [err_message]
    head, _, body = err_message.partition("  - ")
    items = [body] + []
    items = [head + body] if not body else [b.strip() for b in body.split("\n  - ")]
    return [item.rstrip() for item in items if item.strip()]


def _retry_feedback_section(violations: list[str], attempt: int) -> str:
    bullets = "\n".join(f"  - {v}" for v in violations)
    return (
        f"\n\n## Retry attempt {attempt + 1}: previous charter rejected\n"
        f"\nThe charter validator rejected your previous attempt with these "
        f"violations:\n\n{bullets}\n\n"
        "Address each violation and rewrite the three JSON files. The "
        "validator runs again on this attempt — do not produce another "
        "incomplete charter. Use the `Read` tool to inspect the files you "
        "wrote previously (they are still on disk under "
        f"`<output_dir>/.attempt-{attempt}/`) so you can see exactly what "
        "shape was rejected, then re-emit corrected versions."
    )


def _archive_attempt(output_dir: Path, attempt: int) -> None:
    """Move the previous attempt's artifacts under ``.attempt-N/`` for postmortem."""
    archive_dir = output_dir / f".attempt-{attempt}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "target-project-contract.json",
        "verification-contract.json",
        "feature-queue.json",
        "charter-error.json",
    ):
        src = output_dir / name
        if src.exists():
            src.rename(archive_dir / name)


def load_charter(output_dir: Path, *, strict: bool = True) -> CharterBundle:
    """Load the three charter artifacts from disk.

    Raises on missing/invalid files. When ``strict=True`` (default), also
    runs :func:`validate_charter_completeness` and refuses to return a
    bundle whose verification contract or feature acceptance is empty —
    those are the silent-skip configurations we explicitly outlawed.
    Pass ``strict=False`` only for test fixtures or backwards-compat
    inspection of legacy charters.
    """
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

    bundle = CharterBundle(
        contract=contract,
        verification=verification,
        feature_queue=feature_queue,
    )

    if strict:
        violations = validate_charter_completeness(bundle)
        if violations:
            raise ValueError(
                "Charter rejected — production-readiness gates are not "
                "configured. Fix the following and rerun the charter "
                "phase:\n  - " + "\n  - ".join(violations)
            )

    return bundle


def validate_charter_completeness(bundle: CharterBundle) -> list[str]:
    """Return a list of completeness violations. Empty list = charter is OK.

    Enforces the rules that prevent silent skips:

    1. ``verification.backend_test_command`` must be set, OR
       ``verification.frontend_test_command`` must be set, OR
       ``contract.project_type`` is "library" (libraries may use
       ``backend_test_command`` only — checked separately). At least one
       executable test command is required so the integration gate has
       something to run.
    2. For web/api projects, ``verification.backend_health_url`` must be
       set — without it we can't probe whether the app boots.
    3. Every feature must have at least one ``required_file`` or
       ``required_test`` in its acceptance bag. The state-scanner and
       per-feature verifier need ground truth to check against.
    """
    violations: list[str] = []
    v = bundle.verification
    c = bundle.contract

    has_test_cmd = bool(v.backend_test_command.strip()) or bool(
        v.frontend_test_command.strip()
    )
    if not has_test_cmd:
        violations.append(
            "verification-contract: at least one of backend_test_command "
            "or frontend_test_command must be set so the verifier can "
            "actually run tests"
        )

    if c.project_type in {"web", "api"} and not v.backend_health_url.strip():
        violations.append(
            "verification-contract: backend_health_url is required for "
            f"project_type={c.project_type!r} so the integration gate can "
            "probe app readiness"
        )

    for feature in bundle.feature_queue.features:
        accept = feature.acceptance
        if not accept.required_files and not accept.required_tests:
            violations.append(
                f"feature {feature.feature_id!r} has empty acceptance: "
                "populate at least one of required_files / required_tests"
            )

    return violations


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
