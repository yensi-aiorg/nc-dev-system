from pathlib import Path

from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser


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
    assert args.model == "gpt-5.4"
    assert args.timeout == 600
    assert args.max_repairs == 2


def test_cli_full_custom_options() -> None:
    parser = build_parser()
    args = parser.parse_args([
        "full", "--source", "/tmp/requirements.md",
        "--model", "gpt-5.4-mini", "--timeout", "900", "--max-repairs", "3",
        "--dry-run", "--target-repo", "/tmp/repo",
    ])
    assert args.model == "gpt-5.4-mini"
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
