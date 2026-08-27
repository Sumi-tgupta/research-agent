"""
OpenAlex Agent — academic works via the OpenAlex API (https://openalex.org).

Fully keyless and free. OpenAlex indexes ~250M scholarly works and asks only
that heavier users identify themselves with a contact email to enter the
"polite pool" (faster, more reliable) — we pass one when `crossref_mailto`
is configured, and work anonymously otherwise.

Same shape/hardening as the other retrieval agents: a cache check runs before
every call, and the HTTP request is wrapped in exponential backoff that retries
only a 429 or 5xx (see retry.py). A failure here is reported in `errors`, never
raised, so one flaky source can't sink a multi-source pipeline.

One OpenAlex quirk: works don't ship a plain-text abstract (licensing). They
ship an `abstract_inverted_index` — {word: [positions]} — which we reconstruct
back into readable text below.
"""

import requests

from app.cache import Cache, get_default_cache
from app.config import get_settings
from app.retry import RetryExhausted, call_with_backoff, http_status_code, is_retryable_http_error
from app.schemas import AgentResult, Document, SourceType

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
USER_AGENT = "AureliaResearch/1.0 (research assistant; keyless free-tier client)"

# OpenAlex abstracts can be long; keep enough for fact-checking without bloating
# the cache or the LLM context. 2000 chars comfortably covers a full abstract.
MAX_ABSTRACT_CHARS = 2000


def _reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Rebuild readable text from OpenAlex's abstract_inverted_index.

    The index maps each word to the positions it occupies, e.g.
    {"the": [0, 5], "cell": [1]} → "the cell ... the ...". We invert that back
    into a position-ordered word list and join it.
    """
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, indices in inverted_index.items():
        for idx in indices:
            positions.append((idx, word))
    if not positions:
        return None
    positions.sort(key=lambda pair: pair[0])
    text = " ".join(word for _, word in positions).strip()
    if not text:
        return None
    return text[:MAX_ABSTRACT_CHARS]


class OpenAlexAgent:
    def __init__(self, mailto: str | None = None, cache: Cache | None = None):
        settings = get_settings()
        # OpenAlex and Crossref both accept a contact email for their polite
        # pools; we reuse the one configured setting for both.
        self.mailto = mailto if mailto is not None else settings.crossref_mailto
        self.timeout = settings.request_timeout_seconds
        self._cache = cache if cache is not None else get_default_cache()

    def run(self, query: str, max_results: int | None = None) -> AgentResult:
        settings = get_settings()
        max_results = max_results or settings.default_paper_results
        errors: list[str] = []

        cache_key = Cache.make_key("openalex_search", query=query, max_results=max_results)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return AgentResult(
                query=query,
                documents=[Document(**item) for item in cached],
                errors=[],
                source_agent="openalex_agent",
            )

        params = {
            "search": query,
            "per_page": max_results,
            # Ask only for the fields we map — smaller, faster responses.
            "select": (
                "id,doi,display_name,authorships,publication_year,"
                "cited_by_count,abstract_inverted_index"
            ),
        }
        if self.mailto:
            params["mailto"] = self.mailto
        headers = {"User-Agent": USER_AGENT}

        def make_request():
            resp = requests.get(OPENALEX_WORKS_URL, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp

        try:
            resp = call_with_backoff(make_request, is_retryable=is_retryable_http_error)
        except RetryExhausted as exc:
            status = http_status_code(exc.last_exception)
            errors.append(f"OpenAlex search failed after retries (HTTP {status}): {exc.last_exception}")
            return AgentResult(query=query, errors=errors, source_agent="openalex_agent")
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            errors.append(f"OpenAlex search failed (HTTP {status}): {exc}")
            return AgentResult(query=query, errors=errors, source_agent="openalex_agent")
        except Exception as exc:
            errors.append(f"OpenAlex search failed: {exc}")
            return AgentResult(query=query, errors=errors, source_agent="openalex_agent")

        documents: list[Document] = []
        for work in resp.json().get("results", []):
            authors = [
                a.get("author", {}).get("display_name")
                for a in work.get("authorships", [])
            ]
            doi = work.get("doi")  # already a full https://doi.org/... URL
            openalex_id = work.get("id", "")
            documents.append(
                Document(
                    title=work.get("display_name") or "Untitled",
                    authors=[a for a in authors if a],
                    abstract=_reconstruct_abstract(work.get("abstract_inverted_index")),
                    url=doi or openalex_id,
                    source=SourceType.OPENALEX,
                    published_date=str(work["publication_year"]) if work.get("publication_year") else None,
                    citation_count=work.get("cited_by_count"),
                    raw_id=openalex_id.rsplit("/", 1)[-1] if openalex_id else None,
                )
            )

        if documents:
            self._cache.set(cache_key, [doc.model_dump() for doc in documents])

        return AgentResult(query=query, documents=documents, errors=errors, source_agent="openalex_agent")
