"""
PubMed Agent — biomedical literature via Europe PMC
(https://europepmc.org/RestfulWebService).

Europe PMC mirrors PubMed/MEDLINE plus preprints and gives a keyless JSON API,
which is why we go through it rather than NCBI E-utilities (E-utilities is XML,
throttles hard without an API key, and asks for tool/email registration).
Nothing to configure — it's free and open.

`resultType=core` is what makes this worthwhile: it returns the abstract text
inline, so the Fact Checker has real content to verify against rather than just
a title. Same cache + backoff hardening as the sibling retrieval agents; a
failure is reported in `errors`, never raised.
"""

import requests

from app.cache import Cache, get_default_cache
from app.config import get_settings
from app.retry import RetryExhausted, call_with_backoff, http_status_code, is_retryable_http_error
from app.schemas import AgentResult, Document, SourceType

EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
USER_AGENT = "AureliaResearch/1.0 (research assistant; keyless free-tier client)"


def _result_url(result: dict) -> str:
    """Best available canonical link for a Europe PMC record, in order of
    preference: DOI, then the PubMed page, then the Europe PMC article page."""
    doi = result.get("doi")
    if doi:
        return f"https://doi.org/{doi}"
    pmid = result.get("pmid")
    if pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    source, rec_id = result.get("source"), result.get("id")
    if source and rec_id:
        return f"https://europepmc.org/article/{source}/{rec_id}"
    return ""


def _authors(result: dict) -> list[str]:
    """Europe PMC gives a flat `authorString` ("Smith J, Doe A."); a structured
    authorList is also sometimes present. Prefer the structured names, fall back
    to splitting the string."""
    author_list = result.get("authorList", {}).get("author", [])
    names = [a.get("fullName") for a in author_list if a.get("fullName")]
    if names:
        return names
    author_string = (result.get("authorString") or "").rstrip(".")
    return [name.strip() for name in author_string.split(",") if name.strip()]


class PubMedAgent:
    def __init__(self, cache: Cache | None = None):
        settings = get_settings()
        self.timeout = settings.request_timeout_seconds
        self._cache = cache if cache is not None else get_default_cache()

    def run(self, query: str, max_results: int | None = None) -> AgentResult:
        settings = get_settings()
        max_results = max_results or settings.default_paper_results
        errors: list[str] = []

        cache_key = Cache.make_key("europepmc_search", query=query, max_results=max_results)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return AgentResult(
                query=query,
                documents=[Document(**item) for item in cached],
                errors=[],
                source_agent="pubmed_agent",
            )

        params = {
            "query": query,
            "format": "json",
            "pageSize": max_results,
            "resultType": "core",  # includes abstractText
        }
        headers = {"User-Agent": USER_AGENT}

        def make_request():
            resp = requests.get(EUROPE_PMC_SEARCH_URL, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp

        try:
            resp = call_with_backoff(make_request, is_retryable=is_retryable_http_error)
        except RetryExhausted as exc:
            status = http_status_code(exc.last_exception)
            errors.append(f"Europe PMC search failed after retries (HTTP {status}): {exc.last_exception}")
            return AgentResult(query=query, errors=errors, source_agent="pubmed_agent")
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            errors.append(f"Europe PMC search failed (HTTP {status}): {exc}")
            return AgentResult(query=query, errors=errors, source_agent="pubmed_agent")
        except Exception as exc:
            errors.append(f"Europe PMC search failed: {exc}")
            return AgentResult(query=query, errors=errors, source_agent="pubmed_agent")

        results = resp.json().get("resultList", {}).get("result", [])
        documents: list[Document] = []
        for result in results:
            documents.append(
                Document(
                    title=result.get("title") or "Untitled",
                    authors=_authors(result),
                    abstract=result.get("abstractText"),
                    url=_result_url(result),
                    source=SourceType.PUBMED,
                    published_date=result.get("pubYear"),
                    citation_count=result.get("citedByCount"),
                    raw_id=result.get("pmid") or result.get("id"),
                )
            )

        if documents:
            self._cache.set(cache_key, [doc.model_dump() for doc in documents])

        return AgentResult(query=query, documents=documents, errors=errors, source_agent="pubmed_agent")
