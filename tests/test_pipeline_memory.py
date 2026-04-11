"""Tests for pipeline memory safety integration."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Config
from src.pipeline import Pipeline


class TestPhase3ReturnExceptions:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase3_handles_builder_exception(self, tmp_path):
        """Verify gather uses return_exceptions=True so crashes don't propagate."""
        config = Config(output_dir=tmp_path)
        config.ensure_directories()
        pipeline = Pipeline(config)

        features = [{"name": "test-feature", "description": "test"}]
        config.features_path.write_text(json.dumps(features))

        with (
            patch.object(pipeline, "_build_single_feature", new_callable=AsyncMock) as mock_build,
            patch("src.pipeline.cleanup_resources", new_callable=AsyncMock),
            patch("src.pipeline.log_memory_checkpoint") as mock_cp,
        ):
            mock_build.side_effect = MemoryError("simulated OOM")
            mock_cp.return_value = (MagicMock(), MagicMock(value="ok"))

            result = await pipeline.phase3_build()
            assert result["features_failed"] >= 1


class TestCleanupBetweenPhases:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_called_after_phase(self, tmp_path):
        """Verify cleanup_resources runs between phases."""
        config = Config(output_dir=tmp_path, phases=[3])
        config.ensure_directories()
        pipeline = Pipeline(config)

        with (
            patch.object(pipeline, "phase3_build", new_callable=AsyncMock) as mock_p3,
            patch("src.pipeline.cleanup_resources", new_callable=AsyncMock) as mock_cleanup,
            patch("src.pipeline.log_memory_checkpoint") as mock_cp,
        ):
            mock_p3.return_value = {"features_built": 0, "features_failed": 0}
            from src.memory import MemoryPressure
            mock_cp.return_value = (MagicMock(), MemoryPressure.OK)

            pipeline.state["requirements_path"] = str(tmp_path / "req.md")
            (tmp_path / "req.md").write_text("# Test")
            await pipeline.run(str(tmp_path / "req.md"))

            assert mock_cleanup.call_count >= 1
