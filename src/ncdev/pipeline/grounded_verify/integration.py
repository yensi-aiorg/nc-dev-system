# src/ncdev/pipeline/grounded_verify/integration.py
"""Product-level integration gate: prompt builder (Task 2) and gate function (Task 3)."""
from __future__ import annotations

from ncdev.pipeline.grounded_verify.models import EvidenceBundle

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
