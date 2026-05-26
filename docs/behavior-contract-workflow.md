# Behavior Contract Workflow

NC Dev now emits a shared behavior contract that TestCraftr can verify without
requiring the full TestCraftr server stack.

## Generate A Contract

```bash
ncdev spec --source ./PRD.md --target-repo /path/to/app
```

This runs only the charter/spec phase and writes:

```text
.nc-dev/runs/<spec-run>/outputs/behavior-contract.v1.json
.nc-dev/runs/<spec-run>/outputs/behavior-contract.md
```

The JSON file is the machine contract. The Markdown file is for human review.

## What The Contract Contains

- project name and target URLs
- explicit assumptions
- one scenario per feature slice
- Given/When/Then behavior text
- required routes, files, tests, and screenshots
- required verification commands
- performance budgets and prohibited patterns

The contract is intentionally derived from the existing charter artifacts so
it does not create a second planning source of truth.

## TestCraftr Verification

Run TestCraftr in local file mode:

```bash
cd /Users/nrupal/dev/yensi/dev/test-craftr/tc-core
python -m tc_core.cli run \
  --contract /path/to/behavior-contract.v1.json \
  --url http://localhost:3000 \
  --project-path /path/to/app \
  --browser-smoke \
  --out .testcraftr/runs/local-001
```

This writes:

```text
.testcraftr/runs/local-001/verification-report.v1.json
.testcraftr/runs/local-001/issues.md
```

The local runner currently executes deterministic route, file, and test
obligations. With `--browser-smoke`, it also opens required routes in Playwright
and fails on console errors, failed network requests, or blank render output.
Browser personas, visual inspection, and adversarial flows remain in the server
path until they are moved behind the same file-mode runner.

## Fail-Closed Factory Runs

Use this when TestCraftr verification is mandatory:

```bash
ncdev factory \
  --source ./PRD.md \
  --target-repo /path/to/app \
  --probe-test-craftr \
  --test-craftr-mode local \
  --browser-smoke-contract \
  --require-test-craftr
```

In CLI runs, `--test-craftr-mode local` is the default. NC Dev finds the local
runner through `--test-craftr-core-path`, `TEST_CRAFTR_CORE_PATH`, or a sibling
`test-craftr/tc-core` checkout.

`ncdev full --quality-gate` enables local browser smoke verification by default
because that command is explicitly asking for an end-to-end gate.

With `--require-test-craftr`, the factory stops before Product Steward review if
TestCraftr cannot produce a run or reports a local infrastructure failure. This
prevents the build loop from silently continuing after missing verification.
