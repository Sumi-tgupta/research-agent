"""
Generic exponential-backoff retry helper, used by every agent that calls
a rate-limited external API (Tavily, Semantic Scholar, Gemini). Deliberately
generic and centralized here rather than reimplemented per integration, so
retry behavior is consistent and independently testable in one place.

ArXiv is deliberately NOT wrapped with this — the `arxiv` package already
retries HTTPError/ConnectionError internally (`num_retries`, default 3,
confirmed by reading its source), and wrapping an already-retrying call in
another retry layer would just multiply the worst-case wait time for no
benefit.

Only retries what's actually worth retrying: a rate-limit response (429),
a transient server error (5xx), or a network-level hiccup (timeout,
connection reset). Never retries an invalid API key, a malformed request,
or an already-exhausted monthly quota — retrying those wastes the attempt
and can't change the outcome.
"""

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 20.0

# Worth retrying no matter which API raised them - connection-level trouble
# below any particular SDK's own error wrapping.
NETWORK_TRANSIENT_ERRORS = (TimeoutError, ConnectionError)


class RetryExhausted(Exception):
    """Raised when every attempt failed on a retryable error. Wraps the
    last underlying exception so callers can still report what actually
    went wrong, not just "retries exhausted."""

    def __init__(self, attempts: int, last_exception: Exception):
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(f"Gave up after {attempts} attempt(s): {last_exception}")


def http_status_code(exc: Exception) -> int | None:
    """Pulls an HTTP-like status code off whichever exception raised it,
    if any: requests.HTTPError's `.response.status_code`, or
    google-genai's APIError `.code`. Returns None if there isn't one (e.g.
    a plain network error) - callers fall back to type-based checks."""
    response = getattr(exc, "response", None)
    if response is not None and hasattr(response, "status_code"):
        return response.status_code
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    return None


def is_retryable_http_error(exc: Exception) -> bool:
    """True for a 429 (rate limited) or any 5xx (transient server-side
    problem) - the two cases backoff actually helps with. False for other
    4xx (bad request, bad key, forbidden, not found): retrying an
    identical bad request just burns an attempt for the same result.
    Works for both requests.HTTPError (Semantic Scholar) and
    google-genai's APIError (Gemini) via http_status_code()."""
    if isinstance(exc, NETWORK_TRANSIENT_ERRORS):
        return True
    status = http_status_code(exc)
    if status is None:
        return False
    return status == 429 or status >= 500


def is_retryable_tavily_error(exc: Exception) -> bool:
    """Tavily's SDK raises its own exception hierarchy without an HTTP
    status code attached (see tavily.errors) - MissingAPIKeyError,
    InvalidAPIKeyError, UsageLimitExceededError, BadRequestError, and
    ForbiddenError are all permanent/deterministic, so only Tavily's own
    TimeoutError (plus generic network errors) are retried here."""
    if isinstance(exc, NETWORK_TRANSIENT_ERRORS):
        return True
    from tavily.errors import TimeoutError as TavilyTimeoutError

    return isinstance(exc, TavilyTimeoutError)


def call_with_backoff(
    func: Callable[[], T],
    *,
    is_retryable: Callable[[Exception], bool] = is_retryable_http_error,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Calls func() with exponential backoff + jitter, retrying only when
    is_retryable(exc) is True for whatever gets raised. A non-retryable
    exception propagates immediately on the first attempt, completely
    unchanged - existing except-blocks for specific error types (bad key,
    quota exceeded, etc.) keep working exactly as before; this only adds
    retries for the transient case layered on top.

    Raises RetryExhausted if every attempt fails on a retryable error.
    `sleep` defaults to None, resolved to `time.sleep` inside the function
    body rather than bound as a literal default value — tests can either
    pass a fake sleep explicitly, or patch `app.retry.time.sleep` and let
    ordinary callers (which don't override `sleep`) pick that up too.
    """
    sleep = sleep or time.sleep
    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except Exception as exc:
            if not is_retryable(exc):
                raise
            last_exception = exc
            if attempt == max_attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.25)  # jitter - avoid synchronized retry storms
            sleep(delay)

    raise RetryExhausted(max_attempts, last_exception)
