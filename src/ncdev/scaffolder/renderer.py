from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ncdev.models import ArchitectureDoc, FeaturesDoc, ScaffoldingManifestDoc
from ncdev.utils import write_text


def scaffold_greenfield_project(
    templates_root: Path,
    output_dir: Path,
    project_name: str,
    features: FeaturesDoc,
    architecture: ArchitectureDoc,
) -> ScaffoldingManifestDoc:
    env = Environment(loader=FileSystemLoader(str(templates_root / "greenfield")), autoescape=False)

    template_map = {
        "README.md.j2": "README.md",
        "docker-compose.yml.j2": "docker-compose.yml",
        "backend/requirements.txt.j2": "backend/requirements.txt",
        "backend/app/main.py.j2": "backend/app/main.py",
        "backend/app/api/v1/router.py.j2": "backend/app/api/v1/router.py",
        "frontend/package.json.j2": "frontend/package.json",
        "frontend/src/main.tsx.j2": "frontend/src/main.tsx",
        "frontend/src/App.tsx.j2": "frontend/src/App.tsx",
        "playwright.config.ts.j2": "frontend/playwright.config.ts",
    }

    files_written: list[str] = []
    for template_name, rel_target in template_map.items():
        template = env.get_template(template_name)
        rendered = template.render(
            project_name=project_name,
            features=features.features,
            architecture=architecture,
        )
        target = output_dir / rel_target
        write_text(target, rendered)
        files_written.append(str(target.relative_to(output_dir)))

    return ScaffoldingManifestDoc(
        project_name=project_name,
        target_path=str(output_dir),
        files_written=sorted(files_written),
    )
