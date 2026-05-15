# NC Dev Factory Loop — First-Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn NC Dev from an open-loop "build once, hope it's done" sprint engine into a closed-loop autonomous factory that probes, judges, and replans until the product is complete — without human input in the inner loop.

**Architecture:**
- Add a new `ncdev factory` command that owns a `build → probe → judge → decide → repeat` state machine, replacing the current "must build perfectly first, then maybe iterate" gating.
- Add a `ProductSteward` session that holds whole-product UX coherence in its head and emits a `Disposition` (continue / repair / replan / stop) at coherence checkpoints.
- Replace `must_mention_feature_id` string-marker policing with engine-recorded **provenance** (what each session actually touched) — the engine already has this signal via `_diff_since`, we just stop demanding string markers from the model.

**Tech Stack:** Python 3.11+, pydantic, pytest. Reuses existing `run_ai_session`, `run_pipeline`, `QualityGateOrchestrator`. No new external deps.

**Out of scope for this slice (deliberately deferred):**
- ProductDebt model (Move #2) — Steward emits dispositions, downstream debt model can layer on later.
- Capability matrix routing (Move #4) — config-driven router. We keep the static modes for now.
- TestCraftr inter-slice probing — Steward calls the *existing* `QualityGateOrchestrator` only at end-of-slice and end-of-run; mid-feature probing is a later slice.

---

## Self-Review checklist applied at end

- [x] Each task touches a named file path
- [x] Each TDD step has a real test, not "write tests"
- [x] No "TBD" / "fill in details" / "similar to Task N"
- [x] Type names consistent across tasks (`Disposition`, `StewardDecision`, `FactoryState`)
- [x] Every spec requirement from the architecture review maps to a task

---

## File Structure

**Create:**
- `src/ncdev/pipeline/provenance.py` — engine-side feature→artifact tracking. Replaces the model's job of writing `must_mention_feature_id` markers.
- `src/ncdev/pipeline/product_steward.py` — `Disposition` enum, `StewardDecision` model, `run_product_steward()` Claude session.
- `src/ncdev/factory.py` — outer factory loop (`run_factory()`).
- `tests/unit/test_provenance.py`
- `tests/unit/test_product_steward.py`
- `tests/unit/test_factory.py`
- `tests/integration/test_factory_loop.py`

**Modify:**
- `src/ncdev/pipeline/models.py` — soften `FeatureAcceptance.must_mention_feature_id` default to `False`; add `ProvenanceRecord` model.
- `src/ncdev/pipeline/claude_executor.py` — when `must_mention_feature_id` is True, emit a warning instead of a hard failure; consult provenance for the same evidence.
- `src/ncdev/pipeline/engine.py` — persist provenance records to `run_dir/provenance.json` as features complete; expose `run_pipeline_slice()` for the factory to drive one slice at a time.
- `src/ncdev/cli.py` — add `factory` subcommand.
- `prompts/protocols/codex-via-bash.md` — reframe the 5-section shape from "MUST follow" to "a useful default shape; deviate if you have a better one."

**Do NOT touch in this slice:**
- `src/ncdev/pipeline/charter.py` (charter mutation comes in the next slice)
- `src/ncdev/quality_gate/*` (we wrap, don't rewrite)

---

## Task 1: Provenance model + storage

**Files:**
- Modify: `src/ncdev/pipeline/models.py` — add `ProvenanceRecord`.
- Create: `src/ncdev/pipeline/provenance.py` — load/save/query helpers.
- Test: `tests/unit/test_provenance.py`

- [ ] **Step 1.1: Write the failing test**

```python
# tests/unit/test_provenance.py
from pathlib import Path

from ncdev.pipeline.models import ProvenanceRecord
from ncdev.pipeline.provenance import (
    append_provenance,
    load_provenance,
    files_for_feature,
)


def test_append_and_load_roundtrip(tmp_path: Path) -> None:
    rec = ProvenanceRecord(
        feature_id="f02-auth",
        commit_sha="abcdef1234567890",
        files_created=["backend/app/auth.py"],
        files_modified=["backend/app/main.py"],
    )
    append_provenance(tmp_path, rec)
    loaded = load_provenance(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].feature_id == "f02-auth"
    assert "backend/app/auth.py" in loaded[0].files_created


def test_files_for_feature_returns_union(tmp_path: Path) -> None:
    append_provenance(tmp_path, ProvenanceRecord(
        feature_id="f02-auth",
        commit_sha="aaa",
        files_created=["a.py"],
        files_modified=["b.py"],
    ))
    append_provenance(tmp_path, ProvenanceRecord(
        feature_id="f02-auth",
        commit_sha="bbb",
        files_created=["c.py"],
        files_modified=[],
    ))
    assert files_for_feature(tmp_path, "f02-auth") == {"a.py", "b.py", "c.py"}


def test_files_for_feature_unknown_returns_empty(tmp_path: Path) -> None:
    assert files_for_feature(tmp_path, "f99-nope") == set()
```

- [ ] **Step 1.2: Run the test and verify it fails**

```bash
pytest tests/unit/test_provenance.py -v
```
Expected: `ImportError` or `AttributeError: module 'ncdev.pipeline.models' has no attribute 'ProvenanceRecord'`.

- [ ] **Step 1.3: Add the model**

Add to `src/ncdev/pipeline/models.py` after the `FeatureStep` class:

```python
class ProvenanceRecord(BaseModel):
    """What a single feature session actually touched in the repo.

    Replaces the policy of demanding the model write
    ``# Feature: fNN-...`` headers in every file. The engine knows what
    each session touched (via ``git diff``), so we record that as
    authoritative provenance — no string markers required.
    """

    feature_id: str
    commit_sha: str
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
```

- [ ] **Step 1.4: Implement helpers**

Create `src/ncdev/pipeline/provenance.py`:

```python
"""Engine-side feature provenance.

Records which files each feature session touched, persisted as
``<run_dir>/provenance.jsonl``. Downstream verifiers and the Steward
query this instead of demanding string markers in the source files.
"""
from __future__ import annotations

import json
from pathlib import Path

from ncdev.pipeline.models import ProvenanceRecord

_FILENAME = "provenance.jsonl"


def append_provenance(run_dir: Path, record: ProvenanceRecord) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / _FILENAME
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def load_provenance(run_dir: Path) -> list[ProvenanceRecord]:
    path = run_dir / _FILENAME
    if not path.exists():
        return []
    out: list[ProvenanceRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(ProvenanceRecord.model_validate_json(line))
    return out


def files_for_feature(run_dir: Path, feature_id: str) -> set[str]:
    """Return the union of all files touched by any session for this feature."""
    files: set[str] = set()
    for rec in load_provenance(run_dir):
        if rec.feature_id != feature_id:
            continue
        files.update(rec.files_created)
        files.update(rec.files_modified)
    return files
```

- [ ] **Step 1.5: Run the test and verify it passes**

```bash
pytest tests/unit/test_provenance.py -v
```
Expected: 3 passed.

- [ ] **Step 1.6: Commit**

```bash
git add src/ncdev/pipeline/models.py src/ncdev/pipeline/provenance.py tests/unit/test_provenance.py
git commit -m "feat(provenance): engine-recorded feature→file map (replaces marker policing)"
```

---

## Task 2: Engine writes provenance per feature

**Files:**
- Modify: `src/ncdev/pipeline/engine.py` (in the Phase 5 loop, after each `result = execute_feature_claude_driven(...)`).
- Test: extend `tests/unit/test_provenance.py` with an engine-integration test using a stubbed executor.

- [ ] **Step 2.1: Write the failing test**

Add to `tests/unit/test_provenance.py`:

```python
from unittest.mock import patch

from ncdev.pipeline.models import (
    CharterBundle,
    FeatureQueueDoc,
    FeatureStep,
    StepResult,
    StepStatus,
    TargetProjectContract,
    VerificationContract,
)


def test_engine_appends_provenance_after_each_feature(tmp_path, monkeypatch):
    """run_pipeline should write a provenance record per executed feature."""
    from ncdev.pipeline import engine as engine_mod

    bundle = CharterBundle(
        contract=TargetProjectContract(
            project_name="p", project_type="library",
            language="python", database="none", auth="none",
            ports={}, design_archetype="Developer Brutalism",
            design_system_source="claude_generated", uses_citex=False,
            is_brownfield=False, existing_repo_path="",
        ),
        verification=VerificationContract(
            backend_test_command="true",
            frontend_test_command="",
            required_files=[],
            required_screenshots=[],
            prohibited_patterns=[],
            backend_health_url="",
            start_command="",
            stop_command="",
            minimum_test_count=0,
            assets_manifest_required=False,
        ),
        feature_queue=FeatureQueueDoc(
            project_name="p",
            features=[FeatureStep(
                feature_id="f01-test", title="t", description="d",
                acceptance_criteria=[], priority=1,
            )],
        ),
    )

    def fake_generate_charter(**kwargs):
        from ncdev.claude_session import ClaudeSessionResult
        return bundle, ClaudeSessionResult(success=True)

    def fake_execute(feature, target_path, run_dir, **kwargs):
        return StepResult(
            feature_id=feature.feature_id,
            status=StepStatus.PASSED,
            commit_sha="aaa",
            files_created=["src/x.py"],
            files_modified=["src/y.py"],
            build_duration_seconds=1.0,
        )

    monkeypatch.setattr(engine_mod, "generate_charter", fake_generate_charter)
    monkeypatch.setattr(engine_mod, "execute_feature_claude_driven", fake_execute)
    monkeypatch.setattr(engine_mod, "run_design_phase",
                        lambda **kw: type("D", (), {"skipped": True, "hard_failed": False, "design_doc": None})())

    workspace = tmp_path / "ws"
    workspace.mkdir()
    source = workspace / "prd.md"
    source.write_text("# fake prd")

    state = engine_mod.run_pipeline(
        workspace=workspace,
        source_path=source,
        target_repo_path=workspace,
        skip_integration_gate=True,
    )

    from ncdev.pipeline.provenance import files_for_feature
    recorded = files_for_feature(Path(state.run_dir), "f01-test")
    assert recorded == {"src/x.py", "src/y.py"}
```

- [ ] **Step 2.2: Run the test and verify it fails**

```bash
pytest tests/unit/test_provenance.py::test_engine_appends_provenance_after_each_feature -v
```
Expected: `AssertionError: recorded == set()` (or similar) — engine doesn't write provenance yet.

- [ ] **Step 2.3: Wire provenance writes into the engine**

In `src/ncdev/pipeline/engine.py`, add at the top:

```python
from ncdev.pipeline.models import ProvenanceRecord
from ncdev.pipeline.provenance import append_provenance
```

Inside the Phase 5 loop, immediately after the existing
`completed.append(result)` line (around line 260 in current main):

```python
            # Persist provenance — what this feature session actually
            # touched. Replaces marker-policing as the source of truth
            # for feature→artifact mapping.
            append_provenance(run_dir, ProvenanceRecord(
                feature_id=result.feature_id,
                commit_sha=result.commit_sha,
                files_created=list(result.files_created),
                files_modified=list(result.files_modified),
                duration_seconds=result.build_duration_seconds or 0.0,
            ))
```

- [ ] **Step 2.4: Run the test and verify it passes**

```bash
pytest tests/unit/test_provenance.py -v
```
Expected: 4 passed.

- [ ] **Step 2.5: Commit**

```bash
git add src/ncdev/pipeline/engine.py tests/unit/test_provenance.py
git commit -m "feat(engine): persist feature provenance to run_dir/provenance.jsonl"
```

---

## Task 3: Soften must_mention_feature_id (warning, not failure)

**Files:**
- Modify: `src/ncdev/pipeline/models.py` (`FeatureAcceptance.must_mention_feature_id` default → `False`).
- Modify: `src/ncdev/pipeline/claude_executor.py` (`_post_session_verification` — when violated, append to a new `warnings` list instead of `failure_reasons`).
- Modify: `src/ncdev/pipeline/state_scanner.py` (`_required_tests_pass` — skip the mention check when `must_mention_feature_id` is False).
- Test: `tests/unit/test_claude_executor.py` — add a test that verifies a missing-marker file no longer fails.

- [ ] **Step 3.1: Write the failing test**

Add to `tests/unit/test_claude_executor.py`:

```python
def test_must_mention_default_false_does_not_fail(tmp_path):
    """A feature with the default acceptance should not fail merely
    because its required_files don't mention the feature_id."""
    from ncdev.pipeline.claude_executor import _post_session_verification
    from ncdev.pipeline.models import (
        CharterBundle, FeatureStep, FeatureQueueDoc, FeatureAcceptance,
        TargetProjectContract, VerificationContract,
    )
    import subprocess

    # Set up a minimal git repo so verification helpers don't crash
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-m", "init"],
                   cwd=tmp_path, check=True)
    (tmp_path / "src.py").write_text("print('hello')\n")   # NO feature marker

    feature = FeatureStep(
        feature_id="f99-thing",
        title="t",
        description="d",
        acceptance_criteria=[],
        acceptance=FeatureAcceptance(required_files=["src.py"]),
    )
    bundle = CharterBundle(
        contract=TargetProjectContract(
            project_name="p", project_type="library",
            language="python", database="none", auth="none",
            ports={}, design_archetype="Developer Brutalism",
            design_system_source="claude_generated", uses_citex=False,
            is_brownfield=False, existing_repo_path="",
        ),
        verification=VerificationContract(
            backend_test_command="",
            frontend_test_command="",
            required_files=[],
            backend_health_url="",
            start_command="",
            assets_manifest_required=False,
            minimum_test_count=0,
        ),
        feature_queue=FeatureQueueDoc(project_name="p", features=[feature]),
    )

    ver = _post_session_verification(
        tmp_path, feature, bundle,
        run_test_commands=False, probe_health=False,
    )
    # File exists, default is False → no marker requirement → must pass.
    assert ver.overall_passed, f"unexpected failures: {ver.failure_reasons}"
```

- [ ] **Step 3.2: Run the test and verify it fails**

```bash
pytest tests/unit/test_claude_executor.py::test_must_mention_default_false_does_not_fail -v
```
Expected: FAIL — current default is True, missing marker triggers a failure reason.

- [ ] **Step 3.3: Change the default**

In `src/ncdev/pipeline/models.py`, change the `must_mention_feature_id` Field:

```python
    must_mention_feature_id: bool = Field(
        default=False,
        description=(
            "Legacy strict mode. When True, required_files and "
            "required_tests must reference the feature_id literally "
            "(in path or in content). Default False — engine-recorded "
            "provenance (see ncdev.pipeline.provenance) is now the "
            "source of truth for feature→artifact mapping. Set True "
            "only when working with a model that cannot reliably "
            "manage its own provenance and you want belt-and-braces "
            "checks. Charters generated by the planner default this "
            "to False."
        ),
    )
```

- [ ] **Step 3.4: Update the charter prompt to match**

In `src/ncdev/pipeline/charter.py`, in `_feature_queue_schema_excerpt()`, change the `must_mention_feature_id` line:

```python
  must_mention_feature_id: bool      # default False — leave False unless
                                      #   the model has trouble managing
                                      #   provenance on its own (engine
                                      #   records what each session touched
                                      #   in provenance.jsonl)
```

And in the rules block:

```python
- `must_mention_feature_id`: keep `false` (the default). The engine
  records feature→file provenance automatically. Set `true` only as a
  belt-and-braces check for unreliable models.
```

- [ ] **Step 3.5: Run the test and verify it passes**

```bash
pytest tests/unit/test_claude_executor.py::test_must_mention_default_false_does_not_fail tests/unit/test_provenance.py -v
```
Expected: all green.

- [ ] **Step 3.6: Run the full unit suite for regressions**

```bash
pytest tests/unit -q
```
Expected: all green. **If anything fails, fix tests that assumed `must_mention_feature_id=True` as the default — they should now explicitly set it to True in their fixtures.**

- [ ] **Step 3.7: Commit**

```bash
git add src/ncdev/pipeline/models.py src/ncdev/pipeline/charter.py tests/unit/test_claude_executor.py
git commit -m "feat(verify): default must_mention_feature_id to False; provenance is SSOT"
```

---

## Task 4: Demote codex-via-bash from "MUST follow" to "useful default shape"

**Files:**
- Modify: `prompts/protocols/codex-via-bash.md` — rephrase the prescriptive shape.
- Modify: `src/ncdev/pipeline/claude_executor.py` — `build_feature_prompt` Step 7 should no longer demand marker tagging.

- [ ] **Step 4.1: Edit the protocol**

In `prompts/protocols/codex-via-bash.md`, replace the "Prompt shape for Codex (follow this)" section:

```markdown
## Prompt shape for Codex (a useful default)

Codex performs best with concrete, scoped tasks. The shape below is
a default that works — feel free to deviate if your task has a better
fit. The *content* matters: a one-line task statement, enough context
to disambiguate, a verification command that returns 0 on success.

```
# Task
<one-line description>

# Context
<2-3 lines on the surrounding code / feature / current state>

# Requirements
- <bullet 1>
- <bullet 2>

# Files
- Read: <path1>, <path2>
- Create: <path3>
- Modify: <path4>

# Verification
<exact command(s) that must pass when you're done>
```

If your task doesn't fit this shape (e.g. a one-shot mechanical
refactor, a code-review hand-off), use whatever shape best
communicates the goal. The orchestrator does not parse the prompt.
```

- [ ] **Step 4.2: Edit the feature prompt**

In `src/ncdev/pipeline/claude_executor.py`, in `build_feature_prompt`, replace Step 7 with:

```python
"""7. **The engine records what your session touched** automatically — you
   do not need to add `# Feature: <id>` markers to every file. (You may
   add them if it helps readability, but they are not required for the
   verifier.)
"""
```

And in the `## What failure looks like (avoid)` section, remove the
"required_file that exists but doesn't mention `{feature.feature_id}`"
bullet (it is no longer a failure mode in the default config).

- [ ] **Step 4.3: Run tests**

```bash
pytest tests/unit -q
```
Expected: all green (this change is prose-only in the prompt builder; no test depends on it).

- [ ] **Step 4.4: Commit**

```bash
git add prompts/protocols/codex-via-bash.md src/ncdev/pipeline/claude_executor.py
git commit -m "refactor(prompts): demote codex 5-section shape from MUST to default"
```

---

## Task 5: Disposition + StewardDecision models

**Files:**
- Create: `src/ncdev/pipeline/product_steward.py`
- Test: `tests/unit/test_product_steward.py`

- [ ] **Step 5.1: Write the failing test**

```python
# tests/unit/test_product_steward.py
import json

from ncdev.pipeline.product_steward import (
    Disposition,
    StewardDecision,
    parse_steward_response,
)


def test_disposition_enum_values():
    assert Disposition.CONTINUE.value == "continue"
    assert Disposition.REPAIR_CURRENT_SLICE.value == "repair_current_slice"
    assert Disposition.INSERT_FEATURES.value == "insert_features"
    assert Disposition.REWRITE_ACCEPTANCE.value == "rewrite_acceptance"
    assert Disposition.RERUN_CHARTER.value == "rerun_charter"
    assert Disposition.STOP_AS_UNRECOVERABLE.value == "stop_as_unrecoverable"


def test_parse_steward_response_happy_path():
    payload = json.dumps({
        "disposition": "repair_current_slice",
        "reasoning": "f02-auth left the dashboard route 500ing",
        "target_feature_ids": ["f02-auth"],
        "new_features": [],
        "amendments": [],
    })
    decision = parse_steward_response(payload)
    assert decision.disposition == Disposition.REPAIR_CURRENT_SLICE
    assert decision.target_feature_ids == ["f02-auth"]


def test_parse_steward_response_strips_markdown_fences():
    payload = "```json\n" + json.dumps({
        "disposition": "continue",
        "reasoning": "looking good",
    }) + "\n```"
    decision = parse_steward_response(payload)
    assert decision.disposition == Disposition.CONTINUE


def test_parse_steward_response_invalid_disposition_raises():
    import pytest
    with pytest.raises(ValueError):
        parse_steward_response(json.dumps({
            "disposition": "yolo",
            "reasoning": "n/a",
        }))
```

- [ ] **Step 5.2: Run the test and verify it fails**

```bash
pytest tests/unit/test_product_steward.py -v
```
Expected: `ModuleNotFoundError: No module named 'ncdev.pipeline.product_steward'`.

- [ ] **Step 5.3: Create the module**

```python
# src/ncdev/pipeline/product_steward.py
"""Product Steward — the whole-product UX coherence agent.

Runs at coherence checkpoints (end-of-slice, end-of-run, on feature
failure) and decides what the factory should do next: continue,
repair, replan, or stop.

This is the role that holds the entire feature queue + current repo
state + TestCraftr findings in one head and asks "is this product
done from a user's perspective." It is deliberately a single Claude
session (not a pipeline phase) so stronger reasoning models improve
it directly.
"""
from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import DEFAULT_PLAN_TOOLS, ClaudeSessionResult
from ncdev.core.config import NCDevConfig
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureStep,
    StepResult,
)


class Disposition(str, Enum):
    """What the Steward decided the factory should do next."""

    CONTINUE = "continue"
    REPAIR_CURRENT_SLICE = "repair_current_slice"
    INSERT_FEATURES = "insert_features"
    REWRITE_ACCEPTANCE = "rewrite_acceptance"
    RERUN_CHARTER = "rerun_charter"
    STOP_AS_UNRECOVERABLE = "stop_as_unrecoverable"


class FeatureAmendment(BaseModel):
    feature_id: str
    field: str            # e.g. "acceptance.required_files"
    new_value: Any
    reason: str


class StewardDecision(BaseModel):
    disposition: Disposition
    reasoning: str
    target_feature_ids: list[str] = Field(default_factory=list)
    new_features: list[FeatureStep] = Field(default_factory=list)
    amendments: list[FeatureAmendment] = Field(default_factory=list)


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_steward_response(text: str) -> StewardDecision:
    """Parse the Steward's JSON response. Tolerates markdown fences."""
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    data = json.loads(cleaned)
    return StewardDecision.model_validate(data)
```

- [ ] **Step 5.4: Run the test and verify it passes**

```bash
pytest tests/unit/test_product_steward.py -v
```
Expected: 4 passed.

- [ ] **Step 5.5: Commit**

```bash
git add src/ncdev/pipeline/product_steward.py tests/unit/test_product_steward.py
git commit -m "feat(steward): Disposition + StewardDecision models with response parser"
```

---

## Task 6: Steward session — prompt builder + runner

**Files:**
- Modify: `src/ncdev/pipeline/product_steward.py` — add `build_steward_prompt`, `run_product_steward`.
- Test: `tests/unit/test_product_steward.py` — prompt-shape tests + runner with mocked session.

- [ ] **Step 6.1: Write the failing tests**

Append to `tests/unit/test_product_steward.py`:

```python
def _bundle():
    from ncdev.pipeline.models import (
        CharterBundle, FeatureQueueDoc, FeatureStep,
        TargetProjectContract, VerificationContract,
    )
    return CharterBundle(
        contract=TargetProjectContract(
            project_name="salon", project_type="web",
            language="python", database="postgres", auth="keycloak",
            ports={"frontend": 23000}, design_archetype="Warm Playfulness",
            design_system_source="claude_generated", uses_citex=False,
            is_brownfield=False, existing_repo_path="",
        ),
        verification=VerificationContract(
            backend_test_command="pytest", frontend_test_command="npm test",
            backend_health_url="http://localhost:23001/health",
            start_command="docker compose up -d",
            stop_command="docker compose down",
        ),
        feature_queue=FeatureQueueDoc(
            project_name="salon",
            features=[
                FeatureStep(feature_id="f01-scaffold", title="Scaffold",
                            description="boot", acceptance_criteria=[]),
                FeatureStep(feature_id="f02-auth", title="Auth",
                            description="login", acceptance_criteria=[]),
            ],
        ),
    )


def test_prompt_includes_prd_and_failed_feature(tmp_path):
    from ncdev.pipeline.product_steward import build_steward_prompt
    from ncdev.pipeline.models import StepResult, StepStatus

    prd = tmp_path / "prd.md"
    prd.write_text("# Salon PRD\nUsers should manage appointments.")
    prompt = build_steward_prompt(
        prd_path=prd,
        bundle=_bundle(),
        completed=[StepResult(
            feature_id="f01-scaffold", status=StepStatus.PASSED,
            commit_sha="aaa",
        ), StepResult(
            feature_id="f02-auth", status=StepStatus.FAILED,
            error_message="login route returned 500",
        )],
        target_path=tmp_path,
        last_test_craftr_scores=None,
    )
    assert "Salon PRD" in prompt
    assert "f02-auth" in prompt
    assert "FAILED" in prompt
    # The prompt must list the allowed dispositions verbatim
    for v in ("continue", "repair_current_slice", "stop_as_unrecoverable"):
        assert v in prompt


def test_run_product_steward_returns_decision(monkeypatch, tmp_path):
    from ncdev.pipeline import product_steward as ps

    fake_response = '{"disposition": "continue", "reasoning": "all green"}'

    def fake_session(prompt, **kwargs):
        return ClaudeSessionResult(success=True, final_text=fake_response)

    monkeypatch.setattr(ps, "run_ai_session", fake_session)
    prd = tmp_path / "prd.md"
    prd.write_text("# fake")

    decision = ps.run_product_steward(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        run_dir=tmp_path / ".run",
        config=None,
    )
    assert decision.disposition == Disposition.CONTINUE


def test_run_product_steward_falls_back_to_stop_on_invalid_response(monkeypatch, tmp_path):
    from ncdev.pipeline import product_steward as ps

    def fake_session(prompt, **kwargs):
        return ClaudeSessionResult(success=True, final_text="not json")

    monkeypatch.setattr(ps, "run_ai_session", fake_session)
    prd = tmp_path / "prd.md"
    prd.write_text("# fake")

    decision = ps.run_product_steward(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        run_dir=tmp_path / ".run",
        config=None,
    )
    # A malformed Steward response is itself unrecoverable input — we
    # must not silently CONTINUE, that's the silent-skip failure mode.
    assert decision.disposition == Disposition.STOP_AS_UNRECOVERABLE
```

Need to import ClaudeSessionResult at top of test file:

```python
from ncdev.claude_session import ClaudeSessionResult
```

- [ ] **Step 6.2: Run the tests and verify they fail**

```bash
pytest tests/unit/test_product_steward.py -v
```
Expected: 3 NEW failures (the existing 4 still pass).

- [ ] **Step 6.3: Implement the prompt builder + runner**

Append to `src/ncdev/pipeline/product_steward.py`:

```python
def _summarise_completed(completed: list[StepResult]) -> str:
    if not completed:
        return "(no features executed yet)"
    lines = []
    for r in completed:
        files = len(r.files_created) + len(r.files_modified)
        lines.append(
            f"  - {r.feature_id}: {r.status.value} "
            f"({files} files, commit {r.commit_sha[:8] or '(none)'})"
            + (f" — {r.error_message[:120]}" if r.error_message else "")
        )
    return "\n".join(lines)


def build_steward_prompt(
    *,
    prd_path: Path,
    bundle: CharterBundle,
    completed: list[StepResult],
    target_path: Path,
    last_test_craftr_scores: dict | None = None,
) -> str:
    prd_excerpt = prd_path.read_text(encoding="utf-8")[:8000]
    queue_summary = "\n".join(
        f"  - {f.feature_id}: {f.title}"
        for f in bundle.feature_queue.features
    )
    tc_block = (
        "(no TestCraftr probe yet)"
        if last_test_craftr_scores is None
        else json.dumps(last_test_craftr_scores, indent=2)
    )
    return f"""# Product Steward — judgment session

You are the Product Steward. Your job is to look at the *whole product*
— the PRD, the planned feature queue, what's already been built, the
running app's behaviour — and decide what the factory should do next.

You are NOT writing code. You are NOT verifying individual features
(that's already done). You are answering: **"is this product going to
be a working, coherent thing a user can actually use end-to-end, and
if not, what's the cheapest next move?"**

## Inputs

### PRD (truncated to 8000 chars)
```
{prd_excerpt}
```

### Charter — Project contract
- project_type: {bundle.contract.project_type}
- archetype: {bundle.contract.design_archetype}
- stack: {bundle.contract.language} + {bundle.contract.database}

### Planned feature queue
{queue_summary}

### Completed so far
{_summarise_completed(completed)}

### Current repo
- target_path: {target_path}
- (you may use the Read/Glob tools to inspect specific files if needed)

### Last TestCraftr probe
```json
{tc_block}
```

## Your decision

Reply with a SINGLE JSON object (no prose around it). Schema:

```json
{{
  "disposition": "<one of: continue | repair_current_slice | insert_features | rewrite_acceptance | rerun_charter | stop_as_unrecoverable>",
  "reasoning": "<2-4 sentences explaining your call>",
  "target_feature_ids": ["<feature_ids the action applies to>"],
  "new_features": [<full FeatureStep objects if disposition=insert_features>],
  "amendments": [{{"feature_id": "...", "field": "...", "new_value": ..., "reason": "..."}}]
}}
```

### Disposition meanings

- `continue` — current slice is in good shape; build the next feature(s).
- `repair_current_slice` — last slice has a fixable problem; re-run the
  feature(s) listed in `target_feature_ids` with the issue noted in
  `reasoning`. Use for: feature claimed PASSED but routes don't actually
  work, dead UI controls, broken inter-feature integration.
- `insert_features` — the PRD implies a feature the planner missed.
  Provide full FeatureStep objects in `new_features`.
- `rewrite_acceptance` — the planned acceptance criteria for a feature
  are wrong (over- or under-specified). Provide amendments.
- `rerun_charter` — the charter is so off that the cheapest path is a
  fresh planning pass. Use sparingly.
- `stop_as_unrecoverable` — the product can't be completed within budget
  / capability. Explain why.

### Examples of judgement calls you should make

- "f02-auth PASSED but the /dashboard route 404s in the integration
  gate — repair, don't continue" → `repair_current_slice`
- "PRD says 'manage appointments' but no feature handles cancellation
  flows — insert" → `insert_features`
- "Every feature PASSED, integration gate is clean, TestCraftr scored
  all axes above threshold" → `continue` (which at end-of-run means
  "we're done")
- "Three repair attempts on f01 have all failed for the same reason and
  the underlying problem is the contract demanding postgres on a
  sqlite-only host" → `stop_as_unrecoverable`

Return the JSON now.
"""


def run_product_steward(
    *,
    prd_path: Path,
    bundle: CharterBundle,
    completed: list[StepResult],
    target_path: Path,
    run_dir: Path,
    config: NCDevConfig | None,
    last_test_craftr_scores: dict | None = None,
    model: str | None = None,
    max_budget_usd: float | None = None,
) -> StewardDecision:
    """Run one Steward judgment session, return its decision.

    A malformed response collapses to STOP_AS_UNRECOVERABLE — silently
    continuing on a Steward that didn't actually emit a decision is the
    failure mode this whole feature exists to prevent.
    """
    prompt = build_steward_prompt(
        prd_path=prd_path,
        bundle=bundle,
        completed=completed,
        target_path=target_path,
        last_test_craftr_scores=last_test_craftr_scores,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "steward-prompt.md").write_text(prompt, encoding="utf-8")

    session = run_ai_session(
        prompt,
        cwd=target_path,
        config=config,
        tools=DEFAULT_PLAN_TOOLS,
        model=model,
        timeout=600,
        include_codex_protocol=False,
        max_budget_usd=max_budget_usd,
        log_path=run_dir / "steward-session.jsonl",
    )
    (run_dir / "steward-response.md").write_text(
        session.final_text or "(empty)", encoding="utf-8",
    )

    if not session.success or not session.final_text:
        return StewardDecision(
            disposition=Disposition.STOP_AS_UNRECOVERABLE,
            reasoning="Steward session failed or returned no text",
        )
    try:
        return parse_steward_response(session.final_text)
    except (json.JSONDecodeError, ValueError) as exc:
        return StewardDecision(
            disposition=Disposition.STOP_AS_UNRECOVERABLE,
            reasoning=f"Steward response invalid: {exc}",
        )
```

- [ ] **Step 6.4: Run the tests and verify they pass**

```bash
pytest tests/unit/test_product_steward.py -v
```
Expected: 7 passed.

- [ ] **Step 6.5: Commit**

```bash
git add src/ncdev/pipeline/product_steward.py tests/unit/test_product_steward.py
git commit -m "feat(steward): prompt builder + runner with safe failure mode"
```

---

## Task 7: Factory loop skeleton

**Files:**
- Create: `src/ncdev/factory.py`
- Test: `tests/unit/test_factory.py`

- [ ] **Step 7.1: Write the failing tests**

```python
# tests/unit/test_factory.py
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ncdev.factory import (
    FactoryRunState,
    FactoryStopReason,
    run_factory,
)
from ncdev.pipeline.product_steward import Disposition, StewardDecision


def test_factory_stops_when_steward_says_continue_at_end_of_queue(monkeypatch, tmp_path):
    """End-of-queue + Steward says continue → factory exits with status=passed."""
    from ncdev import factory as fac

    # Stub the inner build pass: pretend run_pipeline ran and all features passed.
    fake_state = MagicMock()
    fake_state.status = "passed"
    fake_state.run_id = "test-run"
    fake_state.run_dir = str(tmp_path / "run")
    fake_state.target_path = str(tmp_path / "target")
    fake_state.completed_steps = []
    Path(fake_state.run_dir).mkdir()
    Path(fake_state.target_path).mkdir()

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: fake_state)
    monkeypatch.setattr(fac, "load_charter_bundle_from_run",
                        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])))
    monkeypatch.setattr(fac, "run_product_steward",
                        lambda **kw: StewardDecision(
                            disposition=Disposition.CONTINUE,
                            reasoning="all done",
                        ))

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(
        workspace=tmp_path,
        source_path=prd,
        max_cycles=3,
    )
    assert result.stop_reason == FactoryStopReason.STEWARD_CONTINUE_AT_END
    assert result.cycles_run == 1


