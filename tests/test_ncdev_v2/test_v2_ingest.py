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


def test_ingest_directory_bundle_reads_nonstandard_markdown_names(tmp_path: Path) -> None:
    docs = tmp_path / "planning"
    docs.mkdir()
    (docs / "01-PROBLEM-STATEMENT.md").write_text(
        "# Problem\n\n1. Authentication\n2. Authorization\n",
        encoding="utf-8",
    )
    ingested = ingest_source(str(docs))
    assert "Authentication" in ingested.content


def test_ingest_markdown_file_expands_local_links(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    linked = root / "details.md"
    linked.write_text("- User can manage invoices\n", encoding="utf-8")
    readme = root / "README.md"
    readme.write_text("# Docs\n\nSee [details](./details.md)\n", encoding="utf-8")

    ingested = ingest_source(str(readme))

    assert "User can manage invoices" in ingested.content
    assert any("Expanded" in note for note in ingested.notes)
