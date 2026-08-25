"""
Tests for the FastAPI endpoints added in Phase 6: /research/stream (SSE)
and /reports/pdf. These were also verified live against a running server
(including through the Vite dev proxy) during development — these are the
permanent, re-runnable versions of those checks.

TestClient buffers the full streamed response for `.text`, which is all
that's needed to verify the SSE framing and event sequence; it doesn't
need to actually consume the response incrementally the way a browser would.
"""

import io
import json

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.config import Settings
from app.main import app

client = TestClient(app)

NO_KEYS_SETTINGS = Settings.model_construct(
    tavily_api_key="",
    semantic_scholar_api_key="",
    gemini_api_key="",
    gemini_model="x",
    groq_api_key="",
    groq_model="x",
    default_web_results=5,
    default_paper_results=5,
    request_timeout_seconds=20,
)


def _parse_sse_events(response_text: str) -> list[dict]:
    events = []
    for frame in response_text.split("\n\n"):
        line = frame.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_research_stream_has_sse_content_type_and_covers_every_stage(mocker, isolated_cache):
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.planner_agent.get_gemini_client", return_value=None)
    mocker.patch("app.agents.search_agent.get_settings", return_value=NO_KEYS_SETTINGS)
    mocker.patch("app.agents.paper_retrieval_agent.arxiv.Client.results", side_effect=RuntimeError("down"))
    mocker.patch("app.agents.paper_retrieval_agent.requests.get", side_effect=RuntimeError("down"))
    mocker.patch("app.graph.LocalEmbedder", side_effect=RuntimeError("no network"))

    response = client.post("/research/stream", json={"query": "test query", "num_sub_questions": 1})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse_events(response.text)
    stage_events = [e for e in events if e["type"] == "stage"]
    stages_seen = {e["stage"] for e in stage_events}

    assert stages_seen == {
        "planner", "search_all", "retrieve_all", "dedupe_and_rank",
        "fact_check", "writer", "reviewer", "add_citations", "generate_charts",
    }
    # every stage event carries a human-readable summary, not just a bare stage name
    assert all(e["summary"] for e in stage_events)


def test_research_stream_final_event_carries_the_complete_serialized_result(mocker, isolated_cache):
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.planner_agent.get_gemini_client", return_value=None)
    mocker.patch("app.agents.search_agent.get_settings", return_value=NO_KEYS_SETTINGS)
    mocker.patch("app.agents.paper_retrieval_agent.arxiv.Client.results", return_value=[])
    mocker.patch("app.agents.paper_retrieval_agent.requests.get", side_effect=RuntimeError("down"))
    mocker.patch("app.graph.LocalEmbedder", side_effect=RuntimeError("no network"))

    response = client.post("/research/stream", json={"query": "test query", "num_sub_questions": 1})
    events = _parse_sse_events(response.text)

    complete_events = [e for e in events if e["type"] == "complete"]
    assert len(complete_events) == 1
    result = complete_events[0]["result"]
    # must be plain JSON-safe data (Pydantic objects/enums resolved), not raise on access
    assert result["plan"]["original_query"] == "test query"
    assert isinstance(result["errors"], list)
    assert isinstance(result["verified_claims"], list)


def test_reports_pdf_renders_a_precomputed_report_without_running_the_pipeline():
    response = client.post(
        "/reports/pdf",
        json={
            "title": "A Precomputed Report",
            "final_report": "# A Precomputed Report\n\nSome findings [1].\n\n## References\n\n1. Test Source. (2024). Web. https://example.com",
            "chart_specs": [],
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    text = PdfReader(io.BytesIO(response.content)).pages[0].extract_text()
    assert "A Precomputed Report" in text
    assert "Test Source" in text


def test_reports_pdf_embeds_provided_charts():
    response = client.post(
        "/reports/pdf",
        json={
            "title": "Report With A Chart",
            "final_report": "# Report With A Chart\n\nSome findings.\n",
            "chart_specs": [
                {
                    "title": "Reported values",
                    "chart_type": "bar",
                    "x_label": "Source",
                    "y_label": "Units",
                    "labels": ["A", "B"],
                    "values": [1.0, 2.0],
                }
            ],
        },
    )

    assert response.status_code == 200
    text = PdfReader(io.BytesIO(response.content)).pages[0].extract_text()
    assert "Data Visualizations" in text


# --------------------------------------------------------- top-level safety net

def test_research_survives_a_genuinely_unanticipated_crash(mocker, isolated_cache):
    """Every node already has its own try/except for its own external
    calls — this simulates a bug *outside* any of that (add_citations_node
    has no try/except of its own at all), to prove the outer safety net in
    _invoke_pipeline catches what the per-node fallbacks don't, rather
    than a raw 500 reaching the caller."""
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.graph.build_source_index", side_effect=RuntimeError("unanticipated citation bug"))

    response = client.post("/research", json={"query": "test query", "num_sub_questions": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["original_query"] == "test query"
    assert any("Pipeline failed unexpectedly" in e for e in body["errors"])


def test_research_stream_sends_a_complete_event_even_after_an_unanticipated_crash(mocker, isolated_cache):
    mocker.patch("app.agents.search_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.agents.paper_retrieval_agent.get_default_cache", return_value=isolated_cache)
    mocker.patch("app.graph.build_source_index", side_effect=RuntimeError("unanticipated citation bug"))

    response = client.post("/research/stream", json={"query": "test query", "num_sub_questions": 1})
    events = _parse_sse_events(response.text)

    # the frontend must never be left with only stage events and no
    # resolution — an error event AND a complete event should both arrive
    assert any(e["type"] == "error" for e in events)
    complete_events = [e for e in events if e["type"] == "complete"]
    assert len(complete_events) == 1
    result = complete_events[0]["result"]
    assert result["plan"]["original_query"] == "test query"
    assert any("Pipeline failed unexpectedly" in e for e in result["errors"])
