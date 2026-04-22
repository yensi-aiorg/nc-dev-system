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
