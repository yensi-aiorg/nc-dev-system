"""Tests for the Sentinel HTTP callback client."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest


def _make_result():
    from ncdev.v2.models import FixOutcome, SentinelFixResult

    now = datetime(2026, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
    return SentinelFixResult(
        report_id="rpt_bk_001",
        run_id="fix-rpt_bk_001-20260315-143000",
        outcome=FixOutcome.FIXED,
        outcome_detail="Fixed null check",
        pr_url="https://github.com/org/repo/pull/42",
        started_at=now,
        completed_at=now,
    )


CALLBACK_URL = "https://sentinel.example.com/api/v1/fix-results"
API_KEY = "test-api-key-abc123"


class TestSendFixResultSuccess:
    def test_success_on_first_call(self):
        """Returns True when httpx.post returns 200 on first attempt."""
        result = _make_result()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("ncdev.v2.sentinel_callback.httpx.post", return_value=mock_response) as mock_post:
            from ncdev.v2.sentinel_callback import send_fix_result

            outcome = send_fix_result(
                result=result,
                callback_url=CALLBACK_URL,
                api_key=API_KEY,
                retry_count=3,
                retry_delay_seconds=0,
            )

        assert outcome is True
        assert mock_post.call_count == 1

    def test_correct_headers_sent(self):
        """Verifies Authorization and X-NCDev-Run-ID headers are included."""
        result = _make_result()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("ncdev.v2.sentinel_callback.httpx.post", return_value=mock_response) as mock_post:
            from ncdev.v2.sentinel_callback import send_fix_result

            send_fix_result(
                result=result,
                callback_url=CALLBACK_URL,
                api_key=API_KEY,
                retry_count=1,
                retry_delay_seconds=0,
            )

        _, kwargs = mock_post.call_args
        headers = kwargs["headers"]
        assert headers["Authorization"] == f"Bearer {API_KEY}"
        assert headers["X-NCDev-Run-ID"] == result.run_id
        assert headers["Content-Type"] == "application/json"

    def test_correct_url_called(self):
        """Verifies the callback URL is passed to httpx.post."""
        result = _make_result()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("ncdev.v2.sentinel_callback.httpx.post", return_value=mock_response) as mock_post:
            from ncdev.v2.sentinel_callback import send_fix_result

            send_fix_result(
                result=result,
                callback_url=CALLBACK_URL,
                api_key=API_KEY,
                retry_count=1,
                retry_delay_seconds=0,
            )

        args, _ = mock_post.call_args
        assert args[0] == CALLBACK_URL


class TestSendFixResultRetry:
    def test_retries_on_failure_then_succeeds(self):
        """Returns True when first call returns 500 and second returns 200."""
        result = _make_result()

        mock_500 = MagicMock()
        mock_500.status_code = 500
        mock_200 = MagicMock()
        mock_200.status_code = 200

        with patch(
            "ncdev.v2.sentinel_callback.httpx.post",
            side_effect=[mock_500, mock_200],
        ) as mock_post:
            from ncdev.v2.sentinel_callback import send_fix_result

            outcome = send_fix_result(
                result=result,
                callback_url=CALLBACK_URL,
                api_key=API_KEY,
                retry_count=3,
                retry_delay_seconds=0,
            )

        assert outcome is True
        assert mock_post.call_count == 2

    def test_exhausts_all_retries_returns_false(self):
        """Returns False and calls httpx.post exactly retry_count times when all fail."""
        result = _make_result()

        mock_500 = MagicMock()
        mock_500.status_code = 500

        retry_count = 3

        with patch(
            "ncdev.v2.sentinel_callback.httpx.post",
            return_value=mock_500,
        ) as mock_post:
            from ncdev.v2.sentinel_callback import send_fix_result

            outcome = send_fix_result(
                result=result,
                callback_url=CALLBACK_URL,
                api_key=API_KEY,
                retry_count=retry_count,
                retry_delay_seconds=0,
            )

        assert outcome is False
        assert mock_post.call_count == retry_count

    def test_single_retry_count_no_extra_calls(self):
        """When retry_count=1 and status is 500, calls httpx.post exactly once."""
        result = _make_result()

        mock_500 = MagicMock()
        mock_500.status_code = 500

        with patch(
            "ncdev.v2.sentinel_callback.httpx.post",
            return_value=mock_500,
        ) as mock_post:
            from ncdev.v2.sentinel_callback import send_fix_result

            outcome = send_fix_result(
                result=result,
                callback_url=CALLBACK_URL,
                api_key=API_KEY,
                retry_count=1,
                retry_delay_seconds=0,
            )

        assert outcome is False
        assert mock_post.call_count == 1


class TestSendFixResultException:
    def test_handles_connection_error_returns_false(self):
        """Returns False when httpx.post raises an Exception on all attempts."""
        result = _make_result()

        with patch(
            "ncdev.v2.sentinel_callback.httpx.post",
            side_effect=Exception("Connection refused"),
        ) as mock_post:
            from ncdev.v2.sentinel_callback import send_fix_result

            outcome = send_fix_result(
                result=result,
                callback_url=CALLBACK_URL,
                api_key=API_KEY,
                retry_count=3,
                retry_delay_seconds=0,
            )

        assert outcome is False
        assert mock_post.call_count == 3

    def test_succeeds_after_exception_then_200(self):
        """Returns True when first call raises Exception but second returns 200."""
        result = _make_result()

        mock_200 = MagicMock()
        mock_200.status_code = 200

        with patch(
            "ncdev.v2.sentinel_callback.httpx.post",
            side_effect=[Exception("Timeout"), mock_200],
        ) as mock_post:
            from ncdev.v2.sentinel_callback import send_fix_result

            outcome = send_fix_result(
                result=result,
                callback_url=CALLBACK_URL,
                api_key=API_KEY,
                retry_count=3,
                retry_delay_seconds=0,
            )

        assert outcome is True
        assert mock_post.call_count == 2

    def test_no_sleep_when_delay_is_zero(self):
        """Verifies time.sleep is not called when retry_delay_seconds=0."""
        result = _make_result()

        mock_500 = MagicMock()
        mock_500.status_code = 500

        with patch("ncdev.v2.sentinel_callback.httpx.post", return_value=mock_500):
            with patch("ncdev.v2.sentinel_callback.time.sleep") as mock_sleep:
                from ncdev.v2.sentinel_callback import send_fix_result

                send_fix_result(
                    result=result,
                    callback_url=CALLBACK_URL,
                    api_key=API_KEY,
                    retry_count=3,
                    retry_delay_seconds=0,
                )

        mock_sleep.assert_not_called()

    def test_sleep_called_between_retries(self):
        """Verifies time.sleep is called between retry attempts when delay > 0."""
        result = _make_result()

        mock_500 = MagicMock()
        mock_500.status_code = 500

        with patch("ncdev.v2.sentinel_callback.httpx.post", return_value=mock_500):
            with patch("ncdev.v2.sentinel_callback.time.sleep") as mock_sleep:
                from ncdev.v2.sentinel_callback import send_fix_result

                send_fix_result(
                    result=result,
                    callback_url=CALLBACK_URL,
                    api_key=API_KEY,
                    retry_count=3,
                    retry_delay_seconds=2,
                )

        # Should sleep retry_count - 1 times (not after the last attempt)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2)
