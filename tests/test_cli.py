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
    assert args.base_url == "http://localhost:23300"
    assert args.dry_run is False
    assert args.target_repo is None
    assert args.model == "auto"
    assert args.timeout == 600
    assert args.max_repairs == 2
    assert args.max_wall_time_minutes is None
    assert args.max_consecutive_failures == 3
    assert args.allow_unmetered is False


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


def test_cli_monitor_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["monitor", "--port", "16652", "--run-dir", "/tmp/run"])
    assert args.command == "monitor"
    assert args.port == 16652
    assert args.host == "127.0.0.1"
    assert args.run_dir == "/tmp/run"


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


def test_full_quality_gate_routes_through_factory(monkeypatch, tmp_path):
    """ncdev full --quality-gate (default) calls run_factory."""
    from ncdev import cli
    from ncdev.factory import FactoryRunState, FactoryStopReason

    captured = {}

    def fake_run_factory(**kwargs):
        captured.update(kwargs)
        return FactoryRunState(
            workspace=tmp_path,
            source_path=tmp_path / "x",
            cycles_run=1,
            stop_reason=FactoryStopReason.STEWARD_CONTINUE_AT_END,
        )

    import ncdev.factory as fac
    monkeypatch.setattr(fac, "run_factory", fake_run_factory, raising=False)

    from ncdev.pipeline import engine as engine_mod
    fake_state = type("S", (), {
        "run_id": "x", "status": "passed", "total_features": 1,
        "completed_features": 1, "run_dir": str(tmp_path),
    })()
    monkeypatch.setattr(engine_mod, "run_pipeline", lambda **kw: fake_state)

    prd = tmp_path / "prd.md"
    prd.write_text("# x")
    rc = cli.main([
        "full", "--source", str(prd), "--workspace", str(tmp_path),
        "--quality-gate",
    ])
    assert rc == 0
    assert captured["probe_test_craftr"] is True
    assert captured["require_test_craftr"] is True
    assert captured["max_cycles"] == 3
    assert captured["max_wall_time_minutes"] is None
    assert captured["max_consecutive_failures"] == 3
    assert captured["allow_unmetered"] is False
    assert captured["browser_smoke_contract"] is True
    assert captured["run_required_commands_contract"] is True
    assert captured["persona_pass_contract"] is True
    assert captured["strict_contract"] is True


def test_full_legacy_quality_gate_routes_through_orchestrator(monkeypatch, tmp_path):
    """ncdev full --quality-gate --legacy-quality-gate uses the old path."""
    from ncdev import cli
    from ncdev.quality_gate import orchestrator as orch_mod

    factory_called = []
    import ncdev.factory as fac
    monkeypatch.setattr(
        fac,
        "run_factory",
        lambda **kw: factory_called.append(1),
        raising=False,
    )

    legacy_called = []

    class FakeOrchestrator:
        def __init__(self, *a, **kw):
            pass

        async def run(self, **kw):
            legacy_called.append(1)
            return type(
                "S",
                (),
                {"phase": "passed", "current_cycle": 1, "final_scores": None},
            )()

    monkeypatch.setattr(orch_mod, "QualityGateOrchestrator", FakeOrchestrator)

    from ncdev.pipeline import engine as engine_mod
    fake_state = type("S", (), {
        "run_id": "x", "status": "passed", "total_features": 1,
        "completed_features": 1, "run_dir": str(tmp_path),
    })()
    monkeypatch.setattr(engine_mod, "run_pipeline", lambda **kw: fake_state)

    prd = tmp_path / "prd.md"
    prd.write_text("# x")
    rc = cli.main([
        "full", "--source", str(prd), "--workspace", str(tmp_path),
        "--quality-gate", "--legacy-quality-gate",
    ])
    assert factory_called == []
    assert legacy_called == [1]
    assert rc == 0


def test_cli_parses_factory_subcommand():
    from ncdev.cli import build_parser
    parser = build_parser()
    args = parser.parse_args([
        "factory", "--source", "/tmp/prd.md",
        "--workspace", "/tmp/ws",
        "--max-cycles", "5",
    ])
    assert args.command == "factory"
    assert args.source == "/tmp/prd.md"
    assert args.max_cycles == 5
    assert args.force_resume is False


def test_cli_parses_factory_status_subcommand():
    from ncdev.cli import build_parser

    args = build_parser().parse_args([
        "factory-status",
        "--run-dir",
        "/tmp/run",
        "--json",
    ])
    assert args.command == "factory-status"
    assert args.run_dir == "/tmp/run"
    assert args.json is True


