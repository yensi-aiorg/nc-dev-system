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


def test_bugfix_steering_block_names_systematic_debugging():
    block = render_skill_block(
        select_skills("bugfix", ["systematic-debugging", "test-driven-development"])
    )
    assert "systematic-debugging" in block


def test_select_skills_drops_skill_flagged_hurt():
    lessons = ["frontend-design hurt — produced inconsistent layouts"]
    picked = select_skills("greenfield_ui", INVENTORY, lessons=lessons)
    assert "frontend-design" not in picked
    assert "test-driven-development" in picked  # unaffected skills remain


def test_select_skills_ignores_lessons_without_hurt():
    lessons = ["frontend-design helped a lot"]
    picked = select_skills("greenfield_ui", INVENTORY, lessons=lessons)
    assert "frontend-design" in picked  # "helped" is advisory, not forced


def test_select_skills_no_lessons_is_phase1_behaviour():
    assert select_skills("bugfix", INVENTORY) == select_skills(
        "bugfix", INVENTORY, lessons=None
    )
