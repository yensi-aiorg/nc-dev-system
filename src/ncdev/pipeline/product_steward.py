"""Product Steward — the whole-product UX coherence agent.

Runs at coherence checkpoints (end-of-slice, end-of-run, on feature
failure) and decides what the factory should do next: continue,
repair, replan, or stop.

This is the role that holds the entire feature queue + current repo
state + TestCraftr findings in one head and asks "is this product
done from a user's perspective." It is deliberately a single Claude
session (not a pipeline phase) so stronger reasoning models improve
it directly.
"""
from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import DEFAULT_PLAN_TOOLS, ClaudeSessionResult
from ncdev.core.config import NCDevConfig
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureStep,
    StepResult,
)


class Disposition(str, Enum):
    """What the Steward decided the factory should do next."""

    CONTINUE = "continue"
    REPAIR_CURRENT_SLICE = "repair_current_slice"
    INSERT_FEATURES = "insert_features"
    REWRITE_ACCEPTANCE = "rewrite_acceptance"
    RERUN_CHARTER = "rerun_charter"
    STOP_AS_UNRECOVERABLE = "stop_as_unrecoverable"


class FeatureAmendment(BaseModel):
    feature_id: str
    field: str
    new_value: Any
    reason: str


class StewardDecision(BaseModel):
    disposition: Disposition
    reasoning: str
    target_feature_ids: list[str] = Field(default_factory=list)
    new_features: list[FeatureStep] = Field(default_factory=list)
    amendments: list[FeatureAmendment] = Field(default_factory=list)


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_steward_response(text: str) -> StewardDecision:
    """Parse the Steward's JSON response. Tolerates markdown fences."""
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    data = json.loads(cleaned)
    return StewardDecision.model_validate(data)
