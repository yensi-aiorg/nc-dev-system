# Dynamic Capability Adoption — Phase 3 (Deferred Items & Refinements) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clear every deferred / future-work item left by Phases 1, 2a, 2b, and 2c — runtime model-validation fallback, probe flag-surface capture, the last un-gated resolution path, config-driven gate thresholds, semantic lesson clustering, a lightweight Steward review of authored skills, and factory-end candidate surfacing.

**Architecture:** Eight small, independent refinements to existing modules, plus one new `skill_review.py`. Every change is additive and opt-in or default-safe — the 787 existing tests stay green.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, `difflib` (stdlib). Builds on all prior phases.

**Scope:** Closes the "Deferred / future work" sections of the four prior plans. After this, the dynamic-capability-adoption effort has no open items.

---

## Decisions & assumptions (review before executing)

1. **Model-rejection fallback is one step.** If an auto-resolved model is rejected by the CLI at runtime, the session retries exactly once with the next alias down the chain (`opus → sonnet → haiku`). One retry covers the common case (flagship not entitled → next tier); a second rejection fails the run with a clear error. Explicit pins are never retried.
2. **Rejection detection is keyword-based.** `is_model_rejection_error()` matches known phrases ("model not found", "do not have access", …) in the session error/output. Heuristic by necessity — the CLIs have no machine-readable error code.
3. **Semantic clustering uses `difflib`.** Lessons are grouped when `difflib.SequenceMatcher` ratio ≥ `0.8`. No embeddings / external deps. The threshold is a module constant.
4. **The Steward skill-review is advisory.** `ncdev skill-review` spawns a session that judges an authored `SKILL.md` and prints a verdict; it does not auto-block `skill-promote`. The human gate (Phase 2c) remains the decision point — the review just informs it.
5. **Config-driven gate thresholds read `.nc-dev/config.yaml` lazily.** No call site changes — `capability_policy` loads a `CapabilityGateConfig` itself (cached), defaulting to the current constant values.

---

## File Structure

**New files:**
- `src/ncdev/core/skill_review.py` — `SkillReview` model + `review_skill_candidate()`
- `tests/test_core/test_skill_review.py`
- `tests/test_core/test_phase3_refinements.py` — model-fallback + flag-scrape + factory-surface tests

**Modified files:**
- `src/ncdev/core/capability_policy.py` — `is_model_rejection_error()`, `next_alias_down()`, `CapabilityGateConfig` wiring
- `src/ncdev/claude_session.py` — model-rejection fallback retry
- `src/ncdev/core/capability_probe.py` — record supported CLI flags in the snapshot
- `src/ncdev/ai_provider.py` — `_resolve_claude_model` consults the ledger
- `src/ncdev/core/config.py` — `CapabilityGateConfig` model on `NCDevConfig`
- `src/ncdev/core/skill_candidate.py` — semantic clustering in `detect_skill_candidates`
- `src/ncdev/cli.py` — `ncdev skill-review` command
- `src/ncdev/factory.py` — surface skill candidates when the factory finishes
- `tests/test_core/test_capability_policy.py`, `test_capability_probe.py`, `test_skill_candidate.py` — appended tests

---

## Task 1: `is_model_rejection_error()` + `next_alias_down()`

**Files:**
- Modify: `src/ncdev/core/capability_policy.py`
- Test: `tests/test_core/test_capability_policy.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_core/test_capability_policy.py
from ncdev.core.capability_policy import is_model_rejection_error, next_alias_down


def test_is_model_rejection_error_matches_known_phrases():
    assert is_model_rejection_error("Error: model not found")
    assert is_model_rejection_error("you do not have access to this model")
    assert is_model_rejection_error(None, "invalid model: opus-9")
    assert not is_model_rejection_error("timed out after 600s")
    assert not is_model_rejection_error(None, None)


def test_next_alias_down_steps_through_the_chain():
    assert next_alias_down("anthropic_claude_code", "opus") == "sonnet"
    assert next_alias_down("anthropic_claude_code", "sonnet") == "haiku"
    assert next_alias_down("anthropic_claude_code", "haiku") is None
    # Explicit pins / unknown models have no chain position.
    assert next_alias_down("anthropic_claude_code", "claude-opus-4-7") is None
    assert next_alias_down("openai_codex", "gpt-5.5") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_policy.py -k "rejection or alias_down" -v`
