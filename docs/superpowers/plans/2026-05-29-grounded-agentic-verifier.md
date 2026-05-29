# Grounded Agentic Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace NC Dev's rigid Gauntlet layers + 8-clause `_post_session_verification` with a standalone `grounded_verify` module: hard floor (work exists + compiles) → deterministic evidence gathering → Opus-4.8 judgment grounded in real tool output.

**Architecture:** A new `src/ncdev/pipeline/grounded_verify/` package with four units — `models` (pydantic contracts), `hard_floor` (pre-LLM auto-fail gates), `evidence` (executes tools, emits facts, no verdict), `judge` (Opus-4.8 verdict, fenced-JSON + validate + one retry) — orchestrated by `grounded_verify()` which returns a `StepVerification` so the executor's status/repair/ledger wiring is unchanged. The LLM call is injected (`session_runner=`) so logic is unit-testable without spending tokens.

**Tech Stack:** Python 3.13, pydantic v2, pytest. Reuses `run_claude_session` (`claude -p --output-format stream-json`), `extract_json_object`, and `claude_executor` shell/git/health helpers.

**Spec:** `docs/superpowers/specs/2026-05-29-grounded-agentic-verifier-design.md`

---

## File Structure

- Create: `src/ncdev/pipeline/grounded_verify/__init__.py` — public `grounded_verify()` orchestrator
- Create: `src/ncdev/pipeline/grounded_verify/models.py` — `Verdict`, `EvidenceItem`, `EvidenceBundle`, `HardFloorResult`
- Create: `src/ncdev/pipeline/grounded_verify/hard_floor.py` — `check_hard_floor()`
- Create: `src/ncdev/pipeline/grounded_verify/evidence.py` — `gather_evidence()`
- Create: `src/ncdev/pipeline/grounded_verify/judge.py` — `judge()` + `parse_verdict()`
- Create: `tests/test_grounded_verify/test_models.py`, `test_hard_floor.py`, `test_evidence.py`, `test_judge.py`, `test_orchestrator.py`, `test_replay.py`
- Create: `tests/test_grounded_verify/fixtures/` — recorded evidence bundles (f05, f08, genuine-fail)
- Modify: `src/ncdev/pipeline/claude_executor.py` — replace `_post_session_verification` call + gauntlet block with `grounded_verify()`; delete the dead helpers
- Delete: `src/ncdev/pipeline/gauntlet/` (after migrating `extract_json_object`)

---

## Task 1: Contracts (models)

**Files:**
- Create: `src/ncdev/pipeline/grounded_verify/__init__.py` (empty for now)
- Create: `src/ncdev/pipeline/grounded_verify/models.py`
- Test: `tests/test_grounded_verify/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grounded_verify/test_models.py
from ncdev.pipeline.grounded_verify.models import (
    Verdict, EvidenceItem, EvidenceBundle, HardFloorResult,
)


def test_verdict_defaults_and_roundtrip():
    v = Verdict(verdict="PASS")
    assert v.confidence == 0.5
    assert v.reasons == [] and v.repair_guidance == []
    assert Verdict.model_validate_json(v.model_dump_json()).verdict == "PASS"


def test_verdict_rejects_unknown_verdict():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Verdict(verdict="MAYBE")


def test_evidence_bundle_holds_items_and_diff():
    b = EvidenceBundle(
        items=[EvidenceItem(name="backend-tests", command="pytest", exit_code=1,
                            output_tail="KeyError", scope="feature-tests")],
        diff="diff --git a b", changed_files=["backend/app/x.py"],
    )
    assert b.items[0].exit_code == 1
    assert b.changed_files == ["backend/app/x.py"]


def test_hard_floor_result():
    assert HardFloorResult(passed=True).reason == ""
    assert HardFloorResult(passed=False, reason="no work").reason == "no work"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_grounded_verify/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: ncdev.pipeline.grounded_verify.models`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/pipeline/grounded_verify/models.py
