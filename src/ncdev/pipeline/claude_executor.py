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
import subprocess
import time
from pathlib import Path

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import (
    DEFAULT_BUILD_TOOLS,
)
from ncdev.core.config import NCDevConfig
from ncdev.monitoring import MonitorEventWriter
from ncdev.pipeline.asset_manifest import (
    manifest_prompt_section,
)
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureStep,
    StepResult,
    StepStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt composition
# ---------------------------------------------------------------------------


def _load_prior_verdict_findings(
    feature_id: str,
    current_run_dir: Path | None,
) -> str:
    """Find the most recent prior run's ``verdict.json`` for this feature
    and return a formatted prompt block describing the *specific* reasons
    and repair guidance from the grounded verifier that rejected the prior
    commit.

    Returns an empty string when:
      - no current_run_dir is given,
      - no prior run dir exists alongside it,
      - no verdict.json exists for this feature in any prior run, or
      - the most recent verdict.json for this feature was a PASS.

    This is what makes the repair loop actually close: without it, a
    feature that the verifier rejected is re-attempted with the *same*
    prompt as the first attempt, so the same omission tends to recur.
    With it, the next session sees the verbatim FAIL reasons + repair
    guidance inline and can act on them.
    """
    if current_run_dir is None or not current_run_dir.parent.exists():
        return ""
    runs_root = current_run_dir.parent
    if not runs_root.is_dir():
        return ""
    try:
        candidates = sorted(
            (
                p for p in runs_root.iterdir()
                if p.is_dir() and p != current_run_dir
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return ""
    for prior in candidates:
        vpath = prior / "steps" / feature_id / "verdict.json"
        if not vpath.exists():
            continue
        try:
            v = json.loads(vpath.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if str(v.get("verdict", "")).upper() == "PASS":
            # This prior run actually passed verification for this feature;
            # don't surface it as a repair note. (The feature is being
            # re-attempted because it failed for a different reason.) Stop.
            return ""
        reasons = [r for r in (v.get("reasons") or []) if (r or "").strip()]
        guidance = [
            g for g in (v.get("repair_guidance") or []) if (g or "").strip()
        ]
        if not reasons and not guidance:
            return ""
        lines: list[str] = [
            "## Prior verification findings — fix THESE before re-committing",
            "",
            f"This feature was attempted in a prior cycle (run "
            f"`{prior.name}`) and its commit was rejected by the",
            "grounded verifier. The verbatim failure reasons and repair",
            "guidance are below. Address each one in your repair pass.",
            "",
        ]
        if reasons:
            lines.append("### Failure reasons")
            lines.append("")
            for reason in reasons[:10]:
                short = reason.strip()[:600] + (
                    "... [truncated]" if len(reason.strip()) > 600 else ""
                )
                lines.append(f"- {short}")
            lines.append("")
        if guidance:
            lines.append("### Repair guidance")
            lines.append("")
            for g in guidance[:10]:
                short = g.strip()[:600] + (
                    "... [truncated]" if len(g.strip()) > 600 else ""
                )
                lines.append(f"- {short}")
            lines.append("")
        lines.extend([
            "Treat these as concrete, structured failure modes — not vague",
            "suggestions. For each, decide whether it's a code fix (do it),",
            "a missing dependency (add it), or a genuinely incorrect",
            "acceptance criterion (call out the contract conflict explicitly",
            "in your final response so the Steward can amend it).",
            "",
        ])
        return "\n".join(lines)
    return ""


def build_feature_prompt(
    feature: FeatureStep,
    target_path: Path,
    charter_dir: Path,
    prior_feature_ids: list[str],
    project_id: str,
    citex_url: str = "http://localhost:20161",
    implementer_mode: str = "codex",
    prior_verdict_findings: str = "",
) -> str:
    """Compose the single prompt handed to Claude for this feature.

    Deliberately terse. Heavy reference material (contract, verification,
    design system) stays on disk — Claude reads it with the Read tool.
    This is a departure from the old prescriptive mega-prompts.

    ``implementer_mode`` adapts the workflow language. Pass "codex" when
    the Codex protocol is in scope (Claude delegates impl to Codex via
    Bash). Pass "claude" for claude_only mode where Claude does the
    implementation directly without any shell-out — the Codex sections
    of the prompt would otherwise mislead the model into a tool call
    that won't work.
    """
    prior_block = (
        "No prior features — this is the first build in the queue."
        if not prior_feature_ids
        else f"Prior features already built and verified: {', '.join(prior_feature_ids)}"
    )

    accept = feature.acceptance
    mention_note = (
        f"must mention `{feature.feature_id}` in path or content"
        if accept.must_mention_feature_id
        else "no feature-id marker required; engine provenance tracks ownership"
    )
    accept_block = "\n".join(
        [
            f"- required_files (must exist; {mention_note}): "
            f"{accept.required_files or '(none)'}",
            f"- required_routes (must respond 2xx at integration gate): "
            f"{accept.required_routes or '(none)'}",
            f"- required_tests (must exist and pass; {mention_note}): "
            f"{accept.required_tests or '(none)'}",
            f"- required_screenshots (under .ncdev/evidence/): "
            f"{accept.required_screenshots or '(none)'}",
            f"- verify_app_boots: {accept.verify_app_boots} "
            f"(when True, the per-feature verifier probes the contract's "
            f"backend_health_url at the end of this session — leave the app running)",
            f"- must_mention_feature_id: {accept.must_mention_feature_id}",
        ]
    )

    if implementer_mode == "claude":
        impl_paragraph = (
            "You are running in claude_only mode — there is NO Codex peer in "
            "this session. Do all implementation and test writing yourself "
            "with Edit/Write/Bash. Do not invoke `codex exec`."
        )
        impl_step = (
            "**Implement directly.** Use Edit/Write to author production code "
            "and tests. Run tests with Bash."
        )
    else:
        impl_paragraph = (
            "You have the Claude skill machinery available; use it. Codex is "
            "your implementation peer (see the Codex protocol in your system "
            "prompt) — delegate raw implementation and test writing to Codex "
            "via Bash, keep judgment and review yourself."
        )
        impl_step = (
            "**Delegate implementation to Codex via Bash.** One well-scoped "
            "Codex call per sub-task is better than five vague ones. Review "
            "Codex's output yourself before moving on."
        )

    return f"""# Feature: {feature.feature_id} — {feature.title}

{impl_paragraph}

## Context

- Project charter:        {charter_dir}/target-project-contract.json
- Verification contract:  {charter_dir}/verification-contract.json
- Behavior contract:      {charter_dir}/behavior-contract.v1.json
- Design system:          {charter_dir}/design-system.json  (if present)
- Process runbook:        {charter_dir}/project-runbook.json  (model-authored command policy, if present)
- Feature queue:          {charter_dir}/feature-queue.json
- Target repository:      {target_path}
- Citex project ID:       {project_id}
- Citex URL:              {citex_url}  (optional — query if reachable; skip if not)

{prior_block}
{prior_verdict_findings + chr(10) if prior_verdict_findings else ""}
## Your feature spec

- ID:          {feature.feature_id}
- Title:       {feature.title}
- Description: {feature.description}
- Complexity:  {feature.estimated_complexity}
- Priority:    {feature.priority}

### Acceptance criteria (free-form, for your understanding)
{chr(10).join(f"- {c}" for c in feature.acceptance_criteria) or "- (none specified — infer from description)"}

### Structured acceptance (ENFORCED by the verifier)

The following bag is checked by NC Dev's automated verifier after your
session ends. Failing any clause marks the feature FAILED and halts
the run by default. Plan your work so each clause is satisfied.

{accept_block}

### Test requirements
{chr(10).join(f"- {t}" for t in feature.test_requirements) or "- (use your judgment — tests MUST exist and verify behaviour, not just syntax)"}

### Depends on
{", ".join(feature.depends_on_features) if feature.depends_on_features else "(none)"}

## Required workflow

1. **Read** the charter artifacts listed above. They are the hard
   constraints for stack, ports, auth, deployment. Do not override them.
   Build inside the target repository's normal source/test structure;
   `.nc-dev/` is NC Dev's private run storage and must not contain
   implementation code.
2. **Query Citex** at `{citex_url}` if it is reachable, for context on
   prior features and data models. If Citex is not running, skip this
   step rather than retrying — it is optional infrastructure.
3. **Use the `writing-plans` skill** if this is a high-complexity
   feature. For low complexity, go straight to step 4.
4. **Use the `test-driven-development` skill against the behavior
   contract.** Read `{charter_dir}/behavior-contract.v1.json`, find the
   scenario(s) for `{feature.feature_id}`, and write failing tests first
   for those observable behaviours before implementation. Each
   `required_test` file must exist, target the structured acceptance
   above, and eventually pass.
5. {impl_step}
6. **Emit the asset manifest** as you build — see the schema below.
7. **The engine records what your session touched** automatically — you
   do not need to add `# Feature: <id>` markers to every file. (You may
   add them if it helps readability, but they are not required for the
   verifier.)
8. **Self-verify against EVERY acceptance criterion — one at a time.**
   Before you commit, walk the acceptance-criteria list above item by
   item. For each criterion, name the specific file, line, or passing
   test that proves your diff satisfies it. "Should", "mostly", or
   "the rest cover it" is not proof. An independent oracle reviews the
   diff against each criterion and BLOCKS the commit if even one is
   unmet — and the recurring failure pattern is implementers stopping
   exactly one criterion short. Do not be that implementer. Then use
   the `verification-before-completion` skill: run the verification
   contract's test commands yourself and capture the required
   screenshots.
9. **If verification fails**, use the `systematic-debugging` skill.
   Do not loop blindly — identify root cause, fix narrowly, re-verify.
10. **Commit the work** once verification passes. Use Conventional
    Commits (`feat({feature.feature_id}): <subject>` or
    `fix({feature.feature_id}): <subject>`). Leave the working tree
    clean.

{manifest_prompt_section(feature.feature_id)}

## What success looks like

- Working tree is clean (all changes committed).
- Every entry in `required_files` exists.
- Every entry in `required_tests` exists and passes when run in isolation.
- If `must_mention_feature_id` is true, required files and tests mention
  `{feature.feature_id}` literally (path or content).
- Verification contract is satisfied (boot probe, test commands,
  screenshots, files).
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
- **A cosmetic change dressed up as a fix.** If the bug is a 401/403/
  500, a form that accepts invalid input, or a console error, the fix
  must change that *observable behaviour*. Editing copy, contrast, or
  adding a banner that hides the error is NOT a fix — fix the root
  cause so the failing status becomes a 2xx / the validation actually
  rejects bad input / the console error is gone.
- **Fixing the wrong component.** A bug is defined by the route or
  selector the QA harness actually probes (named in the description /
  acceptance criteria). Patch THAT code path. A similarly-named
  component the probe never exercises is not the bug — verify your
  edit lands on the exact route/element the failure was observed on.

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
    config: NCDevConfig | None = None,
    run_test_commands: bool = True,
    probe_health: bool = True,
    run_gauntlet_check: bool = True,
) -> StepResult:
    """Run one feature via a Claude session and return the StepResult.

    See module docstring for the outer flow. Verification is performed by
    the grounded agentic verifier (``grounded_verify``): a hard floor
    (compile/commit) gate, evidence gathering (tests, diff, screenshots),
    and an evidence-grounded judge. A feature PASSES iff work landed
    (a commit) and the verifier approves.

    ``run_test_commands``, ``probe_health`` and ``run_gauntlet_check`` are
    accepted for backward compatibility but no longer drive behavior — the
    grounded verifier replaced the old post-session checks and the layered
    Gauntlet. (Test commands are sourced from the verification contract.)
    """
    step_dir = run_dir / "steps" / feature.feature_id
    step_dir.mkdir(parents=True, exist_ok=True)
    monitor = MonitorEventWriter(run_dir)

    charter_dir = run_dir / "outputs"
    prior_ids = [r.feature_id for r in prior_results if r.status == StepStatus.PASSED]

    # Adapt the prompt to whether Codex is in scope for this run. In
    # claude_only mode, telling Claude to "delegate to Codex via Bash"
    # is a footgun — codex isn't available and the workflow stalls.
    cfg_mode = config.mode if config is not None else "claude_plan_codex_build"
    implementer_mode = "claude" if cfg_mode in {"claude_only"} else "codex"

    # If this feature was rejected by the grounded verifier in any prior
    # run, surface the verbatim reasons + repair guidance inline so the
    # next session can act on them. Empty string when no prior run
    # rejected this feature.
    prior_verdict_findings = _load_prior_verdict_findings(
        feature_id=feature.feature_id,
        current_run_dir=run_dir,
    )

    prompt = build_feature_prompt(
        feature=feature,
        target_path=target_path,
        charter_dir=charter_dir,
        prior_feature_ids=prior_ids,
        project_id=project_id,
        citex_url=citex_url,
        implementer_mode=implementer_mode,
        prior_verdict_findings=prior_verdict_findings,
    )
    (step_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    # Guarantee a commit identity before any commit in this feature —
    # both Claude's own feature commits and the [BROKEN] fallback.
    _ensure_git_identity(target_path)

    # Snapshot git state so we can detect what changed
    pre_commit = _git_head(target_path)

    start = time.time()
    from ncdev.core.capability_ledger import recent_lessons
    from ncdev.core.capability_probe import scan_installed_skills
    from ncdev.core.skill_selector import (
        render_skill_block,
        select_skills,
        work_type_for,
    )

    # Best-effort work-type classification. If the feature/charter objects
    # in scope expose a clear brownfield or frontend signal, use it; if
    # not, default to False -- that yields a safe "greenfield_backend"
    # skill set and never crashes.
    _is_brownfield = bool(charter_bundle.contract.is_brownfield or charter_bundle.contract.existing_repo_path)
    _touches_frontend = bool(charter_bundle.contract.frontend_framework or charter_bundle.verification.frontend_test_command)
    _work_type = work_type_for(
        is_brownfield=_is_brownfield, touches_frontend=_touches_frontend
    )
    _selected_skills = select_skills(
        _work_type,
        scan_installed_skills(target_path),
        lessons=recent_lessons(project_name=charter_bundle.contract.project_name),
    )
    _skill_block = render_skill_block(_selected_skills)
    monitor.emit(
        "agent_started",
        phase="building",
        feature_id=feature.feature_id,
        message=f"Builder session starting for {feature.feature_id}",
        data={
            "selected_skills": list(_selected_skills),
            "work_type": _work_type,
            "implementer_mode": implementer_mode,
        },
    )

    # Record what the builder capability resolved to, for the ledger.
    from ncdev.core.capability_probe import probe_codex
    from ncdev.core.capability_policy import resolve_model

    _resolved_provider = (
        "openai_codex" if implementer_mode == "codex" else "anthropic_claude_code"
    )
    _resolved_model = (
        resolve_model("openai_codex", model, probe_codex())
        if implementer_mode == "codex"
        else "auto"
    )

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
        append_system_prompt=_skill_block or None,
        on_event=lambda event: monitor.emit_ai_event(
            event,
            phase="building",
            feature_id=feature.feature_id,
        ),
    )
    build_duration = time.time() - start
    monitor.emit(
        "agent_finished",
        phase="building",
        feature_id=feature.feature_id,
        message=session.summary(),
        data={
            "success": session.success,
            "duration_seconds": session.duration_seconds,
            "total_cost_usd": session.total_cost_usd,
            "tool_calls": len(session.tool_calls),
            "codex_invocations": len(session.codex_invocations),
            "subagents_dispatched": list(session.subagents_dispatched),
            "skills_invoked": list(session.skills_invoked),
        },
    )

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

    # Grounded agentic verification — hard floor (compile/commit) + evidence
    # gathering (tests, diff, screenshots) + an evidence-grounded judge. This
    # subsumes the old post-session checks and the layered Gauntlet. Imported
    # lazily: grounded_verify.evidence imports _run_shell from this module, so
    # a module-level import would be circular.
    from ncdev.pipeline.grounded_verify import grounded_verify

    verification = grounded_verify(
        target_path,
        feature_id=feature.feature_id,
        intent=(feature.description or feature.title or feature.feature_id),
        pre_commit=pre_commit,
        backend_test_cmd=charter_bundle.verification.backend_test_command or None,
        frontend_test_cmd=charter_bundle.verification.frontend_test_command or None,
        compile_cmd=charter_bundle.verification.build_command or None,
        changed_files=touched,
        diff=_git_diff_text(target_path, pre_commit),
        prior_context="",
        step_dir=step_dir,
    )
    monitor.emit(
        "verification_finished",
        phase="building",
        feature_id=feature.feature_id,
        message=(
            "verification passed"
            if verification.overall_passed
            else "verification failed"
        ),
        data={
            "overall_passed": verification.overall_passed,
            "failure_reasons": list(verification.failure_reasons),
        },
    )

    # Status: PASSED iff work landed and the grounded verifier approved.
    # session.success is no longer part of the verdict — the SIGTERM
    # false-fail class is gone; the hard floor + evidence judge real state.
    recoverability_note = ""
    gauntlet_note = ""
    if made_commit and verification.overall_passed:
        status = StepStatus.PASSED
    else:
        # Something is wrong. Commit whatever is there with [BROKEN] tag
        # so the next feature has context to build on. If that commit
        # itself fails (repo hook blocks it, git identity missing, etc.)
        # we surface it explicitly — recoverability is a guarantee we
        # promise in the docs, silent failure is not acceptable.
        if dirty:
            if _commit_broken(target_path, feature):
                post_commit = _git_head(target_path)
            else:
                recoverability_note = (
                    " | recoverability: [BROKEN] commit failed — dirty "
                    "working tree remains; see log for git error"
                )
        status = StepStatus.FAILED

    # Reuse the diff — or recompute if a [BROKEN] commit was made above
    files_created = feature_files_created
    files_modified = feature_files_modified
    if status == StepStatus.FAILED and dirty:
        files_created, files_modified = _diff_since(target_path, pre_commit)

    result = StepResult(
        feature_id=feature.feature_id,
        status=status,
        build_duration_seconds=build_duration,
        verify_duration_seconds=0.0,  # Claude's in-session verification is bundled into build time
        repair_attempts=0,   # Claude handles repair internally via skills
        verification=verification,
        files_created=files_created,
        files_modified=files_modified,
        commit_sha=post_commit or "",
        error_message=(session.error or "") + recoverability_note + gauntlet_note,
        builder_output=(session.final_text or "")[:2000],
        resolved_provider=_resolved_provider,
        resolved_model=_resolved_model,
        skills_steered=_selected_skills,
        cost_usd=session.total_cost_usd or 0.0,
    )
    # Persist the session cost + skills in metadata for metrics
    (step_dir / "result.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8",
    )
    (step_dir / "signals.json").write_text(json.dumps({
        "success": session.success,
        "made_commit": made_commit,
        "dirty_after": dirty,
        "skills_invoked": session.skills_invoked,
        "subagents_dispatched": session.subagents_dispatched,
        "codex_invocations": len(session.codex_invocations),
        "tool_calls": len(session.tool_calls),
        "total_cost_usd": session.total_cost_usd,
        "duration_seconds": session.duration_seconds,
    }, indent=2), encoding="utf-8")

    return result


def _run_shell(cmd: str, *, cwd: Path, timeout: int) -> tuple[bool, str]:
    """Run ``cmd`` in a shell. Returns (success, combined_output).

    ``errors="replace"`` on decode: test runners / lint / scanners can
    emit non-UTF-8 bytes (a failing test that prints binary, a tool
    that writes Latin-1). Strict decode would raise UnicodeDecodeError
    and crash the factory mid-run rather than reporting the command as
    failed. Replacement keeps the output a valid str for the verifier.
    """
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=str(cwd),
            capture_output=True, text=True, errors="replace", timeout=timeout,
        )
        return r.returncode == 0, (r.stdout + "\n" + r.stderr)
    except subprocess.TimeoutExpired as exc:
        return False, f"timed out after {timeout}s: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"exec error: {exc}"


def _last_line(text: str) -> str:
    """Summarise failing command output for a failure reason.

    The literal last line is often a generic hint (e.g. a test runner's
    "No tests found. You may need to escape symbols..." footer) while
    the real cause — a ReferenceError, a stack trace — sits a few lines
    above. Prefer the first line that looks like an error; always also
    include the final lines so the runner's own verdict is visible.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return "(no output)"
    error_markers = (
        "error", "exception", "traceback", "referenceerror",
        "typeerror", "assert", "failed", "cannot find",
    )
    picked: list[str] = []
    for line in lines:
        if any(m in line.lower() for m in error_markers):
            picked.append(line)
            break
    picked.extend(line for line in lines[-4:] if line not in picked)
    return " ⏎ ".join(picked)[:400]


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


def _git_diff_text(target_path: Path, ref: str) -> str:
    """Unified diff from ``ref`` to HEAD — the feature's whole change.

    Feeds the gauntlet's anti-bypass (L7) and oracle (L8) layers. An
    empty ref or git failure yields "" so those layers skip cleanly.

    Robustness notes:

    - ``--no-color`` keeps the diff plain (defensive — config could
      force color).
    - ``--no-textconv`` avoids running textconv filters that could be
      slow or themselves emit binary.
    - ``errors="replace"`` on the decode: a feature commit can include
      a file git's heuristic does not classify as binary (e.g. a PDF
      fixture, a font, a sample doc with a stray high byte) and then
      ``git diff`` dumps raw bytes. With strict UTF-8 + ``text=True``
      a single 0xDA byte would raise UnicodeDecodeError and crash the
      whole factory mid-run (observed on f06's commit). We decode the
      captured bytes ourselves with replacement so the diff is always
      a valid str — the oracle reads it as context, not as something
      that must round-trip byte-exact.
    """
    if not ref:
        return ""
    try:
        r = subprocess.run(
            ["git", "diff", "--no-color", "--no-textconv", f"{ref}..HEAD"],
            cwd=str(target_path),
            capture_output=True,  # bytes — we decode explicitly below
            timeout=20,
        )
        if r.returncode != 0:
            return ""
        return r.stdout.decode("utf-8", errors="replace")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _ensure_git_identity(target_path: Path) -> None:
    """Guarantee the repo has a commit identity (v4 defect #6).

    If neither a global nor a local ``user.email`` is set, every
    ``git commit`` in the run fails — including the ``[BROKEN]``
    recoverability commit. A failed ``[BROKEN]`` commit leaves a dirty
    tree that the next cycle misreads as "Claude made changes". We set
    a repo-local fallback identity (never global) so commits always
    succeed; a real configured identity is left untouched.
    """
    try:
        existing = subprocess.run(
            ["git", "config", "user.email"],
            cwd=str(target_path), capture_output=True, text=True, timeout=5,
        )
        if existing.returncode == 0 and existing.stdout.strip():
            return  # a real identity is configured — leave it alone
        for key, value in (
            ("user.email", "ncdev@localhost"),
            ("user.name", "NC Dev"),
        ):
            subprocess.run(
                ["git", "config", "--local", key, value],
                cwd=str(target_path), capture_output=True, text=True, timeout=5,
            )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("git identity setup skipped: %s", exc)


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
            continue
        flag, path = parts[0], parts[-1]
        if flag == "A":
            created.append(path)
        elif flag in ("M", "R", "C"):
            modified.append(path)
    return created, modified


def _commit_broken(target_path: Path, feature: FeatureStep) -> bool:
    """Commit leftover dirty tree with [BROKEN] tag. Returns True on success.

    Explicitly checks git return codes and surfaces failure so the
    caller knows whether recoverability actually worked. If pre-commit
    hooks reject the commit (e.g. the repo has its own guards), we bail
    cleanly and let the orchestrator handle it.
    """
    try:
        add = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(target_path), capture_output=True, text=True, timeout=10,
        )
        if add.returncode != 0:
            logger.warning("BROKEN-commit: git add failed: %s", add.stderr[:200])
            return False
        commit = subprocess.run(
            ["git", "commit", "-m",
             f"[BROKEN] {feature.feature_id}: {feature.title}\n\n"
             "Claude session did not reach a clean-tree final state. "
             "Committed for recoverability."],
            cwd=str(target_path), capture_output=True, text=True, timeout=10,
        )
        if commit.returncode != 0:
            logger.warning(
                "BROKEN-commit: git commit failed (rc=%d): %s",
                commit.returncode,
                (commit.stderr or commit.stdout)[:300],
            )
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("BROKEN-commit: %s", exc)
        return False