def test_cli_parses_factory_baseline_flags():
    from ncdev.cli import build_parser

    args = build_parser().parse_args([
        "factory",
        "--source",
        "/tmp/prd.md",
        "--baseline",
        "--probe-test-craftr",
        "--test-craftr-url",
        "http://localhost:16630",
        "--target-url",
        "http://localhost:23300",
        "--max-wall-time-minutes",
        "480",
        "--max-consecutive-failures",
        "4",
        "--allow-unmetered",
    ])
    assert args.baseline is True
    assert args.probe_test_craftr is True
    assert args.test_craftr_mode == "local"
    assert args.browser_smoke_contract is False
    assert args.interaction_smoke_contract is False
    assert args.run_required_commands_contract is False
    assert args.visual_checks_contract is False
    assert args.persona_pass_contract is False
    assert args.strict_contract is False
    assert args.test_craftr_url == "http://localhost:16630"
    assert args.target_url == "http://localhost:23300"
    assert args.max_wall_time_minutes == 480
    assert args.max_consecutive_failures == 4
    assert args.allow_unmetered is True


def test_cli_factory_calls_run_factory(monkeypatch, tmp_path):
    from ncdev import cli
    from ncdev.factory import FactoryRunState, FactoryStopReason

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")

    captured = {}

    def fake_run_factory(**kwargs):
        captured.update(kwargs)
        return FactoryRunState(
            workspace=tmp_path,
            source_path=prd,
            cycles_run=1,
            stop_reason=FactoryStopReason.STEWARD_CONTINUE_AT_END,
        )

    monkeypatch.setattr(cli, "_factory_runner", fake_run_factory, raising=False)

    rc = cli.main([
        "factory", "--source", str(prd),
        "--workspace", str(tmp_path),
        "--max-cycles", "2",
    ])
    assert rc == 0
    assert captured["max_cycles"] == 2
    assert captured["max_wall_time_minutes"] is None
    assert captured["max_consecutive_failures"] == 3
    assert captured["allow_unmetered"] is False
    assert captured["source_path"] == prd.resolve()
    assert captured["probe_test_craftr"] is True
    assert captured["capture_baseline"] is False
    assert captured["test_craftr_mode"] == "local"
    assert captured["browser_smoke_contract"] is False
    assert captured["interaction_smoke_contract"] is False
    assert captured["run_required_commands_contract"] is False
    assert captured["visual_checks_contract"] is False
    assert captured["persona_pass_contract"] is False
    assert captured["strict_contract"] is False


def test_cli_factory_from_issues_requires_target_repo(tmp_path):
    from ncdev import cli

    report = tmp_path / "tc.json"
    report.write_text('{"run_id":"x","issues":[]}')

    rc = cli.main([
        "factory",
        "--source",
        str(report),
        "--from-issues",
        str(report),
    ])

    assert rc != 0


def test_cli_factory_from_issues_calls_from_issues_runner(monkeypatch, tmp_path):
    from ncdev import cli
    from ncdev.factory import FactoryRunState, FactoryStopReason

    report = tmp_path / "tc.json"
    report.write_text('{"run_id":"x","issues":[]}')
    target = tmp_path / "app"
    target.mkdir()

    captured = {}

    def fake_from_issues(**kw):
        captured.update(kw)
        return FactoryRunState(
            workspace=tmp_path,
            source_path=report,
            cycles_run=1,
            stop_reason=FactoryStopReason.STEWARD_CONTINUE_AT_END,
        )

    monkeypatch.setattr(
        cli,
        "_factory_from_issues_runner",
        fake_from_issues,
        raising=False,
    )

    rc = cli.main([
        "factory",
        "--source",
        str(report),
        "--from-issues",
        str(report),
        "--target-repo",
        str(target),
    ])

    assert rc == 0
    assert captured["report_path"] == report.resolve()
    assert captured["target_repo_path"] == target.resolve()


