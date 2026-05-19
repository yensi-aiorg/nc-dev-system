# Dynamic Capability Adoption — Phase 2 (Ledger & Feedback Loop) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give NC Dev System *memory* — a cross-project ledger that records which model / skill set / flags each factory cycle used and how it performed, then feeds that history back so capability resolution and skill selection improve run over run.

**Architecture:** A new `capability_ledger.py` appends one JSONL entry per factory cycle to `~/.ncdev/capability-ledger.jsonl`, combining objective `RunMetrics` with the Steward's structured `capability_lessons`. `capability_policy.resolve_model` and `skill_selector.select_skills` gain optional ledger-aware paths: a metrics gate demotes a model with a bad recent track record, and narrative bias drops skills the Steward flagged as unhelpful. All ledger consultation is opt-in via new keyword args, so Phase 1 behaviour and its 741 tests are unchanged.

**Tech Stack:** Python 3.13, Pydantic v2, pytest. Builds on Phase 1 (`capability_probe`, `capability_policy`, `skill_selector`) and existing `pipeline/metrics.py`, `pipeline/product_steward.py`, `factory.py`.

**Scope:** This is Phase 2a of the spec `docs/superpowers/specs/2026-05-18-dynamic-capability-adoption-design.md`. Spec §4.3 (**gated skill authoring** — dispatching Claude sessions to write/validate/promote new skills) is a separate, heavier subsystem and is deferred to a **Phase 2b** plan, to be written after this lands. This plan delivers a complete, testable learning loop on its own.

---

## Decisions & assumptions (review before executing)

These concretise underspecified parts of the spec. Adjust on review if you disagree:

1. **One ledger entry per factory cycle**, keyed on the *builder* `(provider, model)` — the capability that most drives build quality. "Cycles-to-done" is derived by counting a run's entries. The orchestrator (planning/review) capability is recorded as a field but not separately gated.
2. **Metrics gate trigger:** over the last `_GATE_WINDOW = 5` ledger entries for a `(provider, model)`, if there are at least `_GATE_MIN_SAMPLES = 3` and the mean failure rate (`1 − first_pass_success_rate`) exceeds `_GATE_FAIL_THRESHOLD = 0.5`, demote to the next alias in the provider's alias chain.
3. **The gate has teeth only where an alias chain exists.** Claude has `opus → sonnet → haiku`; Codex currently exposes a single model, so the gate *records* but cannot demote it. Codex model alternatives are future work (noted, not built here).
4. **Narrative bias is conservative:** a skill the Steward explicitly flags as "hurt" is dropped from selection; "helped" lessons are advisory only (no forced inclusion) to avoid runaway feedback.
5. **Ledger consultation is opt-in.** New keyword args default to "no ledger" → Phase 1 behaviour and tests are untouched.

---

## File Structure

**New files:**
- `src/ncdev/core/capability_ledger.py` — `LedgerEntry` model, ledger path, append/read, `record_cycle()`, gate helper `model_failure_rate()`
- `tests/test_core/test_capability_ledger.py`
- `tests/test_core/test_capability_feedback.py` — end-to-end loop test

**Modified files:**
- `src/ncdev/pipeline/models.py` — `StepResult` gains `resolved_provider`, `resolved_model`, `skills_steered`
- `src/ncdev/pipeline/claude_executor.py` — populate those `StepResult` fields
- `src/ncdev/pipeline/product_steward.py` — `StewardDecision` gains `capability_lessons`; prompt requests them
- `src/ncdev/factory.py` — call `record_cycle()` after each Steward decision
- `src/ncdev/core/capability_policy.py` — `resolve_model` gains an optional ledger-driven metrics gate
- `src/ncdev/core/skill_selector.py` — `select_skills` gains optional narrative bias

---

## Task 1: Capability ledger — model, path, append/read

