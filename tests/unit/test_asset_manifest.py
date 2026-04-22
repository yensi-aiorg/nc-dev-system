"""Tests for Phase D asset manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ncdev.v3.asset_manifest import (
    ASSETS_DIR,
    aggregate_manifests,
    load_feature_manifest,
    manifest_prompt_section,
    save_feature_manifest,
    scan_code_for_asset_references,
    verify_manifest_covers_references,
)
from ncdev.v3.models import AssetManifest, AssetManifestEntry


def _mk_manifest(feature_id: str, *entries: AssetManifestEntry) -> AssetManifest:
    return AssetManifest(feature_id=feature_id, assets=list(entries))


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_save_and_load_manifest_roundtrip(tmp_path: Path):
    m = _mk_manifest(
        "f02-hero",
        AssetManifestEntry(
            id="hero-bg",
            name="Hero background",
            type="image",
            description="Full-bleed gradient",
            generation_prompt="Abstract gradient mesh, deep purples",
            suggested_dimensions="2400x1200",
            target_path="frontend/public/images/hero-bg.webp",
            referenced_in=["frontend/src/pages/Home.tsx:42"],
        ),
    )
    save_feature_manifest(tmp_path, m)
    loaded = load_feature_manifest(tmp_path, "f02-hero")
    assert loaded is not None
    assert loaded.feature_id == "f02-hero"
    assert loaded.assets[0].id == "hero-bg"


def test_load_manifest_returns_none_when_missing(tmp_path: Path):
    assert load_feature_manifest(tmp_path, "nonexistent") is None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_aggregate_merges_multiple_feature_manifests(tmp_path: Path):
    save_feature_manifest(tmp_path, _mk_manifest(
        "f01", AssetManifestEntry(id="a", name="a", type="image",
                                   description="", generation_prompt=""),
    ))
    save_feature_manifest(tmp_path, _mk_manifest(
        "f02", AssetManifestEntry(id="b", name="b", type="svg",
                                   description="", generation_prompt=""),
    ))
    agg = aggregate_manifests(tmp_path)
    assert agg.feature_id == "_all"
    ids = {a.id for a in agg.assets}
    assert ids == {"a", "b"}
    # Aggregate also written to disk
    all_path = tmp_path / ASSETS_DIR / "_all.json"
    assert all_path.exists()


def test_aggregate_deduplicates_by_id(tmp_path: Path):
    save_feature_manifest(tmp_path, _mk_manifest(
        "f01", AssetManifestEntry(id="shared", name="v1", type="image",
                                   description="", generation_prompt=""),
    ))
    save_feature_manifest(tmp_path, _mk_manifest(
        "f02", AssetManifestEntry(id="shared", name="v2", type="image",
                                   description="", generation_prompt=""),
    ))
    agg = aggregate_manifests(tmp_path)
    assert len([a for a in agg.assets if a.id == "shared"]) == 1


def test_aggregate_skips_summary_and_bad_files(tmp_path: Path):
    dir_ = tmp_path / ASSETS_DIR
    dir_.mkdir(parents=True)
    (dir_ / "_all.json").write_text("{}")
    (dir_ / "garbage.json").write_text("{not json")
    save_feature_manifest(tmp_path, _mk_manifest(
        "f01", AssetManifestEntry(id="ok", name="ok", type="image",
                                   description="", generation_prompt=""),
    ))
    agg = aggregate_manifests(tmp_path)
    ids = {a.id for a in agg.assets}
    assert ids == {"ok"}


# ---------------------------------------------------------------------------
# Prompt section
# ---------------------------------------------------------------------------


def test_prompt_section_includes_path_and_schema():
    snippet = manifest_prompt_section("f03-checkout")
    assert "f03-checkout.json" in snippet
    assert ASSETS_DIR in snippet
    assert "generation_prompt" in snippet
    assert "status" in snippet
    # Must cover the six asset types
    for t in ("image", "gif", "svg", "video", "icon", "audio"):
        assert t in snippet


# ---------------------------------------------------------------------------
# Code scanning
# ---------------------------------------------------------------------------


def test_scan_detects_img_tag_references(tmp_path: Path):
    frontend_src = tmp_path / "frontend" / "src" / "pages"
    frontend_src.mkdir(parents=True)
    (frontend_src / "Home.tsx").write_text(
        """export const Home = () => (
  <div>
    <img src="/images/logo.png" alt="logo" />
    <video src="../videos/demo.mp4" />
  </div>
);"""
    )
    hits = scan_code_for_asset_references(tmp_path)
    refs = {h[1] for h in hits}
    assert "/images/logo.png" in refs
    assert "../videos/demo.mp4" in refs


def test_scan_detects_css_url_references(tmp_path: Path):
    css = tmp_path / "frontend" / "src" / "style.css"
    css.parent.mkdir(parents=True)
    css.write_text(
        ".hero { background-image: url('./assets/hero.webp'); }"
    )
    hits = scan_code_for_asset_references(tmp_path)
    assert any("hero.webp" in h[1] for h in hits)


def test_scan_detects_import_statements(tmp_path: Path):
    src = tmp_path / "src" / "App.tsx"
    src.parent.mkdir(parents=True)
    src.write_text("""import logo from "./logo.svg";
