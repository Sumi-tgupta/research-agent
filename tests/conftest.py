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


@pytest.fixture
def isolated_cache(tmp_path):
    return Cache(path=tmp_path / "test_cache.sqlite3")
