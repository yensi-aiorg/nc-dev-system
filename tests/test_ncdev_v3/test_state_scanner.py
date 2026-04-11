import subprocess
from pathlib import Path
from unittest.mock import patch

from ncdev.v3.models import FeatureStep, StepStatus
from ncdev.v3.state_scanner import (
    build_skip_results,
    scan_completed_features,
    _feature_in_git_history,
    _feature_has_files,
)


def _feat(fid: str, title: str) -> FeatureStep:
    return FeatureStep(feature_id=fid, title=title, description=title, acceptance_criteria=["works"])


def test_feature_in_git_history_by_id():
    log = "abc1234 feat(sprint-0): project scaffold\ndef5678 feat(feature-01): user auth"
    assert _feature_in_git_history(_feat("sprint-0", "Scaffold"), log) is True
    assert _feature_in_git_history(_feat("feature-01", "Auth"), log) is True
    assert _feature_in_git_history(_feat("feature-99", "Missing"), log) is False


def test_feature_in_git_history_by_title_keywords():
    log = "abc1234 implement user authentication with jwt tokens"
    feat = _feat("f1", "User Authentication JWT Tokens")
    assert _feature_in_git_history(feat, log) is True


def test_feature_in_git_history_no_match():
    log = "abc1234 fix typo in readme"
    feat = _feat("f1", "User Authentication System")
    assert _feature_in_git_history(feat, log) is False


def test_feature_has_files_scaffold():
    files = {"backend/app/main.py", "backend/requirements.txt", "docker-compose.yml", "readme.md"}
    feat = _feat("sprint-0", "Project Scaffold & Boot")
    assert _feature_has_files(feat, files) is True


def test_feature_has_files_scaffold_incomplete():
    files = {"readme.md"}
    feat = _feat("sprint-0", "Project Scaffold & Boot")
    assert _feature_has_files(feat, files) is False


def test_feature_has_files_by_keyword():
    files = {"backend/app/services/auth_service.py", "backend/app/api/v1/endpoints/auth.py"}
    feat = _feat("f1", "User Authentication")
    assert _feature_has_files(feat, files) is True


def test_feature_has_files_no_match():
    files = {"backend/app/main.py", "readme.md"}
    feat = _feat("f1", "Dashboard Analytics")
    assert _feature_has_files(feat, files) is False


def test_build_skip_results():
    features = [_feat("f1", "Auth"), _feat("f2", "Dashboard"), _feat("f3", "Settings")]
    results = build_skip_results(features, {"f1", "f3"})
    assert len(results) == 2
    assert results[0].feature_id == "f1"
    assert results[0].status == StepStatus.PASSED
    assert "Skipped" in results[0].error_message
    assert results[1].feature_id == "f3"


def test_scan_completed_features_no_git(tmp_path):
    """No .git directory → nothing detected."""
    features = [_feat("f1", "Auth")]
    result = scan_completed_features(tmp_path, features)
    assert result == []


def test_scan_completed_features_with_git(tmp_path):
    """Git repo with matching commit → feature detected."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@test",
                     "commit", "--allow-empty", "-m", "feat(sprint-0): project scaffold"],
                    cwd=tmp_path, capture_output=True)
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("app = 'ok'")
    (tmp_path / "backend" / "requirements.txt").write_text("fastapi")
    (tmp_path / "docker-compose.yml").write_text("version: '3'")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@test",
                     "commit", "-m", "feat(feature-01): user auth"],
                    cwd=tmp_path, capture_output=True)

    features = [
        _feat("sprint-0", "Project Scaffold & Boot"),
        _feat("feature-01", "User Authentication"),
        _feat("feature-02", "Dashboard"),
    ]
    result = scan_completed_features(tmp_path, features)
    assert "sprint-0" in result
    assert "feature-01" in result
    assert "feature-02" not in result
