"""Unit tests for AI vision analysis (src.tester.vision).

Tests cover:
- _encode_image_base64 helper
- _parse_json_response with valid, fenced, and unparseable input
- _dict_to_vision_result conversion
- VisionAnalyzer.__init__ defaults and custom values
- VisionAnalyzer.analyze_screenshot with Ollama mock (success, high confidence)
- VisionAnalyzer.analyze_screenshot with Ollama escalation to Claude
- VisionAnalyzer.analyze_screenshot when Ollama is unavailable (fallback)
- VisionAnalyzer._ollama_analyze (mock httpx)
- VisionAnalyzer._claude_analyze (mock subprocess)
- VisionAnalyzer._run_claude_cli error handling
- VisionAnalyzer.analyze_batch with multiple screenshots
- Confidence threshold handling
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tester.results import VisionIssue, VisionResult
from src.tester.vision import (
    VisionAnalyzer,
    _dict_to_vision_result,
    _encode_image_base64,
    _parse_json_response,
)


# ---------------------------------------------------------------------------
# _encode_image_base64
# ---------------------------------------------------------------------------

class TestEncodeImageBase64:
    @pytest.mark.unit
    def test_encodes_file_contents(self, tmp_path: Path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\x00\x01\x02\x03")

        result = _encode_image_base64(img)
        decoded = base64.b64decode(result)
        assert decoded == b"\x89PNG\x00\x01\x02\x03"

    @pytest.mark.unit
    def test_returns_string(self, tmp_path: Path):
        img = tmp_path / "img.png"
        img.write_bytes(b"data")

        result = _encode_image_base64(img)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------

class TestParseJsonResponse:
    @pytest.mark.unit
    def test_valid_json(self):
        raw = '{"passed": true, "confidence": 0.95, "issues": []}'
        result = _parse_json_response(raw)
        assert result["passed"] is True
        assert result["confidence"] == 0.95
        assert result["issues"] == []

    @pytest.mark.unit
    def test_fenced_json(self):
        raw = "```json\n{\"passed\": false, \"confidence\": 0.5, \"issues\": []}\n```"
        result = _parse_json_response(raw)
        assert result["passed"] is False

    @pytest.mark.unit
    def test_preamble_text(self):
        raw = "Here is my analysis:\n\n{\"passed\": true, \"confidence\": 0.8, \"issues\": []}"
        result = _parse_json_response(raw)
        assert result["passed"] is True

    @pytest.mark.unit
    def test_unparseable_returns_failure(self):
        raw = "This is not JSON at all. No braces."
        result = _parse_json_response(raw)
        assert result["passed"] is False
        assert result["confidence"] == 0.0
        assert len(result["issues"]) > 0
        assert "unparseable" in result["issues"][0]["description"]

    @pytest.mark.unit
    def test_empty_string(self):
        result = _parse_json_response("")
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# _dict_to_vision_result
# ---------------------------------------------------------------------------

class TestDictToVisionResult:
    @pytest.mark.unit
    def test_basic_conversion(self, tmp_path: Path):
        data = {
            "passed": True,
            "confidence": 0.9,
            "issues": [],
            "suggestions": ["Add alt text"],
        }
        result = _dict_to_vision_result(data, tmp_path / "ss.png", "ollama", route="/", viewport="desktop")

        assert isinstance(result, VisionResult)
        assert result.passed is True
        assert result.confidence == 0.9
        assert result.route == "/"
        assert result.viewport == "desktop"
        assert result.analyzer == "ollama"
        assert "Add alt text" in result.suggestions

    @pytest.mark.unit
    def test_with_issues(self, tmp_path: Path):
        data = {
            "passed": False,
            "confidence": 0.6,
            "issues": [
                {
                    "severity": "critical",
                    "description": "Text overflow",
                    "element": ".title",
                    "suggestion": "Add overflow: hidden",
                },
                {
                    "severity": "warning",
                    "description": "Low contrast",
                    "element": ".subtitle",
                    "suggestion": "Increase contrast ratio",
                },
            ],
            "suggestions": [],
        }
        result = _dict_to_vision_result(data, tmp_path / "ss.png", "claude")

        assert result.passed is False
        assert len(result.issues) == 2
        assert result.issues[0].severity == "critical"
        assert result.issues[0].description == "Text overflow"

    @pytest.mark.unit
    def test_missing_optional_fields(self, tmp_path: Path):
        data = {"passed": True}
        result = _dict_to_vision_result(data, tmp_path / "ss.png", "ollama")

        assert result.issues == []
        assert result.suggestions == []
        assert result.confidence == 0.5  # default when not present

    @pytest.mark.unit
    def test_raw_response_stored(self, tmp_path: Path):
        data = {"passed": True, "confidence": 1.0, "issues": []}
        result = _dict_to_vision_result(data, tmp_path / "ss.png", "ollama")

        assert result.raw_response
        parsed_raw = json.loads(result.raw_response)
        assert parsed_raw["passed"] is True


# ---------------------------------------------------------------------------
# VisionAnalyzer.__init__
# ---------------------------------------------------------------------------

class TestVisionAnalyzerInit:
    @pytest.mark.unit
    def test_defaults(self):
        analyzer = VisionAnalyzer()
        assert analyzer.ollama_url == "http://localhost:11434"
        assert analyzer.ollama_model == "qwen2.5vl:7b"
        assert analyzer.confidence_threshold == 0.7
        assert analyzer.claude_model == "sonnet"
        assert analyzer.timeout_seconds == 120

    @pytest.mark.unit
    def test_custom_values(self):
        analyzer = VisionAnalyzer(
            ollama_url="http://gpu-server:11434",
            ollama_model="llava:13b",
            confidence_threshold=0.8,
            claude_model="opus",
            timeout_seconds=60,
        )
        assert analyzer.ollama_url == "http://gpu-server:11434"
        assert analyzer.ollama_model == "llava:13b"
        assert analyzer.confidence_threshold == 0.8
        assert analyzer.claude_model == "opus"

    @pytest.mark.unit
    def test_trailing_slash_stripped(self):
        analyzer = VisionAnalyzer(ollama_url="http://localhost:11434/")
        assert analyzer.ollama_url == "http://localhost:11434"


# ---------------------------------------------------------------------------
# VisionAnalyzer.analyze_screenshot (Ollama success, no escalation)
# ---------------------------------------------------------------------------

class TestAnalyzeScreenshotOllamaSuccess:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_high_confidence_no_escalation(self, tmp_path: Path):
        analyzer = VisionAnalyzer(confidence_threshold=0.7)
        screenshot = tmp_path / "page.png"
        screenshot.write_bytes(b"\x89PNG\x00")

        ollama_response_data = {
            "passed": True,
            "confidence": 0.95,
            "issues": [],
            "suggestions": [],
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": json.dumps(ollama_response_data)}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await analyzer.analyze_screenshot(screenshot, route="/", viewport="desktop")

        assert result.passed is True
        assert result.confidence == 0.95
        assert result.analyzer == "ollama"
        assert result.issues == []


# ---------------------------------------------------------------------------
# VisionAnalyzer.analyze_screenshot (escalation to Claude)
# ---------------------------------------------------------------------------

class TestAnalyzeScreenshotEscalation:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_low_confidence_triggers_escalation(self, tmp_path: Path):
        analyzer = VisionAnalyzer(confidence_threshold=0.7)
        screenshot = tmp_path / "page.png"
        screenshot.write_bytes(b"\x89PNG\x00")

        # Ollama returns low confidence
        ollama_data = {
            "passed": True,
            "confidence": 0.4,
            "issues": [],
            "suggestions": [],
        }
        mock_ollama_resp = MagicMock()
        mock_ollama_resp.json.return_value = {"response": json.dumps(ollama_data)}
        mock_ollama_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_ollama_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        # Claude returns higher confidence
        claude_data = json.dumps({
            "passed": True,
            "confidence": 0.92,
            "issues": [],
            "suggestions": [],
        })

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(claude_data.encode(), b""))
        mock_proc.returncode = 0

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch("asyncio.wait_for", return_value=(claude_data.encode(), b"")):
                    result = await analyzer.analyze_screenshot(screenshot, route="/", viewport="desktop")

        assert result.analyzer == "claude"
        assert result.confidence == 0.92

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_critical_issue_triggers_escalation(self, tmp_path: Path):
        analyzer = VisionAnalyzer(confidence_threshold=0.7)
        screenshot = tmp_path / "page.png"
        screenshot.write_bytes(b"\x89PNG\x00")

        # Ollama returns critical issue with high confidence
        ollama_data = {
            "passed": False,
            "confidence": 0.9,
            "issues": [
                {"severity": "critical", "description": "Page is blank", "element": "body", "suggestion": "Check render"}
            ],
            "suggestions": [],
        }
        mock_ollama_resp = MagicMock()
        mock_ollama_resp.json.return_value = {"response": json.dumps(ollama_data)}
        mock_ollama_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_ollama_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        # Claude confirms
        claude_data = json.dumps({
            "passed": False,
            "confidence": 0.95,
            "issues": [{"severity": "critical", "description": "Page blank", "element": "", "suggestion": ""}],
            "suggestions": [],
        })
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(claude_data.encode(), b""))
        mock_proc.returncode = 0

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch("asyncio.wait_for", return_value=(claude_data.encode(), b"")):
                    result = await analyzer.analyze_screenshot(screenshot, route="/")

        assert result.analyzer == "claude"
        assert result.passed is False


# ---------------------------------------------------------------------------
# VisionAnalyzer when Ollama is unavailable
# ---------------------------------------------------------------------------

class TestAnalyzeScreenshotOllamaUnavailable:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ollama_connection_error_escalates(self, tmp_path: Path):
        analyzer = VisionAnalyzer(confidence_threshold=0.7)
        screenshot = tmp_path / "page.png"
        screenshot.write_bytes(b"\x89PNG\x00")

        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        # Claude fallback
        claude_data = json.dumps({
            "passed": True,
            "confidence": 0.88,
            "issues": [],
            "suggestions": [],
        })
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(claude_data.encode(), b""))
        mock_proc.returncode = 0

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch("asyncio.wait_for", return_value=(claude_data.encode(), b"")):
                    result = await analyzer.analyze_screenshot(screenshot, route="/")

        assert result.analyzer == "claude"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ollama_timeout_escalates(self, tmp_path: Path):
        analyzer = VisionAnalyzer(confidence_threshold=0.7)
        screenshot = tmp_path / "page.png"
        screenshot.write_bytes(b"\x89PNG\x00")

        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        claude_data = json.dumps({"passed": True, "confidence": 0.9, "issues": [], "suggestions": []})
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(claude_data.encode(), b""))
        mock_proc.returncode = 0

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch("asyncio.wait_for", return_value=(claude_data.encode(), b"")):
                    result = await analyzer.analyze_screenshot(screenshot, route="/")

        assert result.analyzer == "claude"


# ---------------------------------------------------------------------------
# VisionAnalyzer.analyze_screenshot -- missing file
# ---------------------------------------------------------------------------

class TestAnalyzeScreenshotMissingFile:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_screenshot_returns_failure(self, tmp_path: Path):
        analyzer = VisionAnalyzer()
        result = await analyzer.analyze_screenshot(tmp_path / "nonexistent.png")

        assert result.passed is False
        assert result.confidence == 0.0
        assert result.analyzer == "none"
        assert len(result.issues) == 1
        assert result.issues[0].severity == "critical"
        assert "not found" in result.issues[0].description


# ---------------------------------------------------------------------------
# VisionAnalyzer._claude_analyze failure handling
# ---------------------------------------------------------------------------

class TestClaudeAnalyzeFailure:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_claude_cli_failure_falls_back_to_ollama(self, tmp_path: Path):
        analyzer = VisionAnalyzer()
        screenshot = tmp_path / "page.png"
        screenshot.write_bytes(b"\x89PNG\x00")

        pre_result = VisionResult(
            screenshot_path=str(screenshot),
            passed=False,
            confidence=0.4,
            issues=[VisionIssue(severity="warning", description="Low contrast")],
            analyzer="ollama",
        )

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("claude not found")):
            result = await analyzer._claude_analyze(screenshot, "", pre_result, route="/", viewport="desktop")

        # Should fall back to Ollama result
        assert result.passed is False
        assert result.confidence == 0.4
        assert "claude-fallback" in result.analyzer
        assert len(result.issues) == 1


# ---------------------------------------------------------------------------
# VisionAnalyzer.analyze_batch
# ---------------------------------------------------------------------------

class TestAnalyzeBatch:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_batch_analyzes_all_screenshots(self, tmp_path: Path):
        analyzer = VisionAnalyzer()

        ss1 = tmp_path / "ss1.png"
        ss2 = tmp_path / "ss2.png"
        ss1.write_bytes(b"\x89PNG")
        ss2.write_bytes(b"\x89PNG")

        screenshots = {
            "/": {"desktop": ss1},
            "/tasks": {"mobile": ss2},
        }

        async def _mock_analyze(path, context="", route="", viewport=""):
            return VisionResult(
                screenshot_path=str(path),
                route=route,
                viewport=viewport,
                passed=True,
                confidence=0.9,
                analyzer="mock",
            )

        with patch.object(analyzer, "analyze_screenshot", side_effect=_mock_analyze):
            results = await analyzer.analyze_batch(screenshots)

        assert len(results) == 2
        routes_found = {r.route for r in results}
        assert "/" in routes_found
        assert "/tasks" in routes_found

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_batch_empty_input(self):
        analyzer = VisionAnalyzer()
        results = await analyzer.analyze_batch({})
        assert results == []