**Files:**
- Create: `src/ncdev/core/capability_ledger.py`
- Test: `tests/test_core/test_capability_ledger.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core/test_capability_ledger.py
from ncdev.core.capability_ledger import (
    LedgerEntry,
    append_entry,
    ledger_path,
    read_entries,
)


def _entry(**over):
    base = dict(
        timestamp="2026-05-19T00:00:00+00:00",
        project_name="demo", run_id="r1", cycle=1,
        provider="openai_codex", model="gpt-5.5",
        skills_steered=["systematic-debugging"], extra_args=[],
        features_total=4, features_passed=3,
        first_pass_success_rate=0.75, repair_rate=0.25, broken_rate=0.0,
        total_cost_usd=1.5, steward_disposition="continue",
        capability_lessons=[],
    )
    base.update(over)
    return LedgerEntry(**base)


def test_ledger_path_is_under_home_ncdev(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    p = ledger_path()
    assert p == tmp_path / ".ncdev" / "capability-ledger.jsonl"


def test_append_then_read_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    append_entry(_entry(run_id="r1"))
    append_entry(_entry(run_id="r2"))
    entries = read_entries()
    assert [e.run_id for e in entries] == ["r1", "r2"]


def test_read_entries_missing_ledger_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    assert read_entries() == []


def test_read_entries_skips_corrupt_lines(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    append_entry(_entry(run_id="good"))
    ledger_path().write_text(
        ledger_path().read_text(encoding="utf-8") + "{bad json\n", encoding="utf-8"
    )
    entries = read_entries()
    assert [e.run_id for e in entries] == ["good"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ncdev.core.capability_ledger'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/core/capability_ledger.py
"""Cross-project capability ledger — NC Dev's memory.

One JSONL entry per factory cycle at ~/.ncdev/capability-ledger.jsonl,
combining objective metrics with the Steward's structured lessons.
Append-only; corrupt lines are skipped on read, never fatal.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class LedgerEntry(BaseModel):
    """One factory cycle's capability record."""

    timestamp: str
    project_name: str
    run_id: str
    cycle: int
    # Capability used (the builder).
    provider: str
    model: str
    skills_steered: list[str] = Field(default_factory=list)
    extra_args: list[str] = Field(default_factory=list)
    # Objective metrics.
    features_total: int = 0
    features_passed: int = 0
    first_pass_success_rate: float = 0.0
    repair_rate: float = 0.0
    broken_rate: float = 0.0
    total_cost_usd: float = 0.0
    # Steward narrative.
    steward_disposition: str = ""
    capability_lessons: list[str] = Field(default_factory=list)


def ledger_path() -> Path:
    """Absolute path to the cross-project ledger file."""
    return Path.home() / ".ncdev" / "capability-ledger.jsonl"


def append_entry(entry: LedgerEntry) -> None:
    """Append one entry as a JSONL line. Creates the ledger if absent."""
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def read_entries() -> list[LedgerEntry]:
    """Read all valid entries in append order. Missing ledger -> []."""
    path = ledger_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries: list[LedgerEntry] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(LedgerEntry.model_validate_json(line))
        except ValueError:
            continue  # skip corrupt line, never fatal
    return entries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_ledger.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_ledger.py tests/test_core/test_capability_ledger.py
git commit -m "feat(capability): cross-project capability ledger — model + JSONL IO"
```

---

## Task 2: Extend `StepResult` with resolved-capability fields

**Files:**
- Modify: `src/ncdev/pipeline/models.py` (`StepResult`, around line 182)
- Test: `tests/test_core/test_capability_ledger.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_core/test_capability_ledger.py
from ncdev.pipeline.models import StepResult, StepStatus


def test_step_result_has_capability_fields_with_safe_defaults():
    step = StepResult(feature_id="f1", status=StepStatus.PASSED)
    assert step.resolved_provider == ""
    assert step.resolved_model == ""
    assert step.skills_steered == []


def test_step_result_accepts_capability_fields():
    step = StepResult(
        feature_id="f1", status=StepStatus.PASSED,
        resolved_provider="openai_codex", resolved_model="gpt-5.5",
        skills_steered=["systematic-debugging"],
    )
    assert step.resolved_model == "gpt-5.5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_ledger.py -k step_result -v`
