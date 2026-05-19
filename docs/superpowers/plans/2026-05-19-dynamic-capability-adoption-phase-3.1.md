# Dynamic Capability Adoption — Phase 3.1 (Wire-Up & Cleanup) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two "built-but-not-wired" gaps found in a post-completion audit: the capability snapshot is never persisted to `.nc-dev/capabilities.json`, and `session_options.py` is an orphaned adapter no live code uses.

**Architecture:** Task 1 deletes the dead `session_options.py` adapter (the de-hardcoding wired `resolve_model()` directly into the session runners, bypassing the adapter) and de-couples the integration test from it. Task 2 adds `persist_capability_snapshot()` and calls it once at the start of `run_pipeline`, so every `ncdev full` / `factory` run writes `.nc-dev/capabilities.json` — delivering spec §3.1, the §5 snapshot guardrail, and the §8 criterion.

**Tech Stack:** Python 3.13, Pydantic v2, pytest. Builds on Phases 1–3.

**Scope:** Closes the two gaps in the spec `docs/superpowers/specs/2026-05-18-dynamic-capability-adoption-design.md` that the prior phases left unwired. Final cleanup of the dynamic-capability-adoption effort.

---

## File Structure

**Deleted files:**
- `src/ncdev/core/session_options.py` — orphaned adapter; no `src/` code imports it
- `tests/test_core/test_session_options.py` — its test

**Modified files:**
- `tests/test_core/test_capability_integration.py` — drop the `build_session_options` dependency
- `src/ncdev/core/capability_probe.py` — add `persist_capability_snapshot()`
- `src/ncdev/pipeline/engine.py` — call `persist_capability_snapshot()` at run start
- `tests/test_core/test_capability_probe.py` — test the new helper

---

## Task 1: Remove the dead `session_options.py` adapter

**Files:**
- Delete: `src/ncdev/core/session_options.py`, `tests/test_core/test_session_options.py`
- Modify: `tests/test_core/test_capability_integration.py`

`session_options.py` defines `SessionOptions` + `build_session_options()`. A repo-wide search confirms nothing under `src/` imports it — the Phase 1 de-hardcoding wired `resolve_model()` directly into `claude_session.py` / `ai_provider.py` / `ai_session.py`, bypassing the adapter. Only two test files reference it: its own test, and `test_capability_integration.py`.

- [ ] **Step 1: Rewrite the integration test to not use the adapter**

Replace the entire contents of `tests/test_core/test_capability_integration.py` with:

```python
"""End-to-end: a capability resolves to a concrete model with no edits."""

from ncdev.core.capability_probe import probe_toolchain, write_snapshot
from ncdev.core.capability_policy import resolve_model


def test_auto_capability_resolves_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/x")
    monkeypatch.setattr("ncdev.core.capability_probe._run_version", lambda _b: "1.2.3")
    monkeypatch.setattr("ncdev.core.capability_probe._run_help", lambda _b: "")
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)

    doc = probe_toolchain(workspace=tmp_path)
    out = tmp_path / ".nc-dev" / "capabilities.json"
    write_snapshot(doc, out)
    assert out.exists()

    # The claude snapshot in the doc resolves "auto" to a concrete model.
    claude_snap = next(s for s in doc.snapshots if s.provider == "anthropic_claude_code")
    model = resolve_model("anthropic_claude_code", "auto", claude_snap)
    assert model == "opus"
    assert "auto" not in model
```

- [ ] **Step 2: Delete the dead module and its test**

```bash
git rm src/ncdev/core/session_options.py tests/test_core/test_session_options.py
```

- [ ] **Step 3: Verify nothing else references it**

Run: `grep -rn "session_options" src tests --include="*.py"`
Expected: no output (zero matches).

If there is any match other than in already-deleted files, stop and report it — something still depends on the module.

- [ ] **Step 4: Run the affected test + full suite**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_integration.py -v`
Expected: PASS (1 test)

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no regressions (the deleted module had no `src/` consumers).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(capability): remove orphaned session_options adapter"
```

---

## Task 2: Persist the capability snapshot on every run

**Files:**
- Modify: `src/ncdev/core/capability_probe.py`
- Modify: `src/ncdev/pipeline/engine.py`
- Test: `tests/test_core/test_capability_probe.py` (append)

`probe_toolchain()` and `write_snapshot()` exist but nothing calls them in a live run. Add a one-call helper and invoke it at the start of `run_pipeline`.

- [ ] **Step 1: Append the failing test**

```python
# Append to tests/test_core/test_capability_probe.py
from ncdev.core.capability_probe import persist_capability_snapshot


def test_persist_capability_snapshot_writes_to_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: None)
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)

    path = persist_capability_snapshot(tmp_path)

    assert path == tmp_path / ".nc-dev" / "capabilities.json"
    assert path.is_file()
    loaded = load_snapshot(path)
    assert loaded is not None
    assert loaded.schema_id == "capability-snapshot.1"
```

(`load_snapshot` is already imported at the top of `tests/test_core/test_capability_probe.py` from earlier tasks; if it is not, add `from ncdev.core.capability_probe import load_snapshot`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_probe.py -k persist -v`
Expected: FAIL — `ImportError: cannot import name 'persist_capability_snapshot'`

- [ ] **Step 3: Add the helper**

Add to `src/ncdev/core/capability_probe.py`:

```python
def persist_capability_snapshot(workspace: Path) -> Path:
    """Probe the toolchain and write the snapshot to the workspace.

    Writes `<workspace>/.nc-dev/capabilities.json` and returns its path.
    """
    path = workspace / ".nc-dev" / "capabilities.json"
    write_snapshot(probe_toolchain(workspace=workspace), path)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_probe.py -k persist -v`
Expected: PASS

- [ ] **Step 5: Wire it into `run_pipeline`**

In `src/ncdev/pipeline/engine.py`, in `run_pipeline`, find the Phase 1 config-load block — it ends with the `state = PipelineRunState(...)` construction. Immediately AFTER the config-load block and BEFORE (or just after) `state = PipelineRunState(...)`, add a best-effort snapshot write:

```python
    # Persist the capability snapshot for this run — telemetry / the
    # spec's snapshot guardrail. Best-effort: never fail a run over it.
    try:
        from ncdev.core.capability_probe import persist_capability_snapshot

        persist_capability_snapshot(workspace)
    except Exception:  # noqa: BLE001
        pass
```

Match the surrounding indentation. Place it so it runs once per `run_pipeline` call (the factory calls `run_pipeline` each cycle, so each cycle refreshes the snapshot).

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no regressions. (`persist_capability_snapshot` is wrapped in `try/except`, and `probe_toolchain` never raises.)

- [ ] **Step 7: Commit**

```bash
git add src/ncdev/core/capability_probe.py src/ncdev/pipeline/engine.py tests/test_core/test_capability_probe.py
git commit -m "feat(capability): persist .nc-dev/capabilities.json on every pipeline run"
```

---

## Done criteria (Phase 3.1)

- `python -m pytest tests/ -q` is green.
- `grep -rn session_options src tests` returns nothing — the orphaned adapter is gone.
- `run_pipeline` writes `<workspace>/.nc-dev/capabilities.json` on every run (delivering spec §3.1, the §5 snapshot guardrail, and the §8 "written every run" criterion).
- No `src/` code defines a function that no `src/` code calls (the two audit findings are closed).

This closes the post-completion audit. The dynamic-capability-adoption effort has no remaining gaps.
