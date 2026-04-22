"""Tests for Phase H hooks — pre_bash_guard.evaluate()."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Import the hook module. Add scripts dir to path for import.
import sys
HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "ncdev-hooks"
sys.path.insert(0, str(HOOKS_DIR))
import pre_bash_guard  # noqa: E402


def _init_git_with_staged(path: Path, file_content: dict[str, str]) -> None:
    """Init a git repo at ``path`` with the given files staged (not committed)."""
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    # Seed a clean initial commit so diff --cached shows real changes
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(path), check=True)
    # Now stage the test files
    for rel, content in file_content.items():
        full = path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        subprocess.run(["git", "add", rel], cwd=str(path), check=True)


# ---------------------------------------------------------------------------
# Non-Bash tools always allowed
# ---------------------------------------------------------------------------


def test_non_bash_tool_is_allowed(tmp_path: Path):
    decision, reason = pre_bash_guard.evaluate("Edit", {"file_path": "x"}, cwd=str(tmp_path))
    assert decision == "allow"
    assert reason == ""


def test_empty_bash_command_allowed(tmp_path: Path):
    decision, _ = pre_bash_guard.evaluate("Bash", {"command": ""}, cwd=str(tmp_path))
    assert decision == "allow"


def test_non_git_commands_allowed(tmp_path: Path):
    decision, _ = pre_bash_guard.evaluate("Bash", {"command": "ls -la"}, cwd=str(tmp_path))
    assert decision == "allow"
    decision, _ = pre_bash_guard.evaluate("Bash", {"command": "pytest -q"}, cwd=str(tmp_path))
    assert decision == "allow"


# ---------------------------------------------------------------------------
# Conventional Commits enforcement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("good", [
    "feat: add login",
    "fix(auth): handle expired tokens",
    "test: cover edge case",
    "chore: bump deps",
    "refactor(api): split router",
    "docs: update readme",
    "perf: cache query",
])
def test_conventional_messages_pass(tmp_path: Path, good: str):
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    cmd = f'git commit -m "{good}"'
    decision, reason = pre_bash_guard.evaluate("Bash", {"command": cmd}, cwd=str(tmp_path))
    assert decision == "allow", reason


@pytest.mark.parametrize("bad", [
    "updated stuff",
    "WIP",
    "quick fix",
    "Added feature",
])
def test_non_conventional_messages_blocked(tmp_path: Path, bad: str):
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    cmd = f'git commit -m "{bad}"'
    decision, reason = pre_bash_guard.evaluate("Bash", {"command": cmd}, cwd=str(tmp_path))
    assert decision == "block"
    assert "Conventional Commits" in reason


def test_commit_with_F_file_flag_is_allowed(tmp_path: Path):
    """-F <file> — message is in a file; we can't introspect, allow."""
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    decision, _ = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -F message.txt'},
        cwd=str(tmp_path),
    )
    assert decision == "allow"


def test_commit_with_heredoc_is_allowed(tmp_path: Path):
    """HEREDOC substitution — can't parse the message cheaply, allow."""
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    cmd = '''git commit -m "$(cat <<'EOF'
feat: add heredoc support
EOF
)"'''
    decision, _ = pre_bash_guard.evaluate(
        "Bash", {"command": cmd}, cwd=str(tmp_path),
    )
    assert decision == "allow"


def test_commit_message_with_escaped_quotes_parses_correctly(tmp_path: Path):
    """Codex flag: escaped inner quotes broke the extractor. Verify fix."""
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    cmd = 'git commit -m "feat: handle \\"escaped\\" quotes"'
    decision, reason = pre_bash_guard.evaluate(
        "Bash", {"command": cmd}, cwd=str(tmp_path),
    )
    # The message starts with "feat:" so Conventional Commits accepts it
    assert decision == "allow", reason


