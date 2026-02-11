"""AI-powered visual analysis of screenshots.

Implements a two-tier strategy:

1. **Ollama Qwen2.5-VL** (fast, free, local) -- used as the first pass.
2. **Claude Vision** (via the ``claude`` CLI) -- escalation when local
   confidence is low or critical issues are detected.

Both analysers produce :class:`VisionResult` instances that are consumed
by :mod:`src.tester.runner` and :mod:`src.tester.results`.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Optional

import httpx
from rich.console import Console

from .results import VisionIssue, VisionResult

console = Console()

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_ANALYSIS_PROMPT = textwrap.dedent("""\
    You are a senior UI/UX quality-assurance engineer.  Analyse the
    provided screenshot of a web application and report any visual issues.

    Check for:
    - Layout problems (overlapping elements, overflow, misalignment)
    - Broken or missing images / icons
    - Illegible or truncated text
    - Inconsistent spacing or padding
    - Responsive design issues for the current viewport
    - Colour contrast or accessibility concerns
    - Missing interactive affordances (buttons that don't look clickable)
    - Empty states that look broken rather than intentional

    {context}

    Respond ONLY with a JSON object (no markdown fencing) with this schema:
    {{
        "passed": true/false,
        "confidence": 0.0-1.0,
        "issues": [
            {{
                "severity": "critical" | "warning" | "info",
                "description": "...",
                "element": "CSS selector or description",
                "suggestion": "..."
            }}
        ],
        "suggestions": ["general improvement suggestion", ...]
    }}
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_image_base64(path: Path) -> str:
    """Read an image file and return its base64-encoded content."""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Best-effort extraction of the first JSON object from *raw*.

    LLM responses sometimes include markdown fences or preamble text; this
    helper strips those away before parsing.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = cleaned.strip().rstrip("`").strip()

    # Try parsing the entire cleaned string first
    try:
        return json.loads(cleaned)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass

    # Fallback: find the first { ... } block
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            return json.loads(match.group(0))  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    # If we cannot parse at all, return a failure-indicating dict
    return {
        "passed": False,
        "confidence": 0.0,
        "issues": [
            {
                "severity": "warning",
                "description": "Vision analyser returned unparseable output",
                "element": "",
                "suggestion": "Manually inspect the screenshot",
            }
        ],
        "suggestions": [],
    }


def _dict_to_vision_result(
    data: dict[str, Any],
    screenshot_path: Path,
    analyzer: str,
    route: str = "",
    viewport: str = "",
) -> VisionResult:
    """Convert a parsed JSON dict into a :class:`VisionResult`."""
    issues: list[VisionIssue] = []
    for raw_issue in data.get("issues", []):
        issues.append(
            VisionIssue(
                severity=raw_issue.get("severity", "warning"),
                description=raw_issue.get("description", "Unknown issue"),
                element=raw_issue.get("element", ""),
                suggestion=raw_issue.get("suggestion", ""),
            )
        )

    return VisionResult(
        screenshot_path=str(screenshot_path),
        route=route,
        viewport=viewport,
        passed=bool(data.get("passed", len(issues) == 0)),
        confidence=float(data.get("confidence", 0.5)),
        issues=issues,
        suggestions=list(data.get("suggestions", [])),
        analyzer=analyzer,
        raw_response=json.dumps(data, indent=2),
    )


# ---------------------------------------------------------------------------
# VisionAnalyzer
# ---------------------------------------------------------------------------

class VisionAnalyzer:
    """Two-tier visual analysis: Ollama (fast/free) then Claude (accurate).

    Parameters
    ----------
    ollama_url:
        Base URL of the local Ollama instance.
    ollama_model:
        Model tag for the vision-capable Ollama model.
    confidence_threshold:
        If the Ollama confidence falls below this value, or if critical
        issues are found, the screenshot is escalated to Claude Vision.
    claude_model:
        Claude model to use for escalation (via the ``claude`` CLI).
    timeout_seconds:
        Per-request timeout for HTTP and subprocess calls.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5vl:7b",
        *,
        confidence_threshold: float = 0.7,
        claude_model: str = "sonnet",
        timeout_seconds: int = 120,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model
        self.confidence_threshold = confidence_threshold
        self.claude_model = claude_model
        self.timeout_seconds = timeout_seconds

    # -- Public API ----------------------------------------------------------

    async def analyze_screenshot(
        self,
        screenshot_path: Path,
        context: str = "",
        *,
        route: str = "",
        viewport: str = "",
    ) -> VisionResult:
        """Analyse a single screenshot using the two-tier strategy.

        1. Run local Ollama vision model.
        2. If confidence < threshold or critical issues detected, escalate
           to Claude Vision for a second opinion.
        """
        screenshot_path = Path(screenshot_path)
        if not screenshot_path.exists():
            return VisionResult(
                screenshot_path=str(screenshot_path),
                route=route,
                viewport=viewport,
                passed=False,
                confidence=0.0,
                issues=[
                    VisionIssue(
                        severity="critical",
                        description=f"Screenshot file not found: {screenshot_path}",
                    )
                ],
                analyzer="none",
            )

        # Tier 1: Ollama
        result = await self._ollama_analyze(screenshot_path, context, route=route, viewport=viewport)

        needs_escalation = (
            result.confidence < self.confidence_threshold
            or any(issue.severity == "critical" for issue in result.issues)
        )

        if needs_escalation:
            console.print(
                f"[yellow]Escalating to Claude Vision "
                f"(confidence={result.confidence:.2f}, "
                f"issues={len(result.issues)})[/yellow]"
            )
            result = await self._claude_analyze(
                screenshot_path, context, result, route=route, viewport=viewport,
            )

        return result

    async def analyze_batch(
        self,
        screenshots: dict[str, dict[str, Path]],
        context: str = "",
        *,
        concurrency: int = 2,
    ) -> list[VisionResult]:
        """Analyse multiple screenshots with bounded concurrency.

        Parameters
        ----------
        screenshots:
            Mapping of ``{route: {viewport_name: path}}``.
        """
        semaphore = asyncio.Semaphore(concurrency)
        results: list[VisionResult] = []

        async def _run(route: str, vp_name: str, path: Path) -> VisionResult:
            async with semaphore:
                return await self.analyze_screenshot(
                    path,
                    context=context,
                    route=route,
                    viewport=vp_name,
                )

        tasks = [
            asyncio.create_task(_run(route, vp_name, path))
            for route, viewports in screenshots.items()
            for vp_name, path in viewports.items()
        ]

        for coro in asyncio.as_completed(tasks):
            results.append(await coro)

        return results

    # -- Ollama tier ---------------------------------------------------------

    async def _ollama_analyze(
        self,
        path: Path,
        context: str,
        *,
        route: str = "",
        viewport: str = "",
    ) -> VisionResult:
        """Run vision analysis via the local Ollama API.

        POST /api/generate with a base64-encoded image.
        """
        image_b64 = _encode_image_base64(path)
        prompt = _ANALYSIS_PROMPT.format(
            context=f"Additional context: {context}" if context else ""
        )

        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 2048,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()
                raw_text: str = body.get("response", "")

            parsed = _parse_json_response(raw_text)
            result = _dict_to_vision_result(parsed, path, analyzer="ollama", route=route, viewport=viewport)
            console.print(
                f"[dim]Ollama analysis of {path.name}: "
                f"passed={result.passed}, confidence={result.confidence:.2f}, "
                f"issues={len(result.issues)}[/dim]"
            )
            return result

        except (httpx.HTTPError, httpx.TimeoutException, ConnectionError) as exc:
            console.print(f"[yellow]Ollama unavailable ({exc.__class__.__name__}), will escalate to Claude.[/yellow]")
            return VisionResult(
                screenshot_path=str(path),
                route=route,
                viewport=viewport,
                passed=False,
                confidence=0.0,
                issues=[
                    VisionIssue(
                        severity="warning",
                        description=f"Ollama analysis failed: {exc}",
                        suggestion="Ensure Ollama is running with the vision model loaded.",
                    )
                ],
                analyzer="ollama",
                raw_response=str(exc),
            )

    # -- Claude tier ---------------------------------------------------------

    async def _claude_analyze(
        self,
        path: Path,
        context: str,
        pre_result: VisionResult,
        *,
        route: str = "",
        viewport: str = "",
    ) -> VisionResult:
        """Escalate to Claude Vision via the ``claude`` CLI.

        The prompt includes a summary of the Ollama pre-screening so Claude
        can focus on confirming or refuting the preliminary findings.
        """
        pre_issues_text = ""
        if pre_result.issues:
            items = "\n".join(
                f"  - [{iss.severity}] {iss.description}" for iss in pre_result.issues
            )
            pre_issues_text = (
                f"\nA preliminary local analysis flagged these potential issues:\n{items}\n"
                "Please confirm or refute each one and add any issues that were missed."
            )

        prompt = _ANALYSIS_PROMPT.format(
            context=(
                f"Additional context: {context}\n{pre_issues_text}"
                if context
                else pre_issues_text
            )
        )

        try:
            result = await self._run_claude_cli(path, prompt, route=route, viewport=viewport)
            console.print(
                f"[dim]Claude analysis of {path.name}: "
                f"passed={result.passed}, confidence={result.confidence:.2f}, "
                f"issues={len(result.issues)}[/dim]"
            )
            return result

        except Exception as exc:
            console.print(f"[red]Claude Vision analysis failed: {exc}[/red]")
            # Fall back to the Ollama result rather than losing information
            return VisionResult(
                screenshot_path=str(path),
                route=route,
                viewport=viewport,
                passed=pre_result.passed,
                confidence=pre_result.confidence,
                issues=pre_result.issues,
                suggestions=pre_result.suggestions + [
                    f"Claude escalation failed ({exc}); showing Ollama results instead."
                ],
                analyzer="ollama+claude-fallback",
                raw_response=pre_result.raw_response,
            )

    async def _run_claude_cli(
        self,
        image_path: Path,
        prompt: str,
        *,
        route: str = "",
        viewport: str = "",
    ) -> VisionResult:
        """Invoke the ``claude`` CLI with an image attachment.

        Usage:
            echo "<prompt>" | claude --model sonnet --image <path> -p
        """
        # Write the prompt to a temporary file to avoid shell-escaping issues
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="nc_vision_"
        ) as tmp:
            tmp.write(prompt)
            prompt_file = Path(tmp.name)

        try:
            proc = await asyncio.create_subprocess_exec(
                "claude",
                "--model",
                self.claude_model,
                "--image",
                str(image_path),
                "-p",
                prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout_seconds,
            )
        finally:
            prompt_file.unlink(missing_ok=True)

        if proc.returncode != 0:
            error_text = stderr.decode().strip() or stdout.decode().strip()
            raise RuntimeError(f"claude CLI returned exit code {proc.returncode}: {error_text}")

        raw_text = stdout.decode().strip()
        parsed = _parse_json_response(raw_text)
        return _dict_to_vision_result(parsed, image_path, analyzer="claude", route=route, viewport=viewport)
