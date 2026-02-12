"""NC Dev System Pipeline Orchestrator.

Implements the 6-phase autonomous build pipeline:

Phase 1: UNDERSTAND -- Parse requirements, extract features, design architecture.
Phase 2: SCAFFOLD  -- Create repo, generate project, set up mocks.
Phase 3: BUILD     -- Parallel feature building in isolated worktrees.
Phase 4: VERIFY    -- Unit tests, E2E tests, screenshots, AI vision analysis.
Phase 5: HARDEN    -- Error handling, responsive, accessibility, performance.
Phase 6: DELIVER   -- Usage docs, screenshots, build report, push to GitHub.

Usage::

    python -m src.pipeline requirements.md --output ./my-project
    python -m src.pipeline requirements.md --phases 1,2
"""

from __future__ import annotations

import asyncio
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from src.config import Config
from src.ollama_client import OllamaClient
from src.utils import (
    PHASE_NAMES,
    check_ports_available,
    console,
    create_progress,
    ensure_dir,
    format_duration,
    load_json,
    print_error,
    print_phase_header,
    print_success,
    print_summary_table,
    print_warning,
    run_command,
    save_json,
)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PipelineError(Exception):
    """Raised when a pipeline phase fails irrecoverably."""

    def __init__(self, phase: int, message: str) -> None:
        self.phase = phase
        super().__init__(f"Phase {phase} ({PHASE_NAMES.get(phase, '?')}): {message}")


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------


