"""
A simple persistent, TTL-based cache for expensive/rate-limited retrieval
calls (web search, paper lookups). Backed by SQLite (stdlib — no extra
dependency) specifically so cached results survive process restarts: the
whole point is not re-spending a web-search provider's free budget (Exa's
monthly credit, Serper's lookup quota) or Semantic Scholar's shared rate
limit on a query already made yesterday,
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
        """A stable cache key from a namespace (e.g. 'exa_search') plus
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


# --------------------------------------------------------------------------- #
# Alternate backends (Phase 12)
#
# The default SQLite backend above writes to a local file, which is perfect for
# dev and self-hosting but useless on hosts with an ephemeral filesystem (HF
# Spaces, Render's free tier): the file — and thus the whole point of surviving
# restarts — vanishes on every redeploy. These two backends move the same cache
# to durable shared infrastructure the free stack already provides. Both
# subclass Cache so agents keep their `cache: Cache | None` annotations and the
# shared `Cache.make_key` unchanged; only the storage of a key/value/timestamp
# differs. Neither is in the ORM or Alembic on purpose — cache rows are
# disposable operational data, recreated on demand, not user content.
# --------------------------------------------------------------------------- #


class RedisCache(Cache):
    """Redis-backed cache (the free tier of Upstash/Redis Cloud works well).

    Keys are namespaced with a fixed prefix so ``clear()`` only drops this app's
    entries via SCAN — it never issues FLUSHDB, which would wipe a database that
    might be shared with something else. TTL is delegated to Redis itself
    (``SET ... EX``), so there's none of the SQLite backend's created_at
    bookkeeping.
    """

    _PREFIX = "apexcache:"

    def __init__(self, url: str, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        # NB: deliberately does NOT call super().__init__ — we don't want the
        # SQLite file created/opened for a Redis-backed instance.
        try:
            import redis  # lazy: only imported when this backend is selected
        except Exception as exc:  # pragma: no cover - exercised via the factory's fallback
            raise RuntimeError(
                "cache_backend='redis' needs the 'redis' package (pip install redis)"
            ) from exc
        self.ttl_seconds = ttl_seconds
        # decode_responses=True → get() returns str, not bytes.
        self._client = redis.Redis.from_url(url, decode_responses=True)
        # Ping now so an unreachable server fails here, letting the factory fall
        # back to SQLite at startup rather than on the first cached call.
        self._client.ping()

    def _k(self, key: str) -> str:
        return f"{self._PREFIX}{key}"

    def get(self, key: str) -> Any | None:
        raw = self._client.get(self._k(key))
        return json.loads(raw) if raw is not None else None

    def set(self, key: str, value: Any) -> None:
        self._client.set(self._k(key), json.dumps(value, default=str), ex=int(self.ttl_seconds))

    def delete(self, key: str) -> None:
        self._client.delete(self._k(key))

    def clear(self) -> None:
        for k in self._client.scan_iter(match=f"{self._PREFIX}*"):
            self._client.delete(k)


class PostgresCache(Cache):
    """SQL cache over a SQLAlchemy engine — intended for the same Postgres the
    saved library uses (reuse ``DATABASE_URL``), so the retrieval cache survives
    restarts on an ephemeral host.

    Mirrors the SQLite backend's schema and read-time TTL/expiry-delete. The SQL
    (``CREATE TABLE IF NOT EXISTS`` + ``INSERT ... ON CONFLICT``) is understood
    by both Postgres and SQLite, so a misconfigured sqlite URL still works rather
    than erroring.
    """

    def __init__(self, url: str, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        # As with RedisCache, no super().__init__: no local SQLite file.
        from sqlalchemy import create_engine

        self.ttl_seconds = ttl_seconds
        self._engine = create_engine(url, pool_pre_ping=True)
        self._init_table()

    def _init_table(self) -> None:
        from sqlalchemy import text

        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS retrieval_cache ("
                    "key VARCHAR(64) PRIMARY KEY, value TEXT NOT NULL, "
                    "created_at DOUBLE PRECISION NOT NULL)"
                )
            )

    def get(self, key: str) -> Any | None:
        from sqlalchemy import text

        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT value, created_at FROM retrieval_cache WHERE key = :k"),
                {"k": key},
            ).fetchone()
        if row is None:
            return None
        value_json, created_at = row[0], row[1]
        if time.time() - float(created_at) > self.ttl_seconds:
            self.delete(key)
            return None
        return json.loads(value_json)

    def set(self, key: str, value: Any) -> None:
        from sqlalchemy import text

        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO retrieval_cache (key, value, created_at) "
                    "VALUES (:k, :v, :c) "
                    "ON CONFLICT (key) DO UPDATE SET "
                    "value = excluded.value, created_at = excluded.created_at"
                ),
                {"k": key, "v": json.dumps(value, default=str), "c": time.time()},
            )

    def delete(self, key: str) -> None:
        from sqlalchemy import text

        with self._engine.begin() as conn:
            conn.execute(text("DELETE FROM retrieval_cache WHERE key = :k"), {"k": key})

    def clear(self) -> None:
        from sqlalchemy import text

        with self._engine.begin() as conn:
            conn.execute(text("DELETE FROM retrieval_cache"))


_default_cache: Cache | None = None


def _build_cache_from_settings() -> Cache:
    """Pick a cache backend from ``settings.cache_backend`` ("sqlite" | "redis" |
    "postgres"). A cache is a pure optimization, so any backend that can't be
    built (missing driver, unreachable server, blank URL) degrades to the
    always-available local SQLite backend rather than failing retrieval — the
    only cost of a misconfigured backend is a cold cache, never a broken run."""
    from app.config import get_settings  # lazy: avoids an import cycle at load

    settings = get_settings()
    backend = (getattr(settings, "cache_backend", "sqlite") or "sqlite").strip().lower()
    try:
        if backend == "redis":
            if not settings.redis_url:
                return Cache()  # no URL configured → local file cache
            return RedisCache(settings.redis_url)
        if backend == "postgres":
            return PostgresCache(settings.database_url)
    except Exception:
        return Cache()  # fail open to the local backend
    return Cache()


def get_default_cache() -> Cache:
    """A shared, lazily-created Cache instance selected by config, so agents
    that don't need a custom cache (i.e. everywhere except tests) don't each
    open their own separate backend connection."""
    global _default_cache
    if _default_cache is None:
        _default_cache = _build_cache_from_settings()
    return _default_cache


def reset_default_cache() -> None:
    """Drop the memoized default instance so the next ``get_default_cache()``
    rebuilds it — used by tests, and after a settings change."""
    global _default_cache
    _default_cache = None
