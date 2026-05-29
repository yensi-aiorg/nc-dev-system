# tests/test_grounded_verify/test_hard_floor.py
from pathlib import Path

from ncdev.pipeline.grounded_verify.hard_floor import check_hard_floor


def test_no_work_fails(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.hard_floor as hf
    monkeypatch.setattr(hf, "_git_head", lambda p: "SAME")
    monkeypatch.setattr(hf, "_git_working_tree_dirty", lambda p: False)
    r = check_hard_floor(tmp_path, pre_commit="SAME", changed_files=[])
    assert r.passed is False
    assert "no work" in r.reason.lower()


def test_syntax_error_fails(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.hard_floor as hf
    # Write a real .py file with a syntax error
    bad_py = tmp_path / "bad.py"
    bad_py.write_text("def foo(\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(hf, "_git_head", lambda p: "NEW")
    monkeypatch.setattr(hf, "_git_working_tree_dirty", lambda p: False)
    r = check_hard_floor(tmp_path, pre_commit="OLD", changed_files=["bad.py"])
    assert r.passed is False
    assert "does not compile" in r.reason.lower()


def test_valid_py_passes(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify.hard_floor as hf
    # Write a valid .py file
    good_py = tmp_path / "good.py"
    good_py.write_text("def foo():\n    return 42\n", encoding="utf-8")
    monkeypatch.setattr(hf, "_git_head", lambda p: "NEW")
    monkeypatch.setattr(hf, "_git_working_tree_dirty", lambda p: False)
    r = check_hard_floor(tmp_path, pre_commit="OLD", changed_files=["good.py"])
    assert r.passed is True
