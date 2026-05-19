"""Guard: hardcoded model literals must not creep back into the
CLI-provider path. The OpenRouter API path is out of scope (spec section 6)."""

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
