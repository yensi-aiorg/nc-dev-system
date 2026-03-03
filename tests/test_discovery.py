from pathlib import Path

from ncdev.analysis.discovery import discover_repo


def test_discover_repo_monorepo_and_hotspots(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (repo / "apps" / "api").mkdir(parents=True, exist_ok=True)
    (repo / "apps" / "web" / "package.json").write_text("{}", encoding="utf-8")
    (repo / "apps" / "api" / "package.json").write_text("{}", encoding="utf-8")

    inv = discover_repo(repo)
    assert inv.monorepo is True
    assert len(inv.package_roots) >= 2
    assert "monorepo-cross-package-change-risk" in inv.hotspots
