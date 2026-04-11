"""Thin HTTP client for the Citex RAG API."""
from __future__ import annotations

import httpx

CITEX_DEFAULT_URL = "http://localhost:20160"


class CitexClient:
    """Client for Citex RAG — shared context layer for all CLI agent instances."""

    def __init__(self, base_url: str = CITEX_DEFAULT_URL, project_id: str = ""):
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id

    def health_check(self) -> bool:
        """Check if Citex is reachable."""
        try:
            resp = httpx.get(f"{self.base_url}/api/v1/health", timeout=5)
            return resp.status_code < 400
        except Exception:
            return False

    def ingest(self, content: str, category: str, metadata: dict | None = None) -> bool:
        """Ingest a document into Citex."""
        try:
            resp = httpx.post(
                f"{self.base_url}/api/v1/documents/ingest",
                json={
                    "project_id": self.project_id,
                    "content": content,
                    "metadata": {"category": category, **(metadata or {})},
                },
                timeout=30,
            )
            return resp.status_code < 400
        except Exception:
            return False

    def query(self, query: str, category: str | None = None, limit: int = 5) -> list[str]:
        """Query Citex for relevant context. Returns list of content strings."""
        try:
            payload: dict = {"project_id": self.project_id, "query": query, "limit": limit}
            if category:
                payload["filter"] = {"category": category}
            resp = httpx.post(
                f"{self.base_url}/api/v1/retrieval/query",
                json=payload,
                timeout=30,
            )
            if resp.status_code < 400:
                data = resp.json()
                return [
                    r.get("content", r.get("text", ""))
                    for r in data.get("results", data.get("documents", []))
                    if r.get("content") or r.get("text")
                ]
        except Exception:
            pass
        return []
