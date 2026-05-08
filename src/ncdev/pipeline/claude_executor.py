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

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import (
    DEFAULT_BUILD_TOOLS,
)
from ncdev.core.config import NCDevConfig
from ncdev.pipeline.asset_manifest import (
    manifest_prompt_section,
    verify_manifest_covers_references,
)
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureStep,
    StepResult,
    StepStatus,
    StepVerification,
    TestResult,
)

logger = logging.getLogger(__name__)


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
    implementer_mode: str = "codex",
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
    accept_block = "\n".join(
        [
            f"- required_files (must exist AND mention `{feature.feature_id}` "
            f"in path or content): {accept.required_files or '(none)'}",
            f"- required_routes (must respond 2xx at integration gate): "
            f"{accept.required_routes or '(none)'}",
            f"- required_tests (must exist, mention `{feature.feature_id}`, "
            f"and pass): {accept.required_tests or '(none)'}",
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
- Design system:          {charter_dir}/design-system.json  (if present)
- Feature queue:          {charter_dir}/feature-queue.json
- Target repository:      {target_path}
- Citex project ID:       {project_id}
- Citex URL:              {citex_url}  (optional — query if reachable; skip if not)

{prior_block}

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
2. **Query Citex** at `{citex_url}` if it is reachable, for context on
   prior features and data models. If Citex is not running, skip this
   step rather than retrying — it is optional infrastructure.
3. **Use the `writing-plans` skill** if this is a high-complexity
   feature. For low complexity, go straight to step 4.
4. **Use the `test-driven-development` skill**. Write failing tests
   first that target the structured acceptance above (each
   `required_test` file must exist, mention the feature_id, and
   eventually pass).
5. {impl_step}
6. **Emit the asset manifest** as you build — see the schema below.
7. **Use the `verification-before-completion` skill** before you
   claim done. Run the verification contract's test commands yourself.
   Capture the required screenshots listed in the structured
   acceptance.
8. **If verification fails**, use the `systematic-debugging` skill.
   Do not loop blindly — identify root cause, fix narrowly, re-verify.
9. **Commit the work** once verification passes. Use Conventional
   Commits (`feat({feature.feature_id}): <subject>` or
   `fix({feature.feature_id}): <subject>`). Leave the working tree
   clean.

{manifest_prompt_section(feature.feature_id)}

## What success looks like

- Working tree is clean (all changes committed).
- Every entry in `required_files` exists AND mentions
  `{feature.feature_id}` literally (path or content).
- Every entry in `required_tests` exists, mentions
  `{feature.feature_id}`, and passes when run in isolation.
- Verification contract is satisfied (boot probe, test commands,
  screenshots, files).
- Asset manifest file exists at
  `.ncdev/assets-needed/{feature.feature_id}.json`.
- Your final response summarises what was built in <= 5 sentences.

## What failure looks like (avoid)

- "Implemented, but tests are still failing — here's what I tried."
  → Not done. Use systematic-debugging.
- Working tree dirty when you're "done." → Commit or revert.
- A `required_file` that exists but doesn't mention `{feature.feature_id}`.
  → The verifier will reject. Add a docstring/header line that names it.
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
    config: NCDevConfig | None = None,
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

    # Adapt the prompt to whether Codex is in scope for this run. In
    # claude_only mode, telling Claude to "delegate to Codex via Bash"
    # is a footgun — codex isn't available and the workflow stalls.
    cfg_mode = config.mode if config is not None else "claude_plan_codex_build"
    implementer_mode = "claude" if cfg_mode in {"claude_only"} else "codex"

    prompt = build_feature_prompt(
        feature=feature,
        target_path=target_path,
        charter_dir=charter_dir,
        prior_feature_ids=prior_ids,
        project_id=project_id,
        citex_url=citex_url,
        implementer_mode=implementer_mode,
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
        error_message=(session.error or "") + recoverability_note,
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
    *,
    run_test_commands: bool = True,
    probe_health: bool = True,
    touched_files: list[str] | None = None,
) -> StepVerification:
    """Enforce every clause of the verification contract.

    Belt-and-braces to Claude's in-session ``verification-before-completion``
    skill — we don't trust "claimed done" to mean "actually done".
    """
    ver = StepVerification()
    reasons: list[str] = []

    # 1. Required files from the verification contract must all exist
    for req in bundle.verification.required_files:
        if not (target_path / req).exists():
            reasons.append(f"required file missing: {req}")

    # 2. Asset manifest must exist and cover code references
    if bundle.verification.assets_manifest_required:
        ok, missing = verify_manifest_covers_references(
            target_path, feature.feature_id,
            touched_files=touched_files,
        )
        if not ok:
            if missing == ["<no-manifest>"]:
                reasons.append(f"asset manifest not written for {feature.feature_id}")
            else:
                reasons.append(f"asset references without manifest: {missing[:5]}")

    # 3. Prohibited patterns (regex — treats entries in the contract as
    #    patterns, falls back to literal match if the regex fails to compile).
    #    Feature-local scope matters here for the same reason it matters for
    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
    #    not fail every future feature.
    patterns = bundle.verification.prohibited_patterns
    if patterns:
        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
        if bad:
            reasons.append(f"prohibited patterns found: {bad[:5]}")

    # 4. Required screenshots — REMOVED from per-feature scope.
    #    The contract's global required_screenshots list spans the
    #    whole product (login, signup, dashboard, ...) and demanding
    #    every feature produce all of them is nonsensical: f01-scaffold
    #    can't capture a "dashboard" screenshot before f08 builds the
    #    dashboard. Per-feature screenshots are enforced under
    #    feature.acceptance.required_screenshots (clause 8 below).
    #    The contract's global list is enforced by the end-of-run
    #    integration gate against the cumulative repo state.

    # 5. Minimum test count — prevents "0 tests, all green" gaming
    if bundle.verification.minimum_test_count > 0:
        count = _count_test_files(target_path)
        ver.unit_tests = TestResult(suite="unit", passed=count, success=count > 0)
        if count < bundle.verification.minimum_test_count:
            reasons.append(
                f"test file count {count} below minimum "
                f"{bundle.verification.minimum_test_count}"
            )

    # 6. Run the declared test commands
    if run_test_commands:
        if bundle.verification.backend_test_command:
            ok, out = _run_shell(
                bundle.verification.backend_test_command,
                cwd=target_path, timeout=600,
            )
            ver.integration_tests = TestResult(
                suite="backend", passed=1 if ok else 0,
                failed=0 if ok else 1, success=ok, output=out[:2000],
            )
            if not ok:
                reasons.append(f"backend tests failed: {_last_line(out)}")
        if bundle.verification.frontend_test_command:
            ok, out = _run_shell(
                bundle.verification.frontend_test_command,
                cwd=target_path, timeout=600,
            )
            ver.e2e_tests = TestResult(
                suite="frontend", passed=1 if ok else 0,
                failed=0 if ok else 1, success=ok, output=out[:2000],
            )
            if not ok:
                reasons.append(f"frontend tests failed: {_last_line(out)}")

    # 7. Health probe — if the contract declares a backend_health_url,
    #    the feature is only "done" when that URL responds. Leaving
    #    backend_health_url empty in the contract disables the probe
    #    (common for CLI/library projects). Codex R2 flagged: if the
    #    user put the URL there, they meant it.
    # Health probe is OPT-IN per feature. Default False because most
    # feature sessions don't keep a daemon running after the session
    # exits — probing them all would always fail. Scaffold / boot
    # features set acceptance.verify_app_boots=True to assert that
    # the app must be reachable after their session, and the
    # integration gate covers the rest at end-of-run.
    if probe_health and feature.acceptance.verify_app_boots and bundle.verification.backend_health_url:
        reachable = _probe_health(
            bundle.verification.backend_health_url,
            timeout=bundle.verification.boot_timeout_seconds,
        )
        ver.app_boots = reachable
        if not reachable:
            reasons.append(
                f"backend health URL unreachable: "
                f"{bundle.verification.backend_health_url} — feature "
                f"{feature.feature_id} declared verify_app_boots=True so the "
                "app must respond at session end"
            )

    # 8. Per-feature acceptance — bind verification to *this feature*, not
    #    just the global contract. Closes the silent-skip path where a
    #    feature could PASS by satisfying a globally-empty contract while
    #    its own required files / tests / screenshots are missing.
    accept = feature.acceptance
    for req_file in accept.required_files:
        fp = target_path / req_file
        if not fp.exists():
            reasons.append(
                f"feature acceptance: required file missing: {req_file}"
            )
            continue
        if accept.must_mention_feature_id and not _file_mentions_token(
            fp, feature.feature_id
        ):
            reasons.append(
                f"feature acceptance: {req_file} does not mention "
                f"feature_id '{feature.feature_id}' (must_mention_feature_id=True)"
            )

    for req_test in accept.required_tests:
        tp = target_path / req_test
        if not tp.exists():
            reasons.append(
                f"feature acceptance: required test missing: {req_test}"
            )
            continue
        if accept.must_mention_feature_id and not _file_mentions_token(
            tp, feature.feature_id
        ):
            reasons.append(
                f"feature acceptance: test {req_test} does not reference "
                f"feature_id '{feature.feature_id}'"
            )
            continue
        if run_test_commands:
            ok, out = _run_shell(
                f"python -m pytest -q -x {req_test}"
                if req_test.endswith(".py")
                else f"npx vitest run {req_test}",
                cwd=target_path,
                timeout=300,
            )
            if not ok:
                reasons.append(
                    f"feature acceptance: required test {req_test} failed: "
                    f"{_last_line(out)}"
                )

    for req_shot in accept.required_screenshots:
        if not _screenshot_exists(target_path, req_shot):
            reasons.append(
                f"feature acceptance: required screenshot not captured: {req_shot}"
            )

    ver.failure_reasons = reasons
    ver.overall_passed = not reasons
    ver.prohibited_patterns = [r for r in reasons if "prohibited" in r.lower()]
    return ver


def _file_mentions_token(path: Path, token: str) -> bool:
    """True if ``path`` (a small text file) references ``token`` literally.

    Reads up to 1 MB to keep verification cheap on large files. Returns
    False on any read error — callers treat that as "doesn't mention",
    which is the safe default for an acceptance gate.
    """
    try:
        if path.stat().st_size > 1_000_000:
            return token in path.name
        text = path.read_text(encoding="utf-8", errors="ignore")
        return token in text or token in path.name
    except OSError:
        return False


def _grep_for_prohibited(
    target_path: Path,
    patterns: list[str],
    *,
    touched_files: list[str] | None = None,
) -> list[str]:
    """Scan git-tracked files for prohibited patterns.

    Each entry is treated as a regular expression via ``re.search``. If
    a pattern fails to compile, falls back to a substring check so
    human-written entries like ``TODO`` still work.

    When ``touched_files`` is provided, only scan that feature-local set.
    This keeps brownfield legacy debt from failing unrelated future work.
    """
    compiled: list[tuple[str, re.Pattern[str] | None]] = []
    for pat in patterns:
        try:
            compiled.append((pat, re.compile(pat)))
        except re.error:
            compiled.append((pat, None))

    hits: list[str] = []
    try:
        ls = subprocess.run(
            ["git", "ls-files"],
            cwd=str(target_path), capture_output=True, text=True, timeout=10,
        )
        if ls.returncode != 0:
            return []
        tracked_files = {f for f in ls.stdout.splitlines() if f}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if touched_files is not None:
        files = [f for f in touched_files if f in tracked_files]
    else:
        files = sorted(tracked_files)

    for f in files:
        fp = target_path / f
        try:
            if fp.stat().st_size > 1_000_000:
                continue
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat, regex in compiled:
            hit = regex.search(text) if regex is not None else (pat in text)
            if hit:
                hits.append(f"{f} contains '{pat}'")
                if len(hits) > 20:
                    return hits
                break   # one hit per file is enough
    return hits


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------


def _screenshot_exists(target_path: Path, name: str) -> bool:
    """True if a file matching the screenshot name exists under the repo.

    Matches by token overlap rather than substring, so a required slug
    "landing-shell" matches Claude's actual output of
    "landing-desktop-1440x900.png" (both share the "landing" token).
    Strict substring matching was rejecting valid screenshots that
    Claude named with viewport / dimension suffixes — a common pattern.

    Search dirs: .ncdev/evidence/<feature_id?>/, evidence/screenshots/,
    docs/screenshots/. Recursive within each.
    """
    slug = name.replace(" ", "-").replace("/", "-").lower()
    slug_tokens = {t for t in slug.split("-") if t and t != "shell"}
    if not slug_tokens:
        return False
    candidate_dirs = [
        target_path / ".ncdev" / "evidence",
        target_path / "evidence" / "screenshots",
        target_path / "docs" / "screenshots",
    ]
    for d in candidate_dirs:
        if not d.exists():
            continue
        for f in d.rglob("*.png"):
            stem = f.stem.lower().replace("_", "-")
            file_tokens = {t for t in stem.split("-") if t}
            # Substring fallback (legacy behaviour: <slug>.png exactly)
            if slug in stem:
                return True
            # Token-overlap match: at least one substantive token in common
            if slug_tokens & file_tokens:
                return True
    return False


def _count_test_files(target_path: Path) -> int:
    patterns = (
        "tests/**/test_*.py",
        "tests/**/*_test.py",
        "**/*.test.ts",
        "**/*.test.tsx",
        "**/*.spec.ts",
        "**/*.spec.tsx",
        "backend/tests/**/*.py",
        "frontend/tests/**/*.ts",
        "frontend/tests/**/*.tsx",
    )
    seen: set[Path] = set()
    for pat in patterns:
        for p in target_path.glob(pat):
            if p.is_file() and "node_modules" not in p.parts:
                seen.add(p.resolve())
    return len(seen)


def _run_shell(cmd: str, *, cwd: Path, timeout: int) -> tuple[bool, str]:
    """Run ``cmd`` in a shell. Returns (success, combined_output)."""
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=str(cwd),
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0, (r.stdout + "\n" + r.stderr)
    except subprocess.TimeoutExpired as exc:
        return False, f"timed out after {timeout}s: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"exec error: {exc}"


def _last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
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
