"""Product Steward — the whole-product UX coherence agent.

Runs at coherence checkpoints (end-of-slice, end-of-run, on feature
failure) and decides what the factory should do next: continue,
repair, replan, or stop.

This is the role that holds the entire feature queue + current repo
state + TestCraftr findings in one head and asks "is this product
done from a user's perspective." It is deliberately a single Claude
session (not a pipeline phase) so stronger reasoning models improve
it directly.
"""
from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import DEFAULT_PLAN_TOOLS
from ncdev.core.config import NCDevConfig
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureStep,
    StepResult,
)
from ncdev.pipeline.product_debt import ProductDebt


class Disposition(str, Enum):
    """What the Steward decided the factory should do next."""

    CONTINUE = "continue"
    REPAIR_CURRENT_SLICE = "repair_current_slice"
    INSERT_FEATURES = "insert_features"
    REWRITE_ACCEPTANCE = "rewrite_acceptance"
    RERUN_CHARTER = "rerun_charter"
    STOP_AS_UNRECOVERABLE = "stop_as_unrecoverable"


class FeatureAmendment(BaseModel):
    feature_id: str
    field: str
    new_value: Any
    reason: str


class StewardDecision(BaseModel):
    disposition: Disposition
    reasoning: str
    target_feature_ids: list[str] = Field(default_factory=list)
    new_features: list[FeatureStep] = Field(default_factory=list)
    amendments: list[FeatureAmendment] = Field(default_factory=list)


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_steward_response(text: str) -> StewardDecision:
    """Parse the Steward's JSON response. Tolerates markdown fences."""
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    data = json.loads(cleaned)
    return StewardDecision.model_validate(data)


def _summarise_completed(completed: list[StepResult]) -> str:
    if not completed:
        return "(no features executed yet)"
    lines = []
    for r in completed:
        files = len(r.files_created) + len(r.files_modified)
        status = getattr(r.status, "name", str(r.status).upper())
        lines.append(
            f"  - {r.feature_id}: {status} "
            f"({files} files, commit {r.commit_sha[:8] or '(none)'})"
            + (f" - {r.error_message[:120]}" if r.error_message else "")
        )
    return "\n".join(lines)


def _contract_stack(bundle: CharterBundle) -> str:
    contract = bundle.contract
    language = getattr(contract, "language", "")
    if not language:
        languages = [
            contract.language_backend,
            contract.language_frontend,
        ]
        language = "/".join(part for part in languages if part) or "unspecified"
    return f"{language} + {contract.database or 'unspecified'}"


def _summarise_product_debt(product_debt: list[ProductDebt] | None) -> str:
    if not product_debt:
        return ""
    lines = ["### Detected product debt", ""]
    for debt in product_debt:
        routes = (
            f" Affected routes: {', '.join(debt.affected_routes)}."
            if debt.affected_routes
            else ""
        )
        lines.append(
            f"  - [{debt.debt_type.value}] {debt.debt_id} "
            f"(confidence {debt.confidence:.1f}): {debt.description} "
            f"Suggested: {debt.suggested_disposition.value}.{routes}"
        )
    return "\n".join(lines)


