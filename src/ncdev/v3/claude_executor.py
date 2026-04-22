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
import subprocess
import time
from pathlib import Path

from ncdev.claude_session import (
    DEFAULT_BUILD_TOOLS,
    ClaudeSessionResult,
    run_claude_session,
)
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
    model: str = "claude-opus-4-6",
    timeout: int = 3600,
    max_budget_usd: float | None = None,
    citex_url: str = "http://localhost:20161",
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
    session = run_claude_session(
        prompt,
        cwd=target_path,
        tools=DEFAULT_BUILD_TOOLS,
        model=model,
        timeout=timeout,
        permission_mode="acceptEdits",
        include_codex_protocol=True,
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

    # Post-hoc verification (Claude's own verification-before-completion
    # skill should have caught most things; this is our belt-and-braces)
    verification = _post_session_verification(
        target_path, feature, charter_bundle,
    )

    # Decide status
    if session.success and made_commit and not dirty and verification.overall_passed:
        status = StepStatus.PASSED
    elif made_commit and verification.overall_passed:
        # Claude might have exited with non-zero for trivial reasons; if
        # the commit and verification are good, we accept.
        status = StepStatus.PASSED
    else:
        # Something is wrong. Commit whatever is there with [BROKEN] tag
        # so the next feature has context to build on.
        if dirty:
            _commit_broken(target_path, feature)
            post_commit = _git_head(target_path)
        status = StepStatus.FAILED

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
        error_message=session.error or "",
        builder_output=(session.final_text or "")[:2000],
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


# ---------------------------------------------------------------------------
# Post-session verification (light — Claude does the heavy lifting)
# ---------------------------------------------------------------------------


def _post_session_verification(
    target_path: Path,
    feature: FeatureStep,
    bundle: CharterBundle,
) -> StepVerification:
    """Sanity-check what Claude left behind. Not the primary gate."""
    ver = StepVerification()
    reasons: list[str] = []

    # 1. Required files from the verification contract must all exist
    for req in bundle.verification.required_files:
        if not (target_path / req).exists():
            reasons.append(f"required file missing: {req}")

    # 2. Asset manifest must exist and cover code references
    if bundle.verification.assets_manifest_required:
        ok, missing = verify_manifest_covers_references(target_path, feature.feature_id)
        if not ok:
            if missing == ["<no-manifest>"]:
                reasons.append(f"asset manifest not written for {feature.feature_id}")
            else:
                reasons.append(f"asset references without manifest: {missing[:5]}")

    # 3. Prohibited patterns (quick grep)
    patterns = bundle.verification.prohibited_patterns
    if patterns:
        bad = _grep_for_prohibited(target_path, patterns)
        if bad:
            reasons.append(f"prohibited patterns found: {bad[:5]}")

    ver.failure_reasons = reasons
    ver.overall_passed = not reasons
    ver.prohibited_patterns = reasons if any("prohibited" in r for r in reasons) else []
    return ver


def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
    """Grep committed files (staged tree) for prohibited patterns."""
    hits: list[str] = []
    try:
        # Only scan files git tracks — avoids node_modules etc.
        ls = subprocess.run(
            ["git", "ls-files"],
            cwd=str(target_path), capture_output=True, text=True, timeout=10,
        )
        if ls.returncode != 0:
            return []
        files = [f for f in ls.stdout.splitlines() if f]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    for pat in patterns:
        for f in files:
            # Skip binary / large files cheaply
            fp = target_path / f
            try:
                if fp.stat().st_size > 1_000_000:
                    continue
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if pat in text:
                hits.append(f"{f} contains '{pat}'")
                if len(hits) > 20:
                    return hits
    return hits


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
            continue
        flag, path = parts[0], parts[-1]
        if flag == "A":
            created.append(path)
        elif flag in ("M", "R", "C"):
            modified.append(path)
    return created, modified


def _commit_broken(target_path: Path, feature: FeatureStep) -> None:
    try:
        subprocess.run(["git", "add", "-A"],
                       cwd=str(target_path), capture_output=True, timeout=10)
        subprocess.run(
            ["git", "commit", "-m",
             f"[BROKEN] {feature.feature_id}: {feature.title}\n\n"
             "Claude session did not reach a clean-tree final state. "
             "Committed for recoverability."],
            cwd=str(target_path), capture_output=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
