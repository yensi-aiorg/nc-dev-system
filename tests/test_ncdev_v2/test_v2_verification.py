from __future__ import annotations

import json
from pathlib import Path

from ncdev.v2.engine import run_v2_prepare, run_v2_verify
from ncdev.v2.verification import _apply_contract_teardown, _bootstrap_target_project, run_v2_verification


def test_v2_verify_dry_run_persists_verification_artifacts(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
- User can manage projects
""".strip(),
        encoding="utf-8",
    )
    prepared = run_v2_prepare(tmp_path, req, dry_run=True)
    verified = run_v2_verify(
        tmp_path,
        prepared.run_id,
        base_url="http://localhost:23000",
        dry_run=True,
    )
    run_dir = Path(verified.run_dir)

    assert verified.metadata["verification_passed"] is True
    assert verified.metadata["bootstrap_succeeded"] is True
    assert (run_dir / "outputs" / "verification-run.json").exists()
    assert (run_dir / "outputs" / "bootstrap-run.json").exists()
    assert (run_dir / "outputs" / "evidence-index.json").exists()
    assert (run_dir / "outputs" / "verification-issues.json").exists()

    bootstrap_payload = json.loads((run_dir / "outputs" / "bootstrap-run.json").read_text(encoding="utf-8"))
    verification_payload = json.loads((run_dir / "outputs" / "verification-run.json").read_text(encoding="utf-8"))
    issues_payload = json.loads((run_dir / "outputs" / "verification-issues.json").read_text(encoding="utf-8"))
    assert bootstrap_payload["bootstrap_succeeded"] is True
    assert verification_payload["dry_run"] is True
    assert verification_payload["bootstrap_succeeded"] is True
    assert issues_payload["issue_count"] >= 1
    assert verification_payload["routes"]


def test_v2_verification_uses_test_runner_when_not_dry_run(tmp_path: Path, monkeypatch) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
- User can manage projects
""".strip(),
        encoding="utf-8",
    )
    prepared = run_v2_prepare(tmp_path, req, dry_run=True)
    run_dir = Path(prepared.run_dir)

    class FakeSuite:
        overall_passed = True

        def summary_dict(self):
            return {
                "overall_passed": True,
                "unit": {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
                "e2e": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
                "visual": {"screenshots_count": 2, "vision_issues": 0, "comparison_failures": 0},
            }

    class FakeRunner:
        def __init__(self, project_path: Path, *, base_url: str = "http://localhost:23000", **kwargs):
            self.project_path = Path(project_path)
            self.base_url = base_url

        async def run_all(self, routes=None):
            reports_dir = self.project_path / ".nc-dev" / "test-reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / "test-suite-results.json").write_text('{"ok": true}', encoding="utf-8")
            screenshots_dir = self.project_path / ".nc-dev" / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            (screenshots_dir / "home-desktop.png").write_bytes(b"\x89PNG\x00")
            return FakeSuite()

    class FakeBootstrap:
        bootstrap_succeeded = True
        started_services = True
        teardown_succeeded = True
        commands = []

    def fake_bootstrap(target_path, *, project_name, base_url, log_dir, verification_contract):
        bootstrap = FakeBootstrap()
        bootstrap.commands = [
            type(
                "CommandRecord",
                (),
                {
                    "command": "docker compose up -d",
                },
            )()
        ]
        return bootstrap

    monkeypatch.setattr("ncdev.v2.verification._bootstrap_target_project", fake_bootstrap)
    monkeypatch.setattr("ncdev.v2.verification._teardown_target_project", lambda target_path, bootstrap_run, log_dir: bootstrap_run)
    monkeypatch.setattr("ncdev.v2.verification.TestRunner", FakeRunner)

    verification_run, evidence_index, bootstrap_run, issue_bundle = run_v2_verification(
        run_dir,
        base_url="http://localhost:9999",
        dry_run=False,
    )

    assert verification_run.overall_passed is True
    assert verification_run.base_url == "http://localhost:9999"
    assert verification_run.bootstrap_succeeded is True
    assert verification_run.bootstrap_commands == ["docker compose up -d"]
    assert bootstrap_run.teardown_succeeded is True
    assert issue_bundle.issue_count >= 0
    assert evidence_index.screenshots
    assert evidence_index.reports


def test_v2_verification_reports_bootstrap_failure(tmp_path: Path, monkeypatch) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
""".strip(),
        encoding="utf-8",
    )
    prepared = run_v2_prepare(tmp_path, req, dry_run=True)
    run_dir = Path(prepared.run_dir)

    class FailedBootstrap:
        bootstrap_succeeded = False
        started_services = False
        teardown_succeeded = False
        commands = []

    def fake_bootstrap(target_path, *, project_name, base_url, log_dir, verification_contract):
        bootstrap = FailedBootstrap()
        bootstrap.commands = [
            type(
                "CommandRecord",
                (),
                {
                    "command": "docker compose up -d",
                },
            )()
        ]
        return bootstrap

    monkeypatch.setattr("ncdev.v2.verification._bootstrap_target_project", fake_bootstrap)

    verification_run, evidence_index, bootstrap_run, issue_bundle = run_v2_verification(
        run_dir,
        base_url="http://localhost:9999",
        dry_run=False,
    )

    assert verification_run.overall_passed is False
    assert verification_run.bootstrap_succeeded is False
    assert verification_run.bootstrap_commands == ["docker compose up -d"]
    assert bootstrap_run.bootstrap_succeeded is False
    assert issue_bundle.issue_count >= 1
    assert evidence_index.project_name == verification_run.project_name


def test_v2_verification_reports_runner_errors_and_teardown(tmp_path: Path, monkeypatch) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
""".strip(),
        encoding="utf-8",
    )
    prepared = run_v2_prepare(tmp_path, req, dry_run=True)
    run_dir = Path(prepared.run_dir)

    class FakeBootstrap:
        bootstrap_succeeded = True
        started_services = True
        teardown_succeeded = False
        commands = []

    bootstrap = FakeBootstrap()
    bootstrap.commands = [
        type(
            "CommandRecord",
            (),
            {
                "command": "docker compose up -d",
            },
        )()
    ]

    class ExplodingRunner:
        def __init__(self, project_path: Path, *, base_url: str = "http://localhost:23000", **kwargs):
            self.project_path = Path(project_path)
            self.base_url = base_url

        async def run_all(self, routes=None):
            raise RuntimeError("playwright crashed")

    def fake_teardown(target_path, bootstrap_run, log_dir, verification_contract):
        bootstrap_run.teardown_attempted = True
        bootstrap_run.teardown_succeeded = False
        return bootstrap_run

    monkeypatch.setattr(
        "ncdev.v2.verification._bootstrap_target_project",
        lambda target_path, *, project_name, base_url, log_dir, verification_contract: bootstrap,
    )
    monkeypatch.setattr("ncdev.v2.verification._apply_contract_teardown", fake_teardown)
    monkeypatch.setattr("ncdev.v2.verification.TestRunner", ExplodingRunner)

    verification_run, evidence_index, bootstrap_run, issue_bundle = run_v2_verification(
        run_dir,
        base_url="http://localhost:9999",
        dry_run=False,
    )

    assert verification_run.overall_passed is False
    assert verification_run.summary["runner_error"] == "playwright crashed"
    assert bootstrap_run.teardown_attempted is True
    assert bootstrap_run.teardown_succeeded is False
    assert issue_bundle.issue_count >= 1
    assert evidence_index.project_name == verification_run.project_name