def test_factory_exhausts_budget(monkeypatch, tmp_path):
    """If the Steward keeps asking for repairs, the factory stops at max_cycles."""
    from ncdev import factory as fac

    fake_state = MagicMock()
    fake_state.status = "failed"
    fake_state.run_id = "test-run"
    fake_state.run_dir = str(tmp_path / "run")
    fake_state.target_path = str(tmp_path / "target")
    Path(fake_state.run_dir).mkdir()
    Path(fake_state.target_path).mkdir()

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: fake_state)
    monkeypatch.setattr(fac, "load_charter_bundle_from_run",
                        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])))
    monkeypatch.setattr(fac, "run_product_steward",
                        lambda **kw: StewardDecision(
                            disposition=Disposition.REPAIR_CURRENT_SLICE,
                            reasoning="still broken",
                            target_feature_ids=["f01"],
                        ))

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(
        workspace=tmp_path,
        source_path=prd,
        max_cycles=3,
    )
    assert result.stop_reason == FactoryStopReason.BUDGET_EXHAUSTED
    assert result.cycles_run == 3


def test_factory_stops_on_unrecoverable(monkeypatch, tmp_path):
    from ncdev import factory as fac

    fake_state = MagicMock()
    fake_state.status = "failed"
    fake_state.run_id = "test-run"
    fake_state.run_dir = str(tmp_path / "run")
    fake_state.target_path = str(tmp_path / "target")
    Path(fake_state.run_dir).mkdir()
    Path(fake_state.target_path).mkdir()

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: fake_state)
    monkeypatch.setattr(fac, "load_charter_bundle_from_run",
                        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])))
    monkeypatch.setattr(fac, "run_product_steward",
                        lambda **kw: StewardDecision(
                            disposition=Disposition.STOP_AS_UNRECOVERABLE,
                            reasoning="unrecoverable: missing infra",
                        ))

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(
        workspace=tmp_path,
        source_path=prd,
        max_cycles=5,
    )
    assert result.stop_reason == FactoryStopReason.STEWARD_UNRECOVERABLE
    assert result.cycles_run == 1
