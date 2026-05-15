import json

from ncdev.pipeline.product_steward import (
    Disposition,
    StewardDecision,
    parse_steward_response,
)


def test_disposition_enum_values():
    assert Disposition.CONTINUE.value == "continue"
    assert Disposition.REPAIR_CURRENT_SLICE.value == "repair_current_slice"
    assert Disposition.INSERT_FEATURES.value == "insert_features"
    assert Disposition.REWRITE_ACCEPTANCE.value == "rewrite_acceptance"
    assert Disposition.RERUN_CHARTER.value == "rerun_charter"
    assert Disposition.STOP_AS_UNRECOVERABLE.value == "stop_as_unrecoverable"


def test_parse_steward_response_happy_path():
    payload = json.dumps({
        "disposition": "repair_current_slice",
        "reasoning": "f02-auth left the dashboard route 500ing",
        "target_feature_ids": ["f02-auth"],
        "new_features": [],
        "amendments": [],
    })
    decision = parse_steward_response(payload)
    assert decision.disposition == Disposition.REPAIR_CURRENT_SLICE
    assert decision.target_feature_ids == ["f02-auth"]


def test_parse_steward_response_strips_markdown_fences():
    payload = "```json\n" + json.dumps({
        "disposition": "continue",
        "reasoning": "looking good",
    }) + "\n```"
    decision = parse_steward_response(payload)
    assert decision.disposition == Disposition.CONTINUE


def test_parse_steward_response_invalid_disposition_raises():
    import pytest

    with pytest.raises(ValueError):
        parse_steward_response(json.dumps({
            "disposition": "yolo",
            "reasoning": "n/a",
        }))
