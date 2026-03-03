from __future__ import annotations

from typing import Any

import httpx


class TestCrafterClient:
    def __init__(self, base_url: str = "http://localhost:16630") -> None:
        self.base_url = base_url.rstrip("/")

    def run(self, prd_path: str, target_url: str, analysis_level: str = "thorough") -> dict[str, Any]:
        payload = {
            "prd_path": prd_path,
            "target_url": target_url,
            "analysis_level": analysis_level,
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{self.base_url}/run", json=payload)
            resp.raise_for_status()
            return resp.json()


class VisualDesignerClient:
    def __init__(self, base_url: str = "http://localhost:12101") -> None:
        self.base_url = base_url.rstrip("/")

    def generate_references(self, journey: str) -> dict[str, Any]:
        payload = {"journey": journey}
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{self.base_url}/layout/generate", json=payload)
            resp.raise_for_status()
            return resp.json()
