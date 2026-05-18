# Dynamic Capability Adoption — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give NC Dev System's capability router *eyes* — a probe that inspects the installed `claude`/`codex` toolchain and a policy that resolves `auto` sentinels into concrete models/flags — so new models and CLI features flow into every build (greenfield, brownfield, bugfix) with zero code edits.

**Architecture:** Three new `src/ncdev/core/` modules — `capability_probe.py` (inspects the toolchain into the *existing* `CapabilitySnapshotDoc` schema), `capability_policy.py` (resolves `auto`/aliases to concrete models + Codex options), `session_options.py` (a `SessionOptions` adapter so the change does not ripple through every caller). Then de-hardcode the model literals in `claude_session.py`, `ai_provider.py`, `ai_session.py`, `cli.py`, and `core/config.py`, and add dynamic skill selection.

**Tech Stack:** Python 3.13, Pydantic v2, pytest. Builds on `core/capability_router.py`, `core/availability.py`, `core/models.py`, `core/config.py`.

**Scope:** This is Phase 1 of the spec `docs/superpowers/specs/2026-05-18-dynamic-capability-adoption-design.md`. Phase 2 (the self-learning ledger) gets its own plan once Phase 1 lands and there is real code to reference.

---

## File Structure

**New files:**
- `src/ncdev/core/capability_probe.py` — inspects the toolchain, produces `CapabilitySnapshotDoc`, atomic persistence to `.nc-dev/capabilities.json`
- `src/ncdev/core/capability_policy.py` — resolves `auto`/alias model requests + Codex advanced options
- `src/ncdev/core/session_options.py` — `SessionOptions` dataclass + `build_session_options()` adapter over `Resolved`
- `src/ncdev/core/skill_selector.py` — picks a skill set per work type from the probed inventory, renders a steering block
- `tests/test_core/test_capability_probe.py`
- `tests/test_core/test_capability_policy.py`
- `tests/test_core/test_session_options.py`
- `tests/test_core/test_skill_selector.py`
- `tests/test_core/test_no_model_literals.py` — guard test: literals stay gone

**Modified files:**
- `src/ncdev/claude_session.py:122` — `model` default `"claude-opus-4-6"` → `"auto"`, resolved
- `src/ncdev/ai_provider.py:289-299,330-341` — `CodexCLIProvider`/`ClaudeCLIProvider` `build_argv()`
- `src/ncdev/ai_session.py:182,209-260` — `effective_model` literal + `run_codex_session()` Codex options
- `src/ncdev/cli.py:316,384` — `full`/`factory` `--model` default → `"auto"`
- `src/ncdev/core/config.py:98-142,244-268` — `DEFAULT_CAPABILITY_CHAINS` + `NCDevConfig.providers` literals → sentinels
- `src/ncdev/pipeline/claude_executor.py` — wire dynamic skill selection into the feature-session prompt

---

## Task 1: Capability probe — provider version + model probe

**Files:**
- Create: `src/ncdev/core/capability_probe.py`
- Test: `tests/test_core/test_capability_probe.py`

The probe reuses the **existing** `ProviderCapabilitySnapshot` / `CapabilityDescriptor` / `CapabilitySnapshotDoc` models in `src/ncdev/core/models.py` (lines 425-453) — it does not define new snapshot types.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core/test_capability_probe.py
from ncdev.core.capability_probe import (
    CLAUDE_MODEL_ALIASES,
    detect_cli_version,
    probe_claude,
    probe_codex,
)
from ncdev.core.models import ProviderCapabilitySnapshot


def test_detect_cli_version_parses_semver():
    assert detect_cli_version("OpenAI Codex v0.130.0") == "0.130.0"
    assert detect_cli_version("1.2.3 (Claude Code)") == "1.2.3"
    assert detect_cli_version("no version here") == "unknown"


def test_probe_claude_when_binary_missing(monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: None)
    snap = probe_claude()
    assert isinstance(snap, ProviderCapabilitySnapshot)
    assert snap.provider == "anthropic_claude_code"
    assert snap.available is False
    assert "claude CLI not found on PATH" in snap.notes


def test_probe_claude_records_aliases_when_present(monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "1.2.3 (Claude Code)"
    )
    snap = probe_claude()
    assert snap.available is True
    assert snap.version == "1.2.3"
    assert snap.model == CLAUDE_MODEL_ALIASES[0]  # "opus" — the default alias


def test_probe_codex_records_version(monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "OpenAI Codex v0.130.0"
    )
    snap = probe_codex()
    assert snap.provider == "openai_codex"
    assert snap.available is True
    assert snap.version == "0.130.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_core/test_capability_probe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ncdev.core.capability_probe'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/core/capability_probe.py
