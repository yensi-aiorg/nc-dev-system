from ncdev.cli import build_parser


def test_cli_fix_parses_report() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo"])
    assert args.command == "fix"
    assert args.report == "/tmp/rpt.json"
    assert args.target == "/tmp/repo"
    assert args.dry_run is False
    assert args.auto_deploy is False
    assert args.max_attempts == 3
    assert args.ui == "headless"


def test_cli_fix_parses_report_dir() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report-dir", "/tmp/reports/", "--target", "/tmp/repo", "--batch"])
    assert args.report_dir == "/tmp/reports/"
    assert args.batch is True


def test_cli_fix_dry_run() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo", "--dry-run"])
    assert args.dry_run is True


def test_cli_fix_auto_deploy() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo", "--auto-deploy"])
    assert args.auto_deploy is True


def test_cli_fix_max_attempts() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo", "--max-attempts", "5"])
    assert args.max_attempts == 5


def test_cli_fix_resume_run_id() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo", "--run-id", "fix-123"])
    assert args.run_id == "fix-123"


def test_cli_serve_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["serve"])
    assert args.command == "serve"
    assert args.port == 16650
    assert args.workers == 1


def test_cli_serve_custom_port() -> None:
    parser = build_parser()
    args = parser.parse_args(["serve", "--port", "9999", "--workers", "4"])
    assert args.port == 9999
    assert args.workers == 4
