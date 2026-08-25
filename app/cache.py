"""
A simple persistent, TTL-based cache for expensive/rate-limited retrieval
calls (web search, paper lookups). Backed by SQLite (stdlib — no extra
dependency) specifically so cached results survive process restarts: the
whole point is not re-spending Tavily's 1,000-credit/month budget (or
Semantic Scholar's shared rate limit) on a query already made yesterday,
which an in-memory-only cache wouldn't help with at all.

Deliberately scoped to the raw retrieval agents (Search, Paper Retrieval)
only — NOT the LLM reasoning agents (Planner, Fact Checker, Writer,
Reviewer, Chart Agent). Those are meant to reflect fresh reasoning over
today's retrieved sources; caching "what the Planner said last time"
would quietly serve stale thinking instead of a rate-limit optimization.
The project plan's own phrasing — "avoid re-querying same sources" — is
specifically about the retrieval layer, not the reasoning layer.
"""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent / ".cache" / "research_cache.sqlite3"
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 7  # 1 week: long enough to matter across a day's worth of
# repeated testing/demoing, short enough that results don't go stale indefinitely.


class Cache:
    def __init__(self, path: Path | str | None = None, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        # `path` resolves to DEFAULT_CACHE_PATH inside the function body
        # rather than being bound as a literal default value - so patching
        # the module-level DEFAULT_CACHE_PATH (e.g. in tests) is actually
        # picked up by callers who don't pass `path` explicitly, the same
        # fix applied to retry.py's `sleep` parameter for the same reason.
        self.path = Path(path) if path is not None else Path(DEFAULT_CACHE_PATH)
        self.ttl_seconds = ttl_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cache_entries ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at REAL NOT NULL)"
            )

    @staticmethod
    def make_key(namespace: str, **params: Any) -> str:
        """A stable cache key from a namespace (e.g. 'tavily_search') plus
        arbitrary parameters, hashed so keys stay a fixed short length
        regardless of query text length. `sort_keys=True` means parameter
        order never matters."""
        payload = json.dumps({"namespace": namespace, **params}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Returns the cached value, or None if missing or expired. An
        expired entry is deleted as a side effect of being read, so the
        table doesn't slowly accumulate dead rows forever."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, created_at FROM cache_entries WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        value_json, created_at = row
        if time.time() - created_at > self.ttl_seconds:
            self.delete(key)
            return None
        return json.loads(value_json)

    def set(self, key: str, value: Any) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO cache_entries (key, value, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, created_at = excluded.created_at",
                (key, json.dumps(value, default=str), time.time()),
            )

    def delete(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cache_entries")


_default_cache: Cache | None = None


def get_default_cache() -> Cache:
    """A shared, lazily-created Cache instance at the default path, so
    agents that don't need a custom cache (i.e. everywhere except tests)
    don't each open their own separate SQLite connection pool."""
    global _default_cache
    if _default_cache is None:
        _default_cache = Cache()
    return _default_cache
