OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db5e0-0add-7dd1-9004-d94dffcbcddb
--------
user
# Peer review request — NC Dev System, Claude-orchestrator migration

You are Codex, and I am Claude. We normally work as peers when building
code: I plan and review, you implement and write tests. Right now I'm
asking you to step out of that dynamic and do a full **critical
engineering review** of a system I just architected and built. I want
you to look at it with fresh eyes — you had no part in the design — and
tell me where it's weak, wrong, or over-engineered.

## Context — what this repo is

**nc-dev-system** (`/Users/nrupal/dev/yensi/dev/nc-dev-system`,
branch `claude-orchestrator-migration`).

The user wanted an autonomous development system that takes a PRD and
builds a full application. The old version had a 9-artifact discovery
pipeline, a per-task provider router with 11 task types, prescriptive
multi-kilobyte build prompts (`FRONTEND_METHODOLOGY`, `GUARDRAILS`,
`QUALITY_STANDARDS`, `INFRASTRUCTURE_STANDARDS`), a Python build/verify/
repair ladder, and it invoked Claude and Codex as raw text-in/text-out
CLIs — not using any of Claude Code's skill/subagent/hook machinery.

The user's observation: that design was written for a less-capable
model era. Today's Claude Code is not a text generator; it's an agent
runtime with skills, subagents, hooks, MCP servers. NC Dev was
reimplementing in Python things the runtime already does better.

## What I just migrated it to

Architecture:

```
ncdev full --source prd.md
  │
  ├─ Preflight (git, claude, codex, Citex, optionally Stitch MCP)
  ├─ Phase 2: Charter (one Claude planning session)
  │     → target-project-contract.json (hard architectural constraints)
  │     → verification-contract.json   (what "done" means)
  │     → feature-queue.json           (ordered features)
  ├─ Phase 3: Design system
  │     ├─ Greenfield UI + Stitch MCP    → Stitch generates tokens + screens
  │     ├─ Brownfield + existing designs → Claude summarises
  │     ├─ Brownfield + no designs       → Claude's frontend-design skill
  │     └─ Greenfield + neither          → HARD FAIL
  ├─ Phase 4: Brownfield context ingestion into Citex (RAG)
  ├─ Phase 5: Sequential feature execution
  │     for each feature:
  │       one Claude session with tools [Read,Write,Edit,Glob,Grep,Bash,Skill,Task]
  │       system prompt includes Codex-via-Bash protocol
  │       hooks wired via --settings (block non-conventional commits, prohibited patterns, force-push)
  │       Claude uses skills: writing-plans, test-driven-development,
  │                           verification-before-completion, systematic-debugging
  │       Claude shells to Codex for implementation + test writing:
  │           codex exec --full-auto --sandbox danger-full-access "<scoped task>"
  │       Claude emits .ncdev/assets-needed/<fid>.json during build
  │       Claude commits with Conventional Commits on verification pass
  │     NC Dev streams events, checks git state, tags [BROKEN] on failure
  └─ Phase 6: Summary + metrics
```

Three explicit guarantees the user asked for:

1. **Codex invocation is direct Bash** — Claude runs `codex exec
   --full-auto --sandbox danger-full-access "<prompt>"` from its Bash
   tool. No Claude-subagent-wraps-Codex indirection (would be paying
   Claude tokens to babysit a Codex call). Codex gets the
   implementation work raw.
2. **Greenfield UI without design system = hard fail.** If there's no
   Stitch MCP configured and no `docs/design-system/` on disk and the
   project is greenfield, the run aborts with an actionable error. No
   "Claude generates tokens itself" fallback for greenfield.
   Brownfield lets Claude decide.
3. **Asset manifest during build, not after.** Every feature session
   must emit `.ncdev/assets-needed/<feature_id>.json` while building.
   Verification scans committed code for asset references and fails
   the feature if references aren't covered by the manifest.

## Mode switch (the user's budget lever)

`.nc-dev/v2/config.yaml` has `mode:`. Flip one line, no code change:

- `claude_plan_codex_build` (default): Claude plans/reviews, delegates impl to Codex via Bash
- `codex_only`: Codex does everything (token-lean days)
- `claude_only`: Claude does everything (no Codex)
- `openrouter`: API-only, needs `OPENROUTER_API_KEY`
- `custom`: hand-tuned routing

Implemented via `MODE_PRESETS` in `src/ncdev/v2/config.py` and a
`model_validator` that stamps `RoutingConfig` from the preset.

## Hooks

`scripts/ncdev-hooks/settings.json` wires a `PreToolUse` hook on Bash
that runs `scripts/ncdev-hooks/pre_bash_guard.py`. The hook:

1. Blocks `git commit` commands whose `-m` message is not Conventional
   Commits (feat/fix/test/chore/refactor/docs/perf/style/build/ci/revert).
2. Inspects the staged diff for prohibited patterns (`TODO`, `FIXME`,
   `console.log(`, "Not yet implemented") and blocks commits that add them.
3. Blocks `git push --force` to main/master/production unless
   `NCDEV_ALLOW_FORCE_PUSH=1`.

The hook is wired automatically by `run_claude_session()` via
`--settings` whenever `enable_ncdev_hooks=True` (default). Caller's
own `settings_path` takes precedence.

## The four migration commits

```
dbeb687 Phase A — Claude session runner + Codex-via-Bash protocol
48f8991 Phase B-C-D — charter + design phase + asset manifest
fdb8807 Phase E-F-G-H — Claude-driven executor, thin dev.py, engine rewrite, hooks
a91fd24 Phase I — delete dead modules, update CLI, rewrite docs
```

Diff vs `main`: 34 files, +4830 / -4331 lines. 372 tests passing.

---

# What I want from you

**Read the code. Form your own opinion. Be blunt.** I explicitly don't
want a polite "this looks great." I want to know what's wrong, what's
fragile, what's over-built, what's missing, what I got subtly
incorrect.

## Files to read (in roughly this order)

Start with the primitive and work up:

1. `src/ncdev/claude_session.py` — **the foundation**. One function
   everything depends on. Does it parse stream-json robustly? Is the
   event signal extraction correct? Is the cost-ceiling, timeout,
   hook-wiring plumbing sound? Will it deadlock on a misbehaving
   Claude process? Does it leak file handles on error paths?
2. `prompts/protocols/codex-via-bash.md` — the protocol Claude reads
   at session start. Is the guidance Codex-prompt-shape-correct?
   Anything that would produce sprawling, unfocused Codex work?
   Cost discipline rules reasonable?
3. `src/ncdev/v3/charter.py` — Phase B. Does the prompt actually elicit
   the three artifacts correctly? Is the schema hinting
   (`_schema_excerpt`) precise enough or hand-wavy? Would a real Claude
   session produce valid JSON from this, or will validation fail most
   of the time?
4. `src/ncdev/v3/models.py` — the pydantic schemas. Are
   `TargetProjectContract`, `VerificationContract`, `CharterBundle`,
   `DesignSystemDoc`, `AssetManifestEntry`, `AssetManifest` right
   for the job? Missing fields that will bite us? Over-rigid types?
5. `src/ncdev/v3/design_phase.py` — Phase C. The four-branch decision
   (Stitch / existing / claude_generated / hard-fail) — correct? Is
   the `stitch_available()` probe useful or just theatre? What
   happens when Stitch works partially?
6. `src/ncdev/v3/asset_manifest.py` — Phase D. `scan_code_for_asset_references`
   regexes — will they over-match or under-match? What assets will
   they miss? What about fingerprinted URLs? Is `verify_manifest_covers_references`
   the right enforcement point?
7. `src/ncdev/v3/claude_executor.py` — Phase E. **The main work unit.**
   Is the prompt telling Claude enough? Too little? Is the post-hoc
   verification the right shape (or should we trust
   `verification-before-completion` entirely)? Is `_commit_broken`
   recoverability enough, or will it create a mess across features?
   What about mid-feature session death (timeout, budget cap, crash)?
8. `src/ncdev/dev.py` — Phase F. The `ncdev dev` thin path. Too thin?
   What's missing compared to what a reasonable freeform dev session
   needs?
9. `src/ncdev/v3/engine.py` — Phase G. The top-level orchestrator.
   Does it handle partial success correctly? What about resuming
   after a crashed run?
10. `scripts/ncdev-hooks/pre_bash_guard.py` — Phase H. The hook. Is
    the commit-message extraction regex good enough? Will the
    staged-diff scan work on binary files (crash? skip?). Anything
    an adversarial Claude could bypass?
11. `src/ncdev/v2/config.py` — `MODE_PRESETS` + `mode` validator.
    Is the preset-always-overrides-routing behaviour confusing?
    What if someone hand-edits `routing:` with `mode: claude_plan_codex_build`?

## Specific questions I want answered

**Robustness**

- `claude_session.py` subprocess handling: what happens if Claude
  writes 100k lines of stream events? Is stdout buffering / Popen
  line-mode going to cause issues? Memory growth on long runs?
- `_extract_event_signals`: the stream-json schema is not stable
  across Claude Code versions. How brittle is my parser?
- `claude_executor._commit_broken`: if git commit itself is blocked
  by the hook (Conventional Commits), the BROKEN-tag commit will
  fail — does the current code notice?
- `pre_bash_guard._extract_commit_message`: what happens with
  `git commit -m "feat: add \"escaped\" quotes"`? Multi-line heredoc?

**Architectural soundness**

- Is "one Claude session per feature" really the right unit? Claude's
  context limit is finite. For a feature that touches 50 files with
  a complex data flow, will one session run out of room? Should we
  have session-per-sub-feature with a shared Citex query layer?
- Claude shells to Codex via Bash — does this actually leverage Codex
  effectively, or will Claude just do the work itself most of the
  time because Bash is slower than Edit for small changes?
- The hard-fail on greenfield UI without design system: right bar,
  or too strict? Should we have a `--skip-design` escape hatch for
  prototyping?
- The asset manifest enforcement: we fail features that reference
  unlisted assets. What about legitimately-missing-assets during
  iteration — is this going to cause frustrating re-runs?

**What's missing**

- No resume-after-crash logic. If engine dies mid-feature, the
  `state.json` is stale. Should there be an `ncdev resume <run_id>`?
- No cost reporting aggregation. Each session has `total_cost_usd`,
  but no run-level roll-up. The user will want "how much did this
  PRD cost?"
- No way for a feature to depend on a feature that's currently in
  a `[BROKEN]` state — do we proceed anyway? Block? Skip?
- No provision for Claude refusing a task (e.g. the feature is
  unclear). Right now this returns success with "I need clarification"
  in the final text and we accept it.

**What's over-engineered**

- Tell me honestly. The user wanted a thin system. Am I carrying
  state I don't need? Modules that could fold? Tests that test the
  mock rather than the behaviour?

**Test quality**

- Run `python -m pytest -q` and give me a sanity check: do the tests
  actually test behaviour, or just structure? Are there critical
  paths with no coverage? Are the `_FakeProc` / `_popen_factory`
  helpers a stand-in that masks real bugs?

**Bugs you can spot**

- Anything you see that I just got wrong. Don't spare me.

## Format of your response

Structure it as:

```
## Architecture verdict
<one paragraph — your overall take>

## Strengths
<3–5 bullets, specific, file:line citations>

## Critical issues
<issues that will break the system in practice — file:line, repro path, suggested fix>

## Concerning but not critical
<smells, likely future pain, couplings>

## Over-engineered / could be deleted
<where I added complexity I don't need>

## Missing
<what production needs that isn't there>

## Test coverage gaps
<the behaviours that aren't actually tested>

## Honest one-liner
<would you want to inherit this codebase? why/why not?>
```

Don't sandbag. If the whole premise is wrong, say so. If there's a
better architecture for the same goals, sketch it.

Go.

codex
Reviewing the orchestration path end to end and running the test suite. I’ll start from the session runner and executor surfaces, then check whether the tests exercise the real failure modes or just mocked structure.
exec
/bin/zsh -lc 'git status --short' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
?? docs/codex-review/

