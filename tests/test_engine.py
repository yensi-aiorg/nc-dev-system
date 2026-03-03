from pathlib import Path

from ncdev.engine import run_brownfield, run_greenfield


def test_greenfield_analysis_writes_outputs(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text("""
# App
- User can sign in
- User can view dashboard
""", encoding="utf-8")

    state = run_greenfield(
        workspace=tmp_path,
        requirements_path=req,
        dry_run=True,
        full=False,
        command="build",
    )

    run_dir = Path(state.run_dir)
    assert (run_dir / "run-state.json").exists()
    assert (run_dir / "outputs" / "features.json").exists()
    assert (run_dir / "outputs" / "architecture.json").exists()
    assert (run_dir / "outputs" / "test-plan.json").exists()
    assert (run_dir / "outputs" / "consensus.json").exists()


def test_brownfield_analysis_writes_outputs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "package.json").write_text("{}", encoding="utf-8")
    (repo / "main.py").write_text("print('ok')\n", encoding="utf-8")

    state = run_brownfield(
        workspace=tmp_path,
        repo_path=repo,
        include_paths=[],
        exclude_paths=[".git"],
        dry_run=True,
        full=False,
        command="analyze",
    )

    run_dir = Path(state.run_dir)
    assert (run_dir / "outputs" / "repo-inventory.json").exists()
    assert (run_dir / "outputs" / "risk-map.json").exists()
    assert (run_dir / "outputs" / "change-plan.json").exists()
    assert (run_dir / "outputs" / "consensus.json").exists()


def test_greenfield_full_pipeline_dry_run(tmp_path: Path) -> None:
    # Minimal templates required by scaffolder.
    template_base = tmp_path / "templates" / "greenfield"
    (template_base / "backend" / "app" / "api" / "v1").mkdir(parents=True, exist_ok=True)
    (template_base / "frontend" / "src").mkdir(parents=True, exist_ok=True)
    (template_base / "README.md.j2").write_text("# {{ project_name }}", encoding="utf-8")
    (template_base / "docker-compose.yml.j2").write_text("services: {}", encoding="utf-8")
    (template_base / "backend" / "requirements.txt.j2").write_text("fastapi", encoding="utf-8")
    (template_base / "backend" / "app" / "main.py.j2").write_text("print('x')", encoding="utf-8")
    (template_base / "backend" / "app" / "api" / "v1" / "router.py.j2").write_text("x=1", encoding="utf-8")
    (template_base / "frontend" / "package.json.j2").write_text("{}", encoding="utf-8")
    (template_base / "frontend" / "src" / "main.tsx.j2").write_text("x", encoding="utf-8")
    (template_base / "frontend" / "src" / "App.tsx.j2").write_text("x", encoding="utf-8")
    (template_base / "playwright.config.ts.j2").write_text("x", encoding="utf-8")

    req = tmp_path / "requirements.md"
    req.write_text("- Feature A", encoding="utf-8")
    state = run_greenfield(tmp_path, req, dry_run=True, full=True, command="build")
    run_dir = Path(state.run_dir)
    assert state.status.value == "passed"
    assert (run_dir / "outputs" / "scaffolding-manifest.json").exists()
    assert (run_dir / "outputs" / "build-result.json").exists()
    assert (run_dir / "outputs" / "test-result.json").exists()
    assert (run_dir / "outputs" / "harden-report.json").exists()
    assert (run_dir / "outputs" / "delivery-report.json").exists()
