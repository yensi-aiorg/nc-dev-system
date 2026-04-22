"""Phase D — Asset manifest.

Every Claude feature-build session must emit
``.ncdev/assets-needed/<feature_id>.json`` describing the images, GIFs,
SVGs, videos, icons, or audio clips the feature needs but couldn't
generate itself. The manifest is produced **during** the build (Claude
writes it as it codes — it knows its own intent), never after.

Downstream systems (Nano Banana 2, a stock-image service, or a human)
read the aggregate ``_all.json`` and populate each asset.

Verification step: scan the committed code for asset references. Every
reference must be present in a manifest entry, or the feature fails
verification. Manifest entries with ``status="pending"`` are OK — the
asset simply hasn't been populated yet. The code shipping without any
manifest is what we reject.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ncdev.v3.models import AssetManifest, AssetManifestEntry


# Directory layout (project-relative):
#   .ncdev/assets-needed/<feature_id>.json
#   .ncdev/assets-needed/_all.json
ASSETS_DIR = ".ncdev/assets-needed"


# ---------------------------------------------------------------------------
# Load / save / aggregate
# ---------------------------------------------------------------------------


def load_feature_manifest(project_root: Path, feature_id: str) -> AssetManifest | None:
    """Load one feature's manifest, or None if it doesn't exist."""
    path = project_root / ASSETS_DIR / f"{feature_id}.json"
    if not path.exists():
        return None
    try:
        return AssetManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def save_feature_manifest(project_root: Path, manifest: AssetManifest) -> Path:
    """Write a feature manifest. Used by tests; Claude writes its own in real runs."""
    out = project_root / ASSETS_DIR / f"{manifest.feature_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return out


def aggregate_manifests(project_root: Path) -> AssetManifest:
    """Merge all per-feature manifests into ``_all.json`` and return it."""
    dir_ = project_root / ASSETS_DIR
    all_assets: list[AssetManifestEntry] = []
    seen: set[str] = set()
    if dir_.exists():
        for path in sorted(dir_.glob("*.json")):
            if path.name in ("_all.json", "_summary.json"):
                continue
            try:
                m = AssetManifest.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for asset in m.assets:
                if asset.id in seen:
                    continue
                seen.add(asset.id)
                all_assets.append(asset)
    aggregate = AssetManifest(feature_id="_all", assets=all_assets)
    out = dir_ / "_all.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(aggregate.model_dump_json(indent=2), encoding="utf-8")
    return aggregate


# ---------------------------------------------------------------------------
# Prompt helper — spliced into every feature build prompt
# ---------------------------------------------------------------------------


def manifest_prompt_section(feature_id: str) -> str:
    """Return the prompt snippet every feature build must include.

    Tells Claude how to emit the asset manifest for this feature as it
    builds. The snippet includes schema and path. Keep short — we embed
    this in every feature prompt.
    """
    return f"""## Asset manifest requirement

While building this feature, identify every image, GIF, SVG, video,
icon, or audio clip you reference in the code but cannot generate
yourself. Write them to:

    {ASSETS_DIR}/{feature_id}.json

Schema (AssetManifest):

    {{
      "feature_id": "{feature_id}",
      "assets": [
        {{
          "id": "hero-bg",                         # unique slug
          "name": "Hero background image",
          "type": "image",                         # image | gif | svg | video | icon | audio
          "description": "Full-bleed gradient banner for the landing hero.",
          "generation_prompt": "Abstract gradient mesh, deep purples and blues, cinematic.",
          "suggested_dimensions": "2400x1200",
          "referenced_in": ["frontend/src/pages/Home.tsx:42"],
          "target_path": "frontend/public/images/hero-bg.webp",
          "status": "pending"
        }}
      ]
    }}

Rules:
- Write this file BEFORE your last commit. No trailing manifests.
- If the feature needs zero assets, write an empty assets array — do
  not skip the file.
- For every <img>, background-image, <video>, <audio>, SVG reference,
  or icon name your code introduces, there MUST be a manifest entry
  unless the asset already exists in the repo.
- Prefer referencing existing assets over inventing new ones. Only add
  manifest entries for genuinely-missing files.