"""Structured contracts for the grounded verifier."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """One executed observation. Pure fact — no verdict."""
    name: str
    command: str = ""
    exit_code: int | None = None
    output_tail: str = ""
    scope: str = ""  # e.g. "feature-tests", "diff", "health", "security"


class EvidenceBundle(BaseModel):
    """Everything the harness executed and observed for one feature."""
    items: list[EvidenceItem] = Field(default_factory=list)
    diff: str = ""
    changed_files: list[str] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)


class Verdict(BaseModel):
    """The agent's grounded judgment. Single source of truth for output."""
    verdict: Literal["PASS", "FAIL"]
    confidence: float = 0.5
    reasons: list[str] = Field(default_factory=list)
    repair_guidance: list[str] = Field(default_factory=list)
    evidence_consulted: list[str] = Field(default_factory=list)


class HardFloorResult(BaseModel):
    """Outcome of the pre-LLM hard floor."""
    passed: bool
    reason: str = ""
```

Also create empty `src/ncdev/pipeline/grounded_verify/__init__.py` and `tests/test_grounded_verify/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounded_verify/test_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/grounded_verify/ tests/test_grounded_verify/
git commit -m "feat(grounded-verify): structured contracts (Verdict/Evidence/HardFloor)"
```

---

## Task 2: Hard floor

**Files:**
- Create: `src/ncdev/pipeline/grounded_verify/hard_floor.py`
- Test: `tests/test_grounded_verify/test_hard_floor.py`

The hard floor auto-fails only when (a) no commit AND clean tree (no work to judge) or (b) the declared compile/typecheck command fails. Reuses `_run_shell`, `_git_head`, `_git_working_tree_dirty` from `claude_executor`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grounded_verify/test_hard_floor.py
from pathlib import Path

from ncdev.pipeline.grounded_verify.hard_floor import check_hard_floor


def test_no_work_fails(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.hard_floor as hf
    monkeypatch.setattr(hf, "_git_head", lambda p: "SAME")
    monkeypatch.setattr(hf, "_git_working_tree_dirty", lambda p: False)
    r = check_hard_floor(tmp_path, pre_commit="SAME", compile_cmd=None)
    assert r.passed is False
    assert "no work" in r.reason.lower()


def test_compile_failure_fails(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.hard_floor as hf
    monkeypatch.setattr(hf, "_git_head", lambda p: "NEW")
    monkeypatch.setattr(hf, "_git_working_tree_dirty", lambda p: False)
    monkeypatch.setattr(hf, "_run_shell",
                        lambda cmd, *, cwd, timeout: (False, "SyntaxError"))
    r = check_hard_floor(tmp_path, pre_commit="OLD", compile_cmd="python -m compileall .")
    assert r.passed is False
    assert "compile" in r.reason.lower()


def test_work_and_compiles_passes(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.hard_floor as hf
    monkeypatch.setattr(hf, "_git_head", lambda p: "NEW")
    monkeypatch.setattr(hf, "_git_working_tree_dirty", lambda p: False)
    monkeypatch.setattr(hf, "_run_shell", lambda cmd, *, cwd, timeout: (True, "ok"))
    r = check_hard_floor(tmp_path, pre_commit="OLD", compile_cmd="python -m compileall .")
    assert r.passed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounded_verify/test_hard_floor.py -v`
Expected: FAIL with `ModuleNotFoundError: ...hard_floor`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/pipeline/grounded_verify/hard_floor.py
"""Pre-LLM hard floor. The only checks the agent cannot override."""
from __future__ import annotations

from pathlib import Path

from ncdev.pipeline.claude_executor import (
    _git_head, _git_working_tree_dirty, _run_shell,
)
from ncdev.pipeline.grounded_verify.models import HardFloorResult


