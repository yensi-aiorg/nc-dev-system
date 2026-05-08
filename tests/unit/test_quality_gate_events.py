"""Tests for quality gate Redis events publisher."""

import json
from unittest.mock import AsyncMock

import pytest

from ncdev.quality_gate.events import NCDevPublisher


@pytest.fixture
def publisher() -> NCDevPublisher:
    """Return a publisher with a mocked Redis connection."""
    pub = NCDevPublisher(redis_url="redis://localhost:16633")
    pub._redis = AsyncMock()
    return pub


class TestNCDevPublisherInit:
    def test_defaults(self):
        pub = NCDevPublisher()
        assert pub.redis_url == "redis://localhost:16633"
        assert pub._redis is None

    def test_custom_url(self):
        pub = NCDevPublisher(redis_url="redis://other:6379")
        assert pub.redis_url == "redis://other:6379"


class TestBuildEvents:
    @pytest.mark.asyncio
    async def test_build_started(self, publisher: NCDevPublisher):
        await publisher.publish_build_started("my-project", 5)

        publisher._redis.publish.assert_awaited_once()
        channel, payload = publisher._redis.publish.call_args.args
        assert channel == "pipeline:events"
        envelope = json.loads(payload)
        assert envelope["type"] == "ncdev.build.started"
        assert envelope["data"]["project_name"] == "my-project"
        assert envelope["data"]["feature_count"] == 5
        assert "timestamp" in envelope

    @pytest.mark.asyncio
    async def test_feature_passed(self, publisher: NCDevPublisher):
        await publisher.publish_feature_passed("f-1", "Login", 12.5)

        channel, payload = publisher._redis.publish.call_args.args
        envelope = json.loads(payload)
        assert envelope["type"] == "ncdev.build.feature_passed"
        assert envelope["data"]["feature_id"] == "f-1"
        assert envelope["data"]["feature_name"] == "Login"
        assert envelope["data"]["duration_s"] == 12.5

    @pytest.mark.asyncio
    async def test_build_complete(self, publisher: NCDevPublisher):
        await publisher.publish_build_complete(8, 2)

        envelope = json.loads(publisher._redis.publish.call_args.args[1])
        assert envelope["type"] == "ncdev.build.complete"
        assert envelope["data"]["features_passed"] == 8
        assert envelope["data"]["features_failed"] == 2


class TestFixEvents:
    @pytest.mark.asyncio
    async def test_fix_started(self, publisher: NCDevPublisher):
        await publisher.publish_fix_started(cycle=3, issue_count=7)

        envelope = json.loads(publisher._redis.publish.call_args.args[1])
        assert envelope["type"] == "ncdev.fix.started"
        assert envelope["data"]["cycle"] == 3
        assert envelope["data"]["issue_count"] == 7

    @pytest.mark.asyncio
    async def test_fix_complete(self, publisher: NCDevPublisher):
        await publisher.publish_fix_complete(cycle=3, issues_fixed=5, issues_remaining=2)

        envelope = json.loads(publisher._redis.publish.call_args.args[1])
        assert envelope["type"] == "ncdev.fix.complete"
        assert envelope["data"]["issues_fixed"] == 5
        assert envelope["data"]["issues_remaining"] == 2

    @pytest.mark.asyncio
    async def test_idle_default_reason(self, publisher: NCDevPublisher):
        await publisher.publish_idle()

        envelope = json.loads(publisher._redis.publish.call_args.args[1])
        assert envelope["type"] == "ncdev.idle"
        assert envelope["data"]["reason"] == "Waiting for Test Craftr"


class TestPipelineEvents:
    @pytest.mark.asyncio
    async def test_pipeline_passed(self, publisher: NCDevPublisher):
        await publisher.publish_pipeline_passed(
            core_flow=95, resilience=85, polish=75, total_cycles=4
        )

        envelope = json.loads(publisher._redis.publish.call_args.args[1])
        assert envelope["type"] == "pipeline.passed"
        assert envelope["data"]["core_flow"] == 95
        assert envelope["data"]["total_cycles"] == 4

    @pytest.mark.asyncio
    async def test_pipeline_failed(self, publisher: NCDevPublisher):
        await publisher.publish_pipeline_failed(
            reason="Max cycles exceeded",
            core_flow=60, resilience=40, polish=30,
        )

        envelope = json.loads(publisher._redis.publish.call_args.args[1])
        assert envelope["type"] == "pipeline.failed"
        assert envelope["data"]["reason"] == "Max cycles exceeded"

    @pytest.mark.asyncio
    async def test_regression_detected(self, publisher: NCDevPublisher):
        await publisher.publish_regression_detected(cycle=2, details="core_flow dropped 95->80")

        envelope = json.loads(publisher._redis.publish.call_args.args[1])
        assert envelope["type"] == "pipeline.regression_detected"
        assert envelope["data"]["cycle"] == 2
        assert envelope["data"]["details"] == "core_flow dropped 95->80"

    @pytest.mark.asyncio
    async def test_cycle_complete(self, publisher: NCDevPublisher):
        await publisher.publish_cycle_complete(cycle=1, core_flow=90, resilience=80, polish=70)

        envelope = json.loads(publisher._redis.publish.call_args.args[1])
        assert envelope["type"] == "pipeline.cycle.complete"
        assert envelope["data"]["cycle"] == 1


class TestEnvelopeFormat:
    @pytest.mark.asyncio
    async def test_envelope_has_iso_timestamp(self, publisher: NCDevPublisher):
        await publisher.publish_build_started("proj", 1)

        envelope = json.loads(publisher._redis.publish.call_args.args[1])
        ts = envelope["timestamp"]
        # Should end with +00:00 (UTC)
        assert "+00:00" in ts or ts.endswith("Z")

    @pytest.mark.asyncio
    async def test_all_publishes_go_to_pipeline_events_channel(
        self, publisher: NCDevPublisher
    ):
        await publisher.publish_cycle_started(1)

        channel = publisher._redis.publish.call_args.args[0]
        assert channel == "pipeline:events"
