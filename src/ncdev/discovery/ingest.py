from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import httpx

from ncdev.utils import read_text, sha256_text


@dataclass
class IngestedAsset:
    path: str
    kind: str
    digest: str
    bytes: int


@dataclass
class IngestedSource:
    source_kind: str
    primary_source: str
    project_name: str
    content: str
    notes: list[str]
    assets: list[IngestedAsset]


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _candidate_files(root: Path) -> list[Path]:
    preferred_names = [
        "README.md",
        "requirements.md",
        "spec.md",
        "prd.md",
        "architecture.md",
        "technical.md",
        "prompt.md",
        "CLAUDE.md",
        "AGENTS.md",
        "package.json",
        "pyproject.toml",
    ]
    preferred_paths: list[Path] = []
    for name in preferred_names:
        preferred_paths.extend([path for path in root.rglob(name) if path.is_file()])

    markdown_paths = [
        path
        for path in root.rglob("*.md")
        if path.is_file() and ".git" not in path.parts and "node_modules" not in path.parts
    ]
    toml_json_paths = [
        path
        for pattern in ("*.toml", "*.json", "*.yaml", "*.yml")
        for path in root.rglob(pattern)
        if path.is_file() and ".git" not in path.parts and "node_modules" not in path.parts
    ]

    ordered: list[Path] = []
    seen: set[str] = set()
    for path in preferred_paths + markdown_paths + toml_json_paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered[:60]


def _combine_text(paths: Iterable[Path], root: Path, limit: int = 20000) -> tuple[str, list[IngestedAsset]]:
    chunks: list[str] = []
    assets: list[IngestedAsset] = []
    used = 0
    for path in paths:
        try:
            text = read_text(path)
        except UnicodeDecodeError:
            continue
        rel = str(path.relative_to(root))
        digest = sha256_text(text)
        chunks.append(f"\n## FILE: {rel}\n{text[:4000]}")
        assets.append(
            IngestedAsset(
                path=str(path),
                kind="repository_file",
                digest=digest,
                bytes=len(text.encode("utf-8")),
            )
        )
        used += len(text)
        if used >= limit:
            break
    return "\n".join(chunks).strip(), assets


def ingest_source(source_input: str) -> IngestedSource:
    if _is_url(source_input):
        with httpx.Client(timeout=10) as client:
            resp = client.get(source_input, follow_redirects=True)
            resp.raise_for_status()
            text = resp.text
        return IngestedSource(
            source_kind="url_reference",
            primary_source=source_input,
            project_name=(urlparse(source_input).hostname or "web-source").replace(".", "-"),
            content=text[:20000],
            notes=["Fetched remote source for discovery normalization."],
            assets=[
                IngestedAsset(
                    path=source_input,
                    kind="url_reference",
                    digest=sha256_text(text),
                    bytes=len(text.encode("utf-8")),
                )
            ],
        )

    path = Path(source_input).expanduser().resolve()
    if path.is_file():
        text = read_text(path)
        return IngestedSource(
            source_kind="requirements_markdown" if path.suffix.lower() in {".md", ".markdown"} else "document_file",
            primary_source=str(path),
            project_name=path.stem or path.name,
            content=text,
            notes=["Normalized single-file source input."],
            assets=[
                IngestedAsset(
                    path=str(path),
                    kind="file",
                    digest=sha256_text(text),
                    bytes=len(text.encode("utf-8")),
                )
            ],
        )

    if path.is_dir():
        is_repo = (path / ".git").exists()
        candidate_paths = _candidate_files(path)
        combined, assets = _combine_text(candidate_paths, path)
        source_kind = "repo_directory" if is_repo else "directory_bundle"
        notes = [
            "Normalized directory input using selected high-signal project files.",
            f"Repository detected={is_repo}.",
        ]
        if not combined:
            combined = f"Directory source at {path} contains no readable high-signal text files."
        return IngestedSource(
            source_kind=source_kind,
            primary_source=str(path),
            project_name=path.name or "project",
            content=combined,
            notes=notes,
            assets=assets,
        )

    raise FileNotFoundError(f"Source input not found: {source_input}")
