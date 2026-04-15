"""Unit tests for ncdev.ai_provider — registry, providers, and fallback."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ncdev.ai_provider import (
    AIProvider,
    ClaudeCLIProvider,
    CodexCLIProvider,
    get_provider,
    get_provider_with_fallback,
    reset_registry,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset the singleton registry before each test."""
    reset_registry()
    yield
    reset_registry()


# ------------------------------------------------------------------
# get_provider
# ------------------------------------------------------------------


class TestGetProvider:
    def test_returns_codex_provider(self):
        provider = get_provider("codex")
        assert isinstance(provider, CodexCLIProvider)

    def test_returns_claude_provider(self):
        provider = get_provider("claude")
        assert isinstance(provider, ClaudeCLIProvider)

    def test_raises_for_unknown(self):
        with pytest.raises(ValueError, match="Unknown AI provider 'gpt4'"):
            get_provider("gpt4")

    def test_singleton_returns_same_instance(self):
        a = get_provider("codex")
        b = get_provider("codex")
        assert a is b

    def test_default_is_codex(self):
        provider = get_provider()
        assert isinstance(provider, CodexCLIProvider)


# ------------------------------------------------------------------
# Provider interface
# ------------------------------------------------------------------


class TestProviderInterface:
    def test_codex_has_complete_method(self):
        provider = get_provider("codex")
        assert hasattr(provider, "complete")
        assert callable(provider.complete)

    def test_codex_has_is_available_method(self):
        provider = get_provider("codex")
        assert hasattr(provider, "is_available")
        assert callable(provider.is_available)

    def test_claude_has_complete_method(self):
        provider = get_provider("claude")
        assert hasattr(provider, "complete")
        assert callable(provider.complete)

    def test_claude_has_is_available_method(self):
        provider = get_provider("claude")
        assert hasattr(provider, "is_available")
        assert callable(provider.is_available)

    def test_both_are_ai_provider_subclasses(self):
        assert isinstance(get_provider("codex"), AIProvider)
        assert isinstance(get_provider("claude"), AIProvider)


# ------------------------------------------------------------------
# _build_shell_cmd
# ------------------------------------------------------------------


class TestBuildShellCmd:
    def test_codex_command_shape(self, tmp_path):
        provider = CodexCLIProvider()
        prompt_file = str(tmp_path / "prompt.txt")
        cmd = provider._build_shell_cmd(prompt_file)
        assert "codex exec --full-auto --skip-git-repo-check -" in cmd
        assert prompt_file in cmd

    def test_codex_ignores_tools(self, tmp_path):
        provider = CodexCLIProvider()
        prompt_file = str(tmp_path / "prompt.txt")
        cmd = provider._build_shell_cmd(prompt_file, tools=["Edit", "Write"])
        # Codex uses --full-auto which grants all tools; tools param is ignored
        assert "--allowedTools" not in cmd

    def test_claude_command_shape(self, tmp_path):
        provider = ClaudeCLIProvider()
        prompt_file = str(tmp_path / "prompt.txt")
        cmd = provider._build_shell_cmd(prompt_file)
        assert "claude -p - --output-format text" in cmd
        assert prompt_file in cmd

    def test_claude_includes_allowed_tools(self, tmp_path):
        provider = ClaudeCLIProvider()
        prompt_file = str(tmp_path / "prompt.txt")
        cmd = provider._build_shell_cmd(prompt_file, tools=["Edit", "Write", "Bash"])
        assert '--allowedTools "Edit,Write,Bash"' in cmd

    def test_claude_no_tools_flag_when_none(self, tmp_path):
        provider = ClaudeCLIProvider()
        prompt_file = str(tmp_path / "prompt.txt")
        cmd = provider._build_shell_cmd(prompt_file, tools=None)
        assert "--allowedTools" not in cmd


# ------------------------------------------------------------------
# get_provider_with_fallback
# ------------------------------------------------------------------


class TestGetProviderWithFallback:
    def test_returns_primary_when_available(self):
        with patch.object(CodexCLIProvider, "is_available", return_value=True):
            provider = get_provider_with_fallback("codex", "claude")
            assert isinstance(provider, CodexCLIProvider)

    def test_returns_fallback_when_primary_unavailable(self):
        with patch.object(CodexCLIProvider, "is_available", return_value=False):
            provider = get_provider_with_fallback("codex", "claude")
            assert isinstance(provider, ClaudeCLIProvider)

    def test_raises_for_unknown_primary(self):
        with pytest.raises(ValueError):
            get_provider_with_fallback("gpt4", "claude")

    def test_raises_for_unknown_fallback(self):
        with patch.object(CodexCLIProvider, "is_available", return_value=False):
            with pytest.raises(ValueError):
                get_provider_with_fallback("codex", "gpt4")
