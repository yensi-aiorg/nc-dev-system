from __future__ import annotations

import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import re
from pathlib import Path

from ncdev.config import NCDevConfig
from ncdev.models import ModelAssessment
from ncdev.utils import sha256_text


FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _normalize_output(output: str) -> str:
    text = output.strip()
    if not text:
        return ""
    fenced = FENCED_JSON_RE.search(text)
    if fenced:
        return fenced.group(1).strip()
    return text


def _parse_structured_output(output: str) -> tuple[str, dict | None]:
    text = _normalize_output(output)
    if not text:
        return "text", None
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return "json", parsed
            return "json", {"value": parsed}
        except json.JSONDecodeError:
            return "text", None
    return "text", None


def _run_one(model_name: str, command: list[str], prompt: str, timeout_seconds: int) -> ModelAssessment:
    started = datetime.now(timezone.utc)
    rendered = [token.format(prompt=prompt) for token in command]
    digest = sha256_text(prompt)

    try:
        proc = subprocess.run(
            rendered,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        output = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        normalized_output = _normalize_output(output)
        if proc.returncode != 0:
            return ModelAssessment(
                task_id="analysis",
                model=model_name,
                input_digest=digest,
                output=normalized_output,
                confidence=0.0,
                risks=["non-zero-exit"],
                status="failed",
                error=f"command failed with exit code {proc.returncode}: {' '.join(shlex.quote(x) for x in rendered)}",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )

        confidence = 0.7
        if len(normalized_output) > 800:
            confidence = 0.85
        elif len(normalized_output) < 80:
            confidence = 0.45
        output_format, structured = _parse_structured_output(normalized_output)

        return ModelAssessment(
            task_id="analysis",
            model=model_name,
            input_digest=digest,
            output=normalized_output,
            confidence=confidence,
            output_format=output_format,
            structured_output=structured,
            risks=[],
            status="ok",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
        )
    except FileNotFoundError:
        return ModelAssessment(
            task_id="analysis",
            model=model_name,
            input_digest=digest,
            output="",
            confidence=0.0,
            risks=["command-not-found"],
            status="failed",
            error=f"command not found for model {model_name}",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
        )
    except subprocess.TimeoutExpired:
        return ModelAssessment(
            task_id="analysis",
            model=model_name,
            input_digest=digest,
            output="",
            confidence=0.0,
            risks=["timeout"],
            status="failed",
            error=f"timeout after {timeout_seconds}s for model {model_name}",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
        )


def _dry_run_assessment(model_name: str, prompt: str) -> ModelAssessment:
    now = datetime.now(timezone.utc)
    digest = sha256_text(prompt)
    return ModelAssessment(
        task_id="analysis",
        model=model_name,
        input_digest=digest,
        output=(
            f"[dry-run:{model_name}] Analysis summary for digest {digest[:12]}. "
            "Proposed direction: continue with phase-1 artifacts and consensus gating."
        ),
        confidence=0.8,
        output_format="text",
        structured_output=None,
        risks=[],
        status="ok",
        started_at=now,
        finished_at=now,
    )


def run_model_assessments(
    prompt: str,
    config: NCDevConfig,
    workspace: Path,
    dry_run: bool,
) -> list[ModelAssessment]:
    _ = workspace
    required = set(config.analysis.models_required)
    model_commands = [x for x in config.analysis.model_commands if x.name in required]

    if dry_run:
        return [_dry_run_assessment(m.name, prompt) for m in model_commands]

    assessments: list[ModelAssessment] = []
    with ThreadPoolExecutor(max_workers=max(1, len(model_commands))) as executor:
        futures = {
            executor.submit(
                _run_one,
                m.name,
                m.command,
                prompt,
                config.analysis.consensus.timeout_seconds,
            ): m.name
            for m in model_commands
        }
        for future in as_completed(futures):
            assessments.append(future.result())

    return sorted(assessments, key=lambda x: x.model)
