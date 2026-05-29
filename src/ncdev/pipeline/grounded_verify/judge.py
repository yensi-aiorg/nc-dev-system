# src/ncdev/pipeline/grounded_verify/judge.py
"""Agent judgment over gathered evidence (Opus 4.8), fenced-JSON + retry."""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from ncdev.pipeline.grounded_verify.models import Verdict

_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE = re.compile(r"\{.*\}", re.DOTALL)


def parse_verdict(text: str) -> Verdict | None:
    """Pull a Verdict out of an LLM response, or None if absent/invalid."""
    m = _FENCED.search(text) or _BARE.search(text)
    if not m:
        return None
    candidate = m.group(1) if m.re is _FENCED else m.group(0)
    try:
        data = json.loads(candidate)
        return Verdict.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        return None
