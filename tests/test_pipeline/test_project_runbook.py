from __future__ import annotations

from pathlib import Path

from ncdev.core.config import NCDevConfig
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureQueueDoc,
    TargetProjectContract,
    VerificationContract,
)
from ncdev.pipeline.project_runbook import (
    build_fallback_runbook,
    command_for_test_from_runbook,
    generate_project_runbook,
    parse_runbook_response,
)


def _bundle() -> CharterBundle:
    return CharterBundle(
        contract=TargetProjectContract(project_name="proj", project_type="web"),
        verification=VerificationContract(
            backend_test_command="cd backend && pytest -q",
            frontend_test_command="cd frontend && npm run test -- --run",
        ),
        feature_queue=FeatureQueueDoc(project_name="proj", features=[]),
    )


def test_fallback_runbook_uses_verification_contract_commands(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    bundle = _bundle()

    runbook = build_fallback_runbook(target_path=tmp_path, bundle=bundle)

    assert runbook.backend.root == "backend"
    assert runbook.backend.single_test_command == "pytest -q -x {test_path}"
    assert "target-project-contract.json" in runbook.protected_files


def test_runbook_command_for_backend_single_test(tmp_path: Path) -> None:
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    test_path = tmp_path / "backend" / "tests" / "test_f01.py"
    test_path.write_text("def test_x(): pass\n")
    runbook = build_fallback_runbook(target_path=tmp_path, bundle=_bundle())

    resolved = command_for_test_from_runbook(
        runbook,
        test_path=test_path,
        target_path=tmp_path,
    )

    assert resolved is not None
    cwd, cmd = resolved
    assert cwd == tmp_path / "backend"
    assert cmd == ["pytest", "-q", "-x", "tests/test_f01.py"]


def test_runbook_command_uses_playwright_for_frontend_e2e_specs(tmp_path: Path) -> None:
    (tmp_path / "frontend" / "tests" / "e2e").mkdir(parents=True)
    (tmp_path / "frontend" / "package.json").write_text('{"name": "x"}')
    test_path = tmp_path / "frontend" / "tests" / "e2e" / "f03_waitlist.spec.ts"
    test_path.write_text("import { test } from '@playwright/test';\n")
    runbook = build_fallback_runbook(target_path=tmp_path, bundle=_bundle())

    resolved = command_for_test_from_runbook(
        runbook,
        test_path=test_path,
        target_path=tmp_path,
    )

    assert resolved is not None
    cwd, cmd = resolved
    assert cwd == tmp_path / "frontend"
    assert cmd == ["npx", "playwright", "test", "tests/e2e/f03_waitlist.spec.ts"]


def test_parse_runbook_response_accepts_fenced_json() -> None:
    parsed = parse_runbook_response(
        """
        ```json
        {
          "version": "1.0",
          "source": "ai_model",
          "project_name": "proj",
          "backend": {
            "root": "backend",
            "test_command": "pytest -q",
            "single_test_command": "pytest -q -x {test_path}"
          },
          "frontend": {
            "root": "frontend",
            "test_command": "npm run test -- --run",
            "single_test_command": "npm run test -- --run {test_path}"
          },
          "protected_files": ["docs/design-system/tokens.json"],
          "mandates": ["Prefer contract commands."]
        }
        ```
        """
    )

    assert parsed is not None
    assert parsed.source == "ai_model"
    assert parsed.backend.root == "backend"


def test_generate_project_runbook_falls_back_when_ai_disabled(tmp_path: Path) -> None:
    config = NCDevConfig()
    config.process_flow.ai_runbook_enabled = False
    bundle = _bundle()
    (tmp_path / "backend").mkdir()
    output_dir = tmp_path / "run" / "outputs"

    runbook = generate_project_runbook(
        target_path=tmp_path,
        output_dir=output_dir,
        bundle=bundle,
        config=config,
    )

    assert runbook.source == "deterministic_fallback"
    assert (output_dir / "project-runbook.json").exists()
    assert (tmp_path / ".ncdev" / "project-runbook.json").exists()
