"""
Mocked tests for the Planner — no live Gemini calls. Verifies the
structured-output parsing and, importantly, the fallback path: a failed or
malformed LLM response should degrade to a usable single-question plan
plus a visible error, never a crash.
"""

from unittest.mock import MagicMock

from app.agents.planner_agent import PlannerAgent, planner_node
from app.schemas import ResearchPlan

VALID_PLAN_JSON = """
{
  "original_query": "impact of microplastics on marine food webs",
  "sub_questions": [
    {
      "question": "What are the main sources of ocean microplastics?",
      "web_query": "where do ocean microplastics come from",
      "academic_query": "sources and pathways of marine microplastic pollution"
    },
    {
      "question": "How do microplastics enter marine food webs?",
      "web_query": "how microplastics get into fish and seafood",
      "academic_query": "trophic transfer of microplastics in marine ecosystems"
    }
  ]
}
"""


def _fake_gemini_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=response_text)
    return client


def test_planner_parses_structured_gemini_response(mocker):
    mocker.patch(
        "app.agents.planner_agent.get_gemini_client",
        return_value=_fake_gemini_client(VALID_PLAN_JSON),
    )

    plan, errors = PlannerAgent().run("impact of microplastics on marine food webs")

    assert errors == []
    assert len(plan.sub_questions) == 2
    assert plan.sub_questions[0].web_query == "where do ocean microplastics come from"
    assert plan.sub_questions[1].academic_query == "trophic transfer of microplastics in marine ecosystems"


def test_planner_falls_back_when_no_key_configured(mocker):
    mocker.patch("app.agents.planner_agent.get_gemini_client", return_value=None)

    plan, errors = PlannerAgent().run("test query")

    assert len(plan.sub_questions) == 1
    assert plan.sub_questions[0].question == "test query"
    assert any("GEMINI_API_KEY" in e for e in errors)


def test_planner_falls_back_on_malformed_json(mocker):
    mocker.patch(
        "app.agents.planner_agent.get_gemini_client",
        return_value=_fake_gemini_client("this is not valid json"),
    )

    plan, errors = PlannerAgent().run("test query")

    assert len(plan.sub_questions) == 1
    assert plan.sub_questions[0].question == "test query"
    assert any("fallback" in e for e in errors)


def test_planner_falls_back_on_empty_sub_questions(mocker):
    mocker.patch(
        "app.agents.planner_agent.get_gemini_client",
        return_value=_fake_gemini_client('{"original_query": "x", "sub_questions": []}'),
    )

    plan, errors = PlannerAgent().run("test query")

    assert len(plan.sub_questions) == 1  # fallback kicked in
    assert errors  # not silent


def test_planner_node_preserves_prior_errors_and_writes_plan(mocker):
    mocker.patch(
        "app.agents.planner_agent.get_gemini_client",
        return_value=_fake_gemini_client(VALID_PLAN_JSON),
    )
    state = {"query": "test", "errors": ["prior error"]}

    update = planner_node(state)

    assert isinstance(update["plan"], ResearchPlan)
    assert len(update["plan"].sub_questions) == 2
    assert update["errors"] == ["prior error"]


class _FakeAPIError(Exception):
    """Stands in for google.genai.errors.APIError's shape - a `.code`
    attribute is all is_retryable_http_error actually looks at."""

    def __init__(self, code: int):
        self.code = code
        super().__init__(f"API error {code}")


def test_planner_retries_a_transient_rate_limit_then_succeeds(mocker):
    mocker.patch("app.retry.time.sleep")  # skip real backoff delays
    client = MagicMock()
    client.models.generate_content.side_effect = [
        _FakeAPIError(429),
        MagicMock(text=VALID_PLAN_JSON),
    ]
    mocker.patch("app.agents.planner_agent.get_gemini_client", return_value=client)

    plan, errors = PlannerAgent().run("impact of microplastics on marine food webs")

    assert errors == []
    assert len(plan.sub_questions) == 2
    assert client.models.generate_content.call_count == 2  # failed once, retried, then succeeded
