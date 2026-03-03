from __future__ import annotations

from pathlib import Path

from ncdev.models import HardenReportDoc


def run_hardening_checks(project_path: Path) -> HardenReportDoc:
    checks = {
        "error_handling": "unknown",
        "responsive": "unknown",
        "accessibility": "unknown",
        "performance": "unknown",
    }
    recommendations: list[str] = []

    backend_main = project_path / "backend" / "app" / "main.py"
    frontend_app = project_path / "frontend" / "src" / "App.tsx"

    if backend_main.exists():
        content = backend_main.read_text(encoding="utf-8")
        checks["error_handling"] = "basic" if "Exception" in content or "HTTPException" in content else "missing"
        if checks["error_handling"] == "missing":
            recommendations.append("Add centralized FastAPI exception handlers.")
    else:
        checks["error_handling"] = "missing"
        recommendations.append("Backend entrypoint missing; scaffold backend before hardening.")

    if frontend_app.exists():
        checks["responsive"] = "basic"
        checks["accessibility"] = "basic"
    else:
        checks["responsive"] = "missing"
        checks["accessibility"] = "missing"
        recommendations.append("Frontend app missing; scaffold frontend before hardening.")

    checks["performance"] = "pending-benchmark"
    recommendations.append("Run Lighthouse and bundle analyzer in CI for performance baseline.")

    return HardenReportDoc(project_path=str(project_path), checks=checks, recommendations=recommendations)