```

- [ ] **Step 7.2: Run the tests and verify they fail**

```bash
pytest tests/unit/test_factory.py -v
```
Expected: `ModuleNotFoundError: No module named 'ncdev.factory'`.

- [ ] **Step 7.3: Implement the factory**

```python
# src/ncdev/factory.py
"""NC Dev Factory — closed-loop autonomous build + judge + replan.

Replaces "ncdev full → maybe quality_gate" with:

    cycle 1: build → judge → continue | repair | replan | stop
    cycle 2: same, with the previous cycle's state carried forward
    ...

The judge is a Product Steward Claude session (see
``ncdev.pipeline.product_steward``). The build is the existing
``run_pipeline``. The factory itself is thin — its only job is to
sequence cycles and act on Steward dispositions until the product
is done or the budget runs out.

Mid-cycle mutations (insert_features / rewrite_acceptance /
rerun_charter) are NOT YET applied in this slice — they are logged
and downgraded to STOP_AS_UNRECOVERABLE for now. The next slice
will wire them up. CONTINUE / REPAIR / STOP work today.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from ncdev.core.config import NCDevConfig
from ncdev.pipeline.charter import load_charter
from ncdev.pipeline.engine import run_pipeline
from ncdev.pipeline.models import CharterBundle
from ncdev.pipeline.product_steward import (
    Disposition,
    StewardDecision,
    run_product_steward,
)

logger = logging.getLogger(__name__)
console = Console()


class FactoryStopReason(str, Enum):
    STEWARD_CONTINUE_AT_END = "steward_continue_at_end"
    STEWARD_UNRECOVERABLE = "steward_unrecoverable"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NOT_YET_IMPLEMENTED = "disposition_not_yet_implemented"


@dataclass
class FactoryRunState:
    workspace: Path
    source_path: Path
    cycles_run: int = 0
    stop_reason: FactoryStopReason | None = None
    last_pipeline_status: str = ""
    decisions: list[StewardDecision] = field(default_factory=list)
    run_dirs: list[str] = field(default_factory=list)


def load_charter_bundle_from_run(run_dir: Path) -> CharterBundle:
    """Indirection point so tests can stub charter loading."""
    return load_charter(run_dir / "outputs", strict=False)


def run_factory(
    *,
    workspace: Path,
    source_path: Path,
    target_repo_path: Path | None = None,
    max_cycles: int = 5,
    builder_model: str | None = None,
    builder_timeout: int = 3600,
    max_budget_usd: float | None = None,
    config: NCDevConfig | None = None,
) -> FactoryRunState:
    """Run the build→judge→repeat loop.

    Returns when the Steward signals CONTINUE at end-of-queue, signals
    STOP_AS_UNRECOVERABLE, returns a not-yet-implemented disposition,
    or ``max_cycles`` has been spent.
    """
    state = FactoryRunState(
        workspace=workspace.resolve(),
        source_path=source_path.resolve(),
    )

    for cycle in range(1, max_cycles + 1):
        console.print(Panel(
            f"[bold cyan]Factory cycle {cycle}/{max_cycles}[/bold cyan]",
            border_style="cyan",
        ))

        # Phase A — build (or re-build)
        pipeline_state = run_pipeline(
            workspace=workspace,
            source_path=source_path,
            target_repo_path=target_repo_path,
            builder_model=builder_model,
            builder_timeout=builder_timeout,
            max_budget_usd=max_budget_usd,
            config=config,
            # Factory owns halting via Steward — engine should always
            # surface FAILED features instead of returning early.
            halt_on_failed=False,
        )
        state.cycles_run = cycle
        state.last_pipeline_status = pipeline_state.status
        state.run_dirs.append(pipeline_state.run_dir)

        # Phase B — judge (Steward)
        run_dir = Path(pipeline_state.run_dir)
        try:
            bundle = load_charter_bundle_from_run(run_dir)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Charter unreadable after build: {exc}[/red]")
            state.stop_reason = FactoryStopReason.STEWARD_UNRECOVERABLE
            return state

        decision = run_product_steward(
            prd_path=source_path,
            bundle=bundle,
            completed=list(pipeline_state.completed_steps),
            target_path=Path(pipeline_state.target_path),
            run_dir=run_dir / "steward" / f"cycle-{cycle}",
            config=config,
            model=builder_model,
            max_budget_usd=max_budget_usd,
        )
        state.decisions.append(decision)
        console.print(
            f"  [cyan]Steward[/cyan]: {decision.disposition.value} — "
            f"{decision.reasoning[:200]}"
        )

        # Phase C — act
        if decision.disposition == Disposition.CONTINUE:
            # CONTINUE at end-of-run = product is done.
            state.stop_reason = FactoryStopReason.STEWARD_CONTINUE_AT_END
            return state
        if decision.disposition == Disposition.STOP_AS_UNRECOVERABLE:
            state.stop_reason = FactoryStopReason.STEWARD_UNRECOVERABLE
            return state
        if decision.disposition == Disposition.REPAIR_CURRENT_SLICE:
            # Repair = next cycle re-runs the affected features. The
            # state scanner will see the FAILED status from this cycle
            # and not skip them. (The next slice will tighten this to
            # only re-run target_feature_ids; for now we re-enter the
            # whole pipeline.)
            continue
        if decision.disposition in {
            Disposition.INSERT_FEATURES,
            Disposition.REWRITE_ACCEPTANCE,
            Disposition.RERUN_CHARTER,
        }:
            console.print(
                f"[yellow]Disposition {decision.disposition.value} "
                "is not yet implemented in this slice — stopping. "
                "Decision persisted for the next slice to act on.[/yellow]"
            )
            state.stop_reason = FactoryStopReason.NOT_YET_IMPLEMENTED
            return state

    state.stop_reason = FactoryStopReason.BUDGET_EXHAUSTED
    return state
```

- [ ] **Step 7.4: Run the tests and verify they pass**

```bash
pytest tests/unit/test_factory.py -v
```
Expected: 3 passed.

- [ ] **Step 7.5: Commit**

```bash
git add src/ncdev/factory.py tests/unit/test_factory.py
git commit -m "feat(factory): closed-loop build→steward→repeat skeleton"
```

---

## Task 8: CLI subcommand `ncdev factory`

**Files:**
- Modify: `src/ncdev/cli.py` — add the `factory` subparser + dispatch.
- Test: `tests/test_cli.py` — add a smoke test that the parser accepts the new command.

- [ ] **Step 8.1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cli_parses_factory_subcommand():
    from ncdev.cli import build_parser
    parser = build_parser()
    args = parser.parse_args([
        "factory", "--source", "/tmp/prd.md",
        "--workspace", "/tmp/ws",
        "--max-cycles", "5",
    ])
    assert args.command == "factory"
    assert args.source == "/tmp/prd.md"
    assert args.max_cycles == 5


def test_cli_factory_calls_run_factory(monkeypatch, tmp_path):
    from ncdev import cli
    from ncdev.factory import FactoryRunState, FactoryStopReason

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")

    captured = {}

    def fake_run_factory(**kwargs):
        captured.update(kwargs)
        return FactoryRunState(
            workspace=tmp_path,
            source_path=prd,
            cycles_run=1,
            stop_reason=FactoryStopReason.STEWARD_CONTINUE_AT_END,
        )

    monkeypatch.setattr(cli, "_factory_runner", fake_run_factory, raising=False)

    rc = cli.main([
        "factory", "--source", str(prd),
        "--workspace", str(tmp_path),
        "--max-cycles", "2",
    ])
    assert rc == 0
    assert captured["max_cycles"] == 2
    assert captured["source_path"] == prd.resolve()
```

- [ ] **Step 8.2: Run the tests and verify they fail**

```bash
pytest tests/test_cli.py::test_cli_parses_factory_subcommand tests/test_cli.py::test_cli_factory_calls_run_factory -v
```
Expected: FAIL — `factory` subcommand not registered, `_factory_runner` attribute doesn't exist.

- [ ] **Step 8.3: Add the subparser + dispatch**

In `src/ncdev/cli.py`, inside `build_parser()` after the `full` parser block (around line 335), insert:

```python
    factory = sub.add_parser(
        "factory",
        help=(
            "Run the autonomous closed-loop factory: build → judge → "
            "repeat until the product is complete or budget runs out."
        ),
    )
    factory.add_argument("--source", required=True,
                         help="Path to PRD / source spec")
    factory.add_argument("--target-repo", default=None,
                         help="Existing target repository (brownfield)")
    factory.add_argument("--workspace", default=None)
    factory.add_argument("--max-cycles", type=int, default=5,
                         help="Stop after this many build→judge cycles")
    factory.add_argument("--model", default="claude-opus-4-6")
    factory.add_argument("--timeout", type=int, default=3600,
                         help="Per-feature builder timeout (seconds)")
    factory.add_argument("--max-budget-usd", type=float, default=None)
```

At module scope (near the top, with other imports), import the runner
and add an indirection-friendly alias so tests can monkey-patch it:

```python
from ncdev.factory import run_factory as _factory_runner_default

# Indirection so tests can monkey-patch easily.
_factory_runner = _factory_runner_default
```

Then in `main()`, after the existing `if args.command == "full":` block,
add:

```python
    if args.command == "factory":
        workspace = _workspace(args.workspace)
        target_repo = _resolve_target_repo(args.target_repo, workspace)
        result = _factory_runner(
            workspace=workspace,
            source_path=Path(args.source).resolve(),
            target_repo_path=target_repo,
            max_cycles=args.max_cycles,
            builder_model=args.model,
            builder_timeout=args.timeout,
            max_budget_usd=args.max_budget_usd,
        )
        console.print(
            f"factory: cycles={result.cycles_run} "
            f"stop_reason={result.stop_reason.value if result.stop_reason else 'none'}"
        )
        return 0 if result.stop_reason in {
            FactoryStopReason.STEWARD_CONTINUE_AT_END,
        } else 1
```

Also add `from ncdev.factory import FactoryStopReason` at the top of the
file.

- [ ] **Step 8.4: Run the tests and verify they pass**

```bash
pytest tests/test_cli.py::test_cli_parses_factory_subcommand tests/test_cli.py::test_cli_factory_calls_run_factory -v
```
Expected: 2 passed.

- [ ] **Step 8.5: Full regression**

```bash
pytest tests -q
```
Expected: all green. If any previously-passing tests now fail because they assumed the `must_mention_feature_id` default was True, update those fixtures to opt back in explicitly — do NOT relax the new default.

- [ ] **Step 8.6: Commit**

```bash
git add src/ncdev/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'ncdev factory' for closed-loop autonomous builds"
```

---

## Task 9: Documentation — CLAUDE.md + quickstart

**Files:**
- Modify: `CLAUDE.md` — short blurb pointing to `ncdev factory` as the autonomous mode; keep `ncdev full` documented as the debug subset.
- Modify: `src/ncdev/cli.py` — update `_quickstart_text()` to mention `factory` first.

- [ ] **Step 9.1: Edit CLAUDE.md**

Replace the existing `**Commands:**` block (lines ~9-13) with:

```markdown
**Commands:**
  - `ncdev factory --source prd.md` — **autonomous closed-loop factory** (build → judge → repeat until product is complete or budget runs out). The default for end-to-end product builds.
  - `ncdev full --source prd.md` — single open-loop PRD build pass (debug / one-shot mode; no Steward).
  - `ncdev dev --project X --task Y` — single-task freeform engineering
  - `ncdev serve` — HTTP intake for Sentinel reports
  - `ncdev doctor` — preflight
```

And add a new section after the architecture diagram:

```markdown
## Factory mode (autonomous closed-loop)

`ncdev factory` adds two layers on top of `ncdev full`:

1. **Product Steward** — a Claude session that runs after each build
   pass with the PRD, feature queue, completed results, and current
   repo state, and emits a `Disposition`:
   `continue | repair_current_slice | insert_features | rewrite_acceptance | rerun_charter | stop_as_unrecoverable`.
2. **Factory loop** — repeats build→steward until the Steward says
   `continue` at end-of-queue (product done), says
   `stop_as_unrecoverable`, or the cycle budget runs out.

The Steward holds whole-product UX coherence in its head — the role
that was missing from `ncdev full`'s feature-local verifiers. As
reasoning models improve, the Steward improves automatically (no
prompt re-tuning required).
```

- [ ] **Step 9.2: Update quickstart text**

In `src/ncdev/cli.py`, edit `_quickstart_text()` to mention `factory`
above `full`. (Keep the `full` line for users who want one-shot
behaviour.)

- [ ] **Step 9.3: Commit**

```bash
git add CLAUDE.md src/ncdev/cli.py
git commit -m "docs(factory): point at ncdev factory as the autonomous default"
```

---

## Task 10: End-to-end integration test (mocked)

**Files:**
- Create: `tests/integration/test_factory_loop.py`

- [ ] **Step 10.1: Write the integration test**

```python
# tests/integration/test_factory_loop.py
"""Factory loop integration test.

