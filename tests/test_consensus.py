from ncdev.analysis.consensus import agreement_score, adjudicate
from ncdev.models import ModelAssessment


def test_agreement_score_in_range() -> None:
    score = agreement_score("alpha beta", "alpha gamma")
    assert 0.0 <= score <= 1.0


def test_adjudicate_blocks_on_failed_model() -> None:
    assessments = [
        ModelAssessment(task_id="analysis", model="claude_cli", input_digest="x", output="ok", status="ok", confidence=0.8),
        ModelAssessment(
            task_id="analysis",
            model="codex_cli",
            input_digest="x",
            output="",
            status="failed",
            confidence=0.0,
            error="boom",
        ),
    ]
    result = adjudicate(assessments, 0.6, 0.55)
    assert result.decision == "blocked"
    assert result.requires_human is True
