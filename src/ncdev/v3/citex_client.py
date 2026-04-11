"""Thin HTTP client for the Citex RAG API."""
from __future__ import annotations

from typing import Any

import httpx

CITEX_DEFAULT_URL = "http://localhost:20160"


class CitexClient:
    """Client for Citex RAG — shared context layer for all CLI agent instances."""

    def __init__(
        self,
        project_id: str,
        base_url: str = CITEX_DEFAULT_URL,
        timeout: float = 30.0,
    ) -> None:
        self.project_id = project_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health_check(self) -> bool:
        """Return True when Citex responds on its health endpoint."""
        try:
            resp = httpx.get(f"{self.base_url}/api/v1/health", timeout=self.timeout)
            return resp.status_code < 400
        except httpx.HTTPError:
            return False

    def ingest(
        self,
        content: str,
        category: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store one context document in Citex."""
        payload = {
            "project_id": self.project_id,
            "content": content,
            "metadata": {
                "category": category,
                **(metadata or {}),
            },
        }
        try:
            resp = httpx.post(
                f"{self.base_url}/api/v1/documents/ingest",
                json=payload,
                timeout=self.timeout,
            )
            return resp.status_code < 400
        except httpx.HTTPError:
            return False

    def query(
        self,
        query: str,
        category: str | None = None,
        limit: int = 5,
    ) -> list[str]:
        """Query Citex for relevant context. Returns list of content strings."""
        payload: dict[str, Any] = {
            "project_id": self.project_id,
            "query": query,
            "limit": limit,
        }
        if category:
            payload["category"] = category
        try:
            resp = httpx.post(
                f"{self.base_url}/api/v1/retrieval/query",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return []
        data = resp.json()
        return [
            r.get("content", r.get("text", ""))
            for r in data.get("results", data.get("documents", []))
            if r.get("content") or r.get("text")
        ]