Drives ``run_factory`` end-to-end with mocked AI sessions and
mocked pipeline. Verifies that:

- a CONTINUE decision at cycle 1 stops the loop with success
- a REPAIR decision triggers a second cycle
- two REPAIRs followed by CONTINUE finishes successfully in cycle 3
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ncdev import factory as fac
from ncdev.factory import FactoryStopReason, run_factory
from ncdev.pipeline.product_steward import Disposition, StewardDecision


def _make_pipeline_state(tmp_path: Path, status: str = "passed"):
    state = MagicMock()
    state.status = status
    state.run_id = "test"
    state.run_dir = str(tmp_path / "run")
    state.target_path = str(tmp_path / "target")
    state.completed_steps = []
    Path(state.run_dir).mkdir(exist_ok=True)
    Path(state.target_path).mkdir(exist_ok=True)
    return state


def test_three_cycle_repair_then_continue(monkeypatch, tmp_path):
    """REPAIR, REPAIR, CONTINUE → success in 3 cycles."""
    pipeline_states = [
        _make_pipeline_state(tmp_path, "partial"),
        _make_pipeline_state(tmp_path, "partial"),
        _make_pipeline_state(tmp_path, "passed"),
    ]
    decisions = iter([
        StewardDecision(disposition=Disposition.REPAIR_CURRENT_SLICE,
                        reasoning="r1", target_feature_ids=["f01"]),
        StewardDecision(disposition=Disposition.REPAIR_CURRENT_SLICE,
                        reasoning="r2", target_feature_ids=["f02"]),
        StewardDecision(disposition=Disposition.CONTINUE,
                        reasoning="done"),
    ])
    pipeline_iter = iter(pipeline_states)

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: next(pipeline_iter))
    monkeypatch.setattr(fac, "load_charter_bundle_from_run",
                        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])))
    monkeypatch.setattr(fac, "run_product_steward",
                        lambda **kw: next(decisions))

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(
        workspace=tmp_path,
        source_path=prd,
        max_cycles=5,
    )
    assert result.cycles_run == 3
    assert result.stop_reason == FactoryStopReason.STEWARD_CONTINUE_AT_END
    assert [d.disposition for d in result.decisions] == [
        Disposition.REPAIR_CURRENT_SLICE,
        Disposition.REPAIR_CURRENT_SLICE,
        Disposition.CONTINUE,
    ]


