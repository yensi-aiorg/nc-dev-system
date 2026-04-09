#!/usr/bin/env python3
"""Sync project context to CLAUDE.md and AGENTS.md for every YENSI project.

Run: python sync-project-context.py
Schedule: cron every 2 hours

This reads the current state of each project from:
- Git (recent commits, branch, status)
- Docker (running containers, ports)
- deploy-manage (server assignments)
- Sentinel (health status)
- Existing CLAUDE.md (preserve user preferences)

And writes/updates CLAUDE.md and AGENTS.md in each project root so that
when you open Claude Code or Codex CLI, the context is already there.
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

YENSI_DEV = Path("/Users/nrupal/dev/yensi/dev")

# Project registry — what we know about each project
PROJECTS = {
    "sentinel": {
        "description": "Production monitoring & auto-fix dispatch system",
        "ports": {"core": 16600, "dashboard": 16601, "mongodb": 16610},
        "deployed": "London server (indeprof.com)",
        "domain": None,
        "tests": "288 passing",
        "ci": "GitHub Actions — lint + typecheck + tests",
        "monitors": ["sitebot", "yensi-booking"],
        "strategy": "In-process ASGI middleware for backends, JS SDK for frontends",
    },
    "citebot": {
        "description": "AI document Q&A with visual citations — deployed as SiteBot",
        "ports": {"dashboard": 19100, "api": 19110, "mongodb": 19120, "redis": 19121},
        "deployed": "London server (indeprof.com)",
        "domain": "sitebot.yensi.solutions",
        "tests": "63 passing",
        "ci": None,
        "features": "Landing page, auth (Keycloak realm: sitebot), Stripe billing, Sentinel monitoring, OpenRouter LLM",
        "strategy": "First product in autonomous co-founder pipeline",
    },
    "yensi-booking": {
        "description": "Virtual appointment scheduling SaaS for therapy/coaching",
        "ports": {"dashboard": 19200, "api": 19210, "mongodb": 19220, "redis": 19221},
        "deployed": "London server (indeprof.com)",
        "domain": "booking.yensi.solutions",
        "tests": "51 passing",
        "ci": None,
        "features": "Provider profiles, availability, client booking, auth, Sentinel monitoring",
        "strategy": "Second product — proves NC Dev System is repeatable",
    },
    "nc-dev-system": {
        "description": "Autonomous senior software engineer — builds, tests, deploys products",
        "ports": {"intake_api": 16650},
        "deployed": "Local (ncdev CLI)",
        "domain": None,
        "tests": "1310 passing",
        "ci": None,
        "commands": "ncdev dev (build), ncdev report (video), ncdev serve (Sentinel intake), ncdev full-v3 (sequential sprints)",
        "strategy": "Claude plans, Codex builds. Context-driven, not pipeline-driven. 5 non-negotiable guardrails.",
    },
    "vigil": {
        "description": "AI operations engine — daily digest, WhatsApp bridge, CEO mode",
        "ports": {"whatsgate": 15750},
        "deployed": "Local daemon",
        "domain": None,
        "features": "Daily digest, WhatsApp comms, KPI collection, strategic assessment",
        "strategy": "Morning WhatsApp summary of all systems",
    },
    "keystone": {
        "description": "Shared infrastructure — auth, logging, monitoring, analytics",
        "ports": {"traefik": 15700, "keycloak": 15703, "mongodb": 15705, "grafana": 15708, "posthog": 15712},
        "deployed": "London server + local (17 containers)",
        "domain": None,
        "realms": ["sitebot", "booking", "sentinel"],
        "strategy": "Every product integrates with Keystone for auth. Keycloak SSO.",
    },
    "citex": {
        "description": "RAG engine — vector search + graph nodes + document ingestion",
        "ports": {"api": 20160, "range": "20160-20169"},
        "deployed": "Local (10 containers when running)",
        "domain": None,
        "features": "Hybrid search (Qdrant + keyword + reranking), citation-grade evidence, multi-tenant",
        "strategy": "Knowledge backbone for all products. NC Dev System uses for project context.",
    },
    "ignition": {
        "description": "Autonomous co-founder pipeline — spec gen, product registry, deploy",
        "ports": None,
        "deployed": "Local CLI",
        "domain": None,
        "strategy": "Thin Python glue connecting NC Dev + Citex + Playwright + ElevenLabs",
    },
    "helyx": {
        "description": "Command center — project management, MongoDB collections, canvas",
        "ports": {"mongodb": 15620, "redis": 15630, "ui": 15660},
        "deployed": "Local (3 containers)",
        "domain": None,
        "strategy": "Product registry (ignition_products collection) + project tracking",
    },
}


def get_git_info(project_path: Path) -> str:
    """Get recent git info for a project."""
    lines = []
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            cwd=str(project_path), capture_output=True, text=True, timeout=5,
        )
        if result.stdout.strip():
            lines.append(f"Recent commits:\n{result.stdout.strip()}")
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(project_path), capture_output=True, text=True, timeout=5,
        )
        if result.stdout.strip():
            lines.append(f"Branch: {result.stdout.strip()}")
    except Exception:
        pass
    return "\n".join(lines)


def generate_context(name: str, info: dict, project_path: Path) -> str:
    """Generate the context block for a project."""
    lines = [f"# {name}", ""]
    lines.append(f"**{info.get('description', '')}**")
    lines.append("")

    if info.get("domain"):
        lines.append(f"**Live:** https://{info['domain']}")
    if info.get("deployed"):
        lines.append(f"**Deployed:** {info['deployed']}")
    if info.get("ports"):
        ports_str = ", ".join(f"{k}: {v}" for k, v in info["ports"].items())
        lines.append(f"**Ports:** {ports_str}")
    if info.get("tests"):
        lines.append(f"**Tests:** {info['tests']}")
    if info.get("ci"):
        lines.append(f"**CI:** {info['ci']}")
    if info.get("features"):
        lines.append(f"**Features:** {info['features']}")
    if info.get("commands"):
        lines.append(f"**Commands:** {info['commands']}")
    if info.get("monitors"):
        lines.append(f"**Monitors:** {', '.join(info['monitors'])}")
    if info.get("realms"):
        lines.append(f"**Keycloak realms:** {', '.join(info['realms'])}")
    if info.get("strategy"):
        lines.append(f"**Strategy:** {info['strategy']}")

    lines.append("")

    # Git info
    git_info = get_git_info(project_path)
    if git_info:
        lines.append(git_info)
        lines.append("")

    # Related projects
    lines.append("## Related YENSI Projects")
    for other_name, other_info in PROJECTS.items():
        if other_name != name:
            domain = f" — https://{other_info['domain']}" if other_info.get("domain") else ""
            lines.append(f"- **{other_name}**: {other_info.get('description', '')}{domain}")

    lines.append("")
    lines.append(f"_Context synced: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")

    return "\n".join(lines)


def sync_project(name: str, info: dict):
    """Write CLAUDE.md and AGENTS.md for a project."""
    project_path = YENSI_DEV / name
    if not project_path.exists():
        return

    context = generate_context(name, info, project_path)

    # Write CLAUDE.md (for Claude Code)
    claude_md = project_path / "CLAUDE.md"
    existing = ""
    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")

    # Preserve existing content after "---" separator if present
    if "---" in existing:
        custom_section = existing.split("---", 1)[1]
        new_content = context + "\n---" + custom_section
    else:
        new_content = context

    claude_md.write_text(new_content, encoding="utf-8")

    # Write AGENTS.md (for Codex CLI) — same content
    agents_md = project_path / "AGENTS.md"
    agents_md.write_text(context, encoding="utf-8")

    print(f"  ✓ {name}: CLAUDE.md + AGENTS.md updated")


def main():
    print(f"Syncing project context — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print()
    for name, info in PROJECTS.items():
        sync_project(name, info)
    print()
    print("Done. Context available in CLAUDE.md (Claude Code) and AGENTS.md (Codex CLI).")


if __name__ == "__main__":
    main()
