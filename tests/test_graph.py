r"""
Mocked end-to-end test of the pipeline, through Phase 5:

    planner -> search_all -> retrieve_all -> dedupe_and_rank -> fact_check
        -> writer -> reviewer -(revise, under cap)-> writer
                            \-(approved, or cap reached)-> add_citations -> generate_charts -> END

Every external call (Gemini, web search, ArXiv, Semantic Scholar, and
the embedding model downloads) is mocked. This proves the wiring, state
merging, and revision loop are correct — not that the live services
behave as documented. Run scripts/run_pipeline.py with real keys for that.
"""

from unittest.mock import MagicMock

from app.graph import build_research_graph
from app.schemas import Document, SourceType
from tests.fakes import FakeEmbedder, FakeResponse, FakeSearchProvider
from tests.test_planner import VALID_PLAN_JSON, _fake_gemini_client

FACT_CHECK_JSON = """
{
  "claims": [
    {"text": "Example finding relevant to the sub-question.", "supporting_source_numbers": [1], "contradicting_source_numbers": []}
  ]
}
"""

APPROVE_JSON = '{"decision": "approve", "feedback": ""}'

SINGLE_SUBQ_PLAN_JSON = (
    '{"original_query": "test query", "sub_questions": '
    '[{"question": "q1", "web_query": "q1", "academic_query": "q1"}]}'
)


def _web_doc(title, url, score=None):
    """A web-search Document as a provider hands it back. snippet="c" mirrors
    the old Tavily mock's `content` field, so downstream dedup and citation
    behavior is identical to before the provider-chain refactor."""
    return Document(title=title, url=url, snippet="c", source=SourceType.WEB, relevance_score=score)


def test_pipeline_wires_planner_output_into_looped_agents(mocker, isolated_cache):
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch(
        "app.agents.planner_agent.get_gemini_client",
        return_value=_fake_gemini_client(VALID_PLAN_JSON),  # 2 sub-questions
    )
    web_provider = FakeSearchProvider("exa", documents=[_web_doc("Web result", "https://x.com", 0.5)])
    mocker.patch("app.agents.search_agent._build_provider_chain", return_value=[web_provider])
    mocker.patch("app.agents.paper_retrieval_agent.arxiv.Client.results", return_value=[])
    mocker.patch("app.agents.paper_retrieval_agent.requests.get", return_value=FakeResponse({"data": []}))
    mocker.patch("app.graph.LocalEmbedder", return_value=FakeEmbedder())
    mocker.patch("app.agents.fact_checker_agent.get_gemini_client", return_value=_fake_gemini_client(FACT_CHECK_JSON))
    # supplementary retrieval is a nice-to-have on top of verified_claims;
    # None keeps this test focused on the core wiring rather than also
    # exercising retrieval_index.py, which has its own test file
    mocker.patch("app.graph.build_retrieval_index", return_value=None)
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=_fake_gemini_client("# A drafted report"))
    mocker.patch("app.agents.reviewer_agent.get_gemini_client", return_value=_fake_gemini_client(APPROVE_JSON))
    mocker.patch("app.agents.chart_agent.get_gemini_client", return_value=_fake_gemini_client('{"charts": []}'))

    graph = build_research_graph()
    result = graph.invoke({"query": "test query", "max_results_per_subquestion": 3})

    assert result["errors"] == []
    assert len(result["plan"].sub_questions) == 2
    # one web-search call per sub-question — proves the loop actually ran
    # over the Planner's output rather than a single hardcoded query
    assert web_provider.calls == 2
    # both mocked web-search calls return identical content, so the dedup step
    # should have collapsed them to one — proves dedupe_and_rank actually ran
    assert len(result["final_documents"]) == 1
    assert result["final_documents"][0].sub_question is not None
    assert len(result["verified_claims"]) == 1
    assert result["verified_claims"][0].supporting_sources == result["final_documents"]
    assert result["draft"] == "# A drafted report"
    assert result["review_decision"] == "approve"
    assert result["revision_count"] == 1
    # the draft had no [N] markers, so final_report is unchanged (nothing
    # to cite) — that's correct, not a bug; see test_citations.py for the
    # marker-resolution logic itself
    assert result["final_report"] == "# A drafted report"
    assert result["chart_specs"] == []


