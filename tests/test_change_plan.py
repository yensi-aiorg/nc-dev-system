from ncdev.analysis.discovery import build_change_plan
from ncdev.models import RepoInventoryDoc, RiskMapDoc


def test_change_plan_noop_when_no_risks_and_hotspots() -> None:
    inventory = RepoInventoryDoc(repo_path="/tmp/repo", hotspots=[])
    risk_map = RiskMapDoc(risks=[])
    plan = build_change_plan(inventory, risk_map)
    assert len(plan.batches) == 1
    assert plan.batches[0].id == "batch-000"
