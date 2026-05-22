"""L5 — visual verification.

Unit tests pass on a visually broken page: a blank render, an error
banner, an unstyled layout, a stack-trace overlay. L5 closes that gap.
It locates the screenshots the build session was required to capture
and runs an AI-vision review of each against the feature's intent.

L5 only applies to features that declare ``required_screenshots`` — a
backend-only feature skips it. A missing screenshot is a blocking
failure (the build session did not produce required evidence); a
screenshot that vision judges broken is a blocking failure.
"""
from __future__ import annotations

import time
from pathlib import Path

from ncdev.pipeline.gauntlet.context import GauntletContext, extract_json_object
from ncdev.pipeline.gauntlet.models import GauntletLayerResult, LayerStatus

# Where build sessions are told to write evidence (see claude_executor).
_EVIDENCE_DIRS = (
    (".ncdev", "evidence"),
    ("evidence", "screenshots"),
    ("docs", "screenshots"),
)


def _locate_screenshot(repo: Path, name: str) -> Path | None:
    """Find the PNG matching a required screenshot name, by token overlap.

    Mirrors claude_executor._screenshot_exists: a required slug
    "landing-shell" matches "landing-desktop-1440x900.png" via the
    shared "landing" token, tolerating viewport/dimension suffixes.
    """
    slug = name.replace(" ", "-").replace("/", "-").lower()
    slug_tokens = {t for t in slug.split("-") if t and t != "shell"}
    if not slug_tokens:
        return None
    for parts in _EVIDENCE_DIRS:
        d = repo.joinpath(*parts)
        if not d.exists():
            continue
        for f in sorted(d.rglob("*.png")):
            stem = f.stem.lower().replace("_", "-")
            file_tokens = {t for t in stem.split("-") if t}
            if slug in stem or (slug_tokens & file_tokens):
                return f
    return None


def _build_vision_prompt(screenshot: Path, feature_title: str, criteria: list[str]) -> str:
    crit = "\n".join(f"  - {c}" for c in criteria)
    return f"""Read the screenshot image at: {screenshot}

It should show a working UI screen for this feature:
Feature: {feature_title}
Relevant acceptance criteria:
{crit}

Judge the rendered screen. Mark it broken if you see ANY of:
  - an error banner, toast, or stack-trace / exception overlay
  - an unstyled or visibly broken layout (overlapping, off-screen)
  - a blank or empty state where real content is expected
  - a perpetual loading spinner / skeleton with no content
  - placeholder lorem-ipsum or obviously fake content

Respond with ONLY a JSON object:
{{"ok": true|false, "reason": "<one line>"}}"""


def _review_screenshot(
    screenshot: Path, ctx: GauntletContext,
) -> tuple[bool, str]:
    """AI-vision review of one screenshot. Returns (ok, reason).

    Isolated so tests can monkeypatch it without spawning a CLI or
    needing a real image.
    """
    from ncdev.claude_session import run_claude_session

    criteria = [c for c in ctx.feature.acceptance_criteria if c.strip()]
    prompt = _build_vision_prompt(screenshot, ctx.feature.title, criteria)
    result = run_claude_session(
        prompt, cwd=ctx.repo, tools=["Read"],
        permission_mode="default", include_codex_protocol=False,
        enable_ncdev_hooks=False, timeout=300,
    )
    verdict = extract_json_object(result.final_text or "")
    if not result.success or verdict is None:
        # Can't get a verdict — report not-ok with a clear reason, but
        # the layer treats an unparseable verdict as ERROR (see below).
        return False, "__no_verdict__"
    return bool(verdict.get("ok", False)), str(verdict.get("reason", ""))


def layer_visual(ctx: GauntletContext) -> GauntletLayerResult:
    """L5 — locate required screenshots and vision-review each."""
    start = time.time()
    required = list(ctx.feature.acceptance.required_screenshots)

    if not required:
        return GauntletLayerResult(
            layer="L5-visual", status=LayerStatus.SKIPPED, blocking=False,
            summary="visual: feature declares no required screenshots — skipped",
        )
    if not ctx.run_commands:
        return GauntletLayerResult(
            layer="L5-visual", status=LayerStatus.SKIPPED, blocking=False,
            summary="visual: command execution disabled — skipped",
        )

    missing: list[str] = []
    broken: list[str] = []
    errored: list[str] = []
    reviewed = 0

    for name in required:
        path = _locate_screenshot(ctx.repo, name)
        if path is None:
            missing.append(name)
            continue
        try:
            ok, reason = _review_screenshot(path, ctx)
        except Exception as exc:  # noqa: BLE001
            errored.append(f"{name}: vision review crashed ({exc})")
            continue
        if reason == "__no_verdict__":
            # A malfunctioned review is not a completed review.
            errored.append(f"{name}: no parseable vision verdict")
            continue
        reviewed += 1
        if not ok:
            broken.append(f"{name}: {reason}")

    duration = time.time() - start
    findings = (
        [f"missing screenshot: {m}" for m in missing]
        + [f"broken screen — {b}" for b in broken]
        + errored
    )

    if missing or broken:
        return GauntletLayerResult(
            layer="L5-visual", status=LayerStatus.FAILED, blocking=True,
            summary=(
                f"visual: {len(missing)} missing, {len(broken)} broken "
                f"of {len(required)} required screenshot(s)"
            ),
            detail="\n".join(findings),
            duration_seconds=duration,
            findings=findings,
        )
    if errored and reviewed == 0:
        # Every review malfunctioned — surface as a non-blocking ERROR
        # rather than bricking the build on a vision-tooling problem.
        return GauntletLayerResult(
            layer="L5-visual", status=LayerStatus.ERROR, blocking=False,
            summary="visual: vision review could not produce a verdict",
            detail="\n".join(errored),
            duration_seconds=duration,
            findings=errored,
        )
    return GauntletLayerResult(
        layer="L5-visual", status=LayerStatus.PASSED, blocking=True,
        summary=f"visual: {reviewed} screenshot(s) reviewed, no visual defects",
        duration_seconds=duration,
        findings=errored,  # advisory: partial review errors, if any
    )