def test_pipeline_accumulates_errors_from_every_stage_without_crashing(mocker, isolated_cache):
    """Every external dependency fails at once — nothing mocked to
    succeed. Checks specific expected errors from each of the seven stages
    rather than an exact count, since that count naturally grows as more
    stages get added in later phases."""
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.retry.time.sleep")  # the persistent 429 below would otherwise retry with real delays
    mocker.patch("app.agents.planner_agent.get_gemini_client", return_value=None)  # -> fallback plan
    # No web-search provider configured: the keyed provider reports itself
    # unconfigured and is skipped, so the search stage contributes an error
    # and no documents — exactly what an empty .env would produce.
    mocker.patch(
        "app.agents.search_agent._build_provider_chain",
        return_value=[FakeSearchProvider("exa", requires_key=True, configured=False)],
    )
    mocker.patch("app.agents.paper_retrieval_agent.arxiv.Client.results", side_effect=RuntimeError("arxiv is down"))
    mocker.patch("app.agents.paper_retrieval_agent.requests.get", return_value=FakeResponse({}, status_code=429))
    mocker.patch("app.graph.LocalEmbedder", return_value=FakeEmbedder())

    graph = build_research_graph()
    result = graph.invoke({"query": "test query"})

    errors = result["errors"]
    assert any("fallback plan" in e for e in errors)  # planner
    assert any("not configured" in e for e in errors)  # search
    assert any("ArXiv search failed" in e for e in errors)  # papers
    assert any("Semantic Scholar rate limit" in e for e in errors)  # papers
    assert result["final_documents"] == []
    # with no documents, fact-checking short-circuits per sub-question
    # (nothing to check) rather than erroring — verified_claims is empty,
    # not an error
    assert result["verified_claims"] == []
    # writer/reviewer still ran and still degraded gracefully
    assert any("used an unformatted claims summary" in e for e in errors)  # writer
    assert any("skipped review, draft approved by default" in e for e in errors)  # reviewer
    assert result["review_decision"] == "approve"  # never gets stuck
    # citations has nothing to fail on (no LLM involved) and chart
    # extraction short-circuits cleanly on an empty verified_claims list —
    # "nothing to check" is not the same failure as "the API call failed",
    # so there's no chart-related error here, just an empty result
    assert result["chart_specs"] == []


def test_pipeline_degrades_gracefully_if_embedding_model_unavailable(mocker, isolated_cache):
    """Simulates no internet access to huggingface.co on first run (exactly
    this project's build sandbox) — dedupe_and_rank should return raw,
    unranked results plus a clear error instead of crashing the pipeline."""
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.planner_agent.get_gemini_client", return_value=_fake_gemini_client(VALID_PLAN_JSON))
    mocker.patch(
        "app.agents.search_agent._build_provider_chain",
        return_value=[FakeSearchProvider("exa", documents=[_web_doc("Web result", "https://x.com", 0.5)])],
    )
    mocker.patch("app.agents.paper_retrieval_agent.arxiv.Client.results", return_value=[])
    mocker.patch("app.agents.paper_retrieval_agent.requests.get", return_value=FakeResponse({"data": []}))
    mocker.patch("app.graph.LocalEmbedder", side_effect=OSError("couldn't reach huggingface.co"))

    graph = build_research_graph()
    result = graph.invoke({"query": "test query"})

    assert any("Dedup/ranking unavailable" in e for e in result["errors"])
    assert len(result["final_documents"]) == 2  # raw, undeduped, but present


def test_pipeline_loops_once_then_stops_when_reviewer_approves(mocker, isolated_cache):
    """Isolates the writer/reviewer loop: leaves search/papers/dedupe/fact-
    check unmocked (they fail gracefully with no keys/network either way,
    landing on an empty verified_claims list), and checks that a REVISE
    followed by an APPROVE produces exactly one revision — the second
    Writer call actually sees the first draft and the reviewer's feedback,
    and the loop stops as soon as it's approved."""
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.planner_agent.get_gemini_client", return_value=_fake_gemini_client(SINGLE_SUBQ_PLAN_JSON))

    writer_client = MagicMock()
    writer_client.models.generate_content.side_effect = [
        MagicMock(text="draft v1"),
        MagicMock(text="draft v2, revised"),
    ]
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=writer_client)

    reviewer_client = MagicMock()
    reviewer_client.models.generate_content.side_effect = [
        MagicMock(text='{"decision": "revise", "feedback": "add more detail"}'),
        MagicMock(text=APPROVE_JSON),
    ]
    mocker.patch("app.agents.reviewer_agent.get_gemini_client", return_value=reviewer_client)

    graph = build_research_graph()
    result = graph.invoke({"query": "test query"})

    assert result["draft"] == "draft v2, revised"
    assert result["revision_count"] == 2
    assert writer_client.models.generate_content.call_count == 2
    assert reviewer_client.models.generate_content.call_count == 2

    second_writer_prompt = writer_client.models.generate_content.call_args_list[1].kwargs["contents"]
    assert "draft v1" in second_writer_prompt
    assert "add more detail" in second_writer_prompt


