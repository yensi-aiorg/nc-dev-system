from __future__ import annotations

import re
from collections import Counter

from ncdev.models import ConsensusDoc, ModelAssessment


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tokenize(text: str) -> Counter[str]:
    return Counter(TOKEN_RE.findall(text.lower()))


def agreement_score(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta and not tb:
        return 1.0
    intersection = sum((ta & tb).values())
    union = sum((ta | tb).values())
    if union == 0:
        return 0.0
    return intersection / union


def adjudicate(assessments: list[ModelAssessment], min_score: float, min_model_confidence: float) -> ConsensusDoc:
    if len(assessments) < 2:
        return ConsensusDoc(
            decision="blocked",
            agreement_score=0.0,
            merged_output="",
            conflicts=["Dual-model requirement not met."],
            requires_human=True,
        )

    by_model = {a.model: a for a in assessments}
    failures = [a for a in assessments if a.status != "ok"]
    if failures:
        return ConsensusDoc(
            decision="blocked",
            agreement_score=0.0,
            merged_output="",
            conflicts=[f"{f.model} failed: {f.error or 'unknown error'}" for f in failures],
            requires_human=True,
        )

    low_confidence = [a for a in assessments if a.confidence < min_model_confidence]
    if low_confidence:
        return ConsensusDoc(
            decision="blocked",
            agreement_score=0.0,
            merged_output="",
            conflicts=[
                f"{a.model} confidence {a.confidence:.2f} below minimum {min_model_confidence:.2f}"
                for a in low_confidence
            ],
            requires_human=True,
        )

    model_names = sorted(by_model.keys())
    first, second = by_model[model_names[0]], by_model[model_names[1]]
    score = agreement_score(first.output, second.output)

    merged = first.output if first.confidence >= second.confidence else second.output
    conflicts: list[str] = []
    decision = "approved"
    requires_human = False

    if score < min_score:
        decision = "blocked"
        requires_human = True
        conflicts.append(
            f"Agreement score {score:.3f} below threshold {min_score:.3f}."
        )

    return ConsensusDoc(
        decision=decision,
        agreement_score=score,
        merged_output=merged,
        conflicts=conflicts,
        requires_human=requires_human,
    )