"""Probe the installed toolchain — give the capability router eyes.

availability.py answers "is the binary there?"; this module answers
"what does it expose?" Results populate the existing
CapabilitySnapshotDoc schema in core/models.py.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from ncdev.core.models import (
    CapabilityDescriptor,
    ProviderCapabilitySnapshot,
)

# Claude CLI accepts these short aliases as --model values. "opus" is the
# default for planning/review/implementation. This is alias-based
# resolution — the CLIs expose no machine-readable model inventory.
CLAUDE_MODEL_ALIASES: tuple[str, ...] = ("opus", "sonnet", "haiku")

# Codex model name used when config requests "auto" and nothing is pinned.
CODEX_DEFAULT_MODEL: str = "gpt-5.5"

_SEMVER = re.compile(r"(\d+\.\d+\.\d+)")


def detect_cli_version(raw: str) -> str:
    """Extract a semver-ish version token from `<cli> --version` output."""
    match = _SEMVER.search(raw or "")
    return match.group(1) if match else "unknown"


def _run_version(binary: str) -> str:
    """Return raw `<binary> --version` stdout, or '' on any failure."""
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return (result.stdout or result.stderr or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def probe_claude() -> ProviderCapabilitySnapshot:
    """Inspect the installed `claude` CLI."""
    if shutil.which("claude") is None:
        return ProviderCapabilitySnapshot(
            provider="anthropic_claude_code",
            model=CLAUDE_MODEL_ALIASES[0],
            available=False,
            notes=["claude CLI not found on PATH"],
        )
    version = detect_cli_version(_run_version("claude"))
    return ProviderCapabilitySnapshot(
        provider="anthropic_claude_code",
        model=CLAUDE_MODEL_ALIASES[0],
        available=True,
        version=version,
        capabilities=CapabilityDescriptor(
            planning=True,
            implementation=True,
            code_review=True,
            mcp=True,
            subagents=True,
            hooks=True,
        ),
        notes=[f"accepted model aliases: {', '.join(CLAUDE_MODEL_ALIASES)}"],
    )


def probe_codex() -> ProviderCapabilitySnapshot:
    """Inspect the installed `codex` CLI."""
    if shutil.which("codex") is None:
        return ProviderCapabilitySnapshot(
            provider="openai_codex",
            model=CODEX_DEFAULT_MODEL,
            available=False,
            notes=["codex CLI not found on PATH"],
        )
    version = detect_cli_version(_run_version("codex"))
    return ProviderCapabilitySnapshot(
        provider="openai_codex",
        model=CODEX_DEFAULT_MODEL,
        available=True,
        version=version,
        capabilities=CapabilityDescriptor(
            implementation=True,
            test_implementation=True,
            shell_execution=True,
            reasoning_effort_levels=["low", "medium", "high"],
        ),
        notes=["reasoning via config key model_reasoning_effort"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_core/test_capability_probe.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_probe.py tests/test_core/test_capability_probe.py
git commit -m "feat(capability): probe claude/codex CLI version + model aliases"
```

---

## Task 2: Capability probe — skill/plugin inventory scan

**Files:**
- Modify: `src/ncdev/core/capability_probe.py`
- Test: `tests/test_core/test_capability_probe.py`

The probe scans for installed Claude skills so skill selection (Task 11) can pick from what is actually present. Sources scanned: `~/.claude/skills`, `~/.claude/plugins`, and `<workspace>/.claude/skills`.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_core/test_capability_probe.py
from pathlib import Path

from ncdev.core.capability_probe import scan_installed_skills


def test_scan_installed_skills_finds_skill_dirs(tmp_path, monkeypatch):
    home_skills = tmp_path / "home" / ".claude" / "skills"
    (home_skills / "systematic-debugging").mkdir(parents=True)
    (home_skills / "frontend-design").mkdir(parents=True)
    workspace = tmp_path / "proj"
    ws_skills = workspace / ".claude" / "skills"
    (ws_skills / "project-local-skill").mkdir(parents=True)
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path / "home")

    found = scan_installed_skills(workspace)

    assert "systematic-debugging" in found
    assert "frontend-design" in found
    assert "project-local-skill" in found


def test_scan_installed_skills_handles_missing_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path / "nope")
    assert scan_installed_skills(tmp_path / "also-nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_core/test_capability_probe.py::test_scan_installed_skills_finds_skill_dirs -v`
Expected: FAIL — `ImportError: cannot import name 'scan_installed_skills'`

- [ ] **Step 3: Write minimal implementation**

```python
# Add to src/ncdev/core/capability_probe.py — add `from pathlib import Path` to imports
def scan_installed_skills(workspace: Path | None = None) -> list[str]:
    """Return sorted, de-duplicated names of installed Claude skills.

    Scans ~/.claude/skills, ~/.claude/plugins, and <workspace>/.claude/skills.
    Each immediate subdirectory is treated as one skill. Missing
    directories are skipped silently — a missing scan source is normal,
    never an error.
    """
    roots: list[Path] = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".claude" / "plugins",
    ]
    if workspace is not None:
        roots.append(workspace / ".claude" / "skills")

    found: set[str] = set()
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for child in root.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    found.add(child.name)
        except OSError:
            continue
    return sorted(found)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_core/test_capability_probe.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_probe.py tests/test_core/test_capability_probe.py
git commit -m "feat(capability): scan installed Claude skills/plugins inventory"
```

---

## Task 3: Capability probe — `probe_toolchain()` + atomic persistence

**Files:**
- Modify: `src/ncdev/core/capability_probe.py`
- Test: `tests/test_core/test_capability_probe.py`

`probe_toolchain()` assembles the full `CapabilitySnapshotDoc`. `write_snapshot()` persists it atomically (temp-file + `os.replace`) so concurrent Sentinel fixes cannot read a half-written file. `load_snapshot()` is the fallback path when a fresh probe fails.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_core/test_capability_probe.py
from ncdev.core.capability_probe import (
    load_snapshot,
    probe_toolchain,
    write_snapshot,
)
from ncdev.core.models import CapabilitySnapshotDoc


def test_probe_toolchain_returns_snapshot_doc(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: None)
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)
    doc = probe_toolchain(workspace=tmp_path)
    assert isinstance(doc, CapabilitySnapshotDoc)
    assert doc.schema_id == "capability-snapshot.1"
    providers = {s.provider for s in doc.snapshots}
    assert providers == {"anthropic_claude_code", "openai_codex"}


def test_write_then_load_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: None)
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)
    doc = probe_toolchain(workspace=tmp_path)
    out = tmp_path / ".nc-dev" / "capabilities.json"

    write_snapshot(doc, out)

    assert out.exists()
    loaded = load_snapshot(out)
    assert loaded is not None
    assert loaded.schema_id == "capability-snapshot.1"
    assert len(loaded.snapshots) == 2


def test_load_snapshot_missing_returns_none(tmp_path):
    assert load_snapshot(tmp_path / "nope.json") is None


def test_load_snapshot_corrupt_returns_none(tmp_path):
    bad = tmp_path / "capabilities.json"
    bad.write_text("{not valid json", encoding="utf-8")
    assert load_snapshot(bad) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_core/test_capability_probe.py -k toolchain -v`
Expected: FAIL — `ImportError: cannot import name 'probe_toolchain'`

- [ ] **Step 3: Write minimal implementation**

```python
# Add to src/ncdev/core/capability_probe.py — add `import os` to imports
def probe_toolchain(workspace: Path | None = None) -> CapabilitySnapshotDoc:
    """Probe every provider into one CapabilitySnapshotDoc.

    Never raises — a failed sub-probe is recorded in that provider's
    snapshot.notes and the snapshot is marked unavailable.
    """
    snapshots = [probe_claude(), probe_codex()]
    skills = scan_installed_skills(workspace)
    for snap in snapshots:
        if snap.provider == "anthropic_claude_code" and snap.available:
            snap.notes.append(f"installed skills: {', '.join(skills) or '(none)'}")
    return CapabilitySnapshotDoc(
        generator="ncdev.core.capability_probe",
        snapshots=snapshots,
    )


def write_snapshot(doc: CapabilitySnapshotDoc, path: Path) -> None:
    """Persist the snapshot atomically.

    Writes to a unique temp file in the same directory, then os.replace()
    onto the target — an atomic rename on POSIX. A concurrent reader sees
    either the old complete file or the new complete file, never a
    partial write. Concurrent writers are last-writer-wins, which is
    safe: every prober inspects the same toolchain.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    tmp.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_snapshot(path: Path) -> CapabilitySnapshotDoc | None:
    """Load a persisted snapshot, or None if missing/corrupt."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return CapabilitySnapshotDoc.model_validate_json(raw)
    except ValueError:
        return None
```

Also add to the imports block at the top of the file:

```python
from ncdev.core.models import (
    CapabilityDescriptor,
    CapabilitySnapshotDoc,
    ProviderCapabilitySnapshot,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_core/test_capability_probe.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_probe.py tests/test_core/test_capability_probe.py
git commit -m "feat(capability): probe_toolchain + atomic snapshot persistence"
```

---

## Task 4: Capability policy — `resolve_model()`

**Files:**
- Create: `src/ncdev/core/capability_policy.py`
- Test: `tests/test_core/test_capability_policy.py`

Resolution order: **explicit pin → known alias → version-keyed table → provider default**. `"auto"` and `None` mean "resolve me"; anything else the CLI would accept verbatim is treated as a hard pin and passed through.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core/test_capability_policy.py
from ncdev.core.capability_policy import resolve_model
from ncdev.core.capability_probe import probe_claude, probe_codex


def _claude_snap(monkeypatch, available=True):
    monkeypatch.setattr(
        "ncdev.core.capability_probe.shutil.which",
        lambda b: "/usr/bin/claude" if available else None,
    )
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "1.2.3 (Claude Code)"
    )
    return probe_claude()


def test_auto_resolves_to_provider_default(monkeypatch):
    snap = _claude_snap(monkeypatch)
    assert resolve_model("anthropic_claude_code", "auto", snap) == "opus"


def test_none_resolves_to_provider_default(monkeypatch):
    snap = _claude_snap(monkeypatch)
    assert resolve_model("anthropic_claude_code", None, snap) == "opus"


def test_known_alias_passes_through(monkeypatch):
    snap = _claude_snap(monkeypatch)
    assert resolve_model("anthropic_claude_code", "sonnet", snap) == "sonnet"


def test_explicit_pin_always_wins(monkeypatch):
    snap = _claude_snap(monkeypatch)
    # An explicit, non-alias model string is a hard pin — never overridden.
    assert resolve_model("anthropic_claude_code", "claude-opus-4-7", snap) == "claude-opus-4-7"


def test_codex_auto_resolves_to_codex_default(monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "OpenAI Codex v0.130.0"
    )
    snap = probe_codex()
    assert resolve_model("openai_codex", "auto", snap) == "gpt-5.5"


def test_unavailable_provider_still_resolves_to_default(monkeypatch):
    snap = _claude_snap(monkeypatch, available=False)
    # Resolution must not depend on availability — availability is the
    # router's job; the policy only maps a request to a concrete string.
    assert resolve_model("anthropic_claude_code", "auto", snap) == "opus"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_core/test_capability_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ncdev.core.capability_policy'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/core/capability_policy.py
"""Resolve a model *request* into a concrete model string.

