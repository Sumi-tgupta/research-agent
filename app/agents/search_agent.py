"""
Search Agent — web search via Tavily.

Standalone and independently testable: call `SearchAgent().run(query)` on
its own, or use `search_agent_node` once the LangGraph pipeline is wired up
in Phase 2. Either way it returns the same `AgentResult`.

Hardening (Phase 7): a cache check runs before every call — a repeated
query within the TTL costs zero Tavily credits — and the actual API call
is wrapped in exponential backoff, retrying only Tavily's own TimeoutError
plus generic network errors. Tavily's permanent failure modes (bad key,
monthly quota exhausted, malformed request) are deliberately not retried;
see retry.py's module docstring for why.
"""

from tavily import TavilyClient
from tavily.errors import (
    InvalidAPIKeyError,
    MissingAPIKeyError,
    UsageLimitExceededError,
)

from app.cache import Cache, get_default_cache
from app.config import get_settings
from app.retry import RetryExhausted, call_with_backoff, is_retryable_tavily_error
from app.schemas import AgentResult, Document, SourceType


class SearchAgent:
    def __init__(self, api_key: str | None = None, cache: Cache | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.tavily_api_key
        self.timeout = settings.request_timeout_seconds
        self._client = TavilyClient(api_key=self.api_key) if self.api_key else None
        self._cache = cache if cache is not None else get_default_cache()

    def run(self, query: str, max_results: int | None = None) -> AgentResult:
        settings = get_settings()
        max_results = max_results or settings.default_web_results
        errors: list[str] = []

        if self._client is None:
            return AgentResult(
                query=query,
                errors=["TAVILY_API_KEY not configured — see .env.example"],
                source_agent="search_agent",
            )

        cache_key = Cache.make_key("tavily_search", query=query, max_results=max_results)
        cached = self._cache.get(cache_key)
        if cached is not None:
            documents = [Document(**item) for item in cached]
            return AgentResult(query=query, documents=documents, errors=[], source_agent="search_agent")

        try:
            # "basic" depth costs 1 credit/search vs 2 for "advanced" —
            # matters on a 1,000-credit/month free tier. Bump to "advanced"
            # per-call later if a query needs deeper page content.
            response = call_with_backoff(
                lambda: self._client.search(
                    query=query,
                    search_depth="basic",
                    max_results=max_results,
                    include_answer=False,
                    timeout=self.timeout,
                ),
                is_retryable=is_retryable_tavily_error,
            )
        except MissingAPIKeyError as exc:
            errors.append(f"Tavily key missing: {exc}")
            return AgentResult(query=query, errors=errors, source_agent="search_agent")
        except InvalidAPIKeyError as exc:
            errors.append(f"Tavily key invalid: {exc}")
            return AgentResult(query=query, errors=errors, source_agent="search_agent")
        except UsageLimitExceededError as exc:
            errors.append(f"Tavily free-tier credits exhausted for this month: {exc}")
            return AgentResult(query=query, errors=errors, source_agent="search_agent")
        except RetryExhausted as exc:
            errors.append(f"Tavily search failed after retries: {exc.last_exception}")
            return AgentResult(query=query, errors=errors, source_agent="search_agent")
        except Exception as exc:  # non-retryable errors not covered above
            errors.append(f"Tavily search failed: {exc}")
            return AgentResult(query=query, errors=errors, source_agent="search_agent")

        documents = [
            Document(
                title=item.get("title") or "Untitled",
                url=item.get("url", ""),
                snippet=item.get("content"),
                source=SourceType.WEB,
                relevance_score=item.get("score"),
            )
            for item in response.get("results", [])
        ]

        if documents:
            self._cache.set(cache_key, [doc.model_dump() for doc in documents])

        return AgentResult(query=query, documents=documents, errors=errors, source_agent="search_agent")


def search_agent_node(state: dict) -> dict:
    """LangGraph node wrapper: reads `query` + `max_web_results` from state,
    returns partial-state updates for `web_results` and `errors`. Not wired
    into a graph until Phase 2 — see scripts/smoke_test_graph.py for a
    minimal proof this slots into a StateGraph cleanly."""
    agent = SearchAgent()
    result = agent.run(state["query"], max_results=state.get("max_web_results"))
    return {
        "web_results": result.documents,
        "errors": [*state.get("errors", []), *result.errors],
    }