Expected: FAIL — `ValidationError` / unexpected keyword `resolved_provider`

- [ ] **Step 3: Add the fields**

In `src/ncdev/pipeline/models.py`, in the `StepResult` model, add three fields after `builder_output`:

```python
    # Capability resolution (Phase 2 — for the capability ledger).
    resolved_provider: str = ""
    resolved_model: str = ""
    skills_steered: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_ledger.py -k step_result -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/models.py tests/test_core/test_capability_ledger.py
git commit -m "feat(capability): StepResult records resolved provider/model/skills"
```

---

## Task 3: Populate the capability fields in `claude_executor.py`

**Files:**
- Modify: `src/ncdev/pipeline/claude_executor.py`
- Test: covered by Task 10's integration test (this task only wires data through)

`claude_executor.py` already (Phase 1, Task 12) computes `_work_type` and a steered skill set, and resolves the builder. This task records that onto the `StepResult` it returns.

- [ ] **Step 1: Capture the steered skill list as a variable**

In `execute_feature_claude_driven`, the Phase 1 block builds `_skill_block` from `select_skills(...)`. Change it to keep the selected list:

Find:
```python
    _skill_block = render_skill_block(
        select_skills(_work_type, scan_installed_skills(target_path))
    )
```
Replace with:
```python
    _selected_skills = select_skills(_work_type, scan_installed_skills(target_path))
    _skill_block = render_skill_block(_selected_skills)
```

- [ ] **Step 2: Resolve the builder capability for the record**

Immediately after the `_skill_block` line, add:

```python
    # Record what the builder capability resolved to, for the ledger.
    from ncdev.core.capability_probe import probe_codex
    from ncdev.core.capability_policy import resolve_model

    _resolved_provider = "openai_codex" if implementer_mode == "codex" else "anthropic_claude_code"
    _resolved_model = (
        resolve_model("openai_codex", model, probe_codex())
        if implementer_mode == "codex"
        else "auto"
    )
```

- [ ] **Step 3: Write the fields onto the returned `StepResult`**

Find every `StepResult(...)` constructed and returned by `execute_feature_claude_driven` and add these three keyword arguments to each:

```python
        resolved_provider=_resolved_provider,
        resolved_model=_resolved_model,
        skills_steered=_selected_skills,
```

If the function builds the `StepResult` in one place near the end, add them there. If there are multiple early-return `StepResult(...)` sites (e.g. a `[BROKEN]` path), add the three kwargs to each so no return path loses the data.

- [ ] **Step 4: Verify no regression**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS (741, no regressions — the new fields have defaults).

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/claude_executor.py
git commit -m "feat(capability): claude_executor records resolved capability on StepResult"
```

---

## Task 4: Ledger `record_cycle()` — the metrics writer

**Files:**
- Modify: `src/ncdev/core/capability_ledger.py`
- Test: `tests/test_core/test_capability_ledger.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_core/test_capability_ledger.py
from ncdev.core.capability_ledger import record_cycle
from ncdev.pipeline.metrics import RunMetrics


def test_record_cycle_writes_entry_from_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    metrics = RunMetrics(
        run_id="r1", project_name="demo", total_features=4,
        passed_features=3, first_pass_success_rate=0.75, repair_rate=0.25,
        builder_primary="codex", builder_model="gpt-5.5",
    )
    steps = [
        StepResult(
            feature_id="f1", status=StepStatus.PASSED,
            resolved_provider="openai_codex", resolved_model="gpt-5.5",
            skills_steered=["systematic-debugging"],
        ),
    ]
    record_cycle(
        metrics=metrics, steps=steps, cycle=1,
        steward_disposition="continue",
        capability_lessons=["codex handled boilerplate well"],
    )
    entries = read_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e.provider == "openai_codex"
    assert e.model == "gpt-5.5"
    assert e.cycle == 1
    assert e.first_pass_success_rate == 0.75
    assert e.skills_steered == ["systematic-debugging"]
    assert e.capability_lessons == ["codex handled boilerplate well"]


