# src/ncdev/pipeline/grounded_verify/judge.py
"""Agent judgment over gathered evidence (Opus 4.8), fenced-JSON + retry."""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from ncdev.pipeline.grounded_verify.models import Verdict

_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE = re.compile(r"\{.*\}", re.DOTALL)


def parse_verdict(text: str) -> Verdict | None:
    """Pull a Verdict out of an LLM response, or None if absent/invalid."""
    m = _FENCED.search(text) or _BARE.search(text)
    if not m:
        return None
    candidate = m.group(1) if m.re is _FENCED else m.group(0)
    try:
        data = json.loads(candidate)
        return Verdict.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        return None


from pathlib import Path
from typing import Callable

from ncdev.claude_session import DEFAULT_BUILD_TOOLS, run_claude_session
from ncdev.pipeline.grounded_verify.models import EvidenceBundle

_RULES = """\
You are the VERIFIER for one feature. Decide whether this feature's slice is genuinely DONE.

Grounding rules (do not violate):
1. A genuinely failing test is decisive toward FAIL — UNLESS you can justify, with
   evidence, that the failure is harness/environmental noise (e.g. a shell `cd` error,
   an unstarted service, an unrelated pre-existing failure). Cite the evidence.
2. Judge INTENT satisfaction, not exact file paths/names. A file at a reasonable
   alternate path satisfies a required-file intent.
3. Findings inside dependencies (.venv, node_modules, site-packages) are NEVER the
   feature's fault. Ignore them.
4. Ground every reason in an evidence item or a tool call you make. Never assert an
   outcome you did not observe. You MAY run bash/read/grep to investigate further.

The hard floor already passed: work exists and the code compiles.

Respond with EXACTLY ONE fenced JSON block matching:
```json
{"verdict": "PASS" | "FAIL", "confidence": 0.0-1.0,
 "reasons": [...], "repair_guidance": [...], "evidence_consulted": [...]}
```"""


def build_prompt(feature_id: str, intent: str, evidence: EvidenceBundle,
                 *, prior_context: str) -> str:
    lines = [_RULES, "", f"## Feature: {feature_id}", f"Intent: {intent}", ""]
    if prior_context:
        lines += ["## Prior attempt", prior_context, ""]
    lines.append("## Gathered evidence (already executed for you)")
    for it in evidence.items:
        lines.append(f"- [{it.name}] cmd=`{it.command}` exit={it.exit_code} scope={it.scope}")
        if it.output_tail:
            lines.append(f"  output (tail):\n{it.output_tail}")
    lines += ["", "## Changed files", *(f"- {f}" for f in evidence.changed_files)]
    if evidence.diff:
        lines += ["", "## Diff (truncated)", evidence.diff]
    return "\n".join(lines)


def judge(
    feature_id: str,
    intent: str,
    evidence: EvidenceBundle,
    *,
    prior_context: str,
    target_path: Path,
    session_runner: Callable = run_claude_session,
    timeout: int = 900,
) -> Verdict:
    prompt = build_prompt(feature_id, intent, evidence, prior_context=prior_context)
    for attempt in range(2):
        result = session_runner(
            prompt, cwd=target_path, tools=DEFAULT_BUILD_TOOLS,
            model="opus", timeout=timeout, permission_mode="acceptEdits",
        )
        verdict = parse_verdict(getattr(result, "final_text", "") or "")
        if verdict is not None:
            return verdict
        prompt = (prompt + "\n\nYour previous response had no valid JSON verdict block. "
                  "Respond with EXACTLY ONE fenced ```json block matching the schema.")
    return Verdict(verdict="FAIL", confidence=0.0,
                   reasons=["verifier could not parse a valid verdict after retry"],
                   repair_guidance=["re-run verification"])