def test_disposition_not_yet_implemented_short_circuits(monkeypatch, tmp_path):
    """INSERT_FEATURES is logged + downgraded for now."""
    monkeypatch.setattr(fac, "run_pipeline",
                        lambda **kw: _make_pipeline_state(tmp_path, "passed"))
    monkeypatch.setattr(fac, "load_charter_bundle_from_run",
                        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])))
    monkeypatch.setattr(fac, "run_product_steward",
                        lambda **kw: StewardDecision(
                            disposition=Disposition.INSERT_FEATURES,
                            reasoning="missing settings page",
                        ))

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(workspace=tmp_path, source_path=prd, max_cycles=5)
    assert result.stop_reason == FactoryStopReason.NOT_YET_IMPLEMENTED
    assert result.cycles_run == 1
```

- [ ] **Step 10.2: Run the integration tests**

```bash
pytest tests/integration/test_factory_loop.py -v
```
Expected: 2 passed.

- [ ] **Step 10.3: Full test suite**

```bash
pytest tests -q
```
Expected: all green.

- [ ] **Step 10.4: Commit**

```bash
git add tests/integration/test_factory_loop.py
git commit -m "test(factory): end-to-end loop integration (3-cycle repair→continue)"
```

---

## Self-review

- **Spec coverage:** Move #1 (factory command) → Tasks 7–8. Move #3 stub (Steward) → Tasks 5–6. Move #5 (demote tactic-prompts) → Tasks 1–4 (provenance replaces the marker policy as ground truth; the prompt is reframed). ✅
- **Placeholder scan:** No TBDs, every step has the actual code. ✅
- **Type consistency:** `Disposition`, `StewardDecision`, `FactoryRunState`, `FactoryStopReason`, `ProvenanceRecord`, `FeatureAmendment` used consistently across tasks. ✅
- **No mutations in this slice:** `INSERT_FEATURES`, `REWRITE_ACCEPTANCE`, `RERUN_CHARTER` short-circuit to `NOT_YET_IMPLEMENTED`. Decision is persisted so the next slice can act on it. Explicit and tested. ✅

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-15-ncdev-factory-loop.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
