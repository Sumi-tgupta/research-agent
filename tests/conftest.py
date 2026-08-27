"""
Shared pytest fixtures.

`isolated_cache` gives any test that constructs a SearchAgent or
PaperRetrievalAgent a temp-file cache instead of the real default one.
Without this, a cached result written by one test (or a previous test
run entirely) could silently satisfy a later test's assertions without
the mocked API call actually having been exercised that time — exactly
the kind of false-positive the cache's own tests must not have.
"""

import pytest

from app.cache import Cache


@pytest.fixture(autouse=True)
def _route_llm_calls_to_gemini_in_tests(mocker):
    """Make the Phase-12 model router deterministic under test.

    The agent tests each mock their own module's ``get_gemini_client`` and
    assert on Gemini-shaped calls (see test_planner / test_writer / test_graph
    / etc.). The router, however, sends "light" stages (fact-check, charts) to
    Groq *first* — and on a machine that happens to have ``GROQ_API_KEY`` set,
    that real Groq client would be built and called, making those tests depend
    on the developer's environment.

    Forcing the router's ``get_groq_client`` to return None means Groq is
    always skipped (a skipped, unconfigured provider is not a failure — see
    ``_run_chain``), so every routed call deterministically falls through to
    the mocked Gemini, exactly as it behaved before routing existed. Tests
    that specifically exercise the Groq path (test_model_router.py) re-patch
    ``app.model_router.get_groq_client`` in their own body, which overrides
    this fixture for the duration of that test."""
    mocker.patch("app.model_router.get_groq_client", return_value=None)


@pytest.fixture
def isolated_cache(tmp_path):
    return Cache(path=tmp_path / "test_cache.sqlite3")