import banner from "./assets/banner.png";""")
    hits = scan_code_for_asset_references(tmp_path)
    refs = {h[1] for h in hits}
    assert any("logo.svg" in r for r in refs)
    assert any("banner.png" in r for r in refs)


def test_scan_ignores_external_urls(tmp_path: Path):
    src = tmp_path / "src" / "App.tsx"
    src.parent.mkdir(parents=True)
    src.write_text(
        """<img src="https://cdn.example.com/logo.png" />"""
    )
    hits = scan_code_for_asset_references(tmp_path)
    # External URL skipped
    assert len(hits) == 0


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def test_verify_fails_without_manifest(tmp_path: Path):
    # Create a file with a reference but no manifest
    src = tmp_path / "frontend" / "src" / "App.tsx"
    src.parent.mkdir(parents=True)
    src.write_text('<img src="/images/missing.png" />')
    ok, missing = verify_manifest_covers_references(tmp_path, "f01")
    assert ok is False
    assert "<no-manifest>" in missing


def test_verify_fails_when_reference_not_in_manifest(tmp_path: Path):
    src = tmp_path / "frontend" / "src" / "App.tsx"
    src.parent.mkdir(parents=True)
    src.write_text('<img src="/images/unlisted.png" />')
    save_feature_manifest(tmp_path, _mk_manifest("f01"))  # empty manifest
    ok, missing = verify_manifest_covers_references(tmp_path, "f01")
    assert ok is False
    assert any("unlisted.png" in m for m in missing)


def test_verify_ignores_assets_outside_touched_files(tmp_path: Path):
    """Feature-local scope: a reference in a file the current feature
    didn't touch must NOT fail this feature's verification.

    Codex's flag: global scans made one legacy unmanaged asset anywhere
    in the repo cause every future feature to fail forever.
    """
    # Legacy file with an unmanaged reference — predates this feature
    legacy = tmp_path / "frontend" / "src" / "Legacy.tsx"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('<img src="/images/legacy.png" />')

    # Feature only touches a clean file
    clean = tmp_path / "frontend" / "src" / "Clean.tsx"
    clean.write_text('export const Clean = () => <div>hi</div>;')

    save_feature_manifest(tmp_path, _mk_manifest("f01"))  # empty manifest OK
    ok, missing = verify_manifest_covers_references(
        tmp_path, "f01",
        touched_files=["frontend/src/Clean.tsx"],  # legacy NOT in list
    )
    assert ok is True, f"missing={missing}"


def test_verify_catches_references_in_touched_files(tmp_path: Path):
    """The feature DID touch a file with an unmanaged reference — must fail."""
    f = tmp_path / "frontend" / "src" / "New.tsx"
    f.parent.mkdir(parents=True)
    f.write_text('<img src="/images/new-hero.png" />')
    save_feature_manifest(tmp_path, _mk_manifest("f01"))
    ok, missing = verify_manifest_covers_references(
        tmp_path, "f01",
        touched_files=["frontend/src/New.tsx"],
    )
    assert ok is False
    assert any("new-hero.png" in m for m in missing)


def test_verify_passes_when_asset_listed_in_manifest(tmp_path: Path):
    src = tmp_path / "frontend" / "src" / "App.tsx"
    src.parent.mkdir(parents=True)
    src.write_text('<img src="/images/hero.png" />')
    save_feature_manifest(tmp_path, _mk_manifest(
        "f01",
        AssetManifestEntry(
            id="hero",
            name="Hero",
            type="image",
            description="Landing hero",
            generation_prompt="...",
            target_path="images/hero.png",
        ),
    ))
    ok, missing = verify_manifest_covers_references(tmp_path, "f01")
    assert ok is True
    assert missing == []


def test_verify_passes_when_asset_already_exists_in_repo(tmp_path: Path):
    # Asset exists on disk; manifest not required for pre-existing ones
    img = tmp_path / "frontend" / "public" / "images" / "logo.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"\x89PNG")
    src = tmp_path / "frontend" / "src" / "App.tsx"
    src.parent.mkdir(parents=True)
    src.write_text('<img src="/images/logo.png" />')
    save_feature_manifest(tmp_path, _mk_manifest("f01"))
    ok, missing = verify_manifest_covers_references(tmp_path, "f01")
    assert ok is True, f"should pass, missing={missing}"


def test_verify_passes_when_manifest_entry_matches_by_id(tmp_path: Path):
    src = tmp_path / "frontend" / "src" / "App.tsx"
    src.parent.mkdir(parents=True)
    src.write_text('<img src="/img/hero-bg.png" />')
    save_feature_manifest(tmp_path, _mk_manifest(
        "f01",
        AssetManifestEntry(
            id="hero-bg",  # matches filename base
            name="Hero BG",
            type="image",
            description="",
            generation_prompt="",
        ),
    ))
    ok, missing = verify_manifest_covers_references(tmp_path, "f01")
    assert ok is True, f"should pass by id match, missing={missing}"