def test_cli_factory_resume_blocks_dirty_target(monkeypatch, tmp_path):
    from ncdev import cli

    source = tmp_path / "prd.md"
    source.write_text("# fake")
    target = tmp_path / "app"
    target.mkdir()
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    (target / "app.py").write_text("print('x')\n")
    subprocess.run(["git", "add", "."], cwd=target, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-m",
            "init",
        ],
        cwd=target,
        check=True,
    )
    (target / "dirty.py").write_text("dirty\n")

    run_dir = tmp_path / ".nc-dev" / "runs" / "factory-1"
    run_dir.mkdir(parents=True)
    (run_dir / "factory-summary.json").write_text(
        f"""{{
  "run_dir": "{run_dir}",
  "source_path": "{source}",
  "target_path": "{target.resolve()}",
  "stop_reason": "wall_time_exhausted",
  "last_pipeline_status": "partial",
  "cycles_run": 2,
  "recorded_cost_usd": 0.0,
  "spend": {{"event_count": 1}},
  "diagnosis": {{"headline": "stopped", "next_actions": []}}
}}
""",
        encoding="utf-8",
    )

    factory_runner = []
    monkeypatch.setattr(
        cli,
        "_factory_with_bundle_runner_default",
        lambda **kw: factory_runner.append(kw),
        raising=False,
    )
    printed: list[str] = []
    monkeypatch.setattr(
        cli.console,
        "print",
        lambda *args, **kwargs: printed.append(str(args[0])),
    )

    rc = cli.main([
        "factory",
        "--source",
        str(source),
        "--target-repo",
        str(target),
        "--resume-charter",
        str(run_dir),
    ])

    assert rc == 1
    assert factory_runner == []
    assert any("Resume preflight blocked" in line for line in printed)
    assert any("Dirty Target Files" in line for line in printed)


def test_cli_factory_resume_force_allows_dirty_target(monkeypatch, tmp_path):
    from ncdev import cli
    from ncdev.factory import FactoryRunState, FactoryStopReason
    from ncdev.pipeline import charter as charter_mod

    source = tmp_path / "prd.md"
    source.write_text("# fake")
    target = tmp_path / "app"
    target.mkdir()
    (target / "dirty.py").write_text("dirty\n")
    run_dir = tmp_path / ".nc-dev" / "runs" / "factory-1"
    run_dir.mkdir(parents=True)
    (run_dir / "factory-summary.json").write_text(
        f"""{{
  "run_dir": "{run_dir}",
  "source_path": "{source}",
  "target_path": "{target.resolve()}",
  "stop_reason": "too_many_failures",
  "last_pipeline_status": "failed",
  "cycles_run": 2,
  "recorded_cost_usd": 0.0,
  "spend": {{"event_count": 1}},
  "diagnosis": {{"headline": "stopped", "next_actions": []}}
}}
""",
        encoding="utf-8",
    )

    bundle = SimpleNamespace(feature_queue=SimpleNamespace(features=[]))
    monkeypatch.setattr(charter_mod, "load_charter", lambda *a, **kw: bundle)
    captured = {}

    def fake_factory_with_bundle(**kw):
        captured.update(kw)
        return FactoryRunState(
            workspace=tmp_path,
            source_path=source,
            cycles_run=1,
            stop_reason=FactoryStopReason.STEWARD_CONTINUE_AT_END,
        )

    monkeypatch.setattr(
        cli,
        "_factory_with_bundle_runner_default",
        fake_factory_with_bundle,
        raising=False,
    )

    rc = cli.main([
        "factory",
        "--source",
        str(source),
        "--target-repo",
        str(target),
        "--resume-charter",
        str(run_dir),
        "--force-resume",
    ])

    assert rc == 0
    assert captured["bundle"] is bundle
    assert captured["target_repo_path"] == target.resolve()


def test_cli_factory_status_reads_summary(monkeypatch, tmp_path):
    from ncdev import cli

    run_dir = tmp_path / ".nc-dev" / "runs" / "factory-1"
    run_dir.mkdir(parents=True)
    (run_dir / "factory-summary.json").write_text(
        """
{
  "run_dir": "factory-1",
  "stop_reason": "too_many_failures",
  "last_pipeline_status": "failed",
  "cycles_run": 2,
  "consecutive_failures": 2,
  "recorded_cost_usd": 0.0,
  "spend": {"event_count": 3, "unmetered_events": 1},
  "diagnosis": {
    "headline": "The consecutive-failure breaker stopped a repeated repair loop.",
    "next_actions": ["Inspect the latest Steward reasoning."]
  }
}
""",
        encoding="utf-8",
    )
    printed: list[str] = []
    monkeypatch.setattr(
        cli.console,
        "print",
        lambda *args, **kwargs: printed.append(str(args[0])),
    )

    rc = cli.main([
        "factory-status",
        "--workspace",
        str(tmp_path),
    ])

    assert rc == 0
    assert any("too_many_failures" in line for line in printed)
    assert any("Next Actions" in line for line in printed)