The CLIs expose no machine-readable model inventory, so resolution is
alias-based, with a version-keyed table as a pinning fallback. Order:
explicit pin > known alias > version table > provider default.
"""

from __future__ import annotations

from ncdev.core.capability_probe import (
    CLAUDE_MODEL_ALIASES,
    CODEX_DEFAULT_MODEL,
)
from ncdev.core.models import ProviderCapabilitySnapshot

# Sentinels that mean "resolve me" rather than "use this exact model".
_AUTO_SENTINELS: frozenset[str] = frozenset({"auto", "latest", ""})

_PROVIDER_DEFAULT: dict[str, str] = {
    "anthropic_claude_code": CLAUDE_MODEL_ALIASES[0],  # "opus"
    "openai_codex": CODEX_DEFAULT_MODEL,
}

# Pinning fallback: map a CLI version floor to a concrete model. Consulted
# only when an alias cannot satisfy a request. Seeded conservatively;
# extend as new generations ship. Phase 2 will keep this fresh from the
# ledger.
VERSION_MODEL_TABLE: dict[str, dict[str, str]] = {
    "anthropic_claude_code": {},
    "openai_codex": {},
}


def resolve_model(
    provider: str,
    requested: str | None,
    snapshot: ProviderCapabilitySnapshot,
) -> str:
    """Resolve `requested` to a concrete model string for `provider`.

    - None / "auto" / "latest" / ""  → the provider default alias
    - a known alias (opus/sonnet/...) → passed through
    - anything else                   → treated as an explicit pin, passed through
    """
    default = _PROVIDER_DEFAULT.get(provider, CLAUDE_MODEL_ALIASES[0])
    if requested is None or requested.strip().lower() in _AUTO_SENTINELS:
        return default
    # Explicit alias or explicit pin: the CLI accepts it verbatim.
    return requested.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_core/test_capability_policy.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_policy.py tests/test_core/test_capability_policy.py
git commit -m "feat(capability): resolve_model — auto/alias/pin resolution"
```

---

## Task 5: Capability policy — `resolve_codex_options()`

**Files:**
- Modify: `src/ncdev/core/capability_policy.py`
- Test: `tests/test_core/test_capability_policy.py`

The NC Dev config field is `reasoning_effort`; the Codex CLI takes reasoning via the config key `model_reasoning_effort`, passed as `-c model_reasoning_effort="<level>"`. This function does the translation, reviving the currently-dead config field.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_core/test_capability_policy.py
from ncdev.core.capability_policy import resolve_codex_options


def test_reasoning_effort_translates_to_codex_config_flag():
    args = resolve_codex_options({"reasoning_effort": "high"})
    assert args == ["-c", 'model_reasoning_effort="high"']


def test_empty_defaults_yield_no_args():
    assert resolve_codex_options({}) == []
    assert resolve_codex_options(None) == []


def test_unknown_defaults_keys_are_ignored():
    # base_url etc. are not CLI flags — must not leak into argv.
    args = resolve_codex_options({"base_url": "http://x", "reasoning_effort": "low"})
    assert args == ["-c", 'model_reasoning_effort="low"']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_core/test_capability_policy.py -k codex_options -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_codex_options'`

- [ ] **Step 3: Write minimal implementation**

```python
# Add to src/ncdev/core/capability_policy.py
def resolve_codex_options(defaults: dict[str, str] | None) -> list[str]:
    """Translate a provider's `defaults` dict into Codex CLI argv fragments.

    Only keys that map to a real Codex CLI option are emitted; unknown
    keys (e.g. base_url) are ignored. `reasoning_effort` maps to the
    Codex config key `model_reasoning_effort` via `-c key="value"`.
    """
    if not defaults:
        return []
    args: list[str] = []
    effort = defaults.get("reasoning_effort")
    if effort:
        args += ["-c", f'model_reasoning_effort="{effort}"']
    return args
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_core/test_capability_policy.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/capability_policy.py tests/test_core/test_capability_policy.py
git commit -m "feat(capability): resolve_codex_options — reasoning_effort translation"
```

---

## Task 6: Session options adapter

**Files:**
- Create: `src/ncdev/core/session_options.py`
- Test: `tests/test_core/test_session_options.py`

`capability_router.Resolved` carries only `(capability, provider, model, chain_position)`. Rather than expand it and ripple a contract change through every caller, `build_session_options()` converts `Resolved` + a snapshot + config into one `SessionOptions` struct that session entry points consume.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core/test_session_options.py
from ncdev.core.capability_router import Resolved
from ncdev.core.capability_probe import probe_toolchain
from ncdev.core.session_options import SessionOptions, build_session_options


def _snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/x")
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "1.2.3"
    )
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)
    return probe_toolchain(workspace=tmp_path)


def test_build_session_options_resolves_auto_model(tmp_path, monkeypatch):
    snap = _snapshot(tmp_path, monkeypatch)
    resolved = Resolved(
        capability="debugging",
        provider="anthropic_claude_code",
        model="auto",
        chain_position=0,
    )
    opts = build_session_options(resolved, snap)
    assert isinstance(opts, SessionOptions)
    assert opts.model == "opus"
    assert opts.extra_args == []


def test_build_session_options_codex_includes_reasoning(tmp_path, monkeypatch):
    snap = _snapshot(tmp_path, monkeypatch)
    resolved = Resolved(
        capability="backend_implementation",
        provider="openai_codex",
        model="auto",
        chain_position=0,
    )
    opts = build_session_options(
        resolved, snap, provider_defaults={"reasoning_effort": "high"}
    )
    assert opts.model == "gpt-5.5"
    assert opts.extra_args == ["-c", 'model_reasoning_effort="high"']


def test_build_session_options_pin_passes_through(tmp_path, monkeypatch):
    snap = _snapshot(tmp_path, monkeypatch)
    resolved = Resolved(
        capability="debugging",
        provider="anthropic_claude_code",
        model="claude-opus-4-7",
        chain_position=0,
    )
    opts = build_session_options(resolved, snap)
    assert opts.model == "claude-opus-4-7"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_core/test_session_options.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ncdev.core.session_options'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/core/session_options.py
"""Adapter: capability_router.Resolved -> SessionOptions.

