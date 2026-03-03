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
