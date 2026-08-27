"""
Search Agent — web search with a free-tier provider chain.

Standalone and independently testable: call `SearchAgent().run(query)` on
its own, or use `search_agent_node` once the LangGraph pipeline is wired up.
Either way it returns the same `AgentResult` with `source_agent="search_agent"`,
so nothing downstream (graph, citations, tests) cares which provider answered.

Why a chain instead of one provider: the free tiers are small and change
their terms, so no single provider is a safe single point of failure. With
`SEARCH_PROVIDER=auto` (the default) the configured keyed providers are tried
in priority order — Exa → Serper → Tavily — and keyless DuckDuckGo always
backstops them, so a run never hard-fails just because a key is missing or a
quota ran out. Set `SEARCH_PROVIDER` to a comma-separated list to force an
exact order (e.g. "serper,duckduckgo").

Hardening (carried over from the original Tavily-only agent): a cache check
runs before each provider call — a repeated query within the TTL costs zero
credits — and every network call is wrapped in exponential backoff, retrying
only transient failures (429 / 5xx / network). A provider that errors or
returns nothing is skipped and the next one is tried; only when the whole
chain comes up empty do we report why.
"""

from typing import Protocol

import requests

from app.cache import Cache, get_default_cache
from app.config import Settings, get_settings
from app.retry import (
    RetryExhausted,
    call_with_backoff,
    is_retryable_http_error,
    is_retryable_tavily_error,
)
from app.schemas import AgentResult, Document, SourceType

# Kept stable on purpose: graph.py, citations, and the tests all key off this
# exact string. The provider that actually answered is an internal detail.
SOURCE_AGENT = "search_agent"


class SearchProvider(Protocol):
    """What SearchAgent needs from a provider. `search` returns normalized
    Documents or raises; the agent owns caching, ordering, and error
    aggregation so providers stay small and single-purpose."""

    name: str
    requires_key: bool

    def is_configured(self) -> bool: ...

    def search(self, query: str, max_results: int, timeout: int) -> list[Document]: ...


# --------------------------------------------------------------- Exa (neural)

class ExaProvider:
    """Exa neural/keyword search (https://exa.ai). Free tier is a recurring
    monthly credit, so keep calls cheap: `type=auto` and highlights only (no
    full-page text, no deep research), which is plenty for snippets."""

    name = "exa"
    requires_key = True

    def __init__(self, settings: Settings, client=None):
        self._api_key = settings.exa_api_key
        self._search_type = settings.exa_search_type or "auto"
        self._client = client  # injectable for tests; otherwise built lazily

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is not None:
            return self._client
        # Lazy import so the package is only required when Exa is actually used.
        from exa_py import Exa

        return Exa(api_key=self._api_key)

    def search(self, query: str, max_results: int, timeout: int) -> list[Document]:
        client = self._get_client()

        def _call():
            # search_and_contents(highlights=True) is the stable exa-py way to
            # get snippet-sized highlights back in one round trip; it maps to
            # the guide's search(..., contents={"highlights": True}).
            return client.search_and_contents(
                query,
                type=self._search_type,
                num_results=max_results,
                highlights=True,
            )

        response = call_with_backoff(_call, is_retryable=is_retryable_http_error)

        documents: list[Document] = []
        for item in getattr(response, "results", None) or []:
            highlights = getattr(item, "highlights", None) or []
            snippet = " … ".join(h.strip() for h in highlights if h) or getattr(item, "text", None)
            documents.append(
                Document(
                    title=getattr(item, "title", None) or "Untitled",
                    url=getattr(item, "url", "") or "",
                    snippet=snippet,
                    source=SourceType.WEB,
                    relevance_score=getattr(item, "score", None),
                )
            )
        return documents


# ------------------------------------------------------------- Serper (Google)

