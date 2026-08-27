"""
Wikipedia Agent — encyclopedic context via the MediaWiki API
(https://en.wikipedia.org/w/api.php).

Keyless and free. Wikipedia isn't a primary source, but it's excellent for
grounding: definitions, background, and orientation on an unfamiliar topic,
with the article itself linking onward to primary sources. It fills the gap
between a raw web result and a peer-reviewed paper, so it's treated as a
WEB-like reference source and its intro text goes in `snippet` (not `abstract`,
which is reserved for paper abstracts).

One request does both jobs: `generator=search` finds the top articles, and
`prop=extracts` returns each article's plain-text intro in the same response —
no per-article follow-up calls. Same cache + backoff hardening as the other
agents; a failure is reported in `errors`, never raised.
"""

import requests

from app.cache import Cache, get_default_cache
from app.config import get_settings
from app.retry import RetryExhausted, call_with_backoff, http_status_code, is_retryable_http_error
from app.schemas import AgentResult, Document, SourceType

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "AureliaResearch/1.0 (research assistant; keyless free-tier client)"

# Intros can run long; keep a useful lead without dragging the whole article
# into the cache and the LLM context.
MAX_SNIPPET_CHARS = 1200


class WikipediaAgent:
    def __init__(self, cache: Cache | None = None):
        settings = get_settings()
        self.timeout = settings.request_timeout_seconds
        self._cache = cache if cache is not None else get_default_cache()

    def run(self, query: str, max_results: int | None = None) -> AgentResult:
        settings = get_settings()
        max_results = max_results or settings.default_web_results
        errors: list[str] = []

        cache_key = Cache.make_key("wikipedia_search", query=query, max_results=max_results)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return AgentResult(
                query=query,
                documents=[Document(**item) for item in cached],
                errors=[],
                source_agent="wikipedia_agent",
            )

        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": max_results,
            "prop": "extracts|info",
            "exintro": 1,        # intro section only
            "explaintext": 1,    # plain text, not HTML
            "exlimit": "max",    # extract for every generated page in one call
            "inprop": "url",     # include canonical fullurl
            "redirects": 1,
        }
        headers = {"User-Agent": USER_AGENT}

        def make_request():
            resp = requests.get(WIKIPEDIA_API_URL, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp

        try:
            resp = call_with_backoff(make_request, is_retryable=is_retryable_http_error)
        except RetryExhausted as exc:
            status = http_status_code(exc.last_exception)
            errors.append(f"Wikipedia search failed after retries (HTTP {status}): {exc.last_exception}")
            return AgentResult(query=query, errors=errors, source_agent="wikipedia_agent")
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            errors.append(f"Wikipedia search failed (HTTP {status}): {exc}")
            return AgentResult(query=query, errors=errors, source_agent="wikipedia_agent")
        except Exception as exc:
            errors.append(f"Wikipedia search failed: {exc}")
            return AgentResult(query=query, errors=errors, source_agent="wikipedia_agent")

        # `pages` is a dict keyed by page id; `index` preserves search rank.
        pages = resp.json().get("query", {}).get("pages", {})
        ordered = sorted(pages.values(), key=lambda p: p.get("index", 1_000_000))

        documents: list[Document] = []
        for page in ordered:
            extract = (page.get("extract") or "").strip()
            documents.append(
                Document(
                    title=page.get("title") or "Untitled",
                    url=page.get("fullurl", ""),
                    snippet=extract[:MAX_SNIPPET_CHARS] or None,
                    source=SourceType.WIKIPEDIA,
                    raw_id=str(page["pageid"]) if page.get("pageid") is not None else None,
                )
            )

        if documents:
            self._cache.set(cache_key, [doc.model_dump() for doc in documents])

        return AgentResult(query=query, documents=documents, errors=errors, source_agent="wikipedia_agent")
