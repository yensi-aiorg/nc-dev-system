"""Quality Gate Events Publisher — publishes ncdev.* and pipeline.* events to Redis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis


class NCDevPublisher:
    """Publishes quality-gate events to the pipeline:events Redis channel."""

    CHANNEL = "pipeline:events"

    def __init__(self, redis_url: str = "redis://localhost:16633") -> None:
        self.redis_url = redis_url
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        """Create an async Redis connection."""
        self._redis = redis.from_url(self.redis_url)

    async def disconnect(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def _publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish a JSON envelope to the pipeline:events channel."""
        envelope = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        assert self._redis is not None, "Call connect() before publishing"
        await self._redis.publish(self.CHANNEL, json.dumps(envelope))

    # ------------------------------------------------------------------
    # Build events (ncdev.build.*)
    # ------------------------------------------------------------------

    async def publish_build_started(
        self, project_name: str, feature_count: int
    ) -> None:
        await self._publish(
            "ncdev.build.started",
            {"project_name": project_name, "feature_count": feature_count},
        )

    async def publish_feature_building(
        self, feature_id: str, feature_name: str, progress: float
    ) -> None:
        await self._publish(
            "ncdev.build.feature_building",
            {
                "feature_id": feature_id,
                "feature_name": feature_name,
                "progress": progress,
            },
        )

    async def publish_feature_passed(
        self, feature_id: str, feature_name: str, duration_s: float
    ) -> None:
        await self._publish(
            "ncdev.build.feature_passed",
            {
                "feature_id": feature_id,
                "feature_name": feature_name,
                "duration_s": duration_s,
            },
        )

    async def publish_feature_failed(
        self, feature_id: str, feature_name: str, reason: str
    ) -> None:
        await self._publish(
            "ncdev.build.feature_failed",
            {
                "feature_id": feature_id,
                "feature_name": feature_name,
                "reason": reason,
            },
        )

    async def publish_build_complete(
        self, features_passed: int, features_failed: int
    ) -> None:
        await self._publish(
            "ncdev.build.complete",
            {
                "features_passed": features_passed,
                "features_failed": features_failed,
            },
        )

    # ------------------------------------------------------------------
    # Fix events (ncdev.fix.*)
    # ------------------------------------------------------------------

    async def publish_fix_started(self, cycle: int, issue_count: int) -> None:
        await self._publish(
            "ncdev.fix.started",
            {"cycle": cycle, "issue_count": issue_count},
        )

    async def publish_fix_issue(
        self, cycle: int, issue_id: str, title: str
    ) -> None:
        await self._publish(
            "ncdev.fix.issue",
            {"cycle": cycle, "issue_id": issue_id, "title": title},
        )

    async def publish_fix_complete(
        self, cycle: int, issues_fixed: int, issues_remaining: int
    ) -> None:
        await self._publish(
            "ncdev.fix.complete",
            {
                "cycle": cycle,
                "issues_fixed": issues_fixed,
                "issues_remaining": issues_remaining,
            },
        )

    async def publish_idle(self, reason: str = "Waiting for Test Craftr") -> None:
        await self._publish("ncdev.idle", {"reason": reason})

    # ------------------------------------------------------------------
    # Pipeline events (pipeline.*)
    # ------------------------------------------------------------------

    async def publish_cycle_started(self, cycle: int) -> None:
        await self._publish("pipeline.cycle.started", {"cycle": cycle})

    async def publish_cycle_complete(
        self, cycle: int, core_flow: int, resilience: int, polish: int
    ) -> None:
        await self._publish(
            "pipeline.cycle.complete",
            {
                "cycle": cycle,
                "core_flow": core_flow,
                "resilience": resilience,
                "polish": polish,
            },
        )

    async def publish_pipeline_passed(
        self,
        core_flow: int,
        resilience: int,
        polish: int,
        total_cycles: int,
    ) -> None:
        await self._publish(
            "pipeline.passed",
            {
                "core_flow": core_flow,
                "resilience": resilience,
                "polish": polish,
                "total_cycles": total_cycles,
            },
        )

    async def publish_pipeline_failed(
        self, reason: str, core_flow: int, resilience: int, polish: int
    ) -> None:
        await self._publish(
            "pipeline.failed",
            {
                "reason": reason,
                "core_flow": core_flow,
                "resilience": resilience,
                "polish": polish,
            },
        )

    async def publish_regression_detected(
        self, cycle: int, details: str
    ) -> None:
        await self._publish(
            "pipeline.regression_detected",
            {"cycle": cycle, "details": details},
        )
