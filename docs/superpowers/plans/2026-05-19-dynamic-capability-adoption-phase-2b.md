# Dynamic Capability Adoption — Phase 2b (Wire the Feedback Loop Live) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase 2a's capability ledger actually *act* — wire the metrics gate and narrative bias into live resolution so a model with a bad recorded track record is demoted on the next real session, and a skill the Steward flagged as "hurt" is dropped on the next real build.

**Architecture:** Phase 2a built the gate (`resolve_model(..., ledger_entries=)`) and bias (`select_skills(..., lessons=)`) but left both opt-in and un-wired. Phase 2b adds a `recent_lessons()` ledger reader and passes ledger data into the three live call sites: the Claude session runner (`claude_session.py`) and the two `select_skills` sites (`claude_executor.py`, `sentinel_reproduce.py`). The gate self-protects — an empty or thin ledger (`< _GATE_MIN_SAMPLES`) causes no change — so wiring it live is safe today and only acts once real history accumulates.

**Tech Stack:** Python 3.13, Pydantic v2, pytest. Builds on Phase 1 + Phase 2a (`capability_ledger`, `capability_policy`, `skill_selector`).

**Scope:** Phase 2b of the spec `docs/superpowers/specs/2026-05-18-dynamic-capability-adoption-design.md` — completes spec §4.2 (feedback into resolution). Spec §4.3 (**gated skill authoring**) remains a separate **Phase 2c** plan.

---

## Decisions & assumptions (review before executing)

1. **The gate is wired only for `auto` model requests.** `claude_session.py` resolves a concrete model only when the request is `auto`/`latest`/`""`; an explicit pin (`--model opus`) bypasses resolution and therefore the gate. Semantics: `auto` = "let the system decide, gating included"; an explicit model = "I chose this, honour it." This is intentional and matches the Phase 1 pin-always-wins rule.
2. **Live-wiring is safe now despite untuned thresholds.** The ledger starts empty; `_gated_model` returns the model unchanged until `_GATE_MIN_SAMPLES` (3) entries exist for a `(provider, model)`. So nothing is demoted until ≥ 3 real cycles show a genuine > 50 % failure rate. The threshold *values* remain tunable constants in `capability_policy.py`.
3. **Narrative bias filters by project where it can.** `claude_executor` knows the project name (`charter_bundle.contract.project_name`) and passes it so lessons are project-scoped. `sentinel_reproduce` has no clean project handle, so it uses cross-project lessons — acceptable, since a "hurt" skill lesson generalises.
4. **One secondary path is left un-gated:** `ai_provider.ClaudeCLIProvider.build_argv` (`_resolve_claude_model`) is not on the primary session path; it is noted in "Deferred" rather than wired, to avoid speculative changes.

---

## File Structure

**Modified files:**
- `src/ncdev/core/capability_ledger.py` — add `recent_lessons()` reader
- `src/ncdev/claude_session.py` — `auto` resolution passes `ledger_entries`
- `src/ncdev/pipeline/claude_executor.py` — `select_skills` call passes `lessons`
- `src/ncdev/sentinel_reproduce.py` — `select_skills` call passes `lessons`

**New files:**
- `tests/test_core/test_capability_live_wiring.py` — end-to-end: a bad ledger demotes a real spawned session's model

---

## Task 1: `recent_lessons()` ledger reader

**Files:**
- Modify: `src/ncdev/core/capability_ledger.py`
- Test: `tests/test_core/test_capability_ledger.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_core/test_capability_ledger.py
from ncdev.core.capability_ledger import recent_lessons


def test_recent_lessons_flattens_capability_lessons(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    append_entry(_entry(run_id="r1", capability_lessons=["lesson A"]))
    append_entry(_entry(run_id="r2", capability_lessons=["lesson B", "lesson C"]))
    assert recent_lessons() == ["lesson A", "lesson B", "lesson C"]


def test_recent_lessons_filters_by_project(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    append_entry(_entry(run_id="r1", project_name="alpha", capability_lessons=["A only"]))
    append_entry(_entry(run_id="r2", project_name="beta", capability_lessons=["B only"]))
    assert recent_lessons(project_name="alpha") == ["A only"]


def test_recent_lessons_respects_limit(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    for i in range(30):
        append_entry(_entry(run_id=f"r{i}", capability_lessons=[f"lesson {i}"]))
    out = recent_lessons(limit=5)
    assert out == [f"lesson {i}" for i in range(25, 30)]


def test_recent_lessons_empty_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    assert recent_lessons() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_ledger.py -k recent_lessons -v`
Expected: FAIL — `ImportError: cannot import name 'recent_lessons'`

- [ ] **Step 3: Write minimal implementation**

