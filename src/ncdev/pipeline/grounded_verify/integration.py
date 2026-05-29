# src/ncdev/pipeline/grounded_verify/integration.py
"""Product-level integration gate: prompt builder (Task 2) and gate function (Task 3)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from ncdev.claude_session import run_claude_session
from ncdev.pipeline.grounded_verify.judge import _run_judge
from ncdev.pipeline.grounded_verify.models import EvidenceBundle, EvidenceItem
from ncdev.pipeline.integration_gate import (
    IntegrationResult,
    _derive_base_url,
    _probe,
    _resolve_url,
    _run_shell,
    _tail,
    _wait_for_health,
)
from ncdev.pipeline.models import CharterBundle, StepResult, StepStatus

_PRODUCT_RULES = """\
You are the INTEGRATION VERIFIER for the whole product. Decide whether the product's \
intent is genuinely satisfied end-to-end.

Grounding rules (do not violate):
1. Judge INTENT satisfaction, not exact file paths or layout.
   A required file satisfied at a reasonable alternate path counts.
   A route returning 2xx satisfies its contract regardless of file layout.
2. Distinguish HOW an executable check failed before ruling:
   - If a test suite, build, lint, or required route genuinely failed (assertions fired,
     non-zero exit with real output), that is decisive toward FAIL unless you can evidence
     it as harness/env noise (e.g. missing interpreter, wrong cwd, unstarted service).
   - If the command failed to EXECUTE (shell error, missing file, unstarted service),
     investigate the working tree before ruling. FAIL only if the implementation is absent
     or you confirm it is actually broken.
3. Findings inside dependencies (.venv, node_modules, site-packages) are NEVER the
   product's fault. Ignore them — dependency-only findings never count.
4. Ground every reason in an evidence item or a tool call you make. Never assert an
   outcome you did not observe. You MAY run Bash/Read/Grep to investigate further.

