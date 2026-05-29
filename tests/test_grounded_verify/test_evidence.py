# tests/test_grounded_verify/test_evidence.py
from pathlib import Path

from ncdev.pipeline.grounded_verify.evidence import gather_evidence, _scoped_bandit_targets


def test_bandit_targets_exclude_deps_and_nonpython():
    changed = [
        "backend/app/api/x.py", "backend/.venv/lib/pymongo/auth.py",
        "frontend/node_modules/a/b.py", "frontend/src/App.tsx",
        "backend/app/api/y.py",
    ]
    assert _scoped_bandit_targets(changed) == ["backend/app/api/x.py", "backend/app/api/y.py"]


def test_gather_runs_declared_tests_and_records_exit(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.evidence as ev
    calls = []

    def fake_shell(cmd, *, cwd, timeout):
        calls.append(cmd)
        return (False, "E   KeyError: 'items'")

    monkeypatch.setattr(ev, "_run_shell", fake_shell)
    bundle = ev.gather_evidence(
        tmp_path, backend_test_cmd="pytest -q", frontend_test_cmd=None,
        changed_files=["backend/app/api/x.py"], diff="diff", screenshots=[],
    )
    names = {i.name: i for i in bundle.items}
    assert "backend-tests" in names
    assert names["backend-tests"].exit_code == 1
    assert "KeyError" in names["backend-tests"].output_tail
    assert bundle.changed_files == ["backend/app/api/x.py"]