class SerperProvider:
    """Serper (https://serper.dev) — Google SERP results over a plain HTTPS
    POST, so no SDK is needed (reuses `requests`, already a dependency). Free
    tier is a one-time allotment of ~2,500 lookups."""

    name = "serper"
    requires_key = True
    _ENDPOINT = "https://google.serper.dev/search"

    def __init__(self, settings: Settings):
        self._api_key = settings.serper_api_key

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def search(self, query: str, max_results: int, timeout: int) -> list[Document]:
        def _call():
            response = requests.post(
                self._ENDPOINT,
                headers={"X-API-KEY": self._api_key, "Content-Type": "application/json"},
                json={"q": query, "num": max_results},
                timeout=timeout,
            )
            # raise_for_status() attaches .response, so is_retryable_http_error
            # can see the 429/5xx status and back off on exactly those.
            response.raise_for_status()
            return response.json()

        payload = call_with_backoff(_call, is_retryable=is_retryable_http_error)

        documents: list[Document] = []
        for item in (payload.get("organic") or [])[:max_results]:
            documents.append(
                Document(
                    title=item.get("title") or "Untitled",
                    url=item.get("link", "") or "",
                    snippet=item.get("snippet"),
                    source=SourceType.WEB,
                    relevance_score=None,  # Serper returns rank, not a score
                )
            )
        return documents


# ---------------------------------------------------------- DuckDuckGo (keyless)

def _is_retryable_ddg_error(exc: Exception) -> bool:
    """DuckDuckGo is unofficial and rate-limits by IP without a real HTTP
    status we can read, so retry network hiccups plus anything whose message
    looks like a rate limit / timeout. Everything else fails fast."""
    if is_retryable_http_error(exc):
        return True
    text = str(exc).lower()
    return any(hint in text for hint in ("ratelimit", "rate limit", "429", "timeout", "timed out"))


class DuckDuckGoProvider:
    """Keyless, unlimited, always-free fallback via the `ddgs` package
    (formerly `duckduckgo_search`). Lower quality and rate-limited, but it
    guarantees the chain can always return *something* with zero config."""

    name = "duckduckgo"
    requires_key = False

    def __init__(self, settings: Settings | None = None, ddgs_factory=None):
        self._ddgs_factory = ddgs_factory  # injectable for tests

    def is_configured(self) -> bool:
        return True

    def _get_ddgs_factory(self):
        if self._ddgs_factory is not None:
            return self._ddgs_factory
        # ddgs was renamed from duckduckgo_search; tolerate either being installed.
        try:
            from ddgs import DDGS
        except ImportError:  # pragma: no cover - depends on which is installed
            from duckduckgo_search import DDGS
        return DDGS

    def search(self, query: str, max_results: int, timeout: int) -> list[Document]:
        ddgs_cls = self._get_ddgs_factory()

        def _call():
            with ddgs_cls() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        results = call_with_backoff(_call, is_retryable=_is_retryable_ddg_error)

        documents: list[Document] = []
        for item in results or []:
            documents.append(
                Document(
                    title=item.get("title") or "Untitled",
                    url=item.get("href", "") or item.get("url", "") or "",
                    snippet=item.get("body"),
                    source=SourceType.WEB,
                    relevance_score=None,
                )
            )
        return documents


# ----------------------------------------------------------- Tavily (optional)

class TavilyProvider:
    """Original provider, kept for anyone who still has a key. Optional now:
    Tavily's free tier began asking for a card, so it is no longer part of the
    default chain unless TAVILY_API_KEY is set."""

    name = "tavily"
    requires_key = True

    def __init__(self, settings: Settings, client=None):
        self._api_key = settings.tavily_api_key
        self._client = client

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is not None:
            return self._client
        from tavily import TavilyClient

        return TavilyClient(api_key=self._api_key)

    def search(self, query: str, max_results: int, timeout: int) -> list[Document]:
        client = self._get_client()

        def _call():
            # "basic" depth is 1 credit/search vs 2 for "advanced".
            return client.search(
                query=query,
                search_depth="basic",
                max_results=max_results,
                include_answer=False,
                timeout=timeout,
            )

        response = call_with_backoff(_call, is_retryable=is_retryable_tavily_error)

        documents: list[Document] = []
        for item in response.get("results", []):
            documents.append(
                Document(
                    title=item.get("title") or "Untitled",
                    url=item.get("url", "") or "",
                    snippet=item.get("content"),
                    source=SourceType.WEB,
                    relevance_score=item.get("score"),
                )
            )
        return documents


# ------------------------------------------------------------- Chain assembly