class Pipeline:
    """NC Dev System Pipeline Orchestrator.

    Drives the six-phase build pipeline, persisting state between phases so
    that runs can be resumed or individual phases can be re-executed in
    isolation.

    Attributes:
        config: Global pipeline configuration.
        state: Mutable dictionary that accumulates results from each phase.
        ollama: Async Ollama client for local model operations.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.state: dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "phases_completed": [],
            "phases_failed": [],
            "success": False,
        }
        self.ollama = OllamaClient(
            base_url=config.ollama.url,
            timeout=config.ollama.timeout,
        )

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    async def _save_state(self) -> None:
        """Persist the current pipeline state to ``.nc-dev/pipeline-state.json``."""
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        await save_json(self.state, self.config.state_path)

    async def _load_state(self) -> None:
        """Restore state from a previous run, if available."""
        if self.config.state_path.exists():
            try:
                self.state.update(load_json(self.config.state_path))
            except Exception:
                # Corrupted state file -- start fresh.
                pass

    # ------------------------------------------------------------------
    # Pre-flight checks
    # ------------------------------------------------------------------

    async def _preflight(self) -> None:
        """Run preflight checks before the pipeline starts.

        * Ensures the output directory is writable.
        * Checks that required ports are available.
        * Probes the Ollama server.
        """
        console.print(Panel("[bold]Running pre-flight checks...[/bold]", style="cyan"))

        # 1. Ensure output directory structure
        self.config.ensure_directories()
        console.print("  [green]+[/green] Output directory ready")

        # 2. Port availability
        all_ports = self.config.ports.all_ports()
        port_status = await check_ports_available(all_ports)
        busy_ports = [p for p, available in port_status.items() if not available]
        if busy_ports:
            print_warning(
                f"  Ports already in use: {', '.join(str(p) for p in busy_ports)}. "
                f"Services using these ports may conflict."
            )
        else:
            console.print("  [green]+[/green] All ports available")

        # 3. Ollama availability
        ollama_up = await self.ollama.is_available()
        if ollama_up:
            models = await self.ollama.list_models()
            console.print(
                f"  [green]+[/green] Ollama online ({len(models)} model(s) available)"
            )
        else:
            print_warning(
                "  Ollama is not reachable -- local model features will be unavailable."
            )

        console.print()

    # ------------------------------------------------------------------
    # Phase dispatch
    # ------------------------------------------------------------------

    _PHASE_METHODS: dict[int, str] = {
        1: "phase1_understand",
        2: "phase2_scaffold",
        3: "phase3_build",
        4: "phase4_verify",
        5: "phase5_harden",
        6: "phase6_deliver",
    }

    async def run(self, requirements_path: str) -> dict[str, Any]:
        """Execute the pipeline (or the selected subset of phases).

        Args:
            requirements_path: Path to the requirements markdown file.

        Returns:
            The final pipeline state dictionary, including a top-level
            ``success`` boolean.
        """
        pipeline_start = time.monotonic()

        # Banner
        console.print(
            Panel(
                f"[bold bright_cyan]NC Dev System Pipeline[/bold bright_cyan]\n"
                f"Project : {self.config.project_name or '(auto-detect)'}\n"
                f"Output  : {self.config.output_dir.resolve()}\n"
                f"Phases  : {', '.join(str(p) for p in self.config.phases)}",
                title="[bold]Pipeline Start[/bold]",
                border_style="bright_cyan",
            )
        )

        # Pre-flight
        await self._preflight()

        # Store the requirements path in state for later phases to reference.
        self.state["requirements_path"] = str(Path(requirements_path).resolve())

        # Load any prior state (for resumed runs).
        await self._load_state()

        all_success = True

        for phase_num in sorted(self.config.phases):
            method_name = self._PHASE_METHODS.get(phase_num)
            if method_name is None:
                print_warning(f"Unknown phase {phase_num} -- skipping.")
                continue

            phase_name = PHASE_NAMES.get(phase_num, "UNKNOWN")
            print_phase_header(phase_num, phase_name)

            phase_start = time.monotonic()
            try:
                method = getattr(self, method_name)
                if phase_num == 1:
                    result = await method(requirements_path)
                else:
                    result = await method()

                elapsed = time.monotonic() - phase_start
                self.state[f"phase{phase_num}"] = result
                self.state["phases_completed"].append(phase_num)

                print_success(
                    f"Phase {phase_num} ({phase_name}) completed in {format_duration(elapsed)}"
                )

            except PipelineError as exc:
                elapsed = time.monotonic() - phase_start
                all_success = False
                self.state["phases_failed"].append(phase_num)
                self.state[f"phase{phase_num}_error"] = str(exc)
                print_error(
                    f"Phase {phase_num} ({phase_name}) FAILED after "
                    f"{format_duration(elapsed)}: {exc}"
                )
                # Stop the pipeline on failure -- later phases depend on earlier ones.
                break

            except Exception as exc:
                elapsed = time.monotonic() - phase_start
                all_success = False
                self.state["phases_failed"].append(phase_num)
                tb = traceback.format_exc()
                self.state[f"phase{phase_num}_error"] = tb
                print_error(
                    f"Phase {phase_num} ({phase_name}) FAILED after "
                    f"{format_duration(elapsed)}: {exc}"
                )
                console.print(f"[dim]{tb}[/dim]")
                break

            finally:
                await self._save_state()

        # Final summary
        total_elapsed = time.monotonic() - pipeline_start
        self.state["success"] = all_success
        self.state["total_duration"] = format_duration(total_elapsed)
        self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
        await self._save_state()

        self._print_final_summary(total_elapsed)
        return self.state

    # ------------------------------------------------------------------
    # Phase 1: UNDERSTAND
    # ------------------------------------------------------------------

    async def phase1_understand(self, requirements_path: str) -> dict[str, Any]:
        """Parse requirements and generate architecture, features, and test plan.

        Reads the requirements markdown, uses the parser module to extract
        structured data, and saves the artefacts under ``.nc-dev/``.
        """
        req_path = Path(requirements_path)
        if not req_path.exists():
            raise PipelineError(1, f"Requirements file not found: {req_path}")

        requirements_text = req_path.read_text(encoding="utf-8")
        if not requirements_text.strip():
            raise PipelineError(1, f"Requirements file is empty: {req_path}")

        console.print(f"  Reading requirements from [bold]{req_path}[/bold]")
        console.print(f"  File size: {len(requirements_text)} characters")

        # Attempt to use the parser module.  If it is not yet implemented we
        # fall back to storing the raw text and a minimal stub structure so
        # the pipeline can still proceed.
        features: list[dict[str, Any]] = []
        architecture: dict[str, Any] = {}
        test_plan: dict[str, Any] = {}

        try:
            from src.parser.models import Architecture, ParseResult, TestPlan

            # The parser subpackage may expose a ``parse_requirements`` function.
            # We attempt the dynamic import; if it is missing we use the fallback.
            parse_fn = None
            try:
                from src.parser import parse_requirements as parse_fn  # type: ignore[import-untyped]
            except ImportError:
                pass

            if parse_fn is not None:
                console.print("  Using parser module to extract features...")
                # parse_requirements expects a file path string, not raw text.
                result: ParseResult = await parse_fn(str(req_path))
                features = [f.model_dump() for f in result.features]
                architecture = result.architecture.model_dump()
                test_plan = result.test_plan.model_dump()

                # Sync project name from architecture if not already set.
                if not self.config.project_name and architecture.get("project_name"):
                    self.config.project_name = architecture["project_name"]
            else:
                console.print(
                    "  [yellow]Parser function not available -- storing raw requirements.[/yellow]"
                )
                project_name = self.config.project_name or _infer_project_name(requirements_text)
                self.config.project_name = project_name

                architecture = Architecture(
                    project_name=project_name,
                    description="Auto-generated from requirements",
                    port_allocation=self.config.ports.as_dict(),
                ).model_dump()

                test_plan = TestPlan().model_dump()

        except ImportError:
            console.print(
                "  [yellow]Parser models not importable -- storing raw requirements.[/yellow]"
            )
            project_name = self.config.project_name or _infer_project_name(requirements_text)
            self.config.project_name = project_name
            architecture = {
                "project_name": project_name,
                "description": "Auto-generated from requirements",
                "port_allocation": self.config.ports.as_dict(),
            }

        # Persist artefacts
        ensure_dir(self.config.nc_dev_path)
        await save_json(features, self.config.features_path)
        await save_json(architecture, self.config.architecture_path)
        await save_json(test_plan, self.config.test_plan_path)

        # Save the raw requirements alongside
        raw_path = self.config.nc_dev_path / "requirements.md"
        raw_path.write_text(requirements_text, encoding="utf-8")

        # Save config snapshot
        self.config.save()

        phase_result: dict[str, Any] = {
            "features_count": len(features),
            "features_path": str(self.config.features_path),
            "architecture_path": str(self.config.architecture_path),
            "test_plan_path": str(self.config.test_plan_path),
            "project_name": self.config.project_name,
        }

        print_summary_table(
            {
                "Project name": self.config.project_name,
                "Features extracted": str(len(features)),
                "Features file": str(self.config.features_path),
                "Architecture file": str(self.config.architecture_path),
                "Test plan file": str(self.config.test_plan_path),
            },
            title="Phase 1 Results",
        )

        return phase_result

    # ------------------------------------------------------------------
    # Phase 2: SCAFFOLD
    # ------------------------------------------------------------------

    async def phase2_scaffold(self) -> dict[str, Any]:
        """Scaffold the project directory using the architecture from Phase 1.

        Creates the full project structure (backend, frontend, docker configs,
        etc.) using the scaffolder module.
        """
        architecture = self._require_artefact(
            self.config.architecture_path, "architecture (run Phase 1 first)"
        )

        project_name = architecture.get("project_name", self.config.project_name)
        if project_name:
            self.config.project_name = project_name

        console.print(f"  Scaffolding project [bold]{project_name}[/bold]...")

        scaffold_result: dict[str, Any] = {
            "project_name": project_name,
            "output_dir": str(self.config.output_dir.resolve()),
        }

        # Attempt to use the scaffolder module.
        try:
            from src.scaffolder import ProjectGenerator, ProjectConfig  # type: ignore[import-untyped]

            project_config = ProjectConfig(
                name=project_name or "project",
                description=architecture.get("description", ""),
                auth_required=architecture.get("auth_required", False),
                features=architecture.get("features", []),
                db_collections=architecture.get("db_collections", []),
                api_contracts=architecture.get("api_contracts", []),
                external_apis=architecture.get("external_apis", []),
            )
            generator = ProjectGenerator(project_config)
            gen_path = await generator.generate(self.config.output_dir)
            scaffold_result["project_path"] = str(gen_path)
            console.print("  [green]Project scaffolded via scaffolder module.[/green]")
        except ImportError:
            console.print(
                "  [yellow]Scaffolder module not available -- "
                "creating minimal directory structure.[/yellow]"
            )
            scaffold_result.update(
                await self._scaffold_minimal(project_name, architecture)
            )

        # Initialise git if not already a repo.
        git_init_result = await self._ensure_git_repo()
        scaffold_result["git_initialized"] = git_init_result

        await save_json(scaffold_result, self.config.nc_dev_path / "scaffold-result.json")

        print_summary_table(
            {
                "Project": project_name,
                "Output": str(self.config.output_dir.resolve()),
                "Git": "initialized" if git_init_result else "already present",
            },
            title="Phase 2 Results",
        )

        return scaffold_result

    async def _scaffold_minimal(
        self, project_name: str, architecture: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a minimal project skeleton when the scaffolder module is unavailable."""
        dirs = [
            "backend/app/api/v1/endpoints",
            "backend/app/core",
            "backend/app/models",
            "backend/app/schemas",
            "backend/app/services",
            "backend/app/db/migrations",
            "backend/tests/unit",
            "backend/tests/integration",
            "backend/tests/e2e",
            "frontend/src/api",
            "frontend/src/stores",
            "frontend/src/components/ui",
            "frontend/src/components/layout",
            "frontend/src/components/features",
            "frontend/src/pages",
            "frontend/src/hooks",
            "frontend/src/types",
            "frontend/src/utils",
            "frontend/src/styles",
            "frontend/src/mocks",
            "frontend/e2e",
            "frontend/tests/unit",
            "scripts",
            "docs/screenshots",
        ]

        created: list[str] = []
        for d in dirs:
            dir_path = self.config.output_dir / d
            dir_path.mkdir(parents=True, exist_ok=True)
            created.append(d)

        return {"directories_created": len(created)}

    async def _ensure_git_repo(self) -> bool:
        """Initialise a git repo in the output directory if one does not exist."""
        git_dir = self.config.output_dir / ".git"
        if git_dir.exists():
            return False

        returncode, _, stderr = await run_command(
            ["git", "init"], cwd=self.config.output_dir
        )
        if returncode != 0:
            print_warning(f"  git init failed: {stderr}")
            return False

        # Create an initial commit so branches work.
        await run_command(
            ["git", "commit", "--allow-empty", "-m", "chore: initial commit"],
            cwd=self.config.output_dir,
        )
        return True

    # ------------------------------------------------------------------
    # Phase 3: BUILD
    # ------------------------------------------------------------------

    async def phase3_build(self) -> dict[str, Any]:
        """Build features in parallel using Codex builders (or fallback).

        For each feature extracted in Phase 1, creates a git worktree and
        spawns a Codex builder.  Up to ``max_parallel_builders`` builders run
        concurrently.  If a builder fails twice, the feature falls back to
        Claude Sonnet via sub-agent.
        """
        features_data = self._require_artefact(
            self.config.features_path, "features (run Phase 1 first)"
        )
        features_list: list[dict[str, Any]] = features_data.get("_root", []) if "_root" in features_data else []

        # features_path may contain a list at the root.
        if not features_list:
            features_list_path = self.config.features_path
            if features_list_path.exists():
                import json
                raw = features_list_path.read_text(encoding="utf-8")
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    features_list = parsed

        if not features_list:
            console.print("  [yellow]No features to build -- skipping Phase 3.[/yellow]")
            return {"features_built": 0, "features_failed": 0}

        console.print(
            f"  Building [bold]{len(features_list)}[/bold] feature(s) "
            f"(max {self.config.build.max_parallel_builders} parallel)..."
        )

        build_results: list[dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.config.build.max_parallel_builders)

        async def _build_feature(feature: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await self._build_single_feature(feature)

        tasks = [_build_feature(f) for f in features_list]
        build_results = await asyncio.gather(*tasks, return_exceptions=False)

        succeeded = sum(1 for r in build_results if r.get("success"))
        failed = sum(1 for r in build_results if not r.get("success"))

        phase_result = {
            "features_built": succeeded,
            "features_failed": failed,
            "results": build_results,
        }

        await save_json(phase_result, self.config.nc_dev_path / "build-results.json")

        print_summary_table(
            {
                "Features attempted": str(len(features_list)),
                "Succeeded": str(succeeded),
                "Failed": str(failed),
            },
            title="Phase 3 Results",
        )

        if failed > 0:
            print_warning(
                f"  {failed} feature(s) failed to build. "
                "Check build-results.json for details."
            )

        return phase_result

    async def _build_single_feature(self, feature: dict[str, Any]) -> dict[str, Any]:
        """Build a single feature, retrying with fallback on failure.

        Attempts the Codex CLI first (up to ``max_codex_attempts``). On
        failure, falls back to the builder module's fallback strategy.
        """
        feature_name = feature.get("name", "unnamed")
        sanitized = feature_name.strip().lower().replace(" ", "-")

        console.print(f"    [cyan]Building feature:[/cyan] {feature_name}")

        # Write the build prompt for this feature.
        prompt_path = self.config.prompts_dir / f"build-{sanitized}.md"
        ensure_dir(self.config.prompts_dir)
        prompt_content = _generate_build_prompt(feature, self.config)
        prompt_path.write_text(prompt_content, encoding="utf-8")

        # Try the builder module first.
        try:
            from src.builder import FallbackStrategy  # type: ignore[import-untyped]

            strategy = FallbackStrategy(
                feature=feature,
                config=self.config,
                prompt_path=prompt_path,
            )
            result = await strategy.execute()
            return result if isinstance(result, dict) else {"success": True, "feature": feature_name}
        except ImportError:
            pass

        # Fallback: attempt Codex CLI directly.
        # Codex CLI handles its own authentication via `codex login`.
        for attempt in range(1, self.config.build.max_codex_attempts + 1):
            console.print(
                f"    Codex attempt {attempt}/{self.config.build.max_codex_attempts} "
                f"for {feature_name}..."
            )

            result_path = self.config.results_dir / f"{sanitized}.json"
            ensure_dir(self.config.results_dir)

            codex_cmd = (
                f'codex exec --full-auto --json '
                f'--cd "{self.config.output_dir}" '
                f'"$(cat {prompt_path})" '
                f"-o {result_path}"
            )

            returncode, stdout, stderr = await run_command(
                codex_cmd,
                cwd=self.config.output_dir,
                timeout=self.config.build.codex_timeout,
            )

            if returncode == 0:
                console.print(f"    [green]Codex succeeded for {feature_name}[/green]")
                return {"success": True, "feature": feature_name, "attempt": attempt}

            console.print(
                f"    [yellow]Codex attempt {attempt} failed "
                f"(exit {returncode}): {stderr[:200]}[/yellow]"
            )

        return {
            "success": False,
            "feature": feature_name,
            "error": f"Codex failed after {self.config.build.max_codex_attempts} attempts",
        }

    # ------------------------------------------------------------------
    # Phase 4: VERIFY
    # ------------------------------------------------------------------

    async def phase4_verify(self) -> dict[str, Any]:
        """Run tests and visual verification with a fix-retest loop.

        Executes unit tests, E2E tests, captures screenshots, and uses AI
        vision analysis.  If failures are found, attempts automatic fixes
        up to ``max_fix_iterations`` times.
        """
        console.print("  Running verification suite...")

        iteration = 0
        max_iterations = self.config.build.max_fix_iterations
        test_results: dict[str, Any] = {}

        while iteration <= max_iterations:
            iteration += 1
            console.print(
                f"  [cyan]Verification iteration {iteration}/{max_iterations + 1}[/cyan]"
            )

            # Run tests via the tester module or fallback commands.
            test_results = await self._run_tests()
            visual_results = await self._run_visual_verification()

            test_results["visual"] = visual_results

            all_passed = (
                test_results.get("unit_passed", True)
                and test_results.get("e2e_passed", True)
                and visual_results.get("passed", True)
            )

            if all_passed:
                console.print("  [green]All verifications passed.[/green]")
                test_results["iterations"] = iteration
                test_results["all_passed"] = True
                break

            if iteration > max_iterations:
                print_warning("  Max fix iterations reached -- some tests still failing.")
                test_results["iterations"] = iteration
                test_results["all_passed"] = False
                break

            # Attempt automatic fixes
            console.print(
                f"  [yellow]Failures detected -- attempting auto-fix "
                f"(iteration {iteration})...[/yellow]"
            )
            await self._attempt_auto_fix(test_results)

        await save_json(test_results, self.config.nc_dev_path / "test-results.json")

        total_passed = test_results.get("unit_total_passed", 0) + test_results.get("e2e_total_passed", 0)
        total_failed = test_results.get("unit_total_failed", 0) + test_results.get("e2e_total_failed", 0)

        print_summary_table(
            {
                "Unit tests passed": str(test_results.get("unit_passed", "N/A")),
                "E2E tests passed": str(test_results.get("e2e_passed", "N/A")),
                "Visual passed": str(visual_results.get("passed", "N/A")),
                "Fix iterations": str(test_results.get("iterations", 0)),
                "Overall": "PASSED" if test_results.get("all_passed") else "FAILED",
            },
            title="Phase 4 Results",
        )

        return test_results

    async def _run_tests(self) -> dict[str, Any]:
        """Execute unit and E2E tests."""
        results: dict[str, Any] = {}

        # Try the tester module first.
        try:
            from src.tester import TestRunner  # type: ignore[import-untyped]

            runner = TestRunner(config=self.config)
            return await runner.run_all()
        except ImportError:
            pass

        # Fallback: run pytest and vitest directly.
        backend_dir = self.config.output_dir / "backend"
        frontend_dir = self.config.output_dir / "frontend"

        # Backend unit tests
        if (backend_dir / "tests").exists():
            console.print("    Running backend tests (pytest)...")
            returncode, stdout, stderr = await run_command(
                ["python", "-m", "pytest", "--tb=short", "-q"],
                cwd=backend_dir,
                timeout=120,
            )
            results["unit_passed"] = returncode == 0
            results["unit_output"] = stdout
            results["unit_stderr"] = stderr
        else:
            results["unit_passed"] = True
            results["unit_output"] = "No backend tests directory"

        # Frontend unit tests
        if (frontend_dir / "package.json").exists():
            console.print("    Running frontend tests (vitest)...")
            returncode, stdout, stderr = await run_command(
                "npx vitest run --reporter=verbose 2>&1",
                cwd=frontend_dir,
                timeout=120,
            )
            results["e2e_passed"] = returncode == 0
            results["e2e_output"] = stdout
            results["e2e_stderr"] = stderr
        else:
            results["e2e_passed"] = True
            results["e2e_output"] = "No frontend package.json"

        return results

    async def _run_visual_verification(self) -> dict[str, Any]:
        """Capture screenshots and run vision analysis."""
        # Try the tester module.
        try:
            from src.tester import ScreenshotCapture, VisionAnalyzer  # type: ignore[import-untyped]

            capture = ScreenshotCapture(config=self.config)
            screenshots = await capture.capture_all()

            analyzer = VisionAnalyzer(config=self.config, ollama=self.ollama)
            vision_results = await analyzer.analyze_all(screenshots)
            return vision_results if isinstance(vision_results, dict) else {"passed": True}
        except ImportError:
            pass

        console.print("    [yellow]Visual verification module not available -- skipping.[/yellow]")
        return {"passed": True, "skipped": True}

    async def _attempt_auto_fix(self, test_results: dict[str, Any]) -> None:
        """Attempt to fix test failures automatically using AI."""
        try:
            from src.tester import AutoFixer  # type: ignore[import-untyped]

            fixer = AutoFixer(config=self.config, ollama=self.ollama)
            await fixer.fix(test_results)
            return
        except ImportError:
            pass

        console.print(
            "    [yellow]Auto-fix module not available -- manual intervention needed.[/yellow]"
        )

    # ------------------------------------------------------------------
    # Phase 5: HARDEN
    # ------------------------------------------------------------------

    async def phase5_harden(self) -> dict[str, Any]:
        """Harden the project: error handling, accessibility, performance.

        Runs a suite of hardening checks and applies fixes where possible.
        """
        console.print("  Running hardening checks...")

        hardening_results: dict[str, Any] = {}

        # Try the hardener module.
        try:
            from src.hardener import HardeningEngine  # type: ignore[import-untyped]

            engine = HardeningEngine(config=self.config)
            hardening_results = await engine.run()
            if not isinstance(hardening_results, dict):
                hardening_results = {}
        except ImportError:
            console.print(
                "  [yellow]Hardener module not available -- running basic checks.[/yellow]"
            )
            hardening_results = await self._basic_hardening()

        await save_json(hardening_results, self.config.nc_dev_path / "hardening-results.json")

        issues_found = hardening_results.get("issues_found", 0)
        issues_fixed = hardening_results.get("issues_fixed", 0)

        print_summary_table(
            {
                "Issues found": str(issues_found),
                "Issues fixed": str(issues_fixed),
                "Remaining": str(issues_found - issues_fixed),
            },
            title="Phase 5 Results",
        )

        return hardening_results

    async def _basic_hardening(self) -> dict[str, Any]:
        """Perform basic hardening checks when the hardener module is unavailable.

        Checks for common issues like missing health endpoints, missing
        security headers, console.log statements, etc.
        """
        issues: list[dict[str, str]] = []
        fixed: list[dict[str, str]] = []

        backend_dir = self.config.output_dir / "backend"
        frontend_dir = self.config.output_dir / "frontend"

        # Check for health endpoint
        health_py = backend_dir / "app" / "api" / "v1" / "endpoints" / "health.py"
        if backend_dir.exists() and not health_py.exists():
            issues.append({
                "type": "missing_health_endpoint",
                "severity": "critical",
                "description": "No /health endpoint found in backend",
            })

        # Check for console.log in frontend source
        if frontend_dir.exists():
            returncode, stdout, _ = await run_command(
                "grep -r 'console.log' --include='*.ts' --include='*.tsx' -l || true",
                cwd=frontend_dir / "src",
                timeout=30,
            )
            if stdout.strip():
                files_with_logs = [f for f in stdout.strip().split("\n") if f]
                issues.append({
                    "type": "console_log",
                    "severity": "warning",
                    "description": f"console.log found in {len(files_with_logs)} file(s)",
                    "files": ", ".join(files_with_logs[:10]),
                })

        # Check for .env.example
        if not (self.config.output_dir / ".env.example").exists():
            issues.append({
                "type": "missing_env_example",
                "severity": "warning",
                "description": "No .env.example file found",
            })

        return {
            "issues_found": len(issues),
            "issues_fixed": len(fixed),
            "issues": issues,
            "fixed": fixed,
        }

    # ------------------------------------------------------------------
    # Phase 6: DELIVER
    # ------------------------------------------------------------------

    async def phase6_deliver(self) -> dict[str, Any]:
        """Generate documentation, build report, and delivery package."""
        console.print("  Generating delivery package...")

        delivery_result: dict[str, Any] = {}

        # Try the reporter module.
        try:
            from src.reporter import DeliveryEngine  # type: ignore[import-untyped]

            engine = DeliveryEngine(config=self.config, state=self.state)
            delivery_result = await engine.deliver()
            if not isinstance(delivery_result, dict):
                delivery_result = {}
        except ImportError:
            console.print(
                "  [yellow]Reporter module not available -- generating basic report.[/yellow]"
            )
            delivery_result = await self._basic_delivery()

        await save_json(delivery_result, self.config.nc_dev_path / "delivery-result.json")

        print_summary_table(
            {
                "Build report": str(delivery_result.get("build_report", "N/A")),
                "Docs generated": str(delivery_result.get("docs_count", 0)),
                "Screenshots": str(delivery_result.get("screenshots_count", 0)),
            },
            title="Phase 6 Results",
        )

        return delivery_result

    async def _basic_delivery(self) -> dict[str, Any]:
        """Generate a minimal build report when the reporter module is unavailable."""
        report_path = self.config.build_report_path
        ensure_dir(report_path.parent)

        # Gather data from state
        phases_ok = self.state.get("phases_completed", [])
        phases_fail = self.state.get("phases_failed", [])
        project_name = self.config.project_name or "NC Dev Project"

        lines = [
            f"# Build Report: {project_name}",
            "",
            f"**Generated**: {datetime.now(timezone.utc).isoformat()}",
            f"**Pipeline duration**: {self.state.get('total_duration', 'N/A')}",
            "",
            "## Phase Results",
            "",
        ]

        for phase_num in range(1, 7):
            name = PHASE_NAMES.get(phase_num, "?")
            if phase_num in phases_ok:
                lines.append(f"- Phase {phase_num} ({name}): **PASSED**")
            elif phase_num in phases_fail:
                error = self.state.get(f"phase{phase_num}_error", "Unknown error")
                lines.append(f"- Phase {phase_num} ({name}): **FAILED** -- {error[:200]}")
            else:
                lines.append(f"- Phase {phase_num} ({name}): *skipped*")

        lines.extend([
            "",
            "## Configuration",
            "",
            f"- Output: `{self.config.output_dir.resolve()}`",
            f"- Frontend port: {self.config.ports.frontend}",
            f"- Backend port: {self.config.ports.backend}",
            f"- MongoDB port: {self.config.ports.mongodb}",
            "",
        ])

        report_text = "\n".join(lines)
        report_path.write_text(report_text, encoding="utf-8")

        # Count screenshots
        screenshots_dir = self.config.screenshots_dir
        screenshot_count = 0
        if screenshots_dir.exists():
            screenshot_count = len(list(screenshots_dir.glob("*.png"))) + len(
                list(screenshots_dir.glob("*.jpg"))
            )

        # Count docs
        docs_dir = self.config.output_dir / "docs"
        docs_count = 0
        if docs_dir.exists():
            docs_count = len(list(docs_dir.glob("*.md")))

        return {
            "build_report": str(report_path),
            "docs_count": docs_count,
            "screenshots_count": screenshot_count,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_artefact(self, path: Path, description: str) -> dict[str, Any]:
        """Load a required JSON artefact or raise ``PipelineError``.

        Args:
            path: Path to the JSON file.
            description: Human-readable description for the error message.

        Returns:
            Parsed JSON dictionary.

        Raises:
            PipelineError: If the file does not exist or cannot be parsed.
        """
        if not path.exists():
            raise PipelineError(
                0, f"Required artefact missing: {description} ({path})"
            )
        try:
            return load_json(path)
        except Exception as exc:
            raise PipelineError(
                0, f"Failed to load {description} from {path}: {exc}"
            ) from exc

    def _print_final_summary(self, total_elapsed: float) -> None:
        """Print the final pipeline summary panel."""
        phases_ok = self.state.get("phases_completed", [])
        phases_fail = self.state.get("phases_failed", [])

        if self.state.get("success"):
            border_style = "bold green"
            status_text = "[bold green]PIPELINE SUCCEEDED[/bold green]"
        else:
            border_style = "bold red"
            status_text = "[bold red]PIPELINE FAILED[/bold red]"

        detail_lines = [
            status_text,
            "",
            f"Duration  : {format_duration(total_elapsed)}",
            f"Completed : {', '.join(str(p) for p in phases_ok) or 'none'}",
        ]

        if phases_fail:
            detail_lines.append(
                f"Failed    : {', '.join(str(p) for p in phases_fail)}"
            )

        detail_lines.extend([
            "",
            f"Output    : {self.config.output_dir.resolve()}",
            f"State     : {self.config.state_path}",
        ])

        console.print()
        console.print(
            Panel(
                "\n".join(detail_lines),
                title="[bold]Pipeline Complete[/bold]",
                border_style=border_style,
            )
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _infer_project_name(requirements_text: str) -> str:
    """Try to extract a project name from the first heading in a markdown file.

    Falls back to ``"nc-dev-project"`` if no heading is found.
    """
    import re

    for line in requirements_text.split("\n"):
        line = line.strip()
        match = re.match(r"^#+\s+(.+)$", line)
        if match:
            raw = match.group(1).strip()
            # Sanitise to something usable as a directory name.
            sanitized = re.sub(r"[^a-zA-Z0-9 _-]", "", raw).strip()
            if sanitized:
                return sanitized.lower().replace(" ", "-")
    return "nc-dev-project"


def _generate_build_prompt(feature: dict[str, Any], config: Config) -> str:
    """Generate a markdown build prompt for a Codex builder.

    The prompt contains all information the builder needs to implement the
    feature without access to the broader pipeline state.
    """
    name = feature.get("name", "Unnamed Feature")
    description = feature.get("description", "")
    endpoints = feature.get("api_endpoints", [])
    routes = feature.get("ui_routes", [])
    acceptance = feature.get("acceptance_criteria", [])

    lines = [
        f"# Build Feature: {name}",
        "",
        f"## Description",
        description or "No description provided.",
        "",
    ]

    if endpoints:
        lines.append("## API Endpoints")
        lines.append("")
        for ep in endpoints:
            method = ep.get("method", "GET")
            path = ep.get("path", "/")
            desc = ep.get("description", "")
            lines.append(f"- `{method} {path}` -- {desc}")
        lines.append("")

    if routes:
        lines.append("## UI Routes")
        lines.append("")
        for rt in routes:
            path = rt.get("path", "/")
            rname = rt.get("name", "")
            desc = rt.get("description", "")
            lines.append(f"- `{path}` ({rname}) -- {desc}")
        lines.append("")

    if acceptance:
        lines.append("## Acceptance Criteria")
        lines.append("")
        for criterion in acceptance:
            lines.append(f"- {criterion}")
        lines.append("")

    lines.extend([
        "## Technical Requirements",
        "",
        "- Backend: FastAPI + MongoDB (Motor async driver)",
        "- Frontend: React 19 + TypeScript + Zustand + Axios + Tailwind CSS",
        f"- Backend port: {config.ports.backend}",
        f"- Frontend port: {config.ports.frontend}",
        f"- MongoDB port: {config.ports.mongodb}",
        "- All API calls go through Zustand stores (never direct from components)",
        "- Service layer pattern in backend (BaseService with CRUD)",
        "- Pydantic v2 schemas for all request/response models",
        "- Include unit tests for all new code",
        "- No TODOs, no stubs, no placeholder implementations",
        "",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for ``python -m src.pipeline``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="NC Dev System Pipeline -- autonomous project builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m src.pipeline requirements.md\n"
            "  python -m src.pipeline requirements.md -o ./my-project --phases 1,2\n"
            "  python -m src.pipeline requirements.md --project-name my-app\n"
        ),
    )

    parser.add_argument(
        "requirements",
        help="Path to the requirements markdown file",
    )
    parser.add_argument(
        "--output", "-o",
        default="./output",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--phases",
        default="1,2,3,4,5,6",
        help="Comma-separated phases to run (default: 1,2,3,4,5,6)",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help="Override project name (auto-detected from requirements if omitted)",
    )

    args = parser.parse_args()

    # Validate requirements file exists before constructing the pipeline.
    req_path = Path(args.requirements)
    if not req_path.exists():
        console.print(f"[bold red]Error:[/bold red] Requirements file not found: {req_path}")
        sys.exit(1)

    # Parse phases
    try:
        phases = [int(p.strip()) for p in args.phases.split(",") if p.strip()]
        for p in phases:
            if p < 1 or p > 6:
                console.print(f"[bold red]Error:[/bold red] Invalid phase number: {p} (must be 1-6)")
                sys.exit(1)
    except ValueError:
        console.print(f"[bold red]Error:[/bold red] Invalid phases format: {args.phases}")
        sys.exit(1)

    config = Config(
        output_dir=Path(args.output),
        phases=sorted(set(phases)),
    )
    if args.project_name:
        config.project_name = args.project_name

    pipeline = Pipeline(config)
    result = asyncio.run(pipeline.run(str(req_path)))

    if result.get("success"):
        console.print("[bold green]Pipeline completed successfully![/bold green]")
    else:
        console.print("[bold red]Pipeline failed.[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
