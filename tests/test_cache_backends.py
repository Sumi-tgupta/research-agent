"""
Tests for the Phase-12 env-driven cache backends (app/cache.py).

The default SQLite backend has its own suite (test_cache.py). Here we cover the
two additions:

  - ``PostgresCache`` exercised against a temp SQLite *file* URL. Its SQL
    (``CREATE TABLE IF NOT EXISTS`` + ``INSERT ... ON CONFLICT``) is understood
    by SQLite too, so the full get/set/delete/clear/TTL contract runs without a
    real Postgres server.
  - the ``get_default_cache()`` factory's backend dispatch and — the important
    part — its fail-open fallback to the local SQLite backend whenever a chosen
    backend can't be built (missing URL, unavailable driver, unreachable
    server). A cache is an optimization; a misconfigured one must never break
    retrieval.

``RedisCache`` isn't unit-tested against a live server here (the free stack has
no local Redis and the suite must stay hermetic/offline); its selection path is
covered via the factory's fallback behavior instead.
"""

import time

import pytest

from app.cache import (
    Cache,
    PostgresCache,
    _build_cache_from_settings,
    get_default_cache,
    reset_default_cache,
)
from app.config import Settings


def _settings(**overrides) -> Settings:
    # model_construct fills defaults for everything not overridden, so these
    # tests don't read the developer's real .env.
    base = dict(cache_backend="sqlite", redis_url="", database_url="sqlite://")
    base.update(overrides)
    return Settings.model_construct(**base)


@pytest.fixture(autouse=True)
def _reset_cache_singleton():
    """Keep the module-level default-cache singleton from leaking between these
    tests (and out to other modules)."""
    reset_default_cache()
    yield
    reset_default_cache()


# --------------------------------------------------------------------------- #
# PostgresCache — full contract against a SQLite file URL
# --------------------------------------------------------------------------- #

def _pg_cache(tmp_path, ttl_seconds: float = 3600) -> PostgresCache:
    url = f"sqlite:///{tmp_path / 'pgcache.sqlite3'}"
    return PostgresCache(url, ttl_seconds=ttl_seconds)


def test_postgrescache_set_then_get_roundtrips(tmp_path):
    cache = _pg_cache(tmp_path)
    cache.set("key1", {"title": "A Result", "score": 0.9})
    assert cache.get("key1") == {"title": "A Result", "score": 0.9}


def test_postgrescache_get_returns_none_for_missing_key(tmp_path):
    assert _pg_cache(tmp_path).get("does-not-exist") is None


def test_postgrescache_get_returns_none_for_expired_entry(tmp_path):
    cache = _pg_cache(tmp_path, ttl_seconds=0.05)
    cache.set("key1", "value")
    time.sleep(0.1)
    assert cache.get("key1") is None


def test_postgrescache_set_overwrites_existing_key(tmp_path):
    cache = _pg_cache(tmp_path)
    cache.set("key1", "first value")
    cache.set("key1", "second value")
    assert cache.get("key1") == "second value"


def test_postgrescache_delete_and_clear(tmp_path):
    cache = _pg_cache(tmp_path)
    cache.set("a", 1)
    cache.set("b", 2)

    cache.delete("a")
    assert cache.get("a") is None and cache.get("b") == 2

    cache.clear()
    assert cache.get("b") is None


def test_postgrescache_inherits_stable_make_key():
    # Subclass must keep the shared key hasher so a key made anywhere resolves
    # the same regardless of which backend is active.
    assert PostgresCache.make_key("tavily_search", q="x") == Cache.make_key("tavily_search", q="x")


# --------------------------------------------------------------------------- #
# get_default_cache() / _build_cache_from_settings() — dispatch + fail-open
# --------------------------------------------------------------------------- #

def test_factory_defaults_to_local_sqlite(tmp_path, mocker):
    mocker.patch("app.cache.get_settings", return_value=_settings(cache_backend="sqlite"))
    mocker.patch("app.cache.DEFAULT_CACHE_PATH", tmp_path / "c.sqlite3")
    assert type(_build_cache_from_settings()) is Cache


def test_factory_redis_without_url_falls_back_to_sqlite(tmp_path, mocker):
    mocker.patch("app.cache.get_settings", return_value=_settings(cache_backend="redis", redis_url=""))
    mocker.patch("app.cache.DEFAULT_CACHE_PATH", tmp_path / "c.sqlite3")
    # No URL configured → don't try Redis, just use the local file cache.
    assert type(_build_cache_from_settings()) is Cache


def test_factory_fails_open_to_sqlite_when_backend_build_errors(tmp_path, mocker):
    mocker.patch(
        "app.cache.get_settings",
        return_value=_settings(cache_backend="redis", redis_url="redis://unreachable:6379"),
    )
    mocker.patch("app.cache.DEFAULT_CACHE_PATH", tmp_path / "c.sqlite3")
    # Simulate the driver missing / server unreachable.
    mocker.patch("app.cache.RedisCache", side_effect=RuntimeError("no redis here"))
    # Must degrade, not raise.
    assert type(_build_cache_from_settings()) is Cache


def test_factory_selects_postgres_backend(tmp_path, mocker):
    url = f"sqlite:///{tmp_path / 'pg.sqlite3'}"
    mocker.patch("app.cache.get_settings", return_value=_settings(cache_backend="postgres", database_url=url))
    assert isinstance(_build_cache_from_settings(), PostgresCache)


def test_get_default_cache_is_a_singleton_and_resettable(tmp_path, mocker):
    mocker.patch("app.cache.get_settings", return_value=_settings(cache_backend="sqlite"))
    mocker.patch("app.cache.DEFAULT_CACHE_PATH", tmp_path / "c.sqlite3")

    first = get_default_cache()
    assert first is get_default_cache()  # memoized

    reset_default_cache()
    assert get_default_cache() is not first  # rebuilt after reset