def test_record_cycle_no_steps_uses_metrics_builder(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    metrics = RunMetrics(run_id="r1", builder_primary="codex", builder_model="gpt-5.5")
    record_cycle(metrics=metrics, steps=[], cycle=1, steward_disposition="continue",
                 capability_lessons=[])
    e = read_entries()[0]
    assert e.provider == "openai_codex"
    assert e.model == "gpt-5.5"
    assert e.broken_rate == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_ledger.py -k record_cycle -v`
Expected: FAIL — `ImportError: cannot import name 'record_cycle'`

- [ ] **Step 3: Write minimal implementation**

```python
# Add to src/ncdev/core/capability_ledger.py — add these imports at the top:
#   from datetime import datetime, timezone
#   from ncdev.pipeline.metrics import RunMetrics
#   from ncdev.pipeline.models import StepResult, StepStatus

# Maps RunMetrics.builder_primary short names to provider registry keys.
_BUILDER_PROVIDER: dict[str, str] = {
    "codex": "openai_codex",
    "claude": "anthropic_claude_code",
}


def record_cycle(
    *,
    metrics: RunMetrics,
    steps: list[StepResult],
    cycle: int,
    steward_disposition: str,
    capability_lessons: list[str],
) -> LedgerEntry:
    """Build one LedgerEntry from a cycle's metrics + steps and append it.

    The builder capability is taken from the steps' recorded resolution
    when available, else from RunMetrics.builder_*.
    """
    provider = _BUILDER_PROVIDER.get(metrics.builder_primary, "openai_codex")
    model = metrics.builder_model
    skills_steered: list[str] = []
    for step in steps:
        if step.resolved_provider:
            provider = step.resolved_provider
        if step.resolved_model and step.resolved_model != "auto":
            model = step.resolved_model
        for skill in step.skills_steered:
            if skill not in skills_steered:
                skills_steered.append(skill)

    total = metrics.total_features or len(steps)
    broken = sum(1 for s in steps if s.status == StepStatus.FAILED)
    broken_rate = (broken / total) if total else 0.0

    entry = LedgerEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        project_name=metrics.project_name,
        run_id=metrics.run_id,
        cycle=cycle,
        provider=provider,
        model=model,
        skills_steered=skills_steered,
        features_total=total,
        features_passed=metrics.passed_features,
        first_pass_success_rate=metrics.first_pass_success_rate,
        repair_rate=metrics.repair_rate,
        broken_rate=broken_rate,
        total_cost_usd=0.0,
        steward_disposition=steward_disposition,
        capability_lessons=list(capability_lessons),
    )
    append_entry(entry)
    return entry
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_ledger.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_ledger.py tests/test_core/test_capability_ledger.py
git commit -m "feat(capability): record_cycle — write a ledger entry from cycle metrics"
```

---

## Task 5: `StewardDecision` gains `capability_lessons`

**Files:**
- Modify: `src/ncdev/pipeline/product_steward.py` (`StewardDecision`, around line 53)
- Test: `tests/unit/test_product_steward.py` (create if absent, else append)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_product_steward.py — create if absent, else append
from ncdev.pipeline.product_steward import StewardDecision, parse_steward_response


def test_steward_decision_capability_lessons_defaults_empty():
    d = StewardDecision(disposition="continue", reasoning="done")
    assert d.capability_lessons == []


def test_parse_steward_response_reads_capability_lessons():
    text = '''{
      "disposition": "continue",
      "reasoning": "product complete",
      "capability_lessons": ["systematic-debugging cut repair attempts on backend features"]
    }'''
    decision = parse_steward_response(text)
    assert decision.capability_lessons == [
        "systematic-debugging cut repair attempts on backend features"
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_product_steward.py -v`
Expected: FAIL — `StewardDecision` has no `capability_lessons`

- [ ] **Step 3: Add the field**

In `src/ncdev/pipeline/product_steward.py`, in the `StewardDecision` model, add after `amendments`:

