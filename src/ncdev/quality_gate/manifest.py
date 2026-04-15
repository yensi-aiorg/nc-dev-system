"""Fix Manifest Generator — converts Test Craftr API responses into fix manifests."""

from __future__ import annotations

from collections import defaultdict

from ncdev.quality_gate.models import FixIssue, FixManifest, IssueEvidence, QualityScores


# Maps TC severity levels to internal priority codes.
_SEVERITY_PRIORITY_MAP: dict[str, str] = {
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
}

# Maps TC issue types to the persona responsible for fixing.
_TYPE_PERSONA_MAP: dict[str, str] = {
    "functionality": "user",
    "visual": "inspector",
    "performance": "inspector",
    "network": "user",
    "console": "destroyer",
    "accessibility": "inspector",
    "ux": "inspector",
    "security": "destroyer",
}

# Priority sort order (lower index = higher priority).
_PRIORITY_ORDER: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

# Type sort order — functionality first (most fixable), visual last (least fixable by code).
_TYPE_ORDER: dict[str, int] = {
    "functionality": 0,
    "network": 1,
    "console": 2,
    "ux": 3,
    "visual": 4,
    "accessibility": 5,
    "performance": 6,
    "security": 7,
}


class ManifestGenerator:
    """Converts Test Craftr issue lists into FixManifest objects for ncdev fix."""

    def generate(
        self,
        run_id: str,
        target_path: str,
        tc_issues: list[dict],
        scores: dict,
    ) -> FixManifest:
        """Convert TC issues into a sorted FixManifest."""
        quality_scores = QualityScores(**scores)
        fix_issues: list[FixIssue] = []

        for issue in tc_issues:
            ctx = issue.get("context", {})
            url = ctx.get("url", "")
            action = ctx.get("action_attempted", "")

            fix_issues.append(
                FixIssue(
                    id=issue["id"],
                    priority=self._severity_to_priority(issue.get("severity", "low")),
                    persona=_TYPE_PERSONA_MAP.get(issue.get("type", ""), "user"),
                    category=issue.get("type", "unknown"),
                    title=issue.get("title", ""),
                    flow=f"{url} → {action}" if url or action else "",
                    expected=ctx.get("expected", ""),
                    actual=ctx.get("actual", ""),
                    root_cause_hint="",
                    reproduction=[
                        f"Navigate to {url}",
                        f"Attempt: {action}",
                        f"Observe: {ctx.get('actual', '')}",
                    ],
                    evidence=IssueEvidence(),
                    affected_files_hint=[ctx.get("element_selector", "")]
                    if ctx.get("element_selector")
                    else [],
                )
            )

        # Sort by priority first, then by type (functionality before visual).
        fix_issues.sort(key=lambda i: (
            _PRIORITY_ORDER.get(i.priority, 99),
            _TYPE_ORDER.get(i.category, 50),
        ))

        return FixManifest(
            run_id=run_id,
            target_path=target_path,
            scores=quality_scores,
            issues=fix_issues,
        )

    @staticmethod
    def _severity_to_priority(severity: str) -> str:
        """Map TC severity to internal priority code."""
        return _SEVERITY_PRIORITY_MAP.get(severity, "P3")

    @staticmethod
    def _group_related(tc_issues: list[dict]) -> list[list[dict]]:
        """Group issues that share the same URL for batch fixing."""
        groups: dict[str, list[dict]] = defaultdict(list)
        for issue in tc_issues:
            url = issue.get("context", {}).get("url", "")
            groups[url].append(issue)
        return list(groups.values())
