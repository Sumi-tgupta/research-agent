"""
Tests for app/cache.py. All real - SQLite is stdlib, no mocking needed.
Each test gets its own temp-file database via pytest's tmp_path fixture,
so tests never touch or depend on the real cache file.
"""

import time

from app.cache import Cache, get_default_cache


def _cache(tmp_path, ttl_seconds: float = 3600) -> Cache:
    return Cache(path=tmp_path / "test_cache.sqlite3", ttl_seconds=ttl_seconds)


def test_set_then_get_roundtrips(tmp_path):
    cache = _cache(tmp_path)
    cache.set("key1", {"title": "A Result", "score": 0.9})

    assert cache.get("key1") == {"title": "A Result", "score": 0.9}


def test_get_returns_none_for_missing_key(tmp_path):
    assert _cache(tmp_path).get("does-not-exist") is None


def test_get_returns_none_for_expired_entry(tmp_path):
    cache = _cache(tmp_path, ttl_seconds=0.05)
    cache.set("key1", "value")
    time.sleep(0.1)

    assert cache.get("key1") is None


def test_expired_entry_is_actually_deleted_not_just_hidden(tmp_path):
    cache = _cache(tmp_path, ttl_seconds=0.05)
    cache.set("key1", "value")
    time.sleep(0.1)
    cache.get("key1")  # triggers deletion as a side effect

    with cache._connect() as conn:
        row = conn.execute("SELECT * FROM cache_entries WHERE key = ?", ("key1",)).fetchone()
    assert row is None


def test_set_overwrites_existing_key(tmp_path):
    cache = _cache(tmp_path)
    cache.set("key1", "first value")
    cache.set("key1", "second value")

    assert cache.get("key1") == "second value"


def test_delete_removes_an_entry(tmp_path):
    cache = _cache(tmp_path)
    cache.set("key1", "value")
    cache.delete("key1")

    assert cache.get("key1") is None


def test_clear_removes_everything(tmp_path):
    cache = _cache(tmp_path)
    cache.set("key1", "a")
    cache.set("key2", "b")
    cache.clear()

    assert cache.get("key1") is None
    assert cache.get("key2") is None


def test_cache_persists_across_separate_instances_of_the_same_file(tmp_path):
    path = tmp_path / "shared.sqlite3"
    Cache(path=path).set("key1", {"persisted": True})

    reopened = Cache(path=path)
    assert reopened.get("key1") == {"persisted": True}


# --------------------------------------------------------------- make_key

def test_make_key_is_stable_regardless_of_kwarg_order():
    key_a = Cache.make_key("tavily_search", query="microplastics", max_results=5)
    key_b = Cache.make_key("tavily_search", max_results=5, query="microplastics")
    assert key_a == key_b


def test_make_key_differs_for_different_params():
    key_a = Cache.make_key("tavily_search", query="microplastics", max_results=5)
    key_b = Cache.make_key("tavily_search", query="microplastics", max_results=10)
    assert key_a != key_b


def test_make_key_differs_for_different_namespace():
    key_a = Cache.make_key("tavily_search", query="x")
    key_b = Cache.make_key("semantic_scholar_search", query="x")
    assert key_a != key_b


# --------------------------------------------------------------- get_default_cache

def test_get_default_cache_returns_the_same_instance(tmp_path, monkeypatch):
    # get_default_cache() is a lazily-initialized module-level singleton
    # pointed at the real DEFAULT_CACHE_PATH. Redirecting that path and
    # resetting the singleton here keeps this test isolated (no real file
    # touched, no state leaking into whichever test runs next) while still
    # exercising the actual singleton logic, not a mock of it.
    monkeypatch.setattr("app.cache.DEFAULT_CACHE_PATH", tmp_path / "default_test_cache.sqlite3")
    monkeypatch.setattr("app.cache._default_cache", None)

    assert get_default_cache() is get_default_cache()
