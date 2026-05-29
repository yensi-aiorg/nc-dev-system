# src/ncdev/pipeline/grounded_verify/judge.py
"""Agent judgment over gathered evidence (Opus 4.8), fenced-JSON + retry."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from ncdev.claude_session import run_claude_session
from ncdev.pipeline.grounded_verify.models import EvidenceBundle, Verdict

# Read-only toolset — the verifier must not be able to mutate the code it judges.
VERIFIER_TOOLS = ("Read", "Glob", "Grep", "Bash")

_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _iter_brace_blocks(text: str):
    """Yield balanced-brace substrings from *text*, left to right."""
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    yield text[start : i + 1]


def parse_verdict(text: str) -> Verdict | None:
    """Pull a Verdict out of an LLM response, or None if absent/invalid.

    Strategy:
    1. Try every ```json fenced block first (in order).
    2. Then try every balanced-brace substring (in order).
    Return the first candidate that parses as a valid Verdict.
    """
    candidates: list[str] = []

    # (a) fenced blocks
    for m in _FENCED.finditer(text):
        candidates.append(m.group(1))

    # (b) balanced-brace substrings
    for block in _iter_brace_blocks(text):
        candidates.append(block)

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            return Verdict.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            continue

    return None


_RULES = """\
You are the VERIFIER for one feature. Decide whether this feature's slice is genuinely DONE.

Grounding rules (do not violate):
1. Distinguish HOW a test command failed before ruling:
   - If the test command FAILED TO EXECUTE — a shell/env/cwd error such as
     "No such file or directory", a missing interpreter, or an unstarted service —
     that is harness noise about the COMMAND, not proof the code is wrong. You MUST
     investigate the working tree (read the changed files, locate the implementation,
     re-run the tests from the correct directory) before ruling. FAIL only if the
     implementation is absent or you confirm it is actually broken.
   - If the tests RAN and assertions failed (real assertion output — AssertionError,
     KeyError, a wrong status code, etc.) that is decisive toward FAIL, unless you can
     evidence it as an unrelated pre-existing or dependency-only failure.
   Always cite the evidence and any tool calls you made.
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
            prompt, cwd=target_path, tools=VERIFIER_TOOLS,
            model="opus", timeout=timeout, permission_mode="default",
        )
        verdict = parse_verdict(getattr(result, "final_text", "") or "")
        if verdict is not None:
            return verdict
        prompt = (prompt + "\n\nYour previous response had no valid JSON verdict block. "
                  "Respond with EXACTLY ONE fenced ```json block matching the schema.")
    return Verdict(verdict="FAIL", confidence=0.0,
                   reasons=["verifier could not parse a valid verdict after retry"],
                   repair_guidance=["re-run verification"])
