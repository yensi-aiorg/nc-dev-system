from pathlib import Path

from ncdev.v2.engine import run_v2_discovery


def test_v2_discovery_writes_contract_artifacts(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
- User can manage projects
- User can review evidence
""".strip(),
        encoding="utf-8",
    )
    state = run_v2_discovery(tmp_path, req, dry_run=True)
    run_dir = Path(state.run_dir)
    assert state.status.value == "passed"
    assert (run_dir / "run-state.json").exists()
    assert (run_dir / "outputs" / "source-pack.json").exists()
    assert (run_dir / "outputs" / "research-pack.json").exists()
    assert (run_dir / "outputs" / "feature-map.json").exists()
    assert (run_dir / "outputs" / "design-pack.json").exists()
    assert (run_dir / "outputs" / "build-plan.json").exists()
    assert (run_dir / "outputs" / "target-project-contract.json").exists()
    assert (run_dir / "outputs" / "scaffold-plan.json").exists()
    assert (run_dir / "outputs" / "capability-snapshot.json").exists()
    assert (run_dir / "outputs" / "routing-plan.json").exists()
    assert (run_dir / "outputs" / "execution-log.json").exists()
