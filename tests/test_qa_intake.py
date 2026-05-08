import json
from pathlib import Path

import pytest

from ncdev.qa_intake import (
    ManualQAImport,
    import_manual_qa_report,
    import_to_dict,
    list_manual_qa_imports,
    update_manual_qa_status,
)


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


def test_import_manual_qa_report_rejects_missing_report(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    with pytest.raises(FileNotFoundError, match="QA report not found"):
        import_manual_qa_report(
            workspace=tmp_path,
            report_path=tmp_path / "missing.md",
            target_repo=target,
        )


def test_import_manual_qa_report_rejects_missing_target(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("# QA")
    with pytest.raises(FileNotFoundError, match="Target repo not found"):
        import_manual_qa_report(
            workspace=tmp_path,
            report_path=report,
            target_repo=tmp_path / "missing",
        )


def test_list_manual_qa_imports_empty_workspace(tmp_path: Path) -> None:
    assert list_manual_qa_imports(workspace=tmp_path) == []


def test_list_manual_qa_imports_filters_unknown_project(tmp_path: Path) -> None:
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
    assert list_manual_qa_imports(workspace=tmp_path, project="Phantom") == []


def test_list_manual_qa_imports_handles_corrupt_metadata(tmp_path: Path) -> None:
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
    Path(item.metadata_path).write_text("{ not valid json }")

    imports = list_manual_qa_imports(workspace=tmp_path, project="Keeper")
    assert len(imports) == 1
    assert imports[0]["status"] == "corrupt"


def test_update_manual_qa_status_raises_on_missing_intake(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Manual QA intake not found"):
        update_manual_qa_status(
            workspace=tmp_path,
            project="Phantom",
            run_id="never-existed",
            status="fixed",
        )


def test_update_manual_qa_status_without_note_does_not_create_notes_field(tmp_path: Path) -> None:
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
        status="in_progress",
    )
    assert metadata["status"] == "in_progress"
    assert "notes" not in metadata


def test_import_to_dict_round_trips_dataclass() -> None:
    item = ManualQAImport(
        project="X",
        run_id="r",
        status="queued",
        report_copy="/r.md",
        metadata_path="/m.json",
        fix_task_path="/f.md",
    )
    assert import_to_dict(item) == {
        "project": "X",
        "run_id": "r",
        "status": "queued",
        "report_copy": "/r.md",
        "metadata_path": "/m.json",
        "fix_task_path": "/f.md",
    }
