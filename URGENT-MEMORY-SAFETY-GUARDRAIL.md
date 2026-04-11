# URGENT: Memory Safety Guardrail — NON-NEGOTIABLE

**Status:** CRITICAL — BLOCKING ALL BUILDS UNTIL IMPLEMENTED
**Date:** 2026-04-11
**Triggered by:** Repeated kernel panics on host machine (Apr 10-11) during Vantage build
**Root cause:** NC Dev System spawned 4 python3.12 processes that consumed 381 GB on a 64 GB machine

---

## What Happened

NC Dev System was building Vantage. During Phase 3 (BUILD), the pipeline spawned 3 parallel Claude CLI builder processes. During Phase 4 (VERIFY), these builders — or the verification suite itself — ran Vantage's Playwright-based scraper tests. Vantage's `BrowserPool` has severe memory leaks (new Chromium per fetch, no cleanup on error, unbounded cascading jobs). With 3 parallel builders each triggering E2E tests that spawn Chromium processes, memory consumption spiralled to 381 GB. The kernel panicked. The machine rebooted. Three times on Apr 10, once on Apr 11.

**NC Dev System is not the only problem — Vantage's scraper code has its own leaks (see `/Users/nrupal/dev/yensi/dev/vantage/URGENT-MEMORY-LEAK-FIX.md`). But NC Dev System amplified the damage by running leaky code in parallel with zero memory awareness. That stops now.**

---

## The 6th Guardrail: Memory Safety

NC Dev System has 5 non-negotiable guardrails. This is the 6th:

> **NC Dev System MUST pre-evaluate every target project for memory safety before running ANY tests, E2E suites, or verification passes. It MUST NOT run resource-intensive operations in parallel across builders. It MUST monitor and cap memory during all execution phases.**

This guardrail is permanent. It is not optional. It is not "nice to have." It exists because the alternative is a bricked development machine.

---

## Mandatory Changes

### 1. PRE-BUILD MEMORY AUDIT (before Phase 4)

Before running ANY tests on a target project, NC Dev System MUST perform a static analysis pass that checks for known memory-leak patterns. This is a NEW sub-phase that runs between BUILD and VERIFY.

**Phase 3.5: MEMORY AUDIT**

Scan the target project's codebase for these red flags:

| Pattern | Why It's Dangerous | What To Flag |
|---------|-------------------|--------------|
| `browser.launch()` / `chromium.launch()` inside a loop or per-request | Spawns unbounded Chromium processes (100-500 MB each) | Flag if launch is not inside a pool with fixed max instances |
| `playwright` in requirements without matching `.close()` calls | Browser processes leak if not explicitly closed | Flag if any code path can skip cleanup |
| `list.append()` / `dict[key] = value` in a loop with no size cap | Unbounded in-memory accumulation | Flag if container grows inside a worker/loop with no `maxlen` or periodic trim |
| Response caching without `max_entries` or `maxsize` | Cache grows until OOM | Flag any `dict`-based cache without eviction |
| Job queues that auto-enqueue child jobs | Exponential job cascade | Flag if a job handler enqueues new jobs without a depth/count limit |
| `asyncio.gather(*tasks)` with `return_exceptions=False` | One OOM crash doesn't stop the others | Flag; should use `return_exceptions=True` or manual task management |
| `try/finally` with multiple cleanup steps not independently guarded | First cleanup failure prevents the rest | Flag sequential cleanup without individual try/except blocks |
| `subprocess.Popen` / `create_subprocess_exec` without memory limits | Child processes can grow unbounded | Flag if no `ulimit` or container memory cap |
| Docker services without `mem_limit` / `deploy.resources.limits` | Containers can consume all host memory | Flag in docker-compose files |

**If ANY of these patterns are found:**
1. Log them as warnings in the build report
2. Generate a `MEMORY-SAFETY-REPORT.md` in the target project's `.nc-dev/` directory
3. Downgrade E2E test concurrency to 1 (sequential only)
4. Add `--memory=4g` to any Docker containers started for testing
5. Do NOT skip the build — the project can still be built. But E2E and verification MUST run with safety constraints.

**If NONE are found:** proceed normally.

### 2. E2E TESTS MUST BE SERIALIZED ACROSS BUILDERS

This is the core change. The current architecture is:

```
Phase 3: BUILD — 3 parallel builders (asyncio.gather)
  Each builder:
    1. Creates worktree
    2. Generates code
    3. Runs unit tests        ← fine in parallel
    4. Runs E2E tests         ← THIS IS THE PROBLEM
    5. Captures screenshots   ← THIS IS ALSO A PROBLEM
```

**The problem:** 3 builders running E2E tests simultaneously means 3 sets of Docker containers, 3 sets of Playwright browsers, 3 sets of Chromium processes — all on the same host. If the target project has ANY memory issues, this multiplies the damage by 3x.