def test_v2_verification_flags_missing_screenshot_coverage_and_reports(tmp_path: Path, monkeypatch) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
- User can manage projects
""".strip(),
        encoding="utf-8",
    )
    prepared = run_v2_prepare(tmp_path, req, dry_run=True)
    run_dir = Path(prepared.run_dir)

    class FakeSuite:
        overall_passed = True

        def summary_dict(self):
            return {
                "overall_passed": True,
                "unit": {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
                "e2e": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
                "visual": {"screenshots_count": 1, "vision_issues": 0, "comparison_failures": 0},
            }

    class FakeRunner:
        def __init__(self, project_path: Path, *, base_url: str = "http://localhost:23000", **kwargs):
            self.project_path = Path(project_path)
            self.base_url = base_url

        async def run_all(self, routes=None):
            screenshots_dir = self.project_path / ".nc-dev" / "screenshots" / "root"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            (screenshots_dir / "desktop.png").write_bytes(b"\x89PNG\x00")
            return FakeSuite()

    class FakeBootstrap:
        bootstrap_succeeded = True
        started_services = False
        teardown_succeeded = True
        commands = []

    monkeypatch.setattr(
        "ncdev.v2.verification._bootstrap_target_project",
        lambda target_path, *, project_name, base_url, log_dir, verification_contract: FakeBootstrap(),
    )
    monkeypatch.setattr("ncdev.v2.verification.TestRunner", FakeRunner)

    verification_run, evidence_index, bootstrap_run, issue_bundle = run_v2_verification(
        run_dir,
        base_url="http://localhost:9999",
        dry_run=False,
    )

    issue_ids = {issue.issue_id for issue in issue_bundle.issues}
    assert verification_run.overall_passed is True
    assert bootstrap_run.bootstrap_succeeded is True
    assert "missing-screenshots" in issue_ids
    assert "missing-test-reports" in issue_ids
    assert len(evidence_index.screenshots) == 1
    assert not evidence_index.reports


def test_v2_bootstrap_supports_background_startup_commands(tmp_path: Path, monkeypatch) -> None:
    target_path = tmp_path / "target"
    target_path.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    class FakeProcess:
        pid = 43210

    monkeypatch.setattr("ncdev.v2.verification._url_reachable", lambda base_url: False)
    monkeypatch.setattr("ncdev.v2.verification._wait_for_reachability", lambda base_url, timeout_seconds=45: True)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    bootstrap_run = _bootstrap_target_project(
        target_path,
        project_name="target",
        base_url="http://localhost:3000",
        log_dir=log_dir,
        verification_contract={"startup_commands": ["npm run dev"], "teardown_commands": []},
    )

    assert bootstrap_run.bootstrap_succeeded is True
    assert bootstrap_run.started_services is True
    assert bootstrap_run.commands
    assert bootstrap_run.commands[0].background is True
    assert bootstrap_run.commands[0].pid == 43210


def test_v2_teardown_terminates_background_startup_processes(tmp_path: Path, monkeypatch) -> None:
    target_path = tmp_path / "target"
    target_path.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    from ncdev.v2.models import BootstrapCommandRecord, BootstrapRunDoc

    bootstrap_run = BootstrapRunDoc(
        generator="test",
        source_inputs=[str(target_path)],
        project_name="target",
        target_path=str(target_path),
        base_url="http://localhost:3000",
        reachable_before_bootstrap=False,
        bootstrap_succeeded=True,
        started_services=True,
        commands=[
            BootstrapCommandRecord(
                stage="bootstrap",
                command="npm run dev",
                succeeded=True,
                background=True,
                pid=43210,
            )
        ],
        summary={},
    )

    killed: list[tuple[int, int]] = []

    monkeypatch.setattr("os.killpg", lambda pid, sig: killed.append((pid, sig)))

    updated = _apply_contract_teardown(
        target_path,
        bootstrap_run,
        log_dir,
        verification_contract={"teardown_commands": []},
    )

    assert updated.teardown_attempted is True
    assert updated.teardown_succeeded is True
    assert killed
    assert updated.teardown_commands
    assert updated.teardown_commands[0].background is True