def build_steward_prompt(
    *,
    prd_path: Path,
    bundle: CharterBundle,
    completed: list[StepResult],
    target_path: Path,
    last_test_craftr_scores: dict | None = None,
    product_debt: list[ProductDebt] | None = None,
) -> str:
    prd_excerpt = prd_path.read_text(encoding="utf-8")[:8000]
    queue_summary = "\n".join(
        f"  - {f.feature_id}: {f.title}"
        for f in bundle.feature_queue.features
    )
    tc_block = (
        "(no TestCraftr probe yet)"
        if last_test_craftr_scores is None
        else json.dumps(last_test_craftr_scores, indent=2)
    )
    product_debt_block = _summarise_product_debt(product_debt)
    product_debt_section = (
        f"\n{product_debt_block}\n"
        if product_debt_block
        else ""
    )
    return f"""# Product Steward - judgment session

You are the Product Steward. Your job is to look at the *whole product*
- the PRD, the planned feature queue, what's already been built, the
running app's behaviour - and decide what the factory should do next.

You are NOT writing code. You are NOT verifying individual features
(that's already done). You are answering: **"is this product going to
be a working, coherent thing a user can actually use end-to-end, and
if not, what's the cheapest next move?"**

## Inputs

### PRD (truncated to 8000 chars)
```
{prd_excerpt}
```

### Charter - Project contract
- project_type: {bundle.contract.project_type}
- archetype: {bundle.contract.design_archetype}
- stack: {_contract_stack(bundle)}

### Planned feature queue
{queue_summary}

### Completed so far
{_summarise_completed(completed)}

### Current repo
- target_path: {target_path}
- (you may use the Read/Glob tools to inspect specific files if needed)

### Last TestCraftr probe
```json
{tc_block}
```
{product_debt_section}

## Your decision

Reply with a SINGLE JSON object (no prose around it). Schema:

```json
{{
  "disposition": "<one of: continue | repair_current_slice | insert_features | rewrite_acceptance | rerun_charter | stop_as_unrecoverable>",
  "reasoning": "<2-4 sentences explaining your call>",
  "target_feature_ids": ["<feature_ids the action applies to>"],
  "new_features": [<full FeatureStep objects if disposition=insert_features>],
  "amendments": [{{"feature_id": "...", "field": "...", "new_value": ..., "reason": "..."}}]
}}
```

### Disposition meanings

- `continue` - current slice is in good shape; build the next feature(s).
- `repair_current_slice` - last slice has a fixable problem; re-run the
  feature(s) listed in `target_feature_ids` with the issue noted in
  `reasoning`. Use for: feature claimed PASSED but routes don't actually
  work, dead UI controls, broken inter-feature integration.
- `insert_features` - the PRD implies a feature the planner missed.
  Provide full FeatureStep objects in `new_features`.
- `rewrite_acceptance` - the planned acceptance criteria for a feature
  are wrong (over- or under-specified). Provide amendments.
- `rerun_charter` - the charter is so off that the cheapest path is a
  fresh planning pass. Use sparingly.
- `stop_as_unrecoverable` - the product can't be completed within budget
  / capability. Explain why.

### Examples of judgement calls you should make

- "f02-auth PASSED but the /dashboard route 404s in the integration
  gate - repair, don't continue" -> `repair_current_slice`
- "PRD says 'manage appointments' but no feature handles cancellation
  flows - insert" -> `insert_features`
- "Every feature PASSED, integration gate is clean, TestCraftr scored
  all axes above threshold" -> `continue` (which at end-of-run means
  "we're done")
- "Three repair attempts on f01 have all failed for the same reason and
  the underlying problem is the contract demanding postgres on a
  sqlite-only host" -> `stop_as_unrecoverable`

Return the JSON now.
"""


def run_product_steward(
    *,
    prd_path: Path,
    bundle: CharterBundle,
    completed: list[StepResult],
    target_path: Path,
    run_dir: Path,
    config: NCDevConfig | None,
    last_test_craftr_scores: dict | None = None,
    product_debt: list[ProductDebt] | None = None,
    model: str | None = None,
    max_budget_usd: float | None = None,
) -> StewardDecision:
    """Run one Steward judgment session, return its decision.

    A malformed response collapses to STOP_AS_UNRECOVERABLE - silently
    continuing on a Steward that didn't actually emit a decision is the
    failure mode this whole feature exists to prevent.
    """
    prompt = build_steward_prompt(
        prd_path=prd_path,
        bundle=bundle,
        completed=completed,
        target_path=target_path,
        last_test_craftr_scores=last_test_craftr_scores,
        product_debt=product_debt,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "steward-prompt.md").write_text(prompt, encoding="utf-8")

    session = run_ai_session(
        prompt,
        cwd=target_path,
        config=config,
        tools=DEFAULT_PLAN_TOOLS,
        model=model,
        timeout=600,
        include_codex_protocol=False,
        max_budget_usd=max_budget_usd,
        log_path=run_dir / "steward-session.jsonl",
    )
    (run_dir / "steward-response.md").write_text(
        session.final_text or "(empty)", encoding="utf-8",
    )

    if not session.success or not session.final_text:
        return StewardDecision(
            disposition=Disposition.STOP_AS_UNRECOVERABLE,
            reasoning="Steward session failed or returned no text",
        )
    try:
        return parse_steward_response(session.final_text)
    except (json.JSONDecodeError, ValueError) as exc:
        return StewardDecision(
            disposition=Disposition.STOP_AS_UNRECOVERABLE,
            reasoning=f"Steward response invalid: {exc}",
        )
