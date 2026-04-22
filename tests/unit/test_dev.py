from __future__ import annotations

from pathlib import Path

import pytest

from ncdev import dev
from ncdev import provider_dispatch
from ncdev.ai_provider import AIProvider, register_provider, reset_registry


class _FakeProvider(AIProvider):
    """Test double: records calls, returns a canned argv."""

    instances: list["_FakeProvider"] = []

    def __init__(self) -> None:
        self.short = "fake"
        self.argv_calls: list[tuple[str, str | None, list[str] | None]] = []
        type(self).instances.append(self)

    def is_available(self) -> bool:  # pragma: no cover - unused
        return True

    async def complete(self, prompt, timeout=300, cwd=None, tools=None):  # pragma: no cover
        return "ok"

    def build_argv(self, prompt, *, model=None, tools=None):
        self.argv_calls.append((prompt, model, tools))
        return ["fake-cli", "--prompt", prompt]

    @property
    def short_name(self) -> str:
        return self.short


def _install_fake(monkeypatch, short_name: str) -> type[_FakeProvider]:
    """Register a fake provider under the given short name and route all tasks to it."""

    class Fake(_FakeProvider):
        pass

    Fake.instances = []
    Fake.short = short_name  # type: ignore[attr-defined]

    register_provider(short_name, Fake)

    # Point every routing alias at the short name so any task_key → Fake.
    original_get_provider_for = provider_dispatch.get_provider_for

    def routed(task_key, **kwargs):
        return Fake()

    monkeypatch.setattr(provider_dispatch, "get_provider_for", routed)
    monkeypatch.setattr(provider_dispatch, "preferred_model_for", lambda *a, **k: None)
    return Fake


@pytest.fixture(autouse=True)
def _reset_registries():
    reset_registry()
    provider_dispatch.reset_cache()
    yield
    reset_registry()
    provider_dispatch.reset_cache()


def test_invoke_ai_planning_uses_dispatched_provider(monkeypatch, tmp_path: Path) -> None:
    Fake = _install_fake(monkeypatch, "fakeplanner")

    class FakeCompleted:
        returncode = 0
        stdout = "planned"
        stderr = ""

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompleted()

    monkeypatch.setattr(dev.subprocess, "run", fake_run)

    result = dev.invoke_ai_planning("project context", "Build feature X", tmp_path)

    assert result == "planned"
    # Fake provider's argv shape was used — no literal "claude" / "codex" assertions.
    assert calls and calls[0][0] == "fake-cli"
    # Fake provider recorded one build_argv call with the planning prompt.
    assert Fake.instances and Fake.instances[0].argv_calls
    prompt, _model, tools = Fake.instances[0].argv_calls[0]
    assert "build-instructions.md" in prompt
    assert tools == ["Read", "Write", "Glob", "Grep"]


def test_invoke_codex_parallel_uses_dispatched_provider(monkeypatch, tmp_path: Path) -> None:
    Fake = _install_fake(monkeypatch, "fakebuilder")

    class FakeCompleted:
        returncode = 0
        stdout = "built"
        stderr = ""

    monkeypatch.setattr(dev.subprocess, "run", lambda *a, **k: FakeCompleted())

    out = dev.invoke_codex_parallel("ctx", "task", tmp_path)
    assert out == "built"

    assert Fake.instances and Fake.instances[0].argv_calls
    _, _, tools = Fake.instances[0].argv_calls[0]
    assert tools == ["Edit", "Write", "Bash", "Read", "Glob", "Grep"]
