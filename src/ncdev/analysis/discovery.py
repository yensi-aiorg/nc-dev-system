from __future__ import annotations

from pathlib import Path

from ncdev.models import ChangeBatch, ChangePlanDoc, RepoInventoryDoc, RiskItem, RiskMapDoc


def _has_any(root: Path, names: list[str]) -> list[str]:
    found: list[str] = []
    for name in names:
        for path in root.rglob(name):
            if path.is_file():
                found.append(str(path.relative_to(root)))
    return sorted(set(found))


def discover_repo(repo: Path, include_paths: list[str] | None = None, exclude_paths: list[str] | None = None) -> RepoInventoryDoc:
    include_paths = include_paths or []
    exclude_paths = set(exclude_paths or [])

    sample_paths: list[Path]
    if include_paths:
        sample_paths = [repo / p for p in include_paths if (repo / p).exists()]
    else:
        sample_paths = [repo]

    language_hits: set[str] = set()
    package_managers: set[str] = set()

    for base in sample_paths:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in exclude_paths for part in path.parts):
                continue
            if path.suffix in {".py"}:
                language_hits.add("python")
            if path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
                language_hits.add("javascript/typescript")
            if path.suffix in {".go"}:
                language_hits.add("go")
            if path.suffix in {".rs"}:
                language_hits.add("rust")

            if path.name == "package.json":
                package_managers.add("npm")
            if path.name == "pnpm-lock.yaml":
                package_managers.add("pnpm")
            if path.name == "poetry.lock":
                package_managers.add("poetry")
            if path.name == "requirements.txt":
                package_managers.add("pip")
            if path.name == "uv.lock":
                package_managers.add("uv")

    ci_files = _has_any(repo, ["ci.yml", "ci.yaml", "pipeline.yml", "pipeline.yaml"])
    docker_files = _has_any(repo, ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"])

    test_frameworks = []
    if _has_any(repo, ["pytest.ini", "conftest.py"]):
        test_frameworks.append("pytest")
    if _has_any(repo, ["vitest.config.ts", "jest.config.js"]):
        test_frameworks.append("vitest/jest")
    if _has_any(repo, ["playwright.config.ts", "playwright.config.js"]):
        test_frameworks.append("playwright")

    entrypoints = _has_any(repo, ["main.py", "app.py", "server.py", "index.ts", "main.ts", "main.tsx"])
    api_surfaces = _has_any(repo, ["openapi.yaml", "openapi.json", "router.py", "routes.py"])
    db_indicators = _has_any(repo, ["alembic.ini", "schema.prisma", "models.py", "migrations.sql"])
    package_roots = sorted(
        {
            str(path.parent.relative_to(repo))
            for path in repo.rglob("package.json")
            if path.is_file() and not any(part in exclude_paths for part in path.parts)
        }
    )
    if not package_roots:
        package_roots = ["."]

    monorepo = len(package_roots) > 1
    dependency_graph: dict[str, list[str]] = {}
    for root in package_roots:
        deps: list[str] = []
        base = repo / root
        if (base / "requirements.txt").exists():
            deps.append("python-runtime")
        if (base / "package.json").exists():
            deps.append("node-runtime")
        if (base / "docker-compose.yml").exists():
            deps.append("docker")
        dependency_graph[root] = deps

    hotspots: list[str] = []
    if monorepo:
        hotspots.append("monorepo-cross-package-change-risk")
    if "pytest" not in test_frameworks:
        hotspots.append("missing-python-tests")
    if "playwright" not in test_frameworks:
        hotspots.append("missing-e2e-tests")
    if not ci_files:
        hotspots.append("missing-ci-gates")

    return RepoInventoryDoc(
        repo_path=str(repo),
        detected_languages=sorted(language_hits),
        package_managers=sorted(package_managers),
        ci_files=ci_files,
        docker_files=docker_files,
        test_frameworks=sorted(set(test_frameworks)),
        entrypoints=entrypoints,
        api_surfaces=api_surfaces,
        db_indicators=db_indicators,
        monorepo=monorepo,
        package_roots=package_roots,
        dependency_graph=dependency_graph,
        hotspots=hotspots,
    )


def build_risk_map(inventory: RepoInventoryDoc) -> RiskMapDoc:
    risks: list[RiskItem] = []

    if "playwright" not in inventory.test_frameworks:
        risks.append(
            RiskItem(
                id="RISK-001",
                severity="medium",
                area="testing",
                detail="No Playwright config detected; E2E baseline may be missing.",
                mitigation="Introduce Playwright incrementally with smoke scenarios first.",
            )
        )

    if not inventory.docker_files:
        risks.append(
            RiskItem(
                id="RISK-002",
                severity="medium",
                area="delivery",
                detail="No Docker artifacts detected; environment parity risk is elevated.",
                mitigation="Add docker-compose.dev.yml and service health checks.",
            )
        )

    if not inventory.ci_files:
        risks.append(
            RiskItem(
                id="RISK-003",
                severity="high",
                area="quality-gates",
                detail="No CI pipeline file detected for automated verification.",
                mitigation="Add CI workflow with lint, unit, and E2E gates.",
            )
        )

    return RiskMapDoc(risks=risks)


def build_change_plan(inventory: RepoInventoryDoc, risk_map: RiskMapDoc) -> ChangePlanDoc:
    baseline_batch = ChangeBatch(
        id="batch-001",
        title="Introduce NC Dev runtime integration baseline",
        changes=[
            "Add .nc-dev runtime config and run artifacts directory.",
            "Wire repository analysis outputs into team workflow.",
        ],
        validations=["Run static checks", "Generate inventory + risk map without failures"],
        rollback=["Remove .nc-dev integration files", "Restore previous CI config"],
    )

    safety_batch = ChangeBatch(
        id="batch-002",
        title="Add quality gates for brownfield-safe rollout",
        changes=[
            "Add consensus gate and dual-model analysis step.",
            f"Address top detected risks: {', '.join([r.id for r in risk_map.risks]) or 'none'}.",
        ],
        validations=["Consensus agreement >= configured threshold", "No new failing tests introduced"],
        rollback=["Disable new gates", "Revert to prior pipeline revision"],
    )

    return ChangePlanDoc(batches=[baseline_batch, safety_batch])
