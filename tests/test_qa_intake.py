import json
from pathlib import Path

from ncdev.qa_intake import import_manual_qa_report, list_manual_qa_imports, update_manual_qa_status


def test_import_manual_qa_report_creates_durable_intake(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    report = tmp_path / "report.md"
    report.write_text("# QA\n\n### P1 - Login broken\n\nActual: 405")

    item = import_manual_qa_report(
        workspace=tmp_path,
        report_path=report,
        target_repo=target,
        project="Keeper",
        base_url="https://keeper.yensi.solutions",
    )

    metadata = json.loads(Path(item.metadata_path).read_text())
    assert item.status == "queued"
    assert metadata["project"] == "Keeper"
    assert metadata["target_repo"] == str(target.resolve())
    assert metadata["base_url"] == "https://keeper.yensi.solutions"
    assert Path(item.report_copy).read_text() == report.read_text()
    assert "P1 - Login broken" in Path(item.fix_task_path).read_text()


def test_list_manual_qa_imports_filters_by_project(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    report = tmp_path / "report.md"
    report.write_text("# QA")

    import_manual_qa_report(
        workspace=tmp_path,
        report_path=report,
        target_repo=target,
        project="Keeper",
    )
    import_manual_qa_report(
        workspace=tmp_path,
        report_path=report,
        target_repo=target,
        project="Other",
    )

    keeper_imports = list_manual_qa_imports(workspace=tmp_path, project="Keeper")
    all_imports = list_manual_qa_imports(workspace=tmp_path)

    assert len(keeper_imports) == 1
    assert keeper_imports[0]["project"] == "Keeper"
    assert len(all_imports) == 2


def test_update_manual_qa_status_adds_note(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    report = tmp_path / "report.md"
    report.write_text("# QA")
    item = import_manual_qa_report(
        workspace=tmp_path,
        report_path=report,
        target_repo=target,
        project="Keeper",
    )

    metadata = update_manual_qa_status(
        workspace=tmp_path,
        project="Keeper",
        run_id=item.run_id,
        status="fixed",
        note="Build and targeted QA passed.",
    )

    assert metadata["status"] == "fixed"
    assert metadata["notes"][0]["note"] == "Build and targeted QA passed."
