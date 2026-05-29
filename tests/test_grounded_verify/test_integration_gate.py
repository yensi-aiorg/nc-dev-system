# tests/test_grounded_verify/test_integration_gate.py
"""Tests for the product-level integration gate prompt builder (Task 2)."""
from ncdev.pipeline.grounded_verify.models import EvidenceBundle, EvidenceItem


def test_integration_prompt_has_intent_evidence_and_rules():
    from ncdev.pipeline.grounded_verify.integration import build_integration_prompt

    ev = EvidenceBundle(
        items=[
            EvidenceItem(name="route:/health", exit_code=0, scope="route"),
            EvidenceItem(name="build", command="docker compose build", exit_code=0, scope="build"),
        ],
        changed_files=[],
    )
    p = build_integration_prompt("Echo service: /health + /api/v1/echo", ev, ["f01", "f02"])
    assert "intent" in p.lower() and ("not exact" in p.lower() or "alternate path" in p.lower())
    assert "route:/health" in p and "```json" in p
