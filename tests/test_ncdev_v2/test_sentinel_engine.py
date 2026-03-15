from __future__ import annotations

import json
from pathlib import Path

import pytest

from ncdev.v2.engine import run_v2_fix
from ncdev.v2.models import V2Phase, V2TaskStatus

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sentinel_reports"


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


class TestRunV2FixDryRun:
    def test_loads_report_and_populates_metadata(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        report_path = FIXTURES / "backend_error.json"
        state = run_v2_fix(
            workspace=ws,
            report_path=report_path,
            target_repo_path=tmp_path / "target",
            dry_run=True,
            run_id="test-fix-001",
        )
        assert state.metadata["mode"] == "sentinel-fix"
        assert state.metadata["report_id"] == "rpt_bk_001"
        assert state.metadata["service_name"] == "helyx-api"
        assert state.metadata["git_sha"] == "a1b2c3d4e5f6"
        assert state.metadata["error_code"] == "E100"
        assert state.metadata["severity"] == "critical"
        assert state.metadata["source"] == "backend"
        assert state.metadata["attempts"] == 0
        assert state.metadata["max_attempts"] == 3
        assert state.metadata["auto_deploy"] is False
        assert "nc-dev/sentinel-fix-rpt_bk_001" == state.metadata["fix_branch"]

    def test_persists_report_artifact(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        report_path = FIXTURES / "backend_error.json"
        state = run_v2_fix(
            workspace=ws,
            report_path=report_path,
            target_repo_path=tmp_path / "target",
            dry_run=True,
            run_id="test-fix-002",
        )
        artifact_paths = [a for a in state.artifacts if "sentinel-report.json" in a]
        assert len(artifact_paths) == 1
        assert Path(artifact_paths[0]).exists()
        data = json.loads(Path(artifact_paths[0]).read_text())
        assert data["report_id"] == "rpt_bk_001"

    def test_load_report_task_passed(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        report_path = FIXTURES / "backend_error.json"
        state = run_v2_fix(
            workspace=ws,
            report_path=report_path,
            target_repo_path=tmp_path / "target",
            dry_run=True,
            run_id="test-fix-003",
        )
        load_task = next(t for t in state.tasks if t.name == "load_report")
        assert load_task.status == V2TaskStatus.PASSED

    def test_other_tasks_stay_pending(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        report_path = FIXTURES / "backend_error.json"
        state = run_v2_fix(
            workspace=ws,
            report_path=report_path,
            target_repo_path=tmp_path / "target",
            dry_run=True,
            run_id="test-fix-004",
        )
        other_names = {"checkout_version", "reproduce", "fix", "validate", "submit"}
        for task in state.tasks:
            if task.name in other_names:
                assert task.status == V2TaskStatus.PENDING, f"{task.name} should be pending"

    def test_dry_run_metadata_flag(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        report_path = FIXTURES / "backend_error.json"
        state = run_v2_fix(
            workspace=ws,
            report_path=report_path,
            target_repo_path=tmp_path / "target",
            dry_run=True,
            run_id="test-fix-005",
        )
        assert state.metadata["dry_run"] is True

    def test_frontend_report_populates_metadata(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        report_path = FIXTURES / "frontend_error.json"
        state = run_v2_fix(
            workspace=ws,
            report_path=report_path,
            target_repo_path=tmp_path / "target",
            dry_run=True,
            run_id="test-fix-006",
        )
        assert state.metadata["source"] == "frontend"
        assert state.metadata["report_id"] == "rpt_fe_001"
        assert state.metadata["service_name"] == "helyx-ui"


class TestRunV2FixInvalidReport:
    def test_invalid_json_blocks(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        bad_report = tmp_path / "bad.json"
        bad_report.write_text("not valid json {{{", encoding="utf-8")
        state = run_v2_fix(
            workspace=ws,
            report_path=bad_report,
            target_repo_path=tmp_path / "target",
            dry_run=True,
            run_id="test-fix-bad-001",
        )
        assert state.status == V2TaskStatus.BLOCKED
        assert state.phase == V2Phase.BLOCKED
        load_task = next(t for t in state.tasks if t.name == "load_report")
        assert load_task.status == V2TaskStatus.BLOCKED
        assert "invalid report" in load_task.message

    def test_invalid_schema_blocks(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        bad_report = tmp_path / "bad_schema.json"
        bad_report.write_text('{"report_id": "x"}', encoding="utf-8")
        state = run_v2_fix(
            workspace=ws,
            report_path=bad_report,
            target_repo_path=tmp_path / "target",
            dry_run=True,
            run_id="test-fix-bad-002",
        )
        assert state.status == V2TaskStatus.BLOCKED
        assert state.phase == V2Phase.BLOCKED


class TestRunV2FixMissingReport:
    def test_missing_file_blocks(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        missing = tmp_path / "nonexistent.json"
        state = run_v2_fix(
            workspace=ws,
            report_path=missing,
            target_repo_path=tmp_path / "target",
            dry_run=True,
            run_id="test-fix-missing-001",
        )
        assert state.status == V2TaskStatus.BLOCKED
        assert state.phase == V2Phase.BLOCKED
        load_task = next(t for t in state.tasks if t.name == "load_report")
        assert load_task.status == V2TaskStatus.BLOCKED
        assert "not found" in load_task.message