**The fix — two-phase build execution:**

```
Phase 3a: PARALLEL BUILD (keep as-is, this is fine)
  - 3 builders run in parallel
  - Each builder generates code and runs UNIT TESTS ONLY
  - Unit tests are fast, lightweight, no browsers, no Docker
  - This is where NC Dev System's speed comes from — DO NOT LIMIT THIS

Phase 3b: SEQUENTIAL VERIFY (new — serialized E2E)
  - After ALL builders complete, run E2E tests ONE FEATURE AT A TIME
  - Each E2E run gets exclusive access to Docker and Playwright
  - Clean up ALL browser processes and Docker containers between runs
  - Monitor memory between each E2E run
  - If memory exceeds 80% of system RAM, pause and force GC before continuing
```

**Implementation in `pipeline.py`:**

```python
# Phase 3a: Parallel build (code generation + unit tests only)
semaphore = asyncio.Semaphore(self.config.build.max_parallel_builders)
build_results = await asyncio.gather(*tasks, return_exceptions=True)  # Note: return_exceptions=True

# Phase 3b: Sequential E2E verification
for feature_result in build_results:
    if isinstance(feature_result, Exception):
        continue
    if not feature_result.get("success"):
        continue
    await self._run_feature_e2e(feature_result)  # Sequential, one at a time
    await self._cleanup_resources()  # Kill orphan browsers, stop Docker containers
    await self._check_memory_pressure()  # Pause if memory > 80%
```

**DO NOT use `asyncio.gather` for E2E tests. Ever. Sequential only.**

### 3. PROCESS CLEANUP BETWEEN PHASES

After every phase transition (3→4, 4→5, etc.), NC Dev System MUST:

```python
async def _cleanup_resources(self):
    """Kill orphaned processes and free memory between phases."""
    # 1. Kill any orphaned Chromium/browser processes
    await run_command("pkill -f chromium 2>/dev/null || true")
    await run_command("pkill -f 'playwright' 2>/dev/null || true")

    # 2. Stop any Docker containers started during testing
    await run_command(
        f"docker compose -f {self.config.output_dir}/docker-compose.dev.yml down 2>/dev/null || true"
    )

    # 3. Clean up stale worktrees
    # (worktrees from failed builders that didn't clean up after themselves)

    # 4. Force Python garbage collection
    import gc
    gc.collect()

    # 5. Log current memory state
    await self._log_memory_usage()
```

This cleanup MUST run:
- Between Phase 3 and Phase 4
- Between each E2E test run in Phase 3b
- Between Phase 4 and Phase 5
- After any builder timeout or crash
- After any phase failure before breaking out of the pipeline loop

### 4. MEMORY MONITORING DURING BUILDS

Add `psutil` as a dependency. Monitor memory at key checkpoints:

```python
import psutil

def _check_memory_pressure(self) -> bool:
    """Return True if memory usage is dangerously high."""
    mem = psutil.virtual_memory()
    usage_pct = mem.percent
    used_gb = mem.used / (1024**3)
    total_gb = mem.total / (1024**3)

    if usage_pct > 90:
        logger.critical(
            "MEMORY CRITICAL: %.1f%% used (%.1fGB / %.1fGB) — "
            "pausing pipeline and forcing cleanup",
            usage_pct, used_gb, total_gb
        )
        self._emergency_cleanup()
        return True

    if usage_pct > 80:
        logger.warning(
            "MEMORY HIGH: %.1f%% used (%.1fGB / %.1fGB) — "
            "downgrading to sequential execution",
            usage_pct, used_gb, total_gb
        )
        return True

    logger.info("Memory OK: %.1f%% used (%.1fGB / %.1fGB)", usage_pct, used_gb, total_gb)
    return False
```

**Memory checkpoints (MANDATORY):**
- Before starting Phase 3 (BUILD)
- After each parallel builder completes
- Before each E2E test run
- After each E2E test run
- Before starting Phase 4 (VERIFY)
- After Phase 5 (HARDEN)

If memory exceeds 80% at any checkpoint:
1. Stop all parallel operations
2. Run `_cleanup_resources()`
3. Wait 10 seconds for OS to reclaim memory
4. Re-check. If still above 80%, switch to fully sequential mode for the rest of the pipeline
5. Log the decision in the build report

If memory exceeds 90%:
1. IMMEDIATELY kill all builder subprocesses
2. Run emergency cleanup
3. Save pipeline state
4. Exit with a clear error message: "Pipeline halted: memory pressure exceeded 90%. Run `ncdev resume` after freeing memory."

### 5. BUILDER SUBPROCESS HARDENING

**`codex_runner.py` changes:**

