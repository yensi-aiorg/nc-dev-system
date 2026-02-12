"""Async client for the local Ollama API.

Wraps the Ollama HTTP API (``/api/generate``, ``/api/tags``, ``/api/pull``)
with proper timeout handling, structured responses, and automatic model
fallback. All methods are async so they integrate cleanly with the rest of
the pipeline.

Typical usage::

    client = OllamaClient()
    if await client.is_available():
        resp = await client.generate("Write a Python hello world", model="qwen3-coder:30b")
        print(resp.text)
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

import httpx
from pydantic import BaseModel, Field


class OllamaResponse(BaseModel):
    """Structured response from an Ollama generation call."""

    text: str = Field(default="", description="Generated text")
    model: str = Field(default="", description="Model that produced the response")
    duration_ms: float = Field(default=0.0, description="Server-side generation time in ms")
    success: bool = Field(default=True, description="Whether the request succeeded")
    error: str | None = Field(default=None, description="Error message on failure")


class OllamaClient:
    """Async client for the Ollama REST API at localhost:11434.

    The client uses ``httpx.AsyncClient`` for non-blocking HTTP and exposes
    helper methods for text generation, vision analysis, availability checks,
    model listing, and model pulling.
    """

    def __init__(self, base_url: str = "http://localhost:11434", timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        """Return a fresh ``AsyncClient`` configured with our base URL and timeout."""
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
        )

    @staticmethod
    def _extract_text(data: dict) -> str:
        """Pull the generated text out of a /api/generate JSON response.

        Ollama's non-streaming response puts the full text in ``"response"``.
        """
        return data.get("response", "")

    @staticmethod
    def _extract_duration_ms(data: dict) -> float:
        """Extract the total generation duration in milliseconds.

        The API returns ``total_duration`` in **nanoseconds**.
        """
        ns = data.get("total_duration", 0)
        return ns / 1_000_000.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        model: str = "qwen3-coder:30b",
        system: str = "",
    ) -> OllamaResponse:
        """Generate text from a prompt.

        Args:
            prompt: The user prompt.
            model: Ollama model tag to use.
            system: Optional system prompt prepended to the context.

        Returns:
            An ``OllamaResponse`` with the generated text or an error.
        """
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        try:
            async with self._client() as client:
                response = await client.post("/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                return OllamaResponse(
                    text=self._extract_text(data),
                    model=data.get("model", model),
                    duration_ms=self._extract_duration_ms(data),
                    success=True,
                )
        except httpx.ConnectError:
            return OllamaResponse(
                model=model,
                success=False,
                error=f"Cannot connect to Ollama at {self.base_url}. Is the server running?",
            )
        except httpx.TimeoutException:
            return OllamaResponse(
                model=model,
                success=False,
                error=f"Request to Ollama timed out after {self.timeout}s.",
            )
        except httpx.HTTPStatusError as exc:
            return OllamaResponse(
                model=model,
                success=False,
                error=f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text[:500]}",
            )
        except Exception as exc:  # noqa: BLE001
            return OllamaResponse(
                model=model,
                success=False,
                error=f"Unexpected error during Ollama generate: {exc}",
            )

    async def generate_with_fallback(
        self,
        prompt: str,
        primary_model: str = "qwen3-coder:30b",
        fallback_model: str = "qwen3-coder:30b",
        system: str = "",
    ) -> OllamaResponse:
        """Try ``primary_model`` first; on failure fall back to ``fallback_model``.

        This is the recommended entry point for code generation — it
        transparently handles the case where the larger model is not pulled
        yet or times out.
        """
        result = await self.generate(prompt, model=primary_model, system=system)
        if result.success:
            return result

        # Retry with the smaller fallback model.
        return await self.generate(prompt, model=fallback_model, system=system)

    async def vision(
        self,
        image_path: str | Path,
        prompt: str,
        model: str = "qwen2.5vl:7b",
    ) -> OllamaResponse:
        """Analyse an image with an Ollama vision model.

        The image is read from disk and base64-encoded for the ``images``
        field expected by ``/api/generate``.

        Args:
            image_path: Path to a PNG/JPEG image file.
            prompt: The analysis prompt (e.g. *"Describe any UI issues"*).
            model: Vision-capable Ollama model tag.

        Returns:
            An ``OllamaResponse`` containing the analysis text or an error.
        """
        image_file = Path(image_path)
        if not image_file.exists():
            return OllamaResponse(
                model=model,
                success=False,
                error=f"Image file not found: {image_file}",
            )

        try:
            raw_bytes = image_file.read_bytes()
        except OSError as exc:
            return OllamaResponse(
                model=model,
                success=False,
                error=f"Could not read image file {image_file}: {exc}",
            )

        encoded = base64.b64encode(raw_bytes).decode("ascii")

        payload: dict = {
            "model": model,
            "prompt": prompt,
            "images": [encoded],
            "stream": False,
        }

        try:
            async with self._client() as client:
                response = await client.post("/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                return OllamaResponse(
                    text=self._extract_text(data),
                    model=data.get("model", model),
                    duration_ms=self._extract_duration_ms(data),
                    success=True,
                )
        except httpx.ConnectError:
            return OllamaResponse(
                model=model,
                success=False,
                error=f"Cannot connect to Ollama at {self.base_url}. Is the server running?",
            )
        except httpx.TimeoutException:
            return OllamaResponse(
                model=model,
                success=False,
                error=f"Vision request timed out after {self.timeout}s.",
            )
        except httpx.HTTPStatusError as exc:
            return OllamaResponse(
                model=model,
                success=False,
                error=f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text[:500]}",
            )
        except Exception as exc:  # noqa: BLE001
            return OllamaResponse(
                model=model,
                success=False,
                error=f"Unexpected error during Ollama vision: {exc}",
            )

    async def is_available(self) -> bool:
        """Return ``True`` if the Ollama server responds to ``/api/tags``."""
        try:
            async with self._client() as client:
                response = await client.get("/api/tags")
                return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, Exception):
            return False

    async def list_models(self) -> list[str]:
        """Return the names of all locally-available models.

        Parses the ``/api/tags`` response and returns a sorted list of model
        name strings (e.g. ``["qwen3:8b", "qwen3-coder:30b"]``).
        Returns an empty list if the server is unreachable.
        """
        try:
            async with self._client() as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                data = response.json()
                models = data.get("models", [])
                return sorted(m.get("name", "") for m in models if m.get("name"))
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, Exception):
            return []

    async def has_model(self, model: str) -> bool:
        """Check whether a specific model is already pulled locally."""
        available = await self.list_models()
        return model in available

    async def pull_model(self, model: str) -> bool:
        """Pull a model from the Ollama registry.

        This is a **blocking** call that streams the download progress
        internally and returns ``True`` once the model is ready.

        Args:
            model: The model tag to pull (e.g. ``"qwen3:8b"``).

        Returns:
            ``True`` if the model was pulled (or already existed), ``False``
            on any error.
        """
        try:
            # Pulling can take a very long time for large models; use a
            # generous timeout (30 minutes).
            pull_timeout = httpx.Timeout(1800.0, connect=10.0)
            async with httpx.AsyncClient(base_url=self.base_url, timeout=pull_timeout) as client:
                response = await client.post(
                    "/api/pull",
                    json={"name": model, "stream": False},
                )
                response.raise_for_status()
                data = response.json()
                status = data.get("status", "")
                return status == "success" or "digest" in status.lower() or response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, Exception):
            return False

    async def ensure_model(self, model: str) -> bool:
        """Make sure a model is locally available, pulling it if necessary.

        Returns:
            ``True`` if the model is available after this call.
        """
        if await self.has_model(model):
            return True
        return await self.pull_model(model)
