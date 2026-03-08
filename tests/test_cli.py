from pathlib import Path

from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser


def test_cli_build_analysis_only_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["build", "--requirements", "/tmp/x.md", "--analysis-only"])
    assert args.analysis_only is True


def test_cli_quickstart_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["quickstart"])
    assert args.command == "quickstart"


def test_cli_doctor_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"


def test_cli_analyze_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["analyze", "--repo", "/tmp/repo"])
    assert args.mode == "brownfield"
    assert args.analysis_only is False


def test_cli_discover_v2_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["discover-v2", "--source", "/tmp/requirements.md"])
    assert args.dry_run is False
    assert args.target_repo is None
    assert args.ui == "headless"


def test_cli_status_v2_parses_run_id() -> None:
    parser = build_parser()
    args = parser.parse_args(["status-v2", "--run-id", "v2-123"])
    assert args.run_id == "v2-123"


def test_cli_prepare_v2_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["prepare-v2", "--source", "/tmp/requirements.md"])
    assert args.dry_run is False
    assert args.target_repo is None
    assert args.ui == "headless"


def test_cli_execute_v2_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["execute-v2", "--run-id", "v2-123"])
    assert args.run_id == "v2-123"
    assert args.dry_run is False
    assert args.ui == "headless"


def test_cli_verify_v2_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["verify-v2", "--run-id", "v2-123"])
    assert args.run_id == "v2-123"
    assert args.base_url == "http://localhost:23000"
    assert args.dry_run is False
    assert args.ui == "headless"


def test_cli_repair_v2_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["repair-v2", "--run-id", "v2-123"])
    assert args.run_id == "v2-123"
    assert args.dry_run is False
    assert args.ui == "headless"


def test_cli_full_v2_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["full-v2", "--source", "/tmp/requirements.md"])
    assert args.base_url == "http://localhost:23000"
    assert args.repair_cycles == 1
    assert args.dry_run is False
    assert args.target_repo is None
    assert args.ui == "headless"


def test_resolve_target_repo_uses_workspace_git_repo(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert _resolve_target_repo(None, tmp_path) == tmp_path


def test_resolve_target_repo_prefers_explicit_value(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    assert _resolve_target_repo(str(explicit), tmp_path) == explicit


def test_quickstart_text_mentions_discover_and_full() -> None:
    text = _quickstart_text()
    assert "discover-v2" in text
    assert "full-v2" in text
    assert "--ui headed" in text


def test_doctor_report_detects_git_repo(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _, report = _doctor_report(tmp_path)
    assert "git repository" in report
