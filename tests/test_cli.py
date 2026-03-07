from ncdev.cli import build_parser


def test_cli_build_analysis_only_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["build", "--requirements", "/tmp/x.md", "--analysis-only"])
    assert args.analysis_only is True


def test_cli_analyze_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["analyze", "--repo", "/tmp/repo"])
    assert args.mode == "brownfield"
    assert args.analysis_only is False


def test_cli_discover_v2_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["discover-v2", "--source", "/tmp/requirements.md"])
    assert args.dry_run is False


def test_cli_status_v2_parses_run_id() -> None:
    parser = build_parser()
    args = parser.parse_args(["status-v2", "--run-id", "v2-123"])
    assert args.run_id == "v2-123"


def test_cli_prepare_v2_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["prepare-v2", "--source", "/tmp/requirements.md"])
    assert args.dry_run is False


def test_cli_execute_v2_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["execute-v2", "--run-id", "v2-123"])
    assert args.run_id == "v2-123"
    assert args.dry_run is False


def test_cli_verify_v2_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["verify-v2", "--run-id", "v2-123"])
    assert args.run_id == "v2-123"
    assert args.base_url == "http://localhost:23000"
    assert args.dry_run is False