def test_pipeline_stops_at_max_revisions_even_if_reviewer_never_approves(mocker, isolated_cache):
    """A reviewer that always says revise must not be able to loop
    forever — max_revisions (explicitly set to 1 here, not the default)
    should cap it after exactly one review pass."""
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.planner_agent.get_gemini_client", return_value=_fake_gemini_client(SINGLE_SUBQ_PLAN_JSON))

    writer_client = MagicMock()
    writer_client.models.generate_content.return_value = MagicMock(text="a draft")
    mocker.patch("app.agents.writer_agent.get_gemini_client", return_value=writer_client)

    reviewer_client = MagicMock()
    reviewer_client.models.generate_content.return_value = MagicMock(
        text='{"decision": "revise", "feedback": "still not good enough"}'
    )
    mocker.patch("app.agents.reviewer_agent.get_gemini_client", return_value=reviewer_client)

    graph = build_research_graph()
    result = graph.invoke({"query": "test query", "max_revisions": 1})

    assert result["revision_count"] == 1
    assert writer_client.models.generate_content.call_count == 1
    assert reviewer_client.models.generate_content.call_count == 1
    assert result["review_decision"] == "revise"  # capped, not actually approved


def test_pipeline_resolves_citations_and_extracts_charts(mocker, isolated_cache):
    """Traces a [1] marker the (mocked) Writer places in its draft all the
    way to a correctly formatted bibliography entry for the actual source
    that ended up as claim #1's supporting source — not just that a
    References section exists, but that it names the right thing."""
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.planner_agent.get_gemini_client", return_value=_fake_gemini_client(SINGLE_SUBQ_PLAN_JSON))
    mocker.patch(
        "app.agents.search_agent._build_provider_chain",
        return_value=[
            FakeSearchProvider(
                "exa",
                documents=[_web_doc("Definitive Source", "https://definitive.example/paper", 0.9)],
            )
        ],
    )
    mocker.patch("app.agents.paper_retrieval_agent.arxiv.Client.results", return_value=[])
    mocker.patch("app.agents.paper_retrieval_agent.requests.get", return_value=FakeResponse({"data": []}))
    mocker.patch("app.graph.LocalEmbedder", return_value=FakeEmbedder())
    mocker.patch(
        "app.agents.fact_checker_agent.get_gemini_client",
        return_value=_fake_gemini_client(FACT_CHECK_JSON),  # cites source [1]
    )
    mocker.patch("app.graph.build_retrieval_index", return_value=None)
    # Simulates what a real Writer call would produce given a numbered
    # source list — a draft that actually places a [1] marker.
    mocker.patch(
        "app.agents.writer_agent.get_gemini_client",
        return_value=_fake_gemini_client("# Report\n\nThe key finding holds up well [1].\n"),
    )
    mocker.patch("app.agents.reviewer_agent.get_gemini_client", return_value=_fake_gemini_client(APPROVE_JSON))
    mocker.patch(
        "app.agents.chart_agent.get_gemini_client",
        return_value=_fake_gemini_client(
            '{"charts": [{"title": "T", "chart_type": "bar", "x_label": "X", "y_label": "Y", '
            '"labels": ["A", "B"], "values": [1, 2]}]}'
        ),
    )

    result = build_research_graph().invoke({"query": "test query", "max_results_per_subquestion": 3})

    assert "## References" in result["final_report"]
    assert "Definitive Source" in result["final_report"]
    assert "definitive.example" in result["final_report"]
    assert len(result["chart_specs"]) == 1
    assert result["chart_specs"][0].title == "T"