Keeps the Resolved dataclass minimal. Session entry points consume one
SessionOptions struct instead of each growing new keyword arguments.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ncdev.core.capability_policy import resolve_codex_options, resolve_model
from ncdev.core.capability_router import Resolved
from ncdev.core.models import CapabilitySnapshotDoc, ProviderCapabilitySnapshot


@dataclass(frozen=True)
class SessionOptions:
    """Everything a session runner needs to start a provider session."""

    provider: str
    model: str
    extra_args: list[str] = field(default_factory=list)
    append_system_prompt_additions: str = ""


def _snapshot_for(
    doc: CapabilitySnapshotDoc, provider: str
) -> ProviderCapabilitySnapshot:
    for snap in doc.snapshots:
        if snap.provider == provider:
            return snap
    # Provider absent from the snapshot: synthesise an unavailable stub so
    # resolution still yields the provider default rather than crashing.
    return ProviderCapabilitySnapshot(provider=provider, model="auto", available=False)


def build_session_options(
    resolved: Resolved,
    snapshot: CapabilitySnapshotDoc,
    *,
    provider_defaults: dict[str, str] | None = None,
    append_system_prompt_additions: str = "",
) -> SessionOptions:
    """Turn a capability resolution into concrete session options."""
    provider_snap = _snapshot_for(snapshot, resolved.provider)
    model = resolve_model(resolved.provider, resolved.model, provider_snap)
    extra_args: list[str] = []
    if resolved.provider == "openai_codex":
        extra_args = resolve_codex_options(provider_defaults)
    return SessionOptions(
        provider=resolved.provider,
        model=model,
        extra_args=extra_args,
        append_system_prompt_additions=append_system_prompt_additions,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_core/test_session_options.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/session_options.py tests/test_core/test_session_options.py
git commit -m "feat(capability): SessionOptions adapter over Resolved"
```

---

## Task 7: De-hardcode `claude_session.py`

**Files:**
- Modify: `src/ncdev/claude_session.py:122`
- Test: `tests/test_no_model_literals.py` (created in Task 13; this task only changes source)

`run_claude_session` accepts `"auto"` and resolves it. The argv builder must never emit `auto` to the CLI — it resolves first.

- [ ] **Step 1: Change the default**

In `src/ncdev/claude_session.py`, change line 122 from:

```python
    model: str = "claude-opus-4-6",
```

to:

```python
    model: str = "auto",
```

Update the docstring at lines 149-150 from `Default: ``claude-opus-4-6``.` to: `Default ``"auto"`` — resolved to a concrete model via capability_policy at call time.`

- [ ] **Step 2: Resolve `auto` before building argv**

In `run_claude_session`, immediately after `tools_list = list(tools)` (line 203), insert:

```python
    # Resolve an "auto" model request to a concrete model. A non-auto
    # value is an explicit pin and passes through untouched.
    if model.strip().lower() in ("auto", "latest", ""):
        from ncdev.core.capability_probe import probe_claude
        from ncdev.core.capability_policy import resolve_model

        model = resolve_model("anthropic_claude_code", model, probe_claude())
```

(The import is local to avoid a module-load cycle and to keep the cost off the path when an explicit model is passed.)

- [ ] **Step 3: Write a behavioural test**

```python
# tests/test_claude_session.py — create if absent, else append
from ncdev import claude_session


def test_auto_model_is_resolved_not_passed_literally(monkeypatch):
    captured = {}

    def fake_popen(cmd, *a, **kw):
        captured["cmd"] = cmd
        raise RuntimeError("stop here — argv captured")

    monkeypatch.setattr(claude_session.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_session.subprocess, "Popen", fake_popen)

    claude_session.run_claude_session("hi", cwd=__import__("pathlib").Path("."))

    cmd = captured["cmd"]
    model_value = cmd[cmd.index("--model") + 1]
    assert model_value != "auto"
    assert model_value == "opus"
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest tests/test_claude_session.py::test_auto_model_is_resolved_not_passed_literally -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/claude_session.py tests/test_claude_session.py
git commit -m "refactor(capability): claude_session resolves auto model, no literal"
```

---

## Task 8: De-hardcode `ai_provider.py` build_argv

**Files:**
- Modify: `src/ncdev/ai_provider.py:296-299` (Codex) and `:336-338` (Claude)
- Test: `tests/test_ai_provider.py` (create if absent, else append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ai_provider.py
from ncdev.ai_provider import ClaudeCLIProvider, CodexCLIProvider


def test_claude_build_argv_no_hardcoded_literal_for_auto():
    argv = ClaudeCLIProvider().build_argv("p", model="auto")
    model = argv[argv.index("--model") + 1]
    assert model == "opus"


def test_claude_build_argv_pin_passes_through():
    argv = ClaudeCLIProvider().build_argv("p", model="claude-opus-4-7")
    assert argv[argv.index("--model") + 1] == "claude-opus-4-7"


def test_codex_build_argv_emits_reasoning_when_requested():
    argv = CodexCLIProvider().build_argv(
        "p", model="auto", codex_options=["-c", 'model_reasoning_effort="high"']
    )
    assert "-c" in argv
    assert 'model_reasoning_effort="high"' in argv
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ai_provider.py -v`
Expected: FAIL — `test_claude_build_argv_no_hardcoded_literal_for_auto` gets `"auto"`; `test_codex...` fails on unexpected `codex_options` kwarg.

- [ ] **Step 3: Fix `ClaudeCLIProvider.build_argv`**

In `src/ncdev/ai_provider.py`, replace lines 336-338:

```python
            "--model",
            model or "claude-opus-4-6",
```

with:

```python
            "--model",
            _resolve_claude_model(model),
```

And add this helper above the `CodexCLIProvider` class (after the `_CLIProviderMixin` definition):

```python
def _resolve_claude_model(model: str | None) -> str:
    """Resolve an auto/None model request to a concrete Claude model."""
    from ncdev.core.capability_policy import resolve_model
    from ncdev.core.capability_probe import probe_claude

    return resolve_model("anthropic_claude_code", model, probe_claude())
```

- [ ] **Step 4: Fix `CodexCLIProvider.build_argv`**

Replace the `CodexCLIProvider.build_argv` method (lines 282-299) with:

```python
    def build_argv(
        self,
        prompt: str,
        *,
        model: str | None = None,
        tools: list[str] | None = None,
        codex_options: list[str] | None = None,
    ) -> list[str]:
        from ncdev.core.capability_policy import resolve_model
        from ncdev.core.capability_probe import probe_codex

        argv = [
            self._cmd_name,
            "exec",
            "--full-auto",
            "--sandbox",
            "danger-full-access",
        ]
        argv += ["--model", resolve_model("openai_codex", model, probe_codex())]
        if codex_options:
            argv += list(codex_options)
        argv.append(prompt)
        return argv
```

Note: the base `AIProvider.build_argv` signature in `ai_provider.py` must also accept `codex_options` (add `codex_options: list[str] | None = None` as a keyword-only parameter to the abstract/base signature so the override is type-compatible).

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/test_ai_provider.py -v`
Expected: PASS (3 tests)

```bash
git add src/ncdev/ai_provider.py tests/test_ai_provider.py
git commit -m "refactor(capability): ai_provider build_argv resolves model + codex opts"
```

---

## Task 9: De-hardcode `ai_session.py`

**Files:**
- Modify: `src/ncdev/ai_session.py:182` and `run_codex_session` (lines ~209-260)
- Test: `tests/test_ai_session.py` (create if absent, else append)

- [ ] **Step 1: Fix the `effective_model` literal**

In `src/ncdev/ai_session.py`, replace line 182:

```python
    effective_model = model or "claude-opus-4-6"
```

with:

```python
    effective_model = model or "auto"
```

`run_claude_session` (Task 7) resolves `"auto"` itself, so passing it through is correct.

- [ ] **Step 2: Pass Codex options through `run_codex_session`**

In `run_codex_session`, replace the argv block:

```python
    cmd: list[str] = [
        "codex", "exec",
        "--full-auto",
        "--sandbox", "danger-full-access",
    ]
    if model:
        cmd += ["--model", model]
    if extra_args:
        cmd += list(extra_args)
    cmd.append(codex_prompt)
```

with:

```python
    from ncdev.core.capability_policy import resolve_model
    from ncdev.core.capability_probe import probe_codex

    cmd: list[str] = [
        "codex", "exec",
        "--full-auto",
        "--sandbox", "danger-full-access",
        "--model", resolve_model("openai_codex", model, probe_codex()),
    ]
    if codex_options:
        cmd += list(codex_options)
    if extra_args:
        cmd += list(extra_args)
    cmd.append(codex_prompt)
```

Add `codex_options: list[str] | None = None` as a keyword-only parameter to the `run_codex_session` signature (after `extra_args`).

- [ ] **Step 3: Write the test**

```python
# tests/test_ai_session.py
from pathlib import Path

from ncdev import ai_session


def test_run_codex_session_resolves_model_and_passes_options(monkeypatch):
    captured = {}

    def fake_popen(cmd, *a, **kw):
        captured["cmd"] = cmd
        raise RuntimeError("stop — argv captured")

    monkeypatch.setattr(ai_session.shutil, "which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(ai_session.subprocess, "Popen", fake_popen)

    ai_session.run_codex_session(
        "task", cwd=Path("."), model="auto",
        codex_options=["-c", 'model_reasoning_effort="high"'],
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "gpt-5.5"
    assert 'model_reasoning_effort="high"' in cmd
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest tests/test_ai_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/ai_session.py tests/test_ai_session.py
git commit -m "refactor(capability): ai_session resolves codex model + reasoning opts"
```

---

## Task 10: De-hardcode `cli.py` and `core/config.py`

**Files:**
- Modify: `src/ncdev/cli.py:316,384`
- Modify: `src/ncdev/core/config.py:98-142` (`DEFAULT_CAPABILITY_CHAINS`) and `:246-260` (`NCDevConfig.providers`)
- Test: `tests/test_core/test_config.py` (create if absent, else append)

- [ ] **Step 1: Change the CLI `--model` defaults**

In `src/ncdev/cli.py`, line 316 — change the `full` parser default:

```python
    full.add_argument("--model", default="auto",
                      help="Claude model: 'auto' (default, newest) or an explicit pin like claude-opus-4-7")
```

Line 384 — change the `factory` parser default:

```python
    factory.add_argument("--model", default="auto")
```

- [ ] **Step 2: Change `DEFAULT_CAPABILITY_CHAINS` literals to sentinels**

In `src/ncdev/core/config.py`, in `DEFAULT_CAPABILITY_CHAINS` (lines 98-142), replace every `CapabilityChoice` model value:
- `model="gpt-5.5"` → `model="auto"`
- `model="opus"` → `model="auto"`
- `model="anthropic/claude-opus-4-6"` (in the `openrouter` block) → **leave unchanged** — the OpenRouter API path is explicitly out of scope (spec §6).

- [ ] **Step 3: Change `NCDevConfig.providers` defaults to sentinels**

In `NCDevConfig.providers` default factory (lines 246-260): in the `anthropic_claude_code` and `openai_codex` `ProviderPreferenceConfig`, replace every `preferred_models` value (`"opus"`, `"gpt-5.5"`) with `"auto"`. Leave the `openrouter` provider's `preferred_models` unchanged (out of scope). Leave `defaults={"reasoning_effort": "high"}` unchanged — it is now consumed (Task 5).

- [ ] **Step 4: Write the test**

```python
# tests/test_core/test_config.py
from ncdev.core.config import DEFAULT_CAPABILITY_CHAINS, NCDevConfig


def test_capability_chains_carry_no_anthropic_or_codex_literals():
    for mode, chains in DEFAULT_CAPABILITY_CHAINS.items():
        for capability, choices in chains.items():
            for choice in choices:
                if choice.provider in ("anthropic_claude_code", "openai_codex"):
                    assert choice.model == "auto", (
                        f"{mode}/{capability} pins {choice.model!r}; expected 'auto'"
                    )


def test_provider_preferred_models_use_auto_sentinel():
    cfg = NCDevConfig()
    for name in ("anthropic_claude_code", "openai_codex"):
        for key, model in cfg.providers[name].preferred_models.items():
            assert model == "auto", f"{name}.{key} still pins {model!r}"
```

- [ ] **Step 5: Run the test and commit**

Run: `python -m pytest tests/test_core/test_config.py -v`
Expected: PASS (2 tests)

```bash
git add src/ncdev/cli.py src/ncdev/core/config.py tests/test_core/test_config.py
git commit -m "refactor(capability): config + cli defaults use auto sentinel"
```

---

## Task 11: Dynamic skill selection module

**Files:**
- Create: `src/ncdev/core/skill_selector.py`
- Test: `tests/test_core/test_skill_selector.py`

`skill_selector.py` picks skills per work type from the probed inventory and renders a steering block. Wiring it into the two session paths is Task 12.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core/test_skill_selector.py
from ncdev.core.skill_selector import (
    render_skill_block,
    select_skills,
    work_type_for,
)


INVENTORY = [
    "systematic-debugging", "frontend-design", "test-driven-development",
    "writing-plans", "verification-before-completion", "goal",
]


def test_greenfield_ui_selects_design_skills():
    picked = select_skills("greenfield_ui", INVENTORY)
    assert "frontend-design" in picked
    assert "goal" in picked


def test_bugfix_selects_systematic_debugging():
    picked = select_skills("bugfix", INVENTORY)
    assert "systematic-debugging" in picked


def test_select_skips_skills_not_installed():
    picked = select_skills("greenfield_ui", ["test-driven-development"])
    assert picked == ["test-driven-development"]


def test_render_skill_block_names_each_skill():
    block = render_skill_block(["systematic-debugging", "writing-plans"])
    assert "systematic-debugging" in block
    assert "writing-plans" in block


def test_render_empty_block_is_empty_string():
    assert render_skill_block([]) == ""


def test_work_type_for_classifies_inputs():
    assert work_type_for(is_brownfield=True, touches_frontend=False) == "brownfield"
    assert work_type_for(is_brownfield=False, touches_frontend=True) == "greenfield_ui"
    assert work_type_for(is_brownfield=False, touches_frontend=False) == "greenfield_backend"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_core/test_skill_selector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ncdev.core.skill_selector'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/core/skill_selector.py
"""Pick skills per work type from the probed inventory and render a
steering block. Replaces a hand-written, never-updated skill list with
a selection driven by what is actually installed.
"""

from __future__ import annotations

# Preferred skills per work type, in priority order. Only skills also
# present in the probed inventory are selected — security: NC Dev steers
# toward this vetted set, never toward arbitrary on-disk skills.
_WORK_TYPE_SKILLS: dict[str, list[str]] = {
    "greenfield_ui": [
        "writing-plans", "test-driven-development", "frontend-design",
        "goal", "verification-before-completion",
    ],
    "greenfield_backend": [
        "writing-plans", "test-driven-development",
        "goal", "verification-before-completion",
    ],
    "brownfield": [
        "writing-plans", "test-driven-development",
        "systematic-debugging", "verification-before-completion",
    ],
    "bugfix": [
        "systematic-debugging", "test-driven-development",
        "verification-before-completion",
    ],
}


def work_type_for(*, is_brownfield: bool, touches_frontend: bool) -> str:
    """Classify a feature build into a work type.

    Bugfix sessions pass the literal "bugfix" directly and do not call
    this — see Task 12.
    """
    if is_brownfield:
        return "brownfield"
    return "greenfield_ui" if touches_frontend else "greenfield_backend"


def select_skills(work_type: str, inventory: list[str]) -> list[str]:
    """Return the preferred skills for `work_type` that are installed."""
    preferred = _WORK_TYPE_SKILLS.get(work_type, _WORK_TYPE_SKILLS["brownfield"])
    installed = set(inventory)
    return [s for s in preferred if s in installed]


def render_skill_block(skills: list[str]) -> str:
    """Render a system-prompt block steering the session toward `skills`."""
    if not skills:
        return ""
    lines = [
        "## Available skills for this session",
        "",
        "These skills are installed and relevant to this work. Invoke "
        "the ones that apply:",
        "",
    ]
    lines += [f"- `{name}`" for name in skills]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_core/test_skill_selector.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/skill_selector.py tests/test_core/test_skill_selector.py
git commit -m "feat(capability): dynamic per-work-type skill selector module"
```

---

## Task 12: Wire skill selection into both session paths

**Files:**
- Modify: `src/ncdev/pipeline/claude_executor.py` (greenfield/brownfield feature sessions)
- Modify: `src/ncdev/sentinel_reproduce.py` (the Sentinel bugfix session)

Spec §3.5 requires skill selection to reach **both** the feature builder and the bugfix path — the bugfix session is the one that most needs `systematic-debugging`. The same `skill_selector` module feeds both; only the work-type differs.

- [ ] **Step 1: Wire `claude_executor.py`**

In `src/ncdev/pipeline/claude_executor.py`, locate where the per-feature `append_system_prompt` is assembled before the `run_claude_session` / `run_ai_session` call. Immediately before that call, insert:

```python
    from ncdev.core.capability_probe import scan_installed_skills
    from ncdev.core.skill_selector import (
        render_skill_block,
        select_skills,
        work_type_for,
    )

    # is_brownfield: True when the target repo pre-existed this run.
    # touches_frontend: True when the feature's files/spec involve UI.
    # Use the charter / feature metadata this module already holds; if a
    # signal is genuinely unavailable, pass False — the result is a safe
    # backend/brownfield skill set, never a crash.
    _work_type = work_type_for(
        is_brownfield=is_brownfield,
        touches_frontend=touches_frontend,
    )
    _skill_block = render_skill_block(
        select_skills(_work_type, scan_installed_skills(cwd))
    )
    if _skill_block:
        append_system_prompt = (
            f"{append_system_prompt}\n\n---\n\n{_skill_block}"
            if append_system_prompt else _skill_block
        )
```

If `is_brownfield` / `touches_frontend` are not already local variables, define them from the charter/feature objects in scope just above this block (e.g. `is_brownfield = bool(charter.target_repo_path)`; `touches_frontend` from the feature's file list or feature type). Keep the derivation to one line each.

- [ ] **Step 2: Wire the Sentinel bugfix session**

In `src/ncdev/sentinel_reproduce.py`, locate the `run_claude_session` / `run_ai_session` call and its `append_system_prompt` argument. Immediately before that call, insert:

```python
    from ncdev.core.capability_probe import scan_installed_skills
    from ncdev.core.skill_selector import render_skill_block, select_skills

    # Bugfix sessions always use the "bugfix" work type — they most
    # need systematic-debugging + reproduction skills.
    _skill_block = render_skill_block(
        select_skills("bugfix", scan_installed_skills(repo_path))
    )
    if _skill_block:
        append_system_prompt = (
            f"{append_system_prompt}\n\n---\n\n{_skill_block}"
            if append_system_prompt else _skill_block
        )
```

Use whatever local variable already holds the cloned repo path in place of `repo_path` if it is named differently.

- [ ] **Step 3: Verify no regressions**

Run: `python -m pytest tests/ -q`
Expected: PASS — the existing suite still green; both files import and run.

- [ ] **Step 4: Add a steering smoke test**

```python
# tests/test_core/test_skill_selector.py — append
from ncdev.core.skill_selector import render_skill_block, select_skills


def test_bugfix_steering_block_names_systematic_debugging():
    block = render_skill_block(
        select_skills("bugfix", ["systematic-debugging", "test-driven-development"])
    )
    assert "systematic-debugging" in block
```

Run: `python -m pytest tests/test_core/test_skill_selector.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/pipeline/claude_executor.py src/ncdev/sentinel_reproduce.py tests/test_core/test_skill_selector.py
git commit -m "feat(capability): steer feature + bugfix sessions to selected skills"
```

---

## Task 13: Integration test + literal guard

**Files:**
- Create: `tests/test_core/test_capability_integration.py`
- Create: `tests/test_no_model_literals.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_core/test_capability_integration.py
"""End-to-end: a capability resolves to a concrete model with no edits."""

from ncdev.core.capability_probe import probe_toolchain, write_snapshot
from ncdev.core.capability_router import Resolved
from ncdev.core.session_options import build_session_options


def test_auto_capability_resolves_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/x")
    monkeypatch.setattr("ncdev.core.capability_probe._run_version", lambda _b: "1.2.3")
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)

    doc = probe_toolchain(workspace=tmp_path)
    out = tmp_path / ".nc-dev" / "capabilities.json"
    write_snapshot(doc, out)
    assert out.exists()

    resolved = Resolved(
        capability="debugging", provider="anthropic_claude_code",
        model="auto", chain_position=0,
    )
    opts = build_session_options(resolved, doc)
    assert opts.model == "opus"
    assert "auto" not in opts.model
```

- [ ] **Step 2: Write the literal-guard test**

```python
# tests/test_no_model_literals.py
"""Guard: hardcoded model literals must not creep back into the
CLI-provider path. The OpenRouter API path is out of scope (spec §6)."""

import re
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src" / "ncdev"
_FORBIDDEN = re.compile(r'["\']claude-opus-4-6["\']|["\']gpt-5\.5["\']')
_GUARDED = [
    "claude_session.py",
    "ai_session.py",
    "cli.py",
]


def test_no_model_literals_in_guarded_files():
    offenders = []
    for rel in _GUARDED:
        text = (_SRC / rel).read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if _FORBIDDEN.search(line):
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, "hardcoded model literals found:\n" + "\n".join(offenders)


def test_capability_chains_have_no_cli_provider_literals():
    text = (_SRC / "core" / "config.py").read_text(encoding="utf-8")
    # gpt-5.5 / bare "opus" CapabilityChoice values must be gone; the
    # OpenRouter "anthropic/claude-opus-4-6" literal is allowed.
    assert 'model="gpt-5.5"' not in text
    assert 'model="opus"' not in text
```

Note: `ai_provider.py` keeps the OpenRouter default `"anthropic/claude-opus-4-6"` (out of scope), so it is intentionally not in `_GUARDED`.

- [ ] **Step 3: Run both tests**

Run: `python -m pytest tests/test_core/test_capability_integration.py tests/test_no_model_literals.py -v`
Expected: PASS

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: PASS — no regressions across the existing 702 tests plus the new ones.

- [ ] **Step 5: Commit**

```bash
git add tests/test_core/test_capability_integration.py tests/test_no_model_literals.py
git commit -m "test(capability): end-to-end resolution + model-literal guard"
```

---

## Done criteria (Phase 1)

- `python -m pytest tests/ -q` is green.
- `ncdev full --model auto` and `ncdev factory --model auto` resolve without a code edit; `ncdev fix` (no `--model` flag) inherits `auto`.
- `.nc-dev/capabilities.json` is written atomically and conforms to `capability-snapshot.1`.
- `reasoning_effort: high` in `.nc-dev/config.yaml` reaches `codex exec` as `-c model_reasoning_effort="high"`.
- No `claude-opus-4-6` / `gpt-5.5` literals remain in the guarded CLI-provider files (`test_no_model_literals.py` green).
- A bugfix session is steered toward `systematic-debugging`; a greenfield UI session toward design skills + `/goal`.

## Deferred within Phase 1

- **Runtime model-validation fallback** (spec §5). This plan implements the *resolution-order* fallback — pin → alias → version table → provider default (§3.2). It does **not** implement runtime detection of a CLI rejecting a resolved model mid-session (entitlement / rollout gap) and retrying with the default. That requires retry logic in the session runners and is a small follow-up task once the resolution path is in place. Until then, an explicit pin in `config.yaml` is the manual recovery path.
- **Generic `--help` flag scraping.** The probe records version, model aliases, skill inventory, and known Codex options — it does not parse the full `--help` flag surface, because nothing in Phase 1 consumes it. Add when a consumer exists.

Phase 2 (the cross-project capability ledger, metrics gate, and skill authoring) is a separate plan, written after Phase 1 lands.