exec
/bin/zsh -lc 'python -m pytest -q' in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "rg -n \"def run_claude_session|def _extract_event_signals|def _commit_broken|def _extract_commit_message|MODE_PRESETS|model_validator|class TargetProjectContract|class VerificationContract|class CharterBundle|class DesignSystemDoc|class AssetManifest|def stitch_available|def scan_code_for_asset_references|def verify_manifest_covers_references|class ClaudeExecutor|def run\\(|def execute_feature|def run_dev_session\" src scripts prompts -S" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
scripts/ncdev-hooks/pre_bash_guard.py:108:def _extract_commit_message(cmd: str) -> str | None:
src/ncdev/dev.py:139:def _commit_broken_leftovers(project_path: Path, task: str) -> str:
src/ncdev/claude_session.py:112:def run_claude_session(
src/ncdev/claude_session.py:352:def _extract_event_signals(
src/ncdev/quality_gate/orchestrator.py:148:    async def run(
src/ncdev/v3/asset_manifest.py:158:def scan_code_for_asset_references(
src/ncdev/v3/asset_manifest.py:196:def verify_manifest_covers_references(
src/ncdev/v3/claude_executor.py:168:def execute_feature_claude_driven(
src/ncdev/v3/claude_executor.py:409:def _commit_broken(target_path: Path, feature: FeatureStep) -> None:
src/ncdev/v3/models.py:146:class TargetProjectContract(BaseModel):
src/ncdev/v3/models.py:184:class VerificationContract(BaseModel):
src/ncdev/v3/models.py:230:class CharterBundle(BaseModel):
src/ncdev/v3/models.py:251:class AssetManifestEntry(BaseModel):
src/ncdev/v3/models.py:269:class AssetManifest(BaseModel):
src/ncdev/v3/models.py:277:class DesignSystemDoc(BaseModel):
src/ncdev/v3/design_phase.py:72:def stitch_available() -> bool:
src/ncdev/v2/config.py:6:from pydantic import BaseModel, Field, model_validator
src/ncdev/v2/config.py:36:MODE_PRESETS: dict[str, dict[str, list[str]]] = {
src/ncdev/v2/config.py:151:            + ", ".join(sorted(MODE_PRESETS.keys()))
src/ncdev/v2/config.py:184:    @model_validator(mode="after")
src/ncdev/v2/config.py:186:        preset = MODE_PRESETS.get(self.mode)
src/ncdev/v2/config.py:190:                + ", ".join(sorted(MODE_PRESETS.keys()))
src/ncdev/v2/models.py:379:class TargetProjectContractDoc(ArtifactEnvelope):
src/ncdev/v2/models.py:409:class VerificationContractDoc(ArtifactEnvelope):

 exited 1 in 4702ms:
/Library/Frameworks/Python.framework/Versions/2.7/Resources/Python.app/Contents/MacOS/Python: No module named pytest

codex
The suite is still running. I’m reading the core paths directly now because the likely risks here are around process boundaries, prompt contracts, and recovery semantics rather than business logic.
exec
/bin/zsh -lc "nl -ba src/ncdev/claude_session.py | sed -n '1,260p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "nl -ba src/ncdev/claude_session.py | sed -n '261,520p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Claude Code session runner — the single way NC Dev spawns Claude.
     2	
     3	This is the primitive every higher-level orchestrator (discovery, feature
     4	executor, dev loop) builds on. It spawns Claude Code in non-interactive
     5	``--print --output-format stream-json`` mode, streams events as they
     6	arrive, writes a full event log, and returns a structured result.
     7	
     8	Skills, subagents, and MCP servers are controlled per call via the
     9	``tools`` and ``append_system_prompt`` arguments. Claude's cost ceiling
    10	is enforced by ``--max-budget-usd`` when ``max_budget_usd`` is provided —
    11	this is the primitive the token-budget-driven mode switch hooks into.
    12	"""
    13	
    14	from __future__ import annotations
    15	
    16	import json
    17	import os
    18	import shutil
    19	import subprocess
    20	import time
    21	from dataclasses import dataclass, field
    22	from pathlib import Path
    23	from typing import Callable, Iterable
    24	
    25	
    26	PROTOCOLS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "protocols"
    27	CODEX_PROTOCOL_PATH = PROTOCOLS_DIR / "codex-via-bash.md"
    28	
    29	# Default NC Dev hooks — block commits with prohibited patterns / non-
    30	# conventional messages, block force-push to protected branches.
    31	NCDEV_HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "ncdev-hooks"
    32	NCDEV_HOOKS_SETTINGS = NCDEV_HOOKS_DIR / "settings.json"
    33	
    34	
    35	# ---------------------------------------------------------------------------
    36	# Result types
    37	# ---------------------------------------------------------------------------
    38	
    39	
    40	@dataclass
    41	class ToolCallRecord:
    42	    """One tool invocation observed in the stream."""
    43	    tool: str
    44	    input_summary: str  # truncated string form of the input
    45	    raw: dict
    46	
    47	
    48	@dataclass
    49	class ClaudeSessionResult:
    50	    """Structured outcome of a Claude session."""
    51	    success: bool
    52	    final_text: str
    53	    exit_code: int
    54	    events: list[dict] = field(default_factory=list)
    55	    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    56	    skills_invoked: list[str] = field(default_factory=list)
    57	    codex_invocations: list[str] = field(default_factory=list)
    58	    subagents_dispatched: list[str] = field(default_factory=list)
    59	    files_touched: list[str] = field(default_factory=list)
    60	    total_cost_usd: float | None = None
    61	    duration_seconds: float = 0.0
    62	    stderr: str = ""
    63	    error: str | None = None
    64	
    65	    def summary(self) -> str:
    66	        parts = [
    67	            f"success={self.success}",
    68	            f"exit={self.exit_code}",
    69	            f"dur={self.duration_seconds:.1f}s",
    70	        ]
    71	        if self.total_cost_usd is not None:
    72	            parts.append(f"cost=${self.total_cost_usd:.3f}")
    73	        if self.tool_calls:
    74	            parts.append(f"tools={len(self.tool_calls)}")
    75	        if self.skills_invoked:
    76	            parts.append(f"skills={','.join(self.skills_invoked)}")
    77	        if self.codex_invocations:
    78	            parts.append(f"codex={len(self.codex_invocations)}")
    79	        return " ".join(parts)
    80	
    81	
    82	# ---------------------------------------------------------------------------
    83	# Runner
    84	# ---------------------------------------------------------------------------
    85	
    86	
    87	# Default tool allowlist for Claude sessions that orchestrate builds.
    88	# Caller can override completely. Tools that enable the Codex-as-peer
    89	# architecture: Bash (to shell out to codex exec), Skill (to invoke skills
    90	# like test-driven-development), Task (to dispatch subagents).
    91	DEFAULT_BUILD_TOOLS: tuple[str, ...] = (
    92	    "Read",
    93	    "Write",
    94	    "Edit",
    95	    "Glob",
    96	    "Grep",
    97	    "Bash",
    98	    "Skill",
    99	    "Task",
   100	)
   101	
   102	# Minimal tool set for planning-only sessions that must not edit code.
   103	DEFAULT_PLAN_TOOLS: tuple[str, ...] = (
   104	    "Read",
   105	    "Glob",
   106	    "Grep",
   107	    "Write",       # may write charter / feature-queue artifacts
   108	    "Skill",
   109	)
   110	
   111	
   112	def run_claude_session(
   113	    prompt: str,
   114	    *,
   115	    cwd: Path,
   116	    tools: Iterable[str] = DEFAULT_BUILD_TOOLS,
   117	    model: str = "claude-opus-4-6",
   118	    timeout: int = 1800,
   119	    permission_mode: str = "acceptEdits",
   120	    append_system_prompt: str | None = None,
   121	    include_codex_protocol: bool = True,
   122	    max_budget_usd: float | None = None,
   123	    log_path: Path | None = None,
   124	    on_event: Callable[[dict], None] | None = None,
   125	    extra_args: list[str] | None = None,
   126	    settings_path: Path | None = None,
   127	    enable_ncdev_hooks: bool = True,
   128	) -> ClaudeSessionResult:
   129	    """Spawn a Claude session and stream its events.
   130	
   131	    Parameters
   132	    ----------
   133	    prompt:
   134	        The user-facing prompt. Pass a task statement, not a huge context
   135	        blob — put big context in files and ask Claude to read them.
   136	    cwd:
   137	        Working directory for the session (the target repo, typically).
   138	    tools:
   139	        Tool allowlist. Use :data:`DEFAULT_BUILD_TOOLS` for feature builds
   140	        (includes Bash for Codex shell-out, Skill for skill invocation,
   141	        Task for subagents). Use :data:`DEFAULT_PLAN_TOOLS` for read-only
   142	        planning sessions.
   143	    model:
   144	        Model label for Claude. Default: ``claude-opus-4-6``.
   145	    timeout:
   146	        Kill-switch in seconds. Separate from ``max_budget_usd`` — both
   147	        can terminate the session.
   148	    permission_mode:
   149	        Passed to ``--permission-mode``. Default ``acceptEdits`` lets the
   150	        model edit files without interactive prompts. Use
   151	        ``bypassPermissions`` for fully trusted runs.
   152	    append_system_prompt:
   153	        Text appended to Claude's default system prompt. Use this to
   154	        inject the Codex protocol, project charter reference, etc.
   155	    include_codex_protocol:
   156	        When True (default), the Codex-via-Bash protocol is prepended to
   157	        ``append_system_prompt`` so every session knows how to delegate
   158	        to Codex. Set False for sessions that must not invoke Codex.
   159	    max_budget_usd:
   160	        Hard cost ceiling for this session. Claude aborts if exceeded.
   161	        This is the hook for budget-driven mode switching.
   162	    log_path:
   163	        If provided, every stream event is appended as a JSONL line.
   164	    on_event:
   165	        Optional callback fired per event in real time. Use for live
   166	        progress UI. Exceptions in the callback are caught and logged.
   167	    extra_args:
   168	        Additional raw flags passed to ``claude``. Escape hatch.
   169	    settings_path:
   170	        Optional path to a Claude Code settings JSON with hooks/MCP
   171	        config. When set, passed via ``--settings``.
   172	    enable_ncdev_hooks:
   173	        When True (default), NC Dev's built-in hook guards (commit
   174	        hygiene + force-push protection) are wired in automatically
   175	        unless ``settings_path`` is also set (caller wins).
   176	    """
   177	    if shutil.which("claude") is None:
   178	        return ClaudeSessionResult(
   179	            success=False, final_text="", exit_code=-1,
   180	            error="claude CLI not found on PATH",
   181	        )
   182	
   183	    # Compose the system prompt append block
   184	    system_prompt_parts: list[str] = []
   185	    if include_codex_protocol and CODEX_PROTOCOL_PATH.exists():
   186	        system_prompt_parts.append(CODEX_PROTOCOL_PATH.read_text(encoding="utf-8"))
   187	    if append_system_prompt:
   188	        system_prompt_parts.append(append_system_prompt)
   189	    system_prompt = "\n\n---\n\n".join(system_prompt_parts) if system_prompt_parts else None
   190	
   191	    tools_list = list(tools)
   192	
   193	    cmd: list[str] = [
   194	        "claude",
   195	        "-p", prompt,
   196	        "--output-format", "stream-json",
   197	        "--include-partial-messages",
   198	        "--include-hook-events",
   199	        "--model", model,
   200	        "--permission-mode", permission_mode,
   201	        "--allowedTools", ",".join(tools_list),
   202	    ]
   203	    if system_prompt:
   204	        cmd += ["--append-system-prompt", system_prompt]
   205	    if max_budget_usd is not None:
   206	        cmd += ["--max-budget-usd", f"{max_budget_usd:.4f}"]
   207	
   208	    # Wire hooks: caller-supplied settings_path wins; otherwise, if
   209	    # enable_ncdev_hooks and the default settings file exists, use it.
   210	    chosen_settings = settings_path
   211	    if chosen_settings is None and enable_ncdev_hooks and NCDEV_HOOKS_SETTINGS.exists():
   212	        chosen_settings = NCDEV_HOOKS_SETTINGS
   213	    env_overrides: dict[str, str] = {}
   214	    if chosen_settings is not None:
   215	        cmd += ["--settings", str(chosen_settings)]
   216	        # Make the hooks dir discoverable to the command substitution in settings.json
   217	        env_overrides["NCDEV_HOOKS_DIR"] = str(NCDEV_HOOKS_DIR)
   218	    if extra_args:
   219	        cmd += list(extra_args)
   220	
   221	    start = time.time()
   222	    events: list[dict] = []
   223	    log_fh = None
   224	    if log_path is not None:
   225	        log_path.parent.mkdir(parents=True, exist_ok=True)
   226	        log_fh = log_path.open("w", encoding="utf-8")
   227	
   228	    subproc_env = os.environ.copy()
   229	    subproc_env.update(env_overrides)
   230	    try:
   231	        proc = subprocess.Popen(
   232	            cmd,
   233	            cwd=str(cwd),
   234	            stdout=subprocess.PIPE,
   235	            stderr=subprocess.PIPE,
   236	            text=True,
   237	            bufsize=1,
   238	            env=subproc_env,
   239	        )
   240	    except (FileNotFoundError, OSError) as exc:
   241	        if log_fh:
   242	            log_fh.close()
   243	        return ClaudeSessionResult(
   244	            success=False, final_text="", exit_code=-1,
   245	            error=f"failed to spawn claude: {exc}",
   246	        )
   247	
   248	    final_text = ""
   249	    skills: list[str] = []
   250	    tool_calls: list[ToolCallRecord] = []
   251	    codex_calls: list[str] = []
   252	    subagents: list[str] = []
   253	    files_touched: set[str] = set()
   254	    total_cost: float | None = None
   255	
   256	    assert proc.stdout is not None
   257	    try:
   258	        for line in proc.stdout:
   259	            line = line.strip()
   260	            if not line:

 succeeded in 0ms:
   261	                continue
   262	            try:
   263	                event = json.loads(line)
   264	            except json.JSONDecodeError:
   265	                # Tolerate non-JSON noise — log raw, skip parse
   266	                if log_fh:
   267	                    log_fh.write(json.dumps({"_raw": line}) + "\n")
   268	                continue
   269	
   270	            events.append(event)
   271	            if log_fh:
   272	                log_fh.write(json.dumps(event) + "\n")
   273	                log_fh.flush()
   274	
   275	            _extract_event_signals(
   276	                event,
   277	                skills=skills,
   278	                tool_calls=tool_calls,
   279	                codex_calls=codex_calls,
   280	                subagents=subagents,
   281	                files_touched=files_touched,
   282	            )
   283	
   284	            if event.get("type") == "result":
   285	                final_text = event.get("result") or event.get("text") or final_text
   286	                total_cost = event.get("total_cost_usd", total_cost)
   287	
   288	            if on_event is not None:
   289	                try:
   290	                    on_event(event)
   291	                except Exception:  # noqa: BLE001
   292	                    # Never let a caller callback crash the session reader
   293	                    pass
   294	
   295	        proc.wait(timeout=timeout)
   296	        stderr_text = proc.stderr.read() if proc.stderr else ""
   297	    except subprocess.TimeoutExpired:
   298	        proc.kill()
   299	        proc.wait(timeout=5)
   300	        stderr_text = proc.stderr.read() if proc.stderr else ""
   301	        if log_fh:
   302	            log_fh.close()
   303	        return ClaudeSessionResult(
   304	            success=False, final_text=final_text, exit_code=-1,
   305	            events=events, tool_calls=tool_calls,
   306	            skills_invoked=skills, codex_invocations=codex_calls,
   307	            subagents_dispatched=subagents,
   308	            files_touched=sorted(files_touched),
   309	            total_cost_usd=total_cost,
   310	            duration_seconds=time.time() - start,
   311	            stderr=stderr_text,
   312	            error=f"claude session timed out after {timeout}s",
   313	        )
   314	    finally:
   315	        if log_fh:
   316	            log_fh.close()
   317	
   318	    exit_code = proc.returncode
   319	    duration = time.time() - start
   320	
   321	    # Fall back to final event text if result event didn't land
   322	    if not final_text:
   323	        for ev in reversed(events):
   324	            if ev.get("type") in ("assistant", "result"):
   325	                text = _extract_text(ev)
   326	                if text:
   327	                    final_text = text
   328	                    break
   329	
   330	    return ClaudeSessionResult(
   331	        success=exit_code == 0,
   332	        final_text=final_text,
   333	        exit_code=exit_code,
   334	        events=events,
   335	        tool_calls=tool_calls,
   336	        skills_invoked=skills,
   337	        codex_invocations=codex_calls,
   338	        subagents_dispatched=subagents,
   339	        files_touched=sorted(files_touched),
   340	        total_cost_usd=total_cost,
   341	        duration_seconds=duration,
   342	        stderr=stderr_text,
   343	        error=None if exit_code == 0 else f"claude exited with code {exit_code}",
   344	    )
   345	
   346	
   347	# ---------------------------------------------------------------------------
   348	# Event parsing helpers
   349	# ---------------------------------------------------------------------------
   350	
   351	
   352	def _extract_event_signals(
   353	    event: dict,
   354	    *,
   355	    skills: list[str],
   356	    tool_calls: list[ToolCallRecord],
   357	    codex_calls: list[str],
   358	    subagents: list[str],
   359	    files_touched: set[str],
   360	) -> None:
   361	    """Pull structured signals out of a stream event.
   362	
   363	    Stream-json schema has evolved across Claude Code versions — we keep
   364	    this tolerant: inspect common shapes, ignore unknowns.
   365	    """
   366	    ev_type = event.get("type")
   367	
   368	    # Tool use appears inside assistant messages as content items with
   369	    # type=tool_use. Extract recursively.
   370	    if ev_type == "assistant":
   371	        message = event.get("message") or {}
   372	        content = message.get("content") or []
   373	        for item in content:
   374	            if not isinstance(item, dict):
   375	                continue
   376	            if item.get("type") == "tool_use":
   377	                tool_name = item.get("name", "?")
   378	                input_data = item.get("input") or {}
   379	                summary = _summarize_input(tool_name, input_data)
   380	                tool_calls.append(ToolCallRecord(
   381	                    tool=tool_name,
   382	                    input_summary=summary,
   383	                    raw=item,
   384	                ))
   385	                if tool_name == "Skill":
   386	                    skill_name = input_data.get("skill") or input_data.get("name")
   387	                    if skill_name and skill_name not in skills:
   388	                        skills.append(skill_name)
   389	                elif tool_name == "Task":
   390	                    agent = input_data.get("subagent_type") or input_data.get("agent")
   391	                    if agent:
   392	                        subagents.append(agent)
   393	                elif tool_name == "Bash":
   394	                    cmd = input_data.get("command", "")
   395	                    if "codex exec" in cmd or cmd.strip().startswith("codex "):
   396	                        codex_calls.append(cmd[:500])
   397	                elif tool_name in ("Write", "Edit"):
   398	                    path = input_data.get("file_path")
   399	                    if path:
   400	                        files_touched.add(path)
   401	
   402	
   403	def _summarize_input(tool: str, data: dict) -> str:
   404	    if tool == "Bash":
   405	        cmd = str(data.get("command", ""))
   406	        return cmd[:200]
   407	    if tool in ("Write", "Edit"):
   408	        return str(data.get("file_path", ""))[:200]
   409	    if tool == "Read":
   410	        return str(data.get("file_path", ""))[:200]
   411	    if tool == "Skill":
   412	        return str(data.get("skill") or data.get("name") or "")[:200]
   413	    if tool == "Task":
   414	        desc = data.get("description", "")
   415	        sub = data.get("subagent_type", "")
   416	        return f"{sub}: {desc}"[:200]
   417	    return str(data)[:200]
   418	
   419	
   420	def _extract_text(event: dict) -> str:
   421	    """Best-effort pull of readable text from an event."""
   422	    if not isinstance(event, dict):
   423	        return ""
   424	    if "result" in event:
   425	        return str(event["result"])
   426	    if "text" in event:
   427	        return str(event["text"])
   428	    message = event.get("message")
   429	    if isinstance(message, dict):
   430	        content = message.get("content")
   431	        if isinstance(content, str):
   432	            return content
   433	        if isinstance(content, list):
   434	            texts: list[str] = []
   435	            for item in content:
   436	                if isinstance(item, dict) and item.get("type") == "text":
   437	                    texts.append(str(item.get("text", "")))
   438	            if texts:
   439	                return "\n".join(texts)
   440	    return ""

exec
/bin/zsh -lc "nl -ba prompts/protocols/codex-via-bash.md | sed -n '1,260p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	# Codex Protocol — How to delegate implementation to Codex via Bash
     2	
     3	You (Claude) are the orchestrator. Codex is your implementation peer — faster
     4	and cheaper than you at writing code, but weaker at judgment. Use Codex for
     5	raw implementation and test writing. Do the planning, review, and debugging
     6	yourself.
     7	
     8	## When to use Codex
     9	
    10	- Writing new implementation code (backend routes, frontend components, migrations)
    11	- Writing tests for specified behavior (given a contract, produce the test file)
    12	- Mechanical refactors (rename, move file, split function) across many files
    13	- Scaffolding boilerplate (Dockerfile, config files, package.json)
    14	
    15	## When NOT to use Codex
    16	
    17	- Anything requiring judgment about architecture or tradeoffs
    18	- Reviewing code (do this yourself)
    19	- Debugging failing tests — use the `systematic-debugging` skill yourself
    20	- Deciding what to build — that's planning, yours
    21	- Anything where you would want to ask a clarifying question first
    22	
    23	## How to invoke Codex
    24	
    25	Use the `Bash` tool. The canonical invocation:
    26	
    27	```bash
    28	codex exec --full-auto --sandbox danger-full-access "<prompt>"
    29	```
    30	
    31	`--full-auto` grants all tool permissions. `--sandbox danger-full-access`
    32	lets Codex edit files in the repo. Prompt is the whole task as a single
    33	string argument — no flags after it.
    34	
    35	For longer prompts, write the prompt to a temp file and pipe:
    36	
    37	```bash
    38	cat .ncdev/tmp/codex-prompt.md | codex exec --full-auto --sandbox danger-full-access -
    39	```
    40	
    41	## Prompt shape for Codex (follow this)
    42	
    43	Codex performs best with concrete, scoped tasks. Structure every Codex
    44	prompt like this:
    45	
    46	```
    47	# Task
    48	<one-line description>
    49	
    50	# Context
    51	<2-3 lines on the surrounding code / feature / current state>
    52	
    53	# Requirements
    54	- <bullet 1>
    55	- <bullet 2>
    56	- ...
    57	
    58	# Files
    59	- Read: <path1>, <path2>
    60	- Create: <path3>
    61	- Modify: <path4>
    62	
    63	# Verification
    64	<exact command(s) that must pass when you're done>
    65	```
    66	
    67	Do not hand Codex vague goals like "make the frontend nicer". It will
    68	produce sprawling, unfocused changes. Every Codex task must be narrow
    69	enough that a single `pytest` or `npm test` command can verify it.
    70	
    71	## Handling Codex output
    72	
    73	Codex returns its work summary on stdout. Exit code 0 means it finished,
    74	not that it succeeded — always run the verification command yourself
    75	afterward.
    76	
    77	- Exit code 0 + verification passes → accept the work, move on
    78	- Exit code 0 + verification fails → review Codex's output, identify the
    79	  specific failure, send Codex a **scoped** repair prompt (include the
    80	  exact error). Do not re-prompt with the original task.
    81	- Exit code != 0 → read stderr, decide whether to retry with a clearer
    82	  prompt or take over the work yourself
    83	
    84	Never let Codex loop more than 2× on the same task. If two tries don't
    85	land it, you do the work yourself — Codex is stuck on something it
    86	doesn't see.
    87	
    88	## Cost discipline
    89	
    90	You pay Claude tokens to orchestrate. Codex calls cost money too, but
    91	different money. Rules:
    92	
    93	- Do not invoke Codex for tasks under ~30 lines of code — faster to do
    94	  it yourself
    95	- Do not invoke Codex for UI tweaks the user can see in a screenshot —
    96	  faster to do it yourself
    97	- Do batch related work into one Codex call rather than three sequential
    98	  calls (one call to write a model + its schema + its route is cheaper
    99	  than three calls)
   100	
   101	## What Codex cannot do
   102	
   103	- Cannot invoke skills or other subagents (it has its own narrower tool set)
   104	- Cannot read NC Dev's Citex context directly — pass relevant findings
   105	  in the prompt
   106	- Cannot reason about cross-feature coherence — that's your job
   107	
   108	## Example
   109	
   110	Good:
   111	
   112	```bash
   113	codex exec --full-auto --sandbox danger-full-access "# Task
   114	Implement POST /api/v1/users/invite endpoint
   115	
   116	# Context
   117	Existing auth lives in backend/app/core/security.py. User model at
   118	backend/app/models/user.py. Invite emails are stubbed via the
   119	mock transport in backend/app/mocks/email.py.
   120	
   121	# Requirements
   122	- Accepts {email, role} JSON body
   123	- Validates email format, role in {admin, member}
   124	- Creates pending User row with status='invited'
   125	- Calls email.send_invite(user)
   126	- Returns 201 + {user_id}
   127	- Rejects duplicate emails with 409
   128	
   129	# Files
   130	- Read: backend/app/models/user.py, backend/app/core/security.py
   131	- Create: backend/app/api/v1/endpoints/invites.py
   132	- Modify: backend/app/api/v1/router.py (register the route)
   133	
   134	# Verification
   135	cd backend && python -m pytest tests/integration/test_invites.py -q
   136	"
   137	```
   138	
   139	Bad (too vague, Codex will wander):
   140	
   141	```bash
   142	codex exec --full-auto --sandbox danger-full-access "Add user invites"
   143	```

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/charter.py | sed -n '1,280p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Phase B — Charter generator.
     2	
     3	Replaces the 9-artifact V2 discovery pipeline with a single Claude session
     4	that reads the PRD (and optionally an existing repo) and emits three
     5	artifacts:
     6	
     7	    target-project-contract.json   # stack, language, DB, auth, ports — the hard constraints
     8	    verification-contract.json     # what "done" means
     9	    feature-queue.json             # ordered FeatureStep list
    10	
    11	The Claude session is pointed at the ``writing-plans`` skill and constrained
    12	to the :data:`ncdev.claude_session.DEFAULT_PLAN_TOOLS` allowlist — it can
    13	read files and write JSON, but cannot edit code or invoke Codex. It produces
    14	the three files directly into ``run_dir/outputs/``.
    15	"""
    16	
    17	from __future__ import annotations
    18	
    19	import json
    20	from pathlib import Path
    21	
    22	from ncdev.claude_session import (
    23	    DEFAULT_PLAN_TOOLS,
    24	    ClaudeSessionResult,
    25	    run_claude_session,
    26	)
    27	from ncdev.v3.models import (
    28	    CharterBundle,
    29	    FeatureQueueDoc,
    30	    TargetProjectContract,
    31	    VerificationContract,
    32	)
    33	
    34	
    35	CHARTER_PROMPT_TEMPLATE = """You are producing the project charter for NC Dev's
    36	sequential verified sprint engine. Your job is PLANNING only — do NOT write
    37	application code, do NOT scaffold, do NOT run tests.
    38	
    39	Use the `writing-plans` skill to structure your work.
    40	
    41	## Input
    42	- PRD file: {prd_path}
    43	- Target repository (may be empty for greenfield, existing for brownfield):
    44	  {target_repo}
    45	- Project type detected: {project_type_hint}
    46	
    47	## Required deliverables
    48	
    49	Write exactly three JSON files into the directory:
    50	
    51	  {output_dir}
    52	
    53	### 1. target-project-contract.json
    54	
    55	The hard architectural constraints for this project. These are the
    56	invariants that must not change across future runs. Schema:
    57	
    58	{contract_schema}
    59	
    60	Rules:
    61	- For greenfield, infer sane defaults from the PRD.
    62	- For brownfield, DETECT from the existing repo — do not override what
    63	  is there. Read package.json / pyproject.toml / docker-compose.yml etc.
    64	- `design_archetype` must be one of: Cinematic Minimalism, Technical
    65	  Elegance, Opinionated Darkness, Warm Playfulness, Developer Brutalism,
    66	  Bold Brand Photography. Pick the one best matching the PRD's tone.
    67	- `design_system_source` is "stitch" for new UIs unless the brownfield
    68	  repo already has docs/design-system/ populated.
    69	- `ports` should not collide with existing ports in the repo.
    70	
    71	### 2. verification-contract.json
    72	
    73	What "done" means for every feature built against this project. Schema:
    74	
    75	{verification_schema}
    76	
    77	Rules:
    78	- `backend_test_command` / `frontend_test_command` — use the commands
    79	  native to the detected frameworks (pytest, vitest, jest, etc.)
    80	- `required_files` — the minimum file list that MUST exist after all
    81	  features are built (Dockerfile, .env.example, README, etc.)
    82	- `required_screenshots` — list the key pages/routes that must have a
    83	  screenshot captured.
    84	- Keep `prohibited_patterns` as-is unless the PRD explicitly calls out
    85	  additions.
    86	
    87	### 3. feature-queue.json
    88	
    89	The ordered build list. Schema:
    90	
    91	{feature_queue_schema}
    92	
    93	Rules:
    94	- Each feature must be independently verifiable (it has tests that run
    95	  and pass in isolation).
    96	- `feature_id` format: `fNN-slug` (f01-scaffold, f02-auth, ...).
    97	- First feature is always `f01-scaffold` — boot skeleton + health check.
    98	- `depends_on_features` must only reference earlier feature_ids.
    99	- For BROWNFIELD with design tokens at docs/design-system/, feature f01
   100	  may be "baseline verification" instead of scaffolding.
   101	- Target 4–12 features for most PRDs. If the PRD is huge, group into
   102	  logical features rather than listing every sub-task.
   103	
   104	## Brownfield special rule
   105	
   106	If the repository already contains a design system at
   107	`docs/design-system/`, or has sample pages under a frontend tree, you MAY
   108	proceed. Otherwise, for greenfield UI projects, you MUST fail the run by
   109	writing ONLY a file named `charter-error.json` with:
   110	
   111	  {{"error": "greenfield UI project requires a design system (Stitch
   112	  setup) before charter generation can proceed", "fix": "run stitch
   113	  setup or supply docs/design-system/ with tokens"}}
   114	
   115	## Output format
   116	
   117	Use the `Write` tool to create each file. Validate with `Read` that you
   118	produced valid JSON. Return a one-sentence summary in your final
   119	response. Do not output the JSON content in your response — just write
   120	the files and confirm.
   121	"""
   122	
   123	
   124	def _schema_excerpt(model_cls) -> str:
   125	    """Render a compact JSON-schema hint for a pydantic model."""
   126	    schema = model_cls.model_json_schema()
   127	    props = schema.get("properties", {})
   128	    lines = []
   129	    for key, spec in props.items():
   130	        t = spec.get("type", "?")
   131	        if t == "array":
   132	            items = spec.get("items", {})
   133	            t = f"array<{items.get('type', '?')}>"
   134	        default = spec.get("default")
   135	        desc = spec.get("description", "")
   136	        tail = f"  # {desc}" if desc else ""
   137	        if default is not None and not isinstance(default, (list, dict)):
   138	            lines.append(f"  {key}: {t} = {default!r}{tail}")
   139	        else:
   140	            lines.append(f"  {key}: {t}{tail}")
   141	    return "{\n" + "\n".join(lines) + "\n}"
   142	
   143	
   144	def _feature_queue_schema_excerpt() -> str:
   145	    return """{
   146	  project_name: str
   147	  features: array<FeatureStep>
   148	}
   149	
   150	FeatureStep = {
   151	  feature_id: str            # "fNN-slug"
   152	  title: str
   153	  description: str
   154	  acceptance_criteria: array<str>
   155	  test_requirements: array<str>
   156	  depends_on_features: array<str>
   157	  priority: int
   158	  estimated_complexity: "low" | "medium" | "high"
   159	}"""
   160	
   161	
   162	def build_charter_prompt(
   163	    prd_path: Path,
   164	    target_repo: Path | None,
   165	    output_dir: Path,
   166	    project_type_hint: str = "web",
   167	) -> str:
   168	    return CHARTER_PROMPT_TEMPLATE.format(
   169	        prd_path=str(prd_path),
   170	        target_repo=str(target_repo) if target_repo else "(none — greenfield)",
   171	        output_dir=str(output_dir),
   172	        project_type_hint=project_type_hint,
   173	        contract_schema=_schema_excerpt(TargetProjectContract),
   174	        verification_schema=_schema_excerpt(VerificationContract),
   175	        feature_queue_schema=_feature_queue_schema_excerpt(),
   176	    )
   177	
   178	
   179	def generate_charter(
   180	    prd_path: Path,
   181	    output_dir: Path,
   182	    *,
   183	    target_repo: Path | None = None,
   184	    project_type_hint: str = "web",
   185	    model: str = "claude-opus-4-6",
   186	    timeout: int = 900,
   187	    max_budget_usd: float | None = None,
   188	    log_path: Path | None = None,
   189	) -> tuple[CharterBundle | None, ClaudeSessionResult]:
   190	    """Run the charter Claude session and load the produced artifacts.
   191	
   192	    Returns ``(bundle, session_result)``. ``bundle`` is None if the
   193	    session failed, produced invalid JSON, or wrote a ``charter-error.json``
   194	    (enforced hard-fail for greenfield UI without design system).
   195	    """
   196	    output_dir.mkdir(parents=True, exist_ok=True)
   197	    prompt = build_charter_prompt(prd_path, target_repo, output_dir, project_type_hint)
   198	
   199	    session = run_claude_session(
   200	        prompt,
   201	        cwd=output_dir,
   202	        tools=DEFAULT_PLAN_TOOLS,
   203	        model=model,
   204	        timeout=timeout,
   205	        include_codex_protocol=False,   # planning only — no Codex shell-out
   206	        max_budget_usd=max_budget_usd,
   207	        log_path=log_path,
   208	    )
   209	
   210	    # Hard-fail: greenfield UI without design system writes this file.
   211	    error_path = output_dir / "charter-error.json"
   212	    if error_path.exists():
   213	        return None, session
   214	
   215	    if not session.success:
   216	        return None, session
   217	
   218	    try:
   219	        bundle = load_charter(output_dir)
   220	    except (FileNotFoundError, json.JSONDecodeError, ValueError):
   221	        return None, session
   222	
   223	    return bundle, session
   224	
   225	
   226	def load_charter(output_dir: Path) -> CharterBundle:
   227	    """Load the three charter artifacts from disk. Raises on missing/invalid."""
   228	    contract_path = output_dir / "target-project-contract.json"
   229	    verification_path = output_dir / "verification-contract.json"
   230	    feature_queue_path = output_dir / "feature-queue.json"
   231	
   232	    for p in (contract_path, verification_path, feature_queue_path):
   233	        if not p.exists():
   234	            raise FileNotFoundError(f"Charter artifact missing: {p}")
   235	
   236	    contract = TargetProjectContract.model_validate_json(
   237	        contract_path.read_text(encoding="utf-8"),
   238	    )
   239	    verification = VerificationContract.model_validate_json(
   240	        verification_path.read_text(encoding="utf-8"),
   241	    )
   242	    feature_queue = FeatureQueueDoc.model_validate_json(
   243	        feature_queue_path.read_text(encoding="utf-8"),
   244	    )
   245	
   246	    return CharterBundle(
   247	        contract=contract,
   248	        verification=verification,
   249	        feature_queue=feature_queue,
   250	    )
   251	
   252	
   253	def write_charter(bundle: CharterBundle, output_dir: Path) -> None:
   254	    """Persist a charter bundle as three JSON files. Useful for tests."""
   255	    output_dir.mkdir(parents=True, exist_ok=True)
   256	    (output_dir / "target-project-contract.json").write_text(
   257	        bundle.contract.model_dump_json(indent=2), encoding="utf-8",
   258	    )
   259	    (output_dir / "verification-contract.json").write_text(
   260	        bundle.verification.model_dump_json(indent=2), encoding="utf-8",
   261	    )
   262	    (output_dir / "feature-queue.json").write_text(
   263	        bundle.feature_queue.model_dump_json(indent=2), encoding="utf-8",
   264	    )

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/models.py | sed -n '1,360p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""V3 models — sequential verified sprint engine."""
     2	
     3	from __future__ import annotations
     4	
     5	from datetime import datetime, timezone
     6	from enum import Enum
     7	from pathlib import Path
     8	from typing import Any
     9	
    10	from pydantic import BaseModel, Field
    11	
    12	
    13	class FeatureStep(BaseModel):
    14	    """A single feature to implement in sequence."""
    15	
    16	    feature_id: str
    17	    title: str
    18	    description: str
    19	    acceptance_criteria: list[str]
    20	    test_requirements: list[str] = Field(default_factory=list)
    21	    depends_on_features: list[str] = Field(default_factory=list)
    22	    priority: int = 0
    23	    estimated_complexity: str = "medium"  # low, medium, high
    24	
    25	
    26	class FeatureQueueDoc(BaseModel):
    27	    """Ordered list of features to implement sequentially."""
    28	
    29	    version: str = "v3"
    30	    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    31	    generator: str = "ncdev.v3.feature_queue"
    32	    project_name: str = ""
    33	    features: list[FeatureStep] = Field(default_factory=list)
    34	    sprint_zero_criteria: list[str] = Field(default_factory=lambda: [
    35	        "App installs without errors",
    36	        "App boots and health endpoint returns OK",
    37	        "Empty test suite runs",
    38	        "First screenshot captured",
    39	    ])
    40	
    41	
    42	class StepStatus(str, Enum):
    43	    PENDING = "pending"
    44	    BUILDING = "building"
    45	    VERIFYING = "verifying"
    46	    REPAIRING = "repairing"
    47	    PASSED = "passed"
    48	    FAILED = "failed"
    49	    SKIPPED = "skipped"
    50	
    51	
    52	class TestResult(BaseModel):
    53	    """Result of running a test suite."""
    54	
    55	    suite: str  # "unit", "integration", "e2e"
    56	    passed: int = 0
    57	    failed: int = 0
    58	    errors: int = 0
    59	    skipped: int = 0
    60	    output: str = ""
    61	    success: bool = False
    62	    duration_seconds: float = 0.0
    63	
    64	
    65	class ScreenshotEvidence(BaseModel):
    66	    """A screenshot captured during verification."""
    67	
    68	    path: str
    69	    description: str
    70	    viewport: str = "desktop"  # desktop, mobile
    71	    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    72	
    73	
    74	class StepVerification(BaseModel):
    75	    """Verification results for a single feature step."""
    76	
    77	    lint_passed: bool = False
    78	    lint_output: str = ""
    79	    unit_tests: TestResult | None = None
    80	    integration_tests: TestResult | None = None
    81	    e2e_tests: TestResult | None = None
    82	    screenshots: list[ScreenshotEvidence] = Field(default_factory=list)
    83	    prohibited_patterns: list[str] = Field(default_factory=list)
    84	    app_boots: bool = False
    85	    overall_passed: bool = False
    86	    failure_reasons: list[str] = Field(default_factory=list)
    87	
    88	
    89	class StepResult(BaseModel):
    90	    """Result of executing one feature step."""
    91	
    92	    feature_id: str
    93	    status: StepStatus
    94	    build_duration_seconds: float = 0.0
    95	    verify_duration_seconds: float = 0.0
    96	    repair_attempts: int = 0
    97	    verification: StepVerification | None = None
    98	    files_created: list[str] = Field(default_factory=list)
    99	    files_modified: list[str] = Field(default_factory=list)
   100	    commit_sha: str = ""
   101	    error_message: str = ""
   102	    builder_output: str = ""
   103	
   104	
   105	class V3RunState(BaseModel):
   106	    """Overall state of a V3 pipeline run."""
   107	
   108	    run_id: str
   109	    command: str = "full"
   110	    workspace: str = ""
   111	    run_dir: str = ""
   112	    target_path: str = ""
   113	    phase: str = "init"
   114	    status: str = "running"
   115	    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
   116	    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
   117	    feature_queue: FeatureQueueDoc | None = None
   118	    completed_steps: list[StepResult] = Field(default_factory=list)
   119	    current_step: str = ""
   120	    total_features: int = 0
   121	    completed_features: int = 0
   122	    metadata: dict[str, Any] = Field(default_factory=dict)
   123	
   124	
   125	class IngestionRecord(BaseModel):
   126	    """One document ingested into Citex."""
   127	    category: str
   128	    char_count: int
   129	    success: bool
   130	
   131	
   132	class IngestionReport(BaseModel):
   133	    """Summary of context ingestion into Citex."""
   134	    project_id: str
   135	    total_documents: int = 0
   136	    successful: int = 0
   137	    failed: int = 0
   138	    records: list[IngestionRecord] = Field(default_factory=list)
   139	
   140	
   141	# ---------------------------------------------------------------------------
   142	# Charter artifacts — the 3 files that replace the old 9-artifact pipeline.
   143	# ---------------------------------------------------------------------------
   144	
   145	
   146	class TargetProjectContract(BaseModel):
   147	    """Hard architectural constraints. The 'don't override' bag.
   148	
   149	    Fields the user controls: stack, language, DB, auth, deployment target,
   150	    ports, design archetype. Claude may infer defaults from the PRD but
   151	    must NOT change these after the first session — they're the invariants.
   152	    """
   153	
   154	    version: str = "v3"
   155	    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
   156	    project_name: str
   157	    project_type: str = "web"  # web | cli | library | api
   158	    is_brownfield: bool = False
   159	    existing_repo_path: str = ""
   160	
   161	    # Stack — each field optional; "none" means explicitly not used.
   162	    backend_framework: str = ""     # fastapi | django | express | none
   163	    frontend_framework: str = ""    # react | vue | svelte | none
   164	    database: str = ""              # mongodb | postgres | sqlite | none
   165	    auth_system: str = ""           # keycloak | jwt | none
   166	    language_backend: str = ""
   167	    language_frontend: str = ""
   168	
   169	    # Deployment
   170	    deployment_target: str = "docker"   # docker | k8s | serverless
   171	    ports: dict[str, int] = Field(default_factory=dict)
   172	
   173	    # Design
   174	    design_archetype: str = ""  # See user's global CLAUDE.md for values
   175	    design_system_source: str = "stitch"   # stitch | existing | claude
   176	    design_system_path: str = "docs/design-system"
   177	
   178	    # Other invariants the orchestrator or verification must know
   179	    uses_citex: bool = True
   180	    uses_mock_apis: bool = True
   181	    production_readiness_required: bool = True
   182	
   183	
   184	class VerificationContract(BaseModel):
   185	    """What 'done' means for this project.
   186	
   187	    The Claude feature-executor session must satisfy every clause before
   188	    committing. Hooks enforce where possible; post-hoc checks cover the rest.
   189	    """
   190	
   191	    version: str = "v3"
   192	    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
   193	
   194	    # App must boot
   195	    backend_health_url: str = ""       # e.g. http://localhost:23001/api/health
   196	    frontend_url: str = ""
   197	    boot_timeout_seconds: int = 60
   198	
   199	    # Tests must exist and pass
   200	    backend_test_command: str = ""     # e.g. "cd backend && python -m pytest -q"
   201	    frontend_test_command: str = ""    # e.g. "cd frontend && npm test -- --run"
   202	    e2e_test_command: str = ""         # e.g. "cd frontend && npx playwright test"
   203	    minimum_test_count: int = 1
   204	
   205	    # Screenshots
   206	    required_screenshots: list[str] = Field(default_factory=list)
   207	    screenshot_viewports: list[str] = Field(default_factory=lambda: ["desktop", "mobile"])
   208	
   209	    # Files that must exist
   210	    required_files: list[str] = Field(default_factory=list)
   211	
   212	    # Assets
   213	    assets_manifest_required: bool = True
   214	    assets_manifest_path: str = ".ncdev/assets-needed"
   215	
   216	    # Prohibited patterns (grep-able — hooks enforce these on commit)
   217	    prohibited_patterns: list[str] = Field(default_factory=lambda: [
   218	        "TODO",
   219	        "FIXME",
   220	        "console.log(",
   221	        r"except:\s*pass",
   222	        "Not yet implemented",
   223	    ])
   224	
   225	    # Commit hygiene
   226	    require_conventional_commits: bool = True
   227	    require_tests_in_commit: bool = True
   228	
   229	
   230	class CharterBundle(BaseModel):
   231	    """The three artifacts produced by the discovery phase, together."""
   232	
   233	    contract: TargetProjectContract
   234	    verification: VerificationContract
   235	    feature_queue: FeatureQueueDoc
   236	
   237	
   238	# ---------------------------------------------------------------------------
   239	# Design system artifact (Phase C output)
   240	# ---------------------------------------------------------------------------
   241	
   242	
   243	class DesignScreen(BaseModel):
   244	    """One design screen / page produced by Stitch or equivalent."""
   245	    name: str
   246	    html_path: str = ""         # path to exported HTML within the repo
   247	    screenshot_path: str = ""   # path to PNG export
   248	    description: str = ""
   249	
   250	
   251	class AssetManifestEntry(BaseModel):
   252	    """One asset the feature needs but couldn't generate itself.
   253	
   254	    Listed so a downstream system (Nano Banana 2, stock image service,
   255	    human) can produce it. Claude writes one of these per asset while
   256	    building the feature — during the build, not after.
   257	    """
   258	    id: str                         # unique slug, e.g. "hero-bg"
   259	    name: str                       # human-readable
   260	    type: str                       # image | gif | svg | video | icon | audio
   261	    description: str                # what it shows / represents
   262	    generation_prompt: str          # prompt for an image-gen AI to produce it
   263	    suggested_dimensions: str = ""  # "1920x1080", "64x64", etc
   264	    referenced_in: list[str] = Field(default_factory=list)   # "src/pages/Home.tsx:42"
   265	    target_path: str = ""           # where in the repo the file should land
   266	    status: str = "pending"         # pending | generated | manual | skipped
   267	
   268	
   269	class AssetManifest(BaseModel):
   270	    """All assets needed by one feature."""
   271	    version: str = "v3"
   272	    feature_id: str
   273	    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
   274	    assets: list[AssetManifestEntry] = Field(default_factory=list)
   275	
   276	
   277	class DesignSystemDoc(BaseModel):
   278	    """Summary of the project's design system.
   279	
   280	    Populated by Phase C. Downstream feature builds reference this to
   281	    know what colours / fonts / spacing / component patterns to use.
   282	    """
   283	    version: str = "v3"
   284	    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
   285	
   286	    project_name: str
   287	    design_archetype: str
   288	    source: str = "stitch"           # stitch | existing | claude_generated
   289	
   290	    # Where the real design tokens live on disk (project-relative)
   291	    tokens_dir: str = "docs/design-system"
   292	    tokens_files: list[str] = Field(default_factory=list)   # e.g. ["tokens.css", "tailwind.config.js"]
   293	
   294	    # Optional: design system description
   295	    colors: dict[str, str] = Field(default_factory=dict)
   296	    typography: dict[str, str] = Field(default_factory=dict)
   297	    spacing: dict[str, str] = Field(default_factory=dict)
   298	
   299	    # Screens exported for reference
   300	    screens: list[DesignScreen] = Field(default_factory=list)
   301	
   302	    # Provenance
   303	    stitch_project_id: str = ""
   304	    notes: list[str] = Field(default_factory=list)

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/design_phase.py | sed -n '1,320p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Phase C — Design system phase.
     2	
     3	For any web / UI project, produces a design system in ``docs/design-system/``
     4	and a summary :class:`DesignSystemDoc` artifact. Three paths:
     5	
     6	    * ``source="stitch"``   — invoke a Claude session with the Stitch MCP
     7	                              server exposed; Claude creates a Stitch
     8	                              project, generates the design system, and
     9	                              downloads tokens + screen HTML.
    10	    * ``source="existing"`` — brownfield case: ``docs/design-system/`` is
    11	                              already populated; Claude reads it and
    12	                              summarises into the artifact.
    13	    * ``source="claude_generated"`` — fallback when Stitch is
    14	                              unavailable AND the project is brownfield.
    15	                              Claude's ``frontend-design`` skill produces
    16	                              the tokens itself.
    17	
    18	Hard-fail rule (enforces the user's ask):
    19	
    20	    Greenfield UI project + no Stitch available + no existing design
    21	    system on disk → fail the run with an actionable error. We will NOT
    22	    let a build proceed without defined designs.
    23	"""
    24	
    25	from __future__ import annotations
    26	
    27	from dataclasses import dataclass
    28	from pathlib import Path
    29	
    30	from ncdev.claude_session import (
    31	    ClaudeSessionResult,
    32	    run_claude_session,
    33	)
    34	from ncdev.v3.models import (
    35	    DesignSystemDoc,
    36	    TargetProjectContract,
    37	)
    38	
    39	
    40	# Tools for the design session: Read/Write/Edit for tokens, Bash for
    41	# any Stitch CLI shell-outs, Skill to trigger frontend-design, Task for
    42	# subagent dispatch. The Stitch MCP tools come through as
    43	# ``mcp__stitch__*`` names — we pass a wildcard via an extra_args flag
    44	# rather than enumerating them (MCP tool names are environment-specific).
    45	DESIGN_TOOLS: tuple[str, ...] = (
    46	    "Read",
    47	    "Write",
    48	    "Edit",
    49	    "Glob",
    50	    "Grep",
    51	    "Bash",
    52	    "Skill",
    53	    "Task",
    54	)
    55	
    56	
    57	@dataclass
    58	class DesignPhaseResult:
    59	    """Outcome of the design phase."""
    60	    skipped: bool = False           # non-UI project
    61	    hard_failed: bool = False       # greenfield UI without designs and no Stitch
    62	    design_doc: DesignSystemDoc | None = None
    63	    session: ClaudeSessionResult | None = None
    64	    error: str | None = None
    65	
    66	
    67	# ---------------------------------------------------------------------------
    68	# Environment probes
    69	# ---------------------------------------------------------------------------
    70	
    71	
    72	def stitch_available() -> bool:
    73	    """Return True if a Stitch MCP server appears to be configured.
    74	
    75	    Detection is intentionally lightweight — we check for the presence of
    76	    a ``stitch`` key in the user's Claude config, or the env var
    77	    ``NCDEV_STITCH_MCP_CONFIG`` pointing at a valid path. A full probe
    78	    would spawn Claude and ask; we avoid that here for speed.
    79	    """
    80	    import os
    81	    if os.environ.get("NCDEV_STITCH_MCP_CONFIG"):
    82	        return bool(Path(os.environ["NCDEV_STITCH_MCP_CONFIG"]).exists())
    83	    # Check user-level Claude config for an mcpServer with "stitch" in name
    84	    config_path = Path.home() / ".claude" / "settings.json"
    85	    if config_path.exists():
    86	        try:
    87	            import json
    88	            cfg = json.loads(config_path.read_text(encoding="utf-8"))
    89	            servers = cfg.get("mcpServers", {})
    90	            return any("stitch" in k.lower() for k in servers.keys())
    91	        except Exception:  # noqa: BLE001
    92	            return False
    93	    return False
    94	
    95	
    96	def existing_design_system_present(target_path: Path) -> bool:
    97	    """True if ``target_path/docs/design-system/`` exists with content."""
    98	    ds = target_path / "docs" / "design-system"
    99	    if not ds.exists() or not ds.is_dir():
   100	        return False
   101	    # Has at least one token-y file
   102	    for f in ds.rglob("*"):
   103	        if f.is_file() and f.stat().st_size > 0:
   104	            return True
   105	    return False
   106	
   107	
   108	def is_ui_project(contract: TargetProjectContract) -> bool:
   109	    return contract.project_type.lower() in ("web", "webapp", "frontend", "spa", "saas")
   110	
   111	
   112	# ---------------------------------------------------------------------------
   113	# Prompt builders
   114	# ---------------------------------------------------------------------------
   115	
   116	
   117	def _stitch_prompt(contract: TargetProjectContract, target_path: Path, output_dir: Path) -> str:
   118	    return f"""You are producing the design system for a new web project using Stitch
   119	(Google's design tool, available via MCP).
   120	
   121	## Project
   122	- Name: {contract.project_name}
   123	- Design archetype: {contract.design_archetype}
   124	- Frontend framework: {contract.frontend_framework}
   125	- Target repository: {target_path}
   126	
   127	## Required workflow
   128	
   129	1. Use the Stitch MCP tools to create a new Stitch project for
   130	   "{contract.project_name}".
   131	2. Generate a design system (colors, typography, spacing, corner
   132	   rounding) aligned with the "{contract.design_archetype}" archetype.
   133	3. Generate the key screens listed in
   134	   ``{output_dir}/../feature-queue.json`` (at least the ones marked as
   135	   having UI).
   136	4. Download the design tokens (CSS variables, Tailwind config, or the
   137	   equivalent for {contract.frontend_framework}) into:
   138	     {target_path}/docs/design-system/
   139	5. Download HTML exports for each screen into:
   140	     {target_path}/docs/design-system/screens/
   141	6. Write a summary artifact at:
   142	     {output_dir}/design-system.json
   143	   Schema (DesignSystemDoc):
   144	     {{
   145	       "project_name": "{contract.project_name}",
   146	       "design_archetype": "{contract.design_archetype}",
   147	       "source": "stitch",
   148	       "tokens_dir": "docs/design-system",
   149	       "tokens_files": ["..."],
   150	       "colors": {{ ... }},
   151	       "typography": {{ ... }},
   152	       "spacing": {{ ... }},
   153	       "screens": [{{ "name": "...", "html_path": "...", "screenshot_path": "..." }}],
   154	       "stitch_project_id": "..."
   155	     }}
   156	
   157	## Rules
   158	
   159	- Do NOT write any application code. Tokens and HTML only.
   160	- Prefer downloading real HTML from Stitch over screenshots — it
   161	  preserves animations and layout metadata.
   162	- If Stitch MCP tools are unavailable or fail, STOP and write
   163	  ``{output_dir}/design-phase-error.json`` with an actionable message.
   164	  Do not fall back to generating tokens yourself.
   165	
   166	Return a one-sentence summary when done.
   167	"""
   168	
   169	
   170	def _brownfield_prompt(contract: TargetProjectContract, target_path: Path, output_dir: Path) -> str:
   171	    return f"""This is a brownfield project. A design system already exists at:
   172	  {target_path}/docs/design-system/
   173	
   174	## Your job
   175	
   176	1. Read the existing design system files.
   177	2. Summarise them into ``{output_dir}/design-system.json`` using schema:
   178	     {{
   179	       "project_name": "{contract.project_name}",
   180	       "design_archetype": "{contract.design_archetype}",
   181	       "source": "existing",
   182	       "tokens_dir": "docs/design-system",
   183	       "tokens_files": ["..."],   # actual filenames found
   184	       "colors": {{ ... }},         # extracted palette
   185	       "typography": {{ ... }},     # font families / sizes found
   186	       "spacing": {{ ... }},
   187	       "screens": [{{ "name": "...", "html_path": "..." }}]
   188	     }}
   189	
   190	## Rules
   191	
   192	- Do NOT modify any files under docs/design-system/ — you are only
   193	  reading and summarising.
   194	- Do not invoke Codex. Do not write implementation code.
   195	
   196	Return a one-sentence summary when done.
   197	"""
   198	
   199	
   200	# ---------------------------------------------------------------------------
   201	# Entry point
   202	# ---------------------------------------------------------------------------
   203	
   204	
   205	def run_design_phase(
   206	    contract: TargetProjectContract,
   207	    target_path: Path,
   208	    output_dir: Path,
   209	    *,
   210	    model: str = "claude-opus-4-6",
   211	    timeout: int = 1200,
   212	    max_budget_usd: float | None = None,
   213	    log_path: Path | None = None,
   214	    stitch_probe: callable = stitch_available,
   215	) -> DesignPhaseResult:
   216	    """Resolve the design system for this project.
   217	
   218	    Returns a :class:`DesignPhaseResult`. The caller MUST check
   219	    ``hard_failed`` and abort the pipeline when True.
   220	    """
   221	    output_dir.mkdir(parents=True, exist_ok=True)
   222	
   223	    # Non-UI projects skip the design phase entirely.
   224	    if not is_ui_project(contract):
   225	        return DesignPhaseResult(skipped=True)
   226	
   227	    has_existing = existing_design_system_present(target_path)
   228	    has_stitch = stitch_probe()
   229	
   230	    # --- Hard-fail: greenfield UI, no existing designs, no Stitch ----------
   231	    if not contract.is_brownfield and not has_existing and not has_stitch:
   232	        err_path = output_dir / "design-phase-error.json"
   233	        err_path.write_text(
   234	            '{"error": "greenfield UI project requires a design system",'
   235	            ' "fix": "install and configure the Stitch MCP server, or '
   236	            'supply docs/design-system/ with design tokens and sample pages"}',
   237	            encoding="utf-8",
   238	        )
   239	        return DesignPhaseResult(
   240	            hard_failed=True,
   241	            error="greenfield UI project requires a design system (Stitch or docs/design-system)",
   242	        )
   243	
   244	    # --- Brownfield with existing design system ----------------------------
   245	    if has_existing:
   246	        prompt = _brownfield_prompt(contract, target_path, output_dir)
   247	        session = run_claude_session(
   248	            prompt,
   249	            cwd=target_path,
   250	            tools=DESIGN_TOOLS,
   251	            model=model,
   252	            timeout=timeout,
   253	            include_codex_protocol=False,
   254	            max_budget_usd=max_budget_usd,
   255	            log_path=log_path,
   256	        )
   257	        doc = _load_design_doc(output_dir)
   258	        return DesignPhaseResult(design_doc=doc, session=session)
   259	
   260	    # --- Greenfield (or brownfield without designs) + Stitch available ----
   261	    if has_stitch:
   262	        prompt = _stitch_prompt(contract, target_path, output_dir)
   263	        session = run_claude_session(
   264	            prompt,
   265	            cwd=target_path,
   266	            tools=DESIGN_TOOLS,
   267	            model=model,
   268	            timeout=timeout,
   269	            include_codex_protocol=False,  # design phase does not build code
   270	            max_budget_usd=max_budget_usd,
   271	            log_path=log_path,
   272	        )
   273	        # Stitch session may itself fail — check for its error file
   274	        err_path = output_dir / "design-phase-error.json"
   275	        if err_path.exists():
   276	            return DesignPhaseResult(
   277	                hard_failed=True,
   278	                session=session,
   279	                error="Stitch design phase failed — see design-phase-error.json",
   280	            )
   281	        doc = _load_design_doc(output_dir)
   282	        return DesignPhaseResult(design_doc=doc, session=session)
   283	
   284	    # --- Brownfield without existing designs and no Stitch: Claude decides --
   285	    # Per the user's ruling: "brownfield or design-provided → Claude makes
   286	    # the call". We spawn Claude with the frontend-design skill; it may
   287	    # generate tokens itself.
   288	    prompt = (
   289	        f"This is a brownfield project '{contract.project_name}' without "
   290	        f"a pre-existing design system and without Stitch MCP available. "
   291	        f"Use the `frontend-design` skill to produce minimal design tokens "
   292	        f"aligned with the '{contract.design_archetype}' archetype, "
   293	        f"write them into {target_path}/docs/design-system/, and "
   294	        f"summarise in {output_dir}/design-system.json with source='claude_generated'. "
   295	        f"If you determine the project genuinely needs Stitch or external "
   296	        f"designs to proceed, write design-phase-error.json instead."
   297	    )
   298	    session = run_claude_session(
   299	        prompt,
   300	        cwd=target_path,
   301	        tools=DESIGN_TOOLS,
   302	        model=model,
   303	        timeout=timeout,
   304	        include_codex_protocol=False,
   305	        max_budget_usd=max_budget_usd,
   306	        log_path=log_path,
   307	    )
   308	    err_path = output_dir / "design-phase-error.json"
   309	    if err_path.exists():
   310	        return DesignPhaseResult(
   311	            hard_failed=True,
   312	            session=session,
   313	            error="Claude determined Stitch or external designs are needed",
   314	        )
   315	    doc = _load_design_doc(output_dir)
   316	    return DesignPhaseResult(design_doc=doc, session=session)
   317	
   318	
   319	def _load_design_doc(output_dir: Path) -> DesignSystemDoc | None:
   320	    path = output_dir / "design-system.json"

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/asset_manifest.py | sed -n '1,320p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Phase D — Asset manifest.
     2	
     3	Every Claude feature-build session must emit
     4	``.ncdev/assets-needed/<feature_id>.json`` describing the images, GIFs,
     5	SVGs, videos, icons, or audio clips the feature needs but couldn't
     6	generate itself. The manifest is produced **during** the build (Claude
     7	writes it as it codes — it knows its own intent), never after.
     8	
     9	Downstream systems (Nano Banana 2, a stock-image service, or a human)
    10	read the aggregate ``_all.json`` and populate each asset.
    11	
    12	Verification step: scan the committed code for asset references. Every
    13	reference must be present in a manifest entry, or the feature fails
    14	verification. Manifest entries with ``status="pending"`` are OK — the
    15	asset simply hasn't been populated yet. The code shipping without any
    16	manifest is what we reject.
    17	"""
    18	
    19	from __future__ import annotations
    20	
    21	import re
    22	from pathlib import Path
    23	from typing import Iterable
    24	
    25	from ncdev.v3.models import AssetManifest, AssetManifestEntry
    26	
    27	
    28	# Directory layout (project-relative):
    29	#   .ncdev/assets-needed/<feature_id>.json
    30	#   .ncdev/assets-needed/_all.json
    31	ASSETS_DIR = ".ncdev/assets-needed"
    32	
    33	
    34	# ---------------------------------------------------------------------------
    35	# Load / save / aggregate
    36	# ---------------------------------------------------------------------------
    37	
    38	
    39	def load_feature_manifest(project_root: Path, feature_id: str) -> AssetManifest | None:
    40	    """Load one feature's manifest, or None if it doesn't exist."""
    41	    path = project_root / ASSETS_DIR / f"{feature_id}.json"
    42	    if not path.exists():
    43	        return None
    44	    try:
    45	        return AssetManifest.model_validate_json(path.read_text(encoding="utf-8"))
    46	    except Exception:  # noqa: BLE001
    47	        return None
    48	
    49	
    50	def save_feature_manifest(project_root: Path, manifest: AssetManifest) -> Path:
    51	    """Write a feature manifest. Used by tests; Claude writes its own in real runs."""
    52	    out = project_root / ASSETS_DIR / f"{manifest.feature_id}.json"
    53	    out.parent.mkdir(parents=True, exist_ok=True)
    54	    out.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    55	    return out
    56	
    57	
    58	def aggregate_manifests(project_root: Path) -> AssetManifest:
    59	    """Merge all per-feature manifests into ``_all.json`` and return it."""
    60	    dir_ = project_root / ASSETS_DIR
    61	    all_assets: list[AssetManifestEntry] = []
    62	    seen: set[str] = set()
    63	    if dir_.exists():
    64	        for path in sorted(dir_.glob("*.json")):
    65	            if path.name in ("_all.json", "_summary.json"):
    66	                continue
    67	            try:
    68	                m = AssetManifest.model_validate_json(path.read_text(encoding="utf-8"))
    69	            except Exception:  # noqa: BLE001
    70	                continue
    71	            for asset in m.assets:
    72	                if asset.id in seen:
    73	                    continue
    74	                seen.add(asset.id)
    75	                all_assets.append(asset)
    76	    aggregate = AssetManifest(feature_id="_all", assets=all_assets)
    77	    out = dir_ / "_all.json"
    78	    out.parent.mkdir(parents=True, exist_ok=True)
    79	    out.write_text(aggregate.model_dump_json(indent=2), encoding="utf-8")
    80	    return aggregate
    81	
    82	
    83	# ---------------------------------------------------------------------------
    84	# Prompt helper — spliced into every feature build prompt
    85	# ---------------------------------------------------------------------------
    86	
    87	
    88	def manifest_prompt_section(feature_id: str) -> str:
    89	    """Return the prompt snippet every feature build must include.
    90	
    91	    Tells Claude how to emit the asset manifest for this feature as it
    92	    builds. The snippet includes schema and path. Keep short — we embed
    93	    this in every feature prompt.
    94	    """
    95	    return f"""## Asset manifest requirement
    96	
    97	While building this feature, identify every image, GIF, SVG, video,
    98	icon, or audio clip you reference in the code but cannot generate
    99	yourself. Write them to:
   100	
   101	    {ASSETS_DIR}/{feature_id}.json
   102	
   103	Schema (AssetManifest):
   104	
   105	    {{
   106	      "feature_id": "{feature_id}",
   107	      "assets": [
   108	        {{
   109	          "id": "hero-bg",                         # unique slug
   110	          "name": "Hero background image",
   111	          "type": "image",                         # image | gif | svg | video | icon | audio
   112	          "description": "Full-bleed gradient banner for the landing hero.",
   113	          "generation_prompt": "Abstract gradient mesh, deep purples and blues, cinematic.",
   114	          "suggested_dimensions": "2400x1200",
   115	          "referenced_in": ["frontend/src/pages/Home.tsx:42"],
   116	          "target_path": "frontend/public/images/hero-bg.webp",
   117	          "status": "pending"
   118	        }}
   119	      ]
   120	    }}
   121	
   122	Rules:
   123	- Write this file BEFORE your last commit. No trailing manifests.
   124	- If the feature needs zero assets, write an empty assets array — do
   125	  not skip the file.
   126	- For every <img>, background-image, <video>, <audio>, SVG reference,
   127	  or icon name your code introduces, there MUST be a manifest entry
   128	  unless the asset already exists in the repo.
   129	- Prefer referencing existing assets over inventing new ones. Only add
   130	  manifest entries for genuinely-missing files.
   131	"""
   132	
   133	
   134	# ---------------------------------------------------------------------------
   135	# Verification — scan code for asset references, cross-check manifest
   136	# ---------------------------------------------------------------------------
   137	
   138	
   139	# Patterns that signal an asset reference in source code
   140	_ASSET_REFERENCE_PATTERNS: tuple[re.Pattern, ...] = (
   141	    # HTML/JSX: <img src="...">, <video src="...">, poster="..."
   142	    re.compile(r"""<(?:img|video|audio|source)\s+[^>]*(?:src|poster)\s*=\s*["']([^"']+)["']""", re.IGNORECASE),
   143	    # JSX/TS import of image: import foo from "./foo.png"
   144	    re.compile(r"""import\s+\w+\s+from\s+["']([^"']+\.(?:png|jpe?g|webp|gif|svg|mp4|webm|mp3|wav|ogg|ico))["']""", re.IGNORECASE),
   145	    # CSS: background(-image): url("...")
   146	    re.compile(r"""url\(\s*["']?([^"')\s]+\.(?:png|jpe?g|webp|gif|svg|mp4|webm|ico))["']?\s*\)""", re.IGNORECASE),
   147	    # Next/Image src, React require: require("./foo.png")
   148	    re.compile(r"""require\(\s*["']([^"']+\.(?:png|jpe?g|webp|gif|svg|mp4|webm|mp3|wav|ogg|ico))["']\s*\)""", re.IGNORECASE),
   149	)
   150	
   151	_CODE_EXTENSIONS: tuple[str, ...] = (
   152	    ".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte", ".html",
   153	    ".css", ".scss", ".sass", ".less",
   154	    ".py", ".go", ".rs", ".rb",
   155	)
   156	
   157	
   158	def scan_code_for_asset_references(
   159	    project_root: Path,
   160	    *,
   161	    include_dirs: Iterable[str] = ("frontend", "src", "app", "pages", "public"),
   162	) -> list[tuple[str, str, int]]:
   163	    """Scan code files for asset references.
   164	
   165	    Returns list of tuples ``(file_path, referenced_asset, line_number)``.
   166	    Paths are project-relative.
   167	    """
   168	    hits: list[tuple[str, str, int]] = []
   169	    candidates: list[Path] = []
   170	    for d in include_dirs:
   171	        dir_path = project_root / d
   172	        if dir_path.exists():
   173	            for ext in _CODE_EXTENSIONS:
   174	                candidates.extend(dir_path.rglob(f"*{ext}"))
   175	    # Also scan top-level code files
   176	    for ext in _CODE_EXTENSIONS:
   177	        candidates.extend(project_root.glob(f"*{ext}"))
   178	
   179	    for fp in candidates:
   180	        try:
   181	            text = fp.read_text(encoding="utf-8", errors="ignore")
   182	        except OSError:
   183	            continue
   184	        rel = str(fp.relative_to(project_root))
   185	        for lineno, line in enumerate(text.splitlines(), start=1):
   186	            for pat in _ASSET_REFERENCE_PATTERNS:
   187	                for m in pat.finditer(line):
   188	                    ref = m.group(1)
   189	                    # Skip absolute URLs — they're external, not repo assets
   190	                    if ref.startswith(("http://", "https://", "data:", "//")):
   191	                        continue
   192	                    hits.append((rel, ref, lineno))
   193	    return hits
   194	
   195	
   196	def verify_manifest_covers_references(
   197	    project_root: Path,
   198	    feature_id: str,
   199	    *,
   200	    include_dirs: Iterable[str] = ("frontend", "src", "app", "pages", "public"),
   201	) -> tuple[bool, list[str]]:
   202	    """Verify every asset reference is accounted for.
   203	
   204	    An asset reference is "accounted for" when:
   205	      - a file at the referenced path exists in the repo, OR
   206	      - a manifest entry (in any per-feature manifest) points at that
   207	        path or has an id/name matching the filename.
   208	
   209	    Returns ``(ok, missing_list)``. When manifest-not-written, ok=False
   210	    and missing_list=["<no-manifest>"].
   211	    """
   212	    # Manifest for this feature must exist
   213	    manifest = load_feature_manifest(project_root, feature_id)
   214	    aggregate = aggregate_manifests(project_root)
   215	
   216	    if manifest is None:
   217	        return False, ["<no-manifest>"]
   218	
   219	    all_entries = aggregate.assets
   220	    managed_paths: set[str] = {
   221	        entry.target_path.lstrip("./") for entry in all_entries if entry.target_path
   222	    }
   223	    managed_ids: set[str] = {entry.id for entry in all_entries}
   224	
   225	    missing: list[str] = []
   226	    for file_ref, asset_ref, lineno in scan_code_for_asset_references(
   227	        project_root, include_dirs=include_dirs,
   228	    ):
   229	        normalised = asset_ref.lstrip("./").lstrip("/")
   230	        # Already exists in the repo?
   231	        candidates = [
   232	            project_root / normalised,
   233	            project_root / "public" / normalised,
   234	            project_root / "frontend" / "public" / normalised,
   235	            project_root / "frontend" / "src" / normalised,
   236	            project_root / "src" / normalised,
   237	        ]
   238	        if any(p.exists() for p in candidates):
   239	            continue
   240	        # Managed in a manifest?
   241	        if normalised in managed_paths:
   242	            continue
   243	        base = normalised.rsplit("/", 1)[-1].rsplit(".", 1)[0]
   244	        if base in managed_ids:
   245	            continue
   246	        missing.append(f"{file_ref}:{lineno} -> {asset_ref}")
   247	
   248	    return (len(missing) == 0), missing

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/claude_executor.py | sed -n '1,260p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Phase E — Claude-driven feature executor.
     2	
     3	Replaces the old ``step_executor.py`` manual build/verify/repair loop.
     4	For each feature we spawn exactly one Claude session. Claude drives
     5	the full build using its own skill machinery:
     6	
     7	    * ``writing-plans``                 — if the feature is complex
     8	    * ``test-driven-development``       — write failing test, then code
     9	    * ``verification-before-completion`` — no "done" without evidence
    10	    * ``systematic-debugging``          — when verification fails
    11	
    12	Claude shells out to Codex via Bash for implementation and test writing
    13	(the Codex-via-bash protocol is injected automatically by
    14	:func:`run_claude_session`).  NC Dev orchestrates the outer loop only:
    15	
    16	    1. Compose the feature prompt (charter refs, prior results, asset
    17	       manifest requirement, verification contract).
    18	    2. Run the session. Stream events.
    19	    3. Inspect git state afterwards:
    20	         * clean working tree + new commit(s) → PASSED
    21	         * changes present but no commit     → commit with [BROKEN] tag
    22	         * no changes at all                 → FAILED, builder didn't do anything
    23	    4. Run post-hoc verification: manifest covers refs, required files exist.
    24	    5. Return StepResult. Orchestrator moves to the next feature.
    25	"""
    26	
    27	from __future__ import annotations
    28	
    29	import json
    30	import subprocess
    31	import time
    32	from pathlib import Path
    33	
    34	from ncdev.claude_session import (
    35	    DEFAULT_BUILD_TOOLS,
    36	    ClaudeSessionResult,
    37	    run_claude_session,
    38	)
    39	from ncdev.v3.asset_manifest import (
    40	    manifest_prompt_section,
    41	    verify_manifest_covers_references,
    42	)
    43	from ncdev.v3.models import (
    44	    CharterBundle,
    45	    FeatureStep,
    46	    StepResult,
    47	    StepStatus,
    48	    StepVerification,
    49	)
    50	
    51	
    52	# ---------------------------------------------------------------------------
    53	# Prompt composition
    54	# ---------------------------------------------------------------------------
    55	
    56	
    57	def build_feature_prompt(
    58	    feature: FeatureStep,
    59	    target_path: Path,
    60	    charter_dir: Path,
    61	    prior_feature_ids: list[str],
    62	    project_id: str,
    63	    citex_url: str = "http://localhost:20161",
    64	) -> str:
    65	    """Compose the single prompt handed to Claude for this feature.
    66	
    67	    Deliberately terse. Heavy reference material (contract, verification,
    68	    design system) stays on disk — Claude reads it with the Read tool.
    69	    This is a departure from the old prescriptive mega-prompts.
    70	    """
    71	    prior_block = (
    72	        "No prior features — this is the first build in the queue."
    73	        if not prior_feature_ids
    74	        else f"Prior features already built and verified: {', '.join(prior_feature_ids)}"
    75	    )
    76	
    77	    return f"""# Feature: {feature.feature_id} — {feature.title}
    78	
    79	You are the engineer for this feature. You have the Claude skill
    80	machinery available; use it. Codex is your implementation peer
    81	(see the Codex protocol in your system prompt) — delegate raw
    82	implementation and test writing to Codex via Bash, keep judgment
    83	and review yourself.
    84	
    85	## Context
    86	
    87	- Project charter:        {charter_dir}/target-project-contract.json
    88	- Verification contract:  {charter_dir}/verification-contract.json
    89	- Design system:          {charter_dir}/design-system.json  (if present)
    90	- Feature queue:          {charter_dir}/feature-queue.json
    91	- Target repository:      {target_path}
    92	- Citex project ID:       {project_id}
    93	- Citex URL:              {citex_url}
    94	
    95	{prior_block}
    96	
    97	## Your feature spec
    98	
    99	- ID:          {feature.feature_id}
   100	- Title:       {feature.title}
   101	- Description: {feature.description}
   102	- Complexity:  {feature.estimated_complexity}
   103	- Priority:    {feature.priority}
   104	
   105	### Acceptance criteria
   106	{chr(10).join(f"- {c}" for c in feature.acceptance_criteria) or "- (none specified — infer from description)"}
   107	
   108	### Test requirements
   109	{chr(10).join(f"- {t}" for t in feature.test_requirements) or "- (use your judgment — tests MUST exist and verify behaviour, not just syntax)"}
   110	
   111	### Depends on
   112	{", ".join(feature.depends_on_features) if feature.depends_on_features else "(none)"}
   113	
   114	## Required workflow
   115	
   116	1. **Read** the charter artifacts listed above. They are the hard
   117	   constraints for stack, ports, auth, deployment. Do not override them.
   118	2. **Query Citex** (the RAG system at `{citex_url}`) for anything you
   119	   need to know about prior features, data models, or existing code.
   120	   Use Bash if Citex exposes a CLI, or read the local `.ncdev/` cache.
   121	3. **Use the `writing-plans` skill** if this is a high-complexity
   122	   feature. For low complexity, go straight to step 4.
   123	4. **Use the `test-driven-development` skill**. Write failing tests
   124	   first (you may delegate the test file content to Codex via Bash).
   125	5. **Delegate implementation to Codex via Bash**. One well-scoped
   126	   Codex call per sub-task is better than five vague ones. Review
   127	   Codex's output yourself before moving on.
   128	6. **Emit the asset manifest** as you build — see the schema below.
   129	7. **Use the `verification-before-completion` skill** before you
   130	   claim done. Run the verification contract's test commands yourself.
   131	   Run the app and probe its health endpoint. Capture the required
   132	   screenshots listed in the verification contract.
   133	8. **If verification fails**, use the `systematic-debugging` skill.
   134	   Do not loop blindly — identify root cause, fix narrowly, re-verify.
   135	9. **Commit the work** once verification passes. Use Conventional
   136	   Commits (feat/fix/test) referencing the feature_id. Leave the
   137	   working tree clean.
   138	
   139	{manifest_prompt_section(feature.feature_id)}
   140	
   141	## What success looks like
   142	
   143	- Working tree is clean (all changes committed).
   144	- The feature's tests exist, run, and pass.
   145	- Verification contract is satisfied (boot, tests, screenshots, files).
   146	- Asset manifest file exists at
   147	  `.ncdev/assets-needed/{feature.feature_id}.json`.
   148	- Your final response summarises what was built in <= 5 sentences.
   149	
   150	## What failure looks like (avoid)
   151	
   152	- "Implemented, but tests are still failing — here's what I tried."
   153	  → Not done. Use systematic-debugging.
   154	- Working tree dirty when you're "done." → Commit or revert.
   155	- Asset manifest missing. → Write it before committing.
   156	- Any of the `prohibited_patterns` in the verification contract
   157	  landed in a commit. → Those are pre-commit-hook blockers; fix.
   158	
   159	Begin.
   160	"""
   161	
   162	
   163	# ---------------------------------------------------------------------------
   164	# Executor
   165	# ---------------------------------------------------------------------------
   166	
   167	
   168	def execute_feature_claude_driven(
   169	    feature: FeatureStep,
   170	    target_path: Path,
   171	    run_dir: Path,
   172	    charter_bundle: CharterBundle,
   173	    prior_results: list[StepResult],
   174	    project_id: str,
   175	    *,
   176	    model: str = "claude-opus-4-6",
   177	    timeout: int = 3600,
   178	    max_budget_usd: float | None = None,
   179	    citex_url: str = "http://localhost:20161",
   180	) -> StepResult:
   181	    """Run one feature via a Claude session and return the StepResult.
   182	
   183	    See module docstring for the outer flow.
   184	    """
   185	    step_dir = run_dir / "steps" / feature.feature_id
   186	    step_dir.mkdir(parents=True, exist_ok=True)
   187	
   188	    charter_dir = run_dir / "outputs"
   189	    prior_ids = [r.feature_id for r in prior_results if r.status == StepStatus.PASSED]
   190	
   191	    prompt = build_feature_prompt(
   192	        feature=feature,
   193	        target_path=target_path,
   194	        charter_dir=charter_dir,
   195	        prior_feature_ids=prior_ids,
   196	        project_id=project_id,
   197	        citex_url=citex_url,
   198	    )
   199	    (step_dir / "prompt.md").write_text(prompt, encoding="utf-8")
   200	
   201	    # Snapshot git state so we can detect what changed
   202	    pre_commit = _git_head(target_path)
   203	
   204	    start = time.time()
   205	    session = run_claude_session(
   206	        prompt,
   207	        cwd=target_path,
   208	        tools=DEFAULT_BUILD_TOOLS,
   209	        model=model,
   210	        timeout=timeout,
   211	        permission_mode="acceptEdits",
   212	        include_codex_protocol=True,
   213	        max_budget_usd=max_budget_usd,
   214	        log_path=step_dir / "session.jsonl",
   215	    )
   216	    build_duration = time.time() - start
   217	
   218	    # Save session summary for debugging
   219	    (step_dir / "session-summary.txt").write_text(session.summary(), encoding="utf-8")
   220	    if session.final_text:
   221	        (step_dir / "final-response.md").write_text(session.final_text, encoding="utf-8")
   222	
   223	    post_commit = _git_head(target_path)
   224	    made_commit = bool(post_commit and post_commit != pre_commit)
   225	    dirty = _git_working_tree_dirty(target_path)
   226	
   227	    # Post-hoc verification (Claude's own verification-before-completion
   228	    # skill should have caught most things; this is our belt-and-braces)
   229	    verification = _post_session_verification(
   230	        target_path, feature, charter_bundle,
   231	    )
   232	
   233	    # Decide status
   234	    if session.success and made_commit and not dirty and verification.overall_passed:
   235	        status = StepStatus.PASSED
   236	    elif made_commit and verification.overall_passed:
   237	        # Claude might have exited with non-zero for trivial reasons; if
   238	        # the commit and verification are good, we accept.
   239	        status = StepStatus.PASSED
   240	    else:
   241	        # Something is wrong. Commit whatever is there with [BROKEN] tag
   242	        # so the next feature has context to build on.
   243	        if dirty:
   244	            _commit_broken(target_path, feature)
   245	            post_commit = _git_head(target_path)
   246	        status = StepStatus.FAILED
   247	
   248	    files_created, files_modified = _diff_since(target_path, pre_commit)
   249	
   250	    result = StepResult(
   251	        feature_id=feature.feature_id,
   252	        status=status,
   253	        build_duration_seconds=build_duration,
   254	        verify_duration_seconds=0.0,  # Claude's in-session verification is bundled into build time
   255	        repair_attempts=0,   # Claude handles repair internally via skills
   256	        verification=verification,
   257	        files_created=files_created,
   258	        files_modified=files_modified,
   259	        commit_sha=post_commit or "",
   260	        error_message=session.error or "",

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/claude_executor.py | sed -n '261,520p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   261	        builder_output=(session.final_text or "")[:2000],
   262	    )
   263	    # Persist the session cost + skills in metadata for metrics
   264	    (step_dir / "result.json").write_text(
   265	        result.model_dump_json(indent=2), encoding="utf-8",
   266	    )
   267	    (step_dir / "signals.json").write_text(json.dumps({
   268	        "success": session.success,
   269	        "made_commit": made_commit,
   270	        "dirty_after": dirty,
   271	        "skills_invoked": session.skills_invoked,
   272	        "subagents_dispatched": session.subagents_dispatched,
   273	        "codex_invocations": len(session.codex_invocations),
   274	        "tool_calls": len(session.tool_calls),
   275	        "total_cost_usd": session.total_cost_usd,
   276	        "duration_seconds": session.duration_seconds,
   277	    }, indent=2), encoding="utf-8")
   278	
   279	    return result
   280	
   281	
   282	# ---------------------------------------------------------------------------
   283	# Post-session verification (light — Claude does the heavy lifting)
   284	# ---------------------------------------------------------------------------
   285	
   286	
   287	def _post_session_verification(
   288	    target_path: Path,
   289	    feature: FeatureStep,
   290	    bundle: CharterBundle,
   291	) -> StepVerification:
   292	    """Sanity-check what Claude left behind. Not the primary gate."""
   293	    ver = StepVerification()
   294	    reasons: list[str] = []
   295	
   296	    # 1. Required files from the verification contract must all exist
   297	    for req in bundle.verification.required_files:
   298	        if not (target_path / req).exists():
   299	            reasons.append(f"required file missing: {req}")
   300	
   301	    # 2. Asset manifest must exist and cover code references
   302	    if bundle.verification.assets_manifest_required:
   303	        ok, missing = verify_manifest_covers_references(target_path, feature.feature_id)
   304	        if not ok:
   305	            if missing == ["<no-manifest>"]:
   306	                reasons.append(f"asset manifest not written for {feature.feature_id}")
   307	            else:
   308	                reasons.append(f"asset references without manifest: {missing[:5]}")
   309	
   310	    # 3. Prohibited patterns (quick grep)
   311	    patterns = bundle.verification.prohibited_patterns
   312	    if patterns:
   313	        bad = _grep_for_prohibited(target_path, patterns)
   314	        if bad:
   315	            reasons.append(f"prohibited patterns found: {bad[:5]}")
   316	
   317	    ver.failure_reasons = reasons
   318	    ver.overall_passed = not reasons
   319	    ver.prohibited_patterns = reasons if any("prohibited" in r for r in reasons) else []
   320	    return ver
   321	
   322	
   323	def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
   324	    """Grep committed files (staged tree) for prohibited patterns."""
   325	    hits: list[str] = []
   326	    try:
   327	        # Only scan files git tracks — avoids node_modules etc.
   328	        ls = subprocess.run(
   329	            ["git", "ls-files"],
   330	            cwd=str(target_path), capture_output=True, text=True, timeout=10,
   331	        )
   332	        if ls.returncode != 0:
   333	            return []
   334	        files = [f for f in ls.stdout.splitlines() if f]
   335	    except (subprocess.TimeoutExpired, FileNotFoundError):
   336	        return []
   337	
   338	    for pat in patterns:
   339	        for f in files:
   340	            # Skip binary / large files cheaply
   341	            fp = target_path / f
   342	            try:
   343	                if fp.stat().st_size > 1_000_000:
   344	                    continue
   345	                text = fp.read_text(encoding="utf-8", errors="ignore")
   346	            except OSError:
   347	                continue
   348	            if pat in text:
   349	                hits.append(f"{f} contains '{pat}'")
   350	                if len(hits) > 20:
   351	                    return hits
   352	    return hits
   353	
   354	
   355	# ---------------------------------------------------------------------------
   356	# Git helpers
   357	# ---------------------------------------------------------------------------
   358	
   359	
   360	def _git_head(target_path: Path) -> str:
   361	    try:
   362	        r = subprocess.run(
   363	            ["git", "rev-parse", "HEAD"],
   364	            cwd=str(target_path), capture_output=True, text=True, timeout=5,
   365	        )
   366	        return r.stdout.strip() if r.returncode == 0 else ""
   367	    except (subprocess.TimeoutExpired, FileNotFoundError):
   368	        return ""
   369	
   370	
   371	def _git_working_tree_dirty(target_path: Path) -> bool:
   372	    try:
   373	        r = subprocess.run(
   374	            ["git", "status", "--porcelain"],
   375	            cwd=str(target_path), capture_output=True, text=True, timeout=5,
   376	        )
   377	        return r.returncode == 0 and bool(r.stdout.strip())
   378	    except (subprocess.TimeoutExpired, FileNotFoundError):
   379	        return False
   380	
   381	
   382	def _diff_since(target_path: Path, ref: str) -> tuple[list[str], list[str]]:
   383	    if not ref:
   384	        return [], []
   385	    try:
   386	        r = subprocess.run(
   387	            ["git", "diff", "--name-status", f"{ref}..HEAD"],
   388	            cwd=str(target_path), capture_output=True, text=True, timeout=10,
   389	        )
   390	        if r.returncode != 0:
   391	            return [], []
   392	    except (subprocess.TimeoutExpired, FileNotFoundError):
   393	        return [], []
   394	
   395	    created: list[str] = []
   396	    modified: list[str] = []
   397	    for line in r.stdout.splitlines():
   398	        parts = line.split("\t")
   399	        if len(parts) < 2:
   400	            continue
   401	        flag, path = parts[0], parts[-1]
   402	        if flag == "A":
   403	            created.append(path)
   404	        elif flag in ("M", "R", "C"):
   405	            modified.append(path)
   406	    return created, modified
   407	
   408	
   409	def _commit_broken(target_path: Path, feature: FeatureStep) -> None:
   410	    try:
   411	        subprocess.run(["git", "add", "-A"],
   412	                       cwd=str(target_path), capture_output=True, timeout=10)
   413	        subprocess.run(
   414	            ["git", "commit", "-m",
   415	             f"[BROKEN] {feature.feature_id}: {feature.title}\n\n"
   416	             "Claude session did not reach a clean-tree final state. "
   417	             "Committed for recoverability."],
   418	            cwd=str(target_path), capture_output=True, timeout=10,
   419	        )
   420	    except (subprocess.TimeoutExpired, FileNotFoundError):
   421	        pass

exec
/bin/zsh -lc "nl -ba src/ncdev/dev.py | sed -n '1,260p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	#!/usr/bin/env python3
     2	"""NC Dev System — thin orchestrator for autonomous development.
     3	
     4	This module is deliberately small. It spawns a single Claude session per
     5	task and lets Claude drive everything via skills + Codex delegation. The
     6	old 5-step plan/build/verify/fix ladder is gone — Claude's
     7	:skill:`test-driven-development`, :skill:`verification-before-completion`,
     8	and :skill:`systematic-debugging` skills handle that loop internally.
     9	
    10	NC Dev's only responsibilities in this file:
    11	
    12	1. Preflight (git repo, Citex reachable, claude + codex CLIs on PATH).
    13	2. Ensure the target project is a git repo (and has a remote for greenfield).
    14	3. Compose a short task prompt referencing the project + Citex.
    15	4. Run one Claude session with full tool access (Bash so Claude can shell
    16	   to Codex, Skill so it can invoke skills, Task so it can dispatch subagents).
    17	5. Commit any dirty leftovers with ``[BROKEN]`` if Claude exited without
    18	   committing (recoverability guarantee).
    19	6. Store a short run summary in Citex.
    20	
    21	For PRD-scale work, use :mod:`ncdev.v3.engine` (full pipeline) or the
    22	``ncdev full`` command. This ``dev`` command is the freeform
    23	``--task "whatever"`` entry point.
    24	"""
    25	
    26	from __future__ import annotations
    27	
    28	import subprocess
    29	import time
    30	from datetime import datetime, timezone
    31	from pathlib import Path
    32	from typing import Any
    33	
    34	from rich.console import Console
    35	from rich.panel import Panel
    36	
    37	from ncdev.claude_session import DEFAULT_BUILD_TOOLS, run_claude_session
    38	from ncdev.preflight import require_citex
    39	
    40	console = Console()
    41	
    42	# ── Citex Integration ───────────────────────────────────────────────────
    43	CITEX_API = "http://localhost:20161"
    44	
    45	
    46	def citex_store(project_id: str, content: str, metadata: dict) -> bool:
    47	    """Store a short run summary in Citex."""
    48	    try:
    49	        import httpx
    50	        resp = httpx.post(
    51	            f"{CITEX_API}/api/v1/documents/ingest",
    52	            json={"project_id": project_id, "content": content, "metadata": metadata},
    53	            timeout=30,
    54	        )
    55	        return resp.status_code < 400
    56	    except Exception as exc:  # noqa: BLE001
    57	        raise RuntimeError(f"Failed to store context in Citex at {CITEX_API}") from exc
    58	
    59	
    60	def citex_query(project_id: str, query: str, limit: int = 10) -> str:
    61	    """Query Citex for relevant project context."""
    62	    try:
    63	        import httpx
    64	        resp = httpx.post(
    65	            f"{CITEX_API}/api/v1/retrieval/query",
    66	            json={"project_id": project_id, "query": query, "limit": limit},
    67	            timeout=30,
    68	        )
    69	        if resp.status_code < 400:
    70	            results = resp.json()
    71	            parts = []
    72	            for r in results.get("results", results.get("documents", [])):
    73	                content = r.get("content", r.get("text", ""))
    74	                if content:
    75	                    parts.append(content[:2000])
    76	            return "\n\n---\n\n".join(parts) if parts else ""
    77	    except Exception as exc:  # noqa: BLE001
    78	        raise RuntimeError(f"Failed to query Citex at {CITEX_API}") from exc
    79	    return ""
    80	
    81	
    82	# ── Git / GitHub setup ──────────────────────────────────────────────────
    83	
    84	
    85	def _ensure_git_repo(project_path: Path, mode: str) -> None:
    86	    """Ensure the project is a git repo (and has a remote for greenfield)."""
    87	    git_dir = project_path / ".git"
    88	    if not git_dir.exists():
    89	        subprocess.run(["git", "init"], cwd=str(project_path),
    90	                       capture_output=True, timeout=10)
    91	        subprocess.run(["git", "add", "-A"], cwd=str(project_path),
    92	                       capture_output=True, timeout=10)
    93	        subprocess.run(
    94	            ["git", "commit", "-q", "-m", "chore: initial commit"],
    95	            cwd=str(project_path), capture_output=True, timeout=10,
    96	        )
    97	    subprocess.run(["git", "config", "pull.rebase", "true"],
    98	                   cwd=str(project_path), capture_output=True, timeout=5)
    99	
   100	    if mode in ("greenfield", "auto"):
   101	        result = subprocess.run(
   102	            ["git", "remote", "get-url", "origin"],
   103	            cwd=str(project_path), capture_output=True, text=True, timeout=5,
   104	        )
   105	        if result.returncode != 0:
   106	            project_name = project_path.name
   107	            console.print(f"  [yellow]Creating GitHub repo: yensi-solutions/{project_name}...[/yellow]")
   108	            gh_result = subprocess.run(
   109	                ["gh", "repo", "create", f"yensi-solutions/{project_name}",
   110	                 "--private", "--source", str(project_path), "--push"],
   111	                cwd=str(project_path), capture_output=True, text=True, timeout=30,
   112	            )
   113	            if gh_result.returncode == 0:
   114	                console.print(f"  [green]✓[/green] GitHub repo created: yensi-solutions/{project_name}")
   115	            else:
   116	                subprocess.run(
   117	                    ["git", "remote", "add", "origin",
   118	                     f"git@github.com:yensi-solutions/{project_name}.git"],
   119	                    cwd=str(project_path), capture_output=True, timeout=5,
   120	                )
   121	
   122	
   123	def _git_head(project_path: Path) -> str:
   124	    r = subprocess.run(
   125	        ["git", "rev-parse", "HEAD"],
   126	        cwd=str(project_path), capture_output=True, text=True, timeout=5,
   127	    )
   128	    return r.stdout.strip() if r.returncode == 0 else ""
   129	
   130	
   131	def _git_working_tree_dirty(project_path: Path) -> bool:
   132	    r = subprocess.run(
   133	        ["git", "status", "--porcelain"],
   134	        cwd=str(project_path), capture_output=True, text=True, timeout=5,
   135	    )
   136	    return r.returncode == 0 and bool(r.stdout.strip())
   137	
   138	
   139	def _commit_broken_leftovers(project_path: Path, task: str) -> str:
   140	    """Commit leftover dirty tree with [BROKEN] tag for recoverability."""
   141	    subprocess.run(["git", "add", "-A"],
   142	                   cwd=str(project_path), capture_output=True, timeout=10)
   143	    r = subprocess.run(
   144	        ["git", "commit", "-m",
   145	         f"[BROKEN] ncdev dev: {task[:80]}\n\n"
   146	         "Claude session exited without a clean working tree. "
   147	         "Committed for recoverability."],
   148	        cwd=str(project_path), capture_output=True, timeout=10,
   149	    )
   150	    if r.returncode != 0:
   151	        return ""
   152	    return _git_head(project_path)
   153	
   154	
   155	# ── Prompt composition (short, contract-driven) ─────────────────────────
   156	
   157	
   158	def _build_task_prompt(task: str, project_path: Path, project_id: str, mode: str) -> str:
   159	    """Compose the short prompt for a freeform dev task.
   160	
   161	    Deliberately terse — the Codex protocol is injected via
   162	    ``--append-system-prompt`` by :func:`run_claude_session`, and Claude
   163	    can read the repo itself with the Read tool. We do not pre-gather
   164	    file trees or README content here; Claude is better at deciding
   165	    what to look at.
   166	    """
   167	    return f"""# Task for this ncdev dev session
   168	
   169	Mode: {mode}
   170	Project: {project_path}
   171	Citex project ID: {project_id}
   172	Citex URL: {CITEX_API}
   173	
   174	## What the user wants
   175	
   176	{task}
   177	
   178	## Your workflow
   179	
   180	You are the engineer. Drive the full cycle yourself using the skill
   181	machinery available to you. Codex is your implementation peer — see
   182	the Codex protocol in your system prompt.
   183	
   184	1. Explore the project using Read/Glob/Grep. Query Citex (via HTTP
   185	   or any CLI it exposes) for prior context.
   186	2. If this is non-trivial, use the `writing-plans` skill.
   187	3. Use `test-driven-development` for any behavioural change.
   188	4. Delegate raw implementation and test writing to Codex via Bash:
   189	   `codex exec --full-auto --sandbox danger-full-access "<scoped task>"`.
   190	5. Use `verification-before-completion` — run the project's tests,
   191	   boot the app, check a health endpoint if one exists. No claiming
   192	   done without evidence.
   193	6. On failure, use `systematic-debugging` — root-cause first, don't
   194	   loop blindly.
   195	7. Commit your work using Conventional Commits. Leave the working
   196	   tree clean.
   197	
   198	## What success looks like
   199	
   200	- Tests exist and pass for any behavioural change.
   201	- Working tree is clean, all changes committed.
   202	- One-paragraph summary in your final response.
   203	
   204	Begin.
   205	"""
   206	
   207	
   208	# ── Main Entry Point ────────────────────────────────────────────────────
   209	
   210	
   211	def run_dev(
   212	    project_path: Path,
   213	    task: str,
   214	    mode: str = "auto",
   215	    *,
   216	    model: str = "claude-opus-4-6",
   217	    timeout: int = 3600,
   218	    max_budget_usd: float | None = None,
   219	) -> dict[str, Any]:
   220	    """Run a single ncdev dev session.
   221	
   222	    This is thin glue. Claude does the actual work; NC Dev handles:
   223	    preflight, git repo setup, session orchestration, broken-tag
   224	    fallback on failure, Citex ingestion of the run summary.
   225	    """
   226	    start = time.time()
   227	    project_id = project_path.name
   228	    run_id = f"dev-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
   229	
   230	    require_citex(CITEX_API)
   231	
   232	    console.print(Panel(
   233	        f"[bold cyan]NC Dev System — thin orchestrator[/bold cyan]\n"
   234	        f"Project: {project_path}\n"
   235	        f"Task:    {task}\n"
   236	        f"Mode:    {mode}\n"
   237	        f"Run:     {run_id}",
   238	        border_style="cyan",
   239	    ))
   240	
   241	    _ensure_git_repo(project_path, mode)
   242	
   243	    pre_head = _git_head(project_path)
   244	
   245	    console.print("\n[bold]Running Claude session...[/bold]")
   246	    log_path = project_path / ".ncdev" / "runs" / run_id / "session.jsonl"
   247	    prompt = _build_task_prompt(task, project_path, project_id, mode)
   248	    session = run_claude_session(
   249	        prompt,
   250	        cwd=project_path,
   251	        tools=DEFAULT_BUILD_TOOLS,
   252	        model=model,
   253	        timeout=timeout,
   254	        permission_mode="acceptEdits",
   255	        include_codex_protocol=True,
   256	        max_budget_usd=max_budget_usd,
   257	        log_path=log_path,
   258	    )
   259	    console.print(f"  Session: {session.summary()}")
   260	

exec
/bin/zsh -lc "nl -ba src/ncdev/dev.py | sed -n '261,420p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   261	    post_head = _git_head(project_path)
   262	    dirty = _git_working_tree_dirty(project_path)
   263	    made_commit = bool(post_head and post_head != pre_head)
   264	
   265	    status = "passed"
   266	    if not session.success or not made_commit:
   267	        status = "failed"
   268	    if dirty:
   269	        # Recoverability: commit leftovers with [BROKEN]
   270	        broken_sha = _commit_broken_leftovers(project_path, task)
   271	        if broken_sha:
   272	            console.print(f"  [yellow]Committed leftovers with [BROKEN] tag: {broken_sha[:8]}[/yellow]")
   273	            post_head = broken_sha
   274	        status = "failed"
   275	
   276	    duration = time.time() - start
   277	
   278	    # Ingest short run summary to Citex (best-effort; do not fail the run)
   279	    try:
   280	        citex_store(
   281	            project_id,
   282	            content=(
   283	                f"ncdev dev run {run_id}\n"
   284	                f"Task: {task}\n"
   285	                f"Status: {status}\n"
   286	                f"Commit: {post_head[:12] if post_head else ''}\n"
   287	                f"Session: {session.summary()}\n"
   288	                f"Final response:\n{(session.final_text or '')[:2000]}"
   289	            ),
   290	            metadata={
   291	                "run_id": run_id,
   292	                "task": task[:500],
   293	                "mode": mode,
   294	                "status": status,
   295	                "commit_sha": post_head,
   296	                "skills_invoked": session.skills_invoked,
   297	                "codex_invocations": len(session.codex_invocations),
   298	                "total_cost_usd": session.total_cost_usd,
   299	                "duration_seconds": duration,
   300	                "timestamp": datetime.now(timezone.utc).isoformat(),
   301	            },
   302	        )
   303	    except Exception as exc:  # noqa: BLE001
   304	        console.print(f"  [yellow]Citex ingestion of run summary failed: {exc}[/yellow]")
   305	
   306	    console.print(Panel(
   307	        f"[bold]Status:[/bold] {status}\n"
   308	        f"[bold]Commit:[/bold] {post_head[:12] if post_head else '(none)'}\n"
   309	        f"[bold]Skills:[/bold] {', '.join(session.skills_invoked) or '(none)'}\n"
   310	        f"[bold]Codex calls:[/bold] {len(session.codex_invocations)}\n"
   311	        f"[bold]Duration:[/bold] {duration:.1f}s"
   312	        + (f"\n[bold]Cost:[/bold] ${session.total_cost_usd:.3f}"
   313	           if session.total_cost_usd is not None else ""),
   314	        title="Run complete",
   315	        border_style="green" if status == "passed" else "yellow",
   316	    ))
   317	
   318	    return {
   319	        "run_id": run_id,
   320	        "status": status,
   321	        "commit_sha": post_head,
   322	        "session_summary": session.summary(),
   323	        "skills_invoked": session.skills_invoked,
   324	        "codex_invocations": session.codex_invocations,
   325	        "total_cost_usd": session.total_cost_usd,
   326	        "duration_seconds": duration,
   327	        "final_text": session.final_text,
   328	    }

codex
I’ve got enough context to start forming opinions. The main pattern so far is “thin in intent, but still optimistic in places where it needs to be adversarial”: process IO, failure classification, hook interaction, and prompt-to-artifact validation.
exec
/bin/zsh -lc "nl -ba src/ncdev/v3/engine.py | sed -n '1,340p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""V3 Engine — sequential verified sprint pipeline (Claude-orchestrated).
     2	
     3	This is the PRD-scale entry point. Replaces the old 9-artifact discovery
     4	+ per-task-routing + parallel-builder pipeline with a thin outer loop:
     5	
     6	    Phase 1 — Preflight                        (this module)
     7	    Phase 2 — Charter generation                (v3.charter)
     8	    Phase 3 — Design system                     (v3.design_phase)
     9	    Phase 4 — Context ingestion into Citex      (v3.context_ingestion — brownfield)
    10	    Phase 5 — Sequential feature execution      (v3.claude_executor)
    11	    Phase 6 — Summary + metrics                 (this module)
    12	
    13	Each phase is a Claude session (or a no-op for greenfield/skipped cases).
    14	NC Dev itself just:
    15	
    16	    * checks preconditions (git, claude, codex, Citex)
    17	    * hands artifacts between phases
    18	    * enforces hard-fail on Phase C for greenfield UI without designs
    19	    * commits on pass, tags [BROKEN] on exhaustion
    20	    * rolls up metrics at the end
    21	
    22	The old run_v3_full() interface is preserved so the ``ncdev full`` CLI
    23	command doesn't need to change.
    24	"""
    25	
    26	from __future__ import annotations
    27	
    28	import json
    29	import time
    30	from pathlib import Path
    31	
    32	from rich.console import Console
    33	from rich.panel import Panel
    34	from rich.table import Table
    35	
    36	from ncdev.utils import make_run_id, write_json
    37	from ncdev.v3.charter import generate_charter, load_charter, write_charter
    38	from ncdev.v3.claude_executor import execute_feature_claude_driven
    39	from ncdev.v3.design_phase import run_design_phase
    40	from ncdev.v3.models import (
    41	    CharterBundle,
    42	    StepResult,
    43	    StepStatus,
    44	    V3RunState,
    45	)
    46	
    47	console = Console()
    48	
    49	
    50	def run_v3_full(
    51	    workspace: Path,
    52	    source_path: Path,
    53	    base_url: str = "http://localhost:23000",
    54	    dry_run: bool = False,
    55	    target_repo_path: Path | None = None,
    56	    run_id: str | None = None,
    57	    builder_model: str = "claude-opus-4-6",
    58	    builder_timeout: int = 3600,
    59	    max_repair_attempts: int = 2,   # retained for signature compat — unused now (Claude handles repair internally)
    60	    max_budget_usd: float | None = None,
    61	) -> V3RunState:
    62	    """Run the full V3 pipeline on a PRD.
    63	
    64	    Entry point for ``ncdev full --source <prd>``.
    65	    """
    66	    # ── Phase 1: Preflight + workspace setup ─────────────────────────────
    67	    run_id = run_id or make_run_id("v3")
    68	    run_dir = workspace / ".nc-dev" / "v2" / "runs" / run_id
    69	    outputs_dir = run_dir / "outputs"
    70	    outputs_dir.mkdir(parents=True, exist_ok=True)
    71	
    72	    state = V3RunState(
    73	        run_id=run_id,
    74	        workspace=str(workspace),
    75	        run_dir=str(run_dir),
    76	        target_path=str(target_repo_path) if target_repo_path else "",
    77	        phase="init",
    78	    )
    79	
    80	    console.print(Panel(
    81	        f"[bold cyan]NC Dev V3 — Claude-orchestrated sprint engine[/bold cyan]\n"
    82	        f"Run ID: {run_id}\n"
    83	        f"Source: {source_path}\n"
    84	        f"Target: {target_repo_path or '(greenfield)'}",
    85	        border_style="cyan",
    86	    ))
    87	
    88	    # ── Phase 2: Charter ─────────────────────────────────────────────────
    89	    state.phase = "charter"
    90	    console.print("\n[bold]Phase 2: Charter (Claude planning session)[/bold]")
    91	
    92	    if dry_run:
    93	        console.print("  [dim]Dry run — skipping charter generation[/dim]")
    94	        bundle = None
    95	    else:
    96	        bundle, charter_session = generate_charter(
    97	            prd_path=source_path,
    98	            output_dir=outputs_dir,
    99	            target_repo=target_repo_path,
   100	            model=builder_model,
   101	            max_budget_usd=max_budget_usd,
   102	            log_path=run_dir / "logs" / "charter.jsonl",
   103	        )
   104	        if bundle is None:
   105	            console.print(Panel(
   106	                f"[bold red]Charter generation failed[/bold red]\n"
   107	                f"Session: {charter_session.summary()}\n"
   108	                f"See: {outputs_dir}/charter-error.json (if present) "
   109	                f"or run log at {run_dir}/logs/charter.jsonl",
   110	                border_style="red",
   111	            ))
   112	            state.phase = "failed"
   113	            state.status = "failed"
   114	            _persist_state(state, run_dir)
   115	            return state
   116	        console.print(f"  [green]✓[/green] Charter: {len(bundle.feature_queue.features)} features queued")
   117	
   118	    # Resolve target path now that we have the charter
   119	    target_path = (
   120	        Path(bundle.contract.existing_repo_path).expanduser().resolve()
   121	        if bundle and bundle.contract.existing_repo_path
   122	        else (target_repo_path or (workspace / (bundle.contract.project_name if bundle else "project"))).resolve()
   123	    )
   124	    target_path.mkdir(parents=True, exist_ok=True)
   125	    state.target_path = str(target_path)
   126	
   127	    # ── Phase 3: Design system ───────────────────────────────────────────
   128	    state.phase = "design"
   129	    console.print("\n[bold]Phase 3: Design system[/bold]")
   130	    if dry_run or bundle is None:
   131	        console.print("  [dim]Skipped[/dim]")
   132	    else:
   133	        design = run_design_phase(
   134	            contract=bundle.contract,
   135	            target_path=target_path,
   136	            output_dir=outputs_dir,
   137	            model=builder_model,
   138	            max_budget_usd=max_budget_usd,
   139	            log_path=run_dir / "logs" / "design.jsonl",
   140	        )
   141	        if design.skipped:
   142	            console.print("  [dim]Non-UI project — design phase skipped[/dim]")
   143	        elif design.hard_failed:
   144	            console.print(Panel(
   145	                f"[bold red]Design phase HARD FAILED[/bold red]\n"
   146	                f"{design.error}\n"
   147	                f"See: {outputs_dir}/design-phase-error.json",
   148	                border_style="red",
   149	            ))
   150	            state.phase = "failed"
   151	            state.status = "failed"
   152	            _persist_state(state, run_dir)
   153	            return state
   154	        else:
   155	            src = design.design_doc.source if design.design_doc else "?"
   156	            console.print(f"  [green]✓[/green] Design system ready (source={src})")
   157	
   158	    # ── Phase 4: Brownfield context ingestion ────────────────────────────
   159	    state.phase = "ingestion"
   160	    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
   161	        console.print("\n[bold]Phase 4: Ingest existing code into Citex[/bold]")
   162	        try:
   163	            from ncdev.v3.citex_client import CitexClient
   164	            from ncdev.v3.context_ingestion import ingest_project_context
   165	            project_id = bundle.contract.project_name
   166	            citex = CitexClient(project_id=project_id)
   167	            if citex.health_check():
   168	                report = ingest_project_context(
   169	                    run_dir=run_dir,
   170	                    target_path=target_path,
   171	                    feature_queue=bundle.feature_queue,
   172	                    project_id=project_id,
   173	                )
   174	                console.print(f"  [green]✓[/green] Ingested {report.successful}/{report.total_documents} docs")
   175	            else:
   176	                console.print("  [yellow]Citex unreachable — feature builds will run without RAG grounding[/yellow]")
   177	        except Exception as exc:  # noqa: BLE001
   178	            console.print(f"  [yellow]Citex ingestion failed: {exc} — continuing without RAG[/yellow]")
   179	    else:
   180	        console.print("\n[dim]Phase 4: Context ingestion skipped (greenfield or dry run)[/dim]")
   181	
   182	    # ── Phase 5: Sequential feature execution ────────────────────────────
   183	    state.phase = "building"
   184	    completed: list[StepResult] = []
   185	
   186	    if dry_run or bundle is None:
   187	        console.print("\n[dim]Phase 5: Feature execution skipped (dry run)[/dim]")
   188	    else:
   189	        features = bundle.feature_queue.features
   190	        state.feature_queue = bundle.feature_queue
   191	        state.total_features = len(features)
   192	
   193	        # Brownfield: skip features already implemented
   194	        remaining = _filter_completed_features(target_path, features, completed)
   195	        console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
   196	
   197	        for feature in remaining:
   198	            state.current_step = feature.feature_id
   199	            _persist_state(state, run_dir)
   200	
   201	            console.print(Panel(
   202	                f"[cyan]{feature.feature_id}[/cyan] — {feature.title}",
   203	                border_style="blue",
   204	            ))
   205	
   206	            result = execute_feature_claude_driven(
   207	                feature=feature,
   208	                target_path=target_path,
   209	                run_dir=run_dir,
   210	                charter_bundle=bundle,
   211	                prior_results=completed,
   212	                project_id=bundle.contract.project_name,
   213	                model=builder_model,
   214	                timeout=builder_timeout,
   215	                max_budget_usd=max_budget_usd,
   216	            )
   217	            completed.append(result)
   218	            state.completed_steps = completed
   219	            state.completed_features = len([r for r in completed if r.status == StepStatus.PASSED])
   220	            _persist_state(state, run_dir)
   221	
   222	            status_style = "green" if result.status == StepStatus.PASSED else "red"
   223	            console.print(f"  [{status_style}]{result.status.value}[/{status_style}] — commit {result.commit_sha[:8] or '(none)'}")
   224	
   225	    # ── Phase 6: Summary ─────────────────────────────────────────────────
   226	    state.phase = "complete"
   227	    passed = [r for r in completed if r.status == StepStatus.PASSED]
   228	    failed = [r for r in completed if r.status == StepStatus.FAILED]
   229	    state.status = "passed" if not failed else ("partial" if passed else "failed")
   230	
   231	    _print_summary_table(completed)
   232	
   233	    _persist_state(state, run_dir)
   234	    return state
   235	
   236	
   237	# ---------------------------------------------------------------------------
   238	# Helpers
   239	# ---------------------------------------------------------------------------
   240	
   241	
   242	def _filter_completed_features(target_path: Path, features, completed: list[StepResult]):
   243	    """Brownfield skip: drop features already implemented in the target repo."""
   244	    try:
   245	        from ncdev.v3.state_scanner import build_skip_results, scan_completed_features
   246	    except ImportError:
   247	        return features
   248	    try:
   249	        done_ids = set(scan_completed_features(target_path, features))
   250	    except Exception:  # noqa: BLE001
   251	        return features
   252	    if not done_ids:
   253	        return features
   254	    skipped = build_skip_results(features, done_ids)
   255	    completed.extend(skipped)
   256	    remaining = [f for f in features if f.feature_id not in done_ids]
   257	    console.print(f"  [dim]Skipping {len(done_ids)} features already implemented[/dim]")
   258	    return remaining
   259	
   260	
   261	def _print_summary_table(completed: list[StepResult]) -> None:
   262	    if not completed:
   263	        return
   264	    table = Table(title="V3 Build Summary")
   265	    table.add_column("Feature", style="cyan")
   266	    table.add_column("Status", style="bold")
   267	    table.add_column("Duration", justify="right")
   268	    table.add_column("Files", justify="right")
   269	    table.add_column("Commit", justify="right")
   270	    for r in completed:
   271	        colour = {
   272	            StepStatus.PASSED: "green",
   273	            StepStatus.FAILED: "red",
   274	            StepStatus.SKIPPED: "yellow",
   275	        }.get(r.status, "white")
   276	        table.add_row(
   277	            r.feature_id,
   278	            f"[{colour}]{r.status.value}[/{colour}]",
   279	            f"{r.build_duration_seconds:.0f}s",
   280	            str(len(r.files_created) + len(r.files_modified)),
   281	            r.commit_sha[:8] if r.commit_sha else "",
   282	        )
   283	    console.print(table)
   284	
   285	
   286	def _persist_state(state: V3RunState, run_dir: Path) -> None:
   287	    run_dir.mkdir(parents=True, exist_ok=True)
   288	    (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")

exec
/bin/zsh -lc "nl -ba scripts/ncdev-hooks/pre_bash_guard.py | sed -n '1,280p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	#!/usr/bin/env python3
     2	"""Claude Code PreToolUse hook — guards ``Bash`` commands.
     3	
     4	Wired in via ``scripts/ncdev-hooks/settings.json`` when NC Dev spawns a
     5	Claude session.  Runs on every Bash tool call and enforces:
     6	
     7	    * ``git commit`` commands cannot land files containing prohibited
     8	      patterns (TODO, FIXME, console.log, bare ``except: pass``,
     9	      "Not yet implemented") in the staged tree.
    10	    * ``git commit`` messages must follow Conventional Commits
    11	      (feat/fix/test/chore/refactor/docs/perf/style/build/ci/revert).
    12	    * ``git push --force`` to protected branches (main/master) is blocked
    13	      unless the user-level allowlist env var is set.
    14	
    15	The hook reads a JSON event from stdin with the tool name and input,
    16	writes a decision JSON to stdout, and exits 0 always — the decision
    17	(allow/block + reason) is conveyed in the JSON body so Claude sees
    18	the structured feedback.
    19	"""
    20	
    21	from __future__ import annotations
    22	
    23	import json
    24	import os
    25	import re
    26	import subprocess
    27	import sys
    28	from pathlib import Path
    29	from typing import Iterable
    30	
    31	# Default prohibited patterns — may be overridden per-project by placing
    32	# a JSON file at $NCDEV_HOOKS_CONFIG.
    33	DEFAULT_PROHIBITED: tuple[str, ...] = (
    34	    "TODO",
    35	    "FIXME",
    36	    "console.log(",
    37	    "Not yet implemented",
    38	    "Coming soon",
    39	)
    40	
    41	CONVENTIONAL_RE = re.compile(
    42	    r"^(feat|fix|test|chore|refactor|docs|perf|style|build|ci|revert)"
    43	    r"(\([^)]+\))?:\s+.+",
    44	    re.MULTILINE,
    45	)
    46	
    47	
    48	def _emit(decision: str, reason: str = "") -> None:
    49	    """Write hook decision JSON and exit cleanly."""
    50	    payload = {"decision": decision}
    51	    if reason:
    52	        payload["reason"] = reason
    53	    sys.stdout.write(json.dumps(payload) + "\n")
    54	    sys.exit(0)
    55	
    56	
    57	def _load_prohibited() -> tuple[str, ...]:
    58	    config_path = os.environ.get("NCDEV_HOOKS_CONFIG")
    59	    if config_path and Path(config_path).exists():
    60	        try:
    61	            cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    62	            pats = cfg.get("prohibited_patterns")
    63	            if isinstance(pats, list) and all(isinstance(p, str) for p in pats):
    64	                return tuple(pats)
    65	        except Exception:  # noqa: BLE001
    66	            pass
    67	    return DEFAULT_PROHIBITED
    68	
    69	
    70	def _staged_file_list(cwd: str | None) -> list[str]:
    71	    r = subprocess.run(
    72	        ["git", "diff", "--cached", "--name-only"],
    73	        cwd=cwd, capture_output=True, text=True, timeout=5,
    74	    )
    75	    if r.returncode != 0:
    76	        return []
    77	    return [line for line in r.stdout.splitlines() if line]
    78	
    79	
    80	def _check_staged_for_prohibited(
    81	    cwd: str | None, patterns: Iterable[str],
    82	) -> list[str]:
    83	    """Return a list of '<file>:<pattern>' violations found in staged diff."""
    84	    hits: list[str] = []
    85	    for path in _staged_file_list(cwd):
    86	        # Diff the staged content only — we want to catch what's about
    87	        # to land, not what's already in HEAD.
    88	        r = subprocess.run(
    89	            ["git", "diff", "--cached", "--", path],
    90	            cwd=cwd, capture_output=True, text=True, timeout=5,
    91	        )
    92	        if r.returncode != 0:
    93	            continue
    94	        # Only inspect added lines (prefixed with "+" but not "+++").
    95	        added = [
    96	            line[1:] for line in r.stdout.splitlines()
    97	            if line.startswith("+") and not line.startswith("+++")
    98	        ]
    99	        blob = "\n".join(added)
   100	        for pat in patterns:
   101	            if pat in blob:
   102	                hits.append(f"{path}:{pat}")
   103	                if len(hits) > 20:
   104	                    return hits
   105	    return hits
   106	
   107	
   108	def _extract_commit_message(cmd: str) -> str | None:
   109	    """Pull the -m argument out of a git-commit command. Best effort."""
   110	    # Naive: look for -m "..." or -m '...'. If the user uses HEREDOC
   111	    # ($(cat <<...)) we cannot cheaply parse it; allow those through.
   112	    m = re.search(r"""-m\s+(['"])(.+?)\1""", cmd, flags=re.DOTALL)
   113	    if m:
   114	        return m.group(2)
   115	    return None
   116	
   117	
   118	def _is_force_push_to_protected(cmd: str) -> bool:
   119	    if "git push" not in cmd:
   120	        return False
   121	    if "--force" not in cmd and "-f " not in cmd and not cmd.rstrip().endswith("-f"):
   122	        return False
   123	    # protected refs
   124	    for ref in ("main", "master", "production", "prod"):
   125	        if re.search(rf"\b{ref}\b", cmd):
   126	            return True
   127	    return False
   128	
   129	
   130	def evaluate(tool_name: str, tool_input: dict, cwd: str | None = None) -> tuple[str, str]:
   131	    """Pure evaluator — given a tool call, return (decision, reason).
   132	
   133	    decision is "allow" or "block". Split out for unit testing; the
   134	    main entry point wraps this in stdin/stdout plumbing.
   135	    """
   136	    if tool_name != "Bash":
   137	        return "allow", ""
   138	
   139	    cmd = str(tool_input.get("command", ""))
   140	    if not cmd:
   141	        return "allow", ""
   142	
   143	    # Force-push protection
   144	    if _is_force_push_to_protected(cmd):
   145	        if os.environ.get("NCDEV_ALLOW_FORCE_PUSH") != "1":
   146	            return "block", (
   147	                "Force-push to a protected branch. Set "
   148	                "NCDEV_ALLOW_FORCE_PUSH=1 in the environment to override, "
   149	                "or push to a feature branch instead."
   150	            )
   151	
   152	    # Only inspect git-commit commands for the remaining rules
   153	    if "git commit" not in cmd:
   154	        return "allow", ""
   155	
   156	    # 1. Conventional Commits message shape
   157	    msg = _extract_commit_message(cmd)
   158	    if msg is not None:
   159	        if not CONVENTIONAL_RE.search(msg):
   160	            return "block", (
   161	                "Commit message does not follow Conventional Commits "
   162	                "(feat|fix|test|chore|refactor|docs|perf|style|build|ci|revert). "
   163	                f"Got: {msg.splitlines()[0][:120]!r}"
   164	            )
   165	
   166	    # 2. Prohibited patterns in staged content
   167	    patterns = _load_prohibited()
   168	    hits = _check_staged_for_prohibited(cwd, patterns)
   169	    if hits:
   170	        preview = ", ".join(hits[:5])
   171	        return "block", (
   172	            f"Staged changes contain prohibited patterns: {preview}"
   173	            + (" (and more)" if len(hits) > 5 else "")
   174	            + ". Remove them before committing."
   175	        )
   176	
   177	    return "allow", ""
   178	
   179	
   180	def main() -> None:
   181	    try:
   182	        event = json.load(sys.stdin)
   183	    except json.JSONDecodeError:
   184	        _emit("allow")
   185	
   186	    tool = event.get("tool_name") or event.get("tool") or ""
   187	    inp = event.get("tool_input") or event.get("input") or {}
   188	    cwd = event.get("cwd")
   189	
   190	    decision, reason = evaluate(tool, inp, cwd)
   191	    _emit(decision, reason)
   192	
   193	
   194	if __name__ == "__main__":
   195	    main()

exec
/bin/zsh -lc "nl -ba src/ncdev/v2/config.py | sed -n '1,320p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	from __future__ import annotations
     2	
     3	from pathlib import Path
     4	
     5	import yaml
     6	from pydantic import BaseModel, Field, model_validator
     7	
     8	from ncdev.v2.models import TaskType
     9	
    10	
    11	# ---------------------------------------------------------------------------
    12	# Routing task keys — single source of truth for RoutingConfig fields.
    13	# ---------------------------------------------------------------------------
    14	
    15	ROUTING_TASK_KEYS: tuple[str, ...] = (
    16	    "source_ingest",
    17	    "repo_analysis",
    18	    "market_research",
    19	    "feature_extraction",
    20	    "design_brief",
    21	    "implementation",
    22	    "test_authoring",
    23	    "review",
    24	    "second_opinion",
    25	    "sentinel_reproduce",
    26	    "sentinel_fix",
    27	)
    28	
    29	
    30	def _uniform_preset(provider: str) -> dict[str, list[str]]:
    31	    return {key: [provider] for key in ROUTING_TASK_KEYS}
    32	
    33	
    34	# Named presets. Flipping `NCDevV2Config.mode` picks one. "custom" leaves
    35	# RoutingConfig untouched so users can hand-tune it.
    36	MODE_PRESETS: dict[str, dict[str, list[str]]] = {
    37	    "codex_only": _uniform_preset("openai_codex"),
    38	    "claude_only": _uniform_preset("anthropic_claude_code"),
    39	    "openrouter": _uniform_preset("openrouter"),
    40	    "claude_plan_codex_build": {
    41	        "source_ingest": ["anthropic_claude_code"],
    42	        "repo_analysis": ["anthropic_claude_code"],
    43	        "market_research": ["anthropic_claude_code"],
    44	        "feature_extraction": ["anthropic_claude_code"],
    45	        "design_brief": ["anthropic_claude_code"],
    46	        "implementation": ["openai_codex"],
    47	        "test_authoring": ["openai_codex"],
    48	        "review": ["anthropic_claude_code"],
    49	        "second_opinion": ["anthropic_claude_code"],
    50	        "sentinel_reproduce": ["anthropic_claude_code"],
    51	        "sentinel_fix": ["openai_codex"],
    52	    },
    53	    "custom": {},
    54	}
    55	
    56	DEFAULT_MODE = "claude_plan_codex_build"
    57	
    58	
    59	class ProviderPreferenceConfig(BaseModel):
    60	    enabled: bool = True
    61	    preferred_models: dict[str, str] = Field(default_factory=dict)
    62	    defaults: dict[str, str] = Field(default_factory=dict)
    63	    features: dict[str, bool] = Field(default_factory=dict)
    64	
    65	
    66	class RoutingConfig(BaseModel):
    67	    source_ingest: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    68	    repo_analysis: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    69	    market_research: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    70	    feature_extraction: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    71	    design_brief: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    72	    implementation: list[str] = Field(default_factory=lambda: ["openai_codex"])
    73	    test_authoring: list[str] = Field(default_factory=lambda: ["openai_codex"])
    74	    review: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    75	    second_opinion: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    76	    sentinel_reproduce: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    77	    sentinel_fix: list[str] = Field(default_factory=lambda: ["openai_codex"])
    78	
    79	    def providers_for(self, task_type: TaskType) -> list[str]:
    80	        mapping = {
    81	            TaskType.SOURCE_INGEST: self.source_ingest,
    82	            TaskType.REPO_ANALYSIS: self.repo_analysis,
    83	            TaskType.MARKET_RESEARCH: self.market_research,
    84	            TaskType.FEATURE_EXTRACTION: self.feature_extraction,
    85	            TaskType.DESIGN_BRIEF: self.design_brief,
    86	            TaskType.BUILD_BATCH: self.implementation,
    87	            TaskType.TEST_AUTHORING: self.test_authoring,
    88	            TaskType.SENTINEL_REPRODUCE: self.sentinel_reproduce,
    89	            TaskType.SENTINEL_FIX: self.sentinel_fix,
    90	        }
    91	        return mapping.get(task_type, self.review)
    92	
    93	
    94	class SentinelServiceConfig(BaseModel):
    95	    repo_path: str = ""
    96	    git_remote: str = ""
    97	    default_branch: str = "main"
    98	    language: str = "python"
    99	    test_commands: dict[str, str] = Field(default_factory=dict)
   100	    pr_labels: list[str] = Field(default_factory=lambda: ["sentinel-auto", "bug"])
   101	    auto_deploy: bool = False
   102	
   103	
   104	class SentinelIntakeConfig(BaseModel):
   105	    enabled: bool = True
   106	    port: int = 16650
   107	    api_key: str = ""
   108	    max_concurrent_runs: int = 3
   109	    queue_max_size: int = 50
   110	
   111	
   112	class SentinelRateLimitConfig(BaseModel):
   113	    max_fixes_per_hour: int = 10
   114	    max_fixes_per_service_per_hour: int = 5
   115	    cooldown_after_failure_seconds: int = 300
   116	
   117	
   118	class SentinelCallbackConfig(BaseModel):
   119	    enabled: bool = True
   120	    url: str = ""
   121	    api_key: str = ""
   122	    retry_count: int = 3
   123	    retry_delay_seconds: int = 5
   124	
   125	
   126	class SentinelGitConfig(BaseModel):
   127	    branch_prefix: str = "sentinel/fix/"
   128	    commit_prefix: str = "[sentinel-fix]"
   129	    pr_label: str = "sentinel-auto"
   130	
   131	
   132	class SentinelConfig(BaseModel):
   133	    intake: SentinelIntakeConfig = Field(default_factory=SentinelIntakeConfig)
   134	    rate_limits: SentinelRateLimitConfig = Field(default_factory=SentinelRateLimitConfig)
   135	    services: dict[str, SentinelServiceConfig] = Field(default_factory=dict)
   136	    callback: SentinelCallbackConfig = Field(default_factory=SentinelCallbackConfig)
   137	    git: SentinelGitConfig = Field(default_factory=SentinelGitConfig)
   138	
   139	
   140	class QualityGateConfig(BaseModel):
   141	    require_local_harness: bool = True
   142	    require_artifacts: bool = True
   143	    require_human_release: bool = True
   144	
   145	
   146	class NCDevV2Config(BaseModel):
   147	    mode: str = Field(
   148	        default=DEFAULT_MODE,
   149	        description=(
   150	            "Named routing preset. One of: "
   151	            + ", ".join(sorted(MODE_PRESETS.keys()))
   152	            + ". Flipping this is the main budget switch — "
   153	            "claude_plan_codex_build (default) uses Claude for planning + "
   154	            "review and delegates implementation to Codex via Bash; "
   155	            "codex_only skips Claude entirely for token-lean days; "
   156	            "claude_only keeps everything on Claude; openrouter routes all "
   157	            "tasks through the OpenRouter API. Use 'custom' to hand-tune."
   158	        ),
   159	    )
   160	    providers: dict[str, ProviderPreferenceConfig] = Field(
   161	        default_factory=lambda: {
   162	            "anthropic_claude_code": ProviderPreferenceConfig(
   163	                enabled=True,
   164	                preferred_models={"planning": "opus", "review": "opus"},
   165	                features={"use_subagents": True, "use_hooks": True, "use_mcp": True},
   166	            ),
   167	            "openai_codex": ProviderPreferenceConfig(
   168	                enabled=True,
   169	                preferred_models={"implementation": "gpt-5.4", "test_implementation": "gpt-5.4"},
   170	                defaults={"reasoning_effort": "high"},
   171	            ),
   172	            "openrouter": ProviderPreferenceConfig(
   173	                enabled=False,
   174	                preferred_models={"planning": "anthropic/claude-opus-4-6"},
   175	                defaults={"base_url": "https://openrouter.ai/api/v1"},
   176	            ),
   177	            "gemini_cli": ProviderPreferenceConfig(enabled=False),
   178	        }
   179	    )
   180	    routing: RoutingConfig = Field(default_factory=RoutingConfig)
   181	    quality_gates: QualityGateConfig = Field(default_factory=QualityGateConfig)
   182	    sentinel: SentinelConfig = Field(default_factory=SentinelConfig)
   183	
   184	    @model_validator(mode="after")
   185	    def _apply_mode_preset(self) -> "NCDevV2Config":
   186	        preset = MODE_PRESETS.get(self.mode)
   187	        if preset is None:
   188	            raise ValueError(
   189	                f"Unknown mode '{self.mode}'. Known modes: "
   190	                + ", ".join(sorted(MODE_PRESETS.keys()))
   191	            )
   192	        if not preset:
   193	            # "custom" — leave RoutingConfig as declared.
   194	            return self
   195	        for field, providers in preset.items():
   196	            setattr(self.routing, field, list(providers))
   197	        return self
   198	
   199	    def to_yaml_dict(self) -> dict[str, object]:
   200	        return self.model_dump(mode="python")
   201	
   202	
   203	def load_v2_config(workspace: Path) -> NCDevV2Config:
   204	    config_path = workspace / ".nc-dev" / "v2" / "config.yaml"
   205	    if not config_path.exists():
   206	        return NCDevV2Config()
   207	    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
   208	    return NCDevV2Config.model_validate(raw)
   209	
   210	
   211	def ensure_default_v2_config(workspace: Path) -> NCDevV2Config:
   212	    workspace.mkdir(parents=True, exist_ok=True)
   213	    config = load_v2_config(workspace)
   214	    config_path = workspace / ".nc-dev" / "v2" / "config.yaml"
   215	    config_path.parent.mkdir(parents=True, exist_ok=True)
   216	    if not config_path.exists():
   217	        yaml.safe_dump(config.to_yaml_dict(), config_path.open("w", encoding="utf-8"), sort_keys=False)
   218	    return config

exec
/bin/zsh -lc "find tests -maxdepth 3 -type f | sort | sed -n '1,240p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
tests/__init__.py
tests/__pycache__/__init__.cpython-313.pyc
tests/__pycache__/__init__.cpython-314.pyc
tests/__pycache__/conftest.cpython-313-pytest-8.4.2.pyc
tests/__pycache__/conftest.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/conftest.cpython-314-pytest-8.4.2.pyc
tests/__pycache__/test_cli.cpython-313-pytest-8.4.2.pyc
tests/__pycache__/test_cli.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_cli.cpython-314-pytest-8.4.2.pyc
tests/__pycache__/test_config.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_memory.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_pipeline.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_preflight.cpython-313-pytest-8.4.2.pyc
tests/__pycache__/test_preflight.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_preflight.cpython-314-pytest-8.4.2.pyc
tests/__pycache__/test_utils.cpython-313-pytest-9.0.3.pyc
tests/conftest.py
tests/fixtures/.gitkeep
tests/fixtures/sample-requirements.md
tests/fixtures/sample_requirements.md
tests/fixtures/sentinel_reports/backend_error.json
tests/fixtures/sentinel_reports/frontend_error.json
tests/integration/__pycache__/test_quality_gate_e2e.cpython-313-pytest-8.4.2.pyc
tests/integration/__pycache__/test_quality_gate_e2e.cpython-314-pytest-8.4.2.pyc
tests/integration/test_quality_gate_e2e.py
tests/test_cli.py
tests/test_ncdev_v2/__init__.py
tests/test_ncdev_v2/__pycache__/__init__.cpython-313.pyc
tests/test_ncdev_v2/__pycache__/__init__.cpython-314.pyc
tests/test_ncdev_v2/__pycache__/test_intake_api.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_intake_api.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_intake_api.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_modes.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_callback.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_callback.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_callback.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_cli.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_cli.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_cli.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_config.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_config.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_config.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_engine.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_engine.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_engine.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_models.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_models.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_models.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_prompts.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_prompts.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_prompts.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_safety.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_safety.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_sentinel_safety.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_v2_adapters.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_v2_adapters.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_v2_adapters.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_v2_config.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_v2_config.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_v2_config.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_v2_execution.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_v2_execution.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_v2_execution.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_v2_routing.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v2/__pycache__/test_v2_routing.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v2/__pycache__/test_v2_routing.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v2/test_intake_api.py
tests/test_ncdev_v2/test_modes.py
tests/test_ncdev_v2/test_sentinel_callback.py
tests/test_ncdev_v2/test_sentinel_cli.py
tests/test_ncdev_v2/test_sentinel_config.py
tests/test_ncdev_v2/test_sentinel_engine.py
tests/test_ncdev_v2/test_sentinel_models.py
tests/test_ncdev_v2/test_sentinel_prompts.py
tests/test_ncdev_v2/test_sentinel_safety.py
tests/test_ncdev_v2/test_v2_adapters.py
tests/test_ncdev_v2/test_v2_config.py
tests/test_ncdev_v2/test_v2_routing.py
tests/test_ncdev_v3/__init__.py
tests/test_ncdev_v3/__pycache__/__init__.cpython-313.pyc
tests/test_ncdev_v3/__pycache__/__init__.cpython-314.pyc
tests/test_ncdev_v3/__pycache__/test_citex_client.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v3/__pycache__/test_citex_client.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v3/__pycache__/test_citex_client.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v3/__pycache__/test_context_ingestion.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v3/__pycache__/test_context_ingestion.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v3/__pycache__/test_context_ingestion.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v3/__pycache__/test_metrics.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v3/__pycache__/test_metrics.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v3/__pycache__/test_metrics.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v3/__pycache__/test_prompt_builder.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v3/__pycache__/test_prompt_builder.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v3/__pycache__/test_prompt_builder.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v3/__pycache__/test_state_scanner.cpython-313-pytest-8.4.2.pyc
tests/test_ncdev_v3/__pycache__/test_state_scanner.cpython-313-pytest-9.0.3.pyc
tests/test_ncdev_v3/__pycache__/test_state_scanner.cpython-314-pytest-8.4.2.pyc
tests/test_ncdev_v3/test_citex_client.py
tests/test_ncdev_v3/test_context_ingestion.py
tests/test_ncdev_v3/test_metrics.py
tests/test_ncdev_v3/test_state_scanner.py
tests/test_preflight.py
tests/unit/__pycache__/test_ai_provider.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_ai_provider.cpython-314-pytest-8.4.2.pyc
tests/unit/__pycache__/test_asset_manifest.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_charter.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_claude_executor.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_claude_session.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_design_phase.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_dev.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_dev.cpython-314-pytest-8.4.2.pyc
tests/unit/__pycache__/test_hooks.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_manifest_generator.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_manifest_generator.cpython-314-pytest-8.4.2.pyc
tests/unit/__pycache__/test_orchestrator.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_orchestrator.cpython-314-pytest-8.4.2.pyc
tests/unit/__pycache__/test_quality_gate_events.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_quality_gate_events.cpython-314-pytest-8.4.2.pyc
tests/unit/__pycache__/test_quality_gate_models.cpython-313-pytest-8.4.2.pyc
tests/unit/__pycache__/test_quality_gate_models.cpython-314-pytest-8.4.2.pyc
tests/unit/test_ai_provider.py
tests/unit/test_asset_manifest.py
tests/unit/test_charter.py
tests/unit/test_claude_executor.py
tests/unit/test_claude_session.py
tests/unit/test_design_phase.py
tests/unit/test_dev.py
tests/unit/test_hooks.py
tests/unit/test_manifest_generator.py
tests/unit/test_orchestrator.py
tests/unit/test_quality_gate_events.py
tests/unit/test_quality_gate_models.py

exec
/bin/zsh -lc 'rg -n "claude_session|design_phase|asset_manifest|claude_executor|pre_bash_guard|v2.config|run_dev|engine" tests -S' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
tests/test_ncdev_v2/test_v2_routing.py:2:from ncdev.v2.config import NCDevV2Config
tests/test_ncdev_v2/test_sentinel_config.py:3:from ncdev.v2.config import (
tests/test_ncdev_v2/test_sentinel_config.py:6:    ensure_default_v2_config,
tests/test_ncdev_v2/test_sentinel_config.py:7:    load_v2_config,
tests/test_ncdev_v2/test_sentinel_config.py:42:    config = ensure_default_v2_config(tmp_path)
tests/test_ncdev_v2/test_sentinel_config.py:43:    loaded = load_v2_config(tmp_path)
tests/test_ncdev_v2/test_sentinel_config.py:52:    config = ensure_default_v2_config(tmp_path)
tests/test_ncdev_v2/test_sentinel_config.py:58:    config = ensure_default_v2_config(tmp_path)
tests/test_ncdev_v2/test_v2_config.py:3:from ncdev.v2.config import ensure_default_v2_config, load_v2_config
tests/test_ncdev_v2/test_v2_config.py:7:def test_v2_config_roundtrip(tmp_path: Path) -> None:
tests/test_ncdev_v2/test_v2_config.py:8:    config = ensure_default_v2_config(tmp_path)
tests/test_ncdev_v2/test_v2_config.py:9:    loaded = load_v2_config(tmp_path)
tests/test_ncdev_v2/test_modes.py:1:"""Tests for the `mode` switch + MODE_PRESETS in v2 config."""
tests/test_ncdev_v2/test_modes.py:10:from ncdev.v2.config import (
tests/test_ncdev_v2/test_modes.py:15:    load_v2_config,
tests/test_ncdev_v2/test_modes.py:98:    loaded = load_v2_config(tmp_path)
tests/test_ncdev_v2/test_modes.py:109:    loaded = load_v2_config(tmp_path)
tests/test_ncdev_v2/test_sentinel_engine.py:8:from ncdev.v2.engine import run_v2_fix
tests/unit/test_claude_executor.py:11:from ncdev.claude_session import ClaudeSessionResult
tests/unit/test_claude_executor.py:12:from ncdev.v3.asset_manifest import save_feature_manifest
tests/unit/test_claude_executor.py:13:from ncdev.v3.claude_executor import (
tests/unit/test_claude_executor.py:154:    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
tests/unit/test_claude_executor.py:189:    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
tests/unit/test_claude_executor.py:213:    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
tests/unit/test_claude_executor.py:232:def test_missing_asset_manifest_causes_verification_failure(tmp_path: Path):
tests/unit/test_claude_executor.py:248:    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
tests/unit/test_claude_executor.py:278:    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
tests/unit/test_claude_executor.py:305:    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
tests/unit/test_asset_manifest.py:10:from ncdev.v3.asset_manifest import (
tests/unit/test_charter.py:11:from ncdev.claude_session import ClaudeSessionResult
tests/unit/test_charter.py:157:    with patch("ncdev.v3.charter.run_claude_session", side_effect=fake_session):
tests/unit/test_charter.py:182:    with patch("ncdev.v3.charter.run_claude_session", side_effect=fake_session):
tests/unit/test_charter.py:201:    with patch("ncdev.v3.charter.run_claude_session", side_effect=fake_session):
tests/unit/test_charter.py:222:    with patch("ncdev.v3.charter.run_claude_session", side_effect=fake_session):
tests/unit/test_charter.py:240:    with patch("ncdev.v3.charter.run_claude_session", side_effect=fake_session):
tests/unit/test_claude_session.py:19:from ncdev import claude_session
tests/unit/test_claude_session.py:20:from ncdev.claude_session import (
tests/unit/test_claude_session.py:24:    run_claude_session,
tests/unit/test_claude_session.py:78:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:79:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:80:            run_claude_session(
tests/unit/test_claude_session.py:114:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:115:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:116:            run_claude_session(
tests/unit/test_claude_session.py:132:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:133:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:134:            run_claude_session(
tests/unit/test_claude_session.py:155:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:156:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:157:            run_claude_session(
tests/unit/test_claude_session.py:198:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:199:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:200:            result = run_claude_session(
tests/unit/test_claude_session.py:227:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:228:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:229:            result = run_claude_session("x", cwd=tmp_path, include_codex_protocol=False)
tests/unit/test_claude_session.py:240:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:241:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:242:            result = run_claude_session("x", cwd=tmp_path, include_codex_protocol=False)
tests/unit/test_claude_session.py:258:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:259:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:260:            run_claude_session(
tests/unit/test_claude_session.py:274:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:275:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:276:            result = run_claude_session(
tests/unit/test_claude_session.py:290:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:291:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:292:            run_claude_session(
tests/unit/test_claude_session.py:313:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:314:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:315:            result = run_claude_session(
tests/unit/test_claude_session.py:328:    with patch("ncdev.claude_session.shutil.which", return_value=None):
tests/unit/test_claude_session.py:329:        result = run_claude_session("x", cwd=tmp_path)
tests/unit/test_claude_session.py:339:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:340:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:341:            result = run_claude_session(
tests/unit/test_claude_session.py:356:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:357:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:358:            run_claude_session(
tests/unit/test_claude_session.py:370:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:371:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:372:            run_claude_session(
tests/unit/test_claude_session.py:384:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:385:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:386:            run_claude_session(
tests/unit/test_claude_session.py:409:    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
tests/unit/test_claude_session.py:410:        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
tests/unit/test_claude_session.py:411:            result = run_claude_session(
tests/unit/test_hooks.py:1:"""Tests for Phase H hooks — pre_bash_guard.evaluate()."""
tests/unit/test_hooks.py:14:import pre_bash_guard  # noqa: E402
tests/unit/test_hooks.py:40:    decision, reason = pre_bash_guard.evaluate("Edit", {"file_path": "x"}, cwd=str(tmp_path))
tests/unit/test_hooks.py:46:    decision, _ = pre_bash_guard.evaluate("Bash", {"command": ""}, cwd=str(tmp_path))
tests/unit/test_hooks.py:51:    decision, _ = pre_bash_guard.evaluate("Bash", {"command": "ls -la"}, cwd=str(tmp_path))
tests/unit/test_hooks.py:53:    decision, _ = pre_bash_guard.evaluate("Bash", {"command": "pytest -q"}, cwd=str(tmp_path))
tests/unit/test_hooks.py:74:    decision, reason = pre_bash_guard.evaluate("Bash", {"command": cmd}, cwd=str(tmp_path))
tests/unit/test_hooks.py:87:    decision, reason = pre_bash_guard.evaluate("Bash", {"command": cmd}, cwd=str(tmp_path))
tests/unit/test_hooks.py:95:    decision, _ = pre_bash_guard.evaluate(
tests/unit/test_hooks.py:112:    decision, reason = pre_bash_guard.evaluate(
tests/unit/test_hooks.py:126:    decision, reason = pre_bash_guard.evaluate(
tests/unit/test_hooks.py:140:    decision, reason = pre_bash_guard.evaluate(
tests/unit/test_hooks.py:161:    decision, reason = pre_bash_guard.evaluate(
tests/unit/test_hooks.py:176:    decision, reason = pre_bash_guard.evaluate(
tests/unit/test_hooks.py:187:    decision, _ = pre_bash_guard.evaluate(
tests/unit/test_hooks.py:197:    decision, _ = pre_bash_guard.evaluate(
tests/unit/test_hooks.py:219:    decision, reason = pre_bash_guard.evaluate(
tests/unit/test_dev.py:12:from ncdev.claude_session import ClaudeSessionResult
tests/unit/test_dev.py:66:def test_run_dev_passes_when_session_commits_cleanly(tmp_path: Path):
tests/unit/test_dev.py:83:    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
tests/unit/test_dev.py:84:        result = dev.run_dev(project, task="add foo", mode="auto")
tests/unit/test_dev.py:106:    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
tests/unit/test_dev.py:107:        result = dev.run_dev(project, task="try something", mode="auto")
tests/unit/test_dev.py:128:    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
tests/unit/test_dev.py:129:        result = dev.run_dev(project, task="x", mode="auto")
tests/unit/test_dev.py:153:    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
tests/unit/test_dev.py:154:        dev.run_dev(project, task="x", max_budget_usd=1.25)
tests/unit/test_dev.py:188:    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
tests/unit/test_dev.py:189:        dev.run_dev(project, task="do a thing", mode="enhance")
tests/unit/test_design_phase.py:11:from ncdev.claude_session import ClaudeSessionResult
tests/unit/test_design_phase.py:12:from ncdev.v3.design_phase import (
tests/unit/test_design_phase.py:17:    run_design_phase,
tests/unit/test_design_phase.py:85:def test_cli_project_skips_design_phase(tmp_path: Path):
tests/unit/test_design_phase.py:87:    result = run_design_phase(contract, tmp_path, tmp_path / "out")
tests/unit/test_design_phase.py:102:    result = run_design_phase(
tests/unit/test_design_phase.py:147:    with patch("ncdev.v3.design_phase.run_claude_session", side_effect=fake_session):
tests/unit/test_design_phase.py:148:        result = run_design_phase(
tests/unit/test_design_phase.py:185:    with patch("ncdev.v3.design_phase.run_claude_session", side_effect=fake_session):
tests/unit/test_design_phase.py:186:        result = run_design_phase(
tests/unit/test_design_phase.py:211:    with patch("ncdev.v3.design_phase.run_claude_session", side_effect=fake_session):
tests/unit/test_design_phase.py:212:        result = run_design_phase(
tests/unit/test_design_phase.py:243:    with patch("ncdev.v3.design_phase.run_claude_session", side_effect=fake_session):
tests/unit/test_design_phase.py:244:        result = run_design_phase(
tests/unit/test_design_phase.py:271:    with patch("ncdev.v3.design_phase.run_claude_session", side_effect=fake_session):
tests/unit/test_design_phase.py:272:        run_design_phase(

codex
`python -m pytest -q` does not run in this environment because `python` resolves to Python 2.7 without `pytest`. I’m checking the relevant unit tests with `python3` separately so the review isn’t based on a false green.
exec
/bin/zsh -lc "nl -ba tests/unit/test_claude_session.py | sed -n '1,520p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Tests for the Claude session runner primitive.
     2	
     3	The runner shells out to the real ``claude`` CLI, so these tests fake the
     4	subprocess layer. They verify:
     5	- The command is composed correctly (tools, model, system prompt, budget)
     6	- Stream-json events are parsed into structured signals (tool calls,
     7	  skills invoked, codex shell-outs, files touched)
     8	- Timeouts, missing CLI, and non-zero exits produce well-formed results
     9	"""
    10	
    11	from __future__ import annotations
    12	
    13	import json
    14	from pathlib import Path
    15	from unittest.mock import patch
    16	
    17	import pytest
    18	
    19	from ncdev import claude_session
    20	from ncdev.claude_session import (
    21	    ClaudeSessionResult,
    22	    DEFAULT_BUILD_TOOLS,
    23	    DEFAULT_PLAN_TOOLS,
    24	    run_claude_session,
    25	)
    26	
    27	
    28	# ---------------------------------------------------------------------------
    29	# Fakes
    30	# ---------------------------------------------------------------------------
    31	
    32	
    33	class _FakeProc:
    34	    """Minimal stand-in for subprocess.Popen."""
    35	
    36	    def __init__(self, stdout_lines: list[str], returncode: int = 0, stderr: str = ""):
    37	        self._stdout_lines = stdout_lines
    38	        self.returncode = returncode
    39	        self.stdout = iter(stdout_lines)
    40	        self.stderr = _FakeStderr(stderr)
    41	
    42	    def wait(self, timeout=None):  # noqa: ARG002
    43	        return self.returncode
    44	
    45	    def kill(self):
    46	        pass
    47	
    48	
    49	class _FakeStderr:
    50	    def __init__(self, text: str):
    51	        self._text = text
    52	
    53	    def read(self) -> str:
    54	        return self._text
    55	
    56	
    57	def _popen_factory(stdout_events: list[dict], returncode: int = 0, stderr: str = ""):
    58	    """Return a Popen stand-in that streams the given JSON events."""
    59	    lines = [json.dumps(ev) + "\n" for ev in stdout_events]
    60	    captured: dict = {}
    61	
    62	    def _popen(cmd, **kwargs):
    63	        captured["cmd"] = cmd
    64	        captured["kwargs"] = kwargs
    65	        return _FakeProc(lines, returncode=returncode, stderr=stderr)
    66	
    67	    return _popen, captured
    68	
    69	
    70	# ---------------------------------------------------------------------------
    71	# Command composition
    72	# ---------------------------------------------------------------------------
    73	
    74	
    75	def test_command_includes_stream_json_and_tools(tmp_path: Path):
    76	    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])
    77	
    78	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
    79	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
    80	            run_claude_session(
    81	                "plan this",
    82	                cwd=tmp_path,
    83	                tools=DEFAULT_PLAN_TOOLS,
    84	                include_codex_protocol=False,
    85	            )
    86	
    87	    cmd = captured["cmd"]
    88	    assert cmd[0] == "claude"
    89	    assert "--print" not in cmd  # we use -p
    90	    assert "-p" in cmd
    91	    assert "--output-format" in cmd
    92	    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    93	    tools_idx = cmd.index("--allowedTools") + 1
    94	    assert cmd[tools_idx] == ",".join(DEFAULT_PLAN_TOOLS)
    95	
    96	
    97	def test_default_build_tools_include_bash_skill_task():
    98	    # These are the three tools that unlock the new architecture.
    99	    assert "Bash" in DEFAULT_BUILD_TOOLS
   100	    assert "Skill" in DEFAULT_BUILD_TOOLS
   101	    assert "Task" in DEFAULT_BUILD_TOOLS
   102	
   103	
   104	def test_plan_tools_exclude_write_beyond_artifacts():
   105	    assert "Bash" not in DEFAULT_PLAN_TOOLS
   106	    assert "Edit" not in DEFAULT_PLAN_TOOLS
   107	    # Write stays — planning sessions write charter/queue JSON.
   108	    assert "Write" in DEFAULT_PLAN_TOOLS
   109	
   110	
   111	def test_max_budget_flag_passed_when_specified(tmp_path: Path):
   112	    popen, captured = _popen_factory([{"type": "result", "result": "done"}])
   113	
   114	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   115	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   116	            run_claude_session(
   117	                "build",
   118	                cwd=tmp_path,
   119	                max_budget_usd=2.50,
   120	                include_codex_protocol=False,
   121	            )
   122	
   123	    cmd = captured["cmd"]
   124	    assert "--max-budget-usd" in cmd
   125	    idx = cmd.index("--max-budget-usd")
   126	    assert cmd[idx + 1] == "2.5000"
   127	
   128	
   129	def test_codex_protocol_prepended_to_system_prompt(tmp_path: Path):
   130	    popen, captured = _popen_factory([{"type": "result", "result": "done"}])
   131	
   132	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   133	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   134	            run_claude_session(
   135	                "build",
   136	                cwd=tmp_path,
   137	                append_system_prompt="project charter here",
   138	                include_codex_protocol=True,
   139	            )
   140	
   141	    cmd = captured["cmd"]
   142	    assert "--append-system-prompt" in cmd
   143	    idx = cmd.index("--append-system-prompt")
   144	    system_text = cmd[idx + 1]
   145	    # Protocol file content is included verbatim
   146	    assert "Codex Protocol" in system_text
   147	    assert "codex exec --full-auto" in system_text
   148	    # Caller's own prompt appended after
   149	    assert "project charter here" in system_text
   150	
   151	
   152	def test_include_codex_protocol_false_omits_protocol(tmp_path: Path):
   153	    popen, captured = _popen_factory([{"type": "result", "result": "done"}])
   154	
   155	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   156	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   157	            run_claude_session(
   158	                "plan only",
   159	                cwd=tmp_path,
   160	                append_system_prompt="just this",
   161	                include_codex_protocol=False,
   162	            )
   163	
   164	    cmd = captured["cmd"]
   165	    idx = cmd.index("--append-system-prompt")
   166	    assert cmd[idx + 1] == "just this"
   167	
   168	
   169	# ---------------------------------------------------------------------------
   170	# Event parsing
   171	# ---------------------------------------------------------------------------
   172	
   173	
   174	def test_tool_calls_extracted_from_stream(tmp_path: Path):
   175	    events = [
   176	        {
   177	            "type": "assistant",
   178	            "message": {
   179	                "content": [
   180	                    {"type": "tool_use", "name": "Read",
   181	                     "input": {"file_path": "src/app.py"}},
   182	                    {"type": "tool_use", "name": "Bash",
   183	                     "input": {"command": "codex exec --full-auto 'Task: impl'"}},
   184	                    {"type": "tool_use", "name": "Skill",
   185	                     "input": {"skill": "test-driven-development"}},
   186	                    {"type": "tool_use", "name": "Task",
   187	                     "input": {"subagent_type": "code-reviewer",
   188	                               "description": "review feature"}},
   189	                    {"type": "tool_use", "name": "Write",
   190	                     "input": {"file_path": "src/new_file.py", "content": "..."}},
   191	                ],
   192	            },
   193	        },
   194	        {"type": "result", "result": "done", "total_cost_usd": 0.42},
   195	    ]
   196	    popen, _ = _popen_factory(events)
   197	
   198	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   199	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   200	            result = run_claude_session(
   201	                "build", cwd=tmp_path, include_codex_protocol=False,
   202	            )
   203	
   204	    assert result.success is True
   205	    assert result.total_cost_usd == 0.42
   206	    # All five tool calls captured
   207	    assert len(result.tool_calls) == 5
   208	    tool_names = [t.tool for t in result.tool_calls]
   209	    assert tool_names == ["Read", "Bash", "Skill", "Task", "Write"]
   210	    # Skill name parsed out
   211	    assert "test-driven-development" in result.skills_invoked
   212	    # Codex shell-out recognized
   213	    assert len(result.codex_invocations) == 1
   214	    assert "codex exec --full-auto" in result.codex_invocations[0]
   215	    # Subagent dispatched
   216	    assert "code-reviewer" in result.subagents_dispatched
   217	    # File touched
   218	    assert "src/new_file.py" in result.files_touched
   219	
   220	
   221	def test_final_text_from_result_event(tmp_path: Path):
   222	    events = [
   223	        {"type": "assistant", "message": {"content": [{"type": "text", "text": "thinking"}]}},
   224	        {"type": "result", "result": "build complete", "total_cost_usd": 0.10},
   225	    ]
   226	    popen, _ = _popen_factory(events)
   227	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   228	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   229	            result = run_claude_session("x", cwd=tmp_path, include_codex_protocol=False)
   230	    assert result.final_text == "build complete"
   231	
   232	
   233	def test_final_text_falls_back_to_last_assistant_message(tmp_path: Path):
   234	    # No result event — runner falls back to extracting from last assistant event
   235	    events = [
   236	        {"type": "assistant",
   237	         "message": {"content": [{"type": "text", "text": "final answer"}]}},
   238	    ]
   239	    popen, _ = _popen_factory(events)
   240	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   241	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   242	            result = run_claude_session("x", cwd=tmp_path, include_codex_protocol=False)
   243	    assert result.final_text == "final answer"
   244	
   245	
   246	def test_on_event_callback_invoked_per_event(tmp_path: Path):
   247	    events = [
   248	        {"type": "assistant", "message": {"content": []}},
   249	        {"type": "result", "result": "ok"},
   250	    ]
   251	    popen, _ = _popen_factory(events)
   252	
   253	    seen: list[dict] = []
   254	
   255	    def cb(ev):
   256	        seen.append(ev)
   257	
   258	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   259	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   260	            run_claude_session(
   261	                "x", cwd=tmp_path, on_event=cb, include_codex_protocol=False,
   262	            )
   263	
   264	    assert len(seen) == 2
   265	
   266	
   267	def test_on_event_exception_does_not_crash_session(tmp_path: Path):
   268	    events = [{"type": "result", "result": "ok"}]
   269	    popen, _ = _popen_factory(events)
   270	
   271	    def bad_cb(_ev):
   272	        raise RuntimeError("boom")
   273	
   274	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   275	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   276	            result = run_claude_session(
   277	                "x", cwd=tmp_path, on_event=bad_cb, include_codex_protocol=False,
   278	            )
   279	    assert result.success is True
   280	
   281	
   282	def test_event_log_written_as_jsonl(tmp_path: Path):
   283	    events = [
   284	        {"type": "assistant", "message": {"content": []}},
   285	        {"type": "result", "result": "ok"},
   286	    ]
   287	    popen, _ = _popen_factory(events)
   288	    log_path = tmp_path / "logs" / "session.jsonl"
   289	
   290	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   291	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   292	            run_claude_session(
   293	                "x", cwd=tmp_path, log_path=log_path, include_codex_protocol=False,
   294	            )
   295	
   296	    assert log_path.exists()
   297	    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
   298	    assert len(lines) == 2
   299	    assert json.loads(lines[0])["type"] == "assistant"
   300	    assert json.loads(lines[1])["type"] == "result"
   301	
   302	
   303	def test_malformed_json_line_is_tolerated(tmp_path: Path):
   304	    # Claude CLI occasionally emits debug noise — runner must not crash.
   305	    lines = [
   306	        "not a json line\n",
   307	        json.dumps({"type": "result", "result": "ok"}) + "\n",
   308	    ]
   309	
   310	    def popen(cmd, **kwargs):  # noqa: ARG001
   311	        return _FakeProc(lines, returncode=0)
   312	
   313	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   314	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   315	            result = run_claude_session(
   316	                "x", cwd=tmp_path, include_codex_protocol=False,
   317	            )
   318	    assert result.success is True
   319	    assert result.final_text == "ok"
   320	
   321	
   322	# ---------------------------------------------------------------------------
   323	# Error paths
   324	# ---------------------------------------------------------------------------
   325	
   326	
   327	def test_claude_cli_missing_returns_structured_error(tmp_path: Path):
   328	    with patch("ncdev.claude_session.shutil.which", return_value=None):
   329	        result = run_claude_session("x", cwd=tmp_path)
   330	    assert result.success is False
   331	    assert result.exit_code == -1
   332	    assert "claude CLI not found" in (result.error or "")
   333	
   334	
   335	def test_non_zero_exit_marked_unsuccessful(tmp_path: Path):
   336	    events = [{"type": "result", "result": "partial"}]
   337	    popen, _ = _popen_factory(events, returncode=2, stderr="something broke")
   338	
   339	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   340	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   341	            result = run_claude_session(
   342	                "x", cwd=tmp_path, include_codex_protocol=False,
   343	            )
   344	
   345	    assert result.success is False
   346	    assert result.exit_code == 2
   347	    assert result.stderr == "something broke"
   348	    assert "exited with code 2" in (result.error or "")
   349	
   350	
   351	def test_ncdev_hooks_wired_in_by_default(tmp_path: Path):
   352	    """When enable_ncdev_hooks=True (default) and the bundled settings
   353	    file exists, --settings is passed to claude."""
   354	    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])
   355	
   356	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   357	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   358	            run_claude_session(
   359	                "do thing", cwd=tmp_path, include_codex_protocol=False,
   360	            )
   361	    cmd = captured["cmd"]
   362	    assert "--settings" in cmd
   363	    idx = cmd.index("--settings")
   364	    settings_path = cmd[idx + 1]
   365	    assert settings_path.endswith("settings.json")
   366	
   367	
   368	def test_enable_ncdev_hooks_false_omits_settings(tmp_path: Path):
   369	    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])
   370	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   371	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   372	            run_claude_session(
   373	                "x", cwd=tmp_path, include_codex_protocol=False,
   374	                enable_ncdev_hooks=False,
   375	            )
   376	    cmd = captured["cmd"]
   377	    assert "--settings" not in cmd
   378	
   379	
   380	def test_caller_supplied_settings_path_wins(tmp_path: Path):
   381	    user_settings = tmp_path / "custom-settings.json"
   382	    user_settings.write_text("{}")
   383	    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])
   384	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   385	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   386	            run_claude_session(
   387	                "x", cwd=tmp_path, include_codex_protocol=False,
   388	                settings_path=user_settings,
   389	            )
   390	    cmd = captured["cmd"]
   391	    idx = cmd.index("--settings")
   392	    assert cmd[idx + 1] == str(user_settings)
   393	
   394	
   395	def test_summary_includes_key_signals(tmp_path: Path):
   396	    events = [
   397	        {
   398	            "type": "assistant",
   399	            "message": {"content": [
   400	                {"type": "tool_use", "name": "Skill",
   401	                 "input": {"skill": "verification-before-completion"}},
   402	                {"type": "tool_use", "name": "Bash",
   403	                 "input": {"command": "codex exec --full-auto 'x'"}},
   404	            ]},
   405	        },
   406	        {"type": "result", "result": "ok", "total_cost_usd": 1.23},
   407	    ]
   408	    popen, _ = _popen_factory(events)
   409	    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
   410	        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
   411	            result = run_claude_session(
   412	                "x", cwd=tmp_path, include_codex_protocol=False,
   413	            )
   414	    s = result.summary()
   415	    assert "success=True" in s
   416	    assert "cost=$1.230" in s
   417	    assert "skills=verification-before-completion" in s
   418	    assert "codex=1" in s

exec
/bin/zsh -lc 'python3 -m pytest -q tests/unit/test_claude_session.py tests/unit/test_claude_executor.py tests/unit/test_asset_manifest.py tests/unit/test_charter.py tests/unit/test_design_phase.py tests/unit/test_hooks.py tests/unit/test_dev.py tests/test_ncdev_v2/test_modes.py' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 exited 1 in 0ms:
/opt/homebrew/opt/python@3.14/bin/python3.14: No module named pytest

exec
/bin/zsh -lc "nl -ba tests/unit/test_claude_executor.py | sed -n '1,380p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Tests for Phase E Claude-driven feature executor."""
     2	
     3	from __future__ import annotations
     4	
     5	import subprocess
     6	from pathlib import Path
     7	from unittest.mock import patch
     8	
     9	import pytest
    10	
    11	from ncdev.claude_session import ClaudeSessionResult
    12	from ncdev.v3.asset_manifest import save_feature_manifest
    13	from ncdev.v3.claude_executor import (
    14	    build_feature_prompt,
    15	    execute_feature_claude_driven,
    16	)
    17	from ncdev.v3.models import (
    18	    AssetManifest,
    19	    AssetManifestEntry,
    20	    CharterBundle,
    21	    FeatureQueueDoc,
    22	    FeatureStep,
    23	    StepResult,
    24	    StepStatus,
    25	    TargetProjectContract,
    26	    VerificationContract,
    27	)
    28	
    29	
    30	# ---------------------------------------------------------------------------
    31	# Helpers
    32	# ---------------------------------------------------------------------------
    33	
    34	
    35	def _make_feature(fid: str = "f01-scaffold") -> FeatureStep:
    36	    return FeatureStep(
    37	        feature_id=fid,
    38	        title="Scaffold",
    39	        description="Boot skeleton + health endpoint",
    40	        acceptance_criteria=["Health endpoint returns 200"],
    41	        test_requirements=["Integration test hits /api/health"],
    42	    )
    43	
    44	
    45	def _make_bundle(required_files: list[str] | None = None) -> CharterBundle:
    46	    return CharterBundle(
    47	        contract=TargetProjectContract(project_name="myapp", project_type="web"),
    48	        verification=VerificationContract(
    49	            backend_health_url="http://localhost:23001/api/health",
    50	            backend_test_command="pytest",
    51	            required_files=required_files or [],
    52	            prohibited_patterns=["TODO"],
    53	            assets_manifest_required=True,
    54	        ),
    55	        feature_queue=FeatureQueueDoc(project_name="myapp", features=[_make_feature()]),
    56	    )
    57	
    58	
    59	def _init_git(path: Path) -> None:
    60	    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    61	    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    62	    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    63	    (path / "README.md").write_text("initial")
    64	    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    65	    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(path), check=True)
    66	
    67	
    68	def _seed_manifest(target: Path, feature_id: str) -> None:
    69	    save_feature_manifest(target, AssetManifest(feature_id=feature_id, assets=[]))
    70	
    71	
    72	# ---------------------------------------------------------------------------
    73	# Prompt shape
    74	# ---------------------------------------------------------------------------
    75	
    76	
    77	def test_prompt_has_expected_structure(tmp_path: Path):
    78	    feature = _make_feature()
    79	    prompt = build_feature_prompt(
    80	        feature=feature,
    81	        target_path=tmp_path,
    82	        charter_dir=tmp_path / "outputs",
    83	        prior_feature_ids=[],
    84	        project_id="myapp",
    85	    )
    86	    # Feature identity
    87	    assert "f01-scaffold" in prompt
    88	    assert "Scaffold" in prompt
    89	    # Points to the charter artifacts on disk, does NOT inline them
    90	    assert "target-project-contract.json" in prompt
    91	    assert "verification-contract.json" in prompt
    92	    assert "design-system.json" in prompt
    93	    # Instructs skill usage
    94	    assert "test-driven-development" in prompt
    95	    assert "verification-before-completion" in prompt
    96	    assert "systematic-debugging" in prompt
    97	    # Codex protocol referenced (detail is in system prompt)
    98	    assert "Codex" in prompt
    99	    # Asset manifest section spliced in
   100	    assert ".ncdev/assets-needed/f01-scaffold.json" in prompt
   101	
   102	
   103	def test_prompt_mentions_prior_features(tmp_path: Path):
   104	    prompt = build_feature_prompt(
   105	        feature=_make_feature("f03-auth"),
   106	        target_path=tmp_path,
   107	        charter_dir=tmp_path / "outputs",
   108	        prior_feature_ids=["f01-scaffold", "f02-db"],
   109	        project_id="myapp",
   110	    )
   111	    assert "f01-scaffold, f02-db" in prompt
   112	
   113	
   114	def test_prompt_handles_empty_acceptance_criteria(tmp_path: Path):
   115	    feature = FeatureStep(
   116	        feature_id="f01",
   117	        title="X",
   118	        description="Y",
   119	        acceptance_criteria=[],
   120	    )
   121	    prompt = build_feature_prompt(
   122	        feature=feature,
   123	        target_path=tmp_path,
   124	        charter_dir=tmp_path,
   125	        prior_feature_ids=[],
   126	        project_id="p",
   127	    )
   128	    assert "infer from description" in prompt
   129	
   130	
   131	# ---------------------------------------------------------------------------
   132	# Executor happy path
   133	# ---------------------------------------------------------------------------
   134	
   135	
   136	def test_passed_when_session_succeeds_and_commits(tmp_path: Path):
   137	    target = tmp_path / "app"
   138	    target.mkdir()
   139	    _init_git(target)
   140	
   141	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   142	        # Simulate Claude making a commit + writing a manifest
   143	        _seed_manifest(target, "f01-scaffold")
   144	        (target / "app.py").write_text("print('hi')")
   145	        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
   146	        subprocess.run(["git", "commit", "-q", "-m", "feat(f01-scaffold): hi"],
   147	                       cwd=str(target), check=True)
   148	        return ClaudeSessionResult(
   149	            success=True, final_text="done", exit_code=0,
   150	            duration_seconds=2.0, total_cost_usd=0.42,
   151	        )
   152	
   153	    bundle = _make_bundle()
   154	    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
   155	        result = execute_feature_claude_driven(
   156	            feature=_make_feature(),
   157	            target_path=target,
   158	            run_dir=tmp_path / "run",
   159	            charter_bundle=bundle,
   160	            prior_results=[],
   161	            project_id="myapp",
   162	        )
   163	
   164	    assert result.status == StepStatus.PASSED
   165	    assert result.commit_sha != ""
   166	    assert "app.py" in result.files_created
   167	    # Session metadata captured on disk
   168	    assert (tmp_path / "run" / "steps" / "f01-scaffold" / "result.json").exists()
   169	    assert (tmp_path / "run" / "steps" / "f01-scaffold" / "signals.json").exists()
   170	
   171	
   172	# ---------------------------------------------------------------------------
   173	# Executor failure paths
   174	# ---------------------------------------------------------------------------
   175	
   176	
   177	def test_failed_when_no_commit_made(tmp_path: Path):
   178	    target = tmp_path / "app"
   179	    target.mkdir()
   180	    _init_git(target)
   181	
   182	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   183	        # Claude session ran but did nothing
   184	        return ClaudeSessionResult(
   185	            success=True, final_text="I'm confused", exit_code=0,
   186	        )
   187	
   188	    bundle = _make_bundle()
   189	    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
   190	        result = execute_feature_claude_driven(
   191	            feature=_make_feature(),
   192	            target_path=target,
   193	            run_dir=tmp_path / "run",
   194	            charter_bundle=bundle,
   195	            prior_results=[],
   196	            project_id="myapp",
   197	        )
   198	    assert result.status == StepStatus.FAILED
   199	
   200	
   201	def test_dirty_working_tree_committed_as_broken(tmp_path: Path):
   202	    target = tmp_path / "app"
   203	    target.mkdir()
   204	    _init_git(target)
   205	
   206	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   207	        # Claude made changes but didn't commit — orchestrator must
   208	        # commit with [BROKEN] tag so the next feature has context.
   209	        (target / "half_done.py").write_text("# TODO implement")
   210	        return ClaudeSessionResult(success=False, final_text="gave up", exit_code=1)
   211	
   212	    bundle = _make_bundle()
   213	    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
   214	        result = execute_feature_claude_driven(
   215	            feature=_make_feature(),
   216	            target_path=target,
   217	            run_dir=tmp_path / "run",
   218	            charter_bundle=bundle,
   219	            prior_results=[],
   220	            project_id="myapp",
   221	        )
   222	
   223	    assert result.status == StepStatus.FAILED
   224	    # A [BROKEN] commit should exist
   225	    log = subprocess.run(
   226	        ["git", "log", "--oneline"],
   227	        cwd=str(target), capture_output=True, text=True, check=True,
   228	    )
   229	    assert "[BROKEN]" in log.stdout
   230	
   231	
   232	def test_missing_asset_manifest_causes_verification_failure(tmp_path: Path):
   233	    target = tmp_path / "app"
   234	    target.mkdir()
   235	    _init_git(target)
   236	
   237	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   238	        # Claude commits code that references an asset but writes no manifest.
   239	        src = target / "src" / "App.tsx"
   240	        src.parent.mkdir(parents=True)
   241	        src.write_text('<img src="/images/missing.png" />')
   242	        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
   243	        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): commit"],
   244	                       cwd=str(target), check=True)
   245	        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
   246	
   247	    bundle = _make_bundle()
   248	    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
   249	        result = execute_feature_claude_driven(
   250	            feature=_make_feature(),
   251	            target_path=target,
   252	            run_dir=tmp_path / "run",
   253	            charter_bundle=bundle,
   254	            prior_results=[],
   255	            project_id="myapp",
   256	        )
   257	
   258	    # Session "succeeded" and committed, but verification blocks the pass
   259	    assert result.status == StepStatus.FAILED
   260	    reasons = result.verification.failure_reasons if result.verification else []
   261	    assert any("manifest" in r.lower() for r in reasons)
   262	
   263	
   264	def test_prohibited_patterns_block_pass(tmp_path: Path):
   265	    target = tmp_path / "app"
   266	    target.mkdir()
   267	    _init_git(target)
   268	
   269	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   270	        _seed_manifest(target, "f01-scaffold")
   271	        (target / "bad.py").write_text("# TODO something")
   272	        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
   273	        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): bad"],
   274	                       cwd=str(target), check=True)
   275	        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
   276	
   277	    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
   278	    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
   279	        result = execute_feature_claude_driven(
   280	            feature=_make_feature(),
   281	            target_path=target,
   282	            run_dir=tmp_path / "run",
   283	            charter_bundle=bundle,
   284	            prior_results=[],
   285	            project_id="myapp",
   286	        )
   287	    assert result.status == StepStatus.FAILED
   288	    assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
   289	
   290	
   291	def test_required_files_missing_blocks_pass(tmp_path: Path):
   292	    target = tmp_path / "app"
   293	    target.mkdir()
   294	    _init_git(target)
   295	
   296	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   297	        _seed_manifest(target, "f01-scaffold")
   298	        (target / "thing.py").write_text("x=1")
   299	        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
   300	        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): x"],
   301	                       cwd=str(target), check=True)
   302	        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
   303	
   304	    bundle = _make_bundle(required_files=["docker-compose.yml", "README.md"])
   305	    with patch("ncdev.v3.claude_executor.run_claude_session", side_effect=fake_session):
   306	        result = execute_feature_claude_driven(
   307	            feature=_make_feature(),
   308	            target_path=target,
   309	            run_dir=tmp_path / "run",
   310	            charter_bundle=bundle,
   311	            prior_results=[],
   312	            project_id="myapp",
   313	        )
   314	    # docker-compose.yml missing — verification fails, but README.md already exists from _init_git.
   315	    assert result.status == StepStatus.FAILED
   316	    reasons = result.verification.failure_reasons
   317	    assert any("docker-compose.yml" in r for r in reasons)

exec
/bin/zsh -lc "nl -ba tests/unit/test_hooks.py | sed -n '1,320p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Tests for Phase H hooks — pre_bash_guard.evaluate()."""
     2	
     3	from __future__ import annotations
     4	
     5	import subprocess
     6	from pathlib import Path
     7	
     8	import pytest
     9	
    10	# Import the hook module. Add scripts dir to path for import.
    11	import sys
    12	HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "ncdev-hooks"
    13	sys.path.insert(0, str(HOOKS_DIR))
    14	import pre_bash_guard  # noqa: E402
    15	
    16	
    17	def _init_git_with_staged(path: Path, file_content: dict[str, str]) -> None:
    18	    """Init a git repo at ``path`` with the given files staged (not committed)."""
    19	    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    20	    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    21	    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    22	    # Seed a clean initial commit so diff --cached shows real changes
    23	    (path / "README.md").write_text("init")
    24	    subprocess.run(["git", "add", "README.md"], cwd=str(path), check=True)
    25	    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(path), check=True)
    26	    # Now stage the test files
    27	    for rel, content in file_content.items():
    28	        full = path / rel
    29	        full.parent.mkdir(parents=True, exist_ok=True)
    30	        full.write_text(content)
    31	        subprocess.run(["git", "add", rel], cwd=str(path), check=True)
    32	
    33	
    34	# ---------------------------------------------------------------------------
    35	# Non-Bash tools always allowed
    36	# ---------------------------------------------------------------------------
    37	
    38	
    39	def test_non_bash_tool_is_allowed(tmp_path: Path):
    40	    decision, reason = pre_bash_guard.evaluate("Edit", {"file_path": "x"}, cwd=str(tmp_path))
    41	    assert decision == "allow"
    42	    assert reason == ""
    43	
    44	
    45	def test_empty_bash_command_allowed(tmp_path: Path):
    46	    decision, _ = pre_bash_guard.evaluate("Bash", {"command": ""}, cwd=str(tmp_path))
    47	    assert decision == "allow"
    48	
    49	
    50	def test_non_git_commands_allowed(tmp_path: Path):
    51	    decision, _ = pre_bash_guard.evaluate("Bash", {"command": "ls -la"}, cwd=str(tmp_path))
    52	    assert decision == "allow"
    53	    decision, _ = pre_bash_guard.evaluate("Bash", {"command": "pytest -q"}, cwd=str(tmp_path))
    54	    assert decision == "allow"
    55	
    56	
    57	# ---------------------------------------------------------------------------
    58	# Conventional Commits enforcement
    59	# ---------------------------------------------------------------------------
    60	
    61	
    62	@pytest.mark.parametrize("good", [
    63	    "feat: add login",
    64	    "fix(auth): handle expired tokens",
    65	    "test: cover edge case",
    66	    "chore: bump deps",
    67	    "refactor(api): split router",
    68	    "docs: update readme",
    69	    "perf: cache query",
    70	])
    71	def test_conventional_messages_pass(tmp_path: Path, good: str):
    72	    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    73	    cmd = f'git commit -m "{good}"'
    74	    decision, reason = pre_bash_guard.evaluate("Bash", {"command": cmd}, cwd=str(tmp_path))
    75	    assert decision == "allow", reason
    76	
    77	
    78	@pytest.mark.parametrize("bad", [
    79	    "updated stuff",
    80	    "WIP",
    81	    "quick fix",
    82	    "Added feature",
    83	])
    84	def test_non_conventional_messages_blocked(tmp_path: Path, bad: str):
    85	    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    86	    cmd = f'git commit -m "{bad}"'
    87	    decision, reason = pre_bash_guard.evaluate("Bash", {"command": cmd}, cwd=str(tmp_path))
    88	    assert decision == "block"
    89	    assert "Conventional Commits" in reason
    90	
    91	
    92	def test_commit_without_inline_m_is_allowed(tmp_path: Path):
    93	    # If we cannot parse the message (HEREDOC), we allow and rely on other checks.
    94	    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    95	    decision, _ = pre_bash_guard.evaluate(
    96	        "Bash",
    97	        {"command": 'git commit -F message.txt'},
    98	        cwd=str(tmp_path),
    99	    )
   100	    assert decision == "allow"
   101	
   102	
   103	# ---------------------------------------------------------------------------
   104	# Prohibited patterns
   105	# ---------------------------------------------------------------------------
   106	
   107	
   108	def test_staged_content_with_todo_is_blocked(tmp_path: Path):
   109	    _init_git_with_staged(tmp_path, {
   110	        "src/app.py": "def run():\n    # TODO implement\n    pass\n",
   111	    })
   112	    decision, reason = pre_bash_guard.evaluate(
   113	        "Bash",
   114	        {"command": 'git commit -m "feat: initial"'},
   115	        cwd=str(tmp_path),
   116	    )
   117	    assert decision == "block"
   118	    assert "TODO" in reason
   119	    assert "src/app.py" in reason
   120	
   121	
   122	def test_staged_content_with_console_log_is_blocked(tmp_path: Path):
   123	    _init_git_with_staged(tmp_path, {
   124	        "frontend/app.tsx": 'export const x = () => { console.log("hi"); };\n',
   125	    })
   126	    decision, reason = pre_bash_guard.evaluate(
   127	        "Bash",
   128	        {"command": 'git commit -m "feat: add thing"'},
   129	        cwd=str(tmp_path),
   130	    )
   131	    assert decision == "block"
   132	    assert "console.log(" in reason
   133	
   134	
   135	def test_clean_staged_content_passes(tmp_path: Path):
   136	    _init_git_with_staged(tmp_path, {
   137	        "src/app.py": "def run():\n    return 42\n",
   138	        "tests/test_app.py": "def test_run():\n    assert run() == 42\n",
   139	    })
   140	    decision, reason = pre_bash_guard.evaluate(
   141	        "Bash",
   142	        {"command": 'git commit -m "feat: add run"'},
   143	        cwd=str(tmp_path),
   144	    )
   145	    assert decision == "allow", reason
   146	
   147	
   148	def test_prohibited_in_existing_unchanged_file_is_ok(tmp_path: Path):
   149	    # Pattern exists in HEAD but is not being added by the current diff — OK.
   150	    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
   151	    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), check=True)
   152	    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path), check=True)
   153	    (tmp_path / "old.py").write_text("# TODO from history\n")
   154	    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
   155	    subprocess.run(["git", "commit", "-q", "-m", "init: legacy"], cwd=str(tmp_path), check=True)
   156	
   157	    # New clean change staged
   158	    (tmp_path / "new.py").write_text("x = 1\n")
   159	    subprocess.run(["git", "add", "new.py"], cwd=str(tmp_path), check=True)
   160	
   161	    decision, reason = pre_bash_guard.evaluate(
   162	        "Bash",
   163	        {"command": 'git commit -m "feat: add new"'},
   164	        cwd=str(tmp_path),
   165	    )
   166	    assert decision == "allow", reason
   167	
   168	
   169	# ---------------------------------------------------------------------------
   170	# Force-push protection
   171	# ---------------------------------------------------------------------------
   172	
   173	
   174	def test_force_push_to_main_blocked(tmp_path: Path, monkeypatch):
   175	    monkeypatch.delenv("NCDEV_ALLOW_FORCE_PUSH", raising=False)
   176	    decision, reason = pre_bash_guard.evaluate(
   177	        "Bash",
   178	        {"command": "git push --force origin main"},
   179	        cwd=str(tmp_path),
   180	    )
   181	    assert decision == "block"
   182	    assert "Force-push" in reason
   183	    assert "NCDEV_ALLOW_FORCE_PUSH" in reason
   184	
   185	
   186	def test_force_push_to_feature_branch_allowed(tmp_path: Path):
   187	    decision, _ = pre_bash_guard.evaluate(
   188	        "Bash",
   189	        {"command": "git push --force origin feature/my-branch"},
   190	        cwd=str(tmp_path),
   191	    )
   192	    assert decision == "allow"
   193	
   194	
   195	def test_force_push_override_env(tmp_path: Path, monkeypatch):
   196	    monkeypatch.setenv("NCDEV_ALLOW_FORCE_PUSH", "1")
   197	    decision, _ = pre_bash_guard.evaluate(
   198	        "Bash",
   199	        {"command": "git push --force origin main"},
   200	        cwd=str(tmp_path),
   201	    )
   202	    assert decision == "allow"
   203	
   204	
   205	# ---------------------------------------------------------------------------
   206	# Project-level hook config override
   207	# ---------------------------------------------------------------------------
   208	
   209	
   210	def test_custom_prohibited_patterns_via_env(tmp_path: Path, monkeypatch):
   211	    config = tmp_path / "hooks.json"
   212	    config.write_text('{"prohibited_patterns": ["SECRET"]}')
   213	    monkeypatch.setenv("NCDEV_HOOKS_CONFIG", str(config))
   214	
   215	    # Stage content with SECRET, not TODO
   216	    _init_git_with_staged(tmp_path, {
   217	        "x.py": 'API_SECRET = "oops"\n',
   218	    })
   219	    decision, reason = pre_bash_guard.evaluate(
   220	        "Bash",
   221	        {"command": 'git commit -m "feat: add key"'},
   222	        cwd=str(tmp_path),
   223	    )
   224	    assert decision == "block"
   225	    assert "SECRET" in reason

exec
/bin/zsh -lc "nl -ba tests/unit/test_asset_manifest.py | sed -n '1,280p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Tests for Phase D asset manifest."""
     2	
     3	from __future__ import annotations
     4	
     5	import json
     6	from pathlib import Path
     7	
     8	import pytest
     9	
    10	from ncdev.v3.asset_manifest import (
    11	    ASSETS_DIR,
    12	    aggregate_manifests,
    13	    load_feature_manifest,
    14	    manifest_prompt_section,
    15	    save_feature_manifest,
    16	    scan_code_for_asset_references,
    17	    verify_manifest_covers_references,
    18	)
    19	from ncdev.v3.models import AssetManifest, AssetManifestEntry
    20	
    21	
    22	def _mk_manifest(feature_id: str, *entries: AssetManifestEntry) -> AssetManifest:
    23	    return AssetManifest(feature_id=feature_id, assets=list(entries))
    24	
    25	
    26	# ---------------------------------------------------------------------------
    27	# Round-trip
    28	# ---------------------------------------------------------------------------
    29	
    30	
    31	def test_save_and_load_manifest_roundtrip(tmp_path: Path):
    32	    m = _mk_manifest(
    33	        "f02-hero",
    34	        AssetManifestEntry(
    35	            id="hero-bg",
    36	            name="Hero background",
    37	            type="image",
    38	            description="Full-bleed gradient",
    39	            generation_prompt="Abstract gradient mesh, deep purples",
    40	            suggested_dimensions="2400x1200",
    41	            target_path="frontend/public/images/hero-bg.webp",
    42	            referenced_in=["frontend/src/pages/Home.tsx:42"],
    43	        ),
    44	    )
    45	    save_feature_manifest(tmp_path, m)
    46	    loaded = load_feature_manifest(tmp_path, "f02-hero")
    47	    assert loaded is not None
    48	    assert loaded.feature_id == "f02-hero"
    49	    assert loaded.assets[0].id == "hero-bg"
    50	
    51	
    52	def test_load_manifest_returns_none_when_missing(tmp_path: Path):
    53	    assert load_feature_manifest(tmp_path, "nonexistent") is None
    54	
    55	
    56	# ---------------------------------------------------------------------------
    57	# Aggregation
    58	# ---------------------------------------------------------------------------
    59	
    60	
    61	def test_aggregate_merges_multiple_feature_manifests(tmp_path: Path):
    62	    save_feature_manifest(tmp_path, _mk_manifest(
    63	        "f01", AssetManifestEntry(id="a", name="a", type="image",
    64	                                   description="", generation_prompt=""),
    65	    ))
    66	    save_feature_manifest(tmp_path, _mk_manifest(
    67	        "f02", AssetManifestEntry(id="b", name="b", type="svg",
    68	                                   description="", generation_prompt=""),
    69	    ))
    70	    agg = aggregate_manifests(tmp_path)
    71	    assert agg.feature_id == "_all"
    72	    ids = {a.id for a in agg.assets}
    73	    assert ids == {"a", "b"}
    74	    # Aggregate also written to disk
    75	    all_path = tmp_path / ASSETS_DIR / "_all.json"
    76	    assert all_path.exists()
    77	
    78	
    79	def test_aggregate_deduplicates_by_id(tmp_path: Path):
    80	    save_feature_manifest(tmp_path, _mk_manifest(
    81	        "f01", AssetManifestEntry(id="shared", name="v1", type="image",
    82	                                   description="", generation_prompt=""),
    83	    ))
    84	    save_feature_manifest(tmp_path, _mk_manifest(
    85	        "f02", AssetManifestEntry(id="shared", name="v2", type="image",
    86	                                   description="", generation_prompt=""),
    87	    ))
    88	    agg = aggregate_manifests(tmp_path)
    89	    assert len([a for a in agg.assets if a.id == "shared"]) == 1
    90	
    91	
    92	def test_aggregate_skips_summary_and_bad_files(tmp_path: Path):
    93	    dir_ = tmp_path / ASSETS_DIR
    94	    dir_.mkdir(parents=True)
    95	    (dir_ / "_all.json").write_text("{}")
    96	    (dir_ / "garbage.json").write_text("{not json")
    97	    save_feature_manifest(tmp_path, _mk_manifest(
    98	        "f01", AssetManifestEntry(id="ok", name="ok", type="image",
    99	                                   description="", generation_prompt=""),
   100	    ))
   101	    agg = aggregate_manifests(tmp_path)
   102	    ids = {a.id for a in agg.assets}
   103	    assert ids == {"ok"}
   104	
   105	
   106	# ---------------------------------------------------------------------------
   107	# Prompt section
   108	# ---------------------------------------------------------------------------
   109	
   110	
   111	def test_prompt_section_includes_path_and_schema():
   112	    snippet = manifest_prompt_section("f03-checkout")
   113	    assert "f03-checkout.json" in snippet
   114	    assert ASSETS_DIR in snippet
   115	    assert "generation_prompt" in snippet
   116	    assert "status" in snippet
   117	    # Must cover the six asset types
   118	    for t in ("image", "gif", "svg", "video", "icon", "audio"):
   119	        assert t in snippet
   120	
   121	
   122	# ---------------------------------------------------------------------------
   123	# Code scanning
   124	# ---------------------------------------------------------------------------
   125	
   126	
   127	def test_scan_detects_img_tag_references(tmp_path: Path):
   128	    frontend_src = tmp_path / "frontend" / "src" / "pages"
   129	    frontend_src.mkdir(parents=True)
   130	    (frontend_src / "Home.tsx").write_text(
   131	        """export const Home = () => (
   132	  <div>
   133	    <img src="/images/logo.png" alt="logo" />
   134	    <video src="../videos/demo.mp4" />
   135	  </div>
   136	);"""
   137	    )
   138	    hits = scan_code_for_asset_references(tmp_path)
   139	    refs = {h[1] for h in hits}
   140	    assert "/images/logo.png" in refs
   141	    assert "../videos/demo.mp4" in refs
   142	
   143	
   144	def test_scan_detects_css_url_references(tmp_path: Path):
   145	    css = tmp_path / "frontend" / "src" / "style.css"
   146	    css.parent.mkdir(parents=True)
   147	    css.write_text(
   148	        ".hero { background-image: url('./assets/hero.webp'); }"
   149	    )
   150	    hits = scan_code_for_asset_references(tmp_path)
   151	    assert any("hero.webp" in h[1] for h in hits)
   152	
   153	
   154	def test_scan_detects_import_statements(tmp_path: Path):
   155	    src = tmp_path / "src" / "App.tsx"
   156	    src.parent.mkdir(parents=True)
   157	    src.write_text("""import logo from "./logo.svg";
   158	import banner from "./assets/banner.png";""")
   159	    hits = scan_code_for_asset_references(tmp_path)
   160	    refs = {h[1] for h in hits}
   161	    assert any("logo.svg" in r for r in refs)
   162	    assert any("banner.png" in r for r in refs)
   163	
   164	
   165	def test_scan_ignores_external_urls(tmp_path: Path):
   166	    src = tmp_path / "src" / "App.tsx"
   167	    src.parent.mkdir(parents=True)
   168	    src.write_text(
   169	        """<img src="https://cdn.example.com/logo.png" />"""
   170	    )
   171	    hits = scan_code_for_asset_references(tmp_path)
   172	    # External URL skipped
   173	    assert len(hits) == 0
   174	
   175	
   176	# ---------------------------------------------------------------------------
   177	# Verification
   178	# ---------------------------------------------------------------------------
   179	
   180	
   181	def test_verify_fails_without_manifest(tmp_path: Path):
   182	    # Create a file with a reference but no manifest
   183	    src = tmp_path / "frontend" / "src" / "App.tsx"
   184	    src.parent.mkdir(parents=True)
   185	    src.write_text('<img src="/images/missing.png" />')
   186	    ok, missing = verify_manifest_covers_references(tmp_path, "f01")
   187	    assert ok is False
   188	    assert "<no-manifest>" in missing
   189	
   190	
   191	def test_verify_fails_when_reference_not_in_manifest(tmp_path: Path):
   192	    src = tmp_path / "frontend" / "src" / "App.tsx"
   193	    src.parent.mkdir(parents=True)
   194	    src.write_text('<img src="/images/unlisted.png" />')
   195	    save_feature_manifest(tmp_path, _mk_manifest("f01"))  # empty manifest
   196	    ok, missing = verify_manifest_covers_references(tmp_path, "f01")
   197	    assert ok is False
   198	    assert any("unlisted.png" in m for m in missing)
   199	
   200	
   201	def test_verify_passes_when_asset_listed_in_manifest(tmp_path: Path):
   202	    src = tmp_path / "frontend" / "src" / "App.tsx"
   203	    src.parent.mkdir(parents=True)
   204	    src.write_text('<img src="/images/hero.png" />')
   205	    save_feature_manifest(tmp_path, _mk_manifest(
   206	        "f01",
   207	        AssetManifestEntry(
   208	            id="hero",
   209	            name="Hero",
   210	            type="image",
   211	            description="Landing hero",
   212	            generation_prompt="...",
   213	            target_path="images/hero.png",
   214	        ),
   215	    ))
   216	    ok, missing = verify_manifest_covers_references(tmp_path, "f01")
   217	    assert ok is True
   218	    assert missing == []
   219	
   220	
   221	def test_verify_passes_when_asset_already_exists_in_repo(tmp_path: Path):
   222	    # Asset exists on disk; manifest not required for pre-existing ones
   223	    img = tmp_path / "frontend" / "public" / "images" / "logo.png"
   224	    img.parent.mkdir(parents=True)
   225	    img.write_bytes(b"\x89PNG")
   226	    src = tmp_path / "frontend" / "src" / "App.tsx"
   227	    src.parent.mkdir(parents=True)
   228	    src.write_text('<img src="/images/logo.png" />')
   229	    save_feature_manifest(tmp_path, _mk_manifest("f01"))
   230	    ok, missing = verify_manifest_covers_references(tmp_path, "f01")
   231	    assert ok is True, f"should pass, missing={missing}"
   232	
   233	
   234	def test_verify_passes_when_manifest_entry_matches_by_id(tmp_path: Path):
   235	    src = tmp_path / "frontend" / "src" / "App.tsx"
   236	    src.parent.mkdir(parents=True)
   237	    src.write_text('<img src="/img/hero-bg.png" />')
   238	    save_feature_manifest(tmp_path, _mk_manifest(
   239	        "f01",
   240	        AssetManifestEntry(
   241	            id="hero-bg",  # matches filename base
   242	            name="Hero BG",
   243	            type="image",
   244	            description="",
   245	            generation_prompt="",
   246	        ),
   247	    ))
   248	    ok, missing = verify_manifest_covers_references(tmp_path, "f01")
   249	    assert ok is True, f"should pass by id match, missing={missing}"

exec
/bin/zsh -lc "nl -ba tests/unit/test_design_phase.py | sed -n '1,340p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Tests for Phase C design system phase."""
     2	
     3	from __future__ import annotations
     4	
     5	import json
     6	from pathlib import Path
     7	from unittest.mock import patch
     8	
     9	import pytest
    10	
    11	from ncdev.claude_session import ClaudeSessionResult
    12	from ncdev.v3.design_phase import (
    13	    DESIGN_TOOLS,
    14	    DesignPhaseResult,
    15	    existing_design_system_present,
    16	    is_ui_project,
    17	    run_design_phase,
    18	    stitch_available,
    19	)
    20	from ncdev.v3.models import DesignSystemDoc, TargetProjectContract
    21	
    22	
    23	def _web_contract(**overrides) -> TargetProjectContract:
    24	    defaults = dict(
    25	        project_name="myapp",
    26	        project_type="web",
    27	        frontend_framework="react",
    28	        design_archetype="Technical Elegance",
    29	        is_brownfield=False,
    30	    )
    31	    defaults.update(overrides)
    32	    return TargetProjectContract(**defaults)
    33	
    34	
    35	# ---------------------------------------------------------------------------
    36	# Helpers
    37	# ---------------------------------------------------------------------------
    38	
    39	
    40	def test_is_ui_project_detects_web_types():
    41	    assert is_ui_project(_web_contract(project_type="web"))
    42	    assert is_ui_project(_web_contract(project_type="webapp"))
    43	    assert is_ui_project(_web_contract(project_type="saas"))
    44	
    45	
    46	def test_is_ui_project_false_for_cli_and_library():
    47	    assert not is_ui_project(_web_contract(project_type="cli"))
    48	    assert not is_ui_project(_web_contract(project_type="library"))
    49	
    50	
    51	def test_existing_design_system_detects_populated_dir(tmp_path: Path):
    52	    ds = tmp_path / "docs" / "design-system"
    53	    ds.mkdir(parents=True)
    54	    (ds / "tokens.css").write_text(":root { --brand: #000; }")
    55	    assert existing_design_system_present(tmp_path) is True
    56	
    57	
    58	def test_existing_design_system_false_for_empty_or_missing(tmp_path: Path):
    59	    assert existing_design_system_present(tmp_path) is False
    60	    ds = tmp_path / "docs" / "design-system"
    61	    ds.mkdir(parents=True)
    62	    assert existing_design_system_present(tmp_path) is False
    63	
    64	
    65	def test_stitch_available_via_env_var(tmp_path: Path, monkeypatch):
    66	    fake_cfg = tmp_path / "stitch.json"
    67	    fake_cfg.write_text("{}")
    68	    monkeypatch.setenv("NCDEV_STITCH_MCP_CONFIG", str(fake_cfg))
    69	    assert stitch_available() is True
    70	
    71	
    72	def test_stitch_available_false_when_env_missing_and_no_config(monkeypatch, tmp_path):
    73	    monkeypatch.delenv("NCDEV_STITCH_MCP_CONFIG", raising=False)
    74	    # Point HOME at a temp dir that has no claude config
    75	    monkeypatch.setenv("HOME", str(tmp_path))
    76	    # Path.home() reads HOME on *nix — this should make it see no config
    77	    assert stitch_available() is False
    78	
    79	
    80	# ---------------------------------------------------------------------------
    81	# Non-UI skip path
    82	# ---------------------------------------------------------------------------
    83	
    84	
    85	def test_cli_project_skips_design_phase(tmp_path: Path):
    86	    contract = _web_contract(project_type="cli")
    87	    result = run_design_phase(contract, tmp_path, tmp_path / "out")
    88	    assert result.skipped is True
    89	    assert result.hard_failed is False
    90	    assert result.design_doc is None
    91	
    92	
    93	# ---------------------------------------------------------------------------
    94	# Hard-fail path
    95	# ---------------------------------------------------------------------------
    96	
    97	
    98	def test_greenfield_ui_without_stitch_or_designs_hard_fails(tmp_path: Path):
    99	    contract = _web_contract(is_brownfield=False)
   100	    output_dir = tmp_path / "out"
   101	
   102	    result = run_design_phase(
   103	        contract, tmp_path, output_dir,
   104	        stitch_probe=lambda: False,   # no Stitch
   105	    )
   106	
   107	    assert result.hard_failed is True
   108	    assert result.error is not None
   109	    assert "greenfield" in result.error.lower() or "design" in result.error.lower()
   110	    # Error artifact written for downstream processing / human
   111	    err = output_dir / "design-phase-error.json"
   112	    assert err.exists()
   113	    payload = json.loads(err.read_text(encoding="utf-8"))
   114	    assert "error" in payload
   115	    assert "fix" in payload
   116	
   117	
   118	# ---------------------------------------------------------------------------
   119	# Brownfield with existing design system
   120	# ---------------------------------------------------------------------------
   121	
   122	
   123	def test_brownfield_with_design_system_runs_summariser(tmp_path: Path):
   124	    contract = _web_contract(is_brownfield=True)
   125	    # Seed existing design system
   126	    ds = tmp_path / "docs" / "design-system"
   127	    ds.mkdir(parents=True)
   128	    (ds / "tokens.css").write_text(":root { --brand: #abcdef; }")
   129	
   130	    output_dir = tmp_path / "out"
   131	    captured: dict = {}
   132	
   133	    def fake_session(prompt, **kwargs):
   134	        captured["prompt"] = prompt
   135	        captured.update(kwargs)
   136	        doc = DesignSystemDoc(
   137	            project_name="myapp",
   138	            design_archetype="Technical Elegance",
   139	            source="existing",
   140	            tokens_files=["tokens.css"],
   141	        )
   142	        (output_dir / "design-system.json").write_text(
   143	            doc.model_dump_json(indent=2), encoding="utf-8",
   144	        )
   145	        return ClaudeSessionResult(success=True, final_text="summarised", exit_code=0)
   146	
   147	    with patch("ncdev.v3.design_phase.run_claude_session", side_effect=fake_session):
   148	        result = run_design_phase(
   149	            contract, tmp_path, output_dir,
   150	            stitch_probe=lambda: False,   # doesn't matter, existing wins
   151	        )
   152	
   153	    assert result.hard_failed is False
   154	    assert result.design_doc is not None
   155	    assert result.design_doc.source == "existing"
   156	    # Prompt must be the brownfield-summariser variant
   157	    assert "read the existing" in captured["prompt"].lower()
   158	    assert "Do NOT modify" in captured["prompt"]
   159	
   160	
   161	# ---------------------------------------------------------------------------
   162	# Stitch path
   163	# ---------------------------------------------------------------------------
   164	
   165	
   166	def test_greenfield_with_stitch_runs_stitch_prompt(tmp_path: Path):
   167	    contract = _web_contract(is_brownfield=False)
   168	    output_dir = tmp_path / "out"
   169	    captured: dict = {}
   170	
   171	    def fake_session(prompt, **kwargs):
   172	        captured["prompt"] = prompt
   173	        doc = DesignSystemDoc(
   174	            project_name="myapp",
   175	            design_archetype="Technical Elegance",
   176	            source="stitch",
   177	            stitch_project_id="stitch-abc",
   178	            tokens_files=["tokens.css", "tailwind.config.js"],
   179	        )
   180	        (output_dir / "design-system.json").write_text(
   181	            doc.model_dump_json(indent=2), encoding="utf-8",
   182	        )
   183	        return ClaudeSessionResult(success=True, final_text="stitch done", exit_code=0)
   184	
   185	    with patch("ncdev.v3.design_phase.run_claude_session", side_effect=fake_session):
   186	        result = run_design_phase(
   187	            contract, tmp_path, output_dir,
   188	            stitch_probe=lambda: True,
   189	        )
   190	
   191	    assert result.hard_failed is False
   192	    assert result.design_doc is not None
   193	    assert result.design_doc.source == "stitch"
   194	    assert result.design_doc.stitch_project_id == "stitch-abc"
   195	    # Stitch prompt
   196	    assert "Stitch" in captured["prompt"]
   197	    assert "MCP" in captured["prompt"]
   198	
   199	
   200	def test_stitch_phase_that_writes_error_file_is_hard_failed(tmp_path: Path):
   201	    contract = _web_contract(is_brownfield=False)
   202	    output_dir = tmp_path / "out"
   203	
   204	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   205	        output_dir.mkdir(parents=True, exist_ok=True)
   206	        (output_dir / "design-phase-error.json").write_text(
   207	            '{"error": "Stitch auth failed", "fix": "re-auth"}', encoding="utf-8",
   208	        )
   209	        return ClaudeSessionResult(success=True, final_text="stitch unreachable", exit_code=0)
   210	
   211	    with patch("ncdev.v3.design_phase.run_claude_session", side_effect=fake_session):
   212	        result = run_design_phase(
   213	            contract, tmp_path, output_dir,
   214	            stitch_probe=lambda: True,
   215	        )
   216	
   217	    assert result.hard_failed is True
   218	    assert "Stitch" in (result.error or "")
   219	
   220	
   221	# ---------------------------------------------------------------------------
   222	# Brownfield without designs + no Stitch: Claude decides
   223	# ---------------------------------------------------------------------------
   224	
   225	
   226	def test_brownfield_without_designs_and_no_stitch_lets_claude_decide(tmp_path: Path):
   227	    contract = _web_contract(is_brownfield=True)
   228	    output_dir = tmp_path / "out"
   229	    captured: dict = {}
   230	
   231	    def fake_session(prompt, **kwargs):
   232	        captured["prompt"] = prompt
   233	        doc = DesignSystemDoc(
   234	            project_name="myapp",
   235	            design_archetype="Technical Elegance",
   236	            source="claude_generated",
   237	        )
   238	        (output_dir / "design-system.json").write_text(
   239	            doc.model_dump_json(indent=2), encoding="utf-8",
   240	        )
   241	        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)
   242	
   243	    with patch("ncdev.v3.design_phase.run_claude_session", side_effect=fake_session):
   244	        result = run_design_phase(
   245	            contract, tmp_path, output_dir,
   246	            stitch_probe=lambda: False,
   247	        )
   248	
   249	    assert result.hard_failed is False
   250	    assert result.design_doc is not None
   251	    assert result.design_doc.source == "claude_generated"
   252	    # Prompt instructs Claude it MAY hard-fail itself if it thinks Stitch needed
   253	    assert "frontend-design" in captured["prompt"]
   254	    assert "design-phase-error.json" in captured["prompt"]
   255	
   256	
   257	def test_design_session_does_not_include_codex_protocol(tmp_path: Path):
   258	    contract = _web_contract(is_brownfield=True)
   259	    ds = tmp_path / "docs" / "design-system"
   260	    ds.mkdir(parents=True)
   261	    (ds / "tokens.css").write_text(":root {}")
   262	    output_dir = tmp_path / "out"
   263	    captured: dict = {}
   264	
   265	    def fake_session(prompt, **kwargs):
   266	        captured.update(kwargs)
   267	        doc = DesignSystemDoc(project_name="x", design_archetype="y", source="existing")
   268	        (output_dir / "design-system.json").write_text(doc.model_dump_json(), encoding="utf-8")
   269	        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)
   270	
   271	    with patch("ncdev.v3.design_phase.run_claude_session", side_effect=fake_session):
   272	        run_design_phase(
   273	            contract, tmp_path, output_dir,
   274	            stitch_probe=lambda: False,
   275	        )
   276	
   277	    # Design phase does not shell out to Codex — protocol must be off
   278	    assert captured["include_codex_protocol"] is False

exec
/bin/zsh -lc "nl -ba tests/unit/test_charter.py | sed -n '1,320p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Tests for Phase B charter generator."""
     2	
     3	from __future__ import annotations
     4	
     5	import json
     6	from pathlib import Path
     7	from unittest.mock import patch
     8	
     9	import pytest
    10	
    11	from ncdev.claude_session import ClaudeSessionResult
    12	from ncdev.v3.charter import (
    13	    build_charter_prompt,
    14	    generate_charter,
    15	    load_charter,
    16	    write_charter,
    17	)
    18	from ncdev.v3.models import (
    19	    CharterBundle,
    20	    FeatureQueueDoc,
    21	    FeatureStep,
    22	    TargetProjectContract,
    23	    VerificationContract,
    24	)
    25	
    26	
    27	def _fake_charter_bundle() -> CharterBundle:
    28	    return CharterBundle(
    29	        contract=TargetProjectContract(
    30	            project_name="myapp",
    31	            project_type="web",
    32	            backend_framework="fastapi",
    33	            frontend_framework="react",
    34	            database="mongodb",
    35	            auth_system="keycloak",
    36	            language_backend="python",
    37	            language_frontend="typescript",
    38	            deployment_target="docker",
    39	            ports={"frontend": 23000, "backend": 23001, "mongodb": 23002},
    40	            design_archetype="Technical Elegance",
    41	            design_system_source="stitch",
    42	        ),
    43	        verification=VerificationContract(
    44	            backend_health_url="http://localhost:23001/api/health",
    45	            frontend_url="http://localhost:23000",
    46	            backend_test_command="cd backend && pytest -q",
    47	            frontend_test_command="cd frontend && npm test -- --run",
    48	            required_screenshots=["homepage", "login"],
    49	            required_files=["docker-compose.yml", "backend/app/main.py"],
    50	        ),
    51	        feature_queue=FeatureQueueDoc(
    52	            project_name="myapp",
    53	            features=[
    54	                FeatureStep(
    55	                    feature_id="f01-scaffold",
    56	                    title="Scaffold project",
    57	                    description="Boot skeleton + health endpoint",
    58	                    acceptance_criteria=["Health endpoint returns 200"],
    59	                ),
    60	                FeatureStep(
    61	                    feature_id="f02-auth",
    62	                    title="Auth",
    63	                    description="Keycloak integration",
    64	                    acceptance_criteria=["Login works"],
    65	                    depends_on_features=["f01-scaffold"],
    66	                ),
    67	            ],
    68	        ),
    69	    )
    70	
    71	
    72	# ---------------------------------------------------------------------------
    73	# Prompt shape
    74	# ---------------------------------------------------------------------------
    75	
    76	
    77	def test_prompt_references_three_artifact_files(tmp_path: Path):
    78	    prompt = build_charter_prompt(
    79	        prd_path=tmp_path / "prd.md",
    80	        target_repo=None,
    81	        output_dir=tmp_path / "outputs",
    82	        project_type_hint="web",
    83	    )
    84	    assert "target-project-contract.json" in prompt
    85	    assert "verification-contract.json" in prompt
    86	    assert "feature-queue.json" in prompt
    87	    # Directs Claude to use the planning skill
    88	    assert "writing-plans" in prompt
    89	
    90	
    91	def test_prompt_includes_hard_fail_rule_for_greenfield_ui_without_design(tmp_path: Path):
    92	    prompt = build_charter_prompt(
    93	        prd_path=tmp_path / "prd.md",
    94	        target_repo=None,
    95	        output_dir=tmp_path / "outputs",
    96	    )
    97	    assert "charter-error.json" in prompt
    98	    assert "greenfield" in prompt.lower()
    99	    assert "design system" in prompt.lower() or "stitch" in prompt.lower()
   100	
   101	
   102	def test_prompt_includes_schema_excerpts(tmp_path: Path):
   103	    prompt = build_charter_prompt(
   104	        prd_path=tmp_path / "prd.md",
   105	        target_repo=tmp_path,
   106	        output_dir=tmp_path / "outputs",
   107	    )
   108	    # Hard-constraint fields surface in the prompt
   109	    assert "backend_framework" in prompt
   110	    assert "design_archetype" in prompt
   111	    assert "required_screenshots" in prompt
   112	
   113	
   114	# ---------------------------------------------------------------------------
   115	# Artifact round-trip
   116	# ---------------------------------------------------------------------------
   117	
   118	
   119	def test_write_and_load_charter_roundtrip(tmp_path: Path):
   120	    bundle = _fake_charter_bundle()
   121	    out = tmp_path / "outputs"
   122	    write_charter(bundle, out)
   123	
   124	    assert (out / "target-project-contract.json").exists()
   125	    assert (out / "verification-contract.json").exists()
   126	    assert (out / "feature-queue.json").exists()
   127	
   128	    loaded = load_charter(out)
   129	    assert loaded.contract.project_name == "myapp"
   130	    assert loaded.contract.design_archetype == "Technical Elegance"
   131	    assert loaded.verification.required_screenshots == ["homepage", "login"]
   132	    assert len(loaded.feature_queue.features) == 2
   133	    assert loaded.feature_queue.features[0].feature_id == "f01-scaffold"
   134	
   135	
   136	def test_load_charter_fails_when_file_missing(tmp_path: Path):
   137	    with pytest.raises(FileNotFoundError):
   138	        load_charter(tmp_path / "nonexistent")
   139	
   140	
   141	# ---------------------------------------------------------------------------
   142	# generate_charter — mocked Claude session
   143	# ---------------------------------------------------------------------------
   144	
   145	
   146	def test_generate_charter_success_loads_bundle(tmp_path: Path):
   147	    """Simulate a successful Claude session that writes the three artifacts."""
   148	    bundle = _fake_charter_bundle()
   149	
   150	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   151	        write_charter(bundle, kwargs["cwd"])
   152	        return ClaudeSessionResult(
   153	            success=True, final_text="charter written",
   154	            exit_code=0, duration_seconds=1.0,
   155	        )
   156	
   157	    with patch("ncdev.v3.charter.run_claude_session", side_effect=fake_session):
   158	        result_bundle, session = generate_charter(
   159	            prd_path=tmp_path / "prd.md",
   160	            output_dir=tmp_path / "outputs",
   161	        )
   162	
   163	    assert session.success is True
   164	    assert result_bundle is not None
   165	    assert result_bundle.contract.project_name == "myapp"
   166	
   167	
   168	def test_generate_charter_hard_fails_on_charter_error_file(tmp_path: Path):
   169	    """Greenfield UI without design system: Claude writes charter-error.json."""
   170	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   171	        out = kwargs["cwd"]
   172	        out.mkdir(parents=True, exist_ok=True)
   173	        (out / "charter-error.json").write_text(json.dumps({
   174	            "error": "greenfield UI project requires a design system",
   175	            "fix": "run stitch setup",
   176	        }), encoding="utf-8")
   177	        return ClaudeSessionResult(
   178	            success=True, final_text="hard fail: design required",
   179	            exit_code=0, duration_seconds=0.5,
   180	        )
   181	
   182	    with patch("ncdev.v3.charter.run_claude_session", side_effect=fake_session):
   183	        result_bundle, session = generate_charter(
   184	            prd_path=tmp_path / "prd.md",
   185	            output_dir=tmp_path / "outputs",
   186	        )
   187	
   188	    # Hard fail — no bundle returned even though session itself succeeded
   189	    assert result_bundle is None
   190	    assert session.success is True
   191	    assert (tmp_path / "outputs" / "charter-error.json").exists()
   192	
   193	
   194	def test_generate_charter_returns_none_when_session_fails(tmp_path: Path):
   195	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   196	        return ClaudeSessionResult(
   197	            success=False, final_text="", exit_code=1,
   198	            error="something broke",
   199	        )
   200	
   201	    with patch("ncdev.v3.charter.run_claude_session", side_effect=fake_session):
   202	        result_bundle, session = generate_charter(
   203	            prd_path=tmp_path / "prd.md",
   204	            output_dir=tmp_path / "outputs",
   205	        )
   206	
   207	    assert result_bundle is None
   208	    assert session.success is False
   209	
   210	
   211	def test_generate_charter_returns_none_on_invalid_json(tmp_path: Path):
   212	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   213	        out = kwargs["cwd"]
   214	        out.mkdir(parents=True, exist_ok=True)
   215	        (out / "target-project-contract.json").write_text("{not json", encoding="utf-8")
   216	        (out / "verification-contract.json").write_text("{}", encoding="utf-8")
   217	        (out / "feature-queue.json").write_text("{}", encoding="utf-8")
   218	        return ClaudeSessionResult(
   219	            success=True, final_text="done", exit_code=0,
   220	        )
   221	
   222	    with patch("ncdev.v3.charter.run_claude_session", side_effect=fake_session):
   223	        result_bundle, _ = generate_charter(
   224	            prd_path=tmp_path / "prd.md",
   225	            output_dir=tmp_path / "outputs",
   226	        )
   227	
   228	    assert result_bundle is None
   229	
   230	
   231	def test_generate_charter_uses_plan_tools_only(tmp_path: Path):
   232	    """The charter session must not have Bash or Edit — read + write only."""
   233	    captured: dict = {}
   234	
   235	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   236	        captured.update(kwargs)
   237	        write_charter(_fake_charter_bundle(), kwargs["cwd"])
   238	        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)
   239	
   240	    with patch("ncdev.v3.charter.run_claude_session", side_effect=fake_session):
   241	        generate_charter(
   242	            prd_path=tmp_path / "prd.md",
   243	            output_dir=tmp_path / "outputs",
   244	        )
   245	
   246	    tools = list(captured["tools"])
   247	    assert "Bash" not in tools
   248	    assert "Edit" not in tools
   249	    assert "Read" in tools
   250	    assert "Write" in tools
   251	    assert captured["include_codex_protocol"] is False

exec
/bin/zsh -lc "nl -ba tests/unit/test_dev.py | sed -n '1,280p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Tests for the thin ``ncdev dev`` orchestrator."""
     2	
     3	from __future__ import annotations
     4	
     5	import subprocess
     6	from pathlib import Path
     7	from unittest.mock import patch
     8	
     9	import pytest
    10	
    11	from ncdev import dev
    12	from ncdev.claude_session import ClaudeSessionResult
    13	
    14	
    15	def _init_git(path: Path) -> None:
    16	    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    17	    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    18	    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    19	    (path / "README.md").write_text("init")
    20	    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    21	    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(path), check=True)
    22	
    23	
    24	@pytest.fixture(autouse=True)
    25	def _patch_citex(monkeypatch):
    26	    """Bypass Citex health checks in tests."""
    27	    monkeypatch.setattr(dev, "require_citex", lambda url=None: None)
    28	    monkeypatch.setattr(dev, "citex_store", lambda *a, **k: True)
    29	
    30	
    31	# ---------------------------------------------------------------------------
    32	# Prompt shape
    33	# ---------------------------------------------------------------------------
    34	
    35	
    36	def test_task_prompt_references_project_and_skills(tmp_path: Path):
    37	    prompt = dev._build_task_prompt(
    38	        "refactor the auth flow",
    39	        project_path=tmp_path,
    40	        project_id="myapp",
    41	        mode="bugfix",
    42	    )
    43	    assert "refactor the auth flow" in prompt
    44	    assert "myapp" in prompt
    45	    assert str(tmp_path) in prompt
    46	    # References the Codex protocol and skill machinery but does not inline them
    47	    assert "Codex protocol" in prompt
    48	    assert "test-driven-development" in prompt
    49	    assert "verification-before-completion" in prompt
    50	    assert "systematic-debugging" in prompt
    51	    # Explicit Codex exec command shape appears as guidance
    52	    assert "codex exec --full-auto" in prompt
    53	
    54	
    55	def test_task_prompt_is_short():
    56	    prompt = dev._build_task_prompt("X", Path("/p"), "pid", "auto")
    57	    # Keep it tight — this is the whole point of the rewrite
    58	    assert len(prompt) < 2500, f"prompt is {len(prompt)} chars, should stay lean"
    59	
    60	
    61	# ---------------------------------------------------------------------------
    62	# Successful run
    63	# ---------------------------------------------------------------------------
    64	
    65	
    66	def test_run_dev_passes_when_session_commits_cleanly(tmp_path: Path):
    67	    project = tmp_path / "app"
    68	    project.mkdir()
    69	    _init_git(project)
    70	
    71	    def fake_session(prompt, **kwargs):  # noqa: ARG001
    72	        # Simulate Claude committing a clean change
    73	        (project / "foo.py").write_text("x = 1")
    74	        subprocess.run(["git", "add", "-A"], cwd=str(project), check=True)
    75	        subprocess.run(["git", "commit", "-q", "-m", "feat: foo"],
    76	                       cwd=str(project), check=True)
    77	        return ClaudeSessionResult(
    78	            success=True, final_text="built foo", exit_code=0,
    79	            duration_seconds=1.0, total_cost_usd=0.05,
    80	            skills_invoked=["test-driven-development"],
    81	        )
    82	
    83	    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
    84	        result = dev.run_dev(project, task="add foo", mode="auto")
    85	
    86	    assert result["status"] == "passed"
    87	    assert result["commit_sha"] != ""
    88	    assert "test-driven-development" in result["skills_invoked"]
    89	
    90	
    91	# ---------------------------------------------------------------------------
    92	# Broken-tag recovery
    93	# ---------------------------------------------------------------------------
    94	
    95	
    96	def test_dirty_working_tree_gets_broken_commit(tmp_path: Path):
    97	    project = tmp_path / "app"
    98	    project.mkdir()
    99	    _init_git(project)
   100	
   101	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   102	        # Claude left changes uncommitted
   103	        (project / "halfdone.py").write_text("# WIP")
   104	        return ClaudeSessionResult(success=False, final_text="stuck", exit_code=1)
   105	
   106	    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
   107	        result = dev.run_dev(project, task="try something", mode="auto")
   108	
   109	    assert result["status"] == "failed"
   110	    # A [BROKEN] commit exists so we can recover
   111	    log = subprocess.run(
   112	        ["git", "log", "--oneline"], cwd=str(project),
   113	        capture_output=True, text=True, check=True,
   114	    )
   115	    assert "[BROKEN]" in log.stdout
   116	
   117	
   118	def test_no_work_done_is_failed(tmp_path: Path):
   119	    project = tmp_path / "app"
   120	    project.mkdir()
   121	    _init_git(project)
   122	
   123	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   124	        return ClaudeSessionResult(
   125	            success=True, final_text="nothing to do", exit_code=0,
   126	        )
   127	
   128	    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
   129	        result = dev.run_dev(project, task="x", mode="auto")
   130	
   131	    assert result["status"] == "failed"
   132	
   133	
   134	# ---------------------------------------------------------------------------
   135	# Session options flow through
   136	# ---------------------------------------------------------------------------
   137	
   138	
   139	def test_max_budget_propagates_to_session(tmp_path: Path):
   140	    project = tmp_path / "app"
   141	    project.mkdir()
   142	    _init_git(project)
   143	    captured: dict = {}
   144	
   145	    def fake_session(prompt, **kwargs):
   146	        captured.update(kwargs)
   147	        (project / "x").write_text("x")
   148	        subprocess.run(["git", "add", "-A"], cwd=str(project), check=True)
   149	        subprocess.run(["git", "commit", "-q", "-m", "feat: x"],
   150	                       cwd=str(project), check=True)
   151	        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)
   152	
   153	    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
   154	        dev.run_dev(project, task="x", max_budget_usd=1.25)
   155	
   156	    assert captured["max_budget_usd"] == 1.25
   157	    # Must include Bash/Skill/Task so Claude can shell to Codex + invoke skills
   158	    tools = list(captured["tools"])
   159	    assert "Bash" in tools and "Skill" in tools and "Task" in tools
   160	    # Codex protocol must be injected — no opt-out for dev mode
   161	    assert captured["include_codex_protocol"] is True
   162	
   163	
   164	# ---------------------------------------------------------------------------
   165	# Citex summary ingestion
   166	# ---------------------------------------------------------------------------
   167	
   168	
   169	def test_run_summary_ingested_to_citex(tmp_path: Path, monkeypatch):
   170	    project = tmp_path / "app"
   171	    project.mkdir()
   172	    _init_git(project)
   173	
   174	    calls = []
   175	    monkeypatch.setattr(dev, "citex_store",
   176	                        lambda pid, content, metadata: calls.append((pid, content, metadata)) or True)
   177	
   178	    def fake_session(prompt, **kwargs):  # noqa: ARG001
   179	        (project / "a").write_text("a")
   180	        subprocess.run(["git", "add", "-A"], cwd=str(project), check=True)
   181	        subprocess.run(["git", "commit", "-q", "-m", "feat: a"],
   182	                       cwd=str(project), check=True)
   183	        return ClaudeSessionResult(
   184	            success=True, final_text="done", exit_code=0,
   185	            skills_invoked=["verification-before-completion"],
   186	        )
   187	
   188	    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
   189	        dev.run_dev(project, task="do a thing", mode="enhance")
   190	
   191	    assert len(calls) == 1
   192	    pid, content, metadata = calls[0]
   193	    assert pid == "app"
   194	    assert "do a thing" in content
   195	    assert metadata["status"] == "passed"
   196	    assert metadata["mode"] == "enhance"
   197	    assert "verification-before-completion" in metadata["skills_invoked"]

exec
/bin/zsh -lc "nl -ba tests/test_ncdev_v2/test_modes.py | sed -n '1,240p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Tests for the `mode` switch + MODE_PRESETS in v2 config."""
     2	
     3	from __future__ import annotations
     4	
     5	from pathlib import Path
     6	
     7	import pytest
     8	import yaml
     9	
    10	from ncdev.v2.config import (
    11	    DEFAULT_MODE,
    12	    MODE_PRESETS,
    13	    NCDevV2Config,
    14	    ROUTING_TASK_KEYS,
    15	    load_v2_config,
    16	)
    17	from ncdev.v2.models import TaskType
    18	
    19	
    20	# ---------------------------------------------------------------------------
    21	# Preset coverage
    22	# ---------------------------------------------------------------------------
    23	
    24	
    25	@pytest.mark.parametrize("mode,expected", [
    26	    ("codex_only", "openai_codex"),
    27	    ("claude_only", "anthropic_claude_code"),
    28	    ("openrouter", "openrouter"),
    29	])
    30	def test_uniform_preset_maps_every_task_to_one_provider(mode, expected):
    31	    cfg = NCDevV2Config(mode=mode)
    32	    for key in ROUTING_TASK_KEYS:
    33	        assert getattr(cfg.routing, key) == [expected], (
    34	            f"mode={mode} key={key} expected=[{expected}] "
    35	            f"actual={getattr(cfg.routing, key)}"
    36	        )
    37	
    38	
    39	def test_claude_plan_codex_build_splits_planning_from_impl():
    40	    cfg = NCDevV2Config(mode="claude_plan_codex_build")
    41	    # Planning/review go to Claude
    42	    for key in ("source_ingest", "design_brief", "review", "second_opinion",
    43	                "market_research", "feature_extraction", "sentinel_reproduce"):
    44	        assert getattr(cfg.routing, key) == ["anthropic_claude_code"], key
    45	    # Development/tests go to Codex
    46	    for key in ("implementation", "test_authoring", "sentinel_fix"):
    47	        assert getattr(cfg.routing, key) == ["openai_codex"], key
    48	
    49	
    50	def test_custom_mode_preserves_hand_tuned_routing():
    51	    cfg = NCDevV2Config(
    52	        mode="custom",
    53	        routing={
    54	            "implementation": ["anthropic_claude_code"],
    55	            "review": ["openai_codex"],
    56	        },
    57	    )
    58	    assert cfg.routing.implementation == ["anthropic_claude_code"]
    59	    assert cfg.routing.review == ["openai_codex"]
    60	
    61	
    62	def test_unknown_mode_rejected():
    63	    with pytest.raises(ValueError, match="Unknown mode"):
    64	        NCDevV2Config(mode="nonsense")
    65	
    66	
    67	def test_default_mode_is_claude_plan_codex_build():
    68	    assert DEFAULT_MODE == "claude_plan_codex_build"
    69	    cfg = NCDevV2Config()
    70	    assert cfg.mode == DEFAULT_MODE
    71	    assert cfg.routing.implementation == ["openai_codex"]
    72	    assert cfg.routing.design_brief == ["anthropic_claude_code"]
    73	
    74	
    75	def test_all_presets_cover_all_routing_keys():
    76	    """Guards against forgetting a key when a new routing field is added."""
    77	    for preset_name, preset in MODE_PRESETS.items():
    78	        if not preset:  # "custom"
    79	            continue
    80	        assert set(preset.keys()) == set(ROUTING_TASK_KEYS), (
    81	            f"preset '{preset_name}' is missing keys: "
    82	            f"{set(ROUTING_TASK_KEYS) - set(preset.keys())}"
    83	        )
    84	
    85	
    86	# ---------------------------------------------------------------------------
    87	# Persistence — mode survives YAML round-trip and is applied on reload.
    88	# ---------------------------------------------------------------------------
    89	
    90	
    91	def test_mode_roundtrip_via_yaml(tmp_path: Path):
    92	    cfg_path = tmp_path / ".nc-dev" / "v2" / "config.yaml"
    93	    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    94	    NCDevV2Config(mode="codex_only").to_yaml_dict()
    95	    raw = NCDevV2Config(mode="codex_only").to_yaml_dict()
    96	    yaml.safe_dump(raw, cfg_path.open("w"), sort_keys=False)
    97	
    98	    loaded = load_v2_config(tmp_path)
    99	    assert loaded.mode == "codex_only"
   100	    assert loaded.routing.design_brief == ["openai_codex"]
   101	    assert loaded.routing.implementation == ["openai_codex"]
   102	
   103	
   104	def test_yaml_without_mode_field_loads_with_default(tmp_path: Path):
   105	    cfg_path = tmp_path / ".nc-dev" / "v2" / "config.yaml"
   106	    cfg_path.parent.mkdir(parents=True, exist_ok=True)
   107	    cfg_path.write_text("routing:\n  implementation: [openai_codex]\n")
   108	
   109	    loaded = load_v2_config(tmp_path)
   110	    assert loaded.mode == DEFAULT_MODE
   111	    # Default mode's preset overrides whatever routing was in the file.
   112	    assert loaded.routing.design_brief == ["anthropic_claude_code"]
   113	
   114	
   115	# ---------------------------------------------------------------------------
   116	# providers_for() reflects the active mode.
   117	# ---------------------------------------------------------------------------
   118	
   119	
   120	@pytest.mark.parametrize("mode,task,expected", [
   121	    ("codex_only", TaskType.DESIGN_BRIEF, ["openai_codex"]),
   122	    ("claude_only", TaskType.BUILD_BATCH, ["anthropic_claude_code"]),
   123	    ("openrouter", TaskType.TEST_AUTHORING, ["openrouter"]),
   124	    ("claude_plan_codex_build", TaskType.DESIGN_BRIEF, ["anthropic_claude_code"]),
   125	    ("claude_plan_codex_build", TaskType.BUILD_BATCH, ["openai_codex"]),
   126	])
   127	def test_providers_for_task_respects_mode(mode, task, expected):
   128	    cfg = NCDevV2Config(mode=mode)
   129	    assert cfg.routing.providers_for(task) == expected

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/design_phase.py | sed -n '318,380p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   318	
   319	def _load_design_doc(output_dir: Path) -> DesignSystemDoc | None:
   320	    path = output_dir / "design-system.json"
   321	    if not path.exists():
   322	        return None
   323	    try:
   324	        return DesignSystemDoc.model_validate_json(path.read_text(encoding="utf-8"))
   325	    except Exception:  # noqa: BLE001
   326	        return None

exec
/bin/zsh -lc "nl -ba scripts/ncdev-hooks/settings.json | sed -n '1,240p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	{
     2	  "_comment": "NC Dev System — Claude Code hooks wired in at session spawn. Passed via --settings <this file> by claude_executor and dev.py. pre_bash_guard.py blocks git commit commands that violate Conventional Commits or contain prohibited patterns; force-push to protected branches requires NCDEV_ALLOW_FORCE_PUSH=1.",
     3	  "hooks": {
     4	    "PreToolUse": [
     5	      {
     6	        "matcher": "Bash",
     7	        "hooks": [
     8	          {
     9	            "type": "command",
    10	            "command": "python3 ${NCDEV_HOOKS_DIR:-.}/pre_bash_guard.py"
    11	          }
    12	        ]
    13	      }
    14	    ]
    15	  }
    16	}

codex
I’m in the test and state layer now. The V3 tests are almost entirely mocked process simulations, which is useful for shape but leaves the actual Claude CLI, hooks, and git-failure interactions mostly unproven.
exec
/bin/zsh -lc "rg -n \"_commit_broken\\(|_commit_broken_leftovers\\(|charter-error|design-phase-error|verification.overall_passed|minimum_test_count|required_screenshots|backend_health_url|frontend_url|e2e_test_command|app_boots\" src/ncdev -S" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc 'rg -n "resume|state.json|total_cost_usd|aggregate.*cost|cost roll|partial|BROKEN|clarification|I need clarification|session.success" src tests -S' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
tests/test_ncdev_v2/test_sentinel_cli.py:41:def test_cli_fix_resume_run_id() -> None:
src/ncdev/dev.py:17:5. Commit any dirty leftovers with ``[BROKEN]`` if Claude exited without
src/ncdev/dev.py:140:    """Commit leftover dirty tree with [BROKEN] tag for recoverability."""
src/ncdev/dev.py:145:         f"[BROKEN] ncdev dev: {task[:80]}\n\n"
src/ncdev/dev.py:266:    if not session.success or not made_commit:
src/ncdev/dev.py:269:        # Recoverability: commit leftovers with [BROKEN]
src/ncdev/dev.py:272:            console.print(f"  [yellow]Committed leftovers with [BROKEN] tag: {broken_sha[:8]}[/yellow]")
src/ncdev/dev.py:298:                "total_cost_usd": session.total_cost_usd,
src/ncdev/dev.py:312:        + (f"\n[bold]Cost:[/bold] ${session.total_cost_usd:.3f}"
src/ncdev/dev.py:313:           if session.total_cost_usd is not None else ""),
src/ncdev/dev.py:325:        "total_cost_usd": session.total_cost_usd,
src/ncdev/claude_session.py:60:    total_cost_usd: float | None = None
src/ncdev/claude_session.py:71:        if self.total_cost_usd is not None:
src/ncdev/claude_session.py:72:            parts.append(f"cost=${self.total_cost_usd:.3f}")
src/ncdev/claude_session.py:197:        "--include-partial-messages",
src/ncdev/claude_session.py:286:                total_cost = event.get("total_cost_usd", total_cost)
src/ncdev/claude_session.py:309:            total_cost_usd=total_cost,
src/ncdev/claude_session.py:340:        total_cost_usd=total_cost,
tests/unit/test_claude_session.py:194:        {"type": "result", "result": "done", "total_cost_usd": 0.42},
tests/unit/test_claude_session.py:205:    assert result.total_cost_usd == 0.42
tests/unit/test_claude_session.py:224:        {"type": "result", "result": "build complete", "total_cost_usd": 0.10},
tests/unit/test_claude_session.py:336:    events = [{"type": "result", "result": "partial"}]
tests/unit/test_claude_session.py:406:        {"type": "result", "result": "ok", "total_cost_usd": 1.23},
tests/unit/test_charter.py:163:    assert session.success is True
tests/unit/test_charter.py:190:    assert session.success is True
tests/unit/test_charter.py:208:    assert session.success is False
tests/unit/test_dev.py:79:            duration_seconds=1.0, total_cost_usd=0.05,
tests/unit/test_dev.py:110:    # A [BROKEN] commit exists so we can recover
tests/unit/test_dev.py:115:    assert "[BROKEN]" in log.stdout
tests/unit/test_claude_executor.py:150:            duration_seconds=2.0, total_cost_usd=0.42,
tests/unit/test_claude_executor.py:208:        # commit with [BROKEN] tag so the next feature has context.
tests/unit/test_claude_executor.py:224:    # A [BROKEN] commit should exist
tests/unit/test_claude_executor.py:229:    assert "[BROKEN]" in log.stdout
src/ncdev/artifacts/state.py:76:    path = Path(state.run_dir) / "run-state.json"
src/ncdev/v3/charter.py:215:    if not session.success:
src/ncdev/v3/engine.py:19:    * commits on pass, tags [BROKEN] on exhaustion
src/ncdev/v3/engine.py:229:    state.status = "passed" if not failed else ("partial" if passed else "failed")
src/ncdev/v3/engine.py:288:    (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
src/ncdev/v3/state_scanner.py:4:what's already built, so the engine can skip completed work and resume from
src/ncdev/v3/state_scanner.py:115:        # Accept green runs and partially green runs that still discovered passing tests.
src/project-template-api/phased_development_plan.md:409:- Implement partial state updates for efficiency
src/ncdev/v3/claude_executor.py:21:         * changes present but no commit     → commit with [BROKEN] tag
src/ncdev/v3/claude_executor.py:234:    if session.success and made_commit and not dirty and verification.overall_passed:
src/ncdev/v3/claude_executor.py:241:        # Something is wrong. Commit whatever is there with [BROKEN] tag
src/ncdev/v3/claude_executor.py:268:        "success": session.success,
src/ncdev/v3/claude_executor.py:275:        "total_cost_usd": session.total_cost_usd,
src/ncdev/v3/claude_executor.py:415:             f"[BROKEN] {feature.feature_id}: {feature.title}\n\n"
src/ncdev/v2/engine.py:57:    path = workspace / ".nc-dev" / "v2" / "runs" / run_id / "run-state.json"

 succeeded in 0ms:
src/ncdev/cli.py:61:def _check_app_boots(target_path: Path) -> bool:
src/ncdev/cli.py:224:        if not _check_app_boots(target):
src/ncdev/dev.py:139:def _commit_broken_leftovers(project_path: Path, task: str) -> str:
src/ncdev/dev.py:270:        broken_sha = _commit_broken_leftovers(project_path, task)
src/ncdev/v3/design_phase.py:163:  ``{output_dir}/design-phase-error.json`` with an actionable message.
src/ncdev/v3/design_phase.py:232:        err_path = output_dir / "design-phase-error.json"
src/ncdev/v3/design_phase.py:274:        err_path = output_dir / "design-phase-error.json"
src/ncdev/v3/design_phase.py:279:                error="Stitch design phase failed — see design-phase-error.json",
src/ncdev/v3/design_phase.py:296:        f"designs to proceed, write design-phase-error.json instead."
src/ncdev/v3/design_phase.py:308:    err_path = output_dir / "design-phase-error.json"
src/ncdev/v3/engine.py:108:                f"See: {outputs_dir}/charter-error.json (if present) "
src/ncdev/v3/engine.py:147:                f"See: {outputs_dir}/design-phase-error.json",
src/ncdev/v3/charter.py:82:- `required_screenshots` — list the key pages/routes that must have a
src/ncdev/v3/charter.py:109:writing ONLY a file named `charter-error.json` with:
src/ncdev/v3/charter.py:193:    session failed, produced invalid JSON, or wrote a ``charter-error.json``
src/ncdev/v3/charter.py:211:    error_path = output_dir / "charter-error.json"
src/ncdev/v3/claude_executor.py:234:    if session.success and made_commit and not dirty and verification.overall_passed:
src/ncdev/v3/claude_executor.py:236:    elif made_commit and verification.overall_passed:
src/ncdev/v3/claude_executor.py:244:            _commit_broken(target_path, feature)
src/ncdev/v3/claude_executor.py:409:def _commit_broken(target_path: Path, feature: FeatureStep) -> None:
src/ncdev/v3/models.py:84:    app_boots: bool = False
src/ncdev/v3/models.py:195:    backend_health_url: str = ""       # e.g. http://localhost:23001/api/health
src/ncdev/v3/models.py:196:    frontend_url: str = ""
src/ncdev/v3/models.py:202:    e2e_test_command: str = ""         # e.g. "cd frontend && npx playwright test"
src/ncdev/v3/models.py:203:    minimum_test_count: int = 1
src/ncdev/v3/models.py:206:    required_screenshots: list[str] = Field(default_factory=list)

exec
/bin/zsh -lc "rg -n \"except:\\\\s\\*pass|prohibited_patterns|grep_for_prohibited|git diff --cached|git commit -m|CONVENTIONAL_RE|TaskType\" src tests -S" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
src/ncdev/v3/models.py:83:    prohibited_patterns: list[str] = Field(default_factory=list)
src/ncdev/v3/models.py:217:    prohibited_patterns: list[str] = Field(default_factory=lambda: [
src/ncdev/v3/charter.py:84:- Keep `prohibited_patterns` as-is unless the PRD explicitly calls out
src/ncdev/v3/claude_executor.py:156:- Any of the `prohibited_patterns` in the verification contract
src/ncdev/v3/claude_executor.py:311:    patterns = bundle.verification.prohibited_patterns
src/ncdev/v3/claude_executor.py:313:        bad = _grep_for_prohibited(target_path, patterns)
src/ncdev/v3/claude_executor.py:319:    ver.prohibited_patterns = reasons if any("prohibited" in r for r in reasons) else []
src/ncdev/v3/claude_executor.py:323:def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
tests/test_ncdev_v2/test_v2_routing.py:3:from ncdev.v2.models import TaskType
tests/test_ncdev_v2/test_v2_routing.py:14:    assert by_task[TaskType.BUILD_BATCH].provider == "openai_codex"
tests/test_ncdev_v2/test_v2_routing.py:15:    assert by_task[TaskType.BUILD_BATCH].model == "gpt-5.4"
tests/test_ncdev_v2/test_v2_routing.py:17:    assert by_task[TaskType.MARKET_RESEARCH].provider == "anthropic_claude_code"
tests/test_ncdev_v2/test_v2_routing.py:18:    assert by_task[TaskType.MARKET_RESEARCH].model == "opus"
tests/test_ncdev_v2/test_modes.py:17:from ncdev.v2.models import TaskType
tests/test_ncdev_v2/test_modes.py:121:    ("codex_only", TaskType.DESIGN_BRIEF, ["openai_codex"]),
tests/test_ncdev_v2/test_modes.py:122:    ("claude_only", TaskType.BUILD_BATCH, ["anthropic_claude_code"]),
tests/test_ncdev_v2/test_modes.py:123:    ("openrouter", TaskType.TEST_AUTHORING, ["openrouter"]),
tests/test_ncdev_v2/test_modes.py:124:    ("claude_plan_codex_build", TaskType.DESIGN_BRIEF, ["anthropic_claude_code"]),
tests/test_ncdev_v2/test_modes.py:125:    ("claude_plan_codex_build", TaskType.BUILD_BATCH, ["openai_codex"]),
src/ncdev/adapters/base.py:13:    TaskType,
src/ncdev/adapters/base.py:54:        task_type: TaskType,
src/ncdev/adapters/base.py:64:        task_type: TaskType,
tests/test_ncdev_v2/test_v2_config.py:4:from ncdev.v2.models import TaskType
tests/test_ncdev_v2/test_v2_config.py:14:    assert config.routing.providers_for(TaskType.BUILD_BATCH) == ["openai_codex"]
tests/test_ncdev_v2/test_v2_config.py:15:    assert config.routing.providers_for(TaskType.MARKET_RESEARCH) == ["anthropic_claude_code"]
src/ncdev/adapters/anthropic_claude_code.py:11:from ncdev.v2.models import CapabilityDescriptor, TaskRequestDoc, TaskType
src/ncdev/adapters/anthropic_claude_code.py:14:TASK_REQUEST_TITLES: dict[TaskType, str] = {
src/ncdev/adapters/anthropic_claude_code.py:15:    TaskType.SOURCE_INGEST: "Normalize source inputs",
src/ncdev/adapters/anthropic_claude_code.py:16:    TaskType.REPO_ANALYSIS: "Analyze repository structure",
src/ncdev/adapters/anthropic_claude_code.py:17:    TaskType.MARKET_RESEARCH: "Synthesize market research",
src/ncdev/adapters/anthropic_claude_code.py:18:    TaskType.FEATURE_EXTRACTION: "Extract feature map",
src/ncdev/adapters/anthropic_claude_code.py:19:    TaskType.UX_ANALYSIS: "Develop UX recommendations",
src/ncdev/adapters/anthropic_claude_code.py:20:    TaskType.DESIGN_BRIEF: "Generate design brief",
src/ncdev/adapters/anthropic_claude_code.py:21:    TaskType.QA_SWEEP: "Review verification coverage",
src/ncdev/adapters/anthropic_claude_code.py:22:    TaskType.DELIVERY_PACK: "Assemble delivery summary",
src/ncdev/adapters/anthropic_claude_code.py:26:TASK_REQUEST_OUTPUTS: dict[TaskType, list[str]] = {
src/ncdev/adapters/anthropic_claude_code.py:27:    TaskType.SOURCE_INGEST: ["source-pack.json"],
src/ncdev/adapters/anthropic_claude_code.py:28:    TaskType.REPO_ANALYSIS: ["repo-analysis.md"],
src/ncdev/adapters/anthropic_claude_code.py:29:    TaskType.MARKET_RESEARCH: ["research-pack.json"],
src/ncdev/adapters/anthropic_claude_code.py:30:    TaskType.FEATURE_EXTRACTION: ["feature-map.json"],
src/ncdev/adapters/anthropic_claude_code.py:31:    TaskType.UX_ANALYSIS: ["ux-analysis.md"],
src/ncdev/adapters/anthropic_claude_code.py:32:    TaskType.DESIGN_BRIEF: ["design-brief.json"],
src/ncdev/adapters/anthropic_claude_code.py:33:    TaskType.QA_SWEEP: ["qa-findings.json"],
src/ncdev/adapters/anthropic_claude_code.py:34:    TaskType.DELIVERY_PACK: ["delivery-report.md"],
src/ncdev/adapters/anthropic_claude_code.py:97:        task_type: TaskType,
src/ncdev/adapters/anthropic_claude_code.py:130:        task_type: TaskType,
tests/test_ncdev_v2/test_sentinel_models.py:24:    TaskType,
tests/test_ncdev_v2/test_sentinel_models.py:32:# TaskType enum
tests/test_ncdev_v2/test_sentinel_models.py:34:class TestTaskTypeEnumExtensions:
tests/test_ncdev_v2/test_sentinel_models.py:36:        assert TaskType.SENTINEL_FIX.value == "sentinel_fix"
tests/test_ncdev_v2/test_sentinel_models.py:39:        assert TaskType.SENTINEL_REPRODUCE.value == "sentinel_reproduce"
tests/test_ncdev_v2/test_sentinel_models.py:42:        members = list(TaskType)
tests/test_ncdev_v2/test_sentinel_models.py:43:        assert members[-2] == TaskType.SENTINEL_FIX
tests/test_ncdev_v2/test_sentinel_models.py:44:        assert members[-1] == TaskType.SENTINEL_REPRODUCE
src/ncdev/adapters/openai_codex.py:11:from ncdev.v2.models import CapabilityDescriptor, TaskRequestDoc, TaskType
src/ncdev/adapters/openai_codex.py:14:TASK_REQUEST_TITLES: dict[TaskType, str] = {
src/ncdev/adapters/openai_codex.py:15:    TaskType.BUILD_BATCH: "Implement build batch",
src/ncdev/adapters/openai_codex.py:16:    TaskType.TEST_AUTHORING: "Author target-project tests",
src/ncdev/adapters/openai_codex.py:17:    TaskType.FIX_BATCH: "Repair failing implementation batch",
src/ncdev/adapters/openai_codex.py:18:    TaskType.QA_SWEEP: "Review implementation evidence",
src/ncdev/adapters/openai_codex.py:22:TASK_REQUEST_OUTPUTS: dict[TaskType, list[str]] = {
src/ncdev/adapters/openai_codex.py:23:    TaskType.BUILD_BATCH: ["target-project code changes", "target-project tests"],
src/ncdev/adapters/openai_codex.py:24:    TaskType.TEST_AUTHORING: ["unit tests", "integration tests", "playwright tests"],
src/ncdev/adapters/openai_codex.py:25:    TaskType.FIX_BATCH: ["bug fixes", "regression coverage"],
src/ncdev/adapters/openai_codex.py:26:    TaskType.QA_SWEEP: ["review notes", "issue bundle candidates"],
src/ncdev/adapters/openai_codex.py:85:        task_type: TaskType,
src/ncdev/adapters/openai_codex.py:119:        task_type: TaskType,
tests/test_ncdev_v2/test_sentinel_config.py:9:from ncdev.v2.models import TaskType
tests/test_ncdev_v2/test_sentinel_config.py:53:    providers = config.routing.providers_for(TaskType.SENTINEL_REPRODUCE)
tests/test_ncdev_v2/test_sentinel_config.py:59:    providers = config.routing.providers_for(TaskType.SENTINEL_FIX)
tests/test_ncdev_v2/test_v2_adapters.py:6:from ncdev.v2.models import TaskType
tests/test_ncdev_v2/test_v2_adapters.py:38:                task_type=TaskType.MARKET_RESEARCH,
tests/test_ncdev_v2/test_v2_adapters.py:60:                task_type=TaskType.MARKET_RESEARCH,
tests/test_ncdev_v2/test_v2_adapters.py:85:                task_type=TaskType.TEST_AUTHORING,
tests/test_ncdev_v2/test_v2_adapters.py:116:                task_type=TaskType.TEST_AUTHORING,
src/ncdev/v2/routing.py:5:from ncdev.v2.models import RoutingDecision, RoutingPlanDoc, TaskType
src/ncdev/v2/routing.py:8:TASK_MODEL_PREFS: dict[TaskType, str] = {
src/ncdev/v2/routing.py:9:    TaskType.SOURCE_INGEST: "planning",
src/ncdev/v2/routing.py:10:    TaskType.REPO_ANALYSIS: "planning",
src/ncdev/v2/routing.py:11:    TaskType.MARKET_RESEARCH: "planning",
src/ncdev/v2/routing.py:12:    TaskType.FEATURE_EXTRACTION: "planning",
src/ncdev/v2/routing.py:13:    TaskType.UX_ANALYSIS: "planning",
src/ncdev/v2/routing.py:14:    TaskType.DESIGN_BRIEF: "planning",
src/ncdev/v2/routing.py:15:    TaskType.DESIGN_REFERENCE_GENERATION: "planning",
src/ncdev/v2/routing.py:16:    TaskType.BUILD_BATCH: "implementation",
src/ncdev/v2/routing.py:17:    TaskType.TEST_PLAN_GENERATION: "planning",
src/ncdev/v2/routing.py:18:    TaskType.TEST_AUTHORING: "test_implementation",
src/ncdev/v2/routing.py:19:    TaskType.QA_SWEEP: "review",
src/ncdev/v2/routing.py:20:    TaskType.ISSUE_TRIAGE: "review",
src/ncdev/v2/routing.py:21:    TaskType.FIX_BATCH: "implementation",
src/ncdev/v2/routing.py:22:    TaskType.DELIVERY_PACK: "review",
src/ncdev/v2/routing.py:26:def _choose_model(config: NCDevV2Config, provider_name: str, adapter: ProviderAdapter, task_type: TaskType) -> str:
src/ncdev/v2/routing.py:39:        TaskType.SOURCE_INGEST,
src/ncdev/v2/routing.py:40:        TaskType.REPO_ANALYSIS,
src/ncdev/v2/routing.py:41:        TaskType.MARKET_RESEARCH,
src/ncdev/v2/routing.py:42:        TaskType.FEATURE_EXTRACTION,
src/ncdev/v2/routing.py:43:    TaskType.DESIGN_BRIEF,
src/ncdev/v2/routing.py:44:    TaskType.BUILD_BATCH,
src/ncdev/v2/routing.py:45:    TaskType.FIX_BATCH,
src/ncdev/v2/routing.py:46:    TaskType.TEST_AUTHORING,
src/ncdev/v2/routing.py:47:    TaskType.QA_SWEEP,
src/ncdev/v2/routing.py:48:    TaskType.DELIVERY_PACK,
tests/unit/test_claude_executor.py:52:            prohibited_patterns=["TODO"],
tests/unit/test_claude_executor.py:264:def test_prohibited_patterns_block_pass(tmp_path: Path):
tests/unit/test_claude_executor.py:277:    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
src/ncdev/v2/config.py:8:from ncdev.v2.models import TaskType
src/ncdev/v2/config.py:79:    def providers_for(self, task_type: TaskType) -> list[str]:
src/ncdev/v2/config.py:81:            TaskType.SOURCE_INGEST: self.source_ingest,
src/ncdev/v2/config.py:82:            TaskType.REPO_ANALYSIS: self.repo_analysis,
src/ncdev/v2/config.py:83:            TaskType.MARKET_RESEARCH: self.market_research,
src/ncdev/v2/config.py:84:            TaskType.FEATURE_EXTRACTION: self.feature_extraction,
src/ncdev/v2/config.py:85:            TaskType.DESIGN_BRIEF: self.design_brief,
src/ncdev/v2/config.py:86:            TaskType.BUILD_BATCH: self.implementation,
src/ncdev/v2/config.py:87:            TaskType.TEST_AUTHORING: self.test_authoring,
src/ncdev/v2/config.py:88:            TaskType.SENTINEL_REPRODUCE: self.sentinel_reproduce,
src/ncdev/v2/config.py:89:            TaskType.SENTINEL_FIX: self.sentinel_fix,
tests/unit/test_hooks.py:73:    cmd = f'git commit -m "{good}"'
tests/unit/test_hooks.py:86:    cmd = f'git commit -m "{bad}"'
tests/unit/test_hooks.py:114:        {"command": 'git commit -m "feat: initial"'},
tests/unit/test_hooks.py:128:        {"command": 'git commit -m "feat: add thing"'},
tests/unit/test_hooks.py:142:        {"command": 'git commit -m "feat: add run"'},
tests/unit/test_hooks.py:163:        {"command": 'git commit -m "feat: add new"'},
tests/unit/test_hooks.py:210:def test_custom_prohibited_patterns_via_env(tmp_path: Path, monkeypatch):
tests/unit/test_hooks.py:212:    config.write_text('{"prohibited_patterns": ["SECRET"]}')
tests/unit/test_hooks.py:221:        {"command": 'git commit -m "feat: add key"'},
src/ncdev/v2/models.py:30:class TaskType(str, Enum):
src/ncdev/v2/models.py:350:    task_type: TaskType
src/ncdev/v2/models.py:459:    task_type: TaskType
src/ncdev/v2/models.py:473:    task_type: TaskType
src/ncdev/v2/models.py:486:    task_type: TaskType
src/ncdev/v2/models.py:505:    task_type: TaskType
src/ncdev/v2/models.py:592:    task_type: TaskType

codex
One more pass on the control plane now: whether the advertised knobs actually drive V3, and whether failures propagate or just get logged and ignored. That’s where most of the “looks right on paper, drifts in production” problems usually sit.
exec
/bin/zsh -lc "nl -ba src/ncdev/v3/state_scanner.py | sed -n '1,260p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "nl -ba src/ncdev/cli.py | sed -n '1,320p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Project state scanner — determines which features are already implemented.
     2	
     3	Scans the target repo's git history, file tree, and test results to figure out
     4	what's already built, so the engine can skip completed work and resume from
     5	where the previous run left off.
     6	"""
     7	from __future__ import annotations
     8	
     9	import re
    10	import subprocess
    11	import sys
    12	from pathlib import Path
    13	
    14	from rich.console import Console
    15	
    16	from ncdev.v3.models import FeatureStep, StepResult, StepStatus
    17	
    18	console = Console()
    19	
    20	
    21	def scan_completed_features(
    22	    target_path: Path,
    23	    feature_queue: list[FeatureStep],
    24	) -> list[str]:
    25	    """Scan the target repo and return feature_ids that are already done.
    26	
    27	    A feature is considered done if:
    28	    1. It appears in a git commit message (feat(feature_id): ...), OR
    29	    2. Key files described by its title/description exist in the repo, AND
    30	    3. The project's tests pass (basic smoke check)
    31	    """
    32	    if not (target_path / ".git").exists():
    33	        return []
    34	
    35	    git_log = _get_git_log(target_path)
    36	    file_tree = _get_file_set(target_path)
    37	    tests_pass = _run_smoke_test(target_path)
    38	
    39	    completed: list[str] = []
    40	
    41	    for feature in feature_queue:
    42	        # Check 1: Is this feature in the git history?
    43	        in_git = _feature_in_git_history(feature, git_log)
    44	
    45	        # Check 2: Do files related to this feature exist?
    46	        has_files = _feature_has_files(feature, file_tree)
    47	
    48	        if tests_pass and (in_git or has_files):
    49	            completed.append(feature.feature_id)
    50	
    51	    return completed
    52	
    53	
    54	def build_skip_results(
    55	    feature_queue: list[FeatureStep],
    56	    completed_ids: set[str],
    57	) -> list[StepResult]:
    58	    """Create SKIPPED StepResults for already-completed features."""
    59	    return [
    60	        StepResult(
    61	            feature_id=f.feature_id,
    62	            status=StepStatus.PASSED,
    63	            error_message="Skipped — already implemented in target repo",
    64	        )
    65	        for f in feature_queue
    66	        if f.feature_id in completed_ids
    67	    ]
    68	
    69	
    70	def _get_git_log(target_path: Path) -> str:
    71	    """Get full git log with commit messages."""
    72	    try:
    73	        result = subprocess.run(
    74	            ["git", "log", "--oneline", "--all", "-200"],
    75	            cwd=str(target_path),
    76	            capture_output=True, text=True, timeout=10,
    77	        )
    78	        return result.stdout.lower() if result.returncode == 0 else ""
    79	    except Exception:
    80	        return ""
    81	
    82	
    83	def _get_file_set(target_path: Path) -> set[str]:
    84	    """Get set of all file paths in the repo (relative, lowercase)."""
    85	    try:
    86	        result = subprocess.run(
    87	            ["git", "ls-files"],
    88	            cwd=str(target_path),
    89	            capture_output=True, text=True, timeout=10,
    90	        )
    91	        if result.returncode == 0:
    92	            return {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
    93	    except Exception:
    94	        pass
    95	    return set()
    96	
    97	
    98	def _run_smoke_test(target_path: Path) -> bool:
    99	    """Quick check: do backend tests pass? (or at least not crash)"""
   100	    backend = target_path / "backend"
   101	    if not backend.exists():
   102	        # Maybe tests are at root level
   103	        backend = target_path
   104	
   105	    has_tests = any(backend.rglob("test_*.py")) or any(backend.rglob("*_test.py"))
   106	    if not has_tests:
   107	        return True
   108	
   109	    try:
   110	        result = subprocess.run(
   111	            [sys.executable, "-m", "pytest", "-q", "-x", "--no-header"],
   112	            cwd=str(backend),
   113	            capture_output=True, text=True, timeout=60,
   114	        )
   115	        # Accept green runs and partially green runs that still discovered passing tests.
   116	        if result.returncode == 0 or "passed" in result.stdout:
   117	            return True
   118	
   119	        combined_output = f"{result.stdout}\n{result.stderr}".lower()
   120	
   121	        # Brownfield repos often do not have pytest wired yet. That should not block
   122	        # feature detection entirely.
   123	        non_blocking_markers = [
   124	            "no tests ran",
   125	            "collected 0 items",
   126	            "unrecognized arguments: --timeout=30",
   127	            "module named pytest",
   128	        ]
   129	        return any(marker in combined_output for marker in non_blocking_markers)
   130	    except Exception:
   131	        return False
   132	
   133	
   134	def _feature_in_git_history(feature: FeatureStep, git_log: str) -> bool:
   135	    """Check if a feature appears in git commit messages."""
   136	    feature_id_lower = feature.feature_id.lower()
   137	    title_lower = feature.title.lower()
   138	
   139	    # Direct feature ID match: feat(sprint-0):, feat(feature-01):, [feature-01]
   140	    if feature_id_lower in git_log:
   141	        return True
   142	
   143	    # Title keywords match (at least 3 significant words from title in same commit line)
   144	    title_words = [w for w in re.split(r'\W+', title_lower) if len(w) > 3]
   145	    if len(title_words) >= 2:
   146	        for line in git_log.splitlines():
   147	            matches = sum(1 for w in title_words if w in line)
   148	            if matches >= min(3, len(title_words)):
   149	                return True
   150	
   151	    return False
   152	
   153	
   154	def _feature_has_files(feature: FeatureStep, file_tree: set[str]) -> bool:
   155	    """Check if files related to the feature exist in the repo.
   156	
   157	    For sprint-0 (scaffold): check for fundamental files.
   158	    For other features: check for feature-specific files using title keywords.
   159	    """
   160	    fid = feature.feature_id.lower()
   161	
   162	    # Sprint-0: scaffold is done if basic project structure exists
   163	    if "sprint-0" in fid or "scaffold" in feature.title.lower():
   164	        scaffold_markers = [
   165	            "backend/app/main.py",
   166	            "backend/requirements.txt",
   167	            "docker-compose.yml",
   168	        ]
   169	        found = sum(1 for m in scaffold_markers if m in file_tree)
   170	        return found >= 2
   171	
   172	    # For other features: extract keywords from title and check file tree
   173	    title_words = [w.lower() for w in re.split(r'\W+', feature.title) if len(w) > 3]
   174	    if not title_words:
   175	        return False
   176	
   177	    # Check if any file path contains feature keywords (prefix match for stems)
   178	    keyword_hits = 0
   179	    for word in title_words:
   180	        # Use first 4+ chars as stem to match "auth" in path against "authentication" in title
   181	        stem = word[:4] if len(word) > 4 else word
   182	        for fpath in file_tree:
   183	            if stem in fpath:
   184	                keyword_hits += 1
   185	                break
   186	
   187	    # Need at least 1 keyword match to consider the feature has files
   188	    return keyword_hits >= 1

 succeeded in 0ms:
     1	from __future__ import annotations
     2	
     3	import argparse
     4	import subprocess
     5	import shutil
     6	import sys
     7	from pathlib import Path
     8	
     9	from rich.console import Console
    10	
    11	from ncdev.preflight import run_preflight, require_citex
    12	from ncdev.v2.engine import (
    13	    load_v2_run_state,
    14	    run_v2_fix,
    15	    summarize_v2_status,
    16	)
    17	from ncdev.v3.engine import run_v3_full
    18	
    19	console = Console()
    20	
    21	
    22	def _workspace(path: str | None) -> Path:
    23	    return Path(path).resolve() if path else Path.cwd()
    24	
    25	
    26	def _resolve_target_repo(explicit_target_repo: str | None, workspace: Path) -> Path | None:
    27	    if explicit_target_repo:
    28	        return Path(explicit_target_repo).resolve()
    29	    if (workspace / ".git").exists():
    30	        return workspace
    31	    return None
    32	
    33	
    34	def _quickstart_text() -> str:
    35	    return """NC Dev System Quickstart
    36	
    37	Recommended flow:
    38	
    39	1. Dry-run discovery
    40	   ncdev full --source ./docs/README.md --dry-run
    41	
    42	2. Full build (sequential verified sprints)
    43	   ncdev full --source ./docs/README.md --base-url http://localhost:23000
    44	
    45	3. Full build with explicit target repo
    46	   ncdev full --source /path/to/docs --target-repo /path/to/repo --base-url http://localhost:23000
    47	
    48	4. Autonomous dev mode
    49	   ncdev dev --project /path/to/project --task "Build feature X"
    50	
    51	5. Generate video report
    52	   ncdev report --project /path/to/project
    53	
    54	Other commands:
    55	   ncdev fix --report report.json --target /path/to/repo
    56	   ncdev serve --port 16650
    57	   ncdev doctor
    58	"""
    59	
    60	
    61	def _check_app_boots(target_path: Path) -> bool:
    62	    """Check whether the backend app still imports cleanly after a fix."""
    63	    backend_path = target_path / "backend"
    64	    if not backend_path.exists():
    65	        return True
    66	
    67	    try:
    68	        result = subprocess.run(
    69	            [sys.executable, "-c", "from app.main import app; print('BOOT_OK')"],
    70	            cwd=str(backend_path),
    71	            capture_output=True,
    72	            text=True,
    73	            timeout=30,
    74	        )
    75	        return "BOOT_OK" in result.stdout
    76	    except Exception:
    77	        return False
    78	
    79	
    80	async def _run_quality_gate_fixes(manifest, config=None) -> int:
    81	    """Apply quality gate fixes using the AI provider adapter.
    82	
    83	    Uses the configured AI provider (default: Codex CLI) with automatic
    84	    fallback (default: Claude CLI). All AI CLI calls go through
    85	    :mod:`ncdev.ai_provider` -- no direct subprocess calls to ``claude``
    86	    or ``codex`` remain in this module.
    87	    """
    88	    from ncdev.ai_provider import get_provider_with_fallback
    89	    from ncdev.quality_gate.config import QualityGateConfig
    90	    from ncdev.quality_gate.models import FixManifest
    91	
    92	    if config is None:
    93	        config = QualityGateConfig()
    94	
    95	    manifest = FixManifest.model_validate(manifest)
    96	    target = Path(manifest.target_path).resolve()
    97	    fixed = 0
    98	
    99	    # Resolve the AI provider from config (primary + fallback)
   100	    provider = get_provider_with_fallback(config.ai_provider, config.ai_fallback)
   101	    console.print(
   102	        f"[dim]AI provider: {type(provider).__name__} "
   103	        f"(primary={config.ai_provider}, fallback={config.ai_fallback})[/dim]"
   104	    )
   105	
   106	    # Process all issues, not just P0/P1. Already sorted by priority.
   107	    all_issues = manifest.issues
   108	    timeout_by_priority = {"P0": 300, "P1": 300, "P2": 180, "P3": 120}
   109	    console.print(
   110	        f"[yellow]Fixing {len(all_issues)} issues "
   111	        f"(P0/P1: {sum(1 for i in all_issues if i.priority in ('P0', 'P1'))}, "
   112	        f"P2: {sum(1 for i in all_issues if i.priority == 'P2')}, "
   113	        f"P3: {sum(1 for i in all_issues if i.priority == 'P3')})[/yellow]"
   114	    )
   115	
   116	    if not all_issues:
   117	        return 0
   118	
   119	    # Group issues by URL for smarter fixing
   120	    from collections import defaultdict
   121	    url_groups: dict[str, list] = defaultdict(list)
   122	    for issue in all_issues:
   123	        url = issue.flow.split(" → ")[0] if " → " in issue.flow else "/"
   124	        url_groups[url].append(issue)
   125	
   126	    console.print(f"[cyan]Grouped into {len(url_groups)} URL groups[/cyan]")
   127	
   128	    # Query Citex for Test Craftr's findings (required for all fix flows)
   129	    require_citex()
   130	    from ncdev.v3.citex_client import CitexClient
   131	    project_id = Path(manifest.target_path).name
   132	    citex = CitexClient(project_id=project_id)
   133	
   134	    fix_tools = ["Edit", "Write", "Bash", "Read", "Glob", "Grep"]
   135	
   136	    for url, group_issues in url_groups.items():
   137	        if not group_issues:
   138	            continue
   139	
   140	        # Use the highest priority timeout for the group
   141	        timeout = min(
   142	            timeout_by_priority.get(i.priority, 120) for i in group_issues
   143	        )
   144	        # Give grouped fixes more time (multiple issues)
   145	        if len(group_issues) > 1:
   146	            timeout = min(timeout * 2, config.ai_fix_timeout)
   147	
   148	        console.print(
   149	            f"\n[cyan]Fixing {len(group_issues)} issue(s) at {url} "
   150	            f"(timeout {timeout}s)[/cyan]"
   151	        )
   152	        for gi in group_issues:
   153	            console.print(f"  [{gi.priority}] {gi.title}")
   154	
   155	        # Checkpoint before fix attempt -- snapshot working tree
   156	        snapshot = subprocess.run(
   157	            ["git", "stash", "create"],
   158	            cwd=str(target),
   159	            capture_output=True,
   160	            text=True,
   161	        )
   162	        stash_sha = snapshot.stdout.strip()
   163	
   164	        # Build a combined prompt for all issues at this URL
   165	        issues_description = "\n\n".join([
   166	            f"Issue {idx+1}: [{i.priority}] {i.title}\n"
   167	            f"  Category: {i.category}\n"
   168	            f"  Flow: {i.flow}\n"
   169	            f"  Expected: {i.expected}\n"
   170	            f"  Actual: {i.actual}\n"
   171	            f"  Hint: {i.root_cause_hint or 'None provided'}\n"
   172	            f"  Affected files: {', '.join(p for p in i.affected_files_hint if p) or 'unknown'}"
   173	            for idx, i in enumerate(group_issues)
   174	        ])
   175	
   176	        # Enrich with Citex context (if available)
   177	        citex_context = ""
   178	        if citex:
   179	            tc_findings = citex.query(f"Test findings for {url}", category="signals", limit=2)
   180	            code_context = citex.query(f"Component handling {url}", category="code", limit=2)
   181	            if tc_findings or code_context:
   182	                findings_text = chr(10).join(tc_findings) if tc_findings else "None available"
   183	                code_text = chr(10).join(code_context) if code_context else "None available"
   184	                citex_context = f"""
   185	
   186	## Additional Context from Citex RAG
   187	### Test Craftr Findings
   188	{findings_text}
   189	
   190	### Relevant Code Context
   191	{code_text}
   192	"""
   193	
   194	        prompt = f"""Fix these {len(group_issues)} related issues at {url}:
   195	
   196	{issues_description}
   197	
   198	These issues are at the same URL and likely share a common root cause.
   199	Analyze them together and make the minimal changes needed.
   200	
   201	Requirements:
   202	- Make the minimal change necessary to fix these issues.
   203	- Do not refactor unrelated code.
   204	- Run the most relevant tests for these issues.
   205	- Leave the repository with your code changes unstaged and uncommitted.
   206	- Print a short summary of what you changed and which tests you ran.
   207	{citex_context}"""
   208	
   209	        result = await provider.complete(
   210	            prompt=prompt,
   211	            timeout=timeout,
   212	            cwd=str(target),
   213	            tools=fix_tools,
   214	        )
   215	
   216	        if result is None:
   217	            console.print(f"    [red]AI provider returned no result -- reverting[/red]")
   218	            subprocess.run(["git", "checkout", "."], cwd=str(target), capture_output=True)
   219	            subprocess.run(["git", "clean", "-fd"], cwd=str(target), capture_output=True)
   220	            if stash_sha:
   221	                subprocess.run(["git", "stash", "apply", stash_sha], cwd=str(target), capture_output=True)
   222	            continue
   223	
   224	        if not _check_app_boots(target):
   225	            console.print("    [red]Fix broke app -- reverting[/red]")
   226	            subprocess.run(["git", "checkout", "."], cwd=str(target), capture_output=True)
   227	            subprocess.run(["git", "clean", "-fd"], cwd=str(target), capture_output=True)
   228	            if stash_sha:
   229	                subprocess.run(["git", "stash", "apply", stash_sha], cwd=str(target), capture_output=True)
   230	            continue
   231	
   232	        # Success -- commit the fix for this URL group
   233	        issue_ids = ", ".join(i.id for i in group_issues)
   234	        commit_msg = (
   235	            f"fix: {len(group_issues)} issues at {url} [{issue_ids}]"
   236	            if len(group_issues) > 1
   237	            else f"fix: {group_issues[0].title} [{group_issues[0].id}]"
   238	        )
   239	        subprocess.run(["git", "add", "-A"], cwd=str(target), capture_output=True)
   240	        commit_result = subprocess.run(
   241	            ["git", "commit", "-m", commit_msg],
   242	            cwd=str(target),
   243	            capture_output=True,
   244	        )
   245	        if commit_result.returncode == 0:
   246	            fixed += len(group_issues)
   247	            console.print(f"    [green]Fixed and committed {len(group_issues)} issue(s)[/green]")
   248	        else:
   249	            console.print("    [yellow]Fix applied but commit failed[/yellow]")
   250	
   251	    tone = "green" if fixed == len(all_issues) else "yellow"
   252	    console.print(
   253	        f"[{tone}]Fixed {fixed}/{len(all_issues)} issues[/{tone}]"
   254	    )
   255	    return fixed
   256	
   257	
   258	def _doctor_report(workspace: Path) -> tuple[bool, str]:
   259	    required = ["git", "python3", "pytest", "claude", "codex", "node", "npm", "npx"]
   260	    core = run_preflight(required)
   261	    docker_path = shutil.which("docker")
   262	
   263	    lines = ["NC Dev System Doctor", "", f"Workspace: {workspace}"]
   264	    if (workspace / ".git").exists():
   265	        lines.append("Target repo inference: current folder is a git repository")
   266	    else:
   267	        lines.append("Target repo inference: current folder is not a git repository")
   268	    lines.append("")
   269	    lines.append("Core requirements:")
   270	    for cmd in required:
   271	        status = "ok" if cmd not in core.missing else "missing"
   272	        lines.append(f"- {cmd}: {status}")
   273	    lines.append("")
   274	    from ncdev.preflight import check_citex
   275	    citex_ok = check_citex()
   276	    lines.append("Optional:")
   277	    lines.append(f"- docker: {'ok' if docker_path else 'missing'}")
   278	    lines.append(f"- citex (localhost:20161): {'ok' if citex_ok else 'not running'}")
   279	    lines.append("")
   280	    if core.ok:
   281	        lines.append("Result: ready")
   282	        lines.append("Next step: run `ncdev quickstart` or `ncdev full --source <entry-doc> --dry-run`")
   283	    else:
   284	        lines.append(f"Result: missing core tools: {', '.join(core.missing)}")
   285	        lines.append("Fix the missing tools above before running a full build.")
   286	    return core.ok, "\n".join(lines)
   287	
   288	
   289	def build_parser() -> argparse.ArgumentParser:
   290	    parser = argparse.ArgumentParser(prog="ncdev", description="NC Dev System — autonomous builder")
   291	    sub = parser.add_subparsers(dest="command", required=True)
   292	
   293	    sub.add_parser("quickstart", help="Print the recommended workflow")
   294	    sub.add_parser("doctor", help="Check prerequisites")
   295	
   296	    # --- Full: Sequential Verified Sprint Engine ---
   297	    full = sub.add_parser("full", help="Run the full sequential verified sprint pipeline")
   298	    full.add_argument("--source", required=True, help="Path to source requirements or spec")
   299	    full.add_argument("--target-repo", default=None, help="Existing target repository")
   300	    full.add_argument("--workspace", default=None)
   301	    full.add_argument("--base-url", default="http://localhost:23000")
   302	    full.add_argument("--dry-run", action="store_true", help="Do not invoke builders")
   303	    full.add_argument("--model", default="claude-opus-4-6",
   304	                      help="Claude model for the orchestrator session (e.g. claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001)")
   305	    full.add_argument("--max-budget-usd", type=float, default=None,
   306	                      help="Cost ceiling per feature session (Claude only — ignored by Codex shell-outs)")
   307	    full.add_argument("--timeout", type=int, default=600, help="Builder timeout per feature (seconds)")
   308	    full.add_argument("--max-repairs", type=int, default=2, help="Max repair attempts per feature")
   309	    full.add_argument("--quality-gate", action="store_true", default=False, help="Run quality gate loop after build completes")
   310	
   311	    # --- Dev Mode: The Autonomous Senior Engineer ---
   312	    dev_parser = sub.add_parser("dev", help="Autonomous development — Claude + Codex + Citex + Playwright")
   313	    dev_parser.add_argument("--project", required=True, help="Path to the project directory")
   314	    dev_parser.add_argument("--task", required=True, help="What to build, fix, or enhance")
   315	    dev_parser.add_argument("--mode", default="auto", choices=["auto", "greenfield", "enhance", "bugfix"], help="Development mode")
   316	
   317	    # --- Report: generate video report for an already-built project ---
   318	    report_parser = sub.add_parser("report", help="Generate video report for a completed project")
   319	    report_parser.add_argument("--project", required=True, help="Path to the project directory")
   320	    report_parser.add_argument("--task", default="", help="Description of what was built (for narration)")

exec
/bin/zsh -lc "rg -n \"load_v2_config|ensure_default_v2_config|mode=|builder_model|run_v3_full\\(|run_dev\\(|claude_plan_codex_build|codex_only|claude_only|openrouter|custom\" src -S" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
src/ncdev/provider_dispatch.py:5:``codex``, ``openrouter``). Callers ask for a provider by task key — the
src/ncdev/provider_dispatch.py:17:from ncdev.v2.config import NCDevV2Config, load_v2_config
src/ncdev/provider_dispatch.py:25:    "openrouter": "openrouter",
src/ncdev/provider_dispatch.py:50:    cfg = load_v2_config(root)
src/ncdev/dev.py:211:def run_dev(
src/ncdev/dev.py:254:        permission_mode="acceptEdits",
src/ncdev/v3/engine.py:22:The old run_v3_full() interface is preserved so the ``ncdev full`` CLI
src/ncdev/v3/engine.py:50:def run_v3_full(
src/ncdev/v3/engine.py:57:    builder_model: str = "claude-opus-4-6",
src/ncdev/v3/engine.py:100:            model=builder_model,
src/ncdev/v3/engine.py:137:            model=builder_model,
src/ncdev/v3/engine.py:213:                model=builder_model,
src/ncdev/v3/context_ingestion.py:228:    Codex, or OpenRouter) is resolved from ``source_ingest`` routing.
src/ncdev/v3/metrics.py:42:    builder_model: str = "gpt-5.4"
src/ncdev/v3/claude_executor.py:211:        permission_mode="acceptEdits",
src/ncdev/cli.py:361:        state = run_v3_full(
src/ncdev/cli.py:367:            builder_model=args.model,
src/ncdev/cli.py:407:        result = run_dev(
src/ncdev/cli.py:410:            mode=args.mode,
src/ncdev/ai_provider.py:78:        (logging, custom timeouts, Popen session groups, etc.) can use
src/ncdev/ai_provider.py:80:        (e.g. OpenRouter) raise :class:`NotImplementedError`.
src/ncdev/ai_provider.py:160:                mode="w", suffix=".txt", delete=False, encoding="utf-8",
src/ncdev/ai_provider.py:345:class OpenRouterProvider(AIProvider):
src/ncdev/ai_provider.py:346:    """API-based provider that routes to models via OpenRouter (openrouter.ai).
src/ncdev/ai_provider.py:348:    Requires ``OPENROUTER_API_KEY`` in the environment. The model is taken from
src/ncdev/ai_provider.py:349:    ``OPENROUTER_MODEL`` (default ``anthropic/claude-opus-4-6``). This provider
src/ncdev/ai_provider.py:354:    _cmd_name = "openrouter"
src/ncdev/ai_provider.py:355:    _BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
src/ncdev/ai_provider.py:358:        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
src/ncdev/ai_provider.py:359:        self._model = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-opus-4-6")
src/ncdev/ai_provider.py:363:        return "openrouter"
src/ncdev/ai_provider.py:376:            logger.error("OPENROUTER_API_KEY is not set; OpenRouter provider is unavailable")
src/ncdev/ai_provider.py:381:            logger.error("httpx is not installed; OpenRouter provider requires httpx")
src/ncdev/ai_provider.py:400:            logger.exception("OpenRouter request failed: %s", exc)
src/ncdev/ai_provider.py:411:    "openrouter": OpenRouterProvider,
src/ncdev/artifacts/state.py:77:    write_json(path, state.model_dump(mode="json"))
src/ncdev/v2/engine.py:120:        report.model_dump(mode="json"),
src/ncdev/v2/__init__.py:1:from ncdev.v2.config import NCDevV2Config, ensure_default_v2_config, load_v2_config
src/ncdev/v2/__init__.py:3:__all__ = ["NCDevV2Config", "ensure_default_v2_config", "load_v2_config"]
src/ncdev/v2/config.py:34:# Named presets. Flipping `NCDevV2Config.mode` picks one. "custom" leaves
src/ncdev/v2/config.py:37:    "codex_only": _uniform_preset("openai_codex"),
src/ncdev/v2/config.py:38:    "claude_only": _uniform_preset("anthropic_claude_code"),
src/ncdev/v2/config.py:39:    "openrouter": _uniform_preset("openrouter"),
src/ncdev/v2/config.py:40:    "claude_plan_codex_build": {
src/ncdev/v2/config.py:53:    "custom": {},
src/ncdev/v2/config.py:56:DEFAULT_MODE = "claude_plan_codex_build"
src/ncdev/v2/config.py:153:            "claude_plan_codex_build (default) uses Claude for planning + "
src/ncdev/v2/config.py:155:            "codex_only skips Claude entirely for token-lean days; "
src/ncdev/v2/config.py:156:            "claude_only keeps everything on Claude; openrouter routes all "
src/ncdev/v2/config.py:157:            "tasks through the OpenRouter API. Use 'custom' to hand-tune."
src/ncdev/v2/config.py:172:            "openrouter": ProviderPreferenceConfig(
src/ncdev/v2/config.py:175:                defaults={"base_url": "https://openrouter.ai/api/v1"},
src/ncdev/v2/config.py:184:    @model_validator(mode="after")
src/ncdev/v2/config.py:193:            # "custom" — leave RoutingConfig as declared.
src/ncdev/v2/config.py:200:        return self.model_dump(mode="python")
src/ncdev/v2/config.py:203:def load_v2_config(workspace: Path) -> NCDevV2Config:
src/ncdev/v2/config.py:211:def ensure_default_v2_config(workspace: Path) -> NCDevV2Config:
src/ncdev/v2/config.py:213:    config = load_v2_config(workspace)

codex
## Architecture verdict
The migration is directionally right: deleting the old prompt/router ladder and treating Claude Code as the actual orchestrator is the correct simplification. The problem is that the new control plane still assumes happy-path agent behavior in places where it needs to be adversarial, so several of the guarantees in the README are weaker than advertised.

## Strengths
- Centralizing all Claude spawning in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:112) is the right primitive. The rest of V3 now depends on one process boundary instead of several ad hoc ones.
- The feature prompt in [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:57) is much healthier than the old mega-prompts: it points Claude at on-disk artifacts instead of inlining huge policy blobs.
- The hard-fail principle for greenfield UI is explicit in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:230). That is the right default if the product requirement is “no generic AI styling.”
- The asset-manifest requirement is conceptually good. Having Claude write intent while building in [asset_manifest.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:88) is better than reconstructing intent after the fact.
- The hook logic being factored into a pure `evaluate()` function in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:130) is a good testing seam.

## Critical issues
- The session timeout is not real, and stderr can deadlock the process. [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:258) blocks on `for line in proc.stdout`, so if Claude hangs without closing stdout you never reach `wait(timeout=...)`. At the same time, stderr is piped but not drained until after stdout EOF at [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:296), so a noisy stderr stream can block the child. Suggested fix: nonblocking/select-based reads or a threaded reader for both pipes, with a wall-clock timeout enforced outside the stdout iterator.
- The charter prompt contradicts the architecture and will reject valid greenfield+Stitch runs. In [charter.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/charter.py:104) the instruction is effectively “greenfield UI must write `charter-error.json` unless designs already exist on disk,” but your actual design decision point lives in Phase C. Phase B cannot know whether Stitch is configured, so this prompt can hard-fail perfectly valid runs before design phase starts.
- Design phase failures can silently pass. In [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:245), [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:261), and [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:298), you return success-path results without requiring `session.success` or a valid `design-system.json`. Then [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:155) happily continues with `source=?`. That will turn design failures into downstream build weirdness instead of a clean stop.
- The verification contract is mostly unenforced. [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:195) defines boot URLs, test commands, screenshot requirements, and minimum test count, but [_post_session_verification](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:287) only checks required files, asset manifests, and prohibited patterns. A feature can “pass” without NC Dev ever verifying tests, app boot, screenshots, or test count.
- Failed dependencies do not block downstream features. The engine just keeps iterating in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:197), and the executor only passes prior `PASSED` ids into prompts at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:189). There is no enforcement that `depends_on_features` must already be green. That will compound failures and produce misleading later results.
- The advertised mode switch is not actually driving V3. `MODE_PRESETS` lives in [v2/config.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v2/config.py:36), but `run_v3_full()` hardcodes Claude in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:57) and `run_dev()` hardcodes Claude in [dev.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/dev.py:216). The CLI `dev --mode` in [cli.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/cli.py:315) is a workflow hint, not the budget/provider mode you describe. That is a user-facing contract bug.
- MCP availability is inferred from one settings source and execution uses another. `stitch_available()` probes user config in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:72), but `run_claude_session()` unconditionally injects `--settings scripts/ncdev-hooks/settings.json` in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:208). If Claude treats `--settings` as replacement rather than merge, you can “detect” Stitch and then spawn a session without Stitch.
- Asset-manifest verification is global, not feature-local. [verify_manifest_covers_references](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:196) scans the whole repo every feature. One legacy missing asset in brownfield code will fail every future feature, even if that feature never touched assets.

## Concerning but not critical
- `_extract_event_signals()` in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:352) only understands one stream shape: `assistant.message.content[].tool_use`. That is brittle for metrics and Codex-call detection across Claude Code versions.
- `_commit_broken()` in [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:409) does not check `git add` or `git commit` return codes. Your PreToolUse hook does not intercept this Python-side subprocess anyway, so if git identity or a real repo hook rejects the commit, recoverability silently disappears.
- `_extract_commit_message()` in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:108) misparses escaped quotes and intentionally gives up on `-F`/heredoc forms, so commit-message enforcement is easy to bypass.
- Prohibited-pattern semantics are inconsistent. `VerificationContract` includes regex-like `r"except:\s*pass"` in [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:217), but both the hook and post-hoc verifier do substring checks in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:100) and [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:348), so that rule never actually matches.
- There are a couple of plain bugs in design handling: `_stitch_prompt()` points Claude at `outputs/../feature-queue.json` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:133), which is the wrong file, and `existing_design_system_present()` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:96) treats any non-empty file under `docs/design-system` as a valid system.

## Over-engineered / could be deleted
- Keeping full raw `events` in memory while also writing JSONL in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:222) is expensive and probably unnecessary outside debug mode.
- The retained V2 mode/routing stack is now mostly ceremonial for V3. If V3 is the product, either wire it in for real or stop advertising it as the control plane.
- `max_repair_attempts` is dead compatibility ballast in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:59).
- `DESIGN_TOOLS` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:45) is too broad for the brownfield summarizer path; giving it `Edit`, `Bash`, and `Task` undermines the “read and summarise only” contract.

## Missing
- A real `ncdev resume <run_id>` path. You already persist state in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:286); not having a reentry path is the obvious next gap.
- Run-level cost aggregation. You store per-session cost in `signals.json`, but the engine never rolls it up into state or summary.
- A first-class “needs clarification / refused / non-actionable” outcome. Right now success is inferred from git side effects, not from whether Claude actually completed the request.
- Actual dependency policy for failed features: stop, skip dependents, or continue only behind an explicit flag.

## Test coverage gaps
- I could not reproduce the claimed suite run here: `python -m pytest -q` fails because `python` is Python 2.7 with no `pytest`, and `python3 -m pytest -q` also fails because `pytest` is not installed for `python3`. So I did static review of the tests, not an executed green run.
- The core process tests are heavily mocked. `_FakeProc` in [test_claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/unit/test_claude_session.py:33) cannot expose the real deadlock cases: blocked stdout iteration, stderr backpressure, pipe closure, or partial-line behavior.
- There is no test for the most dangerous design-phase bug: successful session with missing/invalid `design-system.json` still letting the engine continue.
- There is no test that a failed feature blocks a dependent feature.
- There is no test that the V3 engine actually honors the advertised provider mode switch, because right now it does not.

## Honest one-liner
I’d inherit this codebase after a hardening pass, not today: the simplification is right, but the guarantees around timeout, verification, dependency gating, and MCP/design availability are still softer than the docs claim.
tokens used
161,225
## Architecture verdict
The migration is directionally right: deleting the old prompt/router ladder and treating Claude Code as the actual orchestrator is the correct simplification. The problem is that the new control plane still assumes happy-path agent behavior in places where it needs to be adversarial, so several of the guarantees in the README are weaker than advertised.

## Strengths
- Centralizing all Claude spawning in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:112) is the right primitive. The rest of V3 now depends on one process boundary instead of several ad hoc ones.
- The feature prompt in [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:57) is much healthier than the old mega-prompts: it points Claude at on-disk artifacts instead of inlining huge policy blobs.
- The hard-fail principle for greenfield UI is explicit in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:230). That is the right default if the product requirement is “no generic AI styling.”
- The asset-manifest requirement is conceptually good. Having Claude write intent while building in [asset_manifest.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:88) is better than reconstructing intent after the fact.
- The hook logic being factored into a pure `evaluate()` function in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:130) is a good testing seam.

## Critical issues
- The session timeout is not real, and stderr can deadlock the process. [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:258) blocks on `for line in proc.stdout`, so if Claude hangs without closing stdout you never reach `wait(timeout=...)`. At the same time, stderr is piped but not drained until after stdout EOF at [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:296), so a noisy stderr stream can block the child. Suggested fix: nonblocking/select-based reads or a threaded reader for both pipes, with a wall-clock timeout enforced outside the stdout iterator.
- The charter prompt contradicts the architecture and will reject valid greenfield+Stitch runs. In [charter.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/charter.py:104) the instruction is effectively “greenfield UI must write `charter-error.json` unless designs already exist on disk,” but your actual design decision point lives in Phase C. Phase B cannot know whether Stitch is configured, so this prompt can hard-fail perfectly valid runs before design phase starts.
- Design phase failures can silently pass. In [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:245), [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:261), and [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:298), you return success-path results without requiring `session.success` or a valid `design-system.json`. Then [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:155) happily continues with `source=?`. That will turn design failures into downstream build weirdness instead of a clean stop.
- The verification contract is mostly unenforced. [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:195) defines boot URLs, test commands, screenshot requirements, and minimum test count, but [_post_session_verification](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:287) only checks required files, asset manifests, and prohibited patterns. A feature can “pass” without NC Dev ever verifying tests, app boot, screenshots, or test count.
- Failed dependencies do not block downstream features. The engine just keeps iterating in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:197), and the executor only passes prior `PASSED` ids into prompts at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:189). There is no enforcement that `depends_on_features` must already be green. That will compound failures and produce misleading later results.
- The advertised mode switch is not actually driving V3. `MODE_PRESETS` lives in [v2/config.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v2/config.py:36), but `run_v3_full()` hardcodes Claude in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:57) and `run_dev()` hardcodes Claude in [dev.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/dev.py:216). The CLI `dev --mode` in [cli.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/cli.py:315) is a workflow hint, not the budget/provider mode you describe. That is a user-facing contract bug.
- MCP availability is inferred from one settings source and execution uses another. `stitch_available()` probes user config in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:72), but `run_claude_session()` unconditionally injects `--settings scripts/ncdev-hooks/settings.json` in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:208). If Claude treats `--settings` as replacement rather than merge, you can “detect” Stitch and then spawn a session without Stitch.
- Asset-manifest verification is global, not feature-local. [verify_manifest_covers_references](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:196) scans the whole repo every feature. One legacy missing asset in brownfield code will fail every future feature, even if that feature never touched assets.

## Concerning but not critical
- `_extract_event_signals()` in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:352) only understands one stream shape: `assistant.message.content[].tool_use`. That is brittle for metrics and Codex-call detection across Claude Code versions.
- `_commit_broken()` in [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:409) does not check `git add` or `git commit` return codes. Your PreToolUse hook does not intercept this Python-side subprocess anyway, so if git identity or a real repo hook rejects the commit, recoverability silently disappears.
- `_extract_commit_message()` in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:108) misparses escaped quotes and intentionally gives up on `-F`/heredoc forms, so commit-message enforcement is easy to bypass.
- Prohibited-pattern semantics are inconsistent. `VerificationContract` includes regex-like `r"except:\s*pass"` in [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:217), but both the hook and post-hoc verifier do substring checks in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:100) and [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:348), so that rule never actually matches.
- There are a couple of plain bugs in design handling: `_stitch_prompt()` points Claude at `outputs/../feature-queue.json` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:133), which is the wrong file, and `existing_design_system_present()` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:96) treats any non-empty file under `docs/design-system` as a valid system.

## Over-engineered / could be deleted
- Keeping full raw `events` in memory while also writing JSONL in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:222) is expensive and probably unnecessary outside debug mode.
- The retained V2 mode/routing stack is now mostly ceremonial for V3. If V3 is the product, either wire it in for real or stop advertising it as the control plane.
- `max_repair_attempts` is dead compatibility ballast in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:59).
- `DESIGN_TOOLS` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:45) is too broad for the brownfield summarizer path; giving it `Edit`, `Bash`, and `Task` undermines the “read and summarise only” contract.

## Missing
- A real `ncdev resume <run_id>` path. You already persist state in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:286); not having a reentry path is the obvious next gap.
- Run-level cost aggregation. You store per-session cost in `signals.json`, but the engine never rolls it up into state or summary.
- A first-class “needs clarification / refused / non-actionable” outcome. Right now success is inferred from git side effects, not from whether Claude actually completed the request.
- Actual dependency policy for failed features: stop, skip dependents, or continue only behind an explicit flag.

## Test coverage gaps
- I could not reproduce the claimed suite run here: `python -m pytest -q` fails because `python` is Python 2.7 with no `pytest`, and `python3 -m pytest -q` also fails because `pytest` is not installed for `python3`. So I did static review of the tests, not an executed green run.
- The core process tests are heavily mocked. `_FakeProc` in [test_claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/unit/test_claude_session.py:33) cannot expose the real deadlock cases: blocked stdout iteration, stderr backpressure, pipe closure, or partial-line behavior.
- There is no test for the most dangerous design-phase bug: successful session with missing/invalid `design-system.json` still letting the engine continue.
- There is no test that a failed feature blocks a dependent feature.
- There is no test that the V3 engine actually honors the advertised provider mode switch, because right now it does not.

## Honest one-liner
I’d inherit this codebase after a hardening pass, not today: the simplification is right, but the guarantees around timeout, verification, dependency gating, and MCP/design availability are still softer than the docs claim.