Expected: FAIL — `ImportError: cannot import name 'is_model_rejection_error'`

- [ ] **Step 3: Write minimal implementation**

```python
# Add to src/ncdev/core/capability_policy.py
_MODEL_REJECTION_MARKERS: tuple[str, ...] = (
    "model not found",
    "does not exist",
    "do not have access",
    "invalid model",
    "unknown model",
    "not authorized",
)


def is_model_rejection_error(*text_parts: str | None) -> bool:
    """True if any text part looks like the CLI rejecting the model.

    Heuristic — the CLIs expose no machine-readable error code.
    """
    blob = " ".join(p for p in text_parts if p).lower()
    return any(marker in blob for marker in _MODEL_REJECTION_MARKERS)


def next_alias_down(provider: str, model: str) -> str | None:
    """The next alias one rung down `provider`'s chain, or None.

    Returns None when `model` is not a chain alias (e.g. an explicit
    pin) or is already the last rung.
    """
    chain = _ALIAS_CHAIN.get(provider, ())
    if model not in chain:
        return None
    idx = chain.index(model)
    return chain[idx + 1] if idx + 1 < len(chain) else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_policy.py -k "rejection or alias_down" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_policy.py tests/test_core/test_capability_policy.py
git commit -m "feat(capability): model-rejection detection + alias-chain step-down helper"
```

---

## Task 2: Model-rejection fallback retry in `run_claude_session`

**Files:**
- Modify: `src/ncdev/claude_session.py`
- Test: `tests/test_core/test_phase3_refinements.py`

When `run_claude_session` runs an auto-resolved model and the CLI rejects it, the run should retry once with the next alias down rather than hard-failing. To keep this cleanly testable, `run_claude_session` gains a private `_session_executor` seam — a callable `(model) -> ClaudeSessionResult` that, when supplied, replaces the real CLI spawn. Production never passes it (defaults to `None`); tests inject a fake.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core/test_phase3_refinements.py
from pathlib import Path

import pytest

from ncdev import claude_session
from ncdev.claude_session import ClaudeSessionResult


@pytest.fixture(autouse=True)
def _isolate_ledger(monkeypatch, tmp_path):
    """Every test in this file resolves against an empty ledger, so model
    resolution is deterministic regardless of any real ~/.ncdev state.
    Also makes the `claude` binary appear present so seam tests do not
    depend on the host PATH (the seam replaces the real spawn anyway)."""
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    monkeypatch.setattr(claude_session.shutil, "which", lambda _: "/usr/bin/x")


def test_model_rejection_triggers_one_fallback_retry():
    """An auto-resolved model the CLI rejects is retried once with the
    next alias down the chain."""
    calls = []

    def fake_executor(model):
        calls.append(model)
        if len(calls) == 1:  # first model (opus) rejected
            return ClaudeSessionResult(
                success=False, final_text="", exit_code=1,
                error="API error: you do not have access to this model",
            )
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    result = claude_session.run_claude_session(
        "hi", cwd=Path("."), _session_executor=fake_executor,
    )
    assert result.success is True
    assert calls == ["opus", "sonnet"]


def test_no_retry_when_session_succeeds():
    calls = []

    def fake_executor(model):
        calls.append(model)
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    claude_session.run_claude_session("hi", cwd=Path("."), _session_executor=fake_executor)
    assert calls == ["opus"]  # resolved once, no retry


def test_no_retry_for_explicit_pin():
    calls = []

    def fake_executor(model):
        calls.append(model)
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=1, error="model not found",
        )

    # An explicit model (not "auto") is a pin — never retried.
    claude_session.run_claude_session(
        "hi", cwd=Path("."), model="opus", _session_executor=fake_executor,
    )
    assert calls == ["opus"]


def test_no_retry_for_non_model_failure():
    calls = []

    def fake_executor(model):
        calls.append(model)
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=1, error="timed out after 600s",
        )

    claude_session.run_claude_session("hi", cwd=Path("."), _session_executor=fake_executor)
    assert calls == ["opus"]  # not a model-rejection error -> no retry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_phase3_refinements.py -k retry -v`
Expected: FAIL — `run_claude_session` has no `_session_executor` parameter

