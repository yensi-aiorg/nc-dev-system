# src/ncdev/pipeline/grounded_verify/models.py
"""Structured contracts for the grounded verifier."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """One executed observation. Pure fact — no verdict."""
    name: str
    command: str = ""
    exit_code: int | None = None
    output_tail: str = ""
    scope: str = ""  # e.g. "feature-tests", "diff", "health", "security"


class EvidenceBundle(BaseModel):
    """Everything the harness executed and observed for one feature."""
    items: list[EvidenceItem] = Field(default_factory=list)
    diff: str = ""
    changed_files: list[str] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)


class Verdict(BaseModel):
    """The agent's grounded judgment. Single source of truth for output."""
    verdict: Literal["PASS", "FAIL"]
    confidence: float = 0.5
    reasons: list[str] = Field(default_factory=list)
    repair_guidance: list[str] = Field(default_factory=list)
    evidence_consulted: list[str] = Field(default_factory=list)


class HardFloorResult(BaseModel):
    """Outcome of the pre-LLM hard floor."""
    passed: bool
    reason: str = ""
