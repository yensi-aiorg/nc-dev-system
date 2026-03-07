from __future__ import annotations

import json
from pathlib import Path

from ncdev.v2.engine import run_v2_prepare, run_v2_verify
from ncdev.v2.verification import run_v2_verification


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
    assert (run_dir / "outputs" / "verification-run.json").exists()
    assert (run_dir / "outputs" / "evidence-index.json").exists()

    verification_payload = json.loads((run_dir / "outputs" / "verification-run.json").read_text(encoding="utf-8"))
    assert verification_payload["dry_run"] is True
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

    monkeypatch.setattr("ncdev.v2.verification.TestRunner", FakeRunner)

    verification_run, evidence_index = run_v2_verification(
        run_dir,
        base_url="http://localhost:9999",
        dry_run=False,
    )

    assert verification_run.overall_passed is True
    assert verification_run.base_url == "http://localhost:9999"
    assert evidence_index.screenshots
    assert evidence_index.reports