```python
    capability_lessons: list[str] = Field(default_factory=list)
```

`parse_steward_response` uses `StewardDecision.model_validate(data)`, so it picks up the new field automatically — no parser change needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_product_steward.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/product_steward.py tests/unit/test_product_steward.py
git commit -m "feat(capability): StewardDecision carries structured capability_lessons"
```

---

## Task 6: Steward prompt requests capability lessons

**Files:**
- Modify: `src/ncdev/pipeline/product_steward.py` (`build_steward_prompt` + its JSON-schema block)

The Steward already returns a JSON object (see the existing schema near line 265, the `"disposition": ...` block). This task adds a `capability_lessons` field to the schema and an instruction to fill it.

- [ ] **Step 1: Add `capability_lessons` to the JSON schema in the prompt**

In `build_steward_prompt` (`product_steward.py`, ~line 177), the prompt is an f-string. Its JSON schema block (~lines 264-270) ends with the `"amendments"` line inside a `{{ ... }}` fence. Add one more field after the `"amendments"` line (mind the doubled braces — this is an f-string, so a literal `{` is `{{`):

```
  "amendments": [{{"feature_id": "...", "field": "...", "new_value": ..., "reason": "..."}}],
  "capability_lessons": ["<short structured lessons about which models/skills helped or hurt — e.g. 'systematic-debugging cut repair attempts on backend features'; 'opus over-engineered the charter'. Empty list if nothing notable.>"]
```

(i.e. add a comma to the existing `"amendments"` line and append the `"capability_lessons"` line.)

- [ ] **Step 2: Add an instruction paragraph**

In the same prompt, after the disposition-meanings section, add a short paragraph:

```
### Capability lessons

In `capability_lessons`, record short, concrete observations about how the
*tools* performed this cycle — which skills measurably helped or hurt, whether
the model over- or under-built. One sentence each. These feed NC Dev's
capability ledger and bias future skill selection. Use [] when nothing stands out.
```

- [ ] **Step 3: Add a prompt-content test**

`build_steward_prompt` builds the prompt as an f-string from a `CharterBundle` (which needs a contract, verification contract, and feature queue) — constructing a full valid bundle in a unit test is brittle. The prompt text added in Steps 1-2 is *static*, so assert it is present in the module source directly — concrete and non-flaky:

```python
# Append to tests/unit/test_product_steward.py
from pathlib import Path

import ncdev.pipeline.product_steward as _ps_module


def test_steward_prompt_template_requests_capability_lessons():
    src = Path(_ps_module.__file__).read_text(encoding="utf-8")
    # The JSON schema the Steward must return now includes the field...
    assert '"capability_lessons"' in src
    # ...and the prompt explains what to put there.
    assert "Capability lessons" in src
```

- [ ] **Step 4: Run the test**

Run: `.venv/bin/python -m pytest tests/unit/test_product_steward.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/product_steward.py tests/unit/test_product_steward.py
git commit -m "feat(capability): Steward prompt requests structured capability lessons"
```

---

## Task 7: Wire `record_cycle()` into the factory loop

**Files:**
- Modify: `src/ncdev/factory.py` (the cycle loop, after the Steward decision near line 608)

- [ ] **Step 1: Add the ledger write after the Steward decision**

In `_run_factory_cycle_loop`, immediately after `state.decisions.append(decision)` (around line 608), insert:

```python
        # Phase B.5 — record this cycle in the cross-project capability ledger.
        try:
            from ncdev.core.capability_ledger import record_cycle
            from ncdev.pipeline.metrics import compute_run_metrics

            record_cycle(
                metrics=compute_run_metrics(pipeline_state),
                steps=list(pipeline_state.completed_steps),
                cycle=cycle,
                steward_disposition=decision.disposition.value,
                capability_lessons=list(decision.capability_lessons),
            )
        except Exception as exc:  # noqa: BLE001
            # The ledger is best-effort telemetry — never fail a build over it.
            console.print(f"[yellow]capability ledger write skipped: {exc}[/yellow]")
```

`pipeline_state` is the `PipelineRunState` returned by `run_pipeline` earlier in the same loop iteration; `compute_run_metrics` accepts it directly.

- [ ] **Step 2: Verify no regression**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no regressions. Existing factory tests must not write to the real `~/.ncdev/`; if any factory test exercises this loop, it should monkeypatch `Path.home` or the ledger will be written under the real home. If a test newly touches `~/.ncdev`, add a `monkeypatch.setattr` for `ncdev.core.capability_ledger.Path.home` to that test (mirror the ledger tests) and report it.

- [ ] **Step 3: Commit**

```bash
git add src/ncdev/factory.py
git commit -m "feat(capability): factory loop records each cycle to the ledger"
```

---

## Task 8: Metrics gate in `resolve_model`

**Files:**
- Modify: `src/ncdev/core/capability_policy.py`
- Test: `tests/test_core/test_capability_policy.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_core/test_capability_policy.py
from ncdev.core.capability_ledger import LedgerEntry
from ncdev.core.capability_policy import resolve_model as _rm


def _led(model, fpsr, n=1):
    return [
        LedgerEntry(
            timestamp="t", project_name="p", run_id=f"r{i}", cycle=1,
            provider="anthropic_claude_code", model=model,
            first_pass_success_rate=fpsr,
        )
        for i in range(n)
    ]


def test_gate_demotes_model_with_bad_track_record(monkeypatch):
    snap = _claude_snap(monkeypatch)
    # 4 entries for "opus" averaging 0.2 first-pass success -> 0.8 failure.
    ledger = _led("opus", 0.2, n=4)
    assert _rm("anthropic_claude_code", "auto", snap, ledger_entries=ledger) == "sonnet"


def test_gate_keeps_model_with_good_track_record(monkeypatch):
    snap = _claude_snap(monkeypatch)
    ledger = _led("opus", 0.9, n=4)
    assert _rm("anthropic_claude_code", "auto", snap, ledger_entries=ledger) == "opus"


def test_gate_needs_minimum_samples(monkeypatch):
    snap = _claude_snap(monkeypatch)
    # Only 2 bad entries — below _GATE_MIN_SAMPLES — so no demotion.
    ledger = _led("opus", 0.0, n=2)
    assert _rm("anthropic_claude_code", "auto", snap, ledger_entries=ledger) == "opus"


def test_gate_does_not_apply_to_explicit_pin(monkeypatch):
    snap = _claude_snap(monkeypatch)
    ledger = _led("claude-opus-4-7", 0.0, n=5)
    # An explicit pin is honoured even with a bad record.
    assert _rm("anthropic_claude_code", "claude-opus-4-7", snap, ledger_entries=ledger) == "claude-opus-4-7"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_policy.py -k gate -v`
Expected: FAIL — `resolve_model` has no `ledger_entries` keyword

- [ ] **Step 3: Implement the gate**

In `src/ncdev/core/capability_policy.py`, add the gate constants and helper, and extend `resolve_model`:

```python
# --- Metrics gate (Phase 2) -------------------------------------------------
_GATE_WINDOW = 5          # consider at most this many recent entries
_GATE_MIN_SAMPLES = 3     # need at least this many before gating
_GATE_FAIL_THRESHOLD = 0.5  # mean failure rate above this -> demote

# Per-provider alias chain, best-first. Demotion steps one rung down.
_ALIAS_CHAIN: dict[str, tuple[str, ...]] = {
    "anthropic_claude_code": CLAUDE_MODEL_ALIASES,  # ("opus", "sonnet", "haiku")
    "openai_codex": (CODEX_DEFAULT_MODEL,),         # single model — no demotion target
}


def _gated_model(provider: str, model: str, ledger_entries: list) -> str:
    """Demote `model` one alias rung if its recent track record is bad.

    `ledger_entries` is a list of capability_ledger.LedgerEntry. Only
    entries for this exact (provider, model) count. Returns `model`
    unchanged when there is no demotion target or not enough data.
    """
    chain = _ALIAS_CHAIN.get(provider, ())
    if model not in chain:
        return model
    idx = chain.index(model)
    if idx + 1 >= len(chain):
        return model  # already at the last rung — nowhere to demote
    recent = [
        e for e in ledger_entries
        if e.provider == provider and e.model == model
    ][-_GATE_WINDOW:]
    if len(recent) < _GATE_MIN_SAMPLES:
        return model
    mean_failure = sum(1.0 - e.first_pass_success_rate for e in recent) / len(recent)
    if mean_failure > _GATE_FAIL_THRESHOLD:
        return chain[idx + 1]
    return model
```

Then change the `resolve_model` signature and body. The current function ends with `return requested.strip()`. Replace the whole function with:

```python
def resolve_model(
    provider: str,
    requested: str | None,
    snapshot: ProviderCapabilitySnapshot,
    *,
    ledger_entries: list | None = None,
) -> str:
    """Resolve `requested` to a concrete model string for `provider`.

    - None / "auto" / "latest" / ""  -> the provider default alias
    - a known alias (opus/sonnet/...) -> passed through
    - anything else                   -> treated as an explicit pin, passed through

    When `ledger_entries` is supplied, a resolved *alias* (not an explicit
    pin) is run through the metrics gate: a model with a bad recent track
    record is demoted one rung down its alias chain.
    """
    default = _PROVIDER_DEFAULT.get(provider, CLAUDE_MODEL_ALIASES[0])
    if requested is None or requested.strip().lower() in _AUTO_SENTINELS:
        resolved = default
    else:
        resolved = requested.strip()
    if ledger_entries:
        resolved = _gated_model(provider, resolved, ledger_entries)
    return resolved
```

The gate runs for both `auto`-resolved aliases and explicitly-requested aliases, but `_gated_model` returns non-chain values (explicit pins like `claude-opus-4-7`) untouched — so pins are never demoted.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_policy.py -v`
Expected: PASS (13 tests — 9 from Phase 1 + 4 new)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_policy.py tests/test_core/test_capability_policy.py
git commit -m "feat(capability): metrics gate — demote models with a bad ledger record"
```

---

## Task 9: Narrative bias in `select_skills`

**Files:**
- Modify: `src/ncdev/core/skill_selector.py`
- Test: `tests/test_core/test_skill_selector.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_core/test_skill_selector.py
def test_select_skills_drops_skill_flagged_hurt():
    lessons = ["frontend-design hurt — produced inconsistent layouts"]
    picked = select_skills("greenfield_ui", INVENTORY, lessons=lessons)
    assert "frontend-design" not in picked
    assert "test-driven-development" in picked  # unaffected skills remain


def test_select_skills_ignores_lessons_without_hurt():
    lessons = ["frontend-design helped a lot"]
    picked = select_skills("greenfield_ui", INVENTORY, lessons=lessons)
    assert "frontend-design" in picked  # "helped" is advisory, not forced


def test_select_skills_no_lessons_is_phase1_behaviour():
    assert select_skills("bugfix", INVENTORY) == select_skills(
        "bugfix", INVENTORY, lessons=None
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_selector.py -k lesson -v`
Expected: FAIL — `select_skills` has no `lessons` keyword

- [ ] **Step 3: Implement narrative bias**

In `src/ncdev/core/skill_selector.py`, replace `select_skills` with:

```python
def _skills_flagged_hurt(lessons: list[str]) -> set[str]:
    """Skill names a lesson explicitly flags as harmful.

    A skill is dropped when a lesson mentions its name AND the word
    "hurt". Conservative on purpose — "helped" lessons are advisory.
    """
    flagged: set[str] = set()
    for lesson in lessons:
        low = lesson.lower()
        if "hurt" not in low:
            continue
        for skill in {s for skills in _WORK_TYPE_SKILLS.values() for s in skills}:
            if skill in low:
                flagged.add(skill)
    return flagged


def select_skills(
    work_type: str,
    inventory: list[str],
    *,
    lessons: list[str] | None = None,
) -> list[str]:
    """Return the preferred skills for `work_type` that are installed.

    When `lessons` (Steward capability lessons from the ledger) are
    supplied, any skill a lesson flags as "hurt" is dropped.
    """
    preferred = _WORK_TYPE_SKILLS.get(work_type, _WORK_TYPE_SKILLS["brownfield"])
    installed = set(inventory)
    hurt = _skills_flagged_hurt(lessons) if lessons else set()
    return [s for s in preferred if s in installed and s not in hurt]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_selector.py -v`
Expected: PASS (10 tests — 7 from Phase 1 + 3 new)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/skill_selector.py tests/test_core/test_skill_selector.py
git commit -m "feat(capability): skill selection drops skills the Steward flagged hurt"
```

---

## Task 10: End-to-end feedback loop test

**Files:**
- Create: `tests/test_core/test_capability_feedback.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_core/test_capability_feedback.py
"""End-to-end: a recorded cycle feeds back into the next resolution."""

from ncdev.core.capability_ledger import read_entries, record_cycle
from ncdev.core.capability_policy import resolve_model
from ncdev.core.capability_probe import probe_claude
from ncdev.pipeline.metrics import RunMetrics
from ncdev.pipeline.models import StepResult, StepStatus


def _claude_snapshot(monkeypatch):
    monkeypatch.setattr(
        "ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/claude"
    )
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "1.2.3"
    )
    return probe_claude()


def test_bad_cycles_demote_the_model_on_next_resolve(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    snap = _claude_snapshot(monkeypatch)

    # Record 4 bad cycles for the claude builder ("opus", low success).
    for i in range(4):
        metrics = RunMetrics(
            run_id=f"r{i}", project_name="demo", total_features=4,
            passed_features=1, first_pass_success_rate=0.2,
            builder_primary="claude", builder_model="opus",
        )
        steps = [
            StepResult(
                feature_id="f1", status=StepStatus.FAILED,
                resolved_provider="anthropic_claude_code", resolved_model="opus",
            )
        ]
        record_cycle(
            metrics=metrics, steps=steps, cycle=i + 1,
            steward_disposition="repair_current_slice", capability_lessons=[],
        )

    ledger = read_entries()
    assert len(ledger) == 4

    # Phase-1 resolution (no ledger) still yields the default alias.
    assert resolve_model("anthropic_claude_code", "auto", snap) == "opus"
    # Ledger-aware resolution demotes after the bad track record.
    assert resolve_model(
        "anthropic_claude_code", "auto", snap, ledger_entries=ledger
    ) == "sonnet"
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_feedback.py -v`
Expected: PASS

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/test_core/test_capability_feedback.py
git commit -m "test(capability): end-to-end ledger feedback loop"
```

---

## Done criteria (Phase 2a)

- `python -m pytest tests/ -q` is green.
- A factory run appends one JSONL entry per cycle to `~/.ncdev/capability-ledger.jsonl`.
- A ledger write failure never fails a build (best-effort, wrapped).
- After ≥ 3 cycles with a mean first-pass success rate below 0.5 for a model, the next ledger-aware `resolve_model` demotes it one alias rung.
- A skill the Steward flags as "hurt" in `capability_lessons` is dropped from the next `select_skills`.
- Phase 1 behaviour is unchanged when no ledger is supplied (the 741 existing tests stay green).

## Deferred

- **Phase 2b — gated skill authoring** (spec §4.3): when the ledger shows a recurring hand-fix pattern, a dedicated Claude session uses `superpowers:writing-skills` to author, validate, and (human/Steward-gated) promote a new skill. This is a separate subsystem with its own dispatch, validation, and gating concerns — it gets its own spec-level treatment and plan, built on this ledger.
- **Wiring the metrics gate into live resolution.** This plan builds the gate (`resolve_model(..., ledger_entries=...)`) and proves it end-to-end, but does not yet pass `ledger_entries` from the factory/executor call sites into resolution — that wiring is the first task of Phase 2b, once there is confidence in the gate's thresholds from observing real ledger data.
