from ncdev.core.skill_selector import (
    render_skill_block,
    select_skills,
    work_type_for,
)


INVENTORY = [
    "systematic-debugging", "frontend-design", "test-driven-development",
    "writing-plans", "verification-before-completion", "goal",
]


def test_greenfield_ui_selects_design_skills():
    picked = select_skills("greenfield_ui", INVENTORY)
    assert "frontend-design" in picked
    assert "goal" in picked


def test_bugfix_selects_systematic_debugging():
    picked = select_skills("bugfix", INVENTORY)
    assert "systematic-debugging" in picked


def test_select_skips_skills_not_installed():
    picked = select_skills("greenfield_ui", ["test-driven-development"])
    assert picked == ["test-driven-development"]


def test_render_skill_block_names_each_skill():
    block = render_skill_block(["systematic-debugging", "writing-plans"])
    assert "systematic-debugging" in block
    assert "writing-plans" in block


def test_render_empty_block_is_empty_string():
    assert render_skill_block([]) == ""


def test_work_type_for_classifies_inputs():
    assert work_type_for(is_brownfield=True, touches_frontend=False) == "brownfield"
    assert work_type_for(is_brownfield=False, touches_frontend=True) == "greenfield_ui"
    assert work_type_for(is_brownfield=False, touches_frontend=False) == "greenfield_backend"
