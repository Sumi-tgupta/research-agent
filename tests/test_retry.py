"""
Tests for app/retry.py. All real, no mocking of the retry logic itself -
just an injected fake `sleep` (records calls instead of actually
blocking) so these run instantly instead of waiting through real backoff
delays.
"""

import requests

from app.retry import (
    RetryExhausted,
    call_with_backoff,
    http_status_code,
    is_retryable_http_error,
    is_retryable_tavily_error,
)


class _FakeSleep:
    """Records delays instead of actually blocking."""

    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class _FakeHTTPErrorResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


def _http_error(status_code: int) -> requests.HTTPError:
    return requests.HTTPError(response=_FakeHTTPErrorResponse(status_code))


class _FakeAPIError(Exception):
    """Stands in for google.genai.errors.APIError's shape - a plain
    `.code` attribute, no `.response`."""

    def __init__(self, code: int):
        self.code = code
        super().__init__(f"API error {code}")


# --------------------------------------------------------------- call_with_backoff

def test_succeeds_immediately_without_retrying():
    sleep = _FakeSleep()
    calls = {"count": 0}

    def succeed():
        calls["count"] += 1
        return "ok"

    result = call_with_backoff(succeed, sleep=sleep)

    assert result == "ok"
    assert calls["count"] == 1
    assert sleep.calls == []


def test_retries_a_retryable_error_then_succeeds():
    sleep = _FakeSleep()
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise _http_error(429)
        return "recovered"

    result = call_with_backoff(flaky, is_retryable=is_retryable_http_error, sleep=sleep)

    assert result == "recovered"
    assert attempts["count"] == 3
    assert len(sleep.calls) == 2  # slept between attempt 1->2 and 2->3, not after the final success


def test_backoff_delays_increase_and_respect_max_delay():
    sleep = _FakeSleep()

    def always_fails():
        raise _http_error(500)

    try:
        call_with_backoff(
            always_fails,
            is_retryable=is_retryable_http_error,
            max_attempts=4,
            base_delay=1.0,
            max_delay=3.0,
            sleep=sleep,
        )
    except RetryExhausted:
        pass

    assert len(sleep.calls) == 3  # 3 retries between 4 attempts
    # each delay includes jitter (up to +25%) but should still respect max_delay overall
    assert all(d <= 3.0 * 1.25 for d in sleep.calls)
    # delays should generally trend upward (exponential), even accounting for jitter noise
    assert sleep.calls[0] <= sleep.calls[-1] + 0.5


def test_raises_retry_exhausted_after_max_attempts_wrapping_last_exception():
    sleep = _FakeSleep()
    attempts = {"count": 0}

    def always_fails():
        attempts["count"] += 1
        raise _http_error(503)

    try:
        call_with_backoff(always_fails, is_retryable=is_retryable_http_error, max_attempts=3, sleep=sleep)
        assert False, "expected RetryExhausted"
    except RetryExhausted as exc:
        assert exc.attempts == 3
        assert attempts["count"] == 3
        assert isinstance(exc.last_exception, requests.HTTPError)


def test_non_retryable_error_propagates_immediately_without_retrying():
    sleep = _FakeSleep()
    attempts = {"count": 0}

    def bad_request():
        attempts["count"] += 1
        raise _http_error(400)

    try:
        call_with_backoff(bad_request, is_retryable=is_retryable_http_error, sleep=sleep)
        assert False, "expected the original HTTPError to propagate"
    except requests.HTTPError:
        pass

    assert attempts["count"] == 1  # never retried
    assert sleep.calls == []


# --------------------------------------------------------------- http_status_code

def test_http_status_code_from_requests_style_exception():
    assert http_status_code(_http_error(429)) == 429


def test_http_status_code_from_code_attribute_exception():
    assert http_status_code(_FakeAPIError(500)) == 500


def test_http_status_code_none_for_plain_exception():
    assert http_status_code(ValueError("no status here")) is None


# --------------------------------------------------------------- is_retryable_http_error

def test_429_is_retryable():
    assert is_retryable_http_error(_http_error(429)) is True


def test_5xx_is_retryable():
    assert is_retryable_http_error(_http_error(503)) is True


def test_other_4xx_is_not_retryable():
    assert is_retryable_http_error(_http_error(404)) is False
    assert is_retryable_http_error(_http_error(401)) is False


def test_network_errors_are_retryable():
    assert is_retryable_http_error(TimeoutError("timed out")) is True
    assert is_retryable_http_error(ConnectionError("connection reset")) is True


def test_gemini_style_api_error_uses_code_attribute():
    assert is_retryable_http_error(_FakeAPIError(429)) is True
    assert is_retryable_http_error(_FakeAPIError(500)) is True
    assert is_retryable_http_error(_FakeAPIError(400)) is False


# --------------------------------------------------------------- is_retryable_tavily_error

def test_tavily_timeout_is_retryable():
    from tavily.errors import TimeoutError as TavilyTimeoutError

    assert is_retryable_tavily_error(TavilyTimeoutError("timed out")) is True


def test_tavily_permanent_errors_are_not_retryable():
    from tavily.errors import BadRequestError, ForbiddenError, InvalidAPIKeyError, UsageLimitExceededError

    assert is_retryable_tavily_error(InvalidAPIKeyError("bad key")) is False
    assert is_retryable_tavily_error(UsageLimitExceededError("quota exceeded")) is False
    assert is_retryable_tavily_error(BadRequestError("bad request")) is False
    assert is_retryable_tavily_error(ForbiddenError("forbidden")) is False


def test_tavily_generic_network_error_is_retryable():
    assert is_retryable_tavily_error(ConnectionError("reset")) is True