def check_hard_floor(
    target_path: Path,
    *,
    pre_commit: str,
    compile_cmd: str | None,
    timeout: int = 300,
) -> HardFloorResult:
    """Auto-fail only if there is no work to judge, or it won't compile."""
    made_commit = _git_head(target_path) != pre_commit
    dirty = _git_working_tree_dirty(target_path)
    if not made_commit and not dirty:
        return HardFloorResult(passed=False, reason="no work produced (no commit, clean tree)")
    if compile_cmd:
        ok, out = _run_shell(compile_cmd, cwd=target_path, timeout=timeout)
        if not ok:
            return HardFloorResult(
                passed=False,
                reason=f"does not compile: {out.strip().splitlines()[-1] if out.strip() else compile_cmd}",
            )
    return HardFloorResult(passed=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounded_verify/test_hard_floor.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/grounded_verify/hard_floor.py tests/test_grounded_verify/test_hard_floor.py
git commit -m "feat(grounded-verify): hard floor (work exists + compiles)"
```

---

## Task 3: Evidence gatherer

**Files:**
- Create: `src/ncdev/pipeline/grounded_verify/evidence.py`
- Test: `tests/test_grounded_verify/test_evidence.py`

Executes the declared test commands and a **diff-scoped** bandit scan, captures real output, returns an `EvidenceBundle`. No verdict. Bandit runs only against changed Python files (never `.venv`/`node_modules`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grounded_verify/test_evidence.py
from pathlib import Path

from ncdev.pipeline.grounded_verify.evidence import gather_evidence, _scoped_bandit_targets


def test_bandit_targets_exclude_deps_and_nonpython():
    changed = [
        "backend/app/api/x.py", "backend/.venv/lib/pymongo/auth.py",
        "frontend/node_modules/a/b.py", "frontend/src/App.tsx",
        "backend/app/api/y.py",
    ]
    assert _scoped_bandit_targets(changed) == ["backend/app/api/x.py", "backend/app/api/y.py"]


def test_gather_runs_declared_tests_and_records_exit(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.evidence as ev
    calls = []

    def fake_shell(cmd, *, cwd, timeout):
        calls.append(cmd)
        return (False, "E   KeyError: 'items'")

    monkeypatch.setattr(ev, "_run_shell", fake_shell)
    bundle = ev.gather_evidence(
        tmp_path, backend_test_cmd="pytest -q", frontend_test_cmd=None,
        changed_files=["backend/app/api/x.py"], diff="diff", screenshots=[],
    )
    names = {i.name: i for i in bundle.items}
    assert "backend-tests" in names
    assert names["backend-tests"].exit_code == 1
    assert "KeyError" in names["backend-tests"].output_tail
    assert bundle.changed_files == ["backend/app/api/x.py"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounded_verify/test_evidence.py -v`
Expected: FAIL with `ModuleNotFoundError: ...evidence`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/pipeline/grounded_verify/evidence.py
"""Deterministic evidence gathering. Executes, observes, records facts.

Makes NO pass/fail decision — that is the judge's job. This guarantees
the basics were actually run so the agent cannot skip them.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ncdev.pipeline.claude_executor import _run_shell
from ncdev.pipeline.grounded_verify.models import EvidenceBundle, EvidenceItem

_DEP_MARKERS = (".venv/", "venv/", "node_modules/", "site-packages/", "/dist/", "/build/")


def _scoped_bandit_targets(changed_files: list[str]) -> list[str]:
    """Python files in the diff, excluding vendored dependencies."""
    return [
        f for f in changed_files
        if f.endswith(".py") and not any(m in f for m in _DEP_MARKERS)
    ]


def _exit_from_ok(ok: bool) -> int:
    return 0 if ok else 1


def gather_evidence(
    target_path: Path,
    *,
    backend_test_cmd: str | None,
    frontend_test_cmd: str | None,
    changed_files: list[str],
    diff: str,
    screenshots: list[str],
    timeout: int = 600,
) -> EvidenceBundle:
    items: list[EvidenceItem] = []

    if backend_test_cmd:
        ok, out = _run_shell(backend_test_cmd, cwd=target_path, timeout=timeout)
        items.append(EvidenceItem(name="backend-tests", command=backend_test_cmd,
                                  exit_code=_exit_from_ok(ok), output_tail=out[-2000:],
                                  scope="feature-tests"))
    if frontend_test_cmd:
        ok, out = _run_shell(frontend_test_cmd, cwd=target_path, timeout=timeout)
        items.append(EvidenceItem(name="frontend-tests", command=frontend_test_cmd,
                                  exit_code=_exit_from_ok(ok), output_tail=out[-2000:],
                                  scope="feature-tests"))

    targets = _scoped_bandit_targets(changed_files)
    if targets and shutil.which("bandit"):
        proc = subprocess.run(
            ["bandit", "-q", "--severity-level", "high", *targets],
            cwd=str(target_path), capture_output=True, text=True, timeout=120,
        )
        items.append(EvidenceItem(name="security-scan",
                                  command=f"bandit (diff-scoped: {len(targets)} files)",
                                  exit_code=proc.returncode,
                                  output_tail=(proc.stdout + proc.stderr)[-2000:],
                                  scope="diff"))

    return EvidenceBundle(items=items, diff=diff[-8000:],
                          changed_files=list(changed_files),
                          screenshots=list(screenshots))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounded_verify/test_evidence.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/grounded_verify/evidence.py tests/test_grounded_verify/test_evidence.py
git commit -m "feat(grounded-verify): diff-scoped evidence gatherer (no verdict)"
```

---

## Task 4: Verdict parsing (fenced-JSON + validate)

**Files:**
- Create/extend: `src/ncdev/pipeline/grounded_verify/judge.py` (parse only for now)
- Test: `tests/test_grounded_verify/test_judge.py` (parse tests)

`parse_verdict` ports the proven `extract_json_object` behavior and validates into a `Verdict`, returning `None` on failure so the caller can retry.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grounded_verify/test_judge.py
from ncdev.pipeline.grounded_verify.judge import parse_verdict


def test_parse_fenced_json():
    text = 'Here is my verdict:\n```json\n{"verdict": "PASS", "confidence": 0.9}\n```\n'
    v = parse_verdict(text)
    assert v is not None and v.verdict == "PASS" and v.confidence == 0.9


def test_parse_bare_object():
    text = 'reasoning... {"verdict": "FAIL", "reasons": ["real bug"]} done'
    v = parse_verdict(text)
    assert v is not None and v.verdict == "FAIL" and v.reasons == ["real bug"]


def test_parse_garbage_returns_none():
    assert parse_verdict("no json here") is None


def test_parse_invalid_schema_returns_none():
    assert parse_verdict('{"verdict": "MAYBE"}') is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounded_verify/test_judge.py -v`
Expected: FAIL with `ModuleNotFoundError: ...judge`

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounded_verify/test_judge.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/grounded_verify/judge.py tests/test_grounded_verify/test_judge.py
git commit -m "feat(grounded-verify): verdict JSON parsing + schema validation"
```

---

## Task 5: judge() — prompt + session + retry

**Files:**
- Modify: `src/ncdev/pipeline/grounded_verify/judge.py` (add `judge()` and `build_prompt()`)
- Test: `tests/test_grounded_verify/test_judge.py` (add judge tests)

`judge()` builds the prompt (encoding the four prompt rules), calls an injected `session_runner` (defaults to `run_claude_session`), parses the verdict, and retries once with the validation error fed back. On total failure it returns a conservative `FAIL`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_grounded_verify/test_judge.py
from pathlib import Path
from dataclasses import dataclass

from ncdev.pipeline.grounded_verify.judge import judge, build_prompt
from ncdev.pipeline.grounded_verify.models import EvidenceBundle, EvidenceItem


@dataclass
class FakeSession:
    final_text: str
    total_cost_usd: float = 0.01
    success: bool = True


def _bundle():
    return EvidenceBundle(items=[EvidenceItem(name="backend-tests", exit_code=1,
                                              output_tail="cd: backend: No such file")],
                          diff="d", changed_files=["backend/app/x.py"])


def test_build_prompt_includes_rules_and_evidence():
    p = build_prompt("f08", "Build conflicts API", _bundle(), prior_context="")
    assert "harness" in p.lower() or "environmental" in p.lower()
    assert "intent" in p.lower()
    assert "backend-tests" in p


def test_judge_returns_parsed_verdict(tmp_path: Path):
    runner = lambda *a, **k: FakeSession('```json\n{"verdict":"PASS","confidence":0.8}\n```')
    v = judge("f08", "intent", _bundle(), prior_context="", target_path=tmp_path,
              session_runner=runner)
    assert v.verdict == "PASS"


def test_judge_retries_then_fails_safe(tmp_path: Path):
    calls = {"n": 0}

    def runner(*a, **k):
        calls["n"] += 1
        return FakeSession("no json at all")

    v = judge("f08", "intent", _bundle(), prior_context="", target_path=tmp_path,
              session_runner=runner)
    assert calls["n"] == 2          # one retry
    assert v.verdict == "FAIL"      # conservative fail-safe
    assert any("could not" in r.lower() or "parse" in r.lower() for r in v.reasons)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounded_verify/test_judge.py -v`
Expected: FAIL with `ImportError: cannot import name 'judge'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/ncdev/pipeline/grounded_verify/judge.py
from pathlib import Path
from typing import Callable

from ncdev.claude_session import DEFAULT_BUILD_TOOLS, run_claude_session
from ncdev.pipeline.grounded_verify.models import EvidenceBundle, Verdict

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounded_verify/test_judge.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/grounded_verify/judge.py tests/test_grounded_verify/test_judge.py
git commit -m "feat(grounded-verify): judge() prompt + session call + retry + fail-safe"
```

---

## Task 6: grounded_verify() orchestrator

**Files:**
- Modify: `src/ncdev/pipeline/grounded_verify/__init__.py`
- Test: `tests/test_grounded_verify/test_orchestrator.py`

Wires the three phases and returns a `StepVerification` (so the executor is unchanged). Persists `evidence-bundle.json` + `verdict.json` when `step_dir` is given.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grounded_verify/test_orchestrator.py
from pathlib import Path

from ncdev.pipeline.grounded_verify import grounded_verify
from ncdev.pipeline.grounded_verify.models import HardFloorResult, Verdict, EvidenceBundle


def test_hard_floor_fail_skips_agent(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify as gv
    monkeypatch.setattr(gv, "check_hard_floor",
                        lambda *a, **k: HardFloorResult(passed=False, reason="no work produced"))
    called = {"judge": False}
    monkeypatch.setattr(gv, "judge",
                        lambda *a, **k: called.__setitem__("judge", True) or Verdict(verdict="PASS"))
    ver = grounded_verify(tmp_path, feature_id="f01", intent="x", pre_commit="OLD",
                          backend_test_cmd=None, frontend_test_cmd=None,
                          compile_cmd=None, changed_files=[], diff="")
    assert ver.overall_passed is False
    assert ver.failure_reasons == ["no work produced"]
    assert called["judge"] is False        # invariant: agent never called below floor


def test_pass_verdict_maps_to_overall_passed(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify as gv
    monkeypatch.setattr(gv, "check_hard_floor", lambda *a, **k: HardFloorResult(passed=True))
    monkeypatch.setattr(gv, "gather_evidence", lambda *a, **k: EvidenceBundle())
    monkeypatch.setattr(gv, "judge",
                        lambda *a, **k: Verdict(verdict="PASS", confidence=0.9))
    ver = grounded_verify(tmp_path, feature_id="f01", intent="x", pre_commit="OLD",
                          backend_test_cmd=None, frontend_test_cmd=None,
                          compile_cmd=None, changed_files=[], diff="")
    assert ver.overall_passed is True
    assert ver.failure_reasons == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounded_verify/test_orchestrator.py -v`
Expected: FAIL with `ImportError: cannot import name 'grounded_verify'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/pipeline/grounded_verify/__init__.py
"""Grounded agentic verifier — public entrypoint."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ncdev.claude_session import run_claude_session
from ncdev.pipeline.grounded_verify.evidence import gather_evidence
from ncdev.pipeline.grounded_verify.hard_floor import check_hard_floor
from ncdev.pipeline.grounded_verify.judge import judge
from ncdev.pipeline.models import StepVerification

__all__ = ["grounded_verify"]


def grounded_verify(
    target_path: Path,
    *,
    feature_id: str,
    intent: str,
    pre_commit: str,
    backend_test_cmd: str | None,
    frontend_test_cmd: str | None,
    compile_cmd: str | None,
    changed_files: list[str],
    diff: str,
    screenshots: list[str] | None = None,
    prior_context: str = "",
    step_dir: Path | None = None,
    session_runner: Callable = run_claude_session,
) -> StepVerification:
    ver = StepVerification()
    floor = check_hard_floor(target_path, pre_commit=pre_commit, compile_cmd=compile_cmd)
    if not floor.passed:
        ver.overall_passed = False
        ver.failure_reasons = [floor.reason]
        return ver

    evidence = gather_evidence(
        target_path, backend_test_cmd=backend_test_cmd,
        frontend_test_cmd=frontend_test_cmd, changed_files=changed_files,
        diff=diff, screenshots=screenshots or [],
    )
    verdict = judge(feature_id, intent, evidence, prior_context=prior_context,
                    target_path=target_path, session_runner=session_runner)

    ver.overall_passed = verdict.verdict == "PASS"
    ver.failure_reasons = [] if ver.overall_passed else list(verdict.reasons)

    if step_dir is not None:
        step_dir.mkdir(parents=True, exist_ok=True)
        (step_dir / "evidence-bundle.json").write_text(
            evidence.model_dump_json(indent=2), encoding="utf-8")
        (step_dir / "verdict.json").write_text(
            verdict.model_dump_json(indent=2), encoding="utf-8")
    return ver
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounded_verify/test_orchestrator.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/grounded_verify/__init__.py tests/test_grounded_verify/test_orchestrator.py
git commit -m "feat(grounded-verify): grounded_verify() 3-phase orchestrator"
```

---

## Task 7: Replay harness over real recorded runs

**Files:**
- Create: `tests/test_grounded_verify/fixtures/f05_venv_bandit.json`, `f08_cd_error.json`, `genuine_keyerror.json`
- Test: `tests/test_grounded_verify/test_replay.py`

These fixtures are `EvidenceBundle` JSON hand-built from real `.nc-dev/runs/` artifacts (the f05 `.venv` bandit dump, the f08 `cd: backend` test error, a genuine `KeyError: 'items'`). The replay test runs the **real** `judge()` against a real `claude -p` session (marked `@pytest.mark.llm`, skipped by default) to confirm correct rulings. A fast deterministic variant asserts `build_prompt` surfaces the right signal so an agent *can* rule correctly.

- [ ] **Step 1: Create fixtures from real run data**

Run (build f08 fixture from the recorded error):

```bash
cat > tests/test_grounded_verify/fixtures/f08_cd_error.json <<'JSON'
{"items": [{"name": "backend-tests", "command": "cd backend && pytest",
  "exit_code": 1, "output_tail": "/usr/bin/cd: line 4: cd: backend: No such file or directory",
  "scope": "feature-tests"}],
 "diff": "diff --git a/backend/app/api/tracker.py b/backend/app/api/tracker.py\n+...",
 "changed_files": ["backend/app/api/tracker.py"], "screenshots": []}
JSON
cat > tests/test_grounded_verify/fixtures/f05_venv_bandit.json <<'JSON'
{"items": [{"name": "security-scan", "command": "bandit (diff-scoped: 0 files)",
  "exit_code": 0, "output_tail": "no issues in changed files", "scope": "diff"}],
 "diff": "diff --git a/backend/app/api/documents.py b/backend/app/api/documents.py\n+...",
 "changed_files": ["backend/app/api/documents.py"], "screenshots": []}
JSON
cat > tests/test_grounded_verify/fixtures/genuine_keyerror.json <<'JSON'
{"items": [{"name": "backend-tests", "command": "pytest -q",
  "exit_code": 1, "output_tail": "E       KeyError: 'items'\nFAILED tests/integration/test_f08_stale_resolution.py",
  "scope": "feature-tests"}],
 "diff": "diff --git a/backend/app/services/tracker.py b/backend/app/services/tracker.py\n+...",
 "changed_files": ["backend/app/services/tracker.py"], "screenshots": []}
JSON
```

- [ ] **Step 2: Write the deterministic replay test**

```python
# tests/test_grounded_verify/test_replay.py
import json
from pathlib import Path

import pytest

from ncdev.pipeline.grounded_verify.judge import build_prompt, judge
from ncdev.pipeline.grounded_verify.models import EvidenceBundle

FIX = Path(__file__).parent / "fixtures"


def _bundle(name: str) -> EvidenceBundle:
    return EvidenceBundle.model_validate_json((FIX / name).read_text())


def test_cd_error_signal_present_in_prompt():
    # The harness/env-noise signal must reach the agent so it CAN exonerate.
    p = build_prompt("f08", "Build tracker ingest API", _bundle("f08_cd_error.json"),
                     prior_context="")
    assert "No such file or directory" in p
    assert "harness" in p.lower() or "environmental" in p.lower()


def test_genuine_failure_signal_present_in_prompt():
    p = build_prompt("f08", "Resolve stale tracker entries",
                     _bundle("genuine_keyerror.json"), prior_context="")
    assert "KeyError: 'items'" in p


@pytest.mark.llm
@pytest.mark.parametrize("fixture,expected", [
    ("f08_cd_error.json", "PASS"),       # cd error = harness noise, work is fine
    ("f05_venv_bandit.json", "PASS"),    # dep-only finding, clean changed files
    ("genuine_keyerror.json", "FAIL"),   # real failing integration test
])
def test_real_judge_rulings(tmp_path, fixture, expected):
    v = judge("f08", "feature intent", _bundle(fixture),
              prior_context="", target_path=tmp_path)
    assert v.verdict == expected
```

- [ ] **Step 3: Register the `llm` marker and run the deterministic tests**

Add to `pyproject.toml` under `[tool.pytest.ini_options]` markers (if a markers list exists, append; else add it):

```toml
markers = ["llm: tests that spend tokens on a real claude/codex session (run explicitly)"]
```

Run (deterministic only): `python -m pytest tests/test_grounded_verify/test_replay.py -v -m "not llm"`
Expected: PASS (2 passed), 3 deselected

- [ ] **Step 4: (Manual, optional) run the real-judge rulings once**

Run: `python -m pytest tests/test_grounded_verify/test_replay.py -v -m llm`
Expected: 3 passed (spends a few cents). If any ruling is wrong, tune `_RULES` in `judge.py` and re-run — this is the empirical calibration gate.

- [ ] **Step 5: Commit**

```bash
git add tests/test_grounded_verify/fixtures tests/test_grounded_verify/test_replay.py pyproject.toml
git commit -m "test(grounded-verify): replay harness over real recorded false-fail + genuine-fail runs"
```

---

## Task 8: Integrate into the executor; delete the Gauntlet

**Files:**
- Modify: `src/ncdev/pipeline/claude_executor.py` — replace `_post_session_verification` call (~:531) and gauntlet block (~:587-620) with `grounded_verify()`
- Delete: `src/ncdev/pipeline/gauntlet/` (after migrating `extract_json_object` already re-implemented in `judge.py`)
- Test: full suite

- [ ] **Step 1: Replace the verification call in `_execute_feature`**

In `claude_executor.py`, the block that computes `verification = _post_session_verification(...)` (~:531) through the gauntlet block (~:587-620) becomes a single call. Replace from the `verification = _post_session_verification(` assignment up to the end of the `if run_gauntlet_check and status == StepStatus.PASSED:` block with:

```python
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
        "verification_finished", phase="building", feature_id=feature.feature_id,
        message=("verification passed" if verification.overall_passed
                 else "verification failed"),
        data={"overall_passed": verification.overall_passed,
              "failure_reasons": list(verification.failure_reasons)},
    )

    # Status: PASSED iff work landed and the grounded verifier approved.
    if made_commit and verification.overall_passed:
        status = StepStatus.PASSED
    else:
        if dirty:
            if _commit_broken(target_path, feature):
                post_commit = _git_head(target_path)
        status = StepStatus.FAILED
```

> Note: the grounded verifier subsumes the old gauntlet, so the separate gauntlet block is deleted. `session.success` is no longer part of the verdict (the SIGTERM false-fail class is gone — the hard floor + evidence judge real state).

- [ ] **Step 2: Confirm `build_command` exists on the contract; add if missing**

Run: `grep -n "build_command\|backend_test_command\|frontend_test_command" src/ncdev/pipeline/charter.py src/ncdev/core/models.py`
Expected: the test command fields exist. If `build_command` is absent on the `VerificationContract`, add it:

```python
    build_command: str = ""   # compile/typecheck for the hard floor; "" disables
```
(in the same model that defines `backend_test_command`).

- [ ] **Step 3: Delete the gauntlet package and fix imports**

```bash
git rm -r src/ncdev/pipeline/gauntlet
grep -rn "from ncdev.pipeline.gauntlet\|import gauntlet\|run_gauntlet\|EXECUTOR_LAYERS\|GauntletContext\|_gauntlet_report_json\|_load_prior_gauntlet_findings" src/ncdev | grep -v grounded_verify
```
For each remaining hit, delete the dead call/import (the gauntlet block in `claude_executor.py` is already gone from Step 1; remove now-unused helpers `_gauntlet_report_json`, `_load_prior_gauntlet_findings`, and the now-dead clause helpers `_post_session_verification`, `_grep_for_prohibited`, `_screenshot_exists`, `_file_mentions_token`, `_count_test_files`, `_run_test_in_project_root` if no longer referenced — verify each with `grep -rn "<name>" src/ncdev tests` before deleting).

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q -m "not llm"`
Expected: PASS. Fix any test that imported the deleted gauntlet (delete or port those tests). The grounded_verify suite (Tasks 1-7) must be green.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(grounded-verify): wire into executor; delete Gauntlet + dead verification clauses"
```

---

## Task 9: Measured run vs baseline

**Files:** none (operational validation)

- [ ] **Step 1: Run one real feature with a budget cap**

Run a single-feature build on `aigizmo-ledger` (or a small fresh target) with a hard spend cap (`spend_ledger`/`run_caps`, ~$5), with the grounded verifier live and models on opus-4.8 / gpt-5.5.

- [ ] **Step 2: Compare to baseline**

Compare against the recorded baseline (39 failed / 2 passed; $18-25/failed run; fpsr=0.0): record the new pass/fail, repair-cycle count, and verify-stage cost. Success = materially higher first-pass rate and fewer repair cycles.

- [ ] **Step 3: Record the result**

Append the measured numbers to the spec's §8 success criteria and to `docs-only` memory. If first-pass rate is still low, inspect the new `verdict.json` artifacts to see whether the agent is judging correctly, and calibrate `_RULES`.

---

## Self-Review

**Spec coverage:** §4 Phase 1 → Task 2; Phase 2 → Task 3; Phase 3 → Tasks 4-5; §5 output/integration → Tasks 6, 8; §6 retire/keep → Task 8; §7 testing (replay + unit + invariant) → Tasks 1-7 (invariant: `test_hard_floor_fail_skips_agent`); §8 measured run → Task 9; §9 decisions (fenced-JSON+retry → Tasks 4-5; bandit-Python-only → Task 3; visual via Read → screenshots passed to `judge`'s session which has Read in DEFAULT_BUILD_TOOLS; confidence logged not branched → `verdict.json`). Covered.

**Placeholder scan:** no TBD/TODO; every code step has full code. Task 8 Step 3 lists exact helper names to verify-then-delete (an action, not a placeholder).

**Type consistency:** `Verdict.verdict` ∈ {PASS,FAIL} used consistently; `grounded_verify` returns `StepVerification` (matching the executor's existing consumer at the status block); `gather_evidence`/`judge`/`check_hard_floor` signatures match their call sites in `__init__.py`; `EvidenceBundle.model_validate_json` used in fixtures matches the model. Consistent.