```python
# Add to src/ncdev/core/capability_ledger.py
def recent_lessons(
    *,
    project_name: str | None = None,
    limit: int = 20,
) -> list[str]:
    """Flattened `capability_lessons` from the most recent ledger entries.

    Entries are filtered to `project_name` when given, then the last
    `limit` entries are taken and their lessons concatenated in order.
    """
    entries = read_entries()
    if project_name:
        entries = [e for e in entries if e.project_name == project_name]
    lessons: list[str] = []
    for entry in entries[-limit:]:
        lessons.extend(entry.capability_lessons)
    return lessons
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_ledger.py -v`
Expected: PASS (all ledger tests, including 4 new)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_ledger.py tests/test_core/test_capability_ledger.py
git commit -m "feat(capability): recent_lessons — read recent ledger lessons for bias"
```

---

## Task 2: Wire the metrics gate into `claude_session.py`

**Files:**
- Modify: `src/ncdev/claude_session.py`
- Test: `tests/test_claude_session.py` (append)

`claude_session.py` has a Phase 1 block that resolves an `auto` model. This task makes that resolution ledger-aware.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_claude_session.py
def test_auto_model_demoted_when_ledger_shows_bad_record(monkeypatch, tmp_path):
    """A bad track record for 'opus' in the ledger demotes the auto-resolved
    model to 'sonnet' for a new session."""
    from ncdev.core.capability_ledger import LedgerEntry, append_entry

    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    # Seed 4 bad cycles for the claude builder.
    for i in range(4):
        append_entry(LedgerEntry(
            timestamp="t", project_name="p", run_id=f"r{i}", cycle=1,
            provider="anthropic_claude_code", model="opus",
            first_pass_success_rate=0.1,
        ))

    captured = {}

    def fake_popen(cmd, *a, **kw):
        captured["cmd"] = cmd
        raise OSError("stop — argv captured")

    monkeypatch.setattr(claude_session.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_session.subprocess, "Popen", fake_popen)

    claude_session.run_claude_session("hi", cwd=__import__("pathlib").Path("."))

    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "sonnet"
```

Note: this test's `fake_popen` raises `OSError` (what `Popen` really raises) — `run_claude_session` catches it after the argv is built. If the file's existing `test_auto_model_is_resolved_not_passed_literally` uses `RuntimeError`, leave that one as-is; just append this new test.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_claude_session.py::test_auto_model_demoted_when_ledger_shows_bad_record -v`
Expected: FAIL — model is `opus` (gate not wired), not `sonnet`

- [ ] **Step 3: Wire the ledger into resolution**

In `src/ncdev/claude_session.py`, find the Phase 1 `auto`-resolution block:

```python
    if model.strip().lower() in ("auto", "latest", ""):
        from ncdev.core.capability_probe import probe_claude
        from ncdev.core.capability_policy import resolve_model

        model = resolve_model("anthropic_claude_code", model, probe_claude())
```

Replace it with:

```python
    if model.strip().lower() in ("auto", "latest", ""):
        from ncdev.core.capability_probe import probe_claude
        from ncdev.core.capability_policy import resolve_model
        from ncdev.core.capability_ledger import read_entries

        model = resolve_model(
            "anthropic_claude_code", model, probe_claude(),
            ledger_entries=read_entries(),
        )
```

The imports stay local (no module-load cycle; cost stays off the path for explicit-model callers).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_claude_session.py -v`
Expected: PASS (existing tests + the new one)

- [ ] **Step 5: Confirm no regression, then commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no regressions. `read_entries()` on a missing ledger returns `[]`, so existing claude-session tests (no seeded ledger) resolve exactly as before.

```bash
git add src/ncdev/claude_session.py tests/test_claude_session.py
git commit -m "feat(capability): claude_session metrics gate — demote on bad ledger record"
```

---

## Task 3: Wire narrative bias into `claude_executor.py`

**Files:**
- Modify: `src/ncdev/pipeline/claude_executor.py`
- Test: covered by Task 5's integration test (this task wires data through)

`claude_executor.py` (Phase 2a) calls `select_skills(_work_type, scan_installed_skills(target_path))`. This task passes ledger lessons so a Steward-flagged-"hurt" skill is dropped.

- [ ] **Step 1: Pass `lessons` into the `select_skills` call**

In `execute_feature_claude_driven`, find the Phase 2a line:

```python
    _selected_skills = select_skills(_work_type, scan_installed_skills(target_path))
```

Replace it with:

```python
    from ncdev.core.capability_ledger import recent_lessons

    _selected_skills = select_skills(
        _work_type,
        scan_installed_skills(target_path),
        lessons=recent_lessons(project_name=charter_bundle.contract.project_name),
    )
```

`charter_bundle` is already a parameter of `execute_feature_claude_driven` and `charter_bundle.contract.project_name` is a valid string field (used elsewhere in the pipeline).

- [ ] **Step 2: Verify no regression**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — `recent_lessons` on a missing ledger returns `[]`, so `select_skills` behaves exactly as in Phase 2a.

- [ ] **Step 3: Commit**

```bash
git add src/ncdev/pipeline/claude_executor.py
git commit -m "feat(capability): claude_executor skill selection consults ledger lessons"
```

---

## Task 4: Wire narrative bias into `sentinel_reproduce.py`

**Files:**
- Modify: `src/ncdev/sentinel_reproduce.py`
- Test: `tests/test_core/test_capability_live_wiring.py` (created in Task 5)