_PROVIDER_BUILDERS = {
    "exa": lambda s: ExaProvider(s),
    "serper": lambda s: SerperProvider(s),
    "tavily": lambda s: TavilyProvider(s),
    "duckduckgo": lambda s: DuckDuckGoProvider(s),
}

# Priority for SEARCH_PROVIDER=auto. DuckDuckGo is keyless, so it is always the
# final backstop; the keyed providers ahead of it are only included when their
# key is present.
_AUTO_PRIORITY = ["exa", "serper", "tavily", "duckduckgo"]


def _build_provider_chain(settings: Settings) -> list[SearchProvider]:
    raw = (settings.search_provider or "auto").strip().lower()

    if raw in ("", "auto"):
        chain: list[SearchProvider] = []
        for name in _AUTO_PRIORITY:
            provider = _PROVIDER_BUILDERS[name](settings)
            if not provider.requires_key or provider.is_configured():
                chain.append(provider)
        return chain  # DuckDuckGo is keyless, so this is never empty

    # Explicit comma- (or semicolon-) separated list, honored in the given order.
    names = [n.strip() for n in raw.replace(";", ",").split(",") if n.strip()]
    chain = [_PROVIDER_BUILDERS[n](settings) for n in names if n in _PROVIDER_BUILDERS]
    # Never hard-fail: if the user named only providers that aren't usable
    # (e.g. SEARCH_PROVIDER=exa with no key), fall back to keyless DuckDuckGo.
    if not any((not p.requires_key) or p.is_configured() for p in chain):
        chain.append(DuckDuckGoProvider(settings))
    return chain


class SearchAgent:
    def __init__(self, cache: Cache | None = None, providers: list[SearchProvider] | None = None):
        self.settings = get_settings()
        self.timeout = self.settings.request_timeout_seconds
        self.default_max = self.settings.default_web_results
        self._cache = cache if cache is not None else get_default_cache()
        # `providers` is injectable for tests; production builds from settings.
        self._providers = providers if providers is not None else _build_provider_chain(self.settings)

    def run(self, query: str, max_results: int | None = None) -> AgentResult:
        max_results = max_results or self.default_max
        errors: list[str] = []

        for provider in self._providers:
            if provider.requires_key and not provider.is_configured():
                errors.append(f"{provider.name}: API key not configured — skipped.")
                continue

            # Cache is keyed per provider so switching providers can't serve a
            # stale answer shaped by a different one.
            cache_key = Cache.make_key(f"{provider.name}_search", query=query, max_results=max_results)
            cached = self._cache.get(cache_key)
            if cached is not None:
                documents = [Document(**item) for item in cached]
                return AgentResult(query=query, documents=documents, errors=[], source_agent=SOURCE_AGENT)

            try:
                documents = provider.search(query, max_results, self.timeout)
            except RetryExhausted as exc:
                errors.append(f"{provider.name}: gave up after retries ({exc.last_exception}).")
                continue
            except Exception as exc:  # noqa: BLE001 - one provider failing must not sink the chain
                errors.append(f"{provider.name}: {exc}")
                continue

            if not documents:
                errors.append(f"{provider.name}: no results.")
                continue

            # A provider succeeded: cache it and return clean. Earlier providers'
            # transient errors are intentionally dropped — the chain did its job.
            self._cache.set(cache_key, [doc.model_dump() for doc in documents])
            return AgentResult(query=query, documents=documents, errors=[], source_agent=SOURCE_AGENT)

        # Whole chain came up empty — surface the collected reasons so it's debuggable.
        if not errors:
            errors = ["No web search provider is configured — see .env.example (EXA / SERPER / SEARCH_PROVIDER)."]
        return AgentResult(query=query, documents=[], errors=errors, source_agent=SOURCE_AGENT)


def search_agent_node(state: dict) -> dict:
    """LangGraph node wrapper: reads `query` + `max_web_results` from state,
    returns partial-state updates for `web_results` and `errors`."""
    agent = SearchAgent()
    result = agent.run(state["query"], max_results=state.get("max_web_results"))
    return {
        "web_results": result.documents,
        "errors": [*state.get("errors", []), *result.errors],
    }
