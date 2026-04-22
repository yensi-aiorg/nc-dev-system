OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db668-2114-7c30-8e32-fff70131e58f
--------
user
# Peer review request — Round 4

You are Codex. This is the fourth pass. Your three previous reviews
are on disk at `docs/codex-review/review-response.md`,
`review-response-round2.md`, and `review-response-round3.md`.

Since R3 I committed `f80247f` on `claude-orchestrator-migration`.
It claims to close every item from your R3 review:

- **R3-A (the default-path blocker you called out)**: `_probe_health`
  now polls with short per-request timeout, retries on failure, honours
  the full `boot_timeout_seconds` as the startup grace budget.
- **R3-B**: `state_scanner.build_skip_results` now returns
  `StepStatus.SKIPPED`, not `PASSED`. Engine's `state.completed_features`
  counter adjusted to count PASSED + SKIPPED so the human-facing
  "done" number stays meaningful.
- **R3-C**: `metrics.py` now tracks `blocked_features` + `skipped_features`
  as detail, and `failed_features = FAILED + BLOCKED` so the
  run-level failure count matches the engine's overall-status
  computation.
- **R3-D**: `_TailBuffer` oversized single-chunk behaviour fixed —
  when one chunk > max_bytes, we slice the UTF-8 tail bytes of that
  chunk instead of evicting it wholesale.
- **R3-E**: `run_ai_session` catches `ValueError` from
  `_resolve_custom_providers` and returns a structured
  `ClaudeSessionResult(success=False, error=...)` with an actionable
  message naming the bad provider value.

426/426 tests passing. +8 regression tests.

Your job now:

1. **Verify R3 fixes landed correctly** — same drill as before, but
   focus specifically on the probe polling (your stated blocker),
   `_TailBuffer` edge cases, and the state_scanner semantic fix.
2. **Find bugs I introduced in the R3 pass.**
3. **Decide: ready to inherit?** You said R3 needed the probe fix +
   ideally the TailBuffer fix. Both are done. If anything else is
   still blocking, name it plainly. If not, say so plainly.

## Files to look at

- `src/ncdev/v3/claude_executor.py` around `_probe_health` — new
  polling loop. Is the time-budget math right? Does it respect
  `per_request_timeout`? What if `per_request_timeout > timeout`?
- `src/ncdev/ai_session.py` `_TailBuffer.append()` — new oversized-
  chunk branch. UTF-8 boundary safety on the slice? The decode uses
  `errors="ignore"` — is that acceptable?
- `src/ncdev/v3/state_scanner.py` `build_skip_results` — SKIPPED change.
- `src/ncdev/v3/engine.py` `state.completed_features` — PASSED+SKIPPED.
- `src/ncdev/v3/metrics.py` `compute_run_metrics` — BLOCKED accounting.
- `src/ncdev/ai_session.py` `run_ai_session` — new ValueError catch.

## Specific questions

1. **Probe polling math.** The loop is:
   ```python
   deadline = time.time() + max(timeout, 1)
   while time.time() < deadline:
       ...
       time.sleep(min(poll_interval, max(deadline - time.time(), 0)))
   ```
   Is there a case where a single request's `req_timeout` is tiny
   (because the remaining budget is <5s) and we burn through attempts
   too fast? Is `min(per_request_timeout, remaining)` right when
   `remaining` is 0.1s?
2. **`_TailBuffer` UTF-8 boundary.** Slicing bytes at `-self._max:`
   can land mid-codepoint. `decode(errors="ignore")` drops the broken
   bytes. That's what I wanted, but it means callers see slightly less
   than `max_bytes` in the common case. Acceptable?
3. **`state.completed_features` semantics.** Human reads the run
   panel and sees "3/5 features completed". After R3-B, that 3 now
   includes features the state scanner skipped as brownfield-already-
   done. Is that the right human reading, or should the panel separate
   "built" from "already there"? (Low priority, UX question.)
4. **Metrics throughput math.** `feature_throughput_per_hour` divides
   `len(passed)` by duration. With R3-B, brownfield-skipped features
   are SKIPPED (not PASSED), so they're excluded from throughput —
   correct, because we didn't actually build them. Agree?

## Output shape

Keep it tight. If the blocker list is empty, say so.

```
## R3 fixes verified

## R3 fixes that still didn't land

## New issues introduced in R3

## Ready to inherit?

## Honest one-liner
```

Last round unless you find something real.

