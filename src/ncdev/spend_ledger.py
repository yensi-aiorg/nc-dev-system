"""Append-only spend ledger for unattended factory runs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_spend_event(
    path: Path,
    *,
    component: str,
    action: str,
    cycle: int | None = None,
    metered: bool,
    cost_usd: float | None = None,
    budget_usd: float | None = None,
    status: str = "ok",
    details: dict[str, Any] | None = None,
) -> None:
    """Append one JSONL spend event.

    ``metered=False`` is intentional data, not an error. It tells later
    audits that an invocation happened whose cost could not be measured.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "action": action,
        "cycle": cycle,
        "metered": metered,
        "cost_usd": cost_usd,
        "budget_usd": budget_usd,
        "status": status,
        "details": details or {},
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")
