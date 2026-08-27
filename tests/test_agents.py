"""
Unit tests for the retrieval agents (Search, Paper Retrieval).

Everything here is mocked. None of Tavily / ArXiv / Semantic Scholar are
reachable from the sandbox this project was built in, so these tests prove
the parsing/normalization/error-handling/caching/retry logic is correct,
not that the live APIs behave as documented. Once you have real keys in
.env, also run:

    python -m scripts.smoke_test_graph "your query here"

for an actual end-to-end check against the live services.

Every SearchAgent/PaperRetrievalAgent in this file is given the
`isolated_cache` fixture (see conftest.py) explicitly. Without it, a
cached result from one test — or a previous test run entirely, since the
cache is a real file on disk — could silently satisfy a later test's
assertions without the mocked API call actually being exercised that time.
"""

import arxiv
import requests

from app.agents.paper_retrieval_agent import PaperRetrievalAgent, paper_retrieval_node
from app.agents.search_agent import (
    DuckDuckGoProvider,
    ExaProvider,
    SearchAgent,
    SerperProvider,
    TavilyProvider,
    _build_provider_chain,
    search_agent_node,
)
from app.cache import Cache
from app.config import Settings
from app.schemas import Document, SourceType
from tests.fakes import FakeResponse, FakeSearchProvider

def _settings(**overrides) -> Settings:
    """A Settings object with all defaults, overriding only what a test needs.
    model_construct skips env/.env loading, so these stay hermetic regardless
    of what's in the developer's real .env."""
    return Settings.model_construct(**overrides)


def _web_doc(title: str = "Doc", url: str = "https://example.com/x") -> Document:
    return Document(title=title, url=url, source=SourceType.WEB)


# --- SDK-shaped fakes: stand in for exa-py / tavily-python / ddgs so provider
# response mapping can be tested without those packages installed and without
# any network access. ---

class _ExaResult:
    def __init__(self, title, url, highlights=None, score=None, text=None):
        self.title = title
        self.url = url
        self.highlights = highlights or []
        self.score = score
        self.text = text


class _ExaResponse:
    def __init__(self, results):
        self.results = results


class _FakeExaClient:
    def __init__(self, response):
        self._response = response
        self.calls = 0

    def search_and_contents(self, query, **kwargs):
        self.calls += 1
        return self._response


class _FakeTavilyClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def search(self, **kwargs):
        self.calls += 1
        return self._payload


class _FakeDDGS:
    """Minimal context-manager stand-in for ddgs.DDGS."""

    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def text(self, query, max_results=None):
        return list(self._rows)


def _fake_arxiv_result(title: str = "A Fake Paper About Testing") -> arxiv.Result:
    return arxiv.Result(
        entry_id="https://arxiv.org/abs/1234.5678",
        title=title,
        authors=[arxiv.Result.Author(name="Ada Lovelace")],
        summary="This is a fake abstract used for testing.",
    )


# ---------------------------------------------------------------- Search Agent
#
# Two layers are covered:
#   1. Each provider maps its own API response to Documents (mocked SDK/HTTP).
#   2. The agent orders the chain, falls back, skips, caches, and aggregates
#      errors — all with injected FakeSearchProviders, so no network at all.
# Throughout, source_agent stays "search_agent" no matter which provider wins,
# because everything downstream keys off that string.

# --- provider response mapping ---

def test_exa_provider_maps_highlights_to_snippet():
    client = _FakeExaClient(
        _ExaResponse(
            [
                _ExaResult("Exa A", "https://exa.example/a", highlights=["first", "second"], score=0.91),
                _ExaResult("Exa B", "https://exa.example/b", highlights=[], text="fallback text"),
            ]
        )
    )
    provider = ExaProvider(_settings(exa_api_key="k"), client=client)

    docs = provider.search("q", max_results=2, timeout=5)

    assert client.calls == 1
    assert docs[0].title == "Exa A"
    assert docs[0].url == "https://exa.example/a"
    assert docs[0].snippet == "first … second"
    assert docs[0].source == SourceType.WEB
    assert docs[0].relevance_score == 0.91
    assert docs[1].snippet == "fallback text"  # no highlights → falls back to text


