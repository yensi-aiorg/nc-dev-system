from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main


def test_cli_quickstart_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["quickstart"])
    assert args.command == "quickstart"


def test_cli_doctor_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"


def test_cli_full_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["full", "--source", "/tmp/requirements.md"])
    assert args.base_url == "http://localhost:23000"
    assert args.dry_run is False
    assert args.target_repo is None
    assert args.model == "claude-opus-4-6"
    assert args.timeout == 600
    assert args.max_repairs == 2


def test_cli_full_custom_options() -> None:
    parser = build_parser()
    args = parser.parse_args([
        "full", "--source", "/tmp/requirements.md",
        "--model", "claude-sonnet-4-6", "--timeout", "900", "--max-repairs", "3",
        "--dry-run", "--target-repo", "/tmp/repo",
    ])
    assert args.model == "claude-sonnet-4-6"
    assert args.timeout == 900
    assert args.max_repairs == 3
    assert args.dry_run is True
    assert args.target_repo == "/tmp/repo"


def test_cli_dev_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["dev", "--project", "/tmp/proj", "--task", "Build feature"])
    assert args.command == "dev"
    assert args.project == "/tmp/proj"
    assert args.task == "Build feature"
    assert args.mode == "auto"


def test_cli_fix_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo"])
    assert args.command == "fix"
    assert args.report == "/tmp/rpt.json"
    assert args.target == "/tmp/repo"
    assert args.dry_run is False


def test_cli_serve_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["serve", "--port", "8080"])
    assert args.command == "serve"
    assert args.port == 8080


def test_cli_qa_import_parses(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args([
        "qa-import",
        "--report", "/tmp/qa.md",
        "--target-repo", "/tmp/repo",
        "--project", "Keeper",
        "--base-url", "https://example.com",
    ])
    assert args.command == "qa-import"
    assert args.report == "/tmp/qa.md"
    assert args.target_repo == "/tmp/repo"
    assert args.project == "Keeper"
    assert args.base_url == "https://example.com"


def test_cli_qa_monitor_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["qa-monitor", "--project", "Keeper"])
    assert args.command == "qa-monitor"
    assert args.project == "Keeper"


def test_cli_qa_update_parses() -> None:
    parser = build_parser()
    args = parser.parse_args([
        "qa-update",
        "--project", "Keeper",
        "--run-id", "manual-qa-keeper-x",
        "--status", "fixed",
        "--note", "all green",
    ])
    assert args.command == "qa-update"
    assert args.status == "fixed"
    assert args.note == "all green"


def test_cli_qa_update_rejects_unknown_status() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "qa-update",
            "--project", "Keeper",
            "--run-id", "x",
            "--status", "bogus",
        ])


def test_cli_qa_import_runs_end_to_end(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    report = tmp_path / "qa.md"
    report.write_text("# QA\n\n### P1 - Login broken")

    with patch("sys.argv", [
        "ncdev", "qa-import",
        "--report", str(report),
        "--target-repo", str(target),
        "--project", "Keeper",
        "--workspace", str(tmp_path),
    ]):
        assert main() == 0

    intake_dirs = list((tmp_path / ".nc-dev" / "manual-qa" / "keeper").glob("*"))
    assert len(intake_dirs) == 1
    assert (intake_dirs[0] / "metadata.json").exists()
    assert (intake_dirs[0] / "fix-task.md").exists()


def test_resolve_target_repo_uses_workspace_git_repo(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert _resolve_target_repo(None, tmp_path) == tmp_path


def test_resolve_target_repo_prefers_explicit_value(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    assert _resolve_target_repo(str(explicit), tmp_path) == explicit


def test_quickstart_text_mentions_full() -> None:
    text = _quickstart_text()
    assert "ncdev full" in text
    assert "ncdev dev" in text
    assert "ncdev fix" in text


def test_doctor_report_detects_git_repo(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _, report = _doctor_report(tmp_path)
    assert "git repository" in report


def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
    source = tmp_path / "requirements.md"
    source.write_text("x")
    printed: list[str] = []
    state = SimpleNamespace(
        run_id="r1",
        status="passed",
        completed_features=2,
        total_features=3,
        run_dir="/tmp/run",
    )

    with patch("ncdev.cli.run_pipeline", return_value=state):
        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
                assert main() == 0

    assert any("features: 2/3 completed" in line for line in printed)