"""


# ---------------------------------------------------------------------------
# Verification — scan code for asset references, cross-check manifest
# ---------------------------------------------------------------------------


# Patterns that signal an asset reference in source code
_ASSET_REFERENCE_PATTERNS: tuple[re.Pattern, ...] = (
    # HTML/JSX: <img src="...">, <video src="...">, poster="..."
    re.compile(r"""<(?:img|video|audio|source)\s+[^>]*(?:src|poster)\s*=\s*["']([^"']+)["']""", re.IGNORECASE),
    # JSX/TS import of image: import foo from "./foo.png"
    re.compile(r"""import\s+\w+\s+from\s+["']([^"']+\.(?:png|jpe?g|webp|gif|svg|mp4|webm|mp3|wav|ogg|ico))["']""", re.IGNORECASE),
    # CSS: background(-image): url("...")
    re.compile(r"""url\(\s*["']?([^"')\s]+\.(?:png|jpe?g|webp|gif|svg|mp4|webm|ico))["']?\s*\)""", re.IGNORECASE),
    # Next/Image src, React require: require("./foo.png")
    re.compile(r"""require\(\s*["']([^"']+\.(?:png|jpe?g|webp|gif|svg|mp4|webm|mp3|wav|ogg|ico))["']\s*\)""", re.IGNORECASE),
)

_CODE_EXTENSIONS: tuple[str, ...] = (
    ".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte", ".html",
    ".css", ".scss", ".sass", ".less",
    ".py", ".go", ".rs", ".rb",
)


def scan_code_for_asset_references(
    project_root: Path,
    *,
    include_dirs: Iterable[str] = ("frontend", "src", "app", "pages", "public"),
) -> list[tuple[str, str, int]]:
    """Scan code files for asset references.

    Returns list of tuples ``(file_path, referenced_asset, line_number)``.
    Paths are project-relative.
    """
    hits: list[tuple[str, str, int]] = []
    candidates: list[Path] = []
    for d in include_dirs:
        dir_path = project_root / d
        if dir_path.exists():
            for ext in _CODE_EXTENSIONS:
                candidates.extend(dir_path.rglob(f"*{ext}"))
    # Also scan top-level code files
    for ext in _CODE_EXTENSIONS:
        candidates.extend(project_root.glob(f"*{ext}"))

    for fp in candidates:
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(fp.relative_to(project_root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat in _ASSET_REFERENCE_PATTERNS:
                for m in pat.finditer(line):
                    ref = m.group(1)
                    # Skip absolute URLs — they're external, not repo assets
                    if ref.startswith(("http://", "https://", "data:", "//")):
                        continue
                    hits.append((rel, ref, lineno))
    return hits


def scan_files_for_asset_references(
    project_root: Path,
    files: Iterable[str],
) -> list[tuple[str, str, int]]:
    """Variant of :func:`scan_code_for_asset_references` scoped to a
    specific file list. Paths are project-relative.
    """
    hits: list[tuple[str, str, int]] = []
    for rel in files:
        fp = project_root / rel
        if not fp.exists() or not fp.is_file():
            continue
        # Only code files — skip binaries, images, etc.
        if fp.suffix.lower() not in _CODE_EXTENSIONS:
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat in _ASSET_REFERENCE_PATTERNS:
                for m in pat.finditer(line):
                    ref = m.group(1)
                    if ref.startswith(("http://", "https://", "data:", "//")):
                        continue
                    hits.append((rel, ref, lineno))
    return hits


def verify_manifest_covers_references(
    project_root: Path,
    feature_id: str,
    *,
    include_dirs: Iterable[str] = ("frontend", "src", "app", "pages", "public"),
    touched_files: Iterable[str] | None = None,
) -> tuple[bool, list[str]]:
    """Verify every asset reference is accounted for.

    An asset reference is "accounted for" when:
      - a file at the referenced path exists in the repo, OR
      - a manifest entry (in any per-feature manifest) points at that
        path or has an id/name matching the filename.

    Returns ``(ok, missing_list)``. When manifest-not-written, ok=False
    and missing_list=["<no-manifest>"].

    Scanning scope:
      - If ``touched_files`` is given, scan only those files (feature-local
        verification — the caller passes files_created + files_modified
        from git diff). This is the preferred call shape: one legacy
        unmanaged asset elsewhere won't fail every future feature.
      - Otherwise, fall back to scanning ``include_dirs`` globally. Kept
        for callers that don't know which files changed.
    """
    manifest = load_feature_manifest(project_root, feature_id)
    aggregate = aggregate_manifests(project_root)

    if manifest is None:
        return False, ["<no-manifest>"]

    all_entries = aggregate.assets
    managed_paths: set[str] = {
        entry.target_path.lstrip("./") for entry in all_entries if entry.target_path
    }
    managed_ids: set[str] = {entry.id for entry in all_entries}

    if touched_files is not None:
        refs = scan_files_for_asset_references(project_root, touched_files)
    else:
        refs = scan_code_for_asset_references(project_root, include_dirs=include_dirs)

    missing: list[str] = []
    for file_ref, asset_ref, lineno in refs:
        normalised = asset_ref.lstrip("./").lstrip("/")
        candidates = [
            project_root / normalised,
            project_root / "public" / normalised,
            project_root / "frontend" / "public" / normalised,
            project_root / "frontend" / "src" / normalised,
            project_root / "src" / normalised,
        ]
        if any(p.exists() for p in candidates):
            continue
        if normalised in managed_paths:
            continue
        base = normalised.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if base in managed_ids:
            continue
        missing.append(f"{file_ref}:{lineno} -> {asset_ref}")

    return (len(missing) == 0), missing
