from pathlib import Path

from ncdev.v2.engine import run_v2_prepare


def test_v2_prepare_materializes_ordered_job_queue(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
- User can manage projects
- User can review evidence
""".strip(),
        encoding="utf-8",
    )

    state = run_v2_prepare(tmp_path, req, dry_run=True)
    run_dir = Path(state.run_dir)
    job_queue = (run_dir / "outputs" / "job-queue.json").read_text(encoding="utf-8")

    assert '"job_id": "batch-001"' in job_queue
    assert '"job_id": "test-authoring"' in job_queue
    assert '"job_id": "qa-sweep"' in job_queue
    assert '"job_id": "delivery-pack"' in job_queue
    assert '"depends_on": [' in job_queue
