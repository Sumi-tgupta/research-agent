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
from app.agents.search_agent import SearchAgent, search_agent_node
from app.cache import Cache
from app.config import Settings
from app.schemas import SourceType
from tests.fakes import FakeResponse

FAKE_SETTINGS = Settings.model_construct(
    tavily_api_key="",
    semantic_scholar_api_key="",
    gemini_api_key="",
    gemini_model="gemini-2.5-flash",
    groq_api_key="",
    groq_model="llama-3.3-70b-versatile",
    default_web_results=5,
    default_paper_results=5,
    request_timeout_seconds=20,
)

# search_agent_node() builds `SearchAgent()` with no args, so it always reads
# the key from settings — this variant has one set, for tests that need the
# client to actually get constructed (so the mocked .search() call is reached).
FAKE_SETTINGS_WITH_TAVILY_KEY = FAKE_SETTINGS.model_copy(update={"tavily_api_key": "fake-tavily-key"})


def _fake_arxiv_result(title: str = "A Fake Paper About Testing") -> arxiv.Result:
    return arxiv.Result(
        entry_id="https://arxiv.org/abs/1234.5678",
        title=title,
        authors=[arxiv.Result.Author(name="Ada Lovelace")],
        summary="This is a fake abstract used for testing.",
    )


# ---------------------------------------------------------------- Search Agent

def test_search_agent_normalizes_tavily_results(mocker, isolated_cache):
    mocker.patch(
        "app.agents.search_agent.TavilyClient.search",
        return_value={
            "results": [
                {"title": "Example result", "url": "https://example.com/a", "content": "some snippet", "score": 0.87},
                {"title": "Second result", "url": "https://example.com/b", "content": "another snippet", "score": 0.5},
            ]
        },
    )

    result = SearchAgent(api_key="test-key", cache=isolated_cache).run("test query", max_results=2)

    assert result.source_agent == "search_agent"
    assert result.errors == []
    assert len(result.documents) == 2
    assert result.documents[0].title == "Example result"
    assert result.documents[0].source == SourceType.WEB
    assert result.documents[0].relevance_score == 0.87


def test_search_agent_missing_key_reports_error_without_calling_network(mocker, isolated_cache):
    mocker.patch("app.agents.search_agent.get_settings", return_value=FAKE_SETTINGS)
    # If this test is wrong and a client gets built anyway, failing loudly
    # here is much better than silently making a real HTTP call.
    search_mock = mocker.patch("app.agents.search_agent.TavilyClient.search")

    result = SearchAgent(api_key="", cache=isolated_cache).run("test query")

    assert result.documents == []
    assert any("not configured" in e for e in result.errors)
    search_mock.assert_not_called()


def test_search_agent_node_preserves_prior_errors(mocker, isolated_cache):
    mocker.patch("app.agents.search_agent.get_settings", return_value=FAKE_SETTINGS_WITH_TAVILY_KEY)
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch(
        "app.agents.search_agent.TavilyClient.search",
        return_value={"results": [{"title": "T", "url": "https://x.com", "content": "c", "score": 0.1}]},
    )
    state = {"query": "test", "max_web_results": 1, "errors": ["prior error"]}

    update = search_agent_node(state)

    assert len(update["web_results"]) == 1
    assert update["errors"] == ["prior error"]


def test_search_agent_second_identical_call_hits_cache_not_the_network(mocker, isolated_cache):
    search_mock = mocker.patch(
        "app.agents.search_agent.TavilyClient.search",
        return_value={"results": [{"title": "Cached-ish result", "url": "https://x.com", "content": "c", "score": 0.5}]},
    )
    agent = SearchAgent(api_key="test-key", cache=isolated_cache)

    first = agent.run("repeated query", max_results=3)
    second = agent.run("repeated query", max_results=3)

    assert search_mock.call_count == 1  # the second call was served entirely from cache
    assert second.documents == first.documents
    assert second.errors == []


def test_search_agent_retries_a_transient_timeout_then_succeeds(mocker, isolated_cache):
    from tavily.errors import TimeoutError as TavilyTimeoutError

    mocker.patch("app.retry.time.sleep")  # skip real backoff delays
    call_count = {"n": 0}

    def flaky_search(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise TavilyTimeoutError("temporary timeout")
        return {"results": [{"title": "Recovered result", "url": "https://x.com", "content": "c", "score": 0.5}]}

    mocker.patch("app.agents.search_agent.TavilyClient.search", side_effect=flaky_search)

    result = SearchAgent(api_key="test-key", cache=isolated_cache).run("test query")

    assert result.errors == []
    assert len(result.documents) == 1
    assert call_count["n"] == 2  # failed once, retried, then succeeded


def test_search_agent_does_not_retry_invalid_api_key(mocker, isolated_cache):
    from tavily.errors import InvalidAPIKeyError

    mocker.patch("app.retry.time.sleep")
    search_mock = mocker.patch(
        "app.agents.search_agent.TavilyClient.search", side_effect=InvalidAPIKeyError("bad key")
    )

    result = SearchAgent(api_key="test-key", cache=isolated_cache).run("test query")

    assert search_mock.call_count == 1  # never retried
    assert any("key invalid" in e for e in result.errors)


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