def test_bad_message_with_escaped_quotes_still_blocked(tmp_path: Path):
    """Extractor must not be tricked into missing a bad message by escapes."""
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    cmd = 'git commit -m "updated \\"thing\\" again"'
    decision, reason = pre_bash_guard.evaluate(
        "Bash", {"command": cmd}, cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "Conventional Commits" in reason


# ---------------------------------------------------------------------------
# Prohibited patterns
# ---------------------------------------------------------------------------


def test_staged_content_with_todo_is_blocked(tmp_path: Path):
    _init_git_with_staged(tmp_path, {
        "src/app.py": "def run():\n    # TODO implement\n    pass\n",
    })
    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -m "feat: initial"'},
        cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "TODO" in reason
    assert "src/app.py" in reason


def test_regex_prohibited_pattern_matches_at_hook_level(tmp_path: Path, monkeypatch):
    """Codex R2: hook used substring only; regex entries from the
    verification contract never fired at commit time. Parity check."""
    config = tmp_path / "hooks.json"
    config.write_text('{"prohibited_patterns": ["except:\\\\s*pass"]}')
    monkeypatch.setenv("NCDEV_HOOKS_CONFIG", str(config))

    _init_git_with_staged(tmp_path, {
        "bad.py": "try:\n    x = 1\nexcept:    pass\n",
    })
    decision, reason = pre_bash_guard.evaluate(
        "Bash", {"command": 'git commit -m "feat: add thing"'},
        cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "except:" in reason or "pass" in reason


def test_staged_content_with_console_log_is_blocked(tmp_path: Path):
    _init_git_with_staged(tmp_path, {
        "frontend/app.tsx": 'export const x = () => { console.log("hi"); };\n',
    })
    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -m "feat: add thing"'},
        cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "console.log(" in reason


def test_clean_staged_content_passes(tmp_path: Path):
    _init_git_with_staged(tmp_path, {
        "src/app.py": "def run():\n    return 42\n",
        "tests/test_app.py": "def test_run():\n    assert run() == 42\n",
    })
    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -m "feat: add run"'},
        cwd=str(tmp_path),
    )
    assert decision == "allow", reason


def test_prohibited_in_existing_unchanged_file_is_ok(tmp_path: Path):
    # Pattern exists in HEAD but is not being added by the current diff — OK.
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path), check=True)
    (tmp_path / "old.py").write_text("# TODO from history\n")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init: legacy"], cwd=str(tmp_path), check=True)

    # New clean change staged
    (tmp_path / "new.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "new.py"], cwd=str(tmp_path), check=True)

    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -m "feat: add new"'},
        cwd=str(tmp_path),
    )
    assert decision == "allow", reason


# ---------------------------------------------------------------------------
# Force-push protection
# ---------------------------------------------------------------------------


def test_force_push_to_main_blocked(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NCDEV_ALLOW_FORCE_PUSH", raising=False)
    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": "git push --force origin main"},
        cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "Force-push" in reason
    assert "NCDEV_ALLOW_FORCE_PUSH" in reason


def test_force_push_to_feature_branch_allowed(tmp_path: Path):
    decision, _ = pre_bash_guard.evaluate(
        "Bash",
        {"command": "git push --force origin feature/my-branch"},
        cwd=str(tmp_path),
    )
    assert decision == "allow"


def test_force_push_override_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NCDEV_ALLOW_FORCE_PUSH", "1")
    decision, _ = pre_bash_guard.evaluate(
        "Bash",
        {"command": "git push --force origin main"},
        cwd=str(tmp_path),
    )
    assert decision == "allow"


# ---------------------------------------------------------------------------
# Project-level hook config override
# ---------------------------------------------------------------------------


def test_custom_prohibited_patterns_via_env(tmp_path: Path, monkeypatch):
    config = tmp_path / "hooks.json"
    config.write_text('{"prohibited_patterns": ["SECRET"]}')
    monkeypatch.setenv("NCDEV_HOOKS_CONFIG", str(config))

    # Stage content with SECRET, not TODO
    _init_git_with_staged(tmp_path, {
        "x.py": 'API_SECRET = "oops"\n',
    })
    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -m "feat: add key"'},
        cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "SECRET" in reason
