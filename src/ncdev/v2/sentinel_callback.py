"""HTTP callback client to notify Sentinel of fix results."""
from __future__ import annotations

import logging
import time

import httpx

from ncdev.v2.models import SentinelFixResult

logger = logging.getLogger(__name__)


def send_fix_result(
    *,
    result: SentinelFixResult,
    callback_url: str,
    api_key: str,
    retry_count: int = 3,
    retry_delay_seconds: int = 5,
) -> bool:
    """Send a SentinelFixResult to the Sentinel callback URL.

    Returns True if Sentinel acknowledged the result (200 OK), False otherwise.
    Retries up to retry_count times with retry_delay_seconds between attempts.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-NCDev-Run-ID": result.run_id,
    }
    payload = result.model_dump_json()

    for attempt in range(retry_count):
        try:
            response = httpx.post(
                callback_url,
                content=payload,
                headers=headers,
                timeout=30.0,
            )
            if response.status_code == 200:
                logger.info("Callback succeeded for run %s", result.run_id)
                return True
            logger.warning(
                "Callback attempt %d/%d failed with status %d for run %s",
                attempt + 1,
                retry_count,
                response.status_code,
                result.run_id,
            )
        except Exception:
            logger.warning(
                "Callback attempt %d/%d raised exception for run %s",
                attempt + 1,
                retry_count,
                result.run_id,
                exc_info=True,
            )

        if attempt < retry_count - 1 and retry_delay_seconds > 0:
            time.sleep(retry_delay_seconds)

    logger.error("Callback exhausted all %d retries for run %s", retry_count, result.run_id)
    return False
