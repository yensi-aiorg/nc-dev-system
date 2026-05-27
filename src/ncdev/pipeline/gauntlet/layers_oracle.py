"""L8 — oracle review.

A *different* top-tier model than the one that built the feature scores
the diff against each explicit acceptance criterion. Two research
findings shape this layer:

  * An LLM asked "is this good?" rubber-stamps. An LLM asked "does this
    diff satisfy criterion 3.2?" gives signal. So the prompt is
    anchored to each acceptance criterion, one verdict each.
  * A model reviewing its own output shares its own blind spots. So the
    reviewer provider is decorrelated from the builder: Claude-built →
    GPT reviews; Codex-built → Claude reviews.

A clear "not met" verdict blocks. A session or parse failure is a
non-blocking ERROR — an oracle malfunction is not the feature's fault
and must not brick the build.
"""
from __future__ import annotations

import time

from ncdev.pipeline.gauntlet.context import GauntletContext, extract_json_object
from ncdev.pipeline.gauntlet.models import GauntletLayerResult, LayerStatus

_MAX_DIFF_CHARS = 60_000


def _select_reviewer(builder_provider: str) -> str:
    """Pick a reviewer provider decorrelated from the builder."""
    return "codex" if builder_provider.strip().lower() == "claude" else "claude"


def _build_review_prompt(ctx: GauntletContext) -> str:
    feature = ctx.feature
    criteria = [c for c in feature.acceptance_criteria if c.strip()]
    criteria_block = "\n".join(f"  {i}. {c}" for i, c in enumerate(criteria, 1))
    diff = ctx.diff[:_MAX_DIFF_CHARS]
    truncated = "\n[diff truncated]" if len(ctx.diff) > _MAX_DIFF_CHARS else ""
    changed_block = (
        "\n".join(f"  - {p}" for p in ctx.changed_files[:40])
        if ctx.changed_files
        else "  (no changed files reported)"
    )
    repo = ctx.repo
    return f"""You are an independent code reviewer. You did NOT write this code.

Decide whether the **cumulative repository state** at `{repo}` satisfies
each acceptance criterion for this feature. The session under review
may be a fresh build (large diff) or a repair on top of earlier
commits (small diff). For repairs, the criteria are typically already
satisfied by prior commits — your job is to confirm the repo as a
whole satisfies them, **not** to demand every criterion live in this
session's diff alone.

You have the **Read**, **Grep**, and **Glob** tools. Use them. For
each criterion, locate the file / function / test that implements it
and verify the behaviour is real (not a stub, mock, TODO, or
bypassed integration). The diff below + the changed-files list tell
you what changed *this* session, which is useful context but not
authoritative for "is the criterion met".

Feature: {feature.title}
Description: {feature.description}

Acceptance criteria:
{criteria_block}

Files changed in this session (for context — the criteria may be
satisfied by other files committed earlier):
{changed_block}

Diff for this session (context only — DO NOT judge "met" purely from
the diff; verify against the repo via Read/Grep):
```diff
{diff}{truncated}
```

For EACH numbered criterion: locate the code that proves it (via
Read/Grep across the repo, not just the diff). A criterion is "met"
only if real working code for it exists somewhere in the repo —
stubs, mocks, TODOs, and bypassed integrations are "not_met". If the
diff is small because most of the criterion was already implemented
in a prior commit, that's fine — the cumulative state is what
matters.

Respond with ONLY a JSON object, no prose around it:
{{
  "criteria": [
    {{"index": 1, "verdict": "met|not_met|unclear", "reason": "<one line, name the file/symbol that proves it or names what's missing>"}}
  ],
  "overall": "pass|fail"
}}
"overall" is "fail" if ANY criterion is "not_met"."""


def _parse_verdict(text: str) -> dict | None:
    """Extract the JSON verdict object from a model's response."""
    return extract_json_object(text)


def _run_review_session(provider: str, prompt: str, ctx: GauntletContext) -> tuple[bool, str]:
    """Run the reviewer session. Returns (ok, final_text).

    Isolated in its own function so tests can monkeypatch it without
    spawning a real CLI.
    """
    repo = ctx.repo
    if provider == "claude":
        from ncdev.claude_session import run_claude_session

        result = run_claude_session(
            prompt, cwd=repo, tools=["Read", "Grep", "Glob"],
            permission_mode="default", include_codex_protocol=False,
            enable_ncdev_hooks=False, timeout=600,
        )
    else:
        from ncdev.ai_session import run_codex_session

        result = run_codex_session(prompt, cwd=repo, timeout=600)
    return bool(result.success), result.final_text or ""


def layer_oracle(ctx: GauntletContext) -> GauntletLayerResult:
    """L8 — independent oracle review against acceptance criteria."""
    start = time.time()

    if not ctx.run_commands:
        return GauntletLayerResult(
            layer="L8-oracle", status=LayerStatus.SKIPPED, blocking=False,
            summary="oracle: command execution disabled — skipped",
        )
    if not ctx.diff.strip():
        return GauntletLayerResult(
            layer="L8-oracle", status=LayerStatus.SKIPPED, blocking=False,
            summary="oracle: no diff to review — skipped",
        )
    if not [c for c in ctx.feature.acceptance_criteria if c.strip()]:
        return GauntletLayerResult(
            layer="L8-oracle", status=LayerStatus.SKIPPED, blocking=False,
            summary="oracle: feature has no acceptance criteria — skipped",
        )

    reviewer = _select_reviewer(ctx.builder_provider)
    prompt = _build_review_prompt(ctx)

    try:
        ok, text = _run_review_session(reviewer, prompt, ctx)
    except Exception as exc:  # noqa: BLE001
        return GauntletLayerResult(
            layer="L8-oracle", status=LayerStatus.ERROR, blocking=False,
            summary=f"oracle: reviewer session crashed ({exc})",
            duration_seconds=time.time() - start,
        )

    duration = time.time() - start
    verdict = _parse_verdict(text)
    if not ok or verdict is None:
        # Oracle malfunction — surface it, but do not block the build on
        # our reviewer failing to produce a parseable verdict.
        return GauntletLayerResult(
            layer="L8-oracle", status=LayerStatus.ERROR, blocking=False,
            summary=f"oracle: no parseable verdict from {reviewer} reviewer",
            detail=text[-1500:],
            duration_seconds=duration,
        )

    not_met = [
        c for c in verdict.get("criteria", [])
        if str(c.get("verdict", "")).lower() == "not_met"
    ]
    overall_fail = str(verdict.get("overall", "")).lower() == "fail" or bool(not_met)

    if overall_fail:
        findings = [
            f"criterion {c.get('index', '?')}: {c.get('reason', 'not met')}"
            for c in not_met
        ] or ["reviewer marked the feature overall=fail"]
        return GauntletLayerResult(
            layer="L8-oracle", status=LayerStatus.FAILED, blocking=True,
            summary=(
                f"oracle ({reviewer}): {len(not_met)} acceptance "
                "criterion(s) not met"
            ),
            detail="\n".join(findings),
            duration_seconds=duration,
            findings=findings,
        )
    return GauntletLayerResult(
        layer="L8-oracle", status=LayerStatus.PASSED, blocking=True,
        summary=f"oracle ({reviewer}): all acceptance criteria met",
        duration_seconds=duration,
    )
