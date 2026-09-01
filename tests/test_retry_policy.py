"""Retry classification tests for Standard translation provider failures."""

from __future__ import annotations

import httpx

from ebook_translator.translator.pipeline import _is_retryable_exception


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test/chat/completions")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("provider error", request=request, response=response)


def test_retry_policy_retries_transient_failures() -> None:
    assert _is_retryable_exception(httpx.ReadTimeout("timeout")) is True
    assert _is_retryable_exception(httpx.ConnectError("network")) is True
    assert _is_retryable_exception(_status_error(408)) is True
    assert _is_retryable_exception(_status_error(429)) is True
    assert _is_retryable_exception(_status_error(500)) is True
    assert _is_retryable_exception(_status_error(503)) is True


def test_retry_policy_fails_fast_on_permanent_client_errors() -> None:
    assert _is_retryable_exception(_status_error(400)) is False
    assert _is_retryable_exception(_status_error(401)) is False
    assert _is_retryable_exception(_status_error(403)) is False
    assert _is_retryable_exception(_status_error(404)) is False
    assert _is_retryable_exception(ValueError("bad model config")) is False
