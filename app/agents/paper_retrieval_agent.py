"""
Paper Retrieval Agent — academic search via ArXiv + Semantic Scholar.

Standalone and independently testable, same shape as SearchAgent. ArXiv and
Semantic Scholar are queried separately and merged; a failure in one source
doesn't stop the other (each is caught and reported in `errors` instead of
raising), which matters since these are two independent free services with
their own outages/rate limits.

Hardening (Phase 7): both sources are cached (a repeated query within the
TTL makes zero requests to either). Semantic Scholar's request is also
wrapped in exponential backoff, retrying only a 429 (rate limited) or a
5xx (transient server issue) — see retry.py. ArXiv is deliberately NOT
wrapped in a second retry layer: the `arxiv` package already retries
HTTPError/ConnectionError internally (`num_retries`, default 3), and
stacking another retry loop on top would just multiply the worst-case
wait time for no benefit.
"""

import arxiv
import requests

from app.cache import Cache, get_default_cache
from app.config import get_settings
from app.retry import RetryExhausted, call_with_backoff, http_status_code, is_retryable_http_error
from app.schemas import AgentResult, Document, SourceType

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


class PaperRetrievalAgent:
    def __init__(self, semantic_scholar_api_key: str | None = None, cache: Cache | None = None):
        settings = get_settings()
        self.ss_api_key = semantic_scholar_api_key or settings.semantic_scholar_api_key
        self.timeout = settings.request_timeout_seconds
        # delay_seconds=3.0 (the package default) is ArXiv's own requested
        # politeness interval — leave it alone rather than speeding it up.
        self._arxiv_client = arxiv.Client(delay_seconds=3.0)
        self._cache = cache if cache is not None else get_default_cache()

    def search_arxiv(self, query: str, max_results: int) -> list[Document]:
        cache_key = Cache.make_key("arxiv_search", query=query, max_results=max_results)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return [Document(**item) for item in cached]

        search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)
        documents = []
        for result in self._arxiv_client.results(search):
            documents.append(
                Document(
                    title=result.title,
                    authors=[author.name for author in result.authors],
                    abstract=result.summary,
                    url=result.entry_id,
                    source=SourceType.ARXIV,
                    published_date=result.published.isoformat() if result.published else None,
                    raw_id=result.get_short_id(),
                )
            )

        if documents:
            self._cache.set(cache_key, [doc.model_dump() for doc in documents])
        return documents

    def search_semantic_scholar(self, query: str, max_results: int) -> list[Document]:
        cache_key = Cache.make_key("semantic_scholar_search", query=query, max_results=max_results)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return [Document(**item) for item in cached]

        headers = {"x-api-key": self.ss_api_key} if self.ss_api_key else {}
        params = {
            "query": query,
            "limit": max_results,
            "fields": "title,authors,abstract,url,year,citationCount,externalIds",
        }

        def make_request():
            resp = requests.get(SEMANTIC_SCHOLAR_SEARCH_URL, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp

        resp = call_with_backoff(make_request, is_retryable=is_retryable_http_error)
        data = resp.json()

        documents = []
        for paper in data.get("data", []):
            documents.append(
                Document(
                    title=paper.get("title") or "Untitled",
                    authors=[a["name"] for a in paper.get("authors", []) if a.get("name")],
                    abstract=paper.get("abstract"),
                    url=paper.get("url", ""),
                    source=SourceType.SEMANTIC_SCHOLAR,
                    published_date=str(paper["year"]) if paper.get("year") else None,
                    citation_count=paper.get("citationCount"),
                    raw_id=paper.get("paperId"),
                )
            )

        if documents:
            self._cache.set(cache_key, [doc.model_dump() for doc in documents])
        return documents

    def run(self, query: str, max_results: int | None = None) -> AgentResult:
        settings = get_settings()
        max_results = max_results or settings.default_paper_results
        documents: list[Document] = []
        errors: list[str] = []

        try:
            documents.extend(self.search_arxiv(query, max_results))
        except Exception as exc:
            errors.append(f"ArXiv search failed: {exc}")

        try:
            documents.extend(self.search_semantic_scholar(query, max_results))
        except RetryExhausted as exc:
            status = http_status_code(exc.last_exception)
            if status == 429:
                errors.append(
                    "Semantic Scholar rate limit persisted after retries — add SEMANTIC_SCHOLAR_API_KEY "
                    "in .env for a dedicated (higher) limit."
                )
            else:
                errors.append(f"Semantic Scholar search failed after retries (HTTP {status}): {exc.last_exception}")
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            errors.append(f"Semantic Scholar search failed (HTTP {status}): {exc}")
        except Exception as exc:
            errors.append(f"Semantic Scholar search failed: {exc}")

        return AgentResult(
            query=query,
            documents=documents,
            errors=errors,
            source_agent="paper_retrieval_agent",
        )


def paper_retrieval_node(state: dict) -> dict:
    """LangGraph node wrapper — see search_agent.py's node for the pattern."""
    agent = PaperRetrievalAgent()
    result = agent.run(state["query"], max_results=state.get("max_paper_results"))
    return {
        "paper_results": result.documents,
        "errors": [*state.get("errors", []), *result.errors],
    }
