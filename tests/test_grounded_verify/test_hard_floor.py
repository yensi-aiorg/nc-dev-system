# tests/test_grounded_verify/test_hard_floor.py
from pathlib import Path

from ncdev.pipeline.grounded_verify.hard_floor import check_hard_floor


def test_no_work_fails(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.hard_floor as hf
    monkeypatch.setattr(hf, "_git_head", lambda p: "SAME")
    monkeypatch.setattr(hf, "_git_working_tree_dirty", lambda p: False)
    r = check_hard_floor(tmp_path, pre_commit="SAME", compile_cmd=None)
    assert r.passed is False
    assert "no work" in r.reason.lower()


def test_compile_failure_fails(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.hard_floor as hf
    monkeypatch.setattr(hf, "_git_head", lambda p: "NEW")
    monkeypatch.setattr(hf, "_git_working_tree_dirty", lambda p: False)
    monkeypatch.setattr(hf, "_run_shell",
                        lambda cmd, *, cwd, timeout: (False, "SyntaxError"))
    r = check_hard_floor(tmp_path, pre_commit="OLD", compile_cmd="python -m compileall .")
    assert r.passed is False
    assert "compile" in r.reason.lower()


def test_work_and_compiles_passes(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.hard_floor as hf
    monkeypatch.setattr(hf, "_git_head", lambda p: "NEW")
    monkeypatch.setattr(hf, "_git_working_tree_dirty", lambda p: False)
    monkeypatch.setattr(hf, "_run_shell", lambda cmd, *, cwd, timeout: (True, "ok"))
    r = check_hard_floor(tmp_path, pre_commit="OLD", compile_cmd="python -m compileall .")
    assert r.passed is True
