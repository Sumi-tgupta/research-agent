"""
Crossref Agent — scholarly metadata via the Crossref REST API
(https://api.crossref.org).

Keyless and free. Crossref is the DOI registration agency for most academic
publishers, so it's strong on bibliographic metadata (authors, journal, year,
citation counts) across every discipline. Identifying yourself with a contact
email routes you into the "polite pool" (faster, more reliable); we send it as
both the `mailto` query param and in the User-Agent when `crossref_mailto` is
set, and fall back to the public pool otherwise.

Same cache + backoff hardening as the sibling agents. Two Crossref quirks
handled below: `title` and `container-title` are arrays (we take the first),
and `abstract` — when present — is JATS XML, which we strip to plain text.
"""

import re

import requests

from app.cache import Cache, get_default_cache
from app.config import get_settings
from app.retry import RetryExhausted, call_with_backoff, http_status_code, is_retryable_http_error
from app.schemas import AgentResult, Document, SourceType

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
USER_AGENT_BASE = "AureliaResearch/1.0 (research assistant; keyless free-tier client)"
MAX_ABSTRACT_CHARS = 2000

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_jats(abstract: str | None) -> str | None:
    """Crossref abstracts are JATS XML (<jats:p>…</jats:p>). Drop the tags and
    collapse whitespace to get plain text."""
    if not abstract:
        return None
    text = _WS_RE.sub(" ", _TAG_RE.sub("", abstract)).strip()
    if not text:
        return None
    return text[:MAX_ABSTRACT_CHARS]


def _first(value) -> str | None:
    """Crossref returns `title` / `container-title` as arrays."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _year(item: dict) -> str | None:
    """Pull a publication year from whichever date field is present."""
    for key in ("published", "published-print", "published-online", "issued", "created"):
        parts = item.get(key, {}).get("date-parts")
        if parts and parts[0] and parts[0][0]:
            return str(parts[0][0])
    return None


def _authors(item: dict) -> list[str]:
    names: list[str] = []
    for author in item.get("author", []):
        given, family = author.get("given"), author.get("family")
        full = " ".join(part for part in (given, family) if part)
        names.append(full or author.get("name") or "")
    return [name for name in names if name]


class CrossrefAgent:
    def __init__(self, mailto: str | None = None, cache: Cache | None = None):
        settings = get_settings()
        self.mailto = mailto if mailto is not None else settings.crossref_mailto
        self.timeout = settings.request_timeout_seconds
        self._cache = cache if cache is not None else get_default_cache()

    def run(self, query: str, max_results: int | None = None) -> AgentResult:
        settings = get_settings()
        max_results = max_results or settings.default_paper_results
        errors: list[str] = []

        cache_key = Cache.make_key("crossref_search", query=query, max_results=max_results)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return AgentResult(
                query=query,
                documents=[Document(**item) for item in cached],
                errors=[],
                source_agent="crossref_agent",
            )

        params = {
            "query": query,
            "rows": max_results,
            "select": "DOI,title,author,abstract,URL,published,is-referenced-by-count",
        }
        user_agent = USER_AGENT_BASE
        if self.mailto:
            params["mailto"] = self.mailto
            user_agent = f"{USER_AGENT_BASE} mailto:{self.mailto}"
        headers = {"User-Agent": user_agent}

        def make_request():
            resp = requests.get(CROSSREF_WORKS_URL, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp

        try:
            resp = call_with_backoff(make_request, is_retryable=is_retryable_http_error)
        except RetryExhausted as exc:
            status = http_status_code(exc.last_exception)
            errors.append(f"Crossref search failed after retries (HTTP {status}): {exc.last_exception}")
            return AgentResult(query=query, errors=errors, source_agent="crossref_agent")
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            errors.append(f"Crossref search failed (HTTP {status}): {exc}")
            return AgentResult(query=query, errors=errors, source_agent="crossref_agent")
        except Exception as exc:
            errors.append(f"Crossref search failed: {exc}")
            return AgentResult(query=query, errors=errors, source_agent="crossref_agent")

        items = resp.json().get("message", {}).get("items", [])
        documents: list[Document] = []
        for item in items:
            doi = item.get("DOI")
            documents.append(
                Document(
                    title=_first(item.get("title")) or "Untitled",
                    authors=_authors(item),
                    abstract=_strip_jats(item.get("abstract")),
                    url=item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
                    source=SourceType.CROSSREF,
                    published_date=_year(item),
                    citation_count=item.get("is-referenced-by-count"),
                    raw_id=doi,
                )
            )

        if documents:
            self._cache.set(cache_key, [doc.model_dump() for doc in documents])

        return AgentResult(query=query, documents=documents, errors=errors, source_agent="crossref_agent")
