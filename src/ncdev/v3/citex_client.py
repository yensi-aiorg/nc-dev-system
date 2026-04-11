"""Thin HTTP client for the Citex RAG API."""
from __future__ import annotations

from typing import Any

import httpx

CITEX_DEFAULT_URL = "http://localhost:20161"


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
            resp = httpx.get(f"{self.base_url}/health", timeout=self.timeout)
            return resp.status_code < 400
        except httpx.HTTPError:
            return False

    def ingest(
        self,
        content: str,
        category: str,
        metadata: dict[str, Any] | None = None,
        title: str = "",
    ) -> bool:
        """Store one context document in Citex via POST /api/content."""
        payload: dict[str, Any] = {
            "content": content,
            "contentType": "text",
            "category": category if category in _VALID_CATEGORIES else "document",
            "projectId": self.project_id,
            "createdBy": "ncdev",
            "accessScope": "project",
            "tags": [category],
            "metadata": {
                "ncdev_category": category,
                **(metadata or {}),
            },
        }
        if title:
            payload["title"] = title
        try:
            resp = httpx.post(
                f"{self.base_url}/api/content",
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
            "top_k": limit,
        }
        try:
            resp = httpx.post(
                f"{self.base_url}/api/retrieval/query",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return []
        data = resp.json()
        return [
            r.get("content", r.get("text", ""))
            for r in data.get("results", [])
            if r.get("content") or r.get("text")
        ]


# Citex content categories (from the API schema)
_VALID_CATEGORIES = {
    "projects", "code", "decisions", "agents", "artifacts",
    "signals", "conversations", "external", "document",
}
