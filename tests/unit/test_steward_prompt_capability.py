from pathlib import Path

import ncdev.pipeline.product_steward as _ps_module


def test_steward_prompt_template_requests_capability_lessons():
    src = Path(_ps_module.__file__).read_text(encoding="utf-8")
    # The JSON schema the Steward must return now includes the field...
    assert '"capability_lessons"' in src
    # ...and the prompt explains what to put there.
    assert "Capability lessons" in src
