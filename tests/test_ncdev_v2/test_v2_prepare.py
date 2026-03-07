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
    assert verification_contract["healthcheck_path"] == "/"
    assert verification_contract["startup_timeout_seconds"] == 45
    assert verification_contract["required_viewports"] == ["desktop", "mobile"]
    assert "frontend/e2e/screenshots" in verification_contract["evidence_paths"]
    assert "frontend/playwright-report" in verification_contract["evidence_paths"]
    assert state.metadata["job_count"] >= 3


def test_v2_prepare_can_target_existing_repo(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text("# Product\n- User can sign in\n", encoding="utf-8")
    repo = tmp_path / "target-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "frontend").mkdir()
    (repo / "frontend" / "package.json").write_text('{"name":"target","scripts":{"test":"vitest"}}', encoding="utf-8")
    (repo / "frontend" / "playwright.config.ts").write_text("export default {}", encoding="utf-8")
    (repo / "backend").mkdir()
    (repo / "backend" / "pyproject.toml").write_text("[project]\nname='target'\n", encoding="utf-8")

    state = run_v2_prepare(tmp_path, req, dry_run=True, target_repo_path=repo)
    run_dir = Path(state.run_dir)
    manifest = json.loads((run_dir / "outputs" / "scaffold-manifest.json").read_text(encoding="utf-8"))

    assert manifest["target_path"] == str(repo)
    assert manifest["existing_repo"] is True
    assert manifest["scaffold_applied"] is False
    assert (repo / "docs" / "evidence" / "README.md").exists()
    assert (repo / "frontend" / "e2e" / "screenshots" / ".gitkeep").exists()
