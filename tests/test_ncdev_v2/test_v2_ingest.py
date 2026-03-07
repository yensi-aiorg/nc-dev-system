from pathlib import Path

from ncdev.discovery.ingest import ingest_source
from ncdev.v2.engine import run_v2_discovery


def test_ingest_repository_directory_collects_project_files(tmp_path: Path) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "README.md").write_text("# Demo Repo\n\n- User can sign in\n", encoding="utf-8")
    (repo / "package.json").write_text('{"name":"demo"}', encoding="utf-8")

    ingested = ingest_source(str(repo))
    assert ingested.source_kind == "repo_directory"
    assert ingested.project_name == "demo-repo"
    assert "User can sign in" in ingested.content
    assert len(ingested.assets) >= 1


def test_v2_discovery_accepts_repository_directory_input(tmp_path: Path) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "README.md").write_text("# Demo Repo\n\n- User can sign in\n- User can view dashboard\n", encoding="utf-8")
    state = run_v2_discovery(tmp_path, repo, dry_run=True)
    run_dir = Path(state.run_dir)
    source_pack = (run_dir / "outputs" / "source-pack.json").read_text(encoding="utf-8")
    assert '"source_kind": "repo_directory"' in source_pack