- [ ] **Step 3: Add the seam and fallback logic**

In `src/ncdev/claude_session.py`, edit `run_claude_session`:

1. Add two private keyword parameters at the end of its signature:
```python
    _session_executor=None,
    _model_fallback_done: bool = False,
```

2. As the very first statements of the function body, capture the auto flag and define the retry helper as a nested closure (it captures every parameter from the enclosing scope, so the recursive call needs no re-plumbing beyond what is shown):
```python
    _requested_was_auto = model.strip().lower() in ("auto", "latest", "")

    def _maybe_retry(result, resolved_model):
        """Retry once down the alias chain if the CLI rejected an auto model."""
        if result.success or _model_fallback_done or not _requested_was_auto:
            return result
        from ncdev.core.capability_policy import (
            is_model_rejection_error,
            next_alias_down,
        )
        if not is_model_rejection_error(result.error, result.final_text):
            return result
        fallback = next_alias_down("anthropic_claude_code", resolved_model)
        if fallback is None:
            return result
        return run_claude_session(
            prompt, cwd=cwd, tools=tools, model=fallback, timeout=timeout,
            permission_mode=permission_mode,
            append_system_prompt=append_system_prompt,
            include_codex_protocol=include_codex_protocol,
            max_budget_usd=max_budget_usd, log_path=log_path,
            on_event=on_event, extra_args=extra_args,
            settings_path=settings_path, enable_ncdev_hooks=enable_ncdev_hooks,
            retain_events=retain_events,
            _session_executor=_session_executor, _model_fallback_done=True,
        )
```
(Copy the exact parameter names from `run_claude_session`'s signature into that recursive call. The retry passes a concrete `model=fallback`, so `_requested_was_auto` recomputes `False` on the retry and `_model_fallback_done=True` — together they cap it at one retry.)

3. The model-resolution block already exists (`if model.strip().lower() in ("auto", ...)`). Immediately AFTER it, when the seam is in use, short-circuit the real CLI work:
```python
    if _session_executor is not None:
        return _maybe_retry(_session_executor(model), model)
```

4. The function's final statement is `return ClaudeSessionResult(...)` (the normal-completion path). Change that single `return` to:
```python
    return _maybe_retry(ClaudeSessionResult(...), model)
```
keeping the exact `ClaudeSessionResult(...)` arguments that were already there. (The earlier `return ClaudeSessionResult(...)` sites — claude-not-on-PATH, spawn failure, timeout — are left unchanged; a model rejection only surfaces on normal completion.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_phase3_refinements.py -k retry -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Confirm no regression, then commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — `_session_executor` defaults to `None`, so production behaviour is unchanged.

```bash
git add src/ncdev/claude_session.py tests/test_core/test_phase3_refinements.py
git commit -m "feat(capability): claude_session retries once down the alias chain on model rejection"
```

---

## Task 3: Record supported CLI flags in the capability snapshot

**Files:**
- Modify: `src/ncdev/core/capability_probe.py`
- Test: `tests/test_core/test_capability_probe.py` (append)

The probe records version, aliases, and skills but not the CLI flag surface. This task adds a `--help`-derived flag list to each provider snapshot's `notes` — useful when inspecting `.nc-dev/capabilities.json`.

- [ ] **Step 1: Append the failing test**

```python
# Append to tests/test_core/test_capability_probe.py
from ncdev.core.capability_probe import parse_supported_flags


def test_parse_supported_flags_extracts_long_flags():
    help_text = """Usage: claude [options]
      --model <name>      The model
      --permission-mode   Mode
      -p, --print         Print
    """
    flags = parse_supported_flags(help_text)
    assert "--model" in flags
    assert "--permission-mode" in flags
    assert "--print" in flags


def test_probe_claude_records_flags_in_notes(monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr("ncdev.core.capability_probe._run_version", lambda _b: "1.2.3")
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_help", lambda _b: "  --model x\n  --verbose y"
    )
    snap = probe_claude()
    assert any("flags:" in note and "--model" in note for note in snap.notes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_probe.py -k "supported_flags or records_flags" -v`
Expected: FAIL — `ImportError: cannot import name 'parse_supported_flags'`

- [ ] **Step 3: Write minimal implementation**

```python
# Add to src/ncdev/core/capability_probe.py
_LONG_FLAG = re.compile(r"--[a-z][a-z0-9-]+")


def parse_supported_flags(help_text: str) -> list[str]:
    """Sorted, de-duplicated long flags (`--xyz`) found in CLI help text."""
    return sorted(set(_LONG_FLAG.findall(help_text or "")))


def _run_help(binary: str) -> str:
    """Return raw `<binary> --help` stdout, or '' on any failure."""
    try:
        result = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return (result.stdout or result.stderr or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""
```

Then, in `probe_claude()`, after the snapshot is built for the available case, append a flags note. Insert this just before `probe_claude` returns its available-case `ProviderCapabilitySnapshot` — change the `notes=[...]` list to also include the flags. The simplest non-invasive way: build the snapshot, then append. Replace the available-case `return ProviderCapabilitySnapshot(...)` with:

```python
    snap = ProviderCapabilitySnapshot(
        provider="anthropic_claude_code",
        model=CLAUDE_MODEL_ALIASES[0],
        available=True,
        version=version,
        capabilities=CapabilityDescriptor(
            planning=True, implementation=True, code_review=True,
            mcp=True, subagents=True, hooks=True,
        ),
        notes=[f"accepted model aliases: {', '.join(CLAUDE_MODEL_ALIASES)}"],
    )
    flags = parse_supported_flags(_run_help("claude"))
    if flags:
        snap.notes.append(f"flags: {', '.join(flags)}")
    return snap
```

Apply the equivalent change to `probe_codex()` for the `codex` binary (build `snap`, append `f"flags: ..."` from `_run_help("codex")`, return `snap`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_probe.py -v`
Expected: PASS (all probe tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_probe.py tests/test_core/test_capability_probe.py
git commit -m "feat(capability): probe records supported CLI flags in the snapshot"
```

---

## Task 4: Wire the ledger gate into `ai_provider._resolve_claude_model`

**Files:**
- Modify: `src/ncdev/ai_provider.py`
- Test: `tests/test_ai_provider.py` (append)

`_resolve_claude_model` is the one remaining Claude-model resolution path that does not consult the ledger.

- [ ] **Step 1: Append the failing test**

```python
# Append to tests/test_ai_provider.py
def test_resolve_claude_model_demotes_on_bad_ledger(monkeypatch, tmp_path):
    from ncdev.core.capability_ledger import LedgerEntry, append_entry
    from ncdev.ai_provider import ClaudeCLIProvider

    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    for i in range(4):
        append_entry(LedgerEntry(
            timestamp="t", project_name="p", run_id=f"r{i}", cycle=1,
            provider="anthropic_claude_code", model="opus",
            first_pass_success_rate=0.1,
        ))
    argv = ClaudeCLIProvider().build_argv("p", model="auto")
    assert argv[argv.index("--model") + 1] == "sonnet"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ai_provider.py -k demotes_on_bad_ledger -v`
Expected: FAIL — model resolves to `opus` (ledger not consulted)

- [ ] **Step 3: Wire the ledger in**

In `src/ncdev/ai_provider.py`, replace the `_resolve_claude_model` function:

```python
def _resolve_claude_model(model: str | None) -> str:
    """Resolve an auto/None model request to a concrete Claude model."""
    from ncdev.core.capability_policy import resolve_model
    from ncdev.core.capability_probe import probe_claude
    from ncdev.core.capability_ledger import read_entries

    return resolve_model(
        "anthropic_claude_code", model, probe_claude(),
        ledger_entries=read_entries(),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ai_provider.py -v`
Expected: PASS (all ai_provider tests)

- [ ] **Step 5: Confirm no regression, then commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — empty ledger → unchanged behaviour.

```bash
git add src/ncdev/ai_provider.py tests/test_ai_provider.py
git commit -m "feat(capability): ai_provider _resolve_claude_model consults the ledger gate"
```

---

## Task 5: Config-driven gate thresholds

**Files:**
- Modify: `src/ncdev/core/config.py`, `src/ncdev/core/capability_policy.py`
- Test: `tests/test_core/test_capability_policy.py` (append)

- [ ] **Step 1: Append the failing test**

```python
# Append to tests/test_core/test_capability_policy.py
from ncdev.core.config import CapabilityGateConfig


def test_capability_gate_config_defaults_match_constants():
    cfg = CapabilityGateConfig()
    assert cfg.window == 5
    assert cfg.min_samples == 3
    assert cfg.fail_threshold == 0.5


def test_gate_uses_supplied_config(monkeypatch):
    snap = _claude_snap(monkeypatch)
    ledger = _led("opus", 0.4, n=4)  # 0.6 mean failure
    strict = CapabilityGateConfig(window=5, min_samples=3, fail_threshold=0.3)
    lenient = CapabilityGateConfig(window=5, min_samples=3, fail_threshold=0.9)
    assert _rm("anthropic_claude_code", "auto", snap,
               ledger_entries=ledger, gate_config=strict) == "sonnet"
    assert _rm("anthropic_claude_code", "auto", snap,
               ledger_entries=ledger, gate_config=lenient) == "opus"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_policy.py -k "gate_config or gate_uses" -v`
Expected: FAIL — `ImportError: cannot import name 'CapabilityGateConfig'`

- [ ] **Step 3: Add the config model**

In `src/ncdev/core/config.py`, add this model (near `CapabilityMatrixConfig`):

```python
class CapabilityGateConfig(BaseModel):
    """Thresholds for the capability metrics gate (Phase 2 feedback loop)."""

    window: int = 5            # consider at most this many recent entries
    min_samples: int = 3       # need at least this many before gating
    fail_threshold: float = 0.5  # mean failure rate above this -> demote
```

And add it as a field on `NCDevConfig` (alongside `capabilities`):

```python
    capability_gate: CapabilityGateConfig = Field(default_factory=CapabilityGateConfig)
```

- [ ] **Step 4: Make the gate use it**

In `src/ncdev/core/capability_policy.py`:

1. Add a cached loader (add `from functools import lru_cache` and `from pathlib import Path` to imports):

```python
@lru_cache(maxsize=1)
def _default_gate_config() -> "CapabilityGateConfig":
    """Load gate thresholds from .nc-dev/config.yaml, or defaults on any error."""
    from ncdev.core.config import CapabilityGateConfig, load_config

    try:
        return load_config(Path.cwd()).capability_gate
    except Exception:  # noqa: BLE001
        from ncdev.core.config import CapabilityGateConfig as _C
        return _C()
```

2. Change `_gated_model` to take an optional config and use its fields instead of the `_GATE_*` constants:

```python
def _gated_model(provider: str, model: str, ledger_entries: list, gate_config=None) -> str:
    """Demote `model` one alias rung if its recent track record is bad."""
    if gate_config is None:
        gate_config = _default_gate_config()
    chain = _ALIAS_CHAIN.get(provider, ())
    if model not in chain:
        return model
    idx = chain.index(model)
    if idx + 1 >= len(chain):
        return model
    recent = [
        e for e in ledger_entries
        if e.provider == provider and e.model == model
    ][-gate_config.window:]
    if len(recent) < gate_config.min_samples:
        return model
    mean_failure = sum(1.0 - e.first_pass_success_rate for e in recent) / len(recent)
    if mean_failure > gate_config.fail_threshold:
        return chain[idx + 1]
    return model
```

3. Add a `gate_config` keyword to `resolve_model` and pass it through:

```python
def resolve_model(
    provider: str,
    requested: str | None,
    snapshot: ProviderCapabilitySnapshot,
    *,
    ledger_entries: list | None = None,
    gate_config=None,
) -> str:
```

and inside it change `resolved = _gated_model(provider, resolved, ledger_entries)` to
`resolved = _gated_model(provider, resolved, ledger_entries, gate_config)`.

The old `_GATE_WINDOW` / `_GATE_MIN_SAMPLES` / `_GATE_FAIL_THRESHOLD` constants may be deleted (now superseded by `CapabilityGateConfig` defaults) — remove them and any remaining reference.

- [ ] **Step 5: Run tests + confirm no regression, then commit**

Run: `.venv/bin/python -m pytest tests/test_core/test_capability_policy.py -v` — expect PASS.
Run: `.venv/bin/python -m pytest tests/ -q` — expect no regressions.

```bash
git add src/ncdev/core/config.py src/ncdev/core/capability_policy.py tests/test_core/test_capability_policy.py
git commit -m "feat(capability): config-driven metrics-gate thresholds"
```

---

## Task 6: Semantic clustering in `detect_skill_candidates`

**Files:**
- Modify: `src/ncdev/core/skill_candidate.py`
- Test: `tests/test_core/test_skill_candidate.py` (append)

- [ ] **Step 1: Append the failing test**

```python
# Append to tests/test_core/test_skill_candidate.py
def test_near_identical_lessons_cluster_into_one_candidate():
    entries = [
        _entry("r1", ["had to hand-fix the pagination helper"]),
        _entry("r2", ["had to hand fix the pagination helper"]),   # no hyphen
        _entry("r3", ["had to hand-fix the pagination helpers"]),  # plural
    ]
    candidates = detect_skill_candidates(entries, threshold=3)
    assert len(candidates) == 1
    assert candidates[0].occurrences == 3


def test_clearly_different_lessons_do_not_cluster():
    entries = [
        _entry("r1", ["pagination helper keeps breaking"]),
        _entry("r2", ["authentication tokens expire too early"]),
        _entry("r3", ["the database migration ordering is wrong"]),
    ]
    assert detect_skill_candidates(entries, threshold=3) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_candidate.py -k "cluster" -v`
Expected: FAIL — near-identical lessons are counted separately (exact-match), so no candidate reaches threshold 3

- [ ] **Step 3: Replace exact-match grouping with similarity clustering**

In `src/ncdev/core/skill_candidate.py`, add `from difflib import SequenceMatcher` to the imports, add the threshold constant, and replace `detect_skill_candidates` with a clustering version (keep `SkillCandidate` and `_normalise` unchanged):

```python
# Lessons whose normalised text is at least this similar are one cluster.
_SIMILARITY_THRESHOLD = 0.8


def _similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= _SIMILARITY_THRESHOLD


def detect_skill_candidates(
    entries: list[LedgerEntry],
    *,
    threshold: int = 3,
) -> list[SkillCandidate]:
    """Return ledger patterns recurring `>= threshold` times.

    Lessons are clustered by text similarity (difflib ratio >=
    _SIMILARITY_THRESHOLD), so near-identical phrasings count together.
    Each cluster keeps its first-seen normalised lesson as the pattern.
    """
    clusters: list[dict] = []  # {key, examples: list[str], projects: set[str]}
    for entry in entries:
        for lesson in entry.capability_lessons:
            key = _normalise(lesson)
            if not key:
                continue
            match = next((c for c in clusters if _similar(c["key"], key)), None)
            if match is None:
                clusters.append(
                    {"key": key, "examples": [lesson], "projects": {entry.project_name}}
                )
            else:
                match["examples"].append(lesson)
                match["projects"].add(entry.project_name)

    candidates = [
        SkillCandidate(
            pattern=c["key"],
            occurrences=len(c["examples"]),
            example_lessons=c["examples"],
            projects=sorted(c["projects"]),
        )
        for c in clusters
        if len(c["examples"]) >= threshold
    ]
    candidates.sort(key=lambda c: c.occurrences, reverse=True)
    return candidates
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_candidate.py -v`
Expected: PASS (all skill-candidate tests — the 4 Phase 2c tests still pass; identical lessons trivially cluster)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/skill_candidate.py tests/test_core/test_skill_candidate.py
git commit -m "feat(capability): cluster near-identical lessons in candidate detection"
```

---

## Task 7: `review_skill_candidate()` — lightweight Steward review

**Files:**
- Create: `src/ncdev/core/skill_review.py`
- Test: `tests/test_core/test_skill_review.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core/test_skill_review.py
from ncdev.core.skill_review import SkillReview, review_skill_candidate


def test_review_parses_session_verdict(tmp_path):
    skill_dir = tmp_path / "retry-helper"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# retry-helper\nteaches retries", encoding="utf-8")

    def fake_runner(prompt, *, cwd, **kwargs):
        assert "retry-helper" in (skill_dir / "SKILL.md").read_text(encoding="utf-8")

        class _R:
            success = True
            final_text = '{"approved": true, "reasoning": "clear and well-scoped"}'
        return _R()

    review = review_skill_candidate(skill_dir, run_session=fake_runner)
    assert isinstance(review, SkillReview)
    assert review.approved is True
    assert "well-scoped" in review.reasoning


def test_review_handles_fenced_json(tmp_path):
    skill_dir = tmp_path / "s"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# s", encoding="utf-8")

    def fake_runner(prompt, *, cwd, **kwargs):
        class _R:
            success = True
            final_text = '```json\n{"approved": false, "reasoning": "too vague"}\n```'
        return _R()

    review = review_skill_candidate(skill_dir, run_session=fake_runner)
    assert review.approved is False
    assert review.reasoning == "too vague"


def test_review_missing_skill_md_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        review_skill_candidate(tmp_path / "nope", run_session=lambda *a, **k: None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_review.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ncdev.core.skill_review'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/core/skill_review.py
"""Lightweight Steward review of an authored skill candidate.

Spawns a Claude session that reads a candidate SKILL.md and returns a
structured pass/fail verdict. Advisory — it informs the human promote
gate, it does not replace it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class SkillReview(BaseModel):
    """A Steward verdict on a candidate skill."""

    approved: bool
    reasoning: str = ""


def _build_review_prompt(skill_md: str) -> str:
    return (
        "You are reviewing a candidate Claude skill before it is promoted "
        "into the live skill library. Here is its SKILL.md:\n\n"
        f"---\n{skill_md}\n---\n\n"
        "Judge whether it is a sound, well-scoped, clearly-written skill "
        "that would genuinely help an agent. Reply with a SINGLE JSON "
        'object, no prose around it: {"approved": <true|false>, '
        '"reasoning": "<one or two sentences>"}'
    )


def review_skill_candidate(
    skill_dir: Path,
    *,
    run_session: Callable[..., Any] | None = None,
) -> SkillReview:
    """Spawn a session that reviews the SKILL.md in `skill_dir`.

    Raises FileNotFoundError if there is no SKILL.md. `run_session`
    defaults to claude_session.run_claude_session; tests inject a fake.
    """
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.is_file():
        raise FileNotFoundError(f"No SKILL.md in {skill_dir}")
    if run_session is None:
        from ncdev.claude_session import run_claude_session

        run_session = run_claude_session

    prompt = _build_review_prompt(skill_md_path.read_text(encoding="utf-8"))
    result = run_session(prompt, cwd=skill_dir)
    text = getattr(result, "final_text", "") or ""
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    try:
        data = json.loads(cleaned)
        return SkillReview(approved=bool(data["approved"]),
                           reasoning=str(data.get("reasoning", "")))
    except (ValueError, KeyError, TypeError):
        return SkillReview(
            approved=False,
            reasoning="Could not parse a verdict from the review session.",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_review.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/skill_review.py tests/test_core/test_skill_review.py
git commit -m "feat(capability): review_skill_candidate — lightweight Steward skill review"
```

---

## Task 8: `ncdev skill-review` CLI command

**Files:**
- Modify: `src/ncdev/cli.py`
- Test: `tests/test_core/test_skill_authoring_cli.py` (append)

- [ ] **Step 1: Append the failing test**

```python
# Append to tests/test_core/test_skill_authoring_cli.py
def test_skill_review_command_parses():
    args = build_parser().parse_args(["skill-review", "--name", "retry-helper"])
    assert args.command == "skill-review" and args.name == "retry-helper"


def test_skill_review_missing_candidate_returns_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    assert main(["skill-review", "--name", "nope"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_authoring_cli.py -k skill_review -v`
Expected: FAIL — argparse rejects `skill-review`

- [ ] **Step 3: Add the subparser and dispatch**

In `build_parser()`, after the `skill-promote` subparser, add:

```python
    skill_review = sub.add_parser(
        "skill-review",
        help="Run a lightweight Steward review of a pending authored skill",
    )
    skill_review.add_argument("--name", required=True, help="Pending skill name to review")
```

In `main()`, after the `skill-promote` dispatch block, add:

```python
    if args.command == "skill-review":
        from ncdev.core.skill_author import candidate_skills_dir
        from ncdev.core.skill_review import review_skill_candidate

        skill_dir = candidate_skills_dir() / args.name
        try:
            review = review_skill_candidate(skill_dir)
        except FileNotFoundError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        verdict = "[green]APPROVED[/green]" if review.approved else "[yellow]NOT APPROVED[/yellow]"
        console.print(f"Steward review of '{args.name}': {verdict}")
        console.print(f"  {review.reasoning}")
        return 0 if review.approved else 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_authoring_cli.py -v`
Expected: PASS (all skill-authoring CLI tests)

- [ ] **Step 5: Confirm no regression, then commit**

Run: `.venv/bin/python -m pytest tests/ -q` — expect no regressions.

```bash
git add src/ncdev/cli.py tests/test_core/test_skill_authoring_cli.py
git commit -m "feat(cli): skill-review — lightweight Steward review command"
```

---

## Task 9: Surface skill candidates when the factory finishes

**Files:**
- Modify: `src/ncdev/factory.py`
- Test: `tests/test_core/test_phase3_refinements.py` (append)

After a factory run, print any skill candidates the ledger now shows — so the human knows to consider `ncdev skill-author`.

- [ ] **Step 1: Append the failing test**

```python
# Append to tests/test_core/test_phase3_refinements.py
def test_surface_skill_candidates_prints_detected_patterns(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    from ncdev.core.capability_ledger import LedgerEntry, append_entry
    for i in range(3):
        append_entry(LedgerEntry(
            timestamp="t", project_name="demo", run_id=f"r{i}", cycle=1,
            provider="openai_codex", model="gpt-5.5",
            capability_lessons=["recurring gap in retry handling"],
        ))
    from ncdev.factory import surface_skill_candidates
    surface_skill_candidates()
    out = capsys.readouterr().out
    assert "recurring gap in retry handling" in out
    assert "skill-author" in out  # the hint to act on it


def test_surface_skill_candidates_silent_when_none(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    from ncdev.factory import surface_skill_candidates
    surface_skill_candidates()
    assert capsys.readouterr().out == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_phase3_refinements.py -k surface_skill -v`
Expected: FAIL — `ImportError: cannot import name 'surface_skill_candidates'`

- [ ] **Step 3: Add the function and call it**

In `src/ncdev/factory.py`, add this module-level function:

```python
def surface_skill_candidates() -> None:
    """Print recurring skill candidates from the ledger. Silent when none."""
    from ncdev.core.capability_ledger import read_entries
    from ncdev.core.skill_candidate import detect_skill_candidates

    candidates = detect_skill_candidates(read_entries())
    if not candidates:
        return
    console.print(
        "[bold]Skill candidates detected[/bold] — recurring patterns in the "
        "capability ledger:"
    )
    for c in candidates:
        console.print(f"  - {c.pattern}  [dim](x{c.occurrences})[/dim]")
    console.print(
        "  Consider authoring a skill: "
        "[cyan]ncdev skill-author --name <name> --pattern \"<pattern>\"[/cyan]"
    )
```

Then call it once when a factory run finishes. In `run_factory` (the top-level entry that returns the `FactoryRunState`), find where it returns the state from the cycle loop and call `surface_skill_candidates()` immediately before that return. If `run_factory` ends with `return _run_factory_cycle_loop(...)`, change it to:

```python
    state = _run_factory_cycle_loop(...)  # keep the existing arguments
    surface_skill_candidates()
    return state
```

If `run_factory` already binds the loop result to a variable before returning, just add the `surface_skill_candidates()` call on the line before `return`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_phase3_refinements.py -k surface_skill -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full suite, then commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no regressions.

```bash
git add src/ncdev/factory.py tests/test_core/test_phase3_refinements.py
git commit -m "feat(capability): surface skill candidates when a factory run finishes"
```

---

## Done criteria (Phase 3)

- `python -m pytest tests/ -q` is green.
- A model the CLI rejects at runtime triggers exactly one retry down the alias chain.
- `.nc-dev/capabilities.json` records each provider's supported CLI flags.
- `ai_provider._resolve_claude_model` consults the ledger gate (no resolution path is un-gated).
- Gate thresholds are read from `.nc-dev/config.yaml` (`capability_gate:` section), defaulting to 5 / 3 / 0.5.
- Near-identical recurring lessons cluster into one skill candidate.
- `ncdev skill-review --name X` prints a Steward verdict on a pending skill.
- A finished factory run prints detected skill candidates with a hint to author them.

Every "Deferred / future work" item from Phases 1, 2a, 2b, and 2c is now closed. The dynamic-capability-adoption effort is complete.
