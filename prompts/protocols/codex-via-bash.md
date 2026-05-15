# Codex Protocol — How to delegate implementation to Codex via Bash

You (Claude) are the orchestrator. Codex is your implementation peer — faster
and cheaper than you at writing code, but weaker at judgment. Use Codex for
raw implementation and test writing. Do the planning, review, and debugging
yourself.

## When to use Codex

- Writing new implementation code (backend routes, frontend components, migrations)
- Writing tests for specified behavior (given a contract, produce the test file)
- Mechanical refactors (rename, move file, split function) across many files
- Scaffolding boilerplate (Dockerfile, config files, package.json)

## When NOT to use Codex

- Anything requiring judgment about architecture or tradeoffs
- Reviewing code (do this yourself)
- Debugging failing tests — use the `systematic-debugging` skill yourself
- Deciding what to build — that's planning, yours
- Anything where you would want to ask a clarifying question first

## How to invoke Codex

Use the `Bash` tool. The canonical invocation:

```bash
codex exec --full-auto --sandbox danger-full-access "<prompt>"
```

`--full-auto` grants all tool permissions. `--sandbox danger-full-access`
lets Codex edit files in the repo. Prompt is the whole task as a single
string argument — no flags after it.

For longer prompts, write the prompt to a temp file and pipe:

```bash
cat .ncdev/tmp/codex-prompt.md | codex exec --full-auto --sandbox danger-full-access -
```

## Prompt shape for Codex (a useful default)

Codex performs best with concrete, scoped tasks. The shape below is
a default that works — feel free to deviate if your task has a better
fit. The *content* matters: a one-line task statement, enough context
to disambiguate, a verification command that returns 0 on success.

```
# Task
<one-line description>

# Context
<2-3 lines on the surrounding code / feature / current state>

# Requirements
- <bullet 1>
- <bullet 2>

# Files
- Read: <path1>, <path2>
- Create: <path3>
- Modify: <path4>

# Verification
<exact command(s) that must pass when you're done>
```

If your task doesn't fit this shape (e.g. a one-shot mechanical
refactor, a code-review hand-off), use whatever shape best
communicates the goal. The orchestrator does not parse the prompt.

## Handling Codex output

Codex returns its work summary on stdout. Exit code 0 means it finished,
not that it succeeded — always run the verification command yourself
afterward.

- Exit code 0 + verification passes → accept the work, move on
- Exit code 0 + verification fails → review Codex's output, identify the
  specific failure, send Codex a **scoped** repair prompt (include the
  exact error). Do not re-prompt with the original task.
- Exit code != 0 → read stderr, decide whether to retry with a clearer
  prompt or take over the work yourself

Never let Codex loop more than 2× on the same task. If two tries don't
land it, you do the work yourself — Codex is stuck on something it
doesn't see.

## Cost discipline

You pay Claude tokens to orchestrate. Codex calls cost money too, but
different money. Rules:

- Do not invoke Codex for tasks under ~30 lines of code — faster to do
  it yourself
- Do not invoke Codex for UI tweaks the user can see in a screenshot —
  faster to do it yourself
- Do batch related work into one Codex call rather than three sequential
  calls (one call to write a model + its schema + its route is cheaper
  than three calls)

## What Codex cannot do

- Cannot invoke skills or other subagents (it has its own narrower tool set)
- Cannot read NC Dev's Citex context directly — pass relevant findings
  in the prompt
- Cannot reason about cross-feature coherence — that's your job

## Example

Good:

```bash
codex exec --full-auto --sandbox danger-full-access "# Task
Implement POST /api/v1/users/invite endpoint

# Context
Existing auth lives in backend/app/core/security.py. User model at
backend/app/models/user.py. Invite emails are stubbed via the
mock transport in backend/app/mocks/email.py.

# Requirements
- Accepts {email, role} JSON body
- Validates email format, role in {admin, member}
- Creates pending User row with status='invited'
- Calls email.send_invite(user)
- Returns 201 + {user_id}
- Rejects duplicate emails with 409

# Files
- Read: backend/app/models/user.py, backend/app/core/security.py
- Create: backend/app/api/v1/endpoints/invites.py
- Modify: backend/app/api/v1/router.py (register the route)

# Verification
cd backend && python -m pytest tests/integration/test_invites.py -q
"
```

Bad (too vague, Codex will wander):

```bash
codex exec --full-auto --sandbox danger-full-access "Add user invites"
```
