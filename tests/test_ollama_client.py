"""Unit tests for OllamaClient (src.ollama_client).

Tests cover:
- OllamaResponse dataclass
- OllamaClient.__init__
- OllamaClient.generate (success, connect error, timeout, HTTP error, unexpected error)
- OllamaClient.generate_with_fallback
- OllamaClient.vision (success, missing image, read error, connect error, timeout)
- OllamaClient.is_available
- OllamaClient.list_models
- OllamaClient.has_model
- OllamaClient.pull_model
- OllamaClient.ensure_model
- Static helpers: _extract_text, _extract_duration_ms
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.ollama_client import OllamaClient, OllamaResponse


# ---------------------------------------------------------------------------
# OllamaResponse
# ---------------------------------------------------------------------------


class TestOllamaResponse:
    @pytest.mark.unit
    def test_defaults(self):
        resp = OllamaResponse()
        assert resp.text == ""
        assert resp.model == ""
        assert resp.duration_ms == 0.0
        assert resp.success is True
        assert resp.error is None

    @pytest.mark.unit
    def test_custom_values(self):
        resp = OllamaResponse(
            text="hello world",
            model="llama3.1:8b",
            duration_ms=123.4,
            success=True,
        )
        assert resp.text == "hello world"
        assert resp.model == "llama3.1:8b"

    @pytest.mark.unit
    def test_error_response(self):
        resp = OllamaResponse(success=False, error="Connection refused")
        assert resp.success is False
        assert resp.error == "Connection refused"


# ---------------------------------------------------------------------------
# OllamaClient.__init__
# ---------------------------------------------------------------------------


class TestOllamaClientInit:
    @pytest.mark.unit
    def test_defaults(self):
        client = OllamaClient()
        assert client.base_url == "http://localhost:11434"
        assert client.timeout == 120

    @pytest.mark.unit
    def test_custom_url(self):
        client = OllamaClient(base_url="http://custom:8080/", timeout=60)
        assert client.base_url == "http://custom:8080"
        assert client.timeout == 60

    @pytest.mark.unit
    def test_trailing_slash_stripped(self):
        client = OllamaClient(base_url="http://host:1234/")
        assert client.base_url == "http://host:1234"


# ---------------------------------------------------------------------------
# Static helpers
# ---------------------------------------------------------------------------


class TestStaticHelpers:
    @pytest.mark.unit
    def test_extract_text(self):
        data = {"response": "Hello World"}
        assert OllamaClient._extract_text(data) == "Hello World"

    @pytest.mark.unit
    def test_extract_text_missing(self):
        assert OllamaClient._extract_text({}) == ""

    @pytest.mark.unit
    def test_extract_duration_ms(self):
        data = {"total_duration": 1_500_000_000}  # 1.5 seconds in nanoseconds
        result = OllamaClient._extract_duration_ms(data)
        assert abs(result - 1500.0) < 0.1

    @pytest.mark.unit
    def test_extract_duration_ms_missing(self):
        assert OllamaClient._extract_duration_ms({}) == 0.0


# ---------------------------------------------------------------------------
# OllamaClient.generate
# ---------------------------------------------------------------------------


class TestOllamaGenerate:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_generate(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "def hello(): pass",
            "model": "qwen2.5-coder:32b",
            "total_duration": 2_000_000_000,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.generate("Write hello world")

        assert result.success is True
        assert result.text == "def hello(): pass"
        assert result.model == "qwen2.5-coder:32b"
        assert result.duration_ms > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "result",
            "model": "test",
            "total_duration": 1_000_000,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.generate(
                "Write code", model="test", system="You are a coder"
            )

        assert result.success is True
        # Verify system prompt was included in the payload
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["system"] == "You are a coder"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_connect_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.generate("test prompt")

        assert result.success is False
        assert "Cannot connect" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_timeout(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.generate("test prompt")

        assert result.success is False
        assert "timed out" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=mock_resp
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.generate("test prompt")

        assert result.success is False
        assert "HTTP 500" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_unexpected_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("something weird"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.generate("test prompt")

        assert result.success is False
        assert "Unexpected error" in result.error


# ---------------------------------------------------------------------------
# OllamaClient.generate_with_fallback
# ---------------------------------------------------------------------------


class TestOllamaGenerateWithFallback:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_primary_succeeds(self):
        client = OllamaClient()
        primary_response = OllamaResponse(text="primary", success=True, model="primary")

        with patch.object(client, "generate", new=AsyncMock(return_value=primary_response)):
            result = await client.generate_with_fallback("test")

        assert result.text == "primary"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        client = OllamaClient()

        call_count = 0

        async def generate_side_effect(prompt, model="", system=""):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OllamaResponse(success=False, error="model not found")
            return OllamaResponse(text="fallback result", success=True, model="fallback")

        with patch.object(client, "generate", side_effect=generate_side_effect):
            result = await client.generate_with_fallback("test")

        assert result.success is True
        assert result.text == "fallback result"
        assert call_count == 2


# ---------------------------------------------------------------------------
# OllamaClient.vision
# ---------------------------------------------------------------------------


class TestOllamaVision:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_vision(self, tmp_path: Path):
        image_file = tmp_path / "screenshot.png"
        image_file.write_bytes(b"\x89PNG\r\n\x1a\n fake png data")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "The image shows a login page",
            "model": "qwen2.5vl:7b",
            "total_duration": 3_000_000_000,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.vision(
                image_path=str(image_file),
                prompt="Describe this UI",
            )

        assert result.success is True
        assert "login page" in result.text

        # Verify the image was base64-encoded in the request
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert "images" in payload
        assert len(payload["images"]) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vision_file_not_found(self):
        client = OllamaClient()
        result = await client.vision(
            image_path="/nonexistent/screenshot.png",
            prompt="describe",
        )
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vision_file_read_error(self, tmp_path: Path):
        image_file = tmp_path / "unreadable.png"
        image_file.write_bytes(b"data")

        client = OllamaClient()

        with patch.object(Path, "read_bytes", side_effect=OSError("disk error")):
            result = await client.vision(
                image_path=str(image_file),
                prompt="describe",
            )

        assert result.success is False
        assert "Could not read" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vision_connect_error(self, tmp_path: Path):
        image_file = tmp_path / "img.png"
        image_file.write_bytes(b"data")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.vision(
                image_path=str(image_file),
                prompt="describe",
            )

        assert result.success is False
        assert "Cannot connect" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vision_timeout(self, tmp_path: Path):
        image_file = tmp_path / "img.png"
        image_file.write_bytes(b"data")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.vision(
                image_path=str(image_file),
                prompt="describe",
            )

        assert result.success is False
        assert "timed out" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vision_http_error(self, tmp_path: Path):
        image_file = tmp_path / "img.png"
        image_file.write_bytes(b"data")

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Model not found"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_resp
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.vision(
                image_path=str(image_file),
                prompt="describe",
            )

        assert result.success is False
        assert "HTTP 404" in result.error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vision_unexpected_error(self, tmp_path: Path):
        image_file = tmp_path / "img.png"
        image_file.write_bytes(b"data")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("unexpected"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.vision(
                image_path=str(image_file),
                prompt="describe",
            )

        assert result.success is False
        assert "Unexpected error" in result.error


# ---------------------------------------------------------------------------
# OllamaClient.is_available
# ---------------------------------------------------------------------------


class TestOllamaIsAvailable:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_available(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.is_available()

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_not_available_connect_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.is_available()

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_not_available_non_200(self):
        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.is_available()

        assert result is False


# ---------------------------------------------------------------------------
# OllamaClient.list_models
# ---------------------------------------------------------------------------


class TestOllamaListModels:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_models_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "qwen2.5-coder:32b", "size": 123456},
                {"name": "llama3.1:8b", "size": 78901},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            models = await client.list_models()

        assert len(models) == 2
        assert "llama3.1:8b" in models
        assert "qwen2.5-coder:32b" in models
        assert models == sorted(models)  # Sorted

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_models_empty(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            models = await client.list_models()

        assert models == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_models_connect_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            models = await client.list_models()

        assert models == []


# ---------------------------------------------------------------------------
# OllamaClient.has_model
# ---------------------------------------------------------------------------


class TestOllamaHasModel:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_has_model_true(self):
        client = OllamaClient()
        with patch.object(
            client, "list_models",
            new=AsyncMock(return_value=["llama3.1:8b", "qwen2.5-coder:32b"]),
        ):
            assert await client.has_model("llama3.1:8b") is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_has_model_false(self):
        client = OllamaClient()
        with patch.object(
            client, "list_models",
            new=AsyncMock(return_value=["llama3.1:8b"]),
        ):
            assert await client.has_model("qwen2.5-coder:32b") is False


# ---------------------------------------------------------------------------
# OllamaClient.pull_model
# ---------------------------------------------------------------------------


class TestOllamaPullModel:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pull_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.pull_model("llama3.1:8b")

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pull_failure(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = OllamaClient()
            result = await client.pull_model("llama3.1:8b")

        assert result is False


# ---------------------------------------------------------------------------
# OllamaClient.ensure_model
# ---------------------------------------------------------------------------


class TestOllamaEnsureModel:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_already_available(self):
        client = OllamaClient()
        with patch.object(client, "has_model", new=AsyncMock(return_value=True)):
            result = await client.ensure_model("llama3.1:8b")
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_needs_pull_success(self):
        client = OllamaClient()
        with patch.object(client, "has_model", new=AsyncMock(return_value=False)):
            with patch.object(client, "pull_model", new=AsyncMock(return_value=True)):
                result = await client.ensure_model("llama3.1:8b")
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_needs_pull_failure(self):
        client = OllamaClient()
        with patch.object(client, "has_model", new=AsyncMock(return_value=False)):
            with patch.object(client, "pull_model", new=AsyncMock(return_value=False)):
                result = await client.ensure_model("llama3.1:8b")
        assert result is False
