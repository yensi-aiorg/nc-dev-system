"""Tests for the strict state-scanner.

The scanner only marks a feature SKIPPED when its declared
:class:`FeatureAcceptance` is fully satisfied: a Conventional Commit
names the feature_id, every required_file exists (and mentions the
feature_id where required), every required_test exists AND runs green
AND mentions the feature_id where required.
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from ncdev.pipeline.models import FeatureAcceptance, FeatureStep, StepStatus
from ncdev.pipeline.state_scanner import (
    build_skip_results,
    scan_completed_features,
    _feat_commit_names_feature,
    _file_mentions,
    _has_enforceable_acceptance,
    _required_files_present,
)


def _feat(
    fid: str,
    title: str = "",
    *,
    required_files: list[str] | None = None,
    required_tests: list[str] | None = None,
    must_mention_feature_id: bool = True,
) -> FeatureStep:
    return FeatureStep(
        feature_id=fid,
        title=title or fid,
        description=title or fid,
        acceptance_criteria=["works"],
        acceptance=FeatureAcceptance(
            required_files=required_files or [],
            required_tests=required_tests or [],
            must_mention_feature_id=must_mention_feature_id,
        ),
    )


def _git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)


def _commit(path: Path, msg: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", msg], cwd=str(path), check=True)


# ---------------------------------------------------------------------------
# _has_enforceable_acceptance
# ---------------------------------------------------------------------------


def test_no_acceptance_means_not_enforceable() -> None:
    feature = _feat("f1")  # no required_files, no required_tests
    assert _has_enforceable_acceptance(feature) is False


def test_required_files_alone_is_enforceable() -> None:
    feature = _feat("f1", required_files=["src/x.py"])
    assert _has_enforceable_acceptance(feature) is True


def test_required_tests_alone_is_enforceable() -> None:
    feature = _feat("f1", required_tests=["tests/test_x.py"])
    assert _has_enforceable_acceptance(feature) is True


# ---------------------------------------------------------------------------
# _feat_commit_names_feature
# ---------------------------------------------------------------------------


def test_conventional_commit_with_feature_id_matches() -> None:
    log = "feat(f01-auth): implement login\nrefactor(f02): cleanup\n"
    assert _feat_commit_names_feature(_feat("f01-auth"), log) is True
    assert _feat_commit_names_feature(_feat("f02"), log) is True


def test_plain_mention_in_commit_does_not_match() -> None:
    log = "fix typo in f01-auth docstring\n"
    assert _feat_commit_names_feature(_feat("f01-auth"), log) is False


def test_unrelated_log_does_not_match() -> None:
    log = "feat(other): unrelated work\n"
    assert _feat_commit_names_feature(_feat("f01-auth"), log) is False


def test_all_conventional_types_accepted() -> None:
    for ctype in ["feat", "fix", "chore", "refactor", "perf", "test", "docs"]:
        log = f"{ctype}(f01): work\n"
        assert _feat_commit_names_feature(_feat("f01"), log) is True


# ---------------------------------------------------------------------------
# _required_files_present
# ---------------------------------------------------------------------------


def test_required_files_missing_fails(tmp_path: Path) -> None:
    feature = _feat("f01", required_files=["src/x.py"])
    assert _required_files_present(feature, tmp_path) is False


def test_required_files_must_mention_feature_id(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("def thing(): pass\n")
    feature = _feat("f01-auth", required_files=["src/x.py"])
    assert _required_files_present(feature, tmp_path) is False


def test_required_files_passes_when_content_mentions_id(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("# implements f01-auth\n")
    feature = _feat("f01-auth", required_files=["src/x.py"])
    assert _required_files_present(feature, tmp_path) is True


def test_must_mention_off_skips_content_check(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("def thing(): pass\n")
    feature = _feat(
        "f01", required_files=["x.py"], must_mention_feature_id=False
    )
    assert _required_files_present(feature, tmp_path) is True


# ---------------------------------------------------------------------------
# scan_completed_features — full pipeline
# ---------------------------------------------------------------------------


def test_scan_returns_empty_without_git(tmp_path: Path) -> None:
    features = [_feat("f1", required_files=["x.py"])]
    assert scan_completed_features(tmp_path, features) == []


def test_scan_skips_feature_without_acceptance(tmp_path: Path) -> None:
    """No required_files + no required_tests = NEVER skipped."""
    _git_repo(tmp_path)
    _commit(tmp_path, "feat(f01): implement everything")
    features = [_feat("f01")]
    assert scan_completed_features(tmp_path, features) == []


def test_scan_skips_when_only_commit_matches_but_files_missing(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    _commit(tmp_path, "feat(f01): implement")
    features = [_feat("f01", required_files=["src/missing.py"])]
    assert scan_completed_features(tmp_path, features) == []


def test_scan_skips_when_files_present_but_no_commit(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("# f01\n")
    _commit(tmp_path, "chore: unrelated")
    features = [_feat("f01", required_files=["src/x.py"])]
    assert scan_completed_features(tmp_path, features) == []


def test_scan_returns_completed_when_commit_and_files_satisfy(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("# implements f01\n")
    _commit(tmp_path, "feat(f01): work")
    features = [_feat("f01", required_files=["src/x.py"])]
    assert scan_completed_features(tmp_path, features) == ["f01"]


def test_scan_runs_required_test_and_skips_only_when_green(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_f01.py").write_text(
        textwrap.dedent(
            """
            # f01-auth
            def test_works():
                assert True
            """
        ).lstrip()
    )
    _commit(tmp_path, "feat(f01-auth): tests")
    features = [_feat("f01-auth", required_tests=["tests/test_f01.py"])]
    assert scan_completed_features(tmp_path, features) == ["f01-auth"]


def test_scan_does_not_skip_when_required_test_fails(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_f01.py").write_text(
        textwrap.dedent(
            """
            # f01-auth
            def test_works():
                assert False, "intentionally broken"
            """
        ).lstrip()
    )
    _commit(tmp_path, "feat(f01-auth): broken test")
    features = [_feat("f01-auth", required_tests=["tests/test_f01.py"])]
    assert scan_completed_features(tmp_path, features) == []


def test_scan_does_not_skip_when_test_does_not_mention_feature_id(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    tests = tmp_path / "tests"
    tests.mkdir()
    # Test passes but is generic — never mentions feature_id
    (tests / "test_anything.py").write_text("def test_it(): assert True\n")
    _commit(tmp_path, "feat(f01-auth): generic test")
    features = [_feat("f01-auth", required_tests=["tests/test_anything.py"])]
    assert scan_completed_features(tmp_path, features) == []


# ---------------------------------------------------------------------------
# _file_mentions helper
# ---------------------------------------------------------------------------


def test_file_mentions_matches_path(tmp_path: Path) -> None:
    p = tmp_path / "test_f01_thing.py"
    p.write_text("x = 1\n")
    assert _file_mentions(p, "f01") is True
    assert _file_mentions(p, "f99") is False


def test_file_mentions_matches_content(tmp_path: Path) -> None:
    p = tmp_path / "x.py"
    p.write_text("# this is f01-auth\n")
    assert _file_mentions(p, "f01-auth") is True


def test_file_mentions_returns_false_for_missing_file(tmp_path: Path) -> None:
    assert _file_mentions(tmp_path / "missing.py", "f01") is False


# ---------------------------------------------------------------------------
# build_skip_results
# ---------------------------------------------------------------------------


def test_build_skip_results_emits_skipped_status() -> None:
    features = [_feat("f1"), _feat("f2"), _feat("f3")]
    results = build_skip_results(features, {"f1", "f3"})
    assert [r.feature_id for r in results] == ["f1", "f3"]
    assert all(r.status == StepStatus.SKIPPED for r in results)
    assert all("acceptance verified" in r.error_message for r in results)


# ---------------------------------------------------------------------------
# _runner_for_test — project-root resolver for single-test execution
# ---------------------------------------------------------------------------


def test_runner_for_test_python_finds_pyproject(tmp_path: Path) -> None:
    from ncdev.pipeline.state_scanner import _runner_for_test

    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (tmp_path / "backend" / "tests").mkdir()
    test_file = tmp_path / "backend" / "tests" / "test_x.py"
    test_file.write_text("def test_x(): pass\n")

    project_root, cmd = _runner_for_test(test_file, tmp_path)
    assert project_root == tmp_path / "backend"
    assert cmd is not None
    assert cmd[0].endswith("python") or cmd[0].endswith("python3")
    assert cmd[-1] == "tests/test_x.py"


def test_runner_for_test_frontend_finds_package_json(tmp_path: Path) -> None:
    from ncdev.pipeline.state_scanner import _runner_for_test

    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text('{"name": "x"}')
    (tmp_path / "frontend" / "src" / "__tests__").mkdir(parents=True)
    test_file = tmp_path / "frontend" / "src" / "__tests__" / "smoke.test.tsx"
    test_file.write_text("test('x', () => {});\n")

    project_root, cmd = _runner_for_test(test_file, tmp_path)
    assert project_root == tmp_path / "frontend"
    assert cmd == ["npx", "vitest", "run", "src/__tests__/smoke.test.tsx"]


def test_runner_for_test_falls_back_when_no_marker(tmp_path: Path) -> None:
    from ncdev.pipeline.state_scanner import _runner_for_test

    test_file = tmp_path / "test_x.py"
    test_file.write_text("def test_x(): pass\n")
    project_root, cmd = _runner_for_test(test_file, tmp_path)
    # No marker → root falls back to target_path; absolute test path used
    assert project_root == tmp_path
    assert cmd is not None


def test_runner_for_test_returns_none_for_unknown_suffix(tmp_path: Path) -> None:
    from ncdev.pipeline.state_scanner import _runner_for_test

    test_file = tmp_path / "test.go"
    test_file.touch()
    project_root, cmd = _runner_for_test(test_file, tmp_path)
    assert project_root is None
    assert cmd is None


def test_runner_for_test_picks_playwright_for_e2e_dir(tmp_path: Path) -> None:
    from ncdev.pipeline.state_scanner import _runner_for_test

    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text('{"name": "x"}')
    (tmp_path / "frontend" / "tests" / "e2e").mkdir(parents=True)
    test_file = tmp_path / "frontend" / "tests" / "e2e" / "landing.spec.ts"
    test_file.write_text("import { test } from '@playwright/test';\n")

    project_root, cmd = _runner_for_test(test_file, tmp_path)
    assert project_root == tmp_path / "frontend"
    assert cmd is not None
    assert cmd[:3] == ["npx", "playwright", "test"]


def test_runner_for_test_picks_playwright_when_config_present(tmp_path: Path) -> None:
    from ncdev.pipeline.state_scanner import _runner_for_test

    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text('{"name": "x"}')
    (tmp_path / "frontend" / "playwright.config.ts").write_text("export default {};")
    (tmp_path / "frontend" / "specs").mkdir()
    test_file = tmp_path / "frontend" / "specs" / "checkout.spec.ts"
    test_file.write_text("test('x', () => {});")

    project_root, cmd = _runner_for_test(test_file, tmp_path)
    assert cmd is not None
    assert cmd[:3] == ["npx", "playwright", "test"]
