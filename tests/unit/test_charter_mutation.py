from __future__ import annotations

from pathlib import Path

import pytest

from ncdev.pipeline.charter import load_charter, write_charter
from ncdev.pipeline.charter_mutation import (
    apply_amendments,
    archive_and_clear_charter,
    insert_features,
)
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureAcceptance,
    FeatureQueueDoc,
    FeatureStep,
    TargetProjectContract,
    VerificationContract,
)
from ncdev.pipeline.product_steward import FeatureAmendment


def _feature(
    feature_id: str,
    *,
    required_files: list[str] | None = None,
    required_tests: list[str] | None = None,
) -> FeatureStep:
    return FeatureStep(
        feature_id=feature_id,
        title=f"Feature {feature_id}",
        description=f"Build {feature_id}",
        acceptance_criteria=["Works"],
        acceptance=FeatureAcceptance(
            required_files=required_files or [f"src/{feature_id}.py"],
            required_tests=required_tests or [f"tests/test_{feature_id}.py"],
        ),
    )


def _make_bundle(tmp_path: Path) -> CharterBundle:
    bundle = CharterBundle(
        contract=TargetProjectContract(
            project_name="libproj",
            project_type="library",
            language_backend="python",
            deployment_target="docker",
            design_archetype="Technical Elegance",
            design_system_source="existing",
        ),
        verification=VerificationContract(
            backend_test_command="pytest -q",
            required_files=["pyproject.toml"],
        ),
        feature_queue=FeatureQueueDoc(
            project_name="libproj",
            features=[_feature("f01-scaffold")],
        ),
    )
    write_charter(bundle, tmp_path)
    return bundle


def test_insert_features_appends_new(tmp_path: Path):
    _make_bundle(tmp_path)

    inserted = insert_features(tmp_path, [_feature("f02-api")])

    loaded = load_charter(tmp_path)
    assert inserted == 1
    assert [feature.feature_id for feature in loaded.feature_queue.features] == [
        "f01-scaffold",
        "f02-api",
    ]


def test_insert_features_skips_existing_ids(tmp_path: Path):
    _make_bundle(tmp_path)

    inserted = insert_features(
        tmp_path,
        [_feature("f01-scaffold"), _feature("f02-api")],
    )

    loaded = load_charter(tmp_path)
    assert inserted == 1
    assert [feature.feature_id for feature in loaded.feature_queue.features] == [
        "f01-scaffold",
        "f02-api",
    ]


def test_insert_features_rejects_invalid_charter(tmp_path: Path):
    _make_bundle(tmp_path)
    invalid_feature = FeatureStep(
        feature_id="f02-empty",
        title="Empty",
        description="Missing structured acceptance",
        acceptance_criteria=["Works"],
        acceptance=FeatureAcceptance(),
    )

    with pytest.raises(ValueError, match="charter validation failed"):
        insert_features(tmp_path, [invalid_feature])


def test_apply_amendments_sets_required_files(tmp_path: Path):
    _make_bundle(tmp_path)

    applied = apply_amendments(
        tmp_path,
        [
            FeatureAmendment(
                feature_id="f01-scaffold",
                field="acceptance.required_files",
                new_value=["src/revised.py"],
                reason="Tighter target",
            ),
        ],
    )

    loaded = load_charter(tmp_path)
    assert applied == 1
    assert loaded.feature_queue.features[0].acceptance.required_files == [
        "src/revised.py",
    ]


def test_apply_amendments_missing_feature_id_raises(tmp_path: Path):
    _make_bundle(tmp_path)

    with pytest.raises(KeyError, match="feature_id not found"):
        apply_amendments(
            tmp_path,
            [
                FeatureAmendment(
                    feature_id="f99-missing",
                    field="acceptance.required_files",
                    new_value=["src/missing.py"],
                    reason="Missing feature",
                ),
            ],
        )


def test_apply_amendments_invalid_field_path_raises(tmp_path: Path):
    _make_bundle(tmp_path)

    with pytest.raises(KeyError, match="invalid amendment field path"):
        apply_amendments(
            tmp_path,
            [
                FeatureAmendment(
                    feature_id="f01-scaffold",
                    field="acceptance.not_a_field",
                    new_value=["src/nope.py"],
                    reason="Bad field",
                ),
            ],
        )


def test_archive_and_clear_moves_files(tmp_path: Path):
    _make_bundle(tmp_path)

    archive_path = archive_and_clear_charter(tmp_path)

    assert archive_path == tmp_path / ".attempt-1"
    assert (archive_path / "target-project-contract.json").exists()
    assert (archive_path / "verification-contract.json").exists()
    assert (archive_path / "feature-queue.json").exists()
    assert not (tmp_path / "target-project-contract.json").exists()
    assert not (tmp_path / "verification-contract.json").exists()
    assert not (tmp_path / "feature-queue.json").exists()


def test_archive_increments_attempt_slot(tmp_path: Path):
    _make_bundle(tmp_path)
    (tmp_path / ".attempt-1").mkdir()

    archive_path = archive_and_clear_charter(tmp_path)

    assert archive_path == tmp_path / ".attempt-2"
    assert (archive_path / "feature-queue.json").exists()
