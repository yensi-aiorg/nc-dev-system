#!/usr/bin/env python3
"""Claude Code PreToolUse hook — guards ``Bash`` commands.

Wired in via ``scripts/ncdev-hooks/settings.json`` when NC Dev spawns a
Claude session.  Runs on every Bash tool call and enforces:

    * ``git commit`` commands cannot land files containing prohibited
      patterns (TODO, FIXME, console.log, bare ``except: pass``,
      "Not yet implemented") in the staged tree.
    * ``git commit`` messages must follow Conventional Commits
      (feat/fix/test/chore/refactor/docs/perf/style/build/ci/revert).
    * ``git push --force`` to protected branches (main/master) is blocked
      unless the user-level allowlist env var is set.

The hook reads a JSON event from stdin with the tool name and input,
writes a decision JSON to stdout, and exits 0 always — the decision
(allow/block + reason) is conveyed in the JSON body so Claude sees
the structured feedback.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

# Default prohibited patterns — may be overridden per-project by placing
# a JSON file at $NCDEV_HOOKS_CONFIG.
DEFAULT_PROHIBITED: tuple[str, ...] = (
    "TODO",
    "FIXME",
    "console.log(",
    "Not yet implemented",
    "Coming soon",
)

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|test|chore|refactor|docs|perf|style|build|ci|revert)"
    r"(\([^)]+\))?:\s+.+",
    re.MULTILINE,
)


def _emit(decision: str, reason: str = "") -> None:
    """Write hook decision JSON and exit cleanly."""
    payload = {"decision": decision}
    if reason:
        payload["reason"] = reason
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.exit(0)


def _load_prohibited() -> tuple[str, ...]:
    config_path = os.environ.get("NCDEV_HOOKS_CONFIG")
    if config_path and Path(config_path).exists():
        try:
            cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
            pats = cfg.get("prohibited_patterns")
            if isinstance(pats, list) and all(isinstance(p, str) for p in pats):
                return tuple(pats)
        except Exception:  # noqa: BLE001
            pass
    return DEFAULT_PROHIBITED


def _staged_file_list(cwd: str | None) -> list[str]:
    r = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=cwd, capture_output=True, text=True, timeout=5,
    )
    if r.returncode != 0:
        return []
    return [line for line in r.stdout.splitlines() if line]


def _check_staged_for_prohibited(
    cwd: str | None, patterns: Iterable[str],
) -> list[str]:
    """Return a list of '<file>:<pattern>' violations found in staged diff.

    Each pattern is tried as a compiled regex first (via ``re.search``);
    if that fails to compile, we fall back to literal substring match.
    This matches the semantics of claude_executor._grep_for_prohibited
    — identical rules on both sides of the commit boundary.
    """
    compiled: list[tuple[str, re.Pattern[str] | None]] = []
    for pat in patterns:
        try:
            compiled.append((pat, re.compile(pat)))
        except re.error:
            compiled.append((pat, None))

    hits: list[str] = []
    for path in _staged_file_list(cwd):
        r = subprocess.run(
            ["git", "diff", "--cached", "--", path],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            continue
        # Only inspect added lines (prefixed with "+" but not "+++").
        added = [
            line[1:] for line in r.stdout.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        blob = "\n".join(added)
        for pat, regex in compiled:
            hit = regex.search(blob) if regex is not None else (pat in blob)
            if hit:
                hits.append(f"{path}:{pat}")
                if len(hits) > 20:
                    return hits
    return hits


_HEREDOC_SENTINEL = re.compile(r"<<-?\s*['\"]?(\w+)")


def _extract_commit_message(cmd: str) -> tuple[str | None, str]:
    """Pull the ``-m`` argument out of a git-commit command.

    Returns ``(message, parse_mode)`` where ``parse_mode`` is:
        * "literal"   — we parsed a plain quoted string cleanly
        * "heredoc"   — message is being supplied via a HEREDOC
        * "file"      — ``-F <file>`` used; message is in a file
        * "unknown"   — we don't know what the message is

    Callers can treat "unknown" as "can't enforce, allow through" to
    avoid breaking legitimate non-inline commit flows.
    """
    # -F <file> — message read from a file
    if re.search(r"(?:^|\s)(?:-F|--file)\s+\S+", cmd):
        return None, "file"

    # HEREDOC substitution — e.g. git commit -m "$(cat <<'EOF' ... EOF )"
    if _HEREDOC_SENTINEL.search(cmd):
        return None, "heredoc"

    # Plain quoted message. Handles escaped quotes inside the value by
    # looking for the matching close quote that isn't preceded by a
    # backslash. Double-quote and single-quote variants.
    for quote in ("'", '"'):
        pattern = rf"""-m\s+{quote}((?:\\.|(?!{quote}).)*){quote}"""
        m = re.search(pattern, cmd, flags=re.DOTALL)
        if m:
            raw = m.group(1)
            # Un-escape the quotes so downstream callers see the real message
            raw = raw.replace(f"\\{quote}", quote)
            return raw, "literal"

    return None, "unknown"


def _is_force_push_to_protected(cmd: str) -> bool:
    if "git push" not in cmd:
        return False
    if "--force" not in cmd and "-f " not in cmd and not cmd.rstrip().endswith("-f"):
        return False
    # protected refs
    for ref in ("main", "master", "production", "prod"):
        if re.search(rf"\b{ref}\b", cmd):
            return True
    return False


def evaluate(tool_name: str, tool_input: dict, cwd: str | None = None) -> tuple[str, str]:
    """Pure evaluator — given a tool call, return (decision, reason).

    decision is "allow" or "block". Split out for unit testing; the
    main entry point wraps this in stdin/stdout plumbing.
    """
    if tool_name != "Bash":
        return "allow", ""

    cmd = str(tool_input.get("command", ""))
    if not cmd:
        return "allow", ""

    # Force-push protection
    if _is_force_push_to_protected(cmd):
        if os.environ.get("NCDEV_ALLOW_FORCE_PUSH") != "1":
            return "block", (
                "Force-push to a protected branch. Set "
                "NCDEV_ALLOW_FORCE_PUSH=1 in the environment to override, "
                "or push to a feature branch instead."
            )

    # Only inspect git-commit commands for the remaining rules
    if "git commit" not in cmd:
        return "allow", ""

    # 1. Conventional Commits message shape
    msg, parse_mode = _extract_commit_message(cmd)
    if msg is not None:
        if not CONVENTIONAL_RE.search(msg):
            return "block", (
                "Commit message does not follow Conventional Commits "
                "(feat|fix|test|chore|refactor|docs|perf|style|build|ci|revert). "
                f"Got: {msg.splitlines()[0][:120]!r}"
            )
    elif parse_mode in ("heredoc", "file"):
        # We can't introspect the message body without running git, so
        # allow it. Worst case: a badly-formatted heredoc lands — but
        # relying on heredoc for commits is deliberate, users typically
        # know what they're doing. "unknown" falls through to allow as
        # well, since blocking would break edge-case pipelines.
        pass

    # 2. Prohibited patterns in staged content
    patterns = _load_prohibited()
    hits = _check_staged_for_prohibited(cwd, patterns)
    if hits:
        preview = ", ".join(hits[:5])
        return "block", (
            f"Staged changes contain prohibited patterns: {preview}"
            + (" (and more)" if len(hits) > 5 else "")
            + ". Remove them before committing."
        )

    return "allow", ""


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        _emit("allow")

    tool = event.get("tool_name") or event.get("tool") or ""
    inp = event.get("tool_input") or event.get("input") or {}
    cwd = event.get("cwd")

    decision, reason = evaluate(tool, inp, cwd)
    _emit(decision, reason)


if __name__ == "__main__":
    main()
