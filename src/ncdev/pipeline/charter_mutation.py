"""Mutate charter artifacts on disk in response to Steward decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ncdev.pipeline.charter import load_charter, validate_charter_completeness
from ncdev.pipeline.models import CharterBundle, FeatureQueueDoc, FeatureStep
from ncdev.pipeline.product_steward import FeatureAmendment

_CHARTER_FILES = (
    "target-project-contract.json",
    "verification-contract.json",
    "feature-queue.json",
)


def insert_features(output_dir: Path, new_features: list[FeatureStep]) -> int:
    """Append new features to the on-disk queue, skipping existing IDs."""
    bundle = load_charter(output_dir, strict=False)
    existing_ids = {feature.feature_id for feature in bundle.feature_queue.features}
    features_to_insert = [
        feature
        for feature in new_features
        if feature.feature_id not in existing_ids
    ]

    if not features_to_insert:
        return 0

    updated_queue = bundle.feature_queue.model_copy(
        update={
            "features": [
                *bundle.feature_queue.features,
                *features_to_insert,
            ],
        },
    )
    updated_bundle = bundle.model_copy(update={"feature_queue": updated_queue})
    _validate_or_raise(updated_bundle)
    _write_feature_queue(updated_queue, output_dir)
    return len(features_to_insert)


def apply_amendments(output_dir: Path, amendments: list[FeatureAmendment]) -> int:
    """Apply Steward amendments to existing feature fields on disk."""
    bundle = load_charter(output_dir, strict=False)
    features_by_id = {
        feature.feature_id: index
        for index, feature in enumerate(bundle.feature_queue.features)
    }
    updated_features = list(bundle.feature_queue.features)

    for amendment in amendments:
        if amendment.feature_id not in features_by_id:
            raise KeyError(f"feature_id not found: {amendment.feature_id}")
        feature_index = features_by_id[amendment.feature_id]
        updated_features[feature_index] = _copy_with_dotted_update(
            updated_features[feature_index],
            amendment.field,
            amendment.new_value,
        )

    updated_queue = bundle.feature_queue.model_copy(
        update={"features": updated_features},
    )
    updated_bundle = bundle.model_copy(update={"feature_queue": updated_queue})
    _validate_or_raise(updated_bundle)
    _write_feature_queue(updated_queue, output_dir)
    return len(amendments)


def archive_and_clear_charter(output_dir: Path) -> Path:
    """Archive current charter artifacts into the next ``.attempt-N`` slot."""
    attempt = 1
    while (output_dir / f".attempt-{attempt}").exists():
        attempt += 1

    archive_dir = output_dir / f".attempt-{attempt}"
    archive_dir.mkdir(parents=True, exist_ok=False)
    for name in _CHARTER_FILES:
        src = output_dir / name
        if src.exists():
            src.rename(archive_dir / name)
    return archive_dir


def _copy_with_dotted_update(
    model: BaseModel,
    field_path: str,
    new_value: Any,
) -> BaseModel:
    parts = field_path.split(".")
    if not parts or any(not part for part in parts) or len(parts) > 3:
        raise KeyError(f"invalid amendment field path: {field_path}")
    return _copy_with_path_parts(model, parts, new_value)


def _copy_with_path_parts(
    model: BaseModel,
    parts: list[str],
    new_value: Any,
) -> BaseModel:
    field_name = parts[0]
    if field_name not in model.__class__.model_fields:
        raise KeyError(f"invalid amendment field path: {'.'.join(parts)}")

    if len(parts) == 1:
        return model.model_copy(update={field_name: new_value})

    child = getattr(model, field_name)
    if not isinstance(child, BaseModel):
        raise KeyError(f"invalid amendment field path: {'.'.join(parts)}")

    updated_child = _copy_with_path_parts(child, parts[1:], new_value)
    return model.model_copy(update={field_name: updated_child})


def _validate_or_raise(bundle: CharterBundle) -> None:
    violations = validate_charter_completeness(bundle)
    if violations:
        raise ValueError("charter validation failed: " + "; ".join(violations))


def _write_feature_queue(feature_queue: FeatureQueueDoc, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "feature-queue.json").write_text(
        feature_queue.model_dump_json(indent=2),
        encoding="utf-8",
    )