The builder process spawning MUST be hardened:

```python
# Before spawning, check memory
if self._check_memory_pressure():
    raise CodexRunnerError("Cannot start builder: memory pressure too high")

# Spawn with resource limits (macOS doesn't support cgroups, but we can monitor)
process = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=str(worktree),
)

# Monitor memory during execution
monitor_task = asyncio.create_task(self._monitor_process_memory(process.pid))
```

**`fallback.py` changes:**

```python
# In execute_parallel: change return_exceptions from False to True
results = await asyncio.gather(*tasks, return_exceptions=True)

# Handle exceptions explicitly — don't let one OOM crash hide behind another
for i, res in enumerate(results):
    if isinstance(res, Exception):
        logger.error("Builder %d crashed: %s", i, res)
        await self._cleanup_resources()
```

### 6. DOCKER MEMORY LIMITS IN GENERATED PROJECTS

When NC Dev System generates `docker-compose.dev.yml` for ANY project, it MUST include memory limits:

```yaml
services:
  backend:
    # ... existing config ...
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 512M

  frontend:
    deploy:
      resources:
        limits:
          memory: 2G

  mongodb:
    deploy:
      resources:
        limits:
          memory: 2G

  redis:
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    deploy:
      resources:
        limits:
          memory: 1G
```

Update the Docker Compose Jinja2 templates at `templates/docker-compose.dev.yml.j2` to include these limits by default.

---

## What NC Dev System Must NOT Change

To be clear — the parallel build capability is a strength. These are the things that should stay as they are:

- **3 parallel builders for code generation** — keep this. Writing code is CPU-bound, not memory-intensive.
- **Parallel unit test execution** — keep this. Unit tests are fast and lightweight.
- **10-minute builder timeout** — keep this. It's a reasonable limit.
- **Worktree isolation** — keep this. It's clean and correct.
- **Fallback strategy** — keep this. Retry logic is fine.

The ONLY things that must be serialized are:
1. E2E tests (Playwright browser tests)
2. Screenshot capture (Chromium browser spawning)
3. Docker container lifecycle (compose up/down)
4. Any operation that spawns browser processes

Everything else can stay parallel.

---

## Implementation Priority

| Priority | Change | Files | Effort |
|----------|--------|-------|--------|
| **P0** | E2E test serialization (Phase 3b) | `src/pipeline.py` | Medium |
| **P0** | Process cleanup between phases | `src/pipeline.py`, new `src/utils.py` function | Small |
| **P0** | `return_exceptions=True` in gather calls | `src/pipeline.py`, `src/builder/fallback.py` | Trivial |
| **P1** | Memory monitoring with psutil | `src/pipeline.py`, `src/builder/codex_runner.py` | Medium |
| **P1** | Pre-build memory audit (Phase 3.5) | New `src/auditor/` module | Medium |
| **P2** | Docker memory limits in templates | `templates/docker-compose.dev.yml.j2` | Small |
| **P2** | Screenshot capture serialization | `src/tester/screenshot.py` | Small |

---

## Testing This Fix

After implementing:

1. Run `ncdev dev` against Vantage (the project that caused the crash)
2. Monitor with `watch -n1 'ps aux --sort=-rss | head -20'` in a separate terminal
3. Verify:
   - Memory never exceeds 80% during the build
   - E2E tests run one at a time (check logs for sequential execution)
   - No orphaned Chromium processes after build completes (`pgrep -c chromium` should return 0)
   - Build report includes memory checkpoints
   - `MEMORY-SAFETY-REPORT.md` is generated for Vantage (it has known leak patterns)
4. Run against a clean project (e.g., `yensi-booking`) and verify no performance regression on the parallel build phase

---

## Related Incident Documentation

- **Vantage memory leaks:** `/Users/nrupal/dev/yensi/dev/vantage/URGENT-MEMORY-LEAK-FIX.md`
- **Kernel panic log:** `/Library/Logs/DiagnosticReports/panic-full-2026-04-11-083145.0002.panic`
- **WindowServer crashes:** `/Library/Logs/DiagnosticReports/WindowServer-2026-04-11-075050.ips`
- **Jetsam (OOM) events:** Multiple files from Apr 10-11 in `/Library/Logs/DiagnosticReports/`

---

## Final Note

NC Dev System builds products autonomously. That autonomy comes with responsibility. An autonomous system that can crash the host machine is not autonomous — it is dangerous. Memory safety is not a feature request. It is a prerequisite for the system being trusted to run unsupervised.

This guardrail ensures NC Dev System can still build fast, still build in parallel, still build ambitiously — but it does so without bringing the entire development machine to its knees. The parallel build pipeline is the system's greatest strength. This document does not weaken it. It protects it from destroying itself.