codex
Reviewing the delta around the R3 fixes first, with emphasis on the probe loop, `_TailBuffer`, and the skip-state semantics. Then I’ll check the new regression tests against the code paths they claim to cover and look for any fresh regressions introduced by `f80247f`.
exec
/bin/zsh -lc 'git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && git show --stat --oneline --no-patch f80247f && rg -n "def _probe_health|deadline = time.time|per_request_timeout|req_timeout|_TailBuffer|build_skip_results|completed_features|compute_run_metrics|ValueError|_resolve_custom_providers|feature_throughput_per_hour" src tests' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
claude-orchestrator-migration
f80247f58acf3412c7fe3b82f90aa33335cdfcc3
f80247f fix(hardening-r3): address R3 regressions from Codex round-3 review
src/ncdev/provider_dispatch.py:64:        raise ValueError(
src/ncdev/provider_dispatch.py:81:        raise ValueError(
tests/test_ncdev_v3/test_state_scanner.py:7:    build_skip_results,
tests/test_ncdev_v3/test_state_scanner.py:8:    scan_completed_features,
tests/test_ncdev_v3/test_state_scanner.py:61:def test_build_skip_results():
tests/test_ncdev_v3/test_state_scanner.py:66:    results = build_skip_results(features, {"f1", "f3"})
tests/test_ncdev_v3/test_state_scanner.py:74:def test_scan_completed_features_no_git(tmp_path):
tests/test_ncdev_v3/test_state_scanner.py:77:    result = scan_completed_features(tmp_path, features)
tests/test_ncdev_v3/test_state_scanner.py:81:def test_scan_completed_features_with_git(tmp_path):
tests/test_ncdev_v3/test_state_scanner.py:101:    result = scan_completed_features(tmp_path, features)
src/ncdev/cli.py:376:        console.print(f"features: {state.completed_features}/{state.total_features} passed")
tests/unit/test_ai_provider.py:42:        with pytest.raises(ValueError, match="Unknown AI provider 'gpt4'"):
tests/unit/test_ai_provider.py:143:        with pytest.raises(ValueError):
tests/unit/test_ai_provider.py:148:            with pytest.raises(ValueError):
tests/test_ncdev_v3/test_metrics.py:1:from ncdev.v3.metrics import compute_run_metrics
tests/test_ncdev_v3/test_metrics.py:18:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:37:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:55:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:64:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:74:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:94:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:108:    m = compute_run_metrics(state, ingestion_doc_count=12)
tests/unit/test_claude_executor.py:353:        per_request_timeout=1,
tests/unit/test_claude_executor.py:375:        per_request_timeout=1,
tests/unit/test_claude_executor.py:402:        per_request_timeout=5,
tests/test_ncdev_v2/test_modes.py:63:    with pytest.raises(ValueError, match="Unknown mode"):
tests/unit/test_ai_session.py:30:    user's hand-tuned routing via _resolve_custom_providers."""
tests/unit/test_ai_session.py:197:    ValueError uncaught mid-run. Now must surface as a structured
tests/unit/test_ai_session.py:355:    """Codex R3 flagged: _TailBuffer(10).append('x' * 25) previously
tests/unit/test_ai_session.py:357:    from ncdev.ai_session import _TailBuffer
tests/unit/test_ai_session.py:359:    buf = _TailBuffer(10)
tests/unit/test_ai_session.py:370:    from ncdev.ai_session import _TailBuffer
tests/unit/test_ai_session.py:372:    buf = _TailBuffer(10)
tests/unit/test_ai_session.py:386:    from ncdev.ai_session import _TailBuffer
tests/unit/test_ai_session.py:388:    buf = _TailBuffer(5)
src/ncdev/v3/models.py:122:    completed_features: int = 0
src/ncdev/v3/claude_executor.py:534:def _probe_health(
src/ncdev/v3/claude_executor.py:538:    per_request_timeout: int = 5,
src/ncdev/v3/claude_executor.py:556:    deadline = time.time() + max(timeout, 1)
src/ncdev/v3/claude_executor.py:561:        req_timeout = min(per_request_timeout, remaining)
src/ncdev/v3/claude_executor.py:563:            r = httpx.get(url, timeout=req_timeout)
tests/conftest.py:1212:                    "error": "AssertionError: Expected status 'invalid' to raise ValueError",
src/ncdev/v3/charter.py:212:    except (FileNotFoundError, json.JSONDecodeError, ValueError):
src/ncdev/v3/metrics.py:41:    feature_throughput_per_hour: float = 0.0
src/ncdev/v3/metrics.py:49:def compute_run_metrics(
src/ncdev/v3/metrics.py:113:        feature_throughput_per_hour=(
src/ncdev/v3/state_scanner.py:21:def scan_completed_features(
src/ncdev/v3/state_scanner.py:54:def build_skip_results(
src/ncdev/v3/engine.py:209:        remaining = _filter_completed_features(target_path, features, completed)
src/ncdev/v3/engine.py:263:            state.completed_features = len([
src/ncdev/v3/engine.py:317:def _filter_completed_features(target_path: Path, features, completed: list[StepResult]):
src/ncdev/v3/engine.py:320:        from ncdev.v3.state_scanner import build_skip_results, scan_completed_features
src/ncdev/v3/engine.py:324:        done_ids = set(scan_completed_features(target_path, features))
src/ncdev/v3/engine.py:329:    skipped = build_skip_results(features, done_ids)
tests/test_ncdev_v2/test_sentinel_safety.py:197:        key = DeduplicationTracker.make_key("svc", "file.py", "func", "ValueError")
tests/test_ncdev_v2/test_sentinel_safety.py:202:        key = DeduplicationTracker.make_key("svc", "file.py", "func", "ValueError")
tests/test_ncdev_v2/test_sentinel_safety.py:208:        key = DeduplicationTracker.make_key("svc", "file.py", "func", "ValueError")
src/ncdev/ai_provider.py:420:    Raises :class:`ValueError` for unknown provider names.
src/ncdev/ai_provider.py:423:        raise ValueError(
src/ncdev/ai_provider.py:438:    Raises :class:`ValueError` if neither name is valid.
src/ncdev/ai_session.py:75:def _resolve_custom_providers(cfg: NCDevV2Config) -> tuple[str, str]:
src/ncdev/ai_session.py:141:            orch, impl = _resolve_custom_providers(cfg)
src/ncdev/ai_session.py:142:        except ValueError as exc:
src/ncdev/ai_session.py:271:    stdout_buf = _TailBuffer(max_bytes_per_stream)
src/ncdev/ai_session.py:272:    stderr_buf = _TailBuffer(max_bytes_per_stream)
src/ncdev/ai_session.py:274:    def _drain(stream, buf: "_TailBuffer") -> None:
src/ncdev/ai_session.py:361:class _TailBuffer:
src/ncdev/v2/config.py:188:            raise ValueError(

exec
/bin/zsh -lc "sed -n '1,260p' src/ncdev/v3/claude_executor.py && printf '\\n---FILE---\\n' && sed -n '1,260p' src/ncdev/ai_session.py && printf '\\n---FILE---\\n' && sed -n '1,240p' src/ncdev/v3/state_scanner.py && printf '\\n---FILE---\\n' && sed -n '1,260p' src/ncdev/v3/engine.py && printf '\\n---FILE---\\n' && sed -n '1,260p' src/ncdev/v3/metrics.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Phase E — Claude-driven feature executor.

Replaces the old ``step_executor.py`` manual build/verify/repair loop.
For each feature we spawn exactly one Claude session. Claude drives
the full build using its own skill machinery:

    * ``writing-plans``                 — if the feature is complex
    * ``test-driven-development``       — write failing test, then code
    * ``verification-before-completion`` — no "done" without evidence
    * ``systematic-debugging``          — when verification fails

Claude shells out to Codex via Bash for implementation and test writing
(the Codex-via-bash protocol is injected automatically by
:func:`run_claude_session`).  NC Dev orchestrates the outer loop only:

    1. Compose the feature prompt (charter refs, prior results, asset
       manifest requirement, verification contract).
    2. Run the session. Stream events.
    3. Inspect git state afterwards:
         * clean working tree + new commit(s) → PASSED
         * changes present but no commit     → commit with [BROKEN] tag
         * no changes at all                 → FAILED, builder didn't do anything
    4. Run post-hoc verification: manifest covers refs, required files exist.
    5. Return StepResult. Orchestrator moves to the next feature.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import (
    DEFAULT_BUILD_TOOLS,
    ClaudeSessionResult,
)
from ncdev.v2.config import NCDevV2Config
from ncdev.v3.asset_manifest import (
    manifest_prompt_section,
    verify_manifest_covers_references,
)
from ncdev.v3.models import (
    CharterBundle,
    FeatureStep,
    StepResult,
    StepStatus,
    StepVerification,
    TestResult,
)


# ---------------------------------------------------------------------------
# Prompt composition
# ---------------------------------------------------------------------------


def build_feature_prompt(
    feature: FeatureStep,
    target_path: Path,
    charter_dir: Path,
    prior_feature_ids: list[str],
    project_id: str,
    citex_url: str = "http://localhost:20161",
) -> str:
    """Compose the single prompt handed to Claude for this feature.

    Deliberately terse. Heavy reference material (contract, verification,
    design system) stays on disk — Claude reads it with the Read tool.
    This is a departure from the old prescriptive mega-prompts.
    """
    prior_block = (
        "No prior features — this is the first build in the queue."
        if not prior_feature_ids
        else f"Prior features already built and verified: {', '.join(prior_feature_ids)}"
    )

    return f"""# Feature: {feature.feature_id} — {feature.title}

You are the engineer for this feature. You have the Claude skill
machinery available; use it. Codex is your implementation peer
(see the Codex protocol in your system prompt) — delegate raw
implementation and test writing to Codex via Bash, keep judgment
and review yourself.

## Context

- Project charter:        {charter_dir}/target-project-contract.json
- Verification contract:  {charter_dir}/verification-contract.json
- Design system:          {charter_dir}/design-system.json  (if present)
- Feature queue:          {charter_dir}/feature-queue.json
- Target repository:      {target_path}
- Citex project ID:       {project_id}
- Citex URL:              {citex_url}

{prior_block}

## Your feature spec

- ID:          {feature.feature_id}
- Title:       {feature.title}
- Description: {feature.description}
- Complexity:  {feature.estimated_complexity}
- Priority:    {feature.priority}

### Acceptance criteria
{chr(10).join(f"- {c}" for c in feature.acceptance_criteria) or "- (none specified — infer from description)"}

### Test requirements
{chr(10).join(f"- {t}" for t in feature.test_requirements) or "- (use your judgment — tests MUST exist and verify behaviour, not just syntax)"}

### Depends on
{", ".join(feature.depends_on_features) if feature.depends_on_features else "(none)"}

## Required workflow

1. **Read** the charter artifacts listed above. They are the hard
   constraints for stack, ports, auth, deployment. Do not override them.
2. **Query Citex** (the RAG system at `{citex_url}`) for anything you
   need to know about prior features, data models, or existing code.
   Use Bash if Citex exposes a CLI, or read the local `.ncdev/` cache.
3. **Use the `writing-plans` skill** if this is a high-complexity
   feature. For low complexity, go straight to step 4.
4. **Use the `test-driven-development` skill**. Write failing tests
   first (you may delegate the test file content to Codex via Bash).
5. **Delegate implementation to Codex via Bash**. One well-scoped
   Codex call per sub-task is better than five vague ones. Review
   Codex's output yourself before moving on.
6. **Emit the asset manifest** as you build — see the schema below.
7. **Use the `verification-before-completion` skill** before you
   claim done. Run the verification contract's test commands yourself.
   Run the app and probe its health endpoint. Capture the required
   screenshots listed in the verification contract.
8. **If verification fails**, use the `systematic-debugging` skill.
   Do not loop blindly — identify root cause, fix narrowly, re-verify.
9. **Commit the work** once verification passes. Use Conventional
   Commits (feat/fix/test) referencing the feature_id. Leave the
   working tree clean.

{manifest_prompt_section(feature.feature_id)}

## What success looks like

- Working tree is clean (all changes committed).
- The feature's tests exist, run, and pass.
- Verification contract is satisfied (boot, tests, screenshots, files).
- Asset manifest file exists at
  `.ncdev/assets-needed/{feature.feature_id}.json`.
- Your final response summarises what was built in <= 5 sentences.

## What failure looks like (avoid)

- "Implemented, but tests are still failing — here's what I tried."
  → Not done. Use systematic-debugging.
- Working tree dirty when you're "done." → Commit or revert.
- Asset manifest missing. → Write it before committing.
- Any of the `prohibited_patterns` in the verification contract
  landed in a commit. → Those are pre-commit-hook blockers; fix.

Begin.
"""


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


def execute_feature_claude_driven(
    feature: FeatureStep,
    target_path: Path,
    run_dir: Path,
    charter_bundle: CharterBundle,
    prior_results: list[StepResult],
    project_id: str,
    *,
    model: str | None = None,
    timeout: int = 3600,
    max_budget_usd: float | None = None,
    citex_url: str = "http://localhost:20161",
    config: NCDevV2Config | None = None,
    run_test_commands: bool = True,
    probe_health: bool = True,
) -> StepResult:
    """Run one feature via a Claude session and return the StepResult.

    See module docstring for the outer flow.
    """
    step_dir = run_dir / "steps" / feature.feature_id
    step_dir.mkdir(parents=True, exist_ok=True)

    charter_dir = run_dir / "outputs"
    prior_ids = [r.feature_id for r in prior_results if r.status == StepStatus.PASSED]

    prompt = build_feature_prompt(
        feature=feature,
        target_path=target_path,
        charter_dir=charter_dir,
        prior_feature_ids=prior_ids,
        project_id=project_id,
        citex_url=citex_url,
    )
    (step_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    # Snapshot git state so we can detect what changed
    pre_commit = _git_head(target_path)

    start = time.time()
    session = run_ai_session(
        prompt,
        cwd=target_path,
        config=config,
        workspace=run_dir.parent.parent.parent if run_dir.parent.parent.parent.exists() else None,
        tools=DEFAULT_BUILD_TOOLS,
        model=model,
        timeout=timeout,
        permission_mode="acceptEdits",
        max_budget_usd=max_budget_usd,
        log_path=step_dir / "session.jsonl",
    )
    build_duration = time.time() - start

    # Save session summary for debugging
    (step_dir / "session-summary.txt").write_text(session.summary(), encoding="utf-8")
    if session.final_text:
        (step_dir / "final-response.md").write_text(session.final_text, encoding="utf-8")

    post_commit = _git_head(target_path)
    made_commit = bool(post_commit and post_commit != pre_commit)
    dirty = _git_working_tree_dirty(target_path)

    # Files the feature actually touched — used for feature-local asset
    # manifest verification so one legacy unmanaged asset elsewhere in
    # the repo doesn't fail every future feature.
    feature_files_created, feature_files_modified = _diff_since(target_path, pre_commit)
    touched = feature_files_created + feature_files_modified

    # Post-hoc verification (Claude's own verification-before-completion
    # skill should have caught most things; this is our belt-and-braces)
    verification = _post_session_verification(
        target_path, feature, charter_bundle,
        run_test_commands=run_test_commands,
        probe_health=probe_health,
        touched_files=touched,
    )

    # Decide status
    recoverability_note = ""
    if session.success and made_commit and not dirty and verification.overall_passed:
        status = StepStatus.PASSED
    elif made_commit and verification.overall_passed:
        # Claude might have exited with non-zero for trivial reasons; if
        # the commit and verification are good, we accept.
        status = StepStatus.PASSED
    else:

---FILE---
"""Unified AI session runner — dispatches on mode.

``run_ai_session()`` is the single entry point every phase of NC Dev
calls when it needs an AI-driven session. It reads ``NCDevV2Config.mode``
and dispatches to the right concrete runner:

    * ``claude_plan_codex_build`` → Claude session, Codex protocol
      injected so Claude shells to ``codex exec`` for implementation.
    * ``claude_only`` → Claude session, Codex protocol NOT injected;
      Claude does implementation itself.
    * ``codex_only`` → Codex CLI session, no skills / subagents / hooks;
      Codex handles the whole task directly.
    * ``openrouter`` → raises ``NotImplementedError`` (API-only, no CLI
      tooling). Caller should fall back or surface to the user.
    * ``custom`` → falls back to Claude orchestrator as a safe default.

The returned :class:`ClaudeSessionResult` is the common result shape
across runners — ``skills_invoked`` and ``codex_invocations`` are
populated only when they applied.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

_IS_POSIX = sys.platform != "win32"

# Upper bound per stream for run_codex_session capture. A chatty codex
# run can produce a lot — we keep the tail (recent output is more
# useful than the head) and note truncation.
_CODEX_CAPTURE_MAX_BYTES = 4 * 1024 * 1024   # 4 MB per stream

from ncdev.claude_session import (
    DEFAULT_BUILD_TOOLS,
    ClaudeSessionResult,
    NCDEV_HOOKS_DIR,
    NCDEV_HOOKS_SETTINGS,
    run_claude_session,
)
from ncdev.v2.config import NCDevV2Config, load_v2_config

logger = logging.getLogger(__name__)


# Mode → which provider runs the main orchestrator session.
# "custom" is intentionally absent — it's handled by consulting the
# user's hand-tuned routing via provider_dispatch instead.
MODE_ORCHESTRATOR: dict[str, str] = {
    "claude_plan_codex_build": "claude",
    "claude_only": "claude",
    "codex_only": "codex",
    "openrouter": "openrouter",
}

# Mode → who actually writes code. Used by the Claude runner to decide
# whether to inject the Codex-via-Bash protocol (i.e. "delegate impl
# to Codex") vs do the work itself.
MODE_IMPLEMENTER: dict[str, str] = {
    "claude_plan_codex_build": "codex",
    "claude_only": "claude",
    "codex_only": "codex",
    "openrouter": "openrouter",
}


def _resolve_custom_providers(cfg: NCDevV2Config) -> tuple[str, str]:
    """For ``mode=custom``, read orchestrator + implementer from routing.

    Honours the contract stated in v2/config.py: ``custom`` preserves
    the user's hand-tuned ``routing:`` block. We use routing.review to
    pick the orchestrator (review is the "who reasons about code" task)
    and routing.implementation to pick the implementer.

    Both are mapped through :func:`provider_dispatch.resolve_provider_name`
    so long names like ``anthropic_claude_code`` become short
    registry keys (``claude``, ``codex``, ``openrouter``).
    """
    from ncdev.provider_dispatch import resolve_provider_name

    review_chain = cfg.routing.review or ["anthropic_claude_code"]
    impl_chain = cfg.routing.implementation or ["openai_codex"]
    orch = resolve_provider_name(review_chain[0])
    impl = resolve_provider_name(impl_chain[0])
    return orch, impl


def _resolve_config(
    config: NCDevV2Config | None,
    workspace: Path | None,
) -> NCDevV2Config:
    if config is not None:
        return config
    if workspace is not None:
        try:
            return load_v2_config(workspace)
        except Exception:  # noqa: BLE001
            pass
    return NCDevV2Config()


def run_ai_session(
    prompt: str,
    *,
    cwd: Path,
    config: NCDevV2Config | None = None,
    workspace: Path | None = None,
    tools: Iterable[str] = DEFAULT_BUILD_TOOLS,
    model: str | None = None,
    timeout: int = 1800,
    permission_mode: str = "acceptEdits",
    append_system_prompt: str | None = None,
    include_codex_protocol: bool | None = None,
    max_budget_usd: float | None = None,
    log_path: Path | None = None,
    on_event: Callable[[dict], None] | None = None,
    extra_args: list[str] | None = None,
    settings_path: Path | None = None,
    enable_ncdev_hooks: bool = True,
) -> ClaudeSessionResult:
    """Run an AI session, dispatching on the active mode.

    ``include_codex_protocol`` defaults to ``True`` when the mode's
    implementer is Codex (i.e. Claude should delegate), ``False`` when
    implementer is Claude. Explicit values win.
    """
    cfg = _resolve_config(config, workspace)

    if cfg.mode == "custom":
        # Honour the hand-tuned routing block — this is exactly what
        # "custom" means per the config contract.
        try:
            orch, impl = _resolve_custom_providers(cfg)
        except ValueError as exc:
            # Unknown provider name in routing — surface as a structured
            # session failure, not an uncaught exception mid-run.
            return ClaudeSessionResult(
                success=False, final_text="", exit_code=-1,
                error=(
                    f"custom mode config error: {exc}. "
                    "Check `routing.review` and `routing.implementation` "
                    "in .nc-dev/v2/config.yaml — allowed values are "
                    "'anthropic_claude_code', 'openai_codex', 'openrouter', "
                    "or the short aliases 'claude' / 'codex'."
                ),
            )
    else:
        orch = MODE_ORCHESTRATOR.get(cfg.mode, "claude")
        impl = MODE_IMPLEMENTER.get(cfg.mode, "codex")

    logger.info("run_ai_session mode=%s orch=%s impl=%s cwd=%s", cfg.mode, orch, impl, cwd)

    if orch == "openrouter":
        raise NotImplementedError(
            "openrouter mode is API-only and cannot spawn a file-editing "
            "session. Install and configure the Claude or Codex CLI and "
            "pick a CLI mode (claude_plan_codex_build, claude_only, or "
            "codex_only)."
        )

    if orch == "codex":
        return run_codex_session(
            prompt,
            cwd=cwd,
            timeout=timeout,
            model=model,
            log_path=log_path,
            extra_args=extra_args,
        )

    # orch == "claude"
    if include_codex_protocol is None:
        include_codex_protocol = (impl == "codex")

    effective_model = model or "claude-opus-4-6"
    return run_claude_session(
        prompt,
        cwd=cwd,
        tools=tools,
        model=effective_model,
        timeout=timeout,
        permission_mode=permission_mode,
        append_system_prompt=append_system_prompt,
        include_codex_protocol=include_codex_protocol,
        max_budget_usd=max_budget_usd,
        log_path=log_path,
        on_event=on_event,
        extra_args=extra_args,
        settings_path=settings_path,
        enable_ncdev_hooks=enable_ncdev_hooks,
    )


# ---------------------------------------------------------------------------
# Codex runner — used by codex_only mode
# ---------------------------------------------------------------------------


def run_codex_session(
    prompt: str,
    *,
    cwd: Path,
    timeout: int = 1800,
    model: str | None = None,
    log_path: Path | None = None,
    extra_args: list[str] | None = None,
    max_bytes_per_stream: int = _CODEX_CAPTURE_MAX_BYTES,
) -> ClaudeSessionResult:
    """Run a Codex session. No skills, no subagents, no NC Dev hooks.

    Uses the same safety primitives as :func:`run_claude_session`:
    thread-per-pipe readers so backpressure can't deadlock the child,
    watchdog that kills the process group on wall-clock timeout, and
    a tail-bounded byte buffer per stream so a chatty Codex run
    doesn't blow RAM. Returns the same :class:`ClaudeSessionResult`
    shape (common result type across runners).
    """
    if shutil.which("codex") is None:
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error="codex CLI not found on PATH",
        )

    # Codex prompt must be scoped — no Claude skill references.
    codex_prompt = (
        prompt
        + "\n\n---\n\n"
        + "You are running in codex_only mode (no Claude orchestrator). "
        "Produce a plan, implement, write tests, and commit with "
        "Conventional Commits. Leave the working tree clean when done."
    )

    cmd: list[str] = [
        "codex", "exec",
        "--full-auto",
        "--sandbox", "danger-full-access",
    ]
    if model:
        cmd += ["--model", model]
    if extra_args:
        cmd += list(extra_args)
    cmd.append(codex_prompt)

    popen_kwargs: dict = dict(
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if _IS_POSIX:
        popen_kwargs["start_new_session"] = True

---FILE---
"""Project state scanner — determines which features are already implemented.

Scans the target repo's git history, file tree, and test results to figure out
what's already built, so the engine can skip completed work and resume from
where the previous run left off.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from ncdev.v3.models import FeatureStep, StepResult, StepStatus

console = Console()


def scan_completed_features(
    target_path: Path,
    feature_queue: list[FeatureStep],
) -> list[str]:
    """Scan the target repo and return feature_ids that are already done.

    A feature is considered done if:
    1. It appears in a git commit message (feat(feature_id): ...), OR
    2. Key files described by its title/description exist in the repo, AND
    3. The project's tests pass (basic smoke check)
    """
    if not (target_path / ".git").exists():
        return []

    git_log = _get_git_log(target_path)
    file_tree = _get_file_set(target_path)
    tests_pass = _run_smoke_test(target_path)

    completed: list[str] = []

    for feature in feature_queue:
        # Check 1: Is this feature in the git history?
        in_git = _feature_in_git_history(feature, git_log)

        # Check 2: Do files related to this feature exist?
        has_files = _feature_has_files(feature, file_tree)

        if tests_pass and (in_git or has_files):
            completed.append(feature.feature_id)

    return completed


def build_skip_results(
    feature_queue: list[FeatureStep],
    completed_ids: set[str],
) -> list[StepResult]:
    """Create SKIPPED StepResults for already-completed brownfield features.

    Uses :attr:`StepStatus.SKIPPED` — these features were done before
    this run started. The dependency gate treats SKIPPED as dep-
    satisfying, and metrics / summary correctly exclude them from
    PASSED / BLOCKED / FAILED counters.
    """
    return [
        StepResult(
            feature_id=f.feature_id,
            status=StepStatus.SKIPPED,
            error_message="Already implemented in target repo (state-scanner detection)",
        )
        for f in feature_queue
        if f.feature_id in completed_ids
    ]


def _get_git_log(target_path: Path) -> str:
    """Get full git log with commit messages."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--all", "-200"],
            cwd=str(target_path),
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.lower() if result.returncode == 0 else ""
    except Exception:
        return ""


def _get_file_set(target_path: Path) -> set[str]:
    """Get set of all file paths in the repo (relative, lowercase)."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(target_path),
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        pass
    return set()


def _run_smoke_test(target_path: Path) -> bool:
    """Quick check: do backend tests pass? (or at least not crash)"""
    backend = target_path / "backend"
    if not backend.exists():
        # Maybe tests are at root level
        backend = target_path

    has_tests = any(backend.rglob("test_*.py")) or any(backend.rglob("*_test.py"))
    if not has_tests:
        return True

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "--no-header"],
            cwd=str(backend),
            capture_output=True, text=True, timeout=60,
        )
        # Accept green runs and partially green runs that still discovered passing tests.
        if result.returncode == 0 or "passed" in result.stdout:
            return True

        combined_output = f"{result.stdout}\n{result.stderr}".lower()

        # Brownfield repos often do not have pytest wired yet. That should not block
        # feature detection entirely.
        non_blocking_markers = [
            "no tests ran",
            "collected 0 items",
            "unrecognized arguments: --timeout=30",
            "module named pytest",
        ]
        return any(marker in combined_output for marker in non_blocking_markers)
    except Exception:
        return False


def _feature_in_git_history(feature: FeatureStep, git_log: str) -> bool:
    """Check if a feature appears in git commit messages."""
    feature_id_lower = feature.feature_id.lower()
    title_lower = feature.title.lower()

    # Direct feature ID match: feat(sprint-0):, feat(feature-01):, [feature-01]
    if feature_id_lower in git_log:
        return True

    # Title keywords match (at least 3 significant words from title in same commit line)
    title_words = [w for w in re.split(r'\W+', title_lower) if len(w) > 3]
    if len(title_words) >= 2:
        for line in git_log.splitlines():
            matches = sum(1 for w in title_words if w in line)
            if matches >= min(3, len(title_words)):
                return True

    return False


def _feature_has_files(feature: FeatureStep, file_tree: set[str]) -> bool:
    """Check if files related to the feature exist in the repo.

    For sprint-0 (scaffold): check for fundamental files.
    For other features: check for feature-specific files using title keywords.
    """
    fid = feature.feature_id.lower()

    # Sprint-0: scaffold is done if basic project structure exists
    if "sprint-0" in fid or "scaffold" in feature.title.lower():
        scaffold_markers = [
            "backend/app/main.py",
            "backend/requirements.txt",
            "docker-compose.yml",
        ]
        found = sum(1 for m in scaffold_markers if m in file_tree)
        return found >= 2

    # For other features: extract keywords from title and check file tree
    title_words = [w.lower() for w in re.split(r'\W+', feature.title) if len(w) > 3]
    if not title_words:
        return False

    # Check if any file path contains feature keywords (prefix match for stems)
    keyword_hits = 0
    for word in title_words:
        # Use first 4+ chars as stem to match "auth" in path against "authentication" in title
        stem = word[:4] if len(word) > 4 else word
        for fpath in file_tree:
            if stem in fpath:
                keyword_hits += 1
                break

    # Need at least 1 keyword match to consider the feature has files
    return keyword_hits >= 1

---FILE---
"""V3 Engine — sequential verified sprint pipeline (Claude-orchestrated).

This is the PRD-scale entry point. Replaces the old 9-artifact discovery
+ per-task-routing + parallel-builder pipeline with a thin outer loop:

    Phase 1 — Preflight                        (this module)
    Phase 2 — Charter generation                (v3.charter)
    Phase 3 — Design system                     (v3.design_phase)
    Phase 4 — Context ingestion into Citex      (v3.context_ingestion — brownfield)
    Phase 5 — Sequential feature execution      (v3.claude_executor)
    Phase 6 — Summary + metrics                 (this module)

Each phase is a Claude session (or a no-op for greenfield/skipped cases).
NC Dev itself just:

    * checks preconditions (git, claude, codex, Citex)
    * hands artifacts between phases
    * enforces hard-fail on Phase C for greenfield UI without designs
    * commits on pass, tags [BROKEN] on exhaustion
    * rolls up metrics at the end

The old run_v3_full() interface is preserved so the ``ncdev full`` CLI
command doesn't need to change.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ncdev.utils import make_run_id, write_json
from ncdev.v2.config import NCDevV2Config, ensure_default_v2_config, load_v2_config
from ncdev.v3.charter import generate_charter, load_charter, write_charter
from ncdev.v3.claude_executor import execute_feature_claude_driven
from ncdev.v3.design_phase import run_design_phase
from ncdev.v3.models import (
    CharterBundle,
    StepResult,
    StepStatus,
    V3RunState,
)

console = Console()


def run_v3_full(
    workspace: Path,
    source_path: Path,
    base_url: str = "http://localhost:23000",
    dry_run: bool = False,
    target_repo_path: Path | None = None,
    run_id: str | None = None,
    builder_model: str | None = None,
    builder_timeout: int = 3600,
    max_budget_usd: float | None = None,
    config: NCDevV2Config | None = None,
    strict_deps: bool = False,
    # Retained for CLI signature compat; Claude's systematic-debugging
    # skill handles repair now, so this is a no-op.
    max_repair_attempts: int | None = None,
) -> V3RunState:
    """Run the full V3 pipeline on a PRD.

    Entry point for ``ncdev full --source <prd>``.
    """
    # ── Phase 1: Preflight + workspace setup ─────────────────────────────
    run_id = run_id or make_run_id("v3")
    run_dir = workspace / ".nc-dev" / "v2" / "runs" / run_id
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # Mode-aware config: single source of truth for which CLI runs each
    # session. Load once, pass through every phase.
    if config is None:
        try:
            config = ensure_default_v2_config(workspace)
        except Exception:  # noqa: BLE001
            config = NCDevV2Config()

    state = V3RunState(
        run_id=run_id,
        workspace=str(workspace),
        run_dir=str(run_dir),
        target_path=str(target_repo_path) if target_repo_path else "",
        phase="init",
    )

    console.print(Panel(
        f"[bold cyan]NC Dev V3 — {config.mode} mode[/bold cyan]\n"
        f"Run ID: {run_id}\n"
        f"Source: {source_path}\n"
        f"Target: {target_repo_path or '(greenfield)'}",
        border_style="cyan",
    ))

    # ── Phase 2: Charter ─────────────────────────────────────────────────
    state.phase = "charter"
    console.print("\n[bold]Phase 2: Charter (Claude planning session)[/bold]")

    if dry_run:
        console.print("  [dim]Dry run — skipping charter generation[/dim]")
        bundle = None
    else:
        bundle, charter_session = generate_charter(
            prd_path=source_path,
            output_dir=outputs_dir,
            target_repo=target_repo_path,
            model=builder_model,
            max_budget_usd=max_budget_usd,
            log_path=run_dir / "logs" / "charter.jsonl",
            config=config,
        )
        if bundle is None:
            console.print(Panel(
                f"[bold red]Charter generation failed[/bold red]\n"
                f"Session: {charter_session.summary()}\n"
                f"See: {outputs_dir}/charter-error.json (if present) "
                f"or run log at {run_dir}/logs/charter.jsonl",
                border_style="red",
            ))
            state.phase = "failed"
            state.status = "failed"
            _persist_state(state, run_dir)
            return state
        console.print(f"  [green]✓[/green] Charter: {len(bundle.feature_queue.features)} features queued")

    # Resolve target path now that we have the charter
    target_path = (
        Path(bundle.contract.existing_repo_path).expanduser().resolve()
        if bundle and bundle.contract.existing_repo_path
        else (target_repo_path or (workspace / (bundle.contract.project_name if bundle else "project"))).resolve()
    )
    target_path.mkdir(parents=True, exist_ok=True)
    state.target_path = str(target_path)

    # ── Phase 3: Design system ───────────────────────────────────────────
    state.phase = "design"
    console.print("\n[bold]Phase 3: Design system[/bold]")
    if dry_run or bundle is None:
        console.print("  [dim]Skipped[/dim]")
    else:
        design = run_design_phase(
            contract=bundle.contract,
            target_path=target_path,
            output_dir=outputs_dir,
            model=builder_model,
            max_budget_usd=max_budget_usd,
            log_path=run_dir / "logs" / "design.jsonl",
            config=config,
        )
        if design.skipped:
            console.print("  [dim]Non-UI project — design phase skipped[/dim]")
        elif design.hard_failed:
            console.print(Panel(
                f"[bold red]Design phase HARD FAILED[/bold red]\n"
                f"{design.error}\n"
                f"See: {outputs_dir}/design-phase-error.json",
                border_style="red",
            ))
            state.phase = "failed"
            state.status = "failed"
            _persist_state(state, run_dir)
            return state
        else:
            src = design.design_doc.source if design.design_doc else "?"
            console.print(f"  [green]✓[/green] Design system ready (source={src})")

    # ── Phase 4: Brownfield context ingestion ────────────────────────────
    state.phase = "ingestion"
    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
        console.print("\n[bold]Phase 4: Ingest existing code into Citex[/bold]")
        try:
            from ncdev.v3.citex_client import CitexClient
            from ncdev.v3.context_ingestion import ingest_project_context
            project_id = bundle.contract.project_name
            citex = CitexClient(project_id=project_id)
            if citex.health_check():
                report = ingest_project_context(
                    run_dir=run_dir,
                    target_path=target_path,
                    feature_queue=bundle.feature_queue,
                    project_id=project_id,
                )
                console.print(f"  [green]✓[/green] Ingested {report.successful}/{report.total_documents} docs")
            else:
                console.print("  [yellow]Citex unreachable — feature builds will run without RAG grounding[/yellow]")
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [yellow]Citex ingestion failed: {exc} — continuing without RAG[/yellow]")
    else:
        console.print("\n[dim]Phase 4: Context ingestion skipped (greenfield or dry run)[/dim]")

    # ── Phase 5: Sequential feature execution ────────────────────────────
    state.phase = "building"
    completed: list[StepResult] = []

    if dry_run or bundle is None:
        console.print("\n[dim]Phase 5: Feature execution skipped (dry run)[/dim]")
    else:
        features = bundle.feature_queue.features
        state.feature_queue = bundle.feature_queue
        state.total_features = len(features)

        # Brownfield: skip features already implemented
        remaining = _filter_completed_features(target_path, features, completed)
        console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")

        for feature in remaining:
            state.current_step = feature.feature_id
            _persist_state(state, run_dir)

            # Dependency gate: a feature whose depends_on_features contains
            # any non-PASSED id is skipped rather than built. In strict mode,
            # halt the whole run at the first broken dep.
            unmet = _unmet_dependencies(feature, completed)
            if unmet:
                reason = (
                    f"dependency not satisfied: {', '.join(unmet)} "
                    "(required feature(s) are not in PASSED state)"
                )
                console.print(Panel(
                    f"[red]BLOCKED[/red] {feature.feature_id} — {reason}",
                    border_style="red",
                ))
                completed.append(StepResult(
                    feature_id=feature.feature_id,
                    status=StepStatus.BLOCKED,
                    error_message=reason,
                ))
                state.completed_steps = completed
                _persist_state(state, run_dir)
                if strict_deps:
                    console.print("[red]--strict-deps set: halting run[/red]")
                    break
                continue

            console.print(Panel(
                f"[cyan]{feature.feature_id}[/cyan] — {feature.title}",
                border_style="blue",
            ))

            result = execute_feature_claude_driven(
                feature=feature,
                target_path=target_path,
                run_dir=run_dir,
                charter_bundle=bundle,
                prior_results=completed,
                project_id=bundle.contract.project_name,
                model=builder_model,
                timeout=builder_timeout,
                max_budget_usd=max_budget_usd,
                config=config,
            )
            completed.append(result)
            state.completed_steps = completed
            # Count PASSED + SKIPPED — both are "done from NC Dev's

---FILE---
"""Run-level build metrics for the V3 pipeline."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ncdev.v3.models import StepStatus, V3RunState


class FeatureMetric(BaseModel):
    """Per-feature effectiveness metrics."""

    feature_id: str
    status: str
    passed_first_try: bool
    repair_attempts: int = 0
    build_duration_seconds: float = 0.0
    verify_duration_seconds: float = 0.0
    files_created: int = 0
    files_modified: int = 0


class RunMetrics(BaseModel):
    """Aggregate metrics for one V3 run."""

    run_id: str
    project_name: str = ""
    started_at: str = ""
    completed_at: str = ""
    total_duration_seconds: float = 0.0
    total_features: int = 0
    passed_features: int = 0          # built successfully this run
    failed_features: int = 0          # tried and broke OR dep-blocked
    skipped_features: int = 0         # brownfield — already implemented
    blocked_features: int = 0         # broken dep cascaded here
    first_pass_success_rate: float = 0.0
    repair_rate: float = 0.0
    mean_repair_attempts: float = 0.0
    build_efficiency: float = 0.0
    feature_throughput_per_hour: float = 0.0
    features: list[FeatureMetric] = Field(default_factory=list)
    builder_primary: str = "codex"
    builder_model: str = "gpt-5.4"
    citex_documents_ingested: int = 0
    citex_queries_by_codex: int = 0


def compute_run_metrics(
    state: V3RunState,
    ingestion_doc_count: int = 0,
) -> RunMetrics:
    """Compute aggregate run metrics from the current V3 run state."""
    steps = state.completed_steps
    total = len(steps)

    if total == 0:
        return RunMetrics(run_id=state.run_id, started_at=state.started_at)

    passed = [s for s in steps if s.status == StepStatus.PASSED]
    # Both FAILED (tried and broke) and BLOCKED (upstream dep broke)
    # are failures at the run-metric level — they count against
    # failed_features so the number matches the engine's "unsuccessful"
    # run status. blocked_features is tracked separately for detail.
    failed_direct = [s for s in steps if s.status == StepStatus.FAILED]
    blocked = [s for s in steps if s.status == StepStatus.BLOCKED]
    failed = failed_direct + blocked
    skipped = [s for s in steps if s.status == StepStatus.SKIPPED]
    first_pass = [s for s in passed if s.repair_attempts == 0]
    repaired = [s for s in steps if s.repair_attempts > 0]

    build_sum = sum(s.build_duration_seconds for s in steps)
    verify_sum = sum(s.verify_duration_seconds for s in steps)
    total_active_time = build_sum + verify_sum

    started = _parse_iso(state.started_at)
    completed_at = state.updated_at or state.started_at
    completed = _parse_iso(completed_at)
    total_duration_seconds = max((completed - started).total_seconds(), 0.0)

    feature_metrics = [
        FeatureMetric(
            feature_id=s.feature_id,
            status=s.status.value,
            passed_first_try=(s.status == StepStatus.PASSED and s.repair_attempts == 0),
            repair_attempts=s.repair_attempts,
            build_duration_seconds=s.build_duration_seconds,
            verify_duration_seconds=s.verify_duration_seconds,
            files_created=len(s.files_created),
            files_modified=len(s.files_modified),
        )
        for s in steps
    ]

    return RunMetrics(
        run_id=state.run_id,
        project_name=_resolve_project_name(state),
        started_at=state.started_at,
        completed_at=completed_at,
        total_duration_seconds=total_duration_seconds,
        total_features=total,
        passed_features=len(passed),
        failed_features=len(failed),
        skipped_features=len(skipped),
        blocked_features=len(blocked),
        first_pass_success_rate=len(first_pass) / total,
        repair_rate=len(repaired) / total,
        mean_repair_attempts=(
            sum(s.repair_attempts for s in repaired) / len(repaired)
            if repaired else 0.0
        ),
        build_efficiency=build_sum / total_active_time if total_active_time > 0 else 0.0,
        feature_throughput_per_hour=(
            len(passed) / (total_duration_seconds / 3600.0) if total_duration_seconds > 0 else 0.0
        ),
        features=feature_metrics,
        citex_documents_ingested=ingestion_doc_count,
        citex_queries_by_codex=int(state.metadata.get("citex_queries_by_codex", 0)),
    )


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _resolve_project_name(state: V3RunState) -> str:
    if state.feature_queue and state.feature_queue.project_name:
        return state.feature_queue.project_name
    return str(state.metadata.get("project_id", "")) or "unknown"

codex
I’ve got the main code paths. Next I’m narrowing to the exact branches and test coverage, because the remaining risk here is not broad architecture anymore, it’s off-by-one timing, status semantics, and edge behavior under partial UTF-8 slices.
exec
/bin/zsh -lc 'git diff f80247f''^ f80247f -- src/ncdev/v3/claude_executor.py src/ncdev/ai_session.py src/ncdev/v3/state_scanner.py src/ncdev/v3/engine.py src/ncdev/v3/metrics.py tests/unit/test_claude_executor.py tests/unit/test_ai_session.py tests/test_ncdev_v3/test_state_scanner.py tests/test_ncdev_v3/test_metrics.py' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
diff --git a/src/ncdev/ai_session.py b/src/ncdev/ai_session.py
index dbd9ab6..dd4ce81 100644
--- a/src/ncdev/ai_session.py
+++ b/src/ncdev/ai_session.py
@@ -137,7 +137,21 @@ def run_ai_session(
     if cfg.mode == "custom":
         # Honour the hand-tuned routing block — this is exactly what
         # "custom" means per the config contract.
-        orch, impl = _resolve_custom_providers(cfg)
+        try:
+            orch, impl = _resolve_custom_providers(cfg)
+        except ValueError as exc:
+            # Unknown provider name in routing — surface as a structured
+            # session failure, not an uncaught exception mid-run.
+            return ClaudeSessionResult(
+                success=False, final_text="", exit_code=-1,
+                error=(
+                    f"custom mode config error: {exc}. "
+                    "Check `routing.review` and `routing.implementation` "
+                    "in .nc-dev/v2/config.yaml — allowed values are "
+                    "'anthropic_claude_code', 'openai_codex', 'openrouter', "
+                    "or the short aliases 'claude' / 'codex'."
+                ),
+            )
     else:
         orch = MODE_ORCHESTRATOR.get(cfg.mode, "claude")
         impl = MODE_IMPLEMENTER.get(cfg.mode, "codex")
@@ -350,6 +364,11 @@ class _TailBuffer:
     Recent output is more useful than the head when debugging a builder
     that went off the rails. ``truncated`` flips True once we start
     dropping bytes so callers can surface that to users / logs.
+
+    If a single incoming chunk is larger than ``max_bytes``, we slice
+    the tail bytes out of *that* chunk instead of evicting it wholesale
+    (Codex R3 flagged: the previous behavior produced an empty buffer
+    when a single append overflowed the cap).
     """
 
     __slots__ = ("_chunks", "_size", "_max", "truncated")
@@ -357,16 +376,30 @@ class _TailBuffer:
     def __init__(self, max_bytes: int) -> None:
         self._chunks: list[str] = []
         self._size = 0
-        self._max = max_bytes
+        self._max = max(max_bytes, 1)
         self.truncated = False
 
     def append(self, chunk: str) -> None:
         if not chunk:
             return
-        enc = len(chunk.encode("utf-8", errors="ignore"))
+
+        # Oversized single chunk: keep the tail bytes of this chunk only.
+        chunk_bytes = chunk.encode("utf-8", errors="ignore")
+        if len(chunk_bytes) > self._max:
+            tail_bytes = chunk_bytes[-self._max:]
+            tail = tail_bytes.decode("utf-8", errors="ignore")
+            self._chunks = [tail]
+            self._size = len(tail.encode("utf-8", errors="ignore"))
+            self.truncated = True
+            return
+
         self._chunks.append(chunk)
-        self._size += enc
-        while self._size > self._max and self._chunks:
+        self._size += len(chunk_bytes)
+
+        # Normal eviction path: drop whole chunks from the head until
+        # we're under the cap again. Safe now because no single chunk
+        # is larger than ``_max``.
+        while self._size > self._max and len(self._chunks) > 1:
             head = self._chunks.pop(0)
             self._size -= len(head.encode("utf-8", errors="ignore"))
             self.truncated = True
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index cfd3019..973459e 100644
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -531,15 +531,47 @@ def _last_line(text: str) -> str:
     return lines[-1][:200] if lines else "(no output)"
 
 
-def _probe_health(url: str, *, timeout: int) -> bool:
-    """Best-effort HTTP GET — True if we get a 2xx response."""
+def _probe_health(
+    url: str,
+    *,
+    timeout: int,
+    per_request_timeout: int = 5,
+    poll_interval: float = 1.0,
+) -> bool:
+    """Poll an HTTP endpoint until it returns 2xx or ``timeout`` expires.
+
+    Codex R3 flagged: the earlier single-shot GET failed good builds
+    whose apps needed a few seconds to boot. This implementation
+    honours ``timeout`` as a real startup grace period — per-request
+    timeout stays short (default 5s) so we can retry, but the whole
+    probe budget can run up to the configured ``boot_timeout_seconds``.
+
+    Returns True on first 2xx, False when the budget runs out.
+    """
     try:
         import httpx
-        r = httpx.get(url, timeout=min(timeout, 10))
-        return 200 <= r.status_code < 300
-    except Exception:  # noqa: BLE001
+    except ImportError:   # pragma: no cover - runtime dependency
         return False
 
+    deadline = time.time() + max(timeout, 1)
+    attempts = 0
+    while time.time() < deadline:
+        attempts += 1
+        remaining = max(deadline - time.time(), 0.1)
+        req_timeout = min(per_request_timeout, remaining)
+        try:
+            r = httpx.get(url, timeout=req_timeout)
+            if 200 <= r.status_code < 300:
+                return True
+        except Exception:  # noqa: BLE001
+            # Connection refused / DNS error / timeout — the app is not
+            # ready yet. Wait briefly and retry unless budget exhausted.
+            pass
+        # Sleep until either the next poll or budget expiry, whichever
+        # comes first.
+        time.sleep(min(poll_interval, max(deadline - time.time(), 0)))
+    return False
+
 
 # ---------------------------------------------------------------------------
 # Git helpers
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 61ba796..86cebe1 100644
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -257,7 +257,13 @@ def run_v3_full(
             )
             completed.append(result)
             state.completed_steps = completed
-            state.completed_features = len([r for r in completed if r.status == StepStatus.PASSED])
+            # Count PASSED + SKIPPED — both are "done from NC Dev's
+            # perspective". SKIPPED = brownfield state scanner already
+            # found them in the target repo; PASSED = built this run.
+            state.completed_features = len([
+                r for r in completed
+                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+            ])
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
diff --git a/src/ncdev/v3/metrics.py b/src/ncdev/v3/metrics.py
index eb3e266..830747b 100644
--- a/src/ncdev/v3/metrics.py
+++ b/src/ncdev/v3/metrics.py
@@ -30,8 +30,10 @@ class RunMetrics(BaseModel):
     completed_at: str = ""
     total_duration_seconds: float = 0.0
     total_features: int = 0
-    passed_features: int = 0
-    failed_features: int = 0
+    passed_features: int = 0          # built successfully this run
+    failed_features: int = 0          # tried and broke OR dep-blocked
+    skipped_features: int = 0         # brownfield — already implemented
+    blocked_features: int = 0         # broken dep cascaded here
     first_pass_success_rate: float = 0.0
     repair_rate: float = 0.0
     mean_repair_attempts: float = 0.0
@@ -56,7 +58,14 @@ def compute_run_metrics(
         return RunMetrics(run_id=state.run_id, started_at=state.started_at)
 
     passed = [s for s in steps if s.status == StepStatus.PASSED]
-    failed = [s for s in steps if s.status == StepStatus.FAILED]
+    # Both FAILED (tried and broke) and BLOCKED (upstream dep broke)
+    # are failures at the run-metric level — they count against
+    # failed_features so the number matches the engine's "unsuccessful"
+    # run status. blocked_features is tracked separately for detail.
+    failed_direct = [s for s in steps if s.status == StepStatus.FAILED]
+    blocked = [s for s in steps if s.status == StepStatus.BLOCKED]
+    failed = failed_direct + blocked
+    skipped = [s for s in steps if s.status == StepStatus.SKIPPED]
     first_pass = [s for s in passed if s.repair_attempts == 0]
     repaired = [s for s in steps if s.repair_attempts > 0]
 
@@ -92,6 +101,8 @@ def compute_run_metrics(
         total_features=total,
         passed_features=len(passed),
         failed_features=len(failed),
+        skipped_features=len(skipped),
+        blocked_features=len(blocked),
         first_pass_success_rate=len(first_pass) / total,
         repair_rate=len(repaired) / total,
         mean_repair_attempts=(
diff --git a/src/ncdev/v3/state_scanner.py b/src/ncdev/v3/state_scanner.py
index dad399d..791a44c 100644
--- a/src/ncdev/v3/state_scanner.py
+++ b/src/ncdev/v3/state_scanner.py
@@ -55,12 +55,18 @@ def build_skip_results(
     feature_queue: list[FeatureStep],
     completed_ids: set[str],
 ) -> list[StepResult]:
-    """Create SKIPPED StepResults for already-completed features."""
+    """Create SKIPPED StepResults for already-completed brownfield features.
+
+    Uses :attr:`StepStatus.SKIPPED` — these features were done before
+    this run started. The dependency gate treats SKIPPED as dep-
+    satisfying, and metrics / summary correctly exclude them from
+    PASSED / BLOCKED / FAILED counters.
+    """
     return [
         StepResult(
             feature_id=f.feature_id,
-            status=StepStatus.PASSED,
-            error_message="Skipped — already implemented in target repo",
+            status=StepStatus.SKIPPED,
+            error_message="Already implemented in target repo (state-scanner detection)",
         )
         for f in feature_queue
         if f.feature_id in completed_ids
diff --git a/tests/test_ncdev_v3/test_metrics.py b/tests/test_ncdev_v3/test_metrics.py
index 75e83f7..1678976 100644
--- a/tests/test_ncdev_v3/test_metrics.py
+++ b/tests/test_ncdev_v3/test_metrics.py
@@ -77,6 +77,28 @@ def test_empty_run():
     assert m.features == []
 
 
+def test_blocked_counted_as_failure_not_skipped():
+    """Codex R3: BLOCKED must count against failed_features so metrics
+    match the engine's overall-status determination."""
+    state = V3RunState(
+        run_id="rm1",
+        started_at="2026-04-11T10:00:00+00:00",
+        updated_at="2026-04-11T10:10:00+00:00",
+        completed_steps=[
+            _make_result("f1", StepStatus.PASSED),
+            _make_result("f2", StepStatus.FAILED),
+            _make_result("f3", StepStatus.BLOCKED),
+            _make_result("f4", StepStatus.SKIPPED),
+        ],
+    )
+    m = compute_run_metrics(state)
+    assert m.total_features == 4
+    assert m.passed_features == 1
+    assert m.failed_features == 2      # FAILED + BLOCKED together
+    assert m.blocked_features == 1     # tracked separately for detail
+    assert m.skipped_features == 1
+
+
 def test_ingestion_count_passed_through():
     state = V3RunState(
         run_id="t6", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T10:30:00+00:00",
diff --git a/tests/test_ncdev_v3/test_state_scanner.py b/tests/test_ncdev_v3/test_state_scanner.py
index 8349a1e..5891ff9 100644
--- a/tests/test_ncdev_v3/test_state_scanner.py
+++ b/tests/test_ncdev_v3/test_state_scanner.py
@@ -59,12 +59,15 @@ def test_feature_has_files_no_match():
 
 
 def test_build_skip_results():
+    """Brownfield-done features must be SKIPPED (not PASSED) — the
+    status needs to differentiate 'built this run' from 'already there'
+    so metrics and dep gating stay consistent."""
     features = [_feat("f1", "Auth"), _feat("f2", "Dashboard"), _feat("f3", "Settings")]
     results = build_skip_results(features, {"f1", "f3"})
     assert len(results) == 2
     assert results[0].feature_id == "f1"
-    assert results[0].status == StepStatus.PASSED
-    assert "Skipped" in results[0].error_message
+    assert results[0].status == StepStatus.SKIPPED
+    assert "Already implemented" in results[0].error_message
     assert results[1].feature_id == "f3"
 
 
diff --git a/tests/unit/test_ai_session.py b/tests/unit/test_ai_session.py
index 983a199..99a6af4 100644
--- a/tests/unit/test_ai_session.py
+++ b/tests/unit/test_ai_session.py
@@ -192,6 +192,26 @@ def test_custom_mode_routes_to_codex_when_user_requests_it(tmp_path: Path):
     assert called["claude"] is False
 
 
+def test_custom_mode_unknown_provider_returns_structured_failure(tmp_path: Path):
+    """Codex R3: an unknown provider name in routing used to raise
+    ValueError uncaught mid-run. Now must surface as a structured
+    ClaudeSessionResult with success=False + actionable error."""
+    cfg = NCDevV2Config(
+        mode="custom",
+        routing={
+            "review": ["something_weird"],
+            "implementation": ["openai_codex"],
+        },
+    )
+    result = run_ai_session("x", cwd=tmp_path, config=cfg)
+    assert result.success is False
+    assert result.exit_code == -1
+    assert "custom mode" in (result.error or "")
+    assert "something_weird" in (result.error or "")
+    # Must not have spawned any runner
+    assert result.final_text == ""
+
+
 def test_custom_mode_plan_codex_build_like_routing(tmp_path: Path):
     """User configures custom to mimic claude_plan_codex_build: review=
     claude, implementation=codex → Claude orch WITH codex protocol."""
@@ -331,6 +351,46 @@ def test_run_codex_session_truncates_huge_stream(tmp_path: Path):
     assert len(result.final_text.encode("utf-8")) <= 60_000  # some tolerance
 
 
+def test_tail_buffer_preserves_tail_of_oversized_chunk():
+    """Codex R3 flagged: _TailBuffer(10).append('x' * 25) previously
+    returned ''. Now must preserve the last 10 bytes."""
+    from ncdev.ai_session import _TailBuffer
+
+    buf = _TailBuffer(10)
+    buf.append("x" * 25)
+    text = buf.text()
+    assert buf.truncated is True
+    assert len(text.encode("utf-8")) <= 10
+    # The tail is preserved — last 10 'x' characters
+    assert text == "x" * 10
+
+
+def test_tail_buffer_normal_eviction_across_chunks():
+    """Multiple small chunks — head gets evicted as cap is exceeded."""
+    from ncdev.ai_session import _TailBuffer
+
+    buf = _TailBuffer(10)
+    buf.append("aaaa")
+    buf.append("bbbb")
+    buf.append("cccc")    # total 12 > 10; head "aaaa" gets evicted
+    text = buf.text()
+    assert buf.truncated is True
+    assert "cccc" in text
+    # "aaaa" at the head was evicted; size must be under cap
+    assert len(text.encode("utf-8")) <= 10
+
+
+def test_tail_buffer_keeps_last_chunk_even_when_oversized_alone():
+    """When only one chunk exists and it's oversized, slice its tail
+    instead of losing everything."""
+    from ncdev.ai_session import _TailBuffer
+
+    buf = _TailBuffer(5)
+    buf.append("1234567890")
+    text = buf.text()
+    assert text == "67890"
+
+
 def test_run_codex_session_watchdog_kills_hung_child(tmp_path: Path):
     """Integration: actual hung child must be killed by the watchdog,
     same guarantee as run_claude_session."""
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index 62dc259..a08e209 100644
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -3,6 +3,7 @@
 from __future__ import annotations
 
 import subprocess
+import time
 from pathlib import Path
 from unittest.mock import patch
 
@@ -326,6 +327,85 @@ def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     assert any("backend tests failed" in r for r in reasons)
 
 
+def test_health_probe_polls_until_app_comes_up(monkeypatch):
+    """Codex R3 blocker: probe was single-shot; now it must poll and
+    accept the app when it comes up within boot_timeout_seconds."""
+    from ncdev.v3 import claude_executor as ex
+
+    attempts = {"count": 0}
+
+    class FakeResp:
+        def __init__(self, status):
+            self.status_code = status
+
+    def fake_get(url, timeout=None):  # noqa: ARG001
+        attempts["count"] += 1
+        if attempts["count"] < 3:
+            raise ConnectionError("app not up yet")
+        return FakeResp(200)
+
+    import httpx
+    monkeypatch.setattr(httpx, "get", fake_get)
+
+    result = ex._probe_health(
+        "http://localhost:99999/health",
+        timeout=10,
+        per_request_timeout=1,
+        poll_interval=0.05,
+    )
+    assert result is True
+    # Multiple attempts were made — polling worked
+    assert attempts["count"] >= 3
+
+
+def test_health_probe_returns_false_when_budget_exhausted(monkeypatch):
+    """Apps that never come up within the budget fail cleanly."""
+    from ncdev.v3 import claude_executor as ex
+
+    def fake_get(url, timeout=None):  # noqa: ARG001
+        raise ConnectionError("never up")
+
+    import httpx
+    monkeypatch.setattr(httpx, "get", fake_get)
+
+    start = time.time()
+    result = ex._probe_health(
+        "http://localhost:99999/health",
+        timeout=1,
+        per_request_timeout=1,
+        poll_interval=0.1,
+    )
+    elapsed = time.time() - start
+    assert result is False
+    # Must actually respect the budget — not give up immediately, not
+    # run 10x longer.
+    assert 0.8 <= elapsed < 3.0, f"probe ran for {elapsed:.2f}s, expected ~1s"
+
+
+def test_health_probe_early_success_returns_immediately(monkeypatch):
+    """If the app is already up, don't waste the budget polling."""
+    from ncdev.v3 import claude_executor as ex
+
+    class FakeResp:
+        status_code = 200
+
+    def fake_get(url, timeout=None):  # noqa: ARG001
+        return FakeResp()
+
+    import httpx
+    monkeypatch.setattr(httpx, "get", fake_get)
+
+    start = time.time()
+    result = ex._probe_health(
+        "http://localhost:99999/health",
+        timeout=30,
+        per_request_timeout=5,
+    )
+    elapsed = time.time() - start
+    assert result is True
+    assert elapsed < 1.0
+
+
 def test_health_probe_failure_blocks_pass_when_url_set(tmp_path: Path):
     """Codex R2: boot probe was soft-signal only. When the contract
     declares backend_health_url, we must enforce it — the user put

exec
/bin/zsh -lc "sed -n '520,620p' src/ncdev/v3/claude_executor.py && printf '\\n---\\n' && sed -n '340,430p' src/ncdev/ai_session.py && printf '\\n---\\n' && sed -n '250,340p' src/ncdev/v3/engine.py && printf '\\n---\\n' && sed -n '1,180p' tests/unit/test_claude_executor.py && printf '\\n---\\n' && sed -n '180,430p' tests/unit/test_claude_executor.py && printf '\\n---\\n' && sed -n '1,220p' tests/unit/test_ai_session.py && printf '\\n---\\n' && sed -n '220,430p' tests/unit/test_ai_session.py && printf '\\n---\\n' && sed -n '1,180p' tests/test_ncdev_v3/test_state_scanner.py && printf '\\n---\\n' && sed -n '1,180p' tests/test_ncdev_v3/test_metrics.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0, (r.stdout + "\n" + r.stderr)
    except subprocess.TimeoutExpired as exc:
        return False, f"timed out after {timeout}s: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"exec error: {exc}"


def _last_line(text: str) -> str:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return lines[-1][:200] if lines else "(no output)"


def _probe_health(
    url: str,
    *,
    timeout: int,
    per_request_timeout: int = 5,
    poll_interval: float = 1.0,
) -> bool:
    """Poll an HTTP endpoint until it returns 2xx or ``timeout`` expires.

    Codex R3 flagged: the earlier single-shot GET failed good builds
    whose apps needed a few seconds to boot. This implementation
    honours ``timeout`` as a real startup grace period — per-request
    timeout stays short (default 5s) so we can retry, but the whole
    probe budget can run up to the configured ``boot_timeout_seconds``.

    Returns True on first 2xx, False when the budget runs out.
    """
    try:
        import httpx
    except ImportError:   # pragma: no cover - runtime dependency
        return False

    deadline = time.time() + max(timeout, 1)
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        remaining = max(deadline - time.time(), 0.1)
        req_timeout = min(per_request_timeout, remaining)
        try:
            r = httpx.get(url, timeout=req_timeout)
            if 200 <= r.status_code < 300:
                return True
        except Exception:  # noqa: BLE001
            # Connection refused / DNS error / timeout — the app is not
            # ready yet. Wait briefly and retry unless budget exhausted.
            pass
        # Sleep until either the next poll or budget expiry, whichever
        # comes first.
        time.sleep(min(poll_interval, max(deadline - time.time(), 0)))
    return False


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_head(target_path: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(target_path), capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _git_working_tree_dirty(target_path: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(target_path), capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _diff_since(target_path: Path, ref: str) -> tuple[list[str], list[str]]:
    if not ref:
        return [], []
    try:
        r = subprocess.run(
            ["git", "diff", "--name-status", f"{ref}..HEAD"],
            cwd=str(target_path), capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return [], []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return [], []

    created: list[str] = []
    modified: list[str] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:

---
            exit_code=exit_code,
            duration_seconds=duration,
            stderr=stderr_text,
            error=f"codex session timed out after {timeout}s",
        )

    return ClaudeSessionResult(
        success=exit_code == 0,
        final_text=final_text,
        exit_code=exit_code,
        duration_seconds=duration,
        stderr=stderr_text,
        error=None if exit_code == 0 else f"codex exited with code {exit_code}",
    )


# ---------------------------------------------------------------------------
# Helpers (shared)
# ---------------------------------------------------------------------------


class _TailBuffer:
    """Accumulate text but keep only the tail of ``max_bytes``.

    Recent output is more useful than the head when debugging a builder
    that went off the rails. ``truncated`` flips True once we start
    dropping bytes so callers can surface that to users / logs.

    If a single incoming chunk is larger than ``max_bytes``, we slice
    the tail bytes out of *that* chunk instead of evicting it wholesale
    (Codex R3 flagged: the previous behavior produced an empty buffer
    when a single append overflowed the cap).
    """

    __slots__ = ("_chunks", "_size", "_max", "truncated")

    def __init__(self, max_bytes: int) -> None:
        self._chunks: list[str] = []
        self._size = 0
        self._max = max(max_bytes, 1)
        self.truncated = False

    def append(self, chunk: str) -> None:
        if not chunk:
            return

        # Oversized single chunk: keep the tail bytes of this chunk only.
        chunk_bytes = chunk.encode("utf-8", errors="ignore")
        if len(chunk_bytes) > self._max:
            tail_bytes = chunk_bytes[-self._max:]
            tail = tail_bytes.decode("utf-8", errors="ignore")
            self._chunks = [tail]
            self._size = len(tail.encode("utf-8", errors="ignore"))
            self.truncated = True
            return

        self._chunks.append(chunk)
        self._size += len(chunk_bytes)

        # Normal eviction path: drop whole chunks from the head until
        # we're under the cap again. Safe now because no single chunk
        # is larger than ``_max``.
        while self._size > self._max and len(self._chunks) > 1:
            head = self._chunks.pop(0)
            self._size -= len(head.encode("utf-8", errors="ignore"))
            self.truncated = True

    def text(self) -> str:
        return "".join(self._chunks)


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a process and its children. Mirror of claude_session's helper."""
    if proc.poll() is not None:
        return
    try:
        if _IS_POSIX:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
        else:
            proc.terminate()
            try:

---
                charter_bundle=bundle,
                prior_results=completed,
                project_id=bundle.contract.project_name,
                model=builder_model,
                timeout=builder_timeout,
                max_budget_usd=max_budget_usd,
                config=config,
            )
            completed.append(result)
            state.completed_steps = completed
            # Count PASSED + SKIPPED — both are "done from NC Dev's
            # perspective". SKIPPED = brownfield state scanner already
            # found them in the target repo; PASSED = built this run.
            state.completed_features = len([
                r for r in completed
                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
            ])
            _persist_state(state, run_dir)

            status_style = "green" if result.status == StepStatus.PASSED else "red"
            console.print(f"  [{status_style}]{result.status.value}[/{status_style}] — commit {result.commit_sha[:8] or '(none)'}")

    # ── Phase 6: Summary ─────────────────────────────────────────────────
    state.phase = "complete"
    passed = [r for r in completed if r.status == StepStatus.PASSED]
    # Both FAILED (tried and broke) and BLOCKED (couldn't try because a dep
    # broke) count as run-level failures. Without this, a --strict-deps halt
    # would report "passed" despite halting because of broken deps.
    unsuccessful = [
        r for r in completed
        if r.status in (StepStatus.FAILED, StepStatus.BLOCKED)
    ]
    state.status = "passed" if not unsuccessful else ("partial" if passed else "failed")

    _print_summary_table(completed)

    _persist_state(state, run_dir)
    return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unmet_dependencies(feature, completed: list[StepResult]) -> list[str]:
    """Return the ids in ``feature.depends_on_features`` that are not met.

    A dep is "met" when it appears in ``completed`` with status:
      * PASSED  — built successfully this run
      * SKIPPED — brownfield state-scanner determined it was already
                  implemented in the target repo before this run started
    A dep is "unmet" when it:
      * is missing from the completed list (never attempted), OR
      * has status FAILED (we tried and it broke), OR
      * has status BLOCKED (its own dep was unmet — cascading failure).

    The BLOCKED distinction stops feature-N-blocked from being treated
    as "already done" and letting feature N+1 sail through.
    """
    acceptable = {
        r.feature_id for r in completed
        if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
    }
    return [dep for dep in feature.depends_on_features if dep not in acceptable]


def _filter_completed_features(target_path: Path, features, completed: list[StepResult]):
    """Brownfield skip: drop features already implemented in the target repo."""
    try:
        from ncdev.v3.state_scanner import build_skip_results, scan_completed_features
    except ImportError:
        return features
    try:
        done_ids = set(scan_completed_features(target_path, features))
    except Exception:  # noqa: BLE001
        return features
    if not done_ids:
        return features
    skipped = build_skip_results(features, done_ids)
    completed.extend(skipped)
    remaining = [f for f in features if f.feature_id not in done_ids]
    console.print(f"  [dim]Skipping {len(done_ids)} features already implemented[/dim]")
    return remaining


def _print_summary_table(completed: list[StepResult]) -> None:
    if not completed:
        return
    table = Table(title="V3 Build Summary")
    table.add_column("Feature", style="cyan")

---
"""Tests for Phase E Claude-driven feature executor."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev.claude_session import ClaudeSessionResult
from ncdev.v3.asset_manifest import save_feature_manifest
from ncdev.v3.claude_executor import (
    build_feature_prompt,
    execute_feature_claude_driven,
)
from ncdev.v3.models import (
    AssetManifest,
    AssetManifestEntry,
    CharterBundle,
    FeatureQueueDoc,
    FeatureStep,
    StepResult,
    StepStatus,
    TargetProjectContract,
    VerificationContract,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature(fid: str = "f01-scaffold") -> FeatureStep:
    return FeatureStep(
        feature_id=fid,
        title="Scaffold",
        description="Boot skeleton + health endpoint",
        acceptance_criteria=["Health endpoint returns 200"],
        test_requirements=["Integration test hits /api/health"],
    )


def _make_bundle(required_files: list[str] | None = None) -> CharterBundle:
    # Test-only bundle: empty test commands + no health URL so
    # _post_session_verification doesn't try to run real pytest / probe
    # a non-existent server in unit tests.
    return CharterBundle(
        contract=TargetProjectContract(project_name="myapp", project_type="web"),
        verification=VerificationContract(
            backend_health_url="",
            backend_test_command="",
            frontend_test_command="",
            minimum_test_count=0,
            required_files=required_files or [],
            prohibited_patterns=["TODO"],
            assets_manifest_required=True,
        ),
        feature_queue=FeatureQueueDoc(project_name="myapp", features=[_make_feature()]),
    )


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    (path / "README.md").write_text("initial")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(path), check=True)


def _seed_manifest(target: Path, feature_id: str) -> None:
    save_feature_manifest(target, AssetManifest(feature_id=feature_id, assets=[]))


# ---------------------------------------------------------------------------
# Prompt shape
# ---------------------------------------------------------------------------


def test_prompt_has_expected_structure(tmp_path: Path):
    feature = _make_feature()
    prompt = build_feature_prompt(
        feature=feature,
        target_path=tmp_path,
        charter_dir=tmp_path / "outputs",
        prior_feature_ids=[],
        project_id="myapp",
    )
    # Feature identity
    assert "f01-scaffold" in prompt
    assert "Scaffold" in prompt
    # Points to the charter artifacts on disk, does NOT inline them
    assert "target-project-contract.json" in prompt
    assert "verification-contract.json" in prompt
    assert "design-system.json" in prompt
    # Instructs skill usage
    assert "test-driven-development" in prompt
    assert "verification-before-completion" in prompt
    assert "systematic-debugging" in prompt
    # Codex protocol referenced (detail is in system prompt)
    assert "Codex" in prompt
    # Asset manifest section spliced in
    assert ".ncdev/assets-needed/f01-scaffold.json" in prompt


def test_prompt_mentions_prior_features(tmp_path: Path):
    prompt = build_feature_prompt(
        feature=_make_feature("f03-auth"),
        target_path=tmp_path,
        charter_dir=tmp_path / "outputs",
        prior_feature_ids=["f01-scaffold", "f02-db"],
        project_id="myapp",
    )
    assert "f01-scaffold, f02-db" in prompt


def test_prompt_handles_empty_acceptance_criteria(tmp_path: Path):
    feature = FeatureStep(
        feature_id="f01",
        title="X",
        description="Y",
        acceptance_criteria=[],
    )
    prompt = build_feature_prompt(
        feature=feature,
        target_path=tmp_path,
        charter_dir=tmp_path,
        prior_feature_ids=[],
        project_id="p",
    )
    assert "infer from description" in prompt


# ---------------------------------------------------------------------------
# Executor happy path
# ---------------------------------------------------------------------------


def test_passed_when_session_succeeds_and_commits(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Simulate Claude making a commit + writing a manifest
        _seed_manifest(target, "f01-scaffold")
        (target / "app.py").write_text("print('hi')")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01-scaffold): hi"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(
            success=True, final_text="done", exit_code=0,
            duration_seconds=2.0, total_cost_usd=0.42,
        )

    bundle = _make_bundle()
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    assert result.status == StepStatus.PASSED
    assert result.commit_sha != ""
    assert "app.py" in result.files_created
    # Session metadata captured on disk
    assert (tmp_path / "run" / "steps" / "f01-scaffold" / "result.json").exists()
    assert (tmp_path / "run" / "steps" / "f01-scaffold" / "signals.json").exists()


# ---------------------------------------------------------------------------
# Executor failure paths
# ---------------------------------------------------------------------------

---
# ---------------------------------------------------------------------------


def test_failed_when_no_commit_made(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude session ran but did nothing
        return ClaudeSessionResult(
            success=True, final_text="I'm confused", exit_code=0,
        )

    bundle = _make_bundle()
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    assert result.status == StepStatus.FAILED


def test_dirty_working_tree_committed_as_broken(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude made changes but didn't commit — orchestrator must
        # commit with [BROKEN] tag so the next feature has context.
        (target / "half_done.py").write_text("# TODO implement")
        return ClaudeSessionResult(success=False, final_text="gave up", exit_code=1)

    bundle = _make_bundle()
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    assert result.status == StepStatus.FAILED
    # A [BROKEN] commit should exist
    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=str(target), capture_output=True, text=True, check=True,
    )
    assert "[BROKEN]" in log.stdout


def test_missing_asset_manifest_causes_verification_failure(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude commits code that references an asset but writes no manifest.
        src = target / "src" / "App.tsx"
        src.parent.mkdir(parents=True)
        src.write_text('<img src="/images/missing.png" />')
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): commit"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    # Session "succeeded" and committed, but verification blocks the pass
    assert result.status == StepStatus.FAILED
    reasons = result.verification.failure_reasons if result.verification else []
    assert any("manifest" in r.lower() for r in reasons)


def test_prohibited_patterns_block_pass(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "bad.py").write_text("# TODO something")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): bad"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    assert result.status == StepStatus.FAILED
    assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)


def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
    """New enforcement: backend_test_command actually runs, not just documented."""
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "a.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): a"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()
    # Contract declares a test command that deliberately fails
    bundle.verification.backend_test_command = "false"  # exit 1

    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    assert result.status == StepStatus.FAILED
    reasons = result.verification.failure_reasons if result.verification else []
    assert any("backend tests failed" in r for r in reasons)


def test_health_probe_polls_until_app_comes_up(monkeypatch):
    """Codex R3 blocker: probe was single-shot; now it must poll and
    accept the app when it comes up within boot_timeout_seconds."""
    from ncdev.v3 import claude_executor as ex

    attempts = {"count": 0}

    class FakeResp:
        def __init__(self, status):
            self.status_code = status

    def fake_get(url, timeout=None):  # noqa: ARG001
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("app not up yet")
        return FakeResp(200)

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    result = ex._probe_health(
        "http://localhost:99999/health",
        timeout=10,
        per_request_timeout=1,
        poll_interval=0.05,
    )
    assert result is True
    # Multiple attempts were made — polling worked
    assert attempts["count"] >= 3


def test_health_probe_returns_false_when_budget_exhausted(monkeypatch):
    """Apps that never come up within the budget fail cleanly."""
    from ncdev.v3 import claude_executor as ex

    def fake_get(url, timeout=None):  # noqa: ARG001
        raise ConnectionError("never up")

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    start = time.time()
    result = ex._probe_health(
        "http://localhost:99999/health",
        timeout=1,
        per_request_timeout=1,
        poll_interval=0.1,
    )
    elapsed = time.time() - start
    assert result is False
    # Must actually respect the budget — not give up immediately, not
    # run 10x longer.
    assert 0.8 <= elapsed < 3.0, f"probe ran for {elapsed:.2f}s, expected ~1s"


def test_health_probe_early_success_returns_immediately(monkeypatch):
    """If the app is already up, don't waste the budget polling."""
    from ncdev.v3 import claude_executor as ex

    class FakeResp:
        status_code = 200

    def fake_get(url, timeout=None):  # noqa: ARG001
        return FakeResp()

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    start = time.time()
    result = ex._probe_health(
        "http://localhost:99999/health",
        timeout=30,
        per_request_timeout=5,
    )
    elapsed = time.time() - start
    assert result is True
    assert elapsed < 1.0


def test_health_probe_failure_blocks_pass_when_url_set(tmp_path: Path):
    """Codex R2: boot probe was soft-signal only. When the contract
    declares backend_health_url, we must enforce it — the user put
    the URL there intentionally."""
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "a.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): a"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()
    # Set a URL that definitely doesn't respond
    bundle.verification.backend_health_url = "http://127.0.0.1:1/health"
    bundle.verification.boot_timeout_seconds = 1

    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):

---
"""Tests for the mode-aware AI session dispatcher."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev import ai_session
from ncdev.ai_session import (
    MODE_IMPLEMENTER,
    MODE_ORCHESTRATOR,
    run_ai_session,
    run_codex_session,
)
from ncdev.claude_session import ClaudeSessionResult
from ncdev.v2.config import NCDevV2Config


# ---------------------------------------------------------------------------
# Mode tables
# ---------------------------------------------------------------------------


def test_mode_tables_cover_every_preset_except_custom():
    """Every non-custom preset must have an orchestrator/implementer
    entry. 'custom' is deliberately absent — it's resolved from the
    user's hand-tuned routing via _resolve_custom_providers."""
    from ncdev.v2.config import MODE_PRESETS
    expected = set(MODE_PRESETS.keys()) - {"custom"}
    assert set(MODE_ORCHESTRATOR.keys()) == expected
    assert set(MODE_IMPLEMENTER.keys()) == expected


def test_claude_plan_codex_build_orchestrator_is_claude_implementer_is_codex():
    assert MODE_ORCHESTRATOR["claude_plan_codex_build"] == "claude"
    assert MODE_IMPLEMENTER["claude_plan_codex_build"] == "codex"


def test_codex_only_has_codex_for_both():
    assert MODE_ORCHESTRATOR["codex_only"] == "codex"
    assert MODE_IMPLEMENTER["codex_only"] == "codex"


def test_claude_only_has_claude_for_both():
    assert MODE_ORCHESTRATOR["claude_only"] == "claude"
    assert MODE_IMPLEMENTER["claude_only"] == "claude"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _claude_result() -> ClaudeSessionResult:
    return ClaudeSessionResult(success=True, final_text="claude did it", exit_code=0)


def _codex_result() -> ClaudeSessionResult:
    return ClaudeSessionResult(success=True, final_text="codex did it", exit_code=0)


def test_claude_plan_codex_build_routes_to_claude_with_protocol(tmp_path: Path):
    cfg = NCDevV2Config(mode="claude_plan_codex_build")
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        result = run_ai_session("do it", cwd=tmp_path, config=cfg)

    assert result.final_text == "claude did it"
    # Codex protocol MUST be injected — this is the whole point of
    # claude_plan_codex_build
    assert captured["include_codex_protocol"] is True


def test_claude_only_routes_to_claude_without_protocol(tmp_path: Path):
    cfg = NCDevV2Config(mode="claude_only")
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("do it", cwd=tmp_path, config=cfg)

    # No Codex delegation in claude_only mode
    assert captured["include_codex_protocol"] is False


def test_codex_only_routes_to_codex(tmp_path: Path):
    cfg = NCDevV2Config(mode="codex_only")
    captured: dict = {}

    def fake_codex(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return _codex_result()

    with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
        result = run_ai_session("do it", cwd=tmp_path, config=cfg)

    assert result.final_text == "codex did it"
    assert "prompt" in captured


def test_codex_only_does_not_call_claude(tmp_path: Path):
    """codex_only must not spawn a Claude session under any circumstances."""
    cfg = NCDevV2Config(mode="codex_only")

    def fake_claude(*a, **k):  # noqa: ARG001
        raise AssertionError("Claude must not be invoked in codex_only mode")

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        with patch("ncdev.ai_session.run_codex_session", return_value=_codex_result()):
            run_ai_session("x", cwd=tmp_path, config=cfg)


def test_claude_only_does_not_call_codex(tmp_path: Path):
    cfg = NCDevV2Config(mode="claude_only")

    def fake_codex(*a, **k):  # noqa: ARG001
        raise AssertionError("Codex session must not be invoked in claude_only mode")

    with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
        with patch("ncdev.ai_session.run_claude_session", return_value=_claude_result()):
            run_ai_session("x", cwd=tmp_path, config=cfg)


def test_openrouter_raises_not_implemented(tmp_path: Path):
    cfg = NCDevV2Config(mode="openrouter")
    with pytest.raises(NotImplementedError, match="API-only"):
        run_ai_session("x", cwd=tmp_path, config=cfg)


def test_custom_mode_honours_hand_tuned_routing_claude_everywhere(tmp_path: Path):
    """Codex R2 flagged: custom was hardcoded to claude+codex, ignoring
    the user's routing: block. Verify: user routes everything to
    anthropic_claude_code → Claude orchestrator, Claude implementer,
    protocol OFF (Claude isn't delegating)."""
    cfg = NCDevV2Config(
        mode="custom",
        routing={
            "review": ["anthropic_claude_code"],
            "implementation": ["anthropic_claude_code"],
        },
    )
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("x", cwd=tmp_path, config=cfg)

    # orchestrator=claude, implementer=claude → NO codex protocol
    assert captured["include_codex_protocol"] is False


def test_custom_mode_routes_to_codex_when_user_requests_it(tmp_path: Path):
    """User flips everything to codex via custom — must actually route
    to codex runner, not fall back to Claude."""
    cfg = NCDevV2Config(
        mode="custom",
        routing={
            "review": ["openai_codex"],
            "implementation": ["openai_codex"],
        },
    )
    called = {"claude": False, "codex": False}

    def fake_claude(*a, **k):  # noqa: ARG001
        called["claude"] = True
        return _claude_result()

    def fake_codex(*a, **k):  # noqa: ARG001
        called["codex"] = True
        return _codex_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
            run_ai_session("x", cwd=tmp_path, config=cfg)

    assert called["codex"] is True, "custom mode must route to codex when user routes review+impl to codex"
    assert called["claude"] is False


def test_custom_mode_unknown_provider_returns_structured_failure(tmp_path: Path):
    """Codex R3: an unknown provider name in routing used to raise
    ValueError uncaught mid-run. Now must surface as a structured
    ClaudeSessionResult with success=False + actionable error."""
    cfg = NCDevV2Config(
        mode="custom",
        routing={
            "review": ["something_weird"],
            "implementation": ["openai_codex"],
        },
    )
    result = run_ai_session("x", cwd=tmp_path, config=cfg)
    assert result.success is False
    assert result.exit_code == -1
    assert "custom mode" in (result.error or "")
    assert "something_weird" in (result.error or "")
    # Must not have spawned any runner
    assert result.final_text == ""


def test_custom_mode_plan_codex_build_like_routing(tmp_path: Path):
    """User configures custom to mimic claude_plan_codex_build: review=
    claude, implementation=codex → Claude orch WITH codex protocol."""
    cfg = NCDevV2Config(
        mode="custom",
        routing={

---
        routing={
            "review": ["anthropic_claude_code"],
            "implementation": ["openai_codex"],
        },
    )
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("x", cwd=tmp_path, config=cfg)

    # Claude orchestrates, Codex implements → protocol ON
    assert captured["include_codex_protocol"] is True


def test_explicit_include_codex_protocol_wins_over_mode_default(tmp_path: Path):
    """Caller can override the mode-inferred default."""
    cfg = NCDevV2Config(mode="claude_plan_codex_build")  # would default True
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session(
            "x", cwd=tmp_path, config=cfg, include_codex_protocol=False,
        )
    assert captured["include_codex_protocol"] is False


# ---------------------------------------------------------------------------
# run_codex_session
# ---------------------------------------------------------------------------


def test_run_codex_session_errors_when_cli_missing(tmp_path: Path):
    with patch("ncdev.ai_session.shutil.which", return_value=None):
        result = run_codex_session("task", cwd=tmp_path)
    assert result.success is False
    assert "codex CLI not found" in (result.error or "")


class _FakeCodexProc:
    """Minimal Popen stand-in: stdout + stderr iterable, immediate exit."""

    _next_pid = 9000

    def __init__(self, stdout: str = "codex output\n", stderr: str = "", returncode: int = 0):
        _FakeCodexProc._next_pid += 1
        self.pid = _FakeCodexProc._next_pid
        self.stdout = iter([stdout] if stdout else [])
        self.stderr = iter([stderr] if stderr else [])
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):  # noqa: ARG002
        return self.returncode

    def kill(self):
        pass

    def terminate(self):
        pass


def test_run_codex_session_builds_correct_argv(tmp_path: Path):
    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeCodexProc(stdout="codex output\n")

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
            result = run_codex_session("build feature X", cwd=tmp_path)

    cmd = captured["cmd"]
    assert cmd[0] == "codex"
    assert cmd[1] == "exec"
    assert "--full-auto" in cmd
    assert "--sandbox" in cmd
    assert "danger-full-access" in cmd
    # Prompt is last arg
    assert "build feature X" in cmd[-1]
    assert "codex_only mode" in cmd[-1]
    assert result.success is True
    assert "codex output" in result.final_text


def test_run_codex_session_writes_log(tmp_path: Path):
    def fake_popen(cmd, **kwargs):  # noqa: ARG001
        return _FakeCodexProc(stdout="the work\n", stderr="")

    log_path = tmp_path / "logs" / "codex.log"

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
            run_codex_session("x", cwd=tmp_path, log_path=log_path)

    assert log_path.exists()
    body = log_path.read_text(encoding="utf-8")
    assert "RUNNER: codex" in body
    assert "the work" in body


def test_run_codex_session_truncates_huge_stream(tmp_path: Path):
    """Codex R2 flagged: unbounded capture_output can blow RAM.
    Verify the tail-buffer caps memory for chatty runs."""
    huge = "x" * 1024   # 1KB per line
    lines = [huge + "\n"] * 200  # 200 KB total

    class HugeProc(_FakeCodexProc):
        def __init__(self):
            super().__init__(stdout="", returncode=0)
            self.stdout = iter(lines)

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=lambda *a, **k: HugeProc()):
            # Cap at 50 KB — result must be capped, no crash
            result = run_codex_session(
                "x", cwd=tmp_path, max_bytes_per_stream=50_000,
            )

    assert result.success is True
    assert len(result.final_text.encode("utf-8")) <= 60_000  # some tolerance


def test_tail_buffer_preserves_tail_of_oversized_chunk():
    """Codex R3 flagged: _TailBuffer(10).append('x' * 25) previously
    returned ''. Now must preserve the last 10 bytes."""
    from ncdev.ai_session import _TailBuffer

    buf = _TailBuffer(10)
    buf.append("x" * 25)
    text = buf.text()
    assert buf.truncated is True
    assert len(text.encode("utf-8")) <= 10
    # The tail is preserved — last 10 'x' characters
    assert text == "x" * 10


def test_tail_buffer_normal_eviction_across_chunks():
    """Multiple small chunks — head gets evicted as cap is exceeded."""
    from ncdev.ai_session import _TailBuffer

    buf = _TailBuffer(10)
    buf.append("aaaa")
    buf.append("bbbb")
    buf.append("cccc")    # total 12 > 10; head "aaaa" gets evicted
    text = buf.text()
    assert buf.truncated is True
    assert "cccc" in text
    # "aaaa" at the head was evicted; size must be under cap
    assert len(text.encode("utf-8")) <= 10


def test_tail_buffer_keeps_last_chunk_even_when_oversized_alone():
    """When only one chunk exists and it's oversized, slice its tail
    instead of losing everything."""
    from ncdev.ai_session import _TailBuffer

    buf = _TailBuffer(5)
    buf.append("1234567890")
    text = buf.text()
    assert text == "67890"


def test_run_codex_session_watchdog_kills_hung_child(tmp_path: Path):
    """Integration: actual hung child must be killed by the watchdog,
    same guarantee as run_claude_session."""
    import sys as _sys

    fake_cli = tmp_path / "fake-codex"
    fake_cli.write_text(
        "#!/usr/bin/env python3\nimport time\n"
        "while True:\n    time.sleep(1)\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    import subprocess as _sp
    orig_popen = _sp.Popen

    def fake_popen(cmd, **kwargs):
        new_cmd = [_sys.executable, str(fake_cli)] + list(cmd[1:])
        return orig_popen(new_cmd, **kwargs)

    start = time.time()
    with patch("ncdev.ai_session.shutil.which", return_value=str(fake_cli)):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
            result = run_codex_session("x", cwd=tmp_path, timeout=2)
    elapsed = time.time() - start

    assert elapsed < 15, f"codex watchdog failed: {elapsed:.1f}s"
    assert result.success is False
    assert "timed out" in (result.error or "")

---
import subprocess
from pathlib import Path
from unittest.mock import patch

from ncdev.v3.models import FeatureStep, StepStatus
from ncdev.v3.state_scanner import (
    build_skip_results,
    scan_completed_features,
    _feature_in_git_history,
    _feature_has_files,
)


def _feat(fid: str, title: str) -> FeatureStep:
    return FeatureStep(feature_id=fid, title=title, description=title, acceptance_criteria=["works"])


def test_feature_in_git_history_by_id():
    log = "abc1234 feat(sprint-0): project scaffold\ndef5678 feat(feature-01): user auth"
    assert _feature_in_git_history(_feat("sprint-0", "Scaffold"), log) is True
    assert _feature_in_git_history(_feat("feature-01", "Auth"), log) is True
    assert _feature_in_git_history(_feat("feature-99", "Missing"), log) is False


def test_feature_in_git_history_by_title_keywords():
    log = "abc1234 implement user authentication with jwt tokens"
    feat = _feat("f1", "User Authentication JWT Tokens")
    assert _feature_in_git_history(feat, log) is True


def test_feature_in_git_history_no_match():
    log = "abc1234 fix typo in readme"
    feat = _feat("f1", "User Authentication System")
    assert _feature_in_git_history(feat, log) is False


def test_feature_has_files_scaffold():
    files = {"backend/app/main.py", "backend/requirements.txt", "docker-compose.yml", "readme.md"}
    feat = _feat("sprint-0", "Project Scaffold & Boot")
    assert _feature_has_files(feat, files) is True


def test_feature_has_files_scaffold_incomplete():
    files = {"readme.md"}
    feat = _feat("sprint-0", "Project Scaffold & Boot")
    assert _feature_has_files(feat, files) is False


def test_feature_has_files_by_keyword():
    files = {"backend/app/services/auth_service.py", "backend/app/api/v1/endpoints/auth.py"}
    feat = _feat("f1", "User Authentication")
    assert _feature_has_files(feat, files) is True


def test_feature_has_files_no_match():
    files = {"backend/app/main.py", "readme.md"}
    feat = _feat("f1", "Dashboard Analytics")
    assert _feature_has_files(feat, files) is False


def test_build_skip_results():
    """Brownfield-done features must be SKIPPED (not PASSED) — the
    status needs to differentiate 'built this run' from 'already there'
    so metrics and dep gating stay consistent."""
    features = [_feat("f1", "Auth"), _feat("f2", "Dashboard"), _feat("f3", "Settings")]
    results = build_skip_results(features, {"f1", "f3"})
    assert len(results) == 2
    assert results[0].feature_id == "f1"
    assert results[0].status == StepStatus.SKIPPED
    assert "Already implemented" in results[0].error_message
    assert results[1].feature_id == "f3"


def test_scan_completed_features_no_git(tmp_path):
    """No .git directory → nothing detected."""
    features = [_feat("f1", "Auth")]
    result = scan_completed_features(tmp_path, features)
    assert result == []


def test_scan_completed_features_with_git(tmp_path):
    """Git repo with matching commit → feature detected."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@test",
                     "commit", "--allow-empty", "-m", "feat(sprint-0): project scaffold"],
                    cwd=tmp_path, capture_output=True)
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("app = 'ok'")
    (tmp_path / "backend" / "requirements.txt").write_text("fastapi")
    (tmp_path / "docker-compose.yml").write_text("version: '3'")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@test",
                     "commit", "-m", "feat(feature-01): user auth"],
                    cwd=tmp_path, capture_output=True)

    features = [
        _feat("sprint-0", "Project Scaffold & Boot"),
        _feat("feature-01", "User Authentication"),
        _feat("feature-02", "Dashboard"),
    ]
    result = scan_completed_features(tmp_path, features)
    assert "sprint-0" in result
    assert "feature-01" in result
    assert "feature-02" not in result

---
from ncdev.v3.metrics import compute_run_metrics
from ncdev.v3.models import FeatureQueueDoc, StepResult, StepStatus, V3RunState


def _make_result(fid: str, status: StepStatus, repairs: int = 0, build_s: float = 60, verify_s: float = 10) -> StepResult:
    return StepResult(
        feature_id=fid, status=status, build_duration_seconds=build_s,
        verify_duration_seconds=verify_s, repair_attempts=repairs,
        files_created=["a.py", "b.py"], files_modified=["c.py"],
    )


def test_all_pass_first_try():
    state = V3RunState(
        run_id="t1", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        completed_steps=[_make_result("f1", StepStatus.PASSED), _make_result("f2", StepStatus.PASSED), _make_result("f3", StepStatus.PASSED)],
    )
    m = compute_run_metrics(state)
    assert m.first_pass_success_rate == 1.0
    assert m.repair_rate == 0.0
    assert m.passed_features == 3
    assert m.failed_features == 0
    assert all(f.passed_first_try for f in m.features)


def test_mixed_results():
    state = V3RunState(
        run_id="t2", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        feature_queue=FeatureQueueDoc(project_name="test-proj"),
        completed_steps=[
            _make_result("f1", StepStatus.PASSED, 0),
            _make_result("f2", StepStatus.PASSED, 2),
            _make_result("f3", StepStatus.FAILED, 2),
            _make_result("f4", StepStatus.PASSED, 0),
        ],
    )
    m = compute_run_metrics(state)
    assert m.first_pass_success_rate == 0.5
    assert m.repair_rate == 0.5
    assert m.mean_repair_attempts == 2.0
    assert m.passed_features == 3
    assert m.failed_features == 1
    assert m.project_name == "test-proj"
    assert [f.passed_first_try for f in m.features] == [True, False, False, True]


def test_build_efficiency():
    state = V3RunState(
        run_id="t3", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        completed_steps=[
            _make_result("f1", StepStatus.PASSED, 0, build_s=80, verify_s=20),
            _make_result("f2", StepStatus.PASSED, 0, build_s=120, verify_s=30),
        ],
    )
    m = compute_run_metrics(state)
    assert abs(m.build_efficiency - 0.8) < 0.01


def test_feature_metrics_populated():
    state = V3RunState(
        run_id="t4", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        completed_steps=[_make_result("f1", StepStatus.PASSED, 0)],
    )
    m = compute_run_metrics(state)
    assert len(m.features) == 1
    assert m.features[0].feature_id == "f1"
    assert m.features[0].passed_first_try is True
    assert m.features[0].files_created == 2
    assert m.features[0].files_modified == 1


def test_empty_run():
    state = V3RunState(run_id="t5", started_at="2026-04-11T10:00:00+00:00")
    m = compute_run_metrics(state)
    assert m.first_pass_success_rate == 0.0
    assert m.total_features == 0
    assert m.features == []


def test_blocked_counted_as_failure_not_skipped():
    """Codex R3: BLOCKED must count against failed_features so metrics
    match the engine's overall-status determination."""
    state = V3RunState(
        run_id="rm1",
        started_at="2026-04-11T10:00:00+00:00",
        updated_at="2026-04-11T10:10:00+00:00",
        completed_steps=[
            _make_result("f1", StepStatus.PASSED),
            _make_result("f2", StepStatus.FAILED),
            _make_result("f3", StepStatus.BLOCKED),
            _make_result("f4", StepStatus.SKIPPED),
        ],
    )
    m = compute_run_metrics(state)
    assert m.total_features == 4
    assert m.passed_features == 1
    assert m.failed_features == 2      # FAILED + BLOCKED together
    assert m.blocked_features == 1     # tracked separately for detail
    assert m.skipped_features == 1


def test_ingestion_count_passed_through():
    state = V3RunState(
        run_id="t6", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T10:30:00+00:00",
        completed_steps=[_make_result("f1", StepStatus.PASSED)],
        metadata={"citex_queries_by_codex": 7},
    )
    m = compute_run_metrics(state, ingestion_doc_count=12)
    assert m.citex_documents_ingested == 12
    assert m.citex_queries_by_codex == 7

codex
The fix set is mostly where it should be. I’m checking one remaining seam now: whether the new semantics actually propagate to the user-visible run state in all cases, especially when the state scanner skips features before any new feature runs.
exec
/bin/zsh -lc "sed -n '1,220p' src/ncdev/v3/models.py && printf '\\n---\\n' && sed -n '340,410p' src/ncdev/cli.py && printf '\\n---\\n' && sed -n '1,220p' docs/codex-review/review-response-round3.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""V3 models — sequential verified sprint engine."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FeatureStep(BaseModel):
    """A single feature to implement in sequence."""

    feature_id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    test_requirements: list[str] = Field(default_factory=list)
    depends_on_features: list[str] = Field(default_factory=list)
    priority: int = 0
    estimated_complexity: str = "medium"  # low, medium, high


class FeatureQueueDoc(BaseModel):
    """Ordered list of features to implement sequentially."""

    version: str = "v3"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    generator: str = "ncdev.v3.feature_queue"
    project_name: str = ""
    features: list[FeatureStep] = Field(default_factory=list)
    sprint_zero_criteria: list[str] = Field(default_factory=lambda: [
        "App installs without errors",
        "App boots and health endpoint returns OK",
        "Empty test suite runs",
        "First screenshot captured",
    ])


class StepStatus(str, Enum):
    PENDING = "pending"
    BUILDING = "building"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"   # brownfield state-scanner: feature already implemented
    BLOCKED = "blocked"   # dependency failed / blocked — we did NOT try


class TestResult(BaseModel):
    """Result of running a test suite."""

    suite: str  # "unit", "integration", "e2e"
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    output: str = ""
    success: bool = False
    duration_seconds: float = 0.0


class ScreenshotEvidence(BaseModel):
    """A screenshot captured during verification."""

    path: str
    description: str
    viewport: str = "desktop"  # desktop, mobile
    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StepVerification(BaseModel):
    """Verification results for a single feature step."""

    lint_passed: bool = False
    lint_output: str = ""
    unit_tests: TestResult | None = None
    integration_tests: TestResult | None = None
    e2e_tests: TestResult | None = None
    screenshots: list[ScreenshotEvidence] = Field(default_factory=list)
    prohibited_patterns: list[str] = Field(default_factory=list)
    app_boots: bool = False
    overall_passed: bool = False
    failure_reasons: list[str] = Field(default_factory=list)


class StepResult(BaseModel):
    """Result of executing one feature step."""

    feature_id: str
    status: StepStatus
    build_duration_seconds: float = 0.0
    verify_duration_seconds: float = 0.0
    repair_attempts: int = 0
    verification: StepVerification | None = None
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    commit_sha: str = ""
    error_message: str = ""
    builder_output: str = ""


class V3RunState(BaseModel):
    """Overall state of a V3 pipeline run."""

    run_id: str
    command: str = "full"
    workspace: str = ""
    run_dir: str = ""
    target_path: str = ""
    phase: str = "init"
    status: str = "running"
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    feature_queue: FeatureQueueDoc | None = None
    completed_steps: list[StepResult] = Field(default_factory=list)
    current_step: str = ""
    total_features: int = 0
    completed_features: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionRecord(BaseModel):
    """One document ingested into Citex."""
    category: str
    char_count: int
    success: bool


class IngestionReport(BaseModel):
    """Summary of context ingestion into Citex."""
    project_id: str
    total_documents: int = 0
    successful: int = 0
    failed: int = 0
    records: list[IngestionRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Charter artifacts — the 3 files that replace the old 9-artifact pipeline.
# ---------------------------------------------------------------------------


class TargetProjectContract(BaseModel):
    """Hard architectural constraints. The 'don't override' bag.

    Fields the user controls: stack, language, DB, auth, deployment target,
    ports, design archetype. Claude may infer defaults from the PRD but
    must NOT change these after the first session — they're the invariants.
    """

    version: str = "v3"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    project_name: str
    project_type: str = "web"  # web | cli | library | api
    is_brownfield: bool = False
    existing_repo_path: str = ""

    # Stack — each field optional; "none" means explicitly not used.
    backend_framework: str = ""     # fastapi | django | express | none
    frontend_framework: str = ""    # react | vue | svelte | none
    database: str = ""              # mongodb | postgres | sqlite | none
    auth_system: str = ""           # keycloak | jwt | none
    language_backend: str = ""
    language_frontend: str = ""

    # Deployment
    deployment_target: str = "docker"   # docker | k8s | serverless
    ports: dict[str, int] = Field(default_factory=dict)

    # Design
    design_archetype: str = ""  # See user's global CLAUDE.md for values
    design_system_source: str = "stitch"   # stitch | existing | claude
    design_system_path: str = "docs/design-system"

    # Other invariants the orchestrator or verification must know
    uses_citex: bool = True
    uses_mock_apis: bool = True
    production_readiness_required: bool = True


class VerificationContract(BaseModel):
    """What 'done' means for this project.

    The Claude feature-executor session must satisfy every clause before
    committing. Hooks enforce where possible; post-hoc checks cover the rest.
    """

    version: str = "v3"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # App must boot
    backend_health_url: str = ""       # e.g. http://localhost:23001/api/health
    frontend_url: str = ""
    boot_timeout_seconds: int = 60

    # Tests must exist and pass
    backend_test_command: str = ""     # e.g. "cd backend && python -m pytest -q"
    frontend_test_command: str = ""    # e.g. "cd frontend && npm test -- --run"
    e2e_test_command: str = ""         # e.g. "cd frontend && npx playwright test"
    minimum_test_count: int = 1

    # Screenshots
    required_screenshots: list[str] = Field(default_factory=list)
    screenshot_viewports: list[str] = Field(default_factory=lambda: ["desktop", "mobile"])

    # Files that must exist
    required_files: list[str] = Field(default_factory=list)

    # Assets
    assets_manifest_required: bool = True
    assets_manifest_path: str = ".ncdev/assets-needed"

    # Prohibited patterns (grep-able — hooks enforce these on commit)
    prohibited_patterns: list[str] = Field(default_factory=lambda: [
        "TODO",
        "FIXME",

---
    serve_parser.add_argument("--api-key", default=None, help="API key for authentication")
    serve_parser.add_argument("--workspace", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "quickstart":
        console.print(_quickstart_text())
        return 0

    if args.command == "doctor":
        workspace = Path.cwd()
        ok, report = _doctor_report(workspace)
        console.print(report)
        return 0 if ok else 1

    if args.command == "full":
        workspace = _workspace(args.workspace)
        target_repo = _resolve_target_repo(args.target_repo, workspace)
        state = run_v3_full(
            workspace=workspace,
            source_path=Path(args.source).resolve(),
            base_url=args.base_url,
            dry_run=bool(args.dry_run),
            target_repo_path=target_repo,
            builder_model=args.model,
            builder_timeout=args.timeout,
            max_repair_attempts=args.max_repairs,
            max_budget_usd=getattr(args, "max_budget_usd", None),
            strict_deps=bool(getattr(args, "strict_deps", False)),
        )
        console.print(f"run_id={state.run_id} status={state.status}")
        console.print(f"features: {state.completed_features}/{state.total_features} passed")
        console.print(f"run_dir={state.run_dir}")
        if state.status != "passed":
            return 1

        if args.quality_gate and not args.dry_run:
            import asyncio
            from ncdev.quality_gate.config import QualityGateConfig
            from ncdev.quality_gate.orchestrator import QualityGateOrchestrator

            qg_config = QualityGateConfig(enabled=True, max_cycles=3)
            orchestrator = QualityGateOrchestrator(qg_config)
            prd_content = Path(args.source).resolve().read_text()
            console.print("[cyan]Starting quality gate loop...[/cyan]")
            qg_state = asyncio.run(
                orchestrator.run(
                    project_name=workspace.name,
                    target_url=args.base_url,
                    target_path=str(target_repo or workspace),
                    prd_content=prd_content,
                    fix_callback=_run_quality_gate_fixes,
                )
            )
            console.print(f"quality_gate phase={qg_state.phase} cycles={qg_state.current_cycle}")
            if qg_state.final_scores:
                s = qg_state.final_scores
                console.print(f"scores: core_flow={s.core_flow} resilience={s.resilience} polish={s.polish}")
            return 0 if qg_state.phase == "passed" else 1

        return 0

    if args.command == "dev":
        from ncdev.dev import run_dev
        project_path = Path(args.project).resolve()
        result = run_dev(

---
OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db65d-8d84-7423-ad6a-17fb975c9446
--------
user
# Peer review request — Round 3, post-R2-hardening

You are Codex. This is the third pass. Your first two reviews are on
disk at `docs/codex-review/review-response.md` and
`review-response-round2.md` — read them first so you know what you said.

Since round 2, I committed `4a5a0f7` ("fix(hardening-r2): address
regressions from Codex round-2 review") on
`claude-orchestrator-migration`. It claims to close every critical /
didn't-land / new-bug item from your round-2 review. Your job now:

1. **Verify the R2 fixes landed correctly.** In particular, check the
   fixes I claimed for issues you called "didn't land" and "new issues
   introduced" last time.
2. **Find bugs I introduced in the R2 pass.** Same pattern as R2
   itself — refactors create new bugs.
3. **Reassess the "previously concerning" list** — any of those now
   graduated to critical? Any still open?
4. **Tell me if it's ready to inherit yet.** If not, what's the one
   or two remaining blockers?

Don't repeat ground already covered unless the code regressed. Focus on
what changed in `4a5a0f7` vs `f19934b`.

## What I changed in R2 (commit `4a5a0f7`)

### Fix A — `_commit_broken` NameError
Added `import logging` + `logger = logging.getLogger(__name__)` to
`src/ncdev/v3/claude_executor.py`. Replaced all three
`console.print(...)` calls with `logger.warning(...)`. The function no
longer references a non-existent `console`.

### Fix B — `_commit_broken` return value wired
The caller in `execute_feature_claude_driven()` now does:

```python
if dirty:
    if _commit_broken(target_path, feature):
        post_commit = _git_head(target_path)
    else:
        recoverability_note = (
            " | recoverability: [BROKEN] commit failed — dirty "
            "working tree remains; see log for git error"
        )
    status = StepStatus.FAILED
```

and `recoverability_note` is appended to `StepResult.error_message`.

### Fix C — dep gate SKIPPED conflation
Added `StepStatus.BLOCKED` to `v3/models.py`. In the engine's feature
loop, dep-gated features are now `status=StepStatus.BLOCKED` (not
`SKIPPED`). `_unmet_dependencies` counts only `PASSED` + `SKIPPED`
(brownfield) as satisfied; `FAILED` + `BLOCKED` are unmet. The R1 test
that codified the bug (`SKIPPED counts as satisfied`) is replaced with
`test_blocked_dep_does_NOT_count_as_satisfied`.

### Fix D — `--strict-deps` status reporting
`state.status` computation now bucket-sorts into `unsuccessful = [r
for r in completed if r.status in (FAILED, BLOCKED)]` and uses that
instead of just checking `FAILED`. A dep-halted run reports `failed`
or `partial`, never `passed`.

### Fix E — `custom` mode honours hand-tuned routing
Removed `custom` from `MODE_ORCHESTRATOR` / `MODE_IMPLEMENTER`
hardcoded maps. Added `_resolve_custom_providers(cfg)` in
`ai_session.py`:

```python
def _resolve_custom_providers(cfg: NCDevV2Config) -> tuple[str, str]:
    from ncdev.provider_dispatch import resolve_provider_name
    review_chain = cfg.routing.review or ["anthropic_claude_code"]
    impl_chain = cfg.routing.implementation or ["openai_codex"]
    orch = resolve_provider_name(review_chain[0])
    impl = resolve_provider_name(impl_chain[0])
    return orch, impl
```

Dispatch branches into this helper when `cfg.mode == "custom"`. Three
new tests pin the shapes: `custom` with all-claude, all-codex, and
plan-build-style routing.

### Fix F — hook regex parity with the verifier
`pre_bash_guard._check_staged_for_prohibited` now uses `re.search`
with a literal-substring fallback on `re.error`. Same semantics as
`claude_executor._grep_for_prohibited`. A regex-like pattern in the
contract's `prohibited_patterns` will fire at commit time now, not
only post-hoc.

### Fix G — `run_codex_session` hardened
Replaced `subprocess.run(capture_output=True, ...)` with a Popen +
thread-per-pipe reader + watchdog + `_TailBuffer` pattern that mirrors
`run_claude_session`. `_TailBuffer` accumulates text but keeps only
the tail `max_bytes_per_stream` (default 4 MB per stream). Extracted
`_kill_process_tree()` helper for reuse. Two integration tests: hung
child killed by watchdog within 15 s; 200 KB stream cap enforced.

### Fix H — health probe is hard when URL is set
In `_post_session_verification`:

```python
if probe_health and bundle.verification.backend_health_url:
    reachable = _probe_health(
        bundle.verification.backend_health_url,
        timeout=bundle.verification.boot_timeout_seconds,
    )
    ver.app_boots = reachable
    if not reachable:
        reasons.append(
            f"backend health URL unreachable: "
            f"{bundle.verification.backend_health_url} — the feature "
            "must leave the app in a runnable state"
        )
```

Two tests: URL set + unreachable → feature fails;  URL empty → probe
skipped, feature still passes.

### Numbers
- **418/418 tests passing** (was 411). +7 regression tests.
- Diff `f19934b..4a5a0f7`: 9 source + test files modified, 2 docs added.

## Files to look at this round

- `src/ncdev/v3/claude_executor.py` — particularly the new `logger`
  setup, the `recoverability_note` flow, and the hardened health-probe
  branch.
- `src/ncdev/v3/engine.py` — BLOCKED handling in the feature loop,
  and the new status computation. Does the change make
  `state.completed_features` still correct (it only counts PASSED)?
- `src/ncdev/v3/models.py` — new `BLOCKED` enum value. Any place
  that switches on `StepStatus` and now needs to handle BLOCKED?
- `src/ncdev/ai_session.py` — `_resolve_custom_providers()` and the
  new `run_codex_session` Popen implementation. Thread-safety of
  the `_TailBuffer`?
- `scripts/ncdev-hooks/pre_bash_guard.py` — regex compile +
  literal-fallback parity with the verifier.
- The three dep-gating tests in
  `tests/test_ncdev_v3/test_dependency_gating.py` — do they correctly
  differentiate brownfield SKIPPED (good) from BLOCKED (bad)?

## Specific questions

1. **StepStatus.BLOCKED unhandled somewhere.** Are there any other
   code paths that switch on `StepStatus` (metrics, state scanner,
   Citex reporting, summary tables) that need a BLOCKED case added?
2. **`_resolve_custom_providers()` for unknown provider names.** If a
   user sets `review: ["something_weird"]`, `resolve_provider_name`
   raises `ValueError`. Does `run_ai_session` bubble that sensibly, or
   would it crash mid-run?
3. **`_TailBuffer` bytes vs characters.** I encode each chunk to
   compute its length, then re-encode the head to drop. For multi-byte
   characters this is correct but the slicing on `text()` returns the
   concatenated strings, not trimmed-to-exactly-max-bytes. Is that
   acceptable, or should the tail be exactly bytes-bounded?
4. **`recoverability_note` placement.** I append it to
   `StepResult.error_message` only in the failure branch. If the
   broken commit succeeds, the note is empty string — good. But what
   if the caller reads `error_message` expecting it to be JSON or
   empty on pass? Does this break anyone?
5. **Health-probe hardness + flaky apps.** Now that the probe is a
   hard failure when URL is set, a feature that builds everything
   correctly but takes 90 seconds to boot (slower than
   `boot_timeout_seconds=60`) fails. Is that better or worse than the
   old soft signal? Should there be a retry policy?
6. **Status computation edge case.** If the entire feature list is
   SKIPPED (brownfield rerun, nothing to do), `unsuccessful` is
   empty and `passed` is empty. Current code:
   `"passed" if not unsuccessful else ("partial" if passed else "failed")`
   — so it reports `"passed"`. Is that right, or should an empty
   build report a different status like `"noop"`?

## Output shape

Same format as R2, but if everything really did land, say so plainly:

```
## Architecture verdict
<one paragraph>

## R2 fixes verified
<which ones actually closed the issue>

## R2 fixes that still didn't land
<any claims in the R2 commit that don't match the code>

## New issues introduced in R2
<regressions this pass created>

## Still open from earlier rounds
<unresolved concerns>

## Ready to inherit?
<yes/no + the one thing still blocking, if any>

## Honest one-liner
```

Don't soften. If the blocker list is now empty, say that plainly too.
Go.

codex
I’m reading the prior two review responses and the delta from `f19934b..4a5a0f7` first, then I’ll verify the claimed fixes against the code and tests before I call any remaining blockers.
exec
/bin/zsh -lc "sed -n '1,240p' docs/codex-review/review-response.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "sed -n '1,260p' docs/codex-review/review-response-round2.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/engine.py | sed -n '190,290p' && printf '\\n---\\n' && nl -ba src/ncdev/v3/claude_executor.py | sed -n '534,585p' && printf '\\n---\\n' && nl -ba src/ncdev/ai_session.py | sed -n '361,410p' && printf '\\n---\\n' && nl -ba src/ncdev/v3/state_scanner.py | sed -n '50,90p' && printf '\\n---\\n' && nl -ba src/ncdev/v3/metrics.py | sed -n '49,125p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   190	            else:
   191	                console.print("  [yellow]Citex unreachable — feature builds will run without RAG grounding[/yellow]")
   192	        except Exception as exc:  # noqa: BLE001
   193	            console.print(f"  [yellow]Citex ingestion failed: {exc} — continuing without RAG[/yellow]")
   194	    else:
   195	        console.print("\n[dim]Phase 4: Context ingestion skipped (greenfield or dry run)[/dim]")
   196	
   197	    # ── Phase 5: Sequential feature execution ────────────────────────────
   198	    state.phase = "building"
   199	    completed: list[StepResult] = []
   200	
   201	    if dry_run or bundle is None:
   202	        console.print("\n[dim]Phase 5: Feature execution skipped (dry run)[/dim]")
   203	    else:
   204	        features = bundle.feature_queue.features
   205	        state.feature_queue = bundle.feature_queue
   206	        state.total_features = len(features)
   207	
   208	        # Brownfield: skip features already implemented
   209	        remaining = _filter_completed_features(target_path, features, completed)
   210	        console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
   211	
   212	        for feature in remaining:
   213	            state.current_step = feature.feature_id
   214	            _persist_state(state, run_dir)
   215	
   216	            # Dependency gate: a feature whose depends_on_features contains
   217	            # any non-PASSED id is skipped rather than built. In strict mode,
   218	            # halt the whole run at the first broken dep.
   219	            unmet = _unmet_dependencies(feature, completed)
   220	            if unmet:
   221	                reason = (
   222	                    f"dependency not satisfied: {', '.join(unmet)} "
   223	                    "(required feature(s) are not in PASSED state)"
   224	                )
   225	                console.print(Panel(
   226	                    f"[red]BLOCKED[/red] {feature.feature_id} — {reason}",
   227	                    border_style="red",
   228	                ))
   229	                completed.append(StepResult(
   230	                    feature_id=feature.feature_id,
   231	                    status=StepStatus.BLOCKED,
   232	                    error_message=reason,
   233	                ))
   234	                state.completed_steps = completed
   235	                _persist_state(state, run_dir)
   236	                if strict_deps:
   237	                    console.print("[red]--strict-deps set: halting run[/red]")
   238	                    break
   239	                continue
   240	
   241	            console.print(Panel(
   242	                f"[cyan]{feature.feature_id}[/cyan] — {feature.title}",
   243	                border_style="blue",
   244	            ))
   245	
   246	            result = execute_feature_claude_driven(
   247	                feature=feature,
   248	                target_path=target_path,
   249	                run_dir=run_dir,
   250	                charter_bundle=bundle,
   251	                prior_results=completed,
   252	                project_id=bundle.contract.project_name,
   253	                model=builder_model,
   254	                timeout=builder_timeout,
   255	                max_budget_usd=max_budget_usd,
   256	                config=config,
   257	            )
   258	            completed.append(result)
   259	            state.completed_steps = completed
   260	            # Count PASSED + SKIPPED — both are "done from NC Dev's
   261	            # perspective". SKIPPED = brownfield state scanner already
   262	            # found them in the target repo; PASSED = built this run.
   263	            state.completed_features = len([
   264	                r for r in completed
   265	                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
   266	            ])
   267	            _persist_state(state, run_dir)
   268	
   269	            status_style = "green" if result.status == StepStatus.PASSED else "red"
   270	            console.print(f"  [{status_style}]{result.status.value}[/{status_style}] — commit {result.commit_sha[:8] or '(none)'}")
   271	
   272	    # ── Phase 6: Summary ─────────────────────────────────────────────────
   273	    state.phase = "complete"
   274	    passed = [r for r in completed if r.status == StepStatus.PASSED]
   275	    # Both FAILED (tried and broke) and BLOCKED (couldn't try because a dep
   276	    # broke) count as run-level failures. Without this, a --strict-deps halt
   277	    # would report "passed" despite halting because of broken deps.
   278	    unsuccessful = [
   279	        r for r in completed
   280	        if r.status in (StepStatus.FAILED, StepStatus.BLOCKED)
   281	    ]
   282	    state.status = "passed" if not unsuccessful else ("partial" if passed else "failed")
   283	
   284	    _print_summary_table(completed)
   285	
   286	    _persist_state(state, run_dir)
   287	    return state
   288	
   289	
   290	# ---------------------------------------------------------------------------

---
   534	def _probe_health(
   535	    url: str,
   536	    *,
   537	    timeout: int,
   538	    per_request_timeout: int = 5,
   539	    poll_interval: float = 1.0,
   540	) -> bool:
   541	    """Poll an HTTP endpoint until it returns 2xx or ``timeout`` expires.
   542	
   543	    Codex R3 flagged: the earlier single-shot GET failed good builds
   544	    whose apps needed a few seconds to boot. This implementation
   545	    honours ``timeout`` as a real startup grace period — per-request
   546	    timeout stays short (default 5s) so we can retry, but the whole
   547	    probe budget can run up to the configured ``boot_timeout_seconds``.
   548	
   549	    Returns True on first 2xx, False when the budget runs out.
   550	    """
   551	    try:
   552	        import httpx
   553	    except ImportError:   # pragma: no cover - runtime dependency
   554	        return False
   555	
   556	    deadline = time.time() + max(timeout, 1)
   557	    attempts = 0
   558	    while time.time() < deadline:
   559	        attempts += 1
   560	        remaining = max(deadline - time.time(), 0.1)
   561	        req_timeout = min(per_request_timeout, remaining)
   562	        try:
   563	            r = httpx.get(url, timeout=req_timeout)
   564	            if 200 <= r.status_code < 300:
   565	                return True
   566	        except Exception:  # noqa: BLE001
   567	            # Connection refused / DNS error / timeout — the app is not
   568	            # ready yet. Wait briefly and retry unless budget exhausted.
   569	            pass
   570	        # Sleep until either the next poll or budget expiry, whichever
   571	        # comes first.
   572	        time.sleep(min(poll_interval, max(deadline - time.time(), 0)))
   573	    return False
   574	
   575	
   576	# ---------------------------------------------------------------------------
   577	# Git helpers
   578	# ---------------------------------------------------------------------------
   579	
   580	
   581	def _git_head(target_path: Path) -> str:
   582	    try:
   583	        r = subprocess.run(
   584	            ["git", "rev-parse", "HEAD"],
   585	            cwd=str(target_path), capture_output=True, text=True, timeout=5,

---
   361	class _TailBuffer:
   362	    """Accumulate text but keep only the tail of ``max_bytes``.
   363	
   364	    Recent output is more useful than the head when debugging a builder
   365	    that went off the rails. ``truncated`` flips True once we start
   366	    dropping bytes so callers can surface that to users / logs.
   367	
   368	    If a single incoming chunk is larger than ``max_bytes``, we slice
   369	    the tail bytes out of *that* chunk instead of evicting it wholesale
   370	    (Codex R3 flagged: the previous behavior produced an empty buffer
   371	    when a single append overflowed the cap).
   372	    """
   373	
   374	    __slots__ = ("_chunks", "_size", "_max", "truncated")
   375	
   376	    def __init__(self, max_bytes: int) -> None:
   377	        self._chunks: list[str] = []
   378	        self._size = 0
   379	        self._max = max(max_bytes, 1)
   380	        self.truncated = False
   381	
   382	    def append(self, chunk: str) -> None:
   383	        if not chunk:
   384	            return
   385	
   386	        # Oversized single chunk: keep the tail bytes of this chunk only.
   387	        chunk_bytes = chunk.encode("utf-8", errors="ignore")
   388	        if len(chunk_bytes) > self._max:
   389	            tail_bytes = chunk_bytes[-self._max:]
   390	            tail = tail_bytes.decode("utf-8", errors="ignore")
   391	            self._chunks = [tail]
   392	            self._size = len(tail.encode("utf-8", errors="ignore"))
   393	            self.truncated = True
   394	            return
   395	
   396	        self._chunks.append(chunk)
   397	        self._size += len(chunk_bytes)
   398	
   399	        # Normal eviction path: drop whole chunks from the head until
   400	        # we're under the cap again. Safe now because no single chunk
   401	        # is larger than ``_max``.
   402	        while self._size > self._max and len(self._chunks) > 1:
   403	            head = self._chunks.pop(0)
   404	            self._size -= len(head.encode("utf-8", errors="ignore"))
   405	            self.truncated = True
   406	
   407	    def text(self) -> str:
   408	        return "".join(self._chunks)
   409	
   410	

---
    50	
    51	    return completed
    52	
    53	
    54	def build_skip_results(
    55	    feature_queue: list[FeatureStep],
    56	    completed_ids: set[str],
    57	) -> list[StepResult]:
    58	    """Create SKIPPED StepResults for already-completed brownfield features.
    59	
    60	    Uses :attr:`StepStatus.SKIPPED` — these features were done before
    61	    this run started. The dependency gate treats SKIPPED as dep-
    62	    satisfying, and metrics / summary correctly exclude them from
    63	    PASSED / BLOCKED / FAILED counters.
    64	    """
    65	    return [
    66	        StepResult(
    67	            feature_id=f.feature_id,
    68	            status=StepStatus.SKIPPED,
    69	            error_message="Already implemented in target repo (state-scanner detection)",
    70	        )
    71	        for f in feature_queue
    72	        if f.feature_id in completed_ids
    73	    ]
    74	
    75	
    76	def _get_git_log(target_path: Path) -> str:
    77	    """Get full git log with commit messages."""
    78	    try:
    79	        result = subprocess.run(
    80	            ["git", "log", "--oneline", "--all", "-200"],
    81	            cwd=str(target_path),
    82	            capture_output=True, text=True, timeout=10,
    83	        )
    84	        return result.stdout.lower() if result.returncode == 0 else ""
    85	    except Exception:
    86	        return ""
    87	
    88	
    89	def _get_file_set(target_path: Path) -> set[str]:
    90	    """Get set of all file paths in the repo (relative, lowercase)."""

---
    49	def compute_run_metrics(
    50	    state: V3RunState,
    51	    ingestion_doc_count: int = 0,
    52	) -> RunMetrics:
    53	    """Compute aggregate run metrics from the current V3 run state."""
    54	    steps = state.completed_steps
    55	    total = len(steps)
    56	
    57	    if total == 0:
    58	        return RunMetrics(run_id=state.run_id, started_at=state.started_at)
    59	
    60	    passed = [s for s in steps if s.status == StepStatus.PASSED]
    61	    # Both FAILED (tried and broke) and BLOCKED (upstream dep broke)
    62	    # are failures at the run-metric level — they count against
    63	    # failed_features so the number matches the engine's "unsuccessful"
    64	    # run status. blocked_features is tracked separately for detail.
    65	    failed_direct = [s for s in steps if s.status == StepStatus.FAILED]
    66	    blocked = [s for s in steps if s.status == StepStatus.BLOCKED]
    67	    failed = failed_direct + blocked
    68	    skipped = [s for s in steps if s.status == StepStatus.SKIPPED]
    69	    first_pass = [s for s in passed if s.repair_attempts == 0]
    70	    repaired = [s for s in steps if s.repair_attempts > 0]
    71	
    72	    build_sum = sum(s.build_duration_seconds for s in steps)
    73	    verify_sum = sum(s.verify_duration_seconds for s in steps)
    74	    total_active_time = build_sum + verify_sum
    75	
    76	    started = _parse_iso(state.started_at)
    77	    completed_at = state.updated_at or state.started_at
    78	    completed = _parse_iso(completed_at)
    79	    total_duration_seconds = max((completed - started).total_seconds(), 0.0)
    80	
    81	    feature_metrics = [
    82	        FeatureMetric(
    83	            feature_id=s.feature_id,
    84	            status=s.status.value,
    85	            passed_first_try=(s.status == StepStatus.PASSED and s.repair_attempts == 0),
    86	            repair_attempts=s.repair_attempts,
    87	            build_duration_seconds=s.build_duration_seconds,
    88	            verify_duration_seconds=s.verify_duration_seconds,
    89	            files_created=len(s.files_created),
    90	            files_modified=len(s.files_modified),
    91	        )
    92	        for s in steps
    93	    ]
    94	
    95	    return RunMetrics(
    96	        run_id=state.run_id,
    97	        project_name=_resolve_project_name(state),
    98	        started_at=state.started_at,
    99	        completed_at=completed_at,
   100	        total_duration_seconds=total_duration_seconds,
   101	        total_features=total,
   102	        passed_features=len(passed),
   103	        failed_features=len(failed),
   104	        skipped_features=len(skipped),
   105	        blocked_features=len(blocked),
   106	        first_pass_success_rate=len(first_pass) / total,
   107	        repair_rate=len(repaired) / total,
   108	        mean_repair_attempts=(
   109	            sum(s.repair_attempts for s in repaired) / len(repaired)
   110	            if repaired else 0.0
   111	        ),
   112	        build_efficiency=build_sum / total_active_time if total_active_time > 0 else 0.0,
   113	        feature_throughput_per_hour=(
   114	            len(passed) / (total_duration_seconds / 3600.0) if total_duration_seconds > 0 else 0.0
   115	        ),
   116	        features=feature_metrics,
   117	        citex_documents_ingested=ingestion_doc_count,
   118	        citex_queries_by_codex=int(state.metadata.get("citex_queries_by_codex", 0)),
   119	    )
   120	
   121	
   122	def _parse_iso(value: str) -> datetime:
   123	    return datetime.fromisoformat(value.replace("Z", "+00:00"))
   124	
   125	

