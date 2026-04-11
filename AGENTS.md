# nc-dev-system

**Autonomous senior software engineer — builds, tests, deploys products**

**Deployed:** Local (ncdev CLI)
**Ports:** intake_api: 16650
**Tests:** 1310 passing
**Commands:** ncdev dev (build), ncdev report (video), ncdev serve (Sentinel intake), ncdev full-v3 (sequential sprints)
**Strategy:** Claude plans, Codex builds. Context-driven, not pipeline-driven. 5 non-negotiable guardrails.

Recent commits:
4d87450 feat: sync-project-context — auto-populates CLAUDE.md + AGENTS.md for all projects
16784e1 fix(dev): harden pipeline — brownfield timeouts, non-fatal video, separate report cmd
d98458a fix(dev): treat Claude planning timeout as non-fatal if instructions file exists
010a7e8 feat(serve): wire intake API to uvicorn for Sentinel integration
47dd45e refactor(dev): Claude plans, Codex builds — clear role separation
Branch: main

## Related YENSI Projects
- **sentinel**: Production monitoring & auto-fix dispatch system
- **citebot**: AI document Q&A with visual citations — deployed as SiteBot — https://sitebot.yensi.solutions
- **yensi-booking**: Virtual appointment scheduling SaaS for therapy/coaching — https://booking.yensi.solutions
- **vigil**: AI operations engine — daily digest, WhatsApp bridge, CEO mode
- **keystone**: Shared infrastructure — auth, logging, monitoring, analytics
- **citex**: RAG engine — vector search + graph nodes + document ingestion
- **ignition**: Autonomous co-founder pipeline — spec gen, product registry, deploy
- **helyx**: Command center — project management, MongoDB collections, canvas

_Context synced: 2026-04-11 05:00 UTC_