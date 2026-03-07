from pathlib import Path
import json

from ncdev.v2.engine import run_v2_prepare


def test_v2_prepare_generates_target_project_and_verification_contract(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
- User can manage projects
""".strip(),
        encoding="utf-8",
    )
    state = run_v2_prepare(tmp_path, req, dry_run=True)
    run_dir = Path(state.run_dir)
    assert state.status.value == "passed"
    assert (run_dir / "outputs" / "scaffold-manifest.json").exists()
    assert (run_dir / "outputs" / "verification-contract.json").exists()
    assert (run_dir / "outputs" / "job-queue.json").exists()
    assert (run_dir / "outputs" / "jobs" / "requests" / "batch-001.json").exists()
    assert (run_dir / "outputs" / "jobs" / "requests" / "test-authoring.json").exists()
    target_root = Path(state.metadata["target_project_path"])
    assert (target_root / "frontend" / "package.json").exists()
    assert (target_root / "backend" / "pyproject.toml").exists()
    assert (target_root / "docs" / "evidence" / "README.md").exists()
    assert (target_root / "scripts" / "run-evidence-checks.sh").exists()
    verification_contract = json.loads((run_dir / "outputs" / "verification-contract.json").read_text(encoding="utf-8"))
    assert verification_contract["startup_commands"]
    assert verification_contract["teardown_commands"]
    assert verification_contract["required_viewports"] == ["desktop", "mobile"]
    assert state.metadata["job_count"] >= 3
