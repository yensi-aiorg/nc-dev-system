# Factory Spend And Loop Caps

Phase 4 makes unattended `ncdev factory` runs bounded by policy, not only by
individual Claude/Codex session timeouts.

## Overnight-Safe Command

```bash
ncdev factory \
  --source ./PRD.md \
  --target-repo /path/to/app \
  --max-cycles 5 \
  --max-wall-time-minutes 480 \
  --max-consecutive-failures 3 \
  --max-budget-usd 25 \
  --allow-unmetered \
  --probe-test-craftr \
  --require-test-craftr \
  --test-craftr-mode local \
  --browser-smoke-contract \
  --interaction-smoke-contract \
  --run-required-commands-contract \
  --persona-pass-contract \
  --strict-contract
```

Use `--allow-unmetered` deliberately. NC Dev can pass `--max-budget-usd` into
Claude sessions, but delegated Codex or shell paths do not yet provide reliable
cost telemetry back to the factory. When a dollar cap is set and the selected
mode can use unmetered delegated work, the factory stops before running agents
unless unmetered work is explicitly allowed:

```text
unmetered_spend_blocked
```

This is the intended fail-closed behavior for unattended work.

## Stop Reasons

- `wall_time_exhausted`: the factory-level wall-clock cap was reached.
- `too_many_failures`: the Steward returned too many consecutive non-continue
  cycles, such as repair, insert, rewrite, or rerun-charter.
- `budget_exhausted`: recorded metered spend reached the configured dollar cap,
  or the legacy max-cycle loop was exhausted.
- `unmetered_spend_blocked`: a budgeted run would use an agent path whose cost
  cannot be measured without `--allow-unmetered`.

The per-feature `--timeout` still applies to builder sessions. These caps apply
to the whole factory loop.

## Spend Ledger

Every factory run directory now gets:

```text
.nc-dev/runs/<run-id>/spend-ledger.jsonl
.nc-dev/runs/<run-id>/factory-summary.json
.nc-dev/runs/<run-id>/factory-summary.md
```

The ledger records pipeline, TestCraftr, Steward, and guardrail events. Each row
marks whether the event was metered and includes any available `cost_usd`,
`budget_usd`, status, cycle number, and supporting details.

Local TestCraftr verification is recorded as metered zero-cost work. Agent paths
without reliable cost telemetry are recorded as `metered=false` so an audit can
distinguish "free deterministic local check" from "unknown spend".

## Morning Status Check

After an unattended run, inspect the latest factory run with:

```bash
ncdev factory-status
```

Or inspect a specific run:

```bash
ncdev factory-status --run-dir .nc-dev/runs/<run-id>
ncdev factory-status --run-dir .nc-dev/runs/<run-id> --json
```

The status view reports the stop reason, diagnosis, cycle count, metered spend,
unmetered event count, latest Steward decisions, verification reports, and a
resume command when resuming is appropriate.

For recovery, prefer resuming against the existing charter rather than
regenerating a new one:

```bash
ncdev factory \
  --source ./PRD.md \
  --target-repo /path/to/app \
  --resume-charter .nc-dev/runs/<run-id>
```