def test_serper_provider_maps_organic_results(mocker):
    mocker.patch(
        "app.agents.search_agent.requests.post",
        return_value=FakeResponse(
            {
                "organic": [
                    {"title": "Serper A", "link": "https://s.example/a", "snippet": "snip a", "position": 1},
                    {"title": "Serper B", "link": "https://s.example/b", "snippet": "snip b", "position": 2},
                ]
            }
        ),
    )
    provider = SerperProvider(_settings(serper_api_key="k"))

    docs = provider.search("q", max_results=5, timeout=5)

    assert [d.title for d in docs] == ["Serper A", "Serper B"]
    assert docs[0].url == "https://s.example/a"
    assert docs[0].snippet == "snip a"
    assert docs[0].source == SourceType.WEB


def test_serper_provider_retries_5xx_then_succeeds(mocker):
    mocker.patch("app.retry.time.sleep")  # skip real backoff delays
    calls = {"n": 0}

    def flaky_post(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            return FakeResponse({}, status_code=503)
        return FakeResponse({"organic": [{"title": "Recovered", "link": "https://x.com", "snippet": "c"}]})

    mocker.patch("app.agents.search_agent.requests.post", side_effect=flaky_post)
    provider = SerperProvider(_settings(serper_api_key="k"))

    docs = provider.search("q", max_results=3, timeout=5)

    assert calls["n"] == 2  # failed once, retried, then succeeded
    assert [d.title for d in docs] == ["Recovered"]


def test_duckduckgo_provider_maps_results():
    rows = [
        {"title": "DDG A", "href": "https://d.example/a", "body": "body a"},
        {"title": "DDG B", "href": "https://d.example/b", "body": "body b"},
    ]
    provider = DuckDuckGoProvider(ddgs_factory=lambda: _FakeDDGS(rows))

    docs = provider.search("q", max_results=5, timeout=5)

    assert [d.url for d in docs] == ["https://d.example/a", "https://d.example/b"]
    assert docs[0].snippet == "body a"
    assert docs[0].source == SourceType.WEB


def test_tavily_provider_maps_results():
    client = _FakeTavilyClient(
        {"results": [{"title": "Tavily A", "url": "https://t.example/a", "content": "c a", "score": 0.7}]}
    )
    provider = TavilyProvider(_settings(tavily_api_key="k"), client=client)

    docs = provider.search("q", max_results=3, timeout=5)

    assert client.calls == 1
    assert docs[0].title == "Tavily A"
    assert docs[0].relevance_score == 0.7
    assert docs[0].source == SourceType.WEB


# --- provider-chain assembly ---

def test_auto_chain_is_configured_keyed_providers_then_duckduckgo():
    chain = _build_provider_chain(_settings(search_provider="auto", serper_api_key="k"))
    # exa/tavily have no key so they drop out; keyless ddg is always the backstop.
    assert [p.name for p in chain] == ["serper", "duckduckgo"]


def test_explicit_chain_is_honored_in_the_given_order():
    chain = _build_provider_chain(
        _settings(search_provider="serper,exa", serper_api_key="k", exa_api_key="k2")
    )
    assert [p.name for p in chain] == ["serper", "exa"]


def test_explicit_chain_with_nothing_usable_degrades_to_duckduckgo():
    chain = _build_provider_chain(_settings(search_provider="exa"))  # no exa key set
    assert [p.name for p in chain] == ["exa", "duckduckgo"]


# --- agent orchestration (injected fake providers, no network) ---

def test_agent_returns_first_provider_with_results_and_short_circuits(isolated_cache):
    exa = FakeSearchProvider("exa", documents=[_web_doc("from exa")])
    serper = FakeSearchProvider("serper", documents=[_web_doc("from serper")])
    result = SearchAgent(cache=isolated_cache, providers=[exa, serper]).run("q", max_results=3)

    assert result.source_agent == "search_agent"
    assert result.errors == []
    assert [d.title for d in result.documents] == ["from exa"]
    assert exa.calls == 1
    assert serper.calls == 0  # never reached — exa already answered


def test_agent_falls_back_when_first_provider_errors(isolated_cache):
    exa = FakeSearchProvider("exa", error=RuntimeError("exa down"))
    serper = FakeSearchProvider("serper", documents=[_web_doc("from serper")])
    result = SearchAgent(cache=isolated_cache, providers=[exa, serper]).run("q", max_results=3)

    assert [d.title for d in result.documents] == ["from serper"]
    assert result.errors == []  # a successful fallback returns clean
    assert exa.calls == 1 and serper.calls == 1


def test_agent_falls_back_when_first_provider_returns_empty(isolated_cache):
    exa = FakeSearchProvider("exa", documents=[])
    serper = FakeSearchProvider("serper", documents=[_web_doc("from serper")])
    result = SearchAgent(cache=isolated_cache, providers=[exa, serper]).run("q", max_results=3)

    assert [d.title for d in result.documents] == ["from serper"]
    assert exa.calls == 1 and serper.calls == 1


def test_agent_reports_errors_when_the_whole_chain_fails(isolated_cache):
    exa = FakeSearchProvider("exa", error=RuntimeError("exa down"))
    serper = FakeSearchProvider("serper", error=RuntimeError("serper down"))
    result = SearchAgent(cache=isolated_cache, providers=[exa, serper]).run("q", max_results=3)

    assert result.documents == []
    assert any("exa" in e for e in result.errors)
    assert any("serper" in e for e in result.errors)


def test_agent_skips_unconfigured_keyed_provider_without_calling_it(isolated_cache):
    exa = FakeSearchProvider("exa", requires_key=True, configured=False, documents=[_web_doc("nope")])
    ddg = FakeSearchProvider("duckduckgo", requires_key=False, documents=[_web_doc("from ddg")])
    result = SearchAgent(cache=isolated_cache, providers=[exa, ddg]).run("q", max_results=3)

    assert exa.calls == 0  # no key → never invoked
    assert [d.title for d in result.documents] == ["from ddg"]


def test_agent_second_identical_call_hits_cache_not_the_provider(isolated_cache):
    exa = FakeSearchProvider("exa", documents=[_web_doc("cached")])
    agent = SearchAgent(cache=isolated_cache, providers=[exa])

    first = agent.run("repeated query", max_results=3)
    second = agent.run("repeated query", max_results=3)

    assert exa.calls == 1  # the second call was served entirely from cache
    assert second.documents == first.documents
    assert second.errors == []


def test_search_agent_node_preserves_prior_errors(mocker, isolated_cache):
    mocker.patch(
        "app.agents.search_agent._build_provider_chain",
        return_value=[FakeSearchProvider("exa", documents=[_web_doc("hit")])],
    )
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    state = {"query": "test", "max_web_results": 1, "errors": ["prior error"]}

    update = search_agent_node(state)

    assert len(update["web_results"]) == 1
    assert update["errors"] == ["prior error"]


# ---------------------------------------------------------- Paper Retrieval Agent

def test_paper_agent_merges_both_sources(mocker, isolated_cache):
    mocker.patch(
        "app.agents.paper_retrieval_agent.arxiv.Client.results",
        return_value=[_fake_arxiv_result()],
    )
    mocker.patch(
        "app.agents.paper_retrieval_agent.requests.get",
        return_value=FakeResponse(
            {
                "data": [
                    {
                        "title": "A Fake Semantic Scholar Paper",
                        "authors": [{"name": "Grace Hopper"}],
                        "abstract": "Another fake abstract.",
                        "url": "https://semanticscholar.org/paper/xyz",
                        "year": 2023,
                        "citationCount": 42,
                        "paperId": "abc123",
                    }
                ]
            }
        ),
    )

    result = PaperRetrievalAgent(cache=isolated_cache).run("test query", max_results=5)

    assert result.errors == []
    assert len(result.documents) == 2
    assert {doc.source for doc in result.documents} == {SourceType.ARXIV, SourceType.SEMANTIC_SCHOLAR}
    ss_doc = next(d for d in result.documents if d.source == SourceType.SEMANTIC_SCHOLAR)
    assert ss_doc.citation_count == 42
    assert ss_doc.authors == ["Grace Hopper"]


def test_paper_agent_arxiv_failure_does_not_block_semantic_scholar(mocker, isolated_cache):
    mocker.patch(
        "app.agents.paper_retrieval_agent.arxiv.Client.results",
        side_effect=RuntimeError("arxiv is down"),
    )
    mocker.patch(
        "app.agents.paper_retrieval_agent.requests.get",
        return_value=FakeResponse({"data": [{"title": "Still works", "authors": [], "url": "https://x.com"}]}),
    )

    result = PaperRetrievalAgent(cache=isolated_cache).run("test query")

    assert len(result.documents) == 1
    assert result.documents[0].source == SourceType.SEMANTIC_SCHOLAR
    assert any("ArXiv" in e for e in result.errors)


def test_paper_agent_semantic_scholar_rate_limit_gives_actionable_message(mocker, isolated_cache):
    mocker.patch("app.retry.time.sleep")  # this 429 persists across every retry - skip real delays
    mocker.patch("app.agents.paper_retrieval_agent.arxiv.Client.results", return_value=[])
    mocker.patch(
        "app.agents.paper_retrieval_agent.requests.get",
        return_value=FakeResponse({}, status_code=429),
    )

    result = PaperRetrievalAgent(cache=isolated_cache).run("test query")

    assert result.documents == []
    assert any("SEMANTIC_SCHOLAR_API_KEY" in e for e in result.errors)
    assert any("persisted after retries" in e for e in result.errors)


def test_paper_agent_semantic_scholar_retries_a_5xx_then_succeeds(mocker, isolated_cache):
    mocker.patch("app.retry.time.sleep")
    mocker.patch("app.agents.paper_retrieval_agent.arxiv.Client.results", return_value=[])
    call_count = {"n": 0}

    def flaky_get(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 2:
            return FakeResponse({}, status_code=503)
        return FakeResponse({"data": [{"title": "Recovered paper", "authors": [], "url": "https://x.com"}]})

    mocker.patch("app.agents.paper_retrieval_agent.requests.get", side_effect=flaky_get)

    result = PaperRetrievalAgent(cache=isolated_cache).run("test query")

    assert result.errors == []
    assert len(result.documents) == 1
    assert call_count["n"] == 2


def test_paper_agent_second_identical_call_hits_cache_for_both_sources(mocker, isolated_cache):
    arxiv_mock = mocker.patch(
        "app.agents.paper_retrieval_agent.arxiv.Client.results", return_value=[_fake_arxiv_result()]
    )
    ss_mock = mocker.patch(
        "app.agents.paper_retrieval_agent.requests.get",
        return_value=FakeResponse({"data": [{"title": "A paper", "authors": [], "url": "https://x.com"}]}),
    )
    agent = PaperRetrievalAgent(cache=isolated_cache)

    first = agent.run("repeated query", max_results=3)
    second = agent.run("repeated query", max_results=3)

    assert arxiv_mock.call_count == 1
    assert ss_mock.call_count == 1
    assert len(second.documents) == len(first.documents) == 2
    assert second.errors == []


def test_paper_retrieval_node_preserves_prior_errors(mocker, isolated_cache):
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.arxiv.Client.results", return_value=[_fake_arxiv_result()])
    mocker.patch("app.agents.paper_retrieval_agent.requests.get", return_value=FakeResponse({"data": []}))
    state = {"query": "test", "max_paper_results": 1, "errors": []}

    update = paper_retrieval_node(state)

    assert len(update["paper_results"]) == 1
    assert update["errors"] == []