Respond with EXACTLY ONE fenced JSON block matching:
```json
{"verdict": "PASS" | "FAIL", "confidence": 0.0-1.0,
 "reasons": [...], "repair_guidance": [...], "evidence_consulted": [...]}
```"""


def build_integration_prompt(
    product_intent: str,
    evidence: EvidenceBundle,
    completed_feature_ids: list[str],
    *,
    prior_context: str = "",
) -> str:
    """Build a product-level judge prompt from intent, evidence, and completed feature ids.

    Mirrors ``judge.build_prompt`` in structure and closes with the same fenced-JSON
    ``Verdict`` schema block.  Rules here govern whole-product intent satisfaction
    (not exact file paths; alternate paths count; executable failures are decisive;
    dependency-only findings never count).
    """
    lines = [_PRODUCT_RULES, ""]
    lines += [
        "## Product intent",
        product_intent,
        "",
    ]

    if completed_feature_ids:
        lines += [
            "## Completed features (ids)",
            *(f"- {fid}" for fid in completed_feature_ids),
            "",
        ]

    if prior_context:
        lines += ["## Prior attempt", prior_context, ""]

    lines.append("## Gathered evidence (already executed for you)")
    for it in evidence.items:
        lines.append(
            f"- [{it.name}] cmd=`{it.command}` exit={it.exit_code} scope={it.scope}"
        )
        if it.output_tail:
            lines.append(f"  output (tail):\n{it.output_tail}")

    lines += ["", "## Changed files", *(f"- {f}" for f in evidence.changed_files)]

    if evidence.diff:
        lines += ["", "## Diff (truncated)", evidence.diff]

    return "\n".join(lines)


def grounded_integration_gate(
    bundle: CharterBundle,
    target_path: Path,
    completed: list[StepResult],
    *,
    probe_health: bool = True,
    run_test_commands: bool = True,
    session_runner: Callable = run_claude_session,
) -> IntegrationResult:
    """Product-level integration gate with grounded judge verdict.

    Mirrors ``run_integration_gate`` in observability fields populated but
    delegates the final pass/fail decision to an LLM judge (``_run_judge``)
    rather than exact-path clause matching. The judge sees all gathered
    evidence and rules on intent satisfaction.

    Hard floor: if ``start_command`` is set and the app fails to start,
    returns immediately with ``passed=False`` — no judge is called.
    """
    start = time.time()
    result = IntegrationResult()
    evidence_items: list[EvidenceItem] = []

    # ------------------------------------------------------------------ #
    # Step 1: Hard floor — start the app if configured
    # ------------------------------------------------------------------ #
    started_here = False
    if bundle.verification.start_command and run_test_commands:
        ok, out = _run_shell(
            bundle.verification.start_command,
            cwd=target_path,
            timeout=300,
        )
        if not ok:
            result.passed = False
            result.app_started = False
            result.failures = [f"app did not start: {_tail(out)}"]
            result.duration_seconds = time.time() - start
            return result

        result.app_started = True
        started_here = True
        _wait_for_health(
            bundle.verification.backend_health_url,
            timeout=bundle.verification.boot_timeout_seconds,
        )

    # ------------------------------------------------------------------ #
    # Step 2: Gather evidence — routes, tests, lint, build
    # ------------------------------------------------------------------ #
    built_ids = {r.feature_id for r in completed if r.status == StepStatus.PASSED}

    # Route probes for each built feature
    if probe_health:
        base_url = bundle.verification.frontend_url or _derive_base_url(
            bundle.verification.backend_health_url
        )
        for feat in bundle.feature_queue.features:
            if feat.feature_id not in built_ids:
                continue
            for route in feat.acceptance.required_routes:
                full = _resolve_url(route, base_url)
                result.routes_probed += 1
                reachable = bool(full) and _probe(
                    full, timeout=bundle.verification.boot_timeout_seconds
                )
                evidence_items.append(
                    EvidenceItem(
                        name=f"route:{route}",
                        command=f"GET {full or route}",
                        exit_code=0 if reachable else 1,
                        scope="route",
                    )
                )
                if not reachable:
                    result.routes_failed.append(full or route)

    # Test commands
    if run_test_commands:
        _test_cmds = [
            ("backend_test_command", "backend_tests_ok", "backend_test_output_tail", "test"),
            ("frontend_test_command", "frontend_tests_ok", "frontend_test_output_tail", "test"),
            ("e2e_test_command", "e2e_tests_ok", "e2e_test_output_tail", "test"),
            ("lint_command", "lint_ok", "lint_output_tail", "lint"),
            ("build_command", "build_ok", "build_output_tail", "build"),
        ]
        for attr, ok_field, tail_field, scope in _test_cmds:
            cmd = getattr(bundle.verification, attr, "")
            if not cmd:
                continue
            ok, out = _run_shell(cmd, cwd=target_path, timeout=1800)
            setattr(result, ok_field, ok)
            setattr(result, tail_field, _tail(out))
            evidence_items.append(
                EvidenceItem(
                    name=attr.replace("_command", ""),
                    command=cmd,
                    exit_code=0 if ok else 1,
                    output_tail=_tail(out),
                    scope=scope,
                )
            )

    # Teardown — non-failing
    if started_here and bundle.verification.stop_command:
        ok, _out = _run_shell(bundle.verification.stop_command, cwd=target_path, timeout=120)
        result.app_stopped = ok

    # ------------------------------------------------------------------ #
    # Step 3: Judge
    # ------------------------------------------------------------------ #
    # Derive product intent from the bundle: use project_name + feature titles
    feature_titles = [f.title for f in bundle.feature_queue.features]
    product_intent = bundle.contract.project_name
    if feature_titles:
        product_intent = f"{product_intent}: {'; '.join(feature_titles)}"

    evidence_bundle = EvidenceBundle(items=evidence_items)
    verdict = _run_judge(
        build_integration_prompt(product_intent, evidence_bundle, sorted(built_ids)),
        target_path=target_path,
        session_runner=session_runner,
    )

    # ------------------------------------------------------------------ #
    # Step 4: Map verdict → IntegrationResult
    # ------------------------------------------------------------------ #
    result.passed = verdict.verdict == "PASS"
    if not result.passed:
        result.failures = list(verdict.reasons)

    result.duration_seconds = time.time() - start
    return result