`sentinel_reproduce.py` (Phase 1 Task 12) calls `select_skills("bugfix", scan_installed_skills(repo_dir))`. This task passes ledger lessons.

- [ ] **Step 1: Pass `lessons` into the `select_skills` call**

In `reproduce_failure`, find the Phase 1 line:

```python
    _skill_block = render_skill_block(
        select_skills("bugfix", scan_installed_skills(repo_dir))
    )
```

Replace it with:

```python
    from ncdev.core.capability_ledger import recent_lessons

    _skill_block = render_skill_block(
        select_skills(
            "bugfix",
            scan_installed_skills(repo_dir),
            lessons=recent_lessons(),
        )
    )
```

`sentinel_reproduce` has no clean project handle, so `recent_lessons()` is called without a `project_name` — cross-project "hurt" lessons still apply to a bugfix session.

The existing `from ncdev.core.skill_selector import render_skill_block, select_skills` import a few lines above stays unchanged.

- [ ] **Step 2: Verify no regression**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — empty ledger → `recent_lessons()` returns `[]` → no behaviour change.

- [ ] **Step 3: Commit**

```bash
git add src/ncdev/sentinel_reproduce.py
git commit -m "feat(capability): sentinel bugfix skill selection consults ledger lessons"
```

---

## Task 5: End-to-end live-wiring test

**Files:**
- Create: `tests/test_core/test_capability_live_wiring.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_core/test_capability_live_wiring.py
"""End-to-end: a bad ledger record changes what a real session spawns,
and a 'hurt' lesson drops a skill from a real selection."""

from pathlib import Path

from ncdev import claude_session
from ncdev.core.capability_ledger import LedgerEntry, append_entry
from ncdev.core.capability_probe import scan_installed_skills
from ncdev.core.skill_selector import select_skills


def test_bad_ledger_demotes_a_real_claude_session(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    for i in range(4):
        append_entry(LedgerEntry(
            timestamp="t", project_name="p", run_id=f"r{i}", cycle=1,
            provider="anthropic_claude_code", model="opus",
            first_pass_success_rate=0.1,
        ))

    captured = {}

    def fake_popen(cmd, *a, **kw):
        captured["cmd"] = cmd
        raise OSError("stop — argv captured")

    monkeypatch.setattr(claude_session.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_session.subprocess, "Popen", fake_popen)

    # Default model is "auto" -> resolution runs -> gate consults the ledger.
    claude_session.run_claude_session("hi", cwd=Path("."))

    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "sonnet"


def test_clean_ledger_leaves_a_real_claude_session_on_opus(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    # No ledger entries at all.
    captured = {}

    def fake_popen(cmd, *a, **kw):
        captured["cmd"] = cmd
        raise OSError("stop")

    monkeypatch.setattr(claude_session.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_session.subprocess, "Popen", fake_popen)

    claude_session.run_claude_session("hi", cwd=Path("."))

    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "opus"


def test_hurt_lesson_drops_skill_with_real_selector(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    from ncdev.core.capability_ledger import recent_lessons

    append_entry(LedgerEntry(
        timestamp="t", project_name="p", run_id="r1", cycle=1,
        provider="openai_codex", model="gpt-5.5",
        capability_lessons=["frontend-design hurt — inconsistent output"],
    ))
    picked = select_skills(
        "greenfield_ui",
        ["frontend-design", "test-driven-development", "writing-plans"],
        lessons=recent_lessons(),
    )
    assert "frontend-design" not in picked
    assert "test-driven-development" in picked
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_live_wiring.py -v`
Expected: PASS (3 tests)

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/test_core/test_capability_live_wiring.py
git commit -m "test(capability): end-to-end live-wiring of gate + narrative bias"
```

---

## Done criteria (Phase 2b)

- `python -m pytest tests/ -q` is green.
- With ≥ 3 ledger cycles showing > 50 % failure for an auto-resolved Claude model, a *new* `run_claude_session` spawns the demoted alias — verified by inspecting the spawned argv.
- An empty ledger changes nothing — every existing test resolves exactly as in Phase 2a.
- A skill named in a "hurt" lesson is dropped from both the feature-builder and the Sentinel bugfix skill selection.
- The learning loop is now closed end to end: factory writes the ledger (Phase 2a) → resolution and skill selection read it back (Phase 2b).

## Deferred

- **`ai_provider.ClaudeCLIProvider.build_argv`** (`_resolve_claude_model`) is a secondary resolution path not on the primary session route; left un-gated. Wire it the same way (`resolve_model(..., ledger_entries=read_entries())`) if it later proves to be on a hot path.
- **Phase 2c — gated skill authoring** (spec §4.3): when the ledger shows a recurring hand-fix pattern, a dedicated Claude session uses `superpowers:writing-skills` to author, validate, and (human/Steward-gated) promote a new skill. Separate subsystem, separate plan.
- **Threshold tuning.** `_GATE_WINDOW`, `_GATE_MIN_SAMPLES`, `_GATE_FAIL_THRESHOLD` remain code constants; promoting them to `config.yaml` is worthwhile once real ledger data exists to tune against.
